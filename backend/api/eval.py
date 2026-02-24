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
import threading
import hashlib
import re
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel as PydanticBase
from sqlalchemy.orm import Session, sessionmaker
from langchain_core.messages import SystemMessage, HumanMessage

from core.database import get_db, get_session_maker
from core.models import (
    Project,
    ContentBlock,
    CreatorProfile,
    EvalRun,
    EvalTask,
    EvalTrial,
    EvalTaskV2,
    EvalTrialConfigV2,
    EvalTrialResultV2,
    TaskAnalysisV2,
    EvalSuggestionState,
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
    run_individual_grader,
)
from core.tools.eval_v2_service import (
    compute_content_hash,
    compute_weighted_grader_score,
    aggregate_task_scores,
)
from core.tools.eval_v2_executor import run_experience_trial
from core.models.grader import Grader
from core.llm import get_chat_model
from core.config import settings


router = APIRouter(prefix="/api/eval", tags=["eval"])

# 运行期状态（内存态，不落库）
_TASK_RUNTIME_STATE = {}
_TASK_RUNTIME_LOCK = threading.Lock()


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


# ============== Eval V2 (Task 容器 + TrialConfig) Schemas ==============

class GeneratePersonaRequest(PydanticBase):
    project_id: str
    avoid_names: List[str] = []


class GeneratePromptRequest(PydanticBase):
    prompt_type: str
    context: dict = {}


class CreatePersonaRequest(PydanticBase):
    name: str
    prompt: str
    source: str = "manual"


class UpdatePersonaRequest(PydanticBase):
    name: Optional[str] = None
    prompt: Optional[str] = None
    source: Optional[str] = None


class TrialConfigPayload(PydanticBase):
    name: str
    form_type: str = "assessment"   # assessment | review | experience | scenario
    target_block_ids: List[str] = []
    grader_ids: List[str] = []
    grader_weights: dict = {}
    repeat_count: int = 1
    probe: str = ""
    form_config: dict = {}
    order_index: int = 0


class CreateTaskV2Request(PydanticBase):
    name: str
    description: str = ""
    order_index: int = 0
    trial_configs: List[TrialConfigPayload]


class UpdateTaskV2Request(PydanticBase):
    name: Optional[str] = None
    description: Optional[str] = None
    order_index: Optional[int] = None
    trial_configs: Optional[List[TrialConfigPayload]] = None


class DeleteExecutionItem(PydanticBase):
    task_id: str
    batch_id: str


class BatchDeleteExecutionsRequest(PydanticBase):
    items: List[DeleteExecutionItem]


class SuggestionStateUpsertRequest(PydanticBase):
    source: str
    suggestion: str
    status: str = "applied"

# ============== Config Routes ==============

@router.post("/personas/generate")
async def generate_eval_persona(request: GeneratePersonaRequest, db: Session = Depends(get_db)):
    """AI 生成人物画像（项目级）。"""
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    intent = _get_project_intent(project, db)
    existing = _get_project_personas_from_research(project.id, db)
    existing_names = [p.get("name", "") for p in existing if isinstance(p, dict) and p.get("name")]
    avoid_names = list(dict.fromkeys([*(request.avoid_names or []), *existing_names]))

    generated = await _generate_persona_with_llm(
        project_name=project.name,
        project_intent=intent,
        existing_names=avoid_names,
    )
    return {"persona": generated}


@router.post("/prompts/generate")
async def generate_eval_prompt(request: GeneratePromptRequest):
    """统一 AI 生成提示词接口（仅生成，不做优化）。"""
    prompt_type = (request.prompt_type or "").strip()
    if not prompt_type:
        raise HTTPException(status_code=400, detail="prompt_type 不能为空")

    generated_prompt = await _generate_prompt_with_llm(prompt_type=prompt_type, context=request.context or {})
    return {"generated_prompt": generated_prompt}


@router.get("/config")
def get_eval_config():
    """获取评估系统可用配置项"""
    return {
        "simulator_types": SIMULATOR_TYPES,
        "interaction_modes": INTERACTION_MODES,
        "grader_types": GRADER_TYPES,
        "roles": EVAL_ROLES,
        "eval_runtime": {
            "max_parallel_trials": max(1, int(settings.eval_max_parallel_trials or 1)),
        },
    }


@router.post("/provider/test")
async def test_eval_provider():
    """
    最小化探针：验证当前后端进程真实使用的模型配置可调用。
    """
    model = get_chat_model(temperature=0.0, streaming=False)
    reply = await model.ainvoke([HumanMessage(content="Reply exactly: OK")])
    # 获取当前使用的模型名
    current_model = (settings.anthropic_model if settings.llm_provider == "anthropic" else settings.openai_model)
    raw_content = getattr(reply, "content", "")
    if isinstance(raw_content, list):
        raw_content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in raw_content)
    return {
        "ok": True,
        "model": current_model,
        "provider": settings.llm_provider,
        "reply": str(raw_content)[:120],
    }


@router.get("/personas/{project_id}")
def get_project_personas(project_id: str, db: Session = Depends(get_db)):
    """获取项目的消费者画像（来自消费者调研 ContentBlock）"""
    personas = _get_project_personas_from_research(project_id, db)
    return {"personas": personas}


