# backend/api/eval.py
# 功能: Eval V2 API - 基于 Task 的可组合评估体系
# 主要路由:
#   - /api/eval/config: 获取可用的 simulator_types, interaction_modes, grader_types
#   - /api/eval/personas/{project_id}: 获取项目的消费者画像（来自消费者调研）
#   - /api/eval/runs/{project_id}: CRUD EvalRun
#   - /api/eval/run/{run_id}/tasks: CRUD EvalTask
#   - /api/eval/run/{run_id}/execute: 执行评估（并行执行所有 Task）
#   - /api/eval/task/{task_id}/execute: 执行单个 Task
#   - /api/eval/run/{run_id}/trials: 获取所有 Trial
#   - /api/eval/trial/{trial_id}: 获取 Trial 详情（含完整 LLM 日志）
#   - /api/eval/run/{run_id}/diagnose: 运行综合诊断
#   - /api/eval/generate-for-block/{block_id}: 为 ContentBlock 字段生成评估
# 数据结构: EvalRun, EvalTask, EvalTrial

"""
Eval V2 API
基于 Task 的可组合评估体系
EvalRun → EvalTask[] → EvalTrial[]
每个 Trial 记录完整 LLM 调用日志
"""

import json
import asyncio
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel as PydanticBase
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import (
    Project,
    ContentBlock,
    CreatorProfile,
    EvalRun,
    EvalTask,
    EvalTrial,
    EVAL_ROLES,
    SIMULATOR_TYPES,
    INTERACTION_MODES,
    GRADER_TYPES,
    GenerationLog,
    generate_uuid,
)
from core.tools.eval_engine import (
    run_eval,
    run_task_trial,
    run_diagnoser,
    format_trial_result_markdown,
    format_diagnosis_markdown,
    TrialResult,
)


router = APIRouter(prefix="/api/eval", tags=["eval"])


# ============== Schemas ==============

class CreateEvalRunRequest(PydanticBase):
    """创建评估运行"""
    project_id: str
    name: str = "综合评估"

class UpdateEvalRunRequest(PydanticBase):
    """更新评估运行"""
    name: Optional[str] = None
    config: Optional[dict] = None

class CreateEvalTaskRequest(PydanticBase):
    """创建评估任务"""
    name: str
    simulator_type: str = "coach"          # coach/editor/expert/consumer/seller/custom
    interaction_mode: str = "review"       # review/dialogue/scenario
    simulator_config: Optional[dict] = None
    persona_config: Optional[dict] = None  # {name, background, pain_points, ...}
    target_block_ids: Optional[List[str]] = None
    grader_config: Optional[dict] = None   # {type, dimensions, criteria, custom_prompt}
    order_index: Optional[int] = None

class UpdateEvalTaskRequest(PydanticBase):
    """更新评估任务"""
    name: Optional[str] = None
    simulator_type: Optional[str] = None
    interaction_mode: Optional[str] = None
    simulator_config: Optional[dict] = None
    persona_config: Optional[dict] = None
    target_block_ids: Optional[list] = None
    grader_config: Optional[dict] = None
    order_index: Optional[int] = None

class BatchCreateTasksRequest(PydanticBase):
    """批量创建任务（全回归模板）"""
    project_id: str
    eval_run_id: str
    template: str = "full_regression"  # full_regression / review_only / dialogue_only / custom
    persona_ids: Optional[List[str]] = None  # 选定的 persona block IDs
    custom_tasks: Optional[List[CreateEvalTaskRequest]] = None  # template=custom 时使用

class RunEvalRequest(PydanticBase):
    """运行评估（兼容旧接口）"""
    project_id: str
    name: str = "综合评估"
    roles: List[str] = ["coach", "editor", "expert", "consumer", "seller"]
    input_block_ids: Optional[List[str]] = None
    max_turns: int = 5
    personas: Optional[List[dict]] = None

class EvalRunResponse(PydanticBase):
    id: str
    project_id: str
    name: str
    status: str
    summary: str
    overall_score: Optional[float]
    role_scores: dict
    trial_count: int
    content_block_id: Optional[str]
    config: dict
    created_at: str
    model_config = {"from_attributes": True}

class EvalTaskResponse(PydanticBase):
    id: str
    eval_run_id: str
    name: str
    simulator_type: str
    interaction_mode: str
    simulator_config: dict
    persona_config: dict
    target_block_ids: list
    grader_config: dict
    order_index: int
    status: str
    error: str
    created_at: str
    model_config = {"from_attributes": True}

class EvalTrialResponse(PydanticBase):
    id: str
    eval_run_id: str
    eval_task_id: Optional[str]
    role: str
    role_config: dict
    interaction_mode: str
    input_block_ids: list
    persona: dict
    nodes: list
    result: dict
    grader_outputs: list
    llm_calls: list
    overall_score: Optional[float]
    status: str
    error: str
    tokens_in: int
    tokens_out: int
    cost: float
    created_at: str
    model_config = {"from_attributes": True}


# ============== Config Routes ==============

@router.get("/config")
def get_eval_config():
    """获取评估系统可用配置项"""
    return {
        "simulator_types": SIMULATOR_TYPES,
        "interaction_modes": INTERACTION_MODES,
        "grader_types": GRADER_TYPES,
        "roles": EVAL_ROLES,
    }


@router.get("/personas/{project_id}")
def get_project_personas(project_id: str, db: Session = Depends(get_db)):
    """获取项目的消费者画像（来自消费者调研 ContentBlock）"""
    personas = _get_project_personas_from_research(project_id, db)
    return {"personas": personas}


# ============== EvalRun CRUD ==============

@router.get("/runs/{project_id}", response_model=List[EvalRunResponse])
def list_eval_runs(project_id: str, db: Session = Depends(get_db)):
    """获取项目的所有评估运行"""
    runs = (
        db.query(EvalRun)
        .filter(EvalRun.project_id == project_id)
        .order_by(EvalRun.created_at.desc())
        .all()
    )
    return [_to_run_response(r) for r in runs]