@router.post("/personas/{project_id}")
def create_project_persona(project_id: str, request: CreatePersonaRequest, db: Session = Depends(get_db)):
    """创建项目画像（写入 eval_persona_setup ContentBlock）。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    block = _get_or_create_eval_persona_block(project_id, db)
    personas = _read_personas_from_block(block)
    new_persona = {
        "id": f"p_{generate_uuid().replace('-', '')[:12]}",
        "name": request.name.strip(),
        "prompt": request.prompt.strip(),
        "source": request.source or "manual",
    }
    if not new_persona["name"] or not new_persona["prompt"]:
        raise HTTPException(status_code=400, detail="画像名称和提示词不能为空")

    personas.append(new_persona)
    _write_personas_to_block(block, personas)
    db.commit()
    return {"persona": new_persona}


@router.put("/persona/{persona_id}")
def update_project_persona(persona_id: str, request: UpdatePersonaRequest, db: Session = Depends(get_db)):
    """更新项目画像（在所有项目的 eval_persona_setup 中按 persona_id 查找并更新）。"""
    blocks = db.query(ContentBlock).filter(
        ContentBlock.special_handler == "eval_persona_setup",
        ContentBlock.deleted_at == None,  # noqa: E711
    ).all()
    for block in blocks:
        personas = _read_personas_from_block(block)
        hit = next((p for p in personas if str(p.get("id", "")) == persona_id), None)
        if not hit:
            continue

        if request.name is not None:
            hit["name"] = request.name.strip()
        if request.prompt is not None:
            hit["prompt"] = request.prompt.strip()
        if request.source is not None:
            hit["source"] = request.source
        if not hit.get("name") or not hit.get("prompt"):
            raise HTTPException(status_code=400, detail="画像名称和提示词不能为空")

        _write_personas_to_block(block, personas)
        db.commit()
        return {"persona": hit}
    raise HTTPException(status_code=404, detail="Persona not found")


@router.delete("/persona/{persona_id}")
def delete_project_persona(persona_id: str, db: Session = Depends(get_db)):
    """删除项目画像（在所有项目的 eval_persona_setup 中按 persona_id 删除）。"""
    blocks = db.query(ContentBlock).filter(
        ContentBlock.special_handler == "eval_persona_setup",
        ContentBlock.deleted_at == None,  # noqa: E711
    ).all()
    for block in blocks:
        personas = _read_personas_from_block(block)
        filtered = [p for p in personas if str(p.get("id", "")) != persona_id]
        if len(filtered) == len(personas):
            continue
        _write_personas_to_block(block, filtered)
        db.commit()
        return {"message": "已删除"}
    raise HTTPException(status_code=404, detail="Persona not found")


# ============== Eval V2 Task CRUD (新链路) ==============

@router.get("/tasks/{project_id}")
def list_eval_v2_tasks(project_id: str, db: Session = Depends(get_db)):
    tasks = (
        db.query(EvalTaskV2)
        .filter(EvalTaskV2.project_id == project_id)
        .order_by(EvalTaskV2.order_index, EvalTaskV2.created_at)
        .all()
    )
    healed = False
    for t in tasks:
        rt = _get_task_runtime(t.id)
        if t.status == "running" and not rt.get("is_running", False):
            # 运行态丢失（常见于服务重启/进程中断），避免界面长期假 running
            t.status = "failed"
            if not (t.last_error or "").strip():
                t.last_error = "执行状态丢失（服务重启或任务中断），请重新执行。"
            healed = True
    if healed:
        db.commit()
        for t in tasks:
            db.refresh(t)
    return {"tasks": [_serialize_task_v2(t) for t in tasks]}


@router.post("/tasks/{project_id}")
def create_eval_v2_task(project_id: str, request: CreateTaskV2Request, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not request.trial_configs:
        raise HTTPException(status_code=400, detail="创建 Task 时必须至少包含一个 Trial 配置")

    task = EvalTaskV2(
        id=generate_uuid(),
        project_id=project_id,
        name=request.name,
        description=request.description,
        order_index=request.order_index,
        status="pending",
    )
    db.add(task)
    db.flush()
    _replace_trial_configs_v2(task.id, request.trial_configs, db)
    db.commit()
    db.refresh(task)
    return _serialize_task_v2(task)


@router.put("/task/{task_id}/v2")
def update_eval_v2_task(task_id: str, request: UpdateTaskV2Request, db: Session = Depends(get_db)):
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")

    if request.name is not None:
        task.name = request.name
    if request.description is not None:
        task.description = request.description
    if request.order_index is not None:
        task.order_index = request.order_index

    if request.trial_configs is not None:
        if not request.trial_configs:
            raise HTTPException(status_code=400, detail="Task 至少需要一个 Trial 配置")
        _replace_trial_configs_v2(task.id, request.trial_configs, db)

    task.status = "pending"
    db.commit()
    db.refresh(task)
    return _serialize_task_v2(task)


@router.post("/tasks/{project_id}/execute-all")
async def execute_eval_v2_all_tasks(project_id: str, db: Session = Depends(get_db)):
    tasks = (
        db.query(EvalTaskV2)
        .filter(EvalTaskV2.project_id == project_id)
        .order_by(EvalTaskV2.order_index, EvalTaskV2.created_at)
        .all()
    )
    if not tasks:
        raise HTTPException(status_code=400, detail="当前项目没有可执行的 Eval Task")

    executed = []
    failed = []
    for t in tasks:
        try:
            out = await _execute_task_v2(t.id, db)
            executed.append({"task_id": t.id, "batch_id": out.get("batch_id"), "overall": out.get("overall")})
        except Exception as e:
            failed.append({"task_id": t.id, "error": str(e)})
    return {"executed": executed, "failed": failed}


@router.get("/tasks/{project_id}/report")
def get_eval_v2_report(project_id: str, db: Session = Depends(get_db)):
    tasks = (
        db.query(EvalTaskV2)
        .filter(EvalTaskV2.project_id == project_id)
        .order_by(EvalTaskV2.updated_at.desc())
        .all()
    )
    rows = []
    for t in tasks:
        rows.append({
            "id": t.id,
            "name": t.name,
            "status": t.status,
            "latest_batch_id": t.latest_batch_id,
            "latest_overall": t.latest_overall,
            "latest_scores": t.latest_scores or {},
            "last_executed_at": t.last_executed_at.isoformat() if t.last_executed_at else "",
        })
    return {"tasks": rows}


@router.get("/tasks/{project_id}/executions")
def get_eval_v2_executions(project_id: str, db: Session = Depends(get_db)):
    """
    报告页扁平执行记录：一条记录 = 一个 task 的一个 batch 执行。
    """
    tasks = db.query(EvalTaskV2).filter(EvalTaskV2.project_id == project_id).all()
    if not tasks:
        return {"executions": []}

    task_map = {t.id: t for t in tasks}
    rows = (
        db.query(EvalTrialResultV2)
        .filter(EvalTrialResultV2.project_id == project_id)
        .order_by(EvalTrialResultV2.created_at.desc())
        .all()
    )
    grouped = {}
    for r in rows:
        key = (r.task_id, r.batch_id)
        grouped.setdefault(key, []).append(r)

    executions = []
    for (task_id, batch_id), batch_rows in grouped.items():
        task = task_map.get(task_id)
        if not task:
            continue
        aggregate_input = [
            {"overall_score": x.overall_score, "dimension_scores": x.dimension_scores or {}}
            for x in batch_rows
            if x.status == "completed"
        ]
        agg = aggregate_task_scores(aggregate_input)
        executed_at = max((x.created_at for x in batch_rows if x.created_at), default=None)
        executions.append({
            "task_id": task.id,
            "task_name": task.name,
            "batch_id": batch_id,
            "overall": (agg.get("overall") or {}).get("mean") if agg.get("overall") else None,
            "scores": agg,
            "trial_count": len(batch_rows),
            "status": "completed" if any(x.status == "completed" for x in batch_rows) else "failed",
            "executed_at": executed_at.isoformat() if executed_at else "",
        })

    executions.sort(key=lambda x: x.get("executed_at", ""), reverse=True)
    return {"executions": executions}


@router.delete("/task/{task_id}/batch/{batch_id}")
def delete_eval_v2_task_batch(task_id: str, batch_id: str, db: Session = Depends(get_db)):
    """
    删除某个 task 的单个 batch 记录（trial + analysis）。
    """
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")

    db.query(TaskAnalysisV2).filter(
        TaskAnalysisV2.task_id == task_id,
        TaskAnalysisV2.batch_id == batch_id,
    ).delete()
    db.query(EvalSuggestionState).filter(
        EvalSuggestionState.task_id == task_id,
        EvalSuggestionState.batch_id == batch_id,
    ).delete()
    deleted = db.query(EvalTrialResultV2).filter(
        EvalTrialResultV2.task_id == task_id,
        EvalTrialResultV2.batch_id == batch_id,
    ).delete()

    _recompute_task_latest_after_delete(task, db)
    db.commit()
    db.refresh(task)
    return {"deleted_trials": int(deleted or 0), "task": _serialize_task_v2(task)}


@router.post("/tasks/{project_id}/executions/delete")
def batch_delete_eval_v2_executions(
    project_id: str,
    request: BatchDeleteExecutionsRequest,
    db: Session = Depends(get_db),
):
    """
    批量删除执行记录（按 task_id + batch_id）。
    """
    if not request.items:
        raise HTTPException(status_code=400, detail="items 不能为空")

    touched_task_ids = set()
    deleted_trials = 0
    for item in request.items:
        task = db.query(EvalTaskV2).filter(
            EvalTaskV2.id == item.task_id,
            EvalTaskV2.project_id == project_id,
        ).first()
        if not task:
            continue
        touched_task_ids.add(task.id)
        db.query(TaskAnalysisV2).filter(
            TaskAnalysisV2.task_id == item.task_id,
            TaskAnalysisV2.batch_id == item.batch_id,
        ).delete()
        db.query(EvalSuggestionState).filter(
            EvalSuggestionState.task_id == item.task_id,
            EvalSuggestionState.batch_id == item.batch_id,
        ).delete()
        deleted_trials += int(
            db.query(EvalTrialResultV2).filter(
                EvalTrialResultV2.task_id == item.task_id,
                EvalTrialResultV2.batch_id == item.batch_id,
            ).delete()
            or 0
        )

    for task_id in touched_task_ids:
        task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
        if task:
            _recompute_task_latest_after_delete(task, db)

    db.commit()
    return {
        "deleted_trials": deleted_trials,
        "deleted_batches": len(request.items),
        "touched_tasks": len(touched_task_ids),
    }


@router.get("/task/{task_id}/batch/{batch_id}/suggestion-states")
def get_eval_v2_suggestion_states(task_id: str, batch_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(EvalSuggestionState)
        .filter(
            EvalSuggestionState.task_id == task_id,
            EvalSuggestionState.batch_id == batch_id,
        )
        .all()
    )
    return {
        "states": [
            {
                "id": r.id,
                "source": r.source,
                "suggestion": r.suggestion,
                "suggestion_hash": r.suggestion_hash,
                "status": r.status,
            }
            for r in rows
        ]
    }


@router.post("/task/{task_id}/batch/{batch_id}/suggestion-state")
def upsert_eval_v2_suggestion_state(
    task_id: str,
    batch_id: str,
    request: SuggestionStateUpsertRequest,
    db: Session = Depends(get_db),
):
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")
    sg_hash = _suggestion_hash(request.source, request.suggestion)
    row = (
        db.query(EvalSuggestionState)
        .filter(
            EvalSuggestionState.task_id == task_id,
            EvalSuggestionState.batch_id == batch_id,
            EvalSuggestionState.suggestion_hash == sg_hash,
        )
        .first()
    )
    if not row:
        row = EvalSuggestionState(
            id=generate_uuid(),
            project_id=task.project_id,
            task_id=task_id,
            batch_id=batch_id,
            source=request.source,
            suggestion=request.suggestion,
            suggestion_hash=sg_hash,
            status=request.status or "applied",
        )
        db.add(row)
    else:
        row.status = request.status or "applied"
        row.source = request.source
        row.suggestion = request.suggestion
    db.commit()
    return {"ok": True, "suggestion_hash": sg_hash, "status": row.status}


@router.get("/task/{task_id}/trials")
def get_eval_v2_task_trials(task_id: str, db: Session = Depends(get_db)):
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        # 兼容旧接口：按 eval_task_id 查询旧 Trial
        old_rows = (
            db.query(EvalTrial)
            .filter(EvalTrial.eval_task_id == task_id)
            .order_by(EvalTrial.created_at.desc())
            .all()
        )
        return {"trials": [_to_trial_response(t).model_dump() for t in old_rows]}

    rows = (
        db.query(EvalTrialResultV2)
        .filter(EvalTrialResultV2.task_id == task_id)
        .order_by(EvalTrialResultV2.created_at.desc())
        .all()
    )
    return {"trials": [_serialize_trial_result_v2(r) for r in rows]}


@router.get("/task/{task_id}/latest")
def get_eval_v2_task_latest(task_id: str, db: Session = Depends(get_db)):
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")

    if not task.latest_batch_id:
        return {"task": _serialize_task_v2(task), "trials": []}

    return get_eval_v2_task_batch(task_id, task.latest_batch_id, db)


@router.get("/task/{task_id}/batch/{batch_id}")
def get_eval_v2_task_batch(task_id: str, batch_id: str, db: Session = Depends(get_db)):
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")
    rows = (
        db.query(EvalTrialResultV2)
        .filter(
            EvalTrialResultV2.task_id == task_id,
            EvalTrialResultV2.batch_id == batch_id,
        )
        .order_by(EvalTrialResultV2.created_at.asc())
        .all()
    )
    q = db.query(TaskAnalysisV2).filter(TaskAnalysisV2.task_id == task_id, TaskAnalysisV2.batch_id == batch_id)
    analysis = q.order_by(TaskAnalysisV2.created_at.desc()).first()
    return {
        "task": _serialize_task_v2(task),
        "batch_id": batch_id,
        "trials": [_serialize_trial_result_v2(r) for r in rows],
        "analysis": _serialize_task_analysis_v2(analysis) if analysis else None,
    }


@router.get("/task/{task_id}/diagnosis")
def get_eval_v2_task_diagnosis(task_id: str, batch_id: Optional[str] = None, db: Session = Depends(get_db)):
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")

    q = db.query(TaskAnalysisV2).filter(TaskAnalysisV2.task_id == task_id)
    target_batch_id = batch_id or task.latest_batch_id
    if target_batch_id:
        q = q.filter(TaskAnalysisV2.batch_id == target_batch_id)
    analysis = q.order_by(TaskAnalysisV2.created_at.desc()).first()
    if not analysis:
        return {"analysis": None}
    return {"analysis": _serialize_task_analysis_v2(analysis)}


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
    # 新链路优先：如果是 EvalTaskV2，则走 V2 更新逻辑
    task_v2 = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if task_v2:
        update_data = request.model_dump(exclude_unset=True)
        if "name" in update_data:
            task_v2.name = update_data["name"]
        # 旧 schema 无 description/trial_configs，此端点仅做最小兼容更新
        if "order_index" in update_data and update_data["order_index"] is not None:
            task_v2.order_index = int(update_data["order_index"])
        task_v2.status = "pending"
        db.commit()
        db.refresh(task_v2)
        return EvalTaskResponse(
            id=task_v2.id,
            eval_run_id="",
            name=task_v2.name or "",
            simulator_type="mixed",
            interaction_mode="mixed",
            simulator_config={},
            persona_config={},
            target_block_ids=[],
            grader_config={},
            order_index=task_v2.order_index or 0,
            status=task_v2.status or "pending",
            error=task_v2.last_error or "",
            created_at=task_v2.created_at.isoformat() if task_v2.created_at else "",
        )

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
    task_v2 = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if task_v2:
        db.query(EvalTrialResultV2).filter(EvalTrialResultV2.task_id == task_id).delete()
        db.query(EvalTrialConfigV2).filter(EvalTrialConfigV2.task_id == task_id).delete()
        db.query(TaskAnalysisV2).filter(TaskAnalysisV2.task_id == task_id).delete()
        db.delete(task_v2)
        db.commit()
        return {"message": "已删除"}

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
    task_v2 = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if task_v2:
        return await _execute_task_v2(task_id, db)

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


@router.post("/task/{task_id}/start")
async def start_eval_v2_task(task_id: str, db: Session = Depends(get_db)):
    """
    异步启动 V2 Task 执行（立即返回），用于前端实时进度展示。
    """
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")
    rt = _get_task_runtime(task_id)
    if rt.get("is_running"):
        return {"message": "任务已在运行中", "task_id": task_id}
    if task.status == "paused":
        raise HTTPException(status_code=400, detail="任务已暂停，请使用 resume 继续，或先停止后重新开始")

    cfgs = (
        db.query(EvalTrialConfigV2)
        .filter(EvalTrialConfigV2.task_id == task_id)
        .order_by(EvalTrialConfigV2.order_index.asc())
        .all()
    )
    total_runs = sum(max(1, int(c.repeat_count or 1)) for c in cfgs)
    task.status = "running"
    task.last_error = ""
    db.commit()

    # 启动前清理旧状态，避免历史 stop 标记影响
    _clear_task_runtime(task_id)
    _set_task_runtime(
        task_id,
        {
            "task_id": task_id,
            "batch_id": "",
            "total": total_runs,
            "completed": 0,
            "is_running": True,
            "is_paused": False,
            "pause_requested": False,
            "stop_requested": False,
            "resume_requested": False,
            "max_parallel": max(1, int(settings.eval_max_parallel_trials or 1)),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    asyncio.create_task(_execute_task_v2_background(task_id))
    return {"message": "已开始执行", "task_id": task_id}


@router.post("/task/{task_id}/pause")
def pause_eval_v2_task(task_id: str, db: Session = Depends(get_db)):
    """
    请求暂停正在运行的 V2 Task（在 Trial 边界生效）。
    """
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")
    rt = _get_task_runtime(task_id)
    if not rt.get("is_running"):
        return {"message": "任务当前未在运行", "task_id": task_id}
    # 保持 running，前端通过 pause_requested 展示 pausing；
    # 真正 paused 在 Trial 边界由执行循环落库。
    if task.status != "running":
        task.status = "running"
        db.commit()
    _set_task_runtime(
        task_id,
        {
            "pause_requested": True,
            "is_paused": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"message": "已请求暂停", "task_id": task_id}


@router.post("/task/{task_id}/resume")
async def resume_eval_v2_task(task_id: str, db: Session = Depends(get_db)):
    """
    恢复已暂停任务：在同一 batch 上继续未完成 Trial。
    """
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")
    rt = _get_task_runtime(task_id)
    if rt.get("is_running"):
        # 若处于“请求暂停但尚未停稳”，记录恢复请求，等进入 paused 后自动续跑
        if rt.get("pause_requested"):
            _set_task_runtime(
                task_id,
                {
                    "resume_requested": True,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return {"message": "已排队恢复，暂停完成后会自动继续", "task_id": task_id}
        return {"message": "任务已在运行中", "task_id": task_id}
    if task.status != "paused" or not task.latest_batch_id:
        raise HTTPException(status_code=400, detail="当前任务不处于可恢复状态")

    _set_task_runtime(
        task_id,
        {
            "task_id": task_id,
            "batch_id": task.latest_batch_id,
            "is_running": True,
            "is_paused": False,
            "pause_requested": False,
            "stop_requested": False,
            "resume_requested": False,
            "max_parallel": max(1, int(settings.eval_max_parallel_trials or 1)),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    task.status = "running"
    db.commit()
    asyncio.create_task(_execute_task_v2_background(task_id, resume_batch_id=task.latest_batch_id))
    return {"message": "已恢复执行", "task_id": task_id, "batch_id": task.latest_batch_id}


@router.post("/task/{task_id}/stop")
def stop_eval_v2_task(task_id: str, db: Session = Depends(get_db)):
    """
    请求终止正在运行的 V2 Task（在 Trial 边界生效，终止后不可 resume）。
    """
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")
    rt = _get_task_runtime(task_id)
    if not rt.get("is_running"):
        return {"message": "任务当前未在运行", "task_id": task_id}
    # 立即反映状态，便于用户及时看到“终止中/已终止”
    task.status = "stopped"
    db.commit()
    _set_task_runtime(
        task_id,
        {
            "stop_requested": True,
            "pause_requested": False,
            "is_paused": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"message": "已请求终止", "task_id": task_id}


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


@router.post("/task/{task_id}/diagnose")
async def run_task_diagnosis(task_id: str, batch_id: Optional[str] = None, db: Session = Depends(get_db)):
    """新链路：对单个 Task 的最新 batch 运行跨 Trial 分析。"""
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")
    target_batch_id = batch_id or task.latest_batch_id
    if not target_batch_id:
        raise HTTPException(status_code=400, detail="Task 尚未执行，无法分析")

    rows = (
        db.query(EvalTrialResultV2)
        .filter(
            EvalTrialResultV2.task_id == task_id,
            EvalTrialResultV2.batch_id == target_batch_id,
            EvalTrialResultV2.status == "completed",
        )
        .all()
    )
    if not rows:
        raise HTTPException(status_code=400, detail="当前 batch 没有可分析的 Trial 结果")

    analysis = _build_task_analysis_from_trials(task, rows, target_batch_id)
    db.query(TaskAnalysisV2).filter(
        TaskAnalysisV2.task_id == task_id,
        TaskAnalysisV2.batch_id == target_batch_id,
    ).delete()
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return {"analysis": _serialize_task_analysis_v2(analysis)}


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
    支持 special_handler: eval_persona_setup / eval_task_config / eval_report
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
    
    if handler == "eval_persona_setup":
        return await _handle_persona_setup(block, project, db)
    elif handler == "eval_task_config":
        return await _handle_task_config(block, project, db)
    elif handler == "eval_report":
        return await _handle_eval_report(block, project, db)
    else:
        raise HTTPException(status_code=400, detail=f"未知的评估 handler: {handler}")


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
                
                # 修正 interaction_mode：如果 trial 配置的 mode 与 simulator 的 type 不一致，以 type 为准
                _TYPE_TO_MODE = {"reading": "review", "dialogue": "dialogue", "decision": "scenario", "exploration": "exploration"}
                correct_mode = _TYPE_TO_MODE.get(sim_obj.interaction_type or "", "")
                if correct_mode and tc.get("interaction_mode") != correct_mode:
                    print(f"[eval] 修正 interaction_mode: {tc.get('interaction_mode')} → {correct_mode} (simulator: {sim_obj.name})")
                    tc["interaction_mode"] = correct_mode
    
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


# ============== Helpers ==============

def _collect_content(project_id, block_ids, db, exclude_eval=False):
    """收集项目的已完成内容（P0-1: 统一使用 ContentBlock）"""
    all_content = []
    field_names = []
    
    query = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.block_type == "field",
        ContentBlock.deleted_at == None,  # noqa: E711
    )
    
    if block_ids:
        query = query.filter(ContentBlock.id.in_(block_ids))
    
    if exclude_eval:
        query = query.filter(
            (ContentBlock.special_handler == None) |  # noqa: E711
            (~ContentBlock.special_handler.like("eval_%"))
        )
    
    blocks = query.all()
    
    for block in blocks:
        if block.content and block.content.strip():
            all_content.append(f"## {block.name}\n{block.content}")
            field_names.append(block.name)
    
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
    """获取项目意图（P0-1: 统一使用 ContentBlock）"""
    # 按名称查找
    intent_block = db.query(ContentBlock).filter(
        ContentBlock.project_id == project.id,
        ContentBlock.name.in_(["意图分析", "项目意图", "Intent"]),
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()
    
    if intent_block and intent_block.content:
        return intent_block.content
    
    # 按 special_handler 查找 intent 阶段，再取其子字段
    intent_phase = db.query(ContentBlock).filter(
        ContentBlock.project_id == project.id,
        ContentBlock.special_handler == "intent",
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()
    if intent_phase:
        children = db.query(ContentBlock).filter(
            ContentBlock.parent_id == intent_phase.id,
            ContentBlock.deleted_at == None,  # noqa: E711
        ).all()
        parts = [f"**{c.name}**: {c.content}" for c in children if c.content]
        if parts:
            return "\n".join(parts)
    
    # 没有意图内容时返回空，避免误将项目名当作项目意图注入评估上下文。
    return ""


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
    
    # 4. ProjectField 路径已移除（P0-1 统一到 ContentBlock）
    
    # 5. 从 SimulationRecord 备选
    from core.models import SimulationRecord
    sim_records = db.query(SimulationRecord).filter(
        SimulationRecord.project_id == project_id,
    ).limit(3).all()
    for sr in sim_records:
        if sr.persona:
            personas.append(sr.persona)
    
    return personas


def _get_or_create_eval_persona_block(project_id: str, db) -> ContentBlock:
    block = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.special_handler == "eval_persona_setup",
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()
    if block:
        return block
    block = ContentBlock(
        id=generate_uuid(),
        project_id=project_id,
        parent_id=None,
        name="人物画像设置",
        block_type="field",
        content=json.dumps({"personas": []}, ensure_ascii=False, indent=2),
        special_handler="eval_persona_setup",
        status="completed",
        order_index=99,
    )
    db.add(block)
    db.flush()
    return block


def _read_personas_from_block(block: ContentBlock) -> list:
    if not block or not block.content:
        return []
    try:
        parsed = json.loads(block.content)
    except Exception:
        return _extract_personas_from_text(block.content)
    if isinstance(parsed, dict):
        personas = parsed.get("personas")
        return personas if isinstance(personas, list) else []
    if isinstance(parsed, list):
        return parsed
    return []


def _write_personas_to_block(block: ContentBlock, personas: list) -> None:
    clean = []
    for p in personas:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name", "")).strip()
        prompt = str(p.get("prompt", p.get("background", ""))).strip()
        if not name or not prompt:
            continue
        clean.append({
            "id": str(p.get("id", "")).strip() or f"p_{generate_uuid().replace('-', '')[:12]}",
            "name": name,
            "prompt": prompt,
            "source": str(p.get("source", "manual") or "manual"),
        })
    block.content = json.dumps({"personas": clean, "source": "user_configured"}, ensure_ascii=False, indent=2)
    block.status = "completed"


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


async def _generate_persona_with_llm(project_name: str, project_intent: str, existing_names: List[str]) -> dict:
    """调用 LLM 生成人物画像，失败时返回安全兜底。"""
    names_text = ", ".join([n for n in existing_names if n]) or "（无）"
    system_prompt = "你是一位人物画像设计专家，请严格输出 JSON，不要输出额外文字。"
    user_prompt = f"""请为以下项目生成一个新的用户画像（避免与已有画像重复）：