@router.post("/runs", response_model=EvalRunResponse)
def create_eval_run(request: CreateEvalRunRequest, db: Session = Depends(get_db)):
    """创建新的评估运行（空运行，之后再添加 Task）"""
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    run = EvalRun(
        id=generate_uuid(),
        project_id=project.id,
        name=request.name,
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return _to_run_response(run)


@router.get("/run/{run_id}", response_model=EvalRunResponse)
def get_eval_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    return _to_run_response(run)


@router.put("/run/{run_id}", response_model=EvalRunResponse)
def update_eval_run(run_id: str, request: UpdateEvalRunRequest, db: Session = Depends(get_db)):
    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    if request.name is not None:
        run.name = request.name
    if request.config is not None:
        run.config = request.config
    db.commit()
    db.refresh(run)
    return _to_run_response(run)


@router.delete("/run/{run_id}")
def delete_eval_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    db.query(EvalTrial).filter(EvalTrial.eval_run_id == run_id).delete()
    db.query(EvalTask).filter(EvalTask.eval_run_id == run_id).delete()
    db.delete(run)
    db.commit()
    return {"message": "已删除"}


# ============== EvalTask CRUD ==============

@router.get("/run/{run_id}/tasks", response_model=List[EvalTaskResponse])
def list_eval_tasks(run_id: str, db: Session = Depends(get_db)):
    """获取 EvalRun 的所有 Task"""
    tasks = (
        db.query(EvalTask)
        .filter(EvalTask.eval_run_id == run_id)
        .order_by(EvalTask.order_index)
        .all()
    )
    return [_to_task_response(t) for t in tasks]


@router.post("/run/{run_id}/tasks", response_model=EvalTaskResponse)
def create_eval_task(run_id: str, request: CreateEvalTaskRequest, db: Session = Depends(get_db)):
    """创建单个 Task"""
    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    
    # 自动 order_index
    max_order = db.query(EvalTask).filter(EvalTask.eval_run_id == run_id).count()
    
    task = EvalTask(
        id=generate_uuid(),
        eval_run_id=run_id,
        name=request.name,
        simulator_type=request.simulator_type,
        interaction_mode=request.interaction_mode,
        simulator_config=request.simulator_config or {
            "system_prompt": "",
            "max_turns": 5,
            "feedback_mode": "structured",
        },
        persona_config=request.persona_config or {},
        target_block_ids=request.target_block_ids or [],
        grader_config=request.grader_config or {
            "type": "content",
            "dimensions": [],
            "criteria": {},
            "custom_prompt": "",
        },
        order_index=request.order_index if request.order_index is not None else max_order,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _to_task_response(task)


@router.put("/task/{task_id}", response_model=EvalTaskResponse)
def update_eval_task(task_id: str, request: UpdateEvalTaskRequest, db: Session = Depends(get_db)):
    """更新 Task 配置"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")
    
    for field_name in ["name", "simulator_type", "interaction_mode", "simulator_config",
                       "persona_config", "target_block_ids", "grader_config", "order_index"]:
        val = getattr(request, field_name)
        if val is not None:
            setattr(task, field_name, val)
    
    db.commit()
    db.refresh(task)
    return _to_task_response(task)


@router.delete("/task/{task_id}")
def delete_eval_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")
    db.query(EvalTrial).filter(EvalTrial.eval_task_id == task_id).delete()
    db.delete(task)
    db.commit()
    return {"message": "已删除"}


@router.post("/run/{run_id}/batch-tasks")
def batch_create_tasks(request: BatchCreateTasksRequest, db: Session = Depends(get_db)):
    """批量创建 Tasks（使用模板，如全回归）"""
    run = db.query(EvalRun).filter(EvalRun.id == request.eval_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    
    # 获取 personas
    personas = []
    if request.persona_ids:
        for pid in request.persona_ids:
            persona = _get_persona_by_block_id(pid, db)
            if persona:
                personas.append(persona)
    
    if not personas:
        personas = _get_project_personas_from_research(request.project_id, db)
    if not personas:
        personas = [{"name": "典型用户", "background": "对该领域感兴趣的普通读者"}]
    
    tasks_to_create = []
    
    if request.template == "full_regression":
        # 全回归模板：3个审查 + 消费者对话 × N personas + 销售对话 × N personas
        order = 0
        for role in ["coach", "editor", "expert"]:
            type_info = SIMULATOR_TYPES.get(role, {})
            tasks_to_create.append({
                "name": f"{type_info.get('name', role)}审查",
                "simulator_type": role,
                "interaction_mode": "review",
                "grader_config": {"type": "content", "dimensions": type_info.get("default_dimensions", [])},
                "order_index": order,
            })
            order += 1
        
        for persona in personas:
            p_name = persona.get("name", "用户")
            tasks_to_create.append({
                "name": f"消费者对话-{p_name}",
                "simulator_type": "consumer",
                "interaction_mode": "dialogue",
                "persona_config": persona,
                "simulator_config": {"max_turns": 5, "feedback_mode": "structured"},
                "grader_config": {"type": "combined", "dimensions": SIMULATOR_TYPES.get("consumer", {}).get("default_dimensions", [])},
                "order_index": order,
            })
            order += 1
        
        for persona in personas:
            p_name = persona.get("name", "用户")
            tasks_to_create.append({
                "name": f"销售测试-{p_name}",
                "simulator_type": "seller",
                "interaction_mode": "dialogue",
                "persona_config": persona,
                "simulator_config": {"max_turns": 8, "feedback_mode": "structured"},
                "grader_config": {"type": "combined", "dimensions": SIMULATOR_TYPES.get("seller", {}).get("default_dimensions", [])},
                "order_index": order,
            })
            order += 1
    
    elif request.template == "review_only":
        for i, role in enumerate(["coach", "editor", "expert"]):
            type_info = SIMULATOR_TYPES.get(role, {})
            tasks_to_create.append({
                "name": f"{type_info.get('name', role)}审查",
                "simulator_type": role,
                "interaction_mode": "review",
                "grader_config": {"type": "content", "dimensions": type_info.get("default_dimensions", [])},
                "order_index": i,
            })
    
    elif request.template == "dialogue_only":
        order = 0
        for persona in personas:
            p_name = persona.get("name", "用户")
            tasks_to_create.append({
                "name": f"消费者对话-{p_name}",
                "simulator_type": "consumer",
                "interaction_mode": "dialogue",
                "persona_config": persona,
                "grader_config": {"type": "combined", "dimensions": []},
                "order_index": order,
            })
            order += 1
    
    elif request.template == "custom" and request.custom_tasks:
        for i, ct in enumerate(request.custom_tasks):
            tasks_to_create.append({
                "name": ct.name,
                "simulator_type": ct.simulator_type,
                "interaction_mode": ct.interaction_mode,
                "simulator_config": ct.simulator_config or {},
                "persona_config": ct.persona_config or {},
                "target_block_ids": ct.target_block_ids or [],
                "grader_config": ct.grader_config or {},
                "order_index": ct.order_index or i,
            })
    
    # 创建 Tasks
    created_tasks = []
    for task_data in tasks_to_create:
        task = EvalTask(
            id=generate_uuid(),
            eval_run_id=request.eval_run_id,
            name=task_data.get("name", "未命名任务"),
            simulator_type=task_data.get("simulator_type", "coach"),
            interaction_mode=task_data.get("interaction_mode", "review"),
            simulator_config=task_data.get("simulator_config", {"max_turns": 5}),
            persona_config=task_data.get("persona_config", {}),
            target_block_ids=task_data.get("target_block_ids", []),
            grader_config=task_data.get("grader_config", {"type": "content"}),
            order_index=task_data.get("order_index", 0),
        )
        db.add(task)
        created_tasks.append(task)
    
    db.commit()
    return {
        "message": f"创建了 {len(created_tasks)} 个任务",
        "tasks": [_to_task_response(t) for t in created_tasks],
    }


# ============== Execute ==============

@router.post("/run/{run_id}/execute")
async def execute_eval_run(run_id: str, db: Session = Depends(get_db)):
    """
    执行 EvalRun 的所有 Task（并行执行）
    每个 Task 产生一个 Trial，记录完整 LLM 调用日志
    """
    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    
    tasks = (
        db.query(EvalTask)
        .filter(EvalTask.eval_run_id == run_id, EvalTask.status.in_(["pending", "failed"]))
        .order_by(EvalTask.order_index)
        .all()
    )
    
    if not tasks:
        raise HTTPException(status_code=400, detail="没有待执行的 Task")
    
    project = db.query(Project).filter(Project.id == run.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 收集项目内容
    content, field_names = _collect_content(project.id, None, db, exclude_eval=True)
    if not content:
        raise HTTPException(status_code=400, detail="项目中没有可评估的内容")
    
    creator_profile = _get_creator_profile(project, db)
    intent = _get_project_intent(project, db)
    
    run.status = "running"
    db.commit()
    
    try:
        # 并行执行所有 Task
        async_tasks = []
        for task in tasks:
            task.status = "running"
            
            # 确定目标内容
            task_content = content
            task_field_names = field_names
            if task.target_block_ids:
                task_content, task_field_names = _collect_content(
                    project.id, task.target_block_ids, db
                )
            
            async_tasks.append(_execute_single_task(
                task, task_content, creator_profile, intent, task_field_names
            ))
        
        db.commit()  # commit status updates
        
        results = await asyncio.gather(*async_tasks, return_exceptions=True)
        
        # 保存结果
        role_scores = {}
        all_trial_results = []
        
        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                task.status = "failed"
                task.error = str(result)
                continue
            
            tr: TrialResult = result
            
            # 创建 Trial
            trial = EvalTrial(
                id=generate_uuid(),
                eval_run_id=run.id,
                eval_task_id=task.id,
                role=tr.role,
                role_config={"simulator_type": task.simulator_type},
                interaction_mode=tr.interaction_mode,
                input_block_ids=task.target_block_ids or [],
                persona=task.persona_config or {},
                nodes=tr.nodes,
                result=tr.result,
                grader_outputs=tr.grader_outputs,
                llm_calls=tr.llm_calls,
                overall_score=tr.overall_score,
                status="completed" if tr.success else "failed",
                error=tr.error,
                tokens_in=tr.tokens_in,
                tokens_out=tr.tokens_out,
                cost=tr.cost,
            )
            db.add(trial)
            
            task.status = "completed" if tr.success else "failed"
            task.error = tr.error
            
            if tr.success:
                role_scores[task.name] = tr.overall_score
                all_trial_results.append(tr)
            
            # GenerationLog
            gen_log = GenerationLog(
                id=generate_uuid(),
                project_id=project.id,
                operation=f"eval_task_{task.simulator_type}_{task.interaction_mode}",
                prompt_input=f"EvalTask: {task.name}",
                prompt_output=tr.result.get("summary", "")[:500],
                tokens_in=tr.tokens_in,
                tokens_out=tr.tokens_out,
                cost=tr.cost,
                model="default",
                duration_ms=0,
                status="success" if tr.success else "failed",
            )
            db.add(gen_log)
            
        # 运行诊断
        if all_trial_results:
            diagnosis, diag_call = await run_diagnoser(
                all_trial_results, content[:500], intent
            )
            run.summary = diagnosis.get("summary", "")
            run.overall_score = diagnosis.get("overall_score", 0)
        
        run.status = "completed"
        run.role_scores = role_scores
        run.trial_count = len(results)
        
        db.commit()
        db.refresh(run)
        
        return {
            "message": f"评估完成，执行了 {len(results)} 个 Task",
            "run": _to_run_response(run),
        }
        
    except Exception as e:
        run.status = "failed"
        run.summary = f"评估失败: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail=f"评估运行失败: {str(e)}")


@router.post("/task/{task_id}/execute")
async def execute_single_task(task_id: str, db: Session = Depends(get_db)):
    """执行单个 Task"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")
    
    run = db.query(EvalRun).filter(EvalRun.id == task.eval_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    
    project = db.query(Project).filter(Project.id == run.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    content, field_names = _collect_content(
        project.id, task.target_block_ids or None, db, exclude_eval=True
    )
    if not content:
        raise HTTPException(status_code=400, detail="没有可评估的内容")
    
    creator_profile = _get_creator_profile(project, db)
    intent = _get_project_intent(project, db)
    
    task.status = "running"
    db.commit()
    
    try:
        tr = await _execute_single_task(task, content, creator_profile, intent, field_names)
        
        trial = EvalTrial(
            id=generate_uuid(),
            eval_run_id=run.id,
            eval_task_id=task.id,
            role=tr.role,
            role_config={"simulator_type": task.simulator_type},
            interaction_mode=tr.interaction_mode,
            input_block_ids=task.target_block_ids or [],
            persona=task.persona_config or {},
            nodes=tr.nodes,
            result=tr.result,
            grader_outputs=tr.grader_outputs,
            llm_calls=tr.llm_calls,
            overall_score=tr.overall_score,
            status="completed" if tr.success else "failed",
            error=tr.error,
            tokens_in=tr.tokens_in,
            tokens_out=tr.tokens_out,
            cost=tr.cost,
        )
        db.add(trial)
        
        task.status = "completed" if tr.success else "failed"
        task.error = tr.error
        db.commit()
        db.refresh(trial)
        
        return _to_trial_response(trial)
        
    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Task 执行失败: {str(e)}")


async def _execute_single_task(
    task: EvalTask,
    content: str,
    creator_profile: str,
    intent: str,
    field_names: list,
) -> TrialResult:
    """内部：执行一个 Task"""
    return await run_task_trial(
        simulator_type=task.simulator_type,
        interaction_mode=task.interaction_mode,
                content=content,
                creator_profile=creator_profile,
                intent=intent,
        persona=task.persona_config if task.persona_config else None,
        simulator_config=task.simulator_config,
        grader_config=task.grader_config,
                    content_field_names=field_names,
                )


# ============== Trials ==============

@router.get("/run/{run_id}/trials", response_model=List[EvalTrialResponse])
def get_eval_trials(run_id: str, db: Session = Depends(get_db)):
    trials = (
        db.query(EvalTrial)
        .filter(EvalTrial.eval_run_id == run_id)
        .order_by(EvalTrial.created_at)
        .all()
    )
    return [_to_trial_response(t) for t in trials]


@router.get("/trial/{trial_id}", response_model=EvalTrialResponse)
def get_eval_trial(trial_id: str, db: Session = Depends(get_db)):
    trial = db.query(EvalTrial).filter(EvalTrial.id == trial_id).first()
    if not trial:
        raise HTTPException(status_code=404, detail="EvalTrial not found")
        return _to_trial_response(trial)
        

# ============== Diagnosis ==============

@router.post("/run/{run_id}/diagnose")
async def run_diagnosis(run_id: str, db: Session = Depends(get_db)):
    """对已完成的评估运行执行跨角色诊断"""
    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    
    trials = (
        db.query(EvalTrial)
        .filter(EvalTrial.eval_run_id == run_id, EvalTrial.status == "completed")
        .all()
    )
    
    if not trials:
        raise HTTPException(status_code=400, detail="没有已完成的 Trial")
    
    trial_results = []
    for t in trials:
        tr = TrialResult(
            role=t.role, interaction_mode=t.interaction_mode,
            nodes=t.nodes or [], result=t.result or {},
            grader_outputs=t.grader_outputs or [],
            overall_score=t.overall_score or 0, success=True,
        )
        trial_results.append(tr)
    
    project = db.query(Project).filter(Project.id == run.project_id).first()
    intent = _get_project_intent(project, db) if project else ""
    
    diagnosis, diag_call = await run_diagnoser(
        trial_results=trial_results, intent=intent,
    )
    
    run.summary = diagnosis.get("summary", "")
    run.overall_score = diagnosis.get("overall_score", run.overall_score)
    db.commit()
    
    return {
        "diagnosis": diagnosis,
        "llm_call": diag_call.to_dict() if diag_call else None,
    }


# ============== Legacy: Run Full Eval ==============

@router.post("/run", response_model=EvalRunResponse)
async def run_evaluation(request: RunEvalRequest, db: Session = Depends(get_db)):
    """兼容旧接口：运行完整评估"""
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    content, field_names = _collect_content(project.id, request.input_block_ids, db)
    if not content:
        raise HTTPException(status_code=400, detail="项目中没有可评估的内容")
    
    creator_profile = _get_creator_profile(project, db)
    intent = _get_project_intent(project, db)
    personas = request.personas or _get_project_personas_from_research(project.id, db)
    if not personas:
        personas = [{"name": "典型用户", "background": "对该领域感兴趣的普通读者"}]
    
    eval_run = EvalRun(
        id=generate_uuid(), project_id=project.id, name=request.name,
        config={"roles": request.roles, "max_turns": request.max_turns},
        status="running",
    )
    db.add(eval_run)
    db.commit()
    
    try:
        trial_results, diagnosis = await run_eval(
            content=content, roles=request.roles,
            creator_profile=creator_profile, intent=intent,
            personas=personas, max_turns=request.max_turns,
            content_field_names=field_names,
        )
        
        role_scores = {}
        for tr in trial_results:
            trial = EvalTrial(
                id=generate_uuid(), eval_run_id=eval_run.id,
                role=tr.role, interaction_mode=tr.interaction_mode,
                nodes=tr.nodes, result=tr.result,
                grader_outputs=tr.grader_outputs,
                llm_calls=tr.llm_calls,
                overall_score=tr.overall_score,
                status="completed" if tr.success else "failed",
                error=tr.error, tokens_in=tr.tokens_in,
                tokens_out=tr.tokens_out, cost=tr.cost,
            )
            db.add(trial)
            if tr.success and tr.role not in role_scores:
                role_scores[tr.role] = tr.overall_score
        
        eval_run.status = "completed"
        eval_run.role_scores = role_scores
        eval_run.trial_count = len(trial_results)
        eval_run.overall_score = diagnosis.get("overall_score", 0)
        eval_run.summary = diagnosis.get("summary", "")
        
        db.commit()
        db.refresh(eval_run)
        return _to_run_response(eval_run)
        
    except Exception as e:
        eval_run.status = "failed"
        eval_run.summary = f"评估失败: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail=f"评估运行失败: {str(e)}")


# ============== Generate for ContentBlock ==============

@router.post("/generate-for-block/{block_id}")
async def generate_eval_for_block(block_id: str, db: Session = Depends(get_db)):
    """
    为 ContentBlock 字段生成评估
    处理新版 special_handler: eval_persona_setup / eval_task_config / eval_execution / eval_grader_report / eval_diagnosis
    也兼容旧版: eval_coach / eval_editor / eval_expert / eval_consumer / eval_seller / eval_diagnoser
    """
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id, ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    
    handler = block.special_handler
    if not handler or not handler.startswith("eval_"):
        raise HTTPException(status_code=400, detail="此内容块不是评估字段")
    
    project = db.query(Project).filter(Project.id == block.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 新版 handlers
    if handler == "eval_persona_setup":
        return await _handle_persona_setup(block, project, db)
    elif handler == "eval_task_config":
        return await _handle_task_config(block, project, db)
    elif handler in ("eval_report", "eval_execution", "eval_grader_report", "eval_diagnosis"):
        # 统一到 eval_report 处理：执行 + 评分 + 诊断 一次完成
        return await _handle_eval_report(block, project, db)
    elif handler == "eval_container":
        block.content = "请分别点击各评估字段进行评估。"
        block.status = "completed"
        db.commit()
        return {"message": "容器字段已更新", "content": block.content}
    else:
        # 旧版 eval_coach / eval_editor / etc.
        return await _handle_legacy_eval(block, project, handler, db)


async def _handle_persona_setup(block, project, db):
    """生成目标消费者画像（从消费者调研中提取）"""
    personas = _get_project_personas_from_research(project.id, db)
    
    if not personas:
        block.content = json.dumps({
            "personas": [{"name": "典型用户", "background": f"对{project.name}感兴趣的目标用户", "pain_points": ["待填写"]}],
            "source": "default",
        }, ensure_ascii=False, indent=2)
    else:
        block.content = json.dumps({
            "personas": personas,
            "source": "consumer_research",
        }, ensure_ascii=False, indent=2)
    
    block.status = "pending"  # 需要用户确认
    db.commit()
    return {"message": f"加载了 {len(personas) if personas else 1} 个消费者画像", "content": block.content}


async def _handle_task_config(block, project, db):
    """生成默认的任务配置"""
    # 获取 personas
    persona_block = _find_sibling_by_handler(block, "eval_persona_setup", db)
    personas = []
    if persona_block and persona_block.content:
        try:
            data = json.loads(persona_block.content)
            personas = data.get("personas", [])
        except Exception:
            pass
    
    if not personas:
        personas = [{"name": "典型用户", "background": "目标读者"}]
    
    # 生成全回归任务配置
    tasks_config = []
    order = 0
    for role in ["coach", "editor", "expert"]:
        type_info = SIMULATOR_TYPES.get(role, {})
        tasks_config.append({
            "name": f"{type_info.get('name', role)}审查",
            "simulator_type": role,
            "interaction_mode": "review",
            "persona_config": {},
            "grader_config": {"type": "content", "dimensions": type_info.get("default_dimensions", [])},
            "order_index": order,
        })
        order += 1
    
    for persona in personas:
        p_name = persona.get("name", "用户")
        tasks_config.append({
            "name": f"消费者对话-{p_name}",
            "simulator_type": "consumer",
            "interaction_mode": "dialogue",
            "persona_config": persona,
            "grader_config": {"type": "combined", "dimensions": SIMULATOR_TYPES.get("consumer", {}).get("default_dimensions", [])},
            "order_index": order,
        })
        order += 1
    
    for persona in personas:
        p_name = persona.get("name", "用户")
        tasks_config.append({
            "name": f"销售测试-{p_name}",
            "simulator_type": "seller",
            "interaction_mode": "dialogue",
            "persona_config": persona,
            "grader_config": {"type": "combined", "dimensions": SIMULATOR_TYPES.get("seller", {}).get("default_dimensions", [])},
            "order_index": order,
        })
        order += 1
    
    block.content = json.dumps({
        "trials": tasks_config,
        "template": "full_regression",
        "version": "v2",
    }, ensure_ascii=False, indent=2)
    block.status = "pending"  # 需要用户确认
    db.commit()
    
    return {"message": f"生成了 {len(tasks_config)} 个默认任务配置", "content": block.content}


async def _handle_eval_report(block, project, db):
    """
    统一评估报告处理：执行所有试验 + 各 grader 评分 + 综合诊断，
    所有结果存储在一个 JSON 中，前端用 EvalReportPanel 统一展示。
    """
    # 1. 收集所有 eval_task_config blocks（同级 + 项目内所有）
    all_trials_config = []
    
    # 先找同级
    sibling_config = _find_sibling_by_handler(block, "eval_task_config", db)
    if sibling_config and sibling_config.content:
        try:
            data = json.loads(sibling_config.content)
            all_trials_config.extend(data.get("trials", data.get("tasks", [])))
        except Exception:
            pass
    
    # 再找项目内其他 eval_task_config blocks（不同 parent 的）
    other_configs = db.query(ContentBlock).filter(
        ContentBlock.project_id == project.id,
        ContentBlock.special_handler == "eval_task_config",
        ContentBlock.deleted_at == None,
        ContentBlock.id != (sibling_config.id if sibling_config else ""),
    ).all()
    for cfg_block in other_configs:
        if cfg_block.content:
            try:
                data = json.loads(cfg_block.content)
                all_trials_config.extend(data.get("trials", data.get("tasks", [])))
            except Exception:
                continue

    if not all_trials_config:
        raise HTTPException(
            status_code=400,
            detail="没有配置任何试验（请在「评估任务配置」中添加试验并保存）"
        )

    # 2. 收集项目全部内容（作为 fallback）+ 各试验按 target_block_ids 筛选
    all_content, all_field_names = _collect_content(project.id, None, db, exclude_eval=True)
    if not all_content:
        raise HTTPException(status_code=400, detail="项目中没有可评估的内容")
    
    creator_profile = _get_creator_profile(project, db)
    intent = _get_project_intent(project, db)

    # 3. 解析 grader_ids → grader 信息列表，解析 simulator_id → 实际提示词
    from core.models.grader import Grader
    from core.models.simulator import Simulator
    from core.tools.eval_engine import run_individual_grader
    
    grader_cache = {}
    simulator_cache = {}
    
    for tc in all_trials_config:
        # --- 解析 Grader ---
        grader_ids = tc.get("grader_ids", [])
        resolved_graders = []
        if grader_ids:
            dims_all = []
            for gid in grader_ids:
                if gid not in grader_cache:
                    grader = db.query(Grader).filter(Grader.id == gid).first()
                    if grader:
                        grader_cache[gid] = grader
                grader_obj = grader_cache.get(gid)
                if grader_obj:
                    resolved_graders.append({
                        "id": grader_obj.id,
                        "name": grader_obj.name,
                        "grader_type": grader_obj.grader_type,
                        "prompt_template": grader_obj.prompt_template or "",
                        "dimensions": grader_obj.dimensions or ["综合评价"],
                    })
                    if grader_obj.dimensions:
                        dims_all.extend(grader_obj.dimensions)
            tc["grader_config"] = {
                "type": "content",
                "dimensions": list(dict.fromkeys(dims_all)) if dims_all else ["综合评价"],
                "grader_ids": grader_ids,
            }
        tc["_resolved_graders"] = resolved_graders
        
        # --- 解析 Simulator：用后台配置的提示词替代硬编码 ---
        sim_id = tc.get("simulator_id", "")
        if sim_id:
            if sim_id not in simulator_cache:
                sim = db.query(Simulator).filter(Simulator.id == sim_id).first()
                if sim:
                    simulator_cache[sim_id] = sim
            sim_obj = simulator_cache.get(sim_id)
            if sim_obj:
                sim_config = tc.get("simulator_config") or {}
                sim_config["system_prompt"] = sim_obj.prompt_template or ""
                sim_config["secondary_prompt"] = sim_obj.secondary_prompt or ""
                sim_config["simulator_name"] = sim_obj.name
                sim_config["grader_template"] = sim_obj.grader_template or ""
                sim_config["interaction_type"] = sim_obj.interaction_type or ""  # 关键：传递交互类型
                sim_config.setdefault("max_turns", sim_obj.max_turns or 5)
                tc["simulator_config"] = sim_config
    
    block.status = "in_progress"
    db.commit()
    
    try:
        # 4. 创建 EvalRun
        eval_run = EvalRun(
            id=generate_uuid(), project_id=project.id,
            name=f"评估-{project.name}", status="running",
        )
        db.add(eval_run)
        db.commit()

        # 5. 并行执行所有 Trial（按 target_block_ids 筛选内容）
        async_tasks = []
        for tc in all_trials_config:
            # ===== 关键修复：按试验的 target_block_ids 筛选内容 =====
            trial_target_ids = tc.get("target_block_ids", [])
            if trial_target_ids:
                trial_content, trial_field_names = _collect_content(
                    project.id, trial_target_ids, db, exclude_eval=True
                )
                if not trial_content:
                    trial_content = all_content
                    trial_field_names = all_field_names
            else:
                trial_content = all_content
                trial_field_names = all_field_names
            
            # 存入 tc 供后续 grader 阶段使用（避免变量丢失）
            tc["_trial_content"] = trial_content
            tc["_trial_field_names"] = trial_field_names
            
            async_tasks.append(run_task_trial(
                simulator_type=tc.get("simulator_type", "coach"),
                interaction_mode=tc.get("interaction_mode", "review"),
                content=trial_content,
                creator_profile=creator_profile,
                intent=intent,
                persona=tc.get("persona_config"),
                simulator_config=tc.get("simulator_config", {"max_turns": 5}),
                grader_config=tc.get("grader_config", {"type": "content"}),
                content_field_names=trial_field_names,
            ))

        results = await asyncio.gather(*async_tasks, return_exceptions=True)

        # 6. 收集结果
        report_data = {"eval_run_id": eval_run.id, "trials": [], "diagnosis": None}
        trial_results_for_diagnosis = []

        for tc, result in zip(all_trials_config, results):
            if isinstance(result, Exception):
                report_data["trials"].append({
                    "task_name": tc.get("name", "未知"),
                    "status": "failed",
                    "error": str(result),
                    "simulator_type": tc.get("simulator_type"),
                    "interaction_mode": tc.get("interaction_mode"),
                    "persona_name": tc.get("persona_config", {}).get("name", ""),
                })
                continue

            tr: TrialResult = result

            # 保存 Trial 到数据库
            trial = EvalTrial(
                id=generate_uuid(), eval_run_id=eval_run.id,
                role=tr.role, interaction_mode=tr.interaction_mode,
                persona=tc.get("persona_config", {}),
                nodes=tr.nodes, result=tr.result,
                grader_outputs=tr.grader_outputs, llm_calls=tr.llm_calls,
                overall_score=tr.overall_score,
                status="completed" if tr.success else "failed",
                error=tr.error, tokens_in=tr.tokens_in,
                tokens_out=tr.tokens_out, cost=tr.cost,
            )
            db.add(trial)

            # ======= 运行每个选定的 Grader 独立评分 =======
            grader_results = []
            grader_scores = {}
            extra_llm_calls = []
            
            resolved_graders = tc.get("_resolved_graders", [])
            if resolved_graders and tr.success:
                # 准备互动过程文本（对话类试验用）
                process_transcript = ""
                if tr.nodes:
                    process_transcript = "\n".join(
                        f"[{n.get('role', '?')}] {n.get('content', '')}" for n in tr.nodes
                    )
                
                # 并行运行所有 Grader
                grader_tasks = []
                for rg in resolved_graders:
                    grader_tasks.append(run_individual_grader(
                        grader_name=rg["name"],
                        grader_type=rg["grader_type"],
                        prompt_template=rg["prompt_template"],
                        dimensions=rg["dimensions"],
                        content=tc.get("_trial_content", all_content),
                        trial_result_data=tr.result,
                        process_transcript=process_transcript if rg["grader_type"] == "content_and_process" else "",
                    ))
                
                grader_results_raw = await asyncio.gather(*grader_tasks, return_exceptions=True)
                for gr_result in grader_results_raw:
                    if isinstance(gr_result, Exception):
                        continue
                    go, go_call = gr_result
                    grader_results.append(go)
                    if go.get("overall") is not None:
                        grader_scores[go["grader_name"]] = go["overall"]
                    if go_call:
                        extra_llm_calls.append(go_call)
            
            # 兼容：如果没有 resolved_graders，使用引擎自带的 grader_outputs
            if not resolved_graders:
                for go in (tr.grader_outputs or []):
                    gname = go.get("grader_name", go.get("grader_type", "默认评分器"))
                    gscore = go.get("overall", go.get("quality_score", go.get("process_score", go.get("score", None))))
                    grader_results.append({
                        "grader_name": gname,
                        "grader_type": go.get("grader_type", "content_only"),
                        "overall": gscore,
                        "scores": go.get("scores", {}),
                        "comments": go.get("comments", {}),
                        "feedback": go.get("feedback", go.get("analysis", go.get("summary", ""))),
                    })
                    if gscore is not None:
                        grader_scores[gname] = gscore
            
            # 如果有 grader 分数，重新计算 overall_score（各 grader 均分）
            if grader_scores:
                all_g_scores = [v for v in grader_scores.values() if isinstance(v, (int, float))]
                if all_g_scores:
                    tr.overall_score = round(sum(all_g_scores) / len(all_g_scores), 2)
            
            # 合并额外的 LLM 调用记录
            all_llm_calls = [c.to_dict() if hasattr(c, 'to_dict') else c for c in (tr.llm_calls or [])]
            for ec in extra_llm_calls:
                all_llm_calls.append(ec.to_dict() if hasattr(ec, 'to_dict') else ec)

            trial_entry = {
                "trial_id": trial.id,
                "task_name": tc.get("name", "未知"),
                "simulator_type": tc.get("simulator_type"),
                "simulator_name": tr.role_display_name or tc.get("simulator_name", tc.get("simulator_type", "")),
                "interaction_mode": tc.get("interaction_mode"),
                "persona_name": tc.get("persona_config", {}).get("name", ""),
                "status": "completed" if tr.success else "failed",
                "overall_score": tr.overall_score,
                "grader_results": grader_results,
                "grader_scores": grader_scores,
                "nodes": tr.nodes,
                "result": tr.result,
                "llm_calls": all_llm_calls,
                "tokens_in": tr.tokens_in,
                "tokens_out": tr.tokens_out,
                "cost": tr.cost,
            }
            report_data["trials"].append(trial_entry)

            if tr.success:
                trial_results_for_diagnosis.append(tr)

        # 6. 运行综合诊断（如果有至少一个成功的 trial）
        if trial_results_for_diagnosis:
            try:
                diagnosis, diag_call = await run_diagnoser(
                    trial_results=trial_results_for_diagnosis, intent=intent,
                )
                diagnosis_text = format_diagnosis_markdown(diagnosis)
                if diag_call:
                    diagnosis_text += f"\n\n---\n_诊断 LLM 调用: Tokens {diag_call.tokens_in}↑ {diag_call.tokens_out}↓ | 费用 ¥{diag_call.cost:.4f}_"
                report_data["diagnosis"] = diagnosis_text
            except Exception as diag_err:
                report_data["diagnosis"] = f"诊断生成失败: {str(diag_err)}"

        eval_run.status = "completed"
        eval_run.trial_count = len(results)

        # 7. 将所有 LLM 调用保存到 GenerationLog 审计表
        for trial_entry in report_data["trials"]:
            llm_calls = trial_entry.get("llm_calls", [])
            task_name = trial_entry.get("task_name", "eval")
            for lc in llm_calls:
                if isinstance(lc, dict):
                    inp = lc.get("input", {})
                    gen_log = GenerationLog(
                        id=generate_uuid(),
                        project_id=project.id,
                        field_id=block.id,
                        phase="evaluate",
                        operation=f"eval_{task_name}_{lc.get('step', 'unknown')}",
                        model="gpt-5.1",
                        prompt_input=f"[SYSTEM]\n{inp.get('system_prompt', '')}\n\n[USER]\n{inp.get('user_message', '')}",
                        prompt_output=lc.get("output", ""),
                        tokens_in=lc.get("tokens_in", 0),
                        tokens_out=lc.get("tokens_out", 0),
                        duration_ms=lc.get("duration_ms", 0),
                        cost=lc.get("cost", 0.0),
                        status="success",
                    )
                    db.add(gen_log)

        block.content = json.dumps(report_data, ensure_ascii=False, indent=2)
        block.status = "completed"
        db.commit()

        completed_count = sum(1 for t in report_data["trials"] if t.get("status") == "completed")
        return {
            "message": f"评估完成: {completed_count}/{len(results)} 个试验成功",
            "content": block.content,
        }

    except Exception as e:
        block.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"评估执行失败: {str(e)}")


async def _handle_legacy_eval(block, project, handler, db):
    """处理旧版 eval_coach/editor/expert/consumer/seller/diagnoser"""
    content, field_names = _collect_content(project.id, None, db, exclude_eval=True)
    if not content:
        raise HTTPException(status_code=400, detail="没有可评估的内容")
    
    creator_profile = _get_creator_profile(project, db)
    intent = _get_project_intent(project, db)
    personas = _get_project_personas_from_research(project.id, db)
    
    block.status = "in_progress"
    db.commit()
    
    role = handler.replace("eval_", "")
    
    if role == "diagnoser":
        # 收集同级 eval 字段结果
        trial_results = []
        sibling_blocks = db.query(ContentBlock).filter(
            ContentBlock.project_id == project.id,
            ContentBlock.special_handler.like("eval_%"),
            ContentBlock.special_handler.notin_(["eval_container", "eval_diagnoser",
                "eval_persona_setup", "eval_task_config", "eval_report",
                "eval_execution", "eval_grader_report", "eval_diagnosis"]),
            ContentBlock.status == "completed",
            ContentBlock.deleted_at == None,
        ).all()
        
        for sb in sibling_blocks:
            if sb.content:
                trial_results.append(TrialResult(
                    role=sb.special_handler.replace("eval_", ""),
                    interaction_mode="review",
                    result={"summary": sb.content[:500]},
                    overall_score=_extract_score_from_content(sb.content),
                    success=True,
                ))
        
        if not trial_results:
            raise HTTPException(status_code=400, detail="请先完成其他评估角色的评估")
        
        diagnosis, _ = await run_diagnoser(trial_results, intent=intent)
        block.content = format_diagnosis_markdown(diagnosis)
        block.status = "completed"
        db.commit()
        return {"message": "综合诊断完成", "content": block.content}
    
    # 其他角色
    try:
        persona = personas[0] if personas else {"name": "典型用户", "background": "目标读者"}
        
        tr = await run_task_trial(
            simulator_type=role,
            interaction_mode="dialogue" if role in ("consumer", "seller") else "review",
            content=content,
            creator_profile=creator_profile,
            intent=intent,
            persona=persona if role in ("consumer", "seller") else None,
            grader_config={"type": "combined" if role in ("consumer", "seller") else "content"},
            content_field_names=field_names,
        )
        
        block.content = format_trial_result_markdown(tr)
        block.status = "completed" if tr.success else "failed"
        db.commit()
        
        return {"message": f"评估完成", "content": block.content, "score": tr.overall_score}
        
    except Exception as e:
        block.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"评估失败: {str(e)}")


# ============== Helpers ==============

def _collect_content(project_id, block_ids, db, exclude_eval=False):
    """收集项目的已完成内容"""
    from core.models import ProjectField
    
    all_content = []
    field_names = []
    
    query = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.block_type == "field",
        ContentBlock.deleted_at == None,
    )
    
    if block_ids:
        query = query.filter(ContentBlock.id.in_(block_ids))
    
    if exclude_eval:
        query = query.filter(
            (ContentBlock.special_handler == None) | 
            (~ContentBlock.special_handler.like("eval_%"))
        )
    
    blocks = query.all()
    
    for block in blocks:
        if block.content and block.content.strip():
            all_content.append(f"## {block.name}\n{block.content}")
            field_names.append(block.name)
    
    if not block_ids:
        pfields = db.query(ProjectField).filter(
            ProjectField.project_id == project_id,
            ProjectField.status == "completed",
        ).all()
        for pf in pfields:
            if pf.content and pf.content.strip():
                all_content.append(f"## {pf.name}\n{pf.content}")
                field_names.append(pf.name)
    
    return "\n\n---\n\n".join(all_content), field_names


def _get_creator_profile(project, db) -> str:
    if project.creator_profile_id:
        profile = db.query(CreatorProfile).filter(
            CreatorProfile.id == project.creator_profile_id
        ).first()
        if profile:
            traits = profile.traits or {}
            return f"**{profile.name}**\n语调: {traits.get('tone', '')}\n词汇: {traits.get('vocabulary', '')}\n性格: {traits.get('personality', '')}"
    return ""


def _get_project_intent(project, db) -> str:
    from core.models import ProjectField
    
    intent_block = db.query(ContentBlock).filter(
        ContentBlock.project_id == project.id,
        ContentBlock.name.in_(["意图分析", "项目意图", "Intent"]),
        ContentBlock.deleted_at == None,
    ).first()
    
    if intent_block and intent_block.content:
        return intent_block.content
    
    intent_field = db.query(ProjectField).filter(
        ProjectField.project_id == project.id,
        ProjectField.phase == "intent",
    ).first()
    
    if intent_field and intent_field.content:
        return intent_field.content
    
    return project.name or ""


def _get_project_personas_from_research(project_id: str, db) -> list:
    """
    从消费者调研 / eval_persona_setup ContentBlock 中提取消费者画像
    优先级：eval_persona_setup > research block > 名称匹配 > SimulationRecord
    """
    personas = []
    
    # 1. 优先从 eval_persona_setup block 中提取（用户已配置的画像）
    persona_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.special_handler == "eval_persona_setup",
        ContentBlock.deleted_at == None,
    ).all()
    for pb in persona_blocks:
        if pb.content:
            extracted = _extract_personas_from_text(pb.content)
            personas.extend(extracted)
    if personas:
        return personas
    
    # 2. 从消费者调研 block 中提取
    research_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,
    ).filter(
        (ContentBlock.special_handler == "research") |
        (ContentBlock.name.in_(["消费者调研", "目标用户"]))
    ).all()
    
    for rb in research_blocks:
        if not rb.content:
            continue
        extracted = _extract_personas_from_text(rb.content)
        personas.extend(extracted)
    if personas:
        return personas
    
    # 3. 从子字段中查找（排除 eval_persona_setup 以免当 raw JSON 展示）
    research_children = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,
        ContentBlock.name.like("%画像%"),
        ContentBlock.special_handler != "eval_persona_setup",
    ).all()
    
    for rc in research_children:
        if rc.content:
            # 先尝试 JSON 解析
            extracted = _extract_personas_from_text(rc.content)
            if extracted:
                personas.extend(extracted)
            else:
                personas.append({
                    "name": rc.name,
                    "background": rc.content[:300],
                    "source": "content_block",
                    "block_id": rc.id,
                })
    if personas:
        return personas
    
    # 4. 从传统流程的 ProjectField（phase="research"）中提取
    from core.models import ProjectField
    research_fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
        ProjectField.phase == "research",
    ).all()
    for rf in research_fields:
        if not rf.content:
            continue
        extracted = _extract_personas_from_text(rf.content)
        personas.extend(extracted)
    if personas:
        return personas
    
    # 5. 从 SimulationRecord 备选
    from core.models import SimulationRecord
    sim_records = db.query(SimulationRecord).filter(
        SimulationRecord.project_id == project_id,
    ).limit(3).all()
    for sr in sim_records:
        if sr.persona:
            personas.append(sr.persona)
    
    return personas


def _get_persona_by_block_id(block_id: str, db) -> dict:
    """根据 block ID 获取 persona 信息"""
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if block and block.content:
        return {
            "name": block.name,
            "background": block.content[:500],
            "source": "content_block",
            "block_id": block.id,
        }
    return None


def _extract_personas_from_text(text: str) -> list:
    """从文本中提取消费者画像"""
    import re
    
    personas = []
    
    # 尝试 JSON 解析
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "personas" in data:
            return data["personas"]
    except Exception:
        pass
    
    # 从 Markdown 中提取（格式: ## 画像名 + 描述段落）
    sections = re.split(r'##\s+', text)
    for section in sections:
        if not section.strip():
            continue
        lines = section.strip().split('\n')
        name = lines[0].strip().rstrip('#').strip()
        if not name:
            continue
        content = '\n'.join(lines[1:]).strip()
        if len(content) > 20:
            pain_points = re.findall(r'[-*]\s*痛点[：:]\s*(.+)', content)
            personas.append({
                "name": name,
                "background": content[:300],
                "pain_points": pain_points[:5] if pain_points else [],
                "source": "extracted",
            })
    
    return personas


def _find_sibling_by_handler(block, handler: str, db) -> ContentBlock:
    """找到同级（同 parent_id）的特定 handler 块"""
    return db.query(ContentBlock).filter(
        ContentBlock.project_id == block.project_id,
        ContentBlock.parent_id == block.parent_id,
        ContentBlock.special_handler == handler,
        ContentBlock.deleted_at == None,
    ).first()