【项目名称】
{project_name}

【项目意图】
{project_intent or "未提供"}

【已有画像名称（避免重复）】
{names_text}

输出 JSON:
{{"name":"画像名称","prompt":"完整画像提示词（包含身份、背景、核心需求、顾虑、决策标准）"}}"""
    try:
        model = get_chat_model(temperature=0.8)
        response = await model.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        raw = response.content
        if isinstance(raw, list):
            raw = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in raw)
        parsed = _parse_json_response(raw if isinstance(raw, str) else str(raw))
        name = str(parsed.get("name", "")).strip()
        prompt = str(parsed.get("prompt", "")).strip()
        if not name:
            name = "新画像"
        if not prompt:
            prompt = f"你是{name}，请基于项目目标给出真实消费者视角反馈。"
        return {"name": name, "prompt": prompt}
    except Exception:
        return {
            "name": "新画像",
            "prompt": "你是一个潜在消费者，关注内容是否真正解决你的核心问题、成本是否合理、执行是否可行。",
        }


async def _generate_prompt_with_llm(prompt_type: str, context: dict) -> str:
    prompt_type_name = {
        "persona": "人物画像提示词",
        "consumer_prompt": "消费者提示词",
        "representative_prompt": "内容方提示词",
        "seller_prompt": "卖方提示词",
        "buyer_prompt": "买方提示词",
        "reviewer_prompt": "审查角色提示词",
        "grader_prompt": "评分器提示词",
    }.get(prompt_type, prompt_type)
    required_placeholders = _required_placeholders_for_prompt_type(prompt_type)
    form_type_name = str(context.get("form_type", "通用评估"))
    description = str(context.get("description", "")).strip()
    project_context = str(context.get("project_context", "")).strip()

    system_prompt = "你是一位提示词工程专家。请严格输出 JSON，不要输出额外文字。"
    user_prompt = f"""请为以下评估场景生成提示词：

【提示词类型】{prompt_type_name}
【评估形态】{form_type_name}
【角色/场景描述】{description or "未提供"}
【项目背景】{project_context or "未提供"}
【必须包含占位符】{", ".join(required_placeholders) if required_placeholders else "无"}

要求：
1) 角色定义清晰；
2) 行为要求具体；
3) 如果是评分场景，请包含评分锚点；
4) 包含结构化 JSON 输出格式说明；
5) 保留必须占位符。

输出 JSON:
{{"generated_prompt":"完整提示词"}}"""
    try:
        model = get_chat_model(temperature=0.7)
        response = await model.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        raw = response.content
        if isinstance(raw, list):
            raw = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in raw)
        parsed = _parse_json_response(raw if isinstance(raw, str) else str(raw))
        generated = str(parsed.get("generated_prompt", "")).strip()
        if generated:
            return generated
    except Exception:
        pass

    fallback = "你是评估专家。请基于提供内容执行评估，并严格输出 JSON 结果。"
    for ph in required_placeholders:
        if ph not in fallback:
            fallback += f"\n{ph}"
    return fallback


def _required_placeholders_for_prompt_type(prompt_type: str) -> List[str]:
    mapping = {
        "persona": ["{persona}", "{probe_section}"],
        "consumer_prompt": ["{persona}", "{content}"],
        "representative_prompt": ["{content}", "{probe_section}"],
        "seller_prompt": ["{persona}", "{content}", "{probe_section}"],
        "buyer_prompt": ["{persona}", "{probe_section}"],
        "reviewer_prompt": ["{content}", "{focus}"],
        "grader_prompt": ["{content}"],
    }
    return mapping.get(prompt_type, [])


def _find_sibling_by_handler(block, handler: str, db) -> ContentBlock:
    """找到同级（同 parent_id）的特定 handler 块"""
    return db.query(ContentBlock).filter(
        ContentBlock.project_id == block.project_id,
        ContentBlock.parent_id == block.parent_id,
        ContentBlock.special_handler == handler,
        ContentBlock.deleted_at == None,
    ).first()


def _suggestion_hash(source: str, suggestion: str) -> str:
    base = f"{(source or '').strip()}||{(suggestion or '').strip()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _set_task_runtime(task_id: str, patch: dict) -> None:
    with _TASK_RUNTIME_LOCK:
        prev = _TASK_RUNTIME_STATE.get(task_id, {})
        _TASK_RUNTIME_STATE[task_id] = {**prev, **patch}


def _get_task_runtime(task_id: str) -> dict:
    with _TASK_RUNTIME_LOCK:
        return dict(_TASK_RUNTIME_STATE.get(task_id, {}))


def _clear_task_runtime(task_id: str) -> None:
    with _TASK_RUNTIME_LOCK:
        _TASK_RUNTIME_STATE.pop(task_id, None)


def _build_task_progress_payload(task: EvalTaskV2) -> dict:
    rt = _get_task_runtime(task.id)
    # total 优先运行态；若运行态丢失，回退到 Task 配置总 Trial 数
    fallback_total = 0
    for c in (task.trial_configs or []):
        fallback_total += max(1, int(getattr(c, "repeat_count", 1) or 1))
    total = int(rt.get("total", 0) or fallback_total or 0)

    # completed 优先运行态；若缺失，回退到最新 batch 的已写入结果数
    if "completed" in rt and rt.get("completed") is not None:
        completed = int(rt.get("completed", 0) or 0)
    else:
        latest_batch = task.latest_batch_id or ""
        if latest_batch:
            completed = sum(1 for r in (task.trial_results or []) if (r.batch_id or "") == latest_batch)
        else:
            completed = 0
    if total > 0:
        percent = int(max(0, min(100, round(completed * 100 / total))))
    else:
        percent = 100 if task.status in ("completed", "failed", "stopped") else 0
    is_running = bool(rt.get("is_running", False)) and (task.status == "running")
    return {
        "total": total,
        "completed": completed,
        "percent": percent,
        "max_parallel": int(rt.get("max_parallel", max(1, int(settings.eval_max_parallel_trials or 1)))),
        "is_running": is_running,
        "is_paused": bool(rt.get("is_paused", False)),
        "stop_requested": bool(rt.get("stop_requested", False)),
        "pause_requested": bool(rt.get("pause_requested", False)),
        "resume_requested": bool(rt.get("resume_requested", False)),
        "batch_id": rt.get("batch_id", ""),
        "started_at": rt.get("started_at", ""),
        "updated_at": rt.get("updated_at", ""),
    }


def _recompute_task_latest_after_delete(task: EvalTaskV2, db: Session) -> None:
    latest_row = (
        db.query(EvalTrialResultV2)
        .filter(EvalTrialResultV2.task_id == task.id)
        .order_by(EvalTrialResultV2.created_at.desc())
        .first()
    )
    if not latest_row:
        task.latest_batch_id = ""
        task.latest_scores = {}
        task.latest_overall = None
        task.last_executed_at = None
        task.status = "pending"
        task.last_error = ""
        return

    batch_rows = (
        db.query(EvalTrialResultV2)
        .filter(
            EvalTrialResultV2.task_id == task.id,
            EvalTrialResultV2.batch_id == latest_row.batch_id,
        )
        .all()
    )
    aggregate_input = [
        {"overall_score": x.overall_score, "dimension_scores": x.dimension_scores or {}}
        for x in batch_rows
        if x.status == "completed"
    ]
    agg = aggregate_task_scores(aggregate_input)
    task.latest_batch_id = latest_row.batch_id
    task.latest_scores = agg
    task.latest_overall = (agg.get("overall") or {}).get("mean") if agg.get("overall") else None
    task.last_executed_at = latest_row.created_at
    task.status = "completed" if any(x.status == "completed" for x in batch_rows) else "failed"


def _serialize_task_v2(task: EvalTaskV2) -> dict:
    progress = _build_task_progress_payload(task)
    return {
        "id": task.id,
        "project_id": task.project_id,
        "name": task.name,
        "description": task.description or "",
        "order_index": task.order_index,
        "status": task.status,
        "last_error": task.last_error or "",
        "content_hash": task.content_hash or "",
        "last_executed_at": task.last_executed_at.isoformat() if task.last_executed_at else "",
        "latest_scores": task.latest_scores or {},
        "latest_overall": task.latest_overall,
        "latest_batch_id": task.latest_batch_id or "",
        "progress": progress,
        "can_stop": progress["is_running"],
        "can_pause": progress["is_running"],
        "can_resume": (task.status == "paused"),
        "trial_configs": [
            {
                "id": c.id,
                "name": c.name,
                "form_type": c.form_type,
                "target_block_ids": c.target_block_ids or [],
                "grader_ids": c.grader_ids or [],
                "grader_weights": c.grader_weights or {},
                "repeat_count": c.repeat_count,
                "probe": c.probe or "",
                "form_config": c.form_config or {},
                "order_index": c.order_index,
            }
            for c in sorted(task.trial_configs or [], key=lambda x: x.order_index)
        ],
    }


def _serialize_trial_result_v2(row: EvalTrialResultV2) -> dict:
    grader_results = row.grader_results or []
    evidence = _build_score_evidence(grader_results)
    suggestions = _extract_independent_suggestions(grader_results)
    return {
        "id": row.id,
        "task_id": row.task_id,
        "trial_config_id": row.trial_config_id,
        "trial_config_name": (row.trial_config.name if getattr(row, "trial_config", None) else ""),
        "project_id": row.project_id,
        "batch_id": row.batch_id,
        "repeat_index": row.repeat_index,
        "form_type": row.form_type,
        "process": row.process or [],
        "grader_results": grader_results,
        "dimension_scores": row.dimension_scores or {},
        "overall_score": row.overall_score,
        "overall_comment": _build_trial_overall_comment(row.form_type, row.overall_score, evidence),
        "score_evidence": evidence,
        "improvement_suggestions": suggestions,
        "llm_calls": row.llm_calls or [],
        "tokens_in": row.tokens_in or 0,
        "tokens_out": row.tokens_out or 0,
        "cost": row.cost or 0.0,
        "status": row.status,
        "error": row.error or "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _serialize_task_analysis_v2(analysis: TaskAnalysisV2) -> dict:
    return {
        "id": analysis.id,
        "task_id": analysis.task_id,
        "batch_id": analysis.batch_id,
        "patterns": analysis.patterns or [],
        "suggestions": analysis.suggestions or [],
        "strengths": analysis.strengths or [],
        "summary": analysis.summary or "",
        "llm_calls": analysis.llm_calls or [],
        "cost": analysis.cost or 0.0,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else "",
    }


def _build_score_evidence(grader_results: list) -> list[dict]:
    evidence_rows = []
    for gr in grader_results:
        if not isinstance(gr, dict):
            continue
        gname = str(gr.get("grader_name") or "评分器")
        scores = gr.get("scores") or {}
        comments = gr.get("comments") or {}
        if not isinstance(scores, dict):
            continue
        for dim, score in scores.items():
            dim_name = str(dim)
            ev_text = ""
            if isinstance(comments, dict):
                ev_text = str(comments.get(dim_name) or "").strip()
            if not ev_text:
                ev_text = "未提供该维度评分依据。"
            evidence_rows.append(
                {
                    "grader_name": gname,
                    "dimension": dim_name,
                    "score": score,
                    "evidence": ev_text,
                }
            )
    return evidence_rows


def _build_trial_overall_comment(form_type: str, overall_score: Optional[float], evidence_rows: list[dict]) -> str:
    if overall_score is None:
        return "本 Trial 尚无可用总评（可能执行失败或未产出可评分结果）。"
    summary = f"本 Trial 总体得分 {float(overall_score):.2f}/10。"
    if evidence_rows:
        top = evidence_rows[0]
        summary += f" 主要评分依据来自「{top.get('grader_name', '评分器')}」在「{top.get('dimension', '综合')}」维度的判断。"
    mode_hint = {
        "assessment": "该形态为直接判定，重点依据内容质量评分。",
        "review": "该形态为视角审查，重点依据角色视角下的内容判断。",
        "experience": "该形态为消费体验，结合探索过程与内容结果综合判断。",
        "scenario": "该形态为场景模拟，结合对话过程与内容结果综合判断。",
    }.get(form_type, "")
    if mode_hint:
        summary += f" {mode_hint}"
    return summary


def _extract_independent_suggestions(grader_results: list) -> list[str]:
    """
    从 grader feedback 中提取“独立建议句”，与 Trial 总评分离。
    """
    keywords = ["建议", "应", "需要", "优化", "改", "补充", "删除", "避免", "修正", "调整", "简化", "明确"]
    out = []
    for gr in grader_results:
        if not isinstance(gr, dict):
            continue
        feedback = str(gr.get("feedback") or "").strip()
        if not feedback:
            continue
        parts = re.split(r"[\n。；;]", feedback)
        for p in parts:
            line = p.strip()
            if len(line) < 6:
                continue
            if not any(k in line for k in keywords):
                continue
            out.append(line)
    deduped = []
    seen = set()
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        deduped.append(x)
    return deduped[:8]


def _replace_trial_configs_v2(task_id: str, trial_payloads: List[TrialConfigPayload], db: Session) -> None:
    db.query(EvalTrialConfigV2).filter(EvalTrialConfigV2.task_id == task_id).delete()
    for idx, tc in enumerate(trial_payloads):
        row = EvalTrialConfigV2(
            id=generate_uuid(),
            task_id=task_id,
            name=tc.name,
            form_type=tc.form_type,
            target_block_ids=tc.target_block_ids or [],
            grader_ids=tc.grader_ids or [],
            grader_weights=tc.grader_weights or {},
            repeat_count=max(1, int(tc.repeat_count or 1)),
            probe=tc.probe or "",
            form_config=tc.form_config or {},
            order_index=tc.order_index if tc.order_index is not None else idx,
        )
        db.add(row)


def _collect_eval_texts_by_block_ids(project_id: str, target_block_ids: list, db: Session) -> tuple[str, list[str], list[str]]:
    blocks_q = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.block_type == "field",
        ContentBlock.deleted_at == None,  # noqa: E711
    )
    if target_block_ids:
        blocks_q = blocks_q.filter(ContentBlock.id.in_(target_block_ids))
    else:
        blocks_q = blocks_q.filter(
            (ContentBlock.special_handler == None) |  # noqa: E711
            (~ContentBlock.special_handler.like("eval_%"))
        )

    blocks = blocks_q.order_by(ContentBlock.order_index.asc(), ContentBlock.created_at.asc()).all()
    content_parts = []
    names = []
    raw_contents = []
    for b in blocks:
        if b.content and b.content.strip():
            names.append(b.name)
            raw_contents.append(b.content)
            content_parts.append(f"## {b.name}\n{b.content}")
    return "\n\n---\n\n".join(content_parts), names, raw_contents


def _collect_eval_blocks_by_ids(project_id: str, target_block_ids: list, db: Session) -> List[dict]:
    """收集可评估内容块，用于 Experience 分块探索。"""
    blocks_q = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.block_type == "field",
        ContentBlock.deleted_at == None,  # noqa: E711
    )
    if target_block_ids:
        blocks_q = blocks_q.filter(ContentBlock.id.in_(target_block_ids))
    else:
        blocks_q = blocks_q.filter(
            (ContentBlock.special_handler == None) |  # noqa: E711
            (~ContentBlock.special_handler.like("eval_%"))
        )
    rows = blocks_q.order_by(ContentBlock.order_index.asc(), ContentBlock.created_at.asc()).all()
    out = []
    for r in rows:
        content = (r.content or "").strip()
        if not content:
            continue
        out.append({"id": r.id, "title": r.name, "content": content})
    return out


def _get_persona_map(project_id: str, db: Session) -> dict:
    blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.special_handler == "eval_persona_setup",
        ContentBlock.deleted_at == None,  # noqa: E711
    ).all()
    out = {}
    for pb in blocks:
        if not pb.content:
            continue
        try:
            data = json.loads(pb.content)
            for p in data.get("personas", []):
                pid = p.get("id")
                if pid:
                    out[pid] = p
        except Exception:
            continue
    return out


async def _run_selected_graders(
    grader_ids: list,
    content: str,
    process: list,
    fallback_grader_outputs: list,
    db: Session,
) -> tuple[list, list]:
    """
    运行选定 Grader（返回 grader_results, llm_calls）。
    """
    if not grader_ids:
        # 兼容：无显式 grader_ids，回退引擎内建 grader 输出
        mapped = []
        for go in fallback_grader_outputs or []:
            if not isinstance(go, dict):
                continue
            mapped.append({
                "grader_id": go.get("grader_id", ""),
                "grader_name": go.get("grader_name", go.get("grader_type", "默认评分器")),
                "scores": go.get("scores", {}) or {},
                "comments": go.get("comments", {}) or {},
                "feedback": go.get("feedback", go.get("analysis", go.get("summary", ""))),
            })
        return mapped, []

    process_transcript = _build_process_transcript(process)

    graders = db.query(Grader).filter(Grader.id.in_(grader_ids)).all()
    grader_map = {g.id: g for g in graders}
    tasks = []
    task_order = []
    for gid in grader_ids:
        g = grader_map.get(gid)
        if not g:
            continue
        tasks.append(
            run_individual_grader(
                grader_name=g.name,
                grader_type=g.grader_type,
                prompt_template=g.prompt_template or "",
                dimensions=g.dimensions or ["综合评价"],
                content=content,
                trial_result_data={},
                process_transcript=process_transcript,
            )
        )
        task_order.append(gid)

    results = await asyncio.gather(*tasks, return_exceptions=True)
    grader_results = []
    llm_calls = []
    for idx, res in enumerate(results):
        if isinstance(res, Exception):
            continue
        go, go_call = res
        gid = task_order[idx] if idx < len(task_order) else ""
        grader_results.append({
            "grader_id": gid,
            "grader_name": go.get("grader_name", ""),
            "scores": go.get("scores", {}) or {},
            "comments": go.get("comments", {}) or {},
            "feedback": go.get("feedback", ""),
        })
        if go_call:
            llm_calls.append(go_call.to_dict() if hasattr(go_call, "to_dict") else go_call)
    return grader_results, llm_calls


def _build_process_transcript(process: list) -> str:
    """
    将 Trial 过程统一序列化为可读 transcript，供 content_and_process grader 使用。
    兼容两类结构：
    - 对话节点: {role, content, turn}
    - 体验探索: {type: plan|per_block|summary, data: {...}}
    """
    if not process:
        return ""
    lines = []
    for idx, node in enumerate(process):
        if not isinstance(node, dict):
            lines.append(f"[step_{idx + 1}] {str(node)}")
            continue
        role = str(node.get("role") or "").strip()
        content = str(node.get("content") or "").strip()
        if role or content:
            turn = node.get("turn")
            turn_tag = f"#{turn}" if turn is not None else f"#{idx + 1}"
            lines.append(f"[dialogue {turn_tag} {role or 'assistant'}] {content}")
            continue

        ntype = str(node.get("type") or "").strip()
        if ntype == "plan":
            data = node.get("data") or {}
            goal = str(data.get("overall_goal") or "").strip()
            lines.append(f"[experience 阶段1-规划] 目标: {goal or '未提供'}")
            for pidx, p in enumerate(data.get("plan") or []):
                if not isinstance(p, dict):
                    continue
                title = p.get("block_title") or p.get("block_id") or f"block_{pidx+1}"
                reason = p.get("reason") or ""
                expectation = p.get("expectation") or ""
                lines.append(f"  - 先看 {title}; 原因: {reason}; 预期: {expectation}")
            continue
        if ntype == "per_block":
            data = node.get("data") or {}
            title = node.get("block_title") or node.get("block_id") or "未命名内容块"
            lines.append(f"[experience 阶段2-逐块探索] {title}")
            lines.append(
                f"  discovery={data.get('discovery', '')}; doubt={data.get('doubt', '')}; "
                f"missing={data.get('missing', '')}; feeling={data.get('feeling', '')}; score={data.get('score', '-')}"
            )
            continue
        if ntype == "summary":
            data = node.get("data") or {}
            lines.append("[experience 阶段3-总结]")
            lines.append(
                f"  overall_impression={data.get('overall_impression', '')}; "
                f"addressed={data.get('concerns_addressed', [])}; "
                f"unaddressed={data.get('concerns_unaddressed', [])}; summary={data.get('summary', '')}"
            )
            continue

        # 兜底：保留原始结构，确保过程不会丢。
        lines.append(f"[process #{idx + 1}] {json.dumps(node, ensure_ascii=False)}")

    return "\n".join(lines).strip()


async def _run_trial_config_once(
    task: EvalTaskV2,
    trial_cfg: EvalTrialConfigV2,
    repeat_index: int,
    batch_id: str,
    persona_map: dict,
    db: Session,
) -> EvalTrialResultV2:
    content_text, _, raw_contents = _collect_eval_texts_by_block_ids(
        task.project_id, trial_cfg.target_block_ids or [], db
    )
    content_blocks = _collect_eval_blocks_by_ids(task.project_id, trial_cfg.target_block_ids or [], db)
    if not content_text:
        return EvalTrialResultV2(
            id=generate_uuid(),
            task_id=task.id,
            trial_config_id=trial_cfg.id,
            project_id=task.project_id,
            batch_id=batch_id,
            repeat_index=repeat_index,
            form_type=trial_cfg.form_type,
            status="failed",
            error="没有可评估内容",
        )

    creator_profile = ""
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if project:
        creator_profile = _get_creator_profile(project, db)
    intent = _get_project_intent(project, db) if project else ""

    llm_calls = []
    process = []
    grader_results = []
    dimension_scores = {}
    overall_score = None
    status = "completed"
    error = ""
    tokens_in = 0
    tokens_out = 0
    cost = 0.0

    try:
        form = trial_cfg.form_type
        form_config = trial_cfg.form_config or {}
        probe_text = trial_cfg.probe or form_config.get("probe", "")

        if form == "assessment":
            # 直接判定：只跑 Grader
            grader_results, g_calls = await _run_selected_graders(
                trial_cfg.grader_ids or [],
                content_text,
                [],
                [],
                db,
            )
            llm_calls.extend(g_calls)
            overall_score, dimension_scores = compute_weighted_grader_score(
                grader_results, trial_cfg.grader_weights or {}
            )

        elif form == "experience":
            # Experience: 三步分块探索（规划 -> 逐块 -> 总结）
            persona_id = form_config.get("persona_id")
            p = persona_map.get(persona_id, {}) if persona_id else {}
            persona_name = p.get("name", form_config.get("persona_name", "消费者"))
            persona_prompt = p.get("prompt", form_config.get("persona_prompt", "你是一个真实消费者。"))
            exp_result = await run_experience_trial(
                persona_name=persona_name,
                persona_prompt=persona_prompt,
                probe=probe_text,
                blocks=content_blocks,
            )
            process = exp_result.process or []
            llm_calls.extend(exp_result.llm_calls or [])
            if exp_result.error:
                status = "failed"
                error = exp_result.error

            selected_graders, g_calls = await _run_selected_graders(
                trial_cfg.grader_ids or [],
                content_text,
                process,
                [],
                db,
            )
            grader_results = selected_graders
            llm_calls.extend(g_calls)
            overall_score, dimension_scores = compute_weighted_grader_score(
                grader_results, trial_cfg.grader_weights or {}
            )
            if overall_score is None:
                # 无 Grader 时回退到分块探索均值
                overall_score = exp_result.exploration_score
                if overall_score is not None:
                    dimension_scores = {"体验探索分": overall_score}

        else:
            # review / scenario 借助现有 run_task_trial
            simulator_type = "coach"
            interaction_mode = "review"
            simulator_config = {}
            persona = None

            if form == "review":
                interaction_mode = "review"
                persona_id = form_config.get("persona_id")
                reviewer = persona_map.get(persona_id, {}) if persona_id else {}
                simulator_type = form_config.get("simulator_type", "editor")
                persona = reviewer if reviewer else {"name": "审查角色", "prompt": form_config.get("system_prompt", "")}
                simulator_config = {
                    "system_prompt": form_config.get("system_prompt", reviewer.get("prompt", "")),
                    "max_turns": 1,
                }
            elif form == "scenario":
                interaction_mode = "scenario"
                simulator_type = "seller"
                role_a_id = form_config.get("role_a_persona_id")
                role_b_id = form_config.get("role_b_persona_id")
                role_a = persona_map.get(role_a_id, {}) if role_a_id else {}
                role_b = persona_map.get(role_b_id, {}) if role_b_id else {}
                persona = role_b if role_b else {"name": "角色B", "prompt": form_config.get("role_b_prompt", "")}
                simulator_config = {
                    "system_prompt": form_config.get("role_a_prompt", role_a.get("prompt", "")),
                    "secondary_prompt": form_config.get("role_b_prompt", role_b.get("prompt", "")),
                    "max_turns": int(form_config.get("max_turns", 5) or 5),
                }

            if probe_text:
                origin = simulator_config.get("system_prompt", "")
                simulator_config["system_prompt"] = (origin + f"\n\n【本次焦点】\n{probe_text}").strip()

            fallback_note = None
            try:
                trial = await run_task_trial(
                    simulator_type=simulator_type,
                    interaction_mode=interaction_mode,
                    content=content_text,
                    creator_profile=creator_profile,
                    intent=intent,
                    persona=persona,
                    simulator_config=simulator_config,
                    grader_config={"type": "content", "dimensions": []},
                )
            except Exception as trial_err:
                # 场景模拟兜底：若 seller 路径异常，回退到 consumer 对话，避免整条 Trial 直接失败。
                if form == "scenario":
                    fallback_persona = persona or {"name": "目标消费者", "background": "默认画像"}
                    fallback_cfg = {
                        "system_prompt": form_config.get("role_b_prompt", ""),
                        "max_turns": int(form_config.get("max_turns", 5) or 5),
                    }
                    trial = await run_task_trial(
                        simulator_type="consumer",
                        interaction_mode="dialogue",
                        content=content_text,
                        creator_profile=creator_profile,
                        intent=intent,
                        persona=fallback_persona,
                        simulator_config=fallback_cfg,
                        grader_config={"type": "content", "dimensions": []},
                    )
                    fallback_note = {
                        "type": "system_note",
                        "stage": "兜底策略",
                        "content": f"scenario 模式主路径失败，已回退到 dialogue 兜底执行: {str(trial_err)}",
                    }
                else:
                    raise

            process = trial.nodes or []
            if fallback_note:
                process = [fallback_note, *process]
            llm_calls.extend(trial.llm_calls or [])
            tokens_in += int(trial.tokens_in or 0)
            tokens_out += int(trial.tokens_out or 0)
            cost += float(trial.cost or 0.0)
            if not trial.success:
                status = "failed"
                error = trial.error or "trial 执行失败"

            selected_graders, g_calls = await _run_selected_graders(
                trial_cfg.grader_ids or [],
                content_text,
                process,
                trial.grader_outputs or [],
                db,
            )
            grader_results = selected_graders
            llm_calls.extend(g_calls)
            overall_score, dimension_scores = compute_weighted_grader_score(
                grader_results, trial_cfg.grader_weights or {}
            )

        content_hash = compute_content_hash(raw_contents)
        task.content_hash = content_hash

    except Exception as e:
        status = "failed"
        error = str(e)

    # 汇总日志统计（部分 call 可能是 dict）
    for c in llm_calls:
        if isinstance(c, dict):
            tokens_in += int(c.get("tokens_in", 0) or 0)
            tokens_out += int(c.get("tokens_out", 0) or 0)
            cost += float(c.get("cost", 0.0) or 0.0)

    return EvalTrialResultV2(
        id=generate_uuid(),
        task_id=task.id,
        trial_config_id=trial_cfg.id,
        project_id=task.project_id,
        batch_id=batch_id,
        repeat_index=repeat_index,
        form_type=trial_cfg.form_type,
        process=process,
        grader_results=grader_results,
        dimension_scores=dimension_scores,
        overall_score=overall_score,
        llm_calls=llm_calls,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost,
        status=status,
        error=error,
    )


def _build_trial_plan(configs: List[EvalTrialConfigV2]) -> list[tuple[EvalTrialConfigV2, int]]:
    plan = []
    for cfg in configs:
        repeats = max(1, int(cfg.repeat_count or 1))
        for ridx in range(repeats):
            plan.append((cfg, ridx))
    return plan


def _row_to_payload(row: EvalTrialResultV2) -> dict:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "trial_config_id": row.trial_config_id,
        "project_id": row.project_id,
        "batch_id": row.batch_id,
        "repeat_index": row.repeat_index,
        "form_type": row.form_type,
        "process": row.process or [],
        "grader_results": row.grader_results or [],
        "dimension_scores": row.dimension_scores or {},
        "overall_score": row.overall_score,
        "llm_calls": row.llm_calls or [],
        "tokens_in": row.tokens_in or 0,
        "tokens_out": row.tokens_out or 0,
        "cost": row.cost or 0.0,
        "status": row.status or "failed",
        "error": row.error or "",
    }


async def _run_trial_plan_item_isolated(
    session_factory,
    task_id: str,
    trial_config_id: str,
    repeat_index: int,
    batch_id: str,
) -> dict:
    wdb = session_factory()
    try:
        task = wdb.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
        cfg = wdb.query(EvalTrialConfigV2).filter(EvalTrialConfigV2.id == trial_config_id).first()
        if not task or not cfg:
            return {
                "id": generate_uuid(),
                "task_id": task_id,
                "trial_config_id": trial_config_id,
                "project_id": task.project_id if task else "",
                "batch_id": batch_id,
                "repeat_index": repeat_index,
                "form_type": cfg.form_type if cfg else "assessment",
                "status": "failed",
                "error": "任务或试验配置不存在",
            }
        persona_map = _get_persona_map(task.project_id, wdb)
        try:
            row = await asyncio.wait_for(
                _run_trial_config_once(task, cfg, repeat_index, batch_id, persona_map, wdb),
                timeout=300,
            )
        except asyncio.TimeoutError:
            row = EvalTrialResultV2(
                id=generate_uuid(),
                task_id=task.id,
                trial_config_id=cfg.id,
                project_id=task.project_id,
                batch_id=batch_id,
                repeat_index=repeat_index,
                form_type=cfg.form_type,
                status="failed",
                error="单次 Trial 执行超时（300s）",
            )
        return _row_to_payload(row)
    finally:
        wdb.close()


def _load_done_keys_for_batch(task_id: str, batch_id: str, db: Session) -> set[tuple[str, int]]:
    rows = (
        db.query(EvalTrialResultV2.trial_config_id, EvalTrialResultV2.repeat_index)
        .filter(
            EvalTrialResultV2.task_id == task_id,
            EvalTrialResultV2.batch_id == batch_id,
        )
        .all()
    )
    return {(str(tc_id), int(ridx)) for tc_id, ridx in rows}


async def _execute_task_v2(task_id: str, db: Session, resume_batch_id: Optional[str] = None) -> dict:
    task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="EvalTask not found")

    configs = (
        db.query(EvalTrialConfigV2)
        .filter(EvalTrialConfigV2.task_id == task_id)
        .order_by(EvalTrialConfigV2.order_index.asc())
        .all()
    )
    if not configs:
        raise HTTPException(status_code=400, detail="Task 没有 Trial 配置")

    plan = _build_trial_plan(configs)
    total_runs = len(plan)
    batch_id = resume_batch_id or generate_uuid()
    done_keys = _load_done_keys_for_batch(task_id, batch_id, db) if resume_batch_id else set()
    pending_plan = [(cfg.id, ridx) for cfg, ridx in plan if (cfg.id, ridx) not in done_keys]
    max_parallel = max(1, int(settings.eval_max_parallel_trials or 1))
    worker_session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db.get_bind(),
    )

    task.status = "running"
    task.last_error = ""
    # 在执行开始即写入当前 batch，便于进度与排障
    task.latest_batch_id = batch_id
    db.commit()
    _set_task_runtime(
        task_id,
        {
            "task_id": task_id,
            "batch_id": batch_id,
            "total": total_runs,
            "completed": len(done_keys),
            "is_running": True,
            "is_paused": False,
            "pause_requested": False,
            "stop_requested": False,
            "started_at": _get_task_runtime(task_id).get("started_at", datetime.now(timezone.utc).isoformat()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    run_rows = []
    stopped = False
    paused = False
    inflight: dict[asyncio.Task, tuple[str, int]] = {}
    cursor = 0
    while cursor < len(pending_plan) or inflight:
        rt = _get_task_runtime(task_id)
        while (
            cursor < len(pending_plan)
            and len(inflight) < max_parallel
            and not rt.get("stop_requested")
            and not rt.get("pause_requested")
        ):
            cfg_id, ridx = pending_plan[cursor]
            cursor += 1
            t = asyncio.create_task(_run_trial_plan_item_isolated(worker_session_factory, task_id, cfg_id, ridx, batch_id))
            inflight[t] = (cfg_id, ridx)

        if not inflight:
            if rt.get("stop_requested"):
                stopped = True
            if rt.get("pause_requested"):
                paused = True
            break

        done, _ = await asyncio.wait(set(inflight.keys()), return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            cfg_id, ridx = inflight.pop(t, ("", 0))
            try:
                payload = t.result()
            except Exception as e:
                payload = {
                    "id": generate_uuid(),
                    "task_id": task.id,
                    "trial_config_id": cfg_id,
                    "project_id": task.project_id,
                    "batch_id": batch_id,
                    "repeat_index": ridx,
                    "form_type": "assessment",
                    "status": "failed",
                    "error": str(e),
                }
            row = EvalTrialResultV2(**payload)
            db.add(row)
            run_rows.append(row)
            _set_task_runtime(
                task_id,
                {
                    "completed": len(done_keys) + len(run_rows),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        rt_after = _get_task_runtime(task_id)
        if rt_after.get("stop_requested"):
            stopped = True
        if rt_after.get("pause_requested"):
            paused = True

    db.flush()

    all_rows = (
        db.query(EvalTrialResultV2)
        .filter(
            EvalTrialResultV2.task_id == task_id,
            EvalTrialResultV2.batch_id == batch_id,
        )
        .order_by(EvalTrialResultV2.created_at.asc())
        .all()
    )
    aggregate_input = [
        {"overall_score": r.overall_score, "dimension_scores": r.dimension_scores or {}}
        for r in all_rows
        if r.status == "completed"
    ]
    agg = aggregate_task_scores(aggregate_input)
    task.latest_scores = agg
    task.latest_overall = (agg.get("overall") or {}).get("mean") if agg.get("overall") else None
    task.latest_batch_id = batch_id
    task.last_executed_at = datetime.now(timezone.utc)
    if stopped:
        task.status = "stopped"
    elif paused:
        task.status = "paused"
    else:
        task.status = "completed" if any(r.status == "completed" for r in all_rows) else "failed"
    task.last_error = "; ".join([r.error for r in all_rows if r.error])[:2000]

    db.commit()
    db.refresh(task)
    _set_task_runtime(
        task_id,
        {
            "completed": len(done_keys) + len(run_rows),
            "is_running": False,
            "is_paused": paused,
            "pause_requested": False,
            "stop_requested": False,
            "max_parallel": max_parallel,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # 若用户在“暂停尚未落稳”阶段已点击恢复，则自动续跑
    rt_final = _get_task_runtime(task_id)
    if task.status == "paused" and rt_final.get("resume_requested"):
        _set_task_runtime(task_id, {"resume_requested": False, "updated_at": datetime.now(timezone.utc).isoformat()})
        asyncio.create_task(_execute_task_v2_background(task_id, resume_batch_id=batch_id))

    return {
        "task": _serialize_task_v2(task),
        "batch_id": batch_id,
        "overall": task.latest_overall,
        "trials": [_serialize_trial_result_v2(r) for r in all_rows],
    }


async def _execute_task_v2_background(task_id: str, resume_batch_id: Optional[str] = None) -> None:
    """
    后台执行 V2 Task，使用独立 DB Session，避免请求结束后 session 失效。
    """
    SessionLocal = get_session_maker()
    db = SessionLocal()
    try:
        await _execute_task_v2(task_id, db, resume_batch_id=resume_batch_id)
    except Exception as e:
        task = db.query(EvalTaskV2).filter(EvalTaskV2.id == task_id).first()
        if task:
            task.status = "failed"
            task.last_error = str(e)[:2000]
            db.commit()
    finally:
        rt = _get_task_runtime(task_id)
        _set_task_runtime(
            task_id,
            {
                "is_running": False,
                "is_paused": bool(rt.get("is_paused", False)),
                "pause_requested": False,
                "stop_requested": False,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.close()


def _build_task_analysis_from_trials(task: EvalTaskV2, rows: List[EvalTrialResultV2], batch_id: str) -> TaskAnalysisV2:
    # 规则化分析（避免额外 LLM 成本，先提供可靠可解释的结果）
    dim_low_count = {}
    feedback_lines = []
    strengths = []
    for r in rows:
        dims = r.dimension_scores or {}
        for dim, score in dims.items():
            if isinstance(score, (int, float)) and score < 7:
                dim_low_count[dim] = dim_low_count.get(dim, 0) + 1
        for gr in r.grader_results or []:
            fb = (gr or {}).get("feedback", "")
            if fb:
                feedback_lines.append(str(fb))
            comments = (gr or {}).get("comments", {}) or {}
            for k, v in comments.items():
                if isinstance(v, str) and ("优点" in v or "清晰" in v or "准确" in v):
                    strengths.append(f"{k}: {v[:80]}")

    patterns = []
    suggestions = []
    total = max(1, len(rows))
    for dim, cnt in sorted(dim_low_count.items(), key=lambda x: x[1], reverse=True):
        severity = "high" if cnt / total >= 0.6 else "medium"
        patterns.append({
            "title": f"{dim} 在多个 Trial 中偏低",
            "frequency": f"{cnt}/{total}",
            "evidence": [f"{cnt} 次结果低于 7 分"],
            "severity": severity,
        })
        suggestions.append({
            "title": f"优先提升「{dim}」",
            "severity": severity,
            "detail": f"针对 {dim} 增加更具体的论据、结构化表达和可执行示例。",
            "related_patterns": [f"{dim} 在多个 Trial 中偏低"],
        })

    if not patterns and feedback_lines:
        patterns.append({
            "title": "反馈聚焦在少数改进点",
            "frequency": f"{len(feedback_lines)}/{total}",
            "evidence": feedback_lines[:3],
            "severity": "medium",
        })
        suggestions.append({
            "title": "基于反馈逐条改写关键段落",
            "severity": "medium",
            "detail": "优先处理重复出现的负向反馈，逐条验证改写后分数变化。",
            "related_patterns": ["反馈聚焦在少数改进点"],
        })

    summary = f"任务「{task.name}」共分析 {len(rows)} 条 Trial，识别到 {len(patterns)} 个共性模式。"

    return TaskAnalysisV2(
        id=generate_uuid(),
        task_id=task.id,
        batch_id=batch_id,
        patterns=patterns,
        suggestions=suggestions,
        strengths=strengths[:8],
        summary=summary,
        llm_calls=[],
        cost=0.0,
    )


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