def _extract_score_from_content(content: str) -> float:
    import re
    match = re.search(r'(\d+(?:\.\d+)?)/10', content)
    if match:
        return float(match.group(1))
    return 5.0


def _to_run_response(r: EvalRun) -> EvalRunResponse:
    return EvalRunResponse(
        id=r.id, project_id=r.project_id,
        name=r.name or "", status=r.status or "pending",
        summary=r.summary or "", overall_score=r.overall_score,
        role_scores=r.role_scores or {}, trial_count=r.trial_count or 0,
        content_block_id=r.content_block_id, config=r.config or {},
        created_at=r.created_at.isoformat() if r.created_at else "",
    )


def _to_task_response(t: EvalTask) -> EvalTaskResponse:
    return EvalTaskResponse(
        id=t.id, eval_run_id=t.eval_run_id, name=t.name or "",
        simulator_type=t.simulator_type or "coach",
        interaction_mode=t.interaction_mode or "review",
        simulator_config=t.simulator_config or {},
        persona_config=t.persona_config or {},
        target_block_ids=t.target_block_ids or [],
        grader_config=t.grader_config or {},
        order_index=t.order_index or 0,
        status=t.status or "pending", error=t.error or "",
        created_at=t.created_at.isoformat() if t.created_at else "",
    )


def _to_trial_response(t: EvalTrial) -> EvalTrialResponse:
    return EvalTrialResponse(
        id=t.id, eval_run_id=t.eval_run_id,
        eval_task_id=t.eval_task_id,
        role=t.role or "", role_config=t.role_config or {},
        interaction_mode=t.interaction_mode or "review",
        input_block_ids=t.input_block_ids or [],
        persona=t.persona or {}, nodes=t.nodes or [],
        result=t.result or {}, grader_outputs=t.grader_outputs or [],
        llm_calls=t.llm_calls or [],
        overall_score=t.overall_score, status=t.status or "pending",
        error=t.error or "", tokens_in=t.tokens_in or 0,
        tokens_out=t.tokens_out or 0, cost=t.cost or 0.0,
        created_at=t.created_at.isoformat() if t.created_at else "",
    )
