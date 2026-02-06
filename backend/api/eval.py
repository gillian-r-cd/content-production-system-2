# backend/api/eval.py
# 功能: Eval 体系 API - 角色驱动的内容评估
# 主要路由: 运行评估、查看Trial、运行诊断
# 数据结构: EvalRun, EvalTrial

"""
Eval API
角色驱动的内容评估体系，支持5种评估角色 + 诊断器
"""

import json
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
    EvalTrial,
    EVAL_ROLES,
    GenerationLog,
    generate_uuid,
)
from core.tools.eval_engine import (
    run_eval,
    run_review_trial,
    run_consumer_dialogue_trial,
    run_seller_dialogue_trial,
    run_diagnoser,
    format_trial_result_markdown,
    format_diagnosis_markdown,
    TrialResult,
)


router = APIRouter(prefix="/api/eval", tags=["eval"])


# ============== Schemas ==============

class RunEvalRequest(PydanticBase):
    """运行评估请求"""
    project_id: str
    name: str = "综合评估"
    roles: List[str] = ["coach", "editor", "expert", "consumer", "seller"]
    input_block_ids: Optional[List[str]] = None  # None = 所有已完成字段
    max_turns: int = 5
    personas: Optional[List[dict]] = None  # 不指定则使用项目消费者画像


class RunSingleTrialRequest(PydanticBase):
    """运行单个 Trial 请求"""
    project_id: str
    role: str  # coach/editor/expert/consumer/seller
    input_block_ids: Optional[List[str]] = None
    persona: Optional[dict] = None
    interaction_mode: str = "review"  # review/dialogue


class EvalRunResponse(PydanticBase):
    """EvalRun 响应"""
    id: str
    project_id: str
    name: str
    status: str
    summary: str
    overall_score: Optional[float]
    role_scores: dict
    trial_count: int
    content_block_id: Optional[str]
    created_at: str
    
    model_config = {"from_attributes": True}


class EvalTrialResponse(PydanticBase):
    """EvalTrial 响应"""
    id: str
    eval_run_id: str
    role: str
    role_config: dict
    interaction_mode: str
    input_block_ids: list
    persona: dict
    nodes: list
    result: dict
    grader_outputs: list
    overall_score: Optional[float]
    status: str
    error: str
    tokens_in: int
    tokens_out: int
    cost: float
    created_at: str
    
    model_config = {"from_attributes": True}


# ============== Routes ==============

@router.get("/roles")
def get_available_roles():
    """获取所有可用的评估角色"""
    return EVAL_ROLES


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


@router.get("/run/{run_id}", response_model=EvalRunResponse)
def get_eval_run(run_id: str, db: Session = Depends(get_db)):
    """获取评估运行详情"""
    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    return _to_run_response(run)


@router.get("/run/{run_id}/trials", response_model=List[EvalTrialResponse])
def get_eval_trials(run_id: str, db: Session = Depends(get_db)):
    """获取评估运行的所有 Trial"""
    trials = (
        db.query(EvalTrial)
        .filter(EvalTrial.eval_run_id == run_id)
        .order_by(EvalTrial.created_at)
        .all()
    )
    return [_to_trial_response(t) for t in trials]


@router.get("/trial/{trial_id}", response_model=EvalTrialResponse)
def get_eval_trial(trial_id: str, db: Session = Depends(get_db)):
    """获取单个 Trial 详情"""
    trial = db.query(EvalTrial).filter(EvalTrial.id == trial_id).first()
    if not trial:
        raise HTTPException(status_code=404, detail="EvalTrial not found")
    return _to_trial_response(trial)


@router.post("/run", response_model=EvalRunResponse)
async def run_evaluation(request: RunEvalRequest, db: Session = Depends(get_db)):
    """
    运行完整评估（所有角色并行执行）
    """
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 收集内容
    content, field_names = _collect_content(
        project.id, request.input_block_ids, db
    )
    if not content:
        raise HTTPException(status_code=400, detail="项目中没有可评估的内容")
    
    # 获取创作者特质
    creator_profile = _get_creator_profile(project, db)
    
    # 获取意图
    intent = _get_project_intent(project, db)
    
    # 获取 personas
    personas = request.personas or _get_project_personas(project, db)
    
    # 创建 EvalRun
    eval_run = EvalRun(
        id=generate_uuid(),
        project_id=project.id,
        name=request.name,
        config={
            "roles": request.roles,
            "max_turns": request.max_turns,
            "input_block_ids": request.input_block_ids,
        },
        status="running",
    )
    db.add(eval_run)
    db.commit()
    
    try:
        # 运行评估
        trial_results, diagnosis = await run_eval(
            content=content,
            roles=request.roles,
            creator_profile=creator_profile,
            intent=intent,
            personas=personas,
            max_turns=request.max_turns,
            content_field_names=field_names,
        )
        
        # 保存 Trials
        role_scores = {}
        for tr in trial_results:
            trial = EvalTrial(
                id=generate_uuid(),
                eval_run_id=eval_run.id,
                role=tr.role,
                role_config={"system_prompt": "..."},
                interaction_mode=tr.interaction_mode,
                input_block_ids=request.input_block_ids or [],
                persona=tr.result.get("persona", {}),
                nodes=tr.nodes,
                result=tr.result,
                grader_outputs=tr.grader_outputs,
                overall_score=tr.overall_score,
                status="completed" if tr.success else "failed",
                error=tr.error,
                tokens_in=tr.tokens_in,
                tokens_out=tr.tokens_out,
                cost=tr.cost,
            )
            db.add(trial)
            
            # 记录 GenerationLog
            gen_log = GenerationLog(
                id=generate_uuid(),
                project_id=project.id,
                operation=f"eval_{tr.role}_{tr.interaction_mode}",
                prompt_input=f"Eval Trial: {tr.role}",
                prompt_output=tr.result.get("summary", "")[:500],
                tokens_in=tr.tokens_in,
                tokens_out=tr.tokens_out,
                cost=tr.cost,
                model="default",
                duration_ms=0,
                status="success" if tr.success else "failed",
            )
            db.add(gen_log)
            
            if tr.success and tr.role not in role_scores:
                role_scores[tr.role] = tr.overall_score
        
        # 更新 EvalRun
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


@router.post("/trial", response_model=EvalTrialResponse)
async def run_single_trial(request: RunSingleTrialRequest, db: Session = Depends(get_db)):
    """运行单个 Trial（可单独执行某个角色的评估）"""
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if request.role not in EVAL_ROLES:
        raise HTTPException(status_code=400, detail=f"无效角色: {request.role}")
    
    content, field_names = _collect_content(
        project.id, request.input_block_ids, db
    )
    if not content:
        raise HTTPException(status_code=400, detail="项目中没有可评估的内容")
    
    creator_profile = _get_creator_profile(project, db)
    intent = _get_project_intent(project, db)
    persona = (request.persona or _get_project_personas(project, db)[0]) if request.role in ("consumer", "seller") else {}
    
    try:
        result: TrialResult
        
        if request.role in ("coach", "editor", "expert"):
            result = await run_review_trial(
                role=request.role,
                content=content,
                creator_profile=creator_profile,
                intent=intent,
            )
        elif request.role == "consumer":
            if request.interaction_mode == "dialogue":
                result = await run_consumer_dialogue_trial(
                    content=content,
                    persona=persona,
                    content_field_names=field_names,
                )
            else:
                result = await run_review_trial(
                    role="consumer",
                    content=content,
                    persona=persona,
                )
        elif request.role == "seller":
            result = await run_seller_dialogue_trial(
                content=content,
                persona=persona,
            )
        else:
            raise HTTPException(status_code=400, detail=f"未支持的角色: {request.role}")
        
        # 保存 Trial（无 EvalRun 的独立 Trial - 创建临时 EvalRun）
        eval_run = EvalRun(
            id=generate_uuid(),
            project_id=project.id,
            name=f"单项评估: {EVAL_ROLES[request.role]['name']}",
            config={"roles": [request.role]},
            status="completed",
            overall_score=result.overall_score,
            role_scores={request.role: result.overall_score},
            trial_count=1,
        )
        db.add(eval_run)
        
        trial = EvalTrial(
            id=generate_uuid(),
            eval_run_id=eval_run.id,
            role=result.role,
            interaction_mode=result.interaction_mode,
            input_block_ids=request.input_block_ids or [],
            persona=persona or {},
            nodes=result.nodes,
            result=result.result,
            overall_score=result.overall_score,
            status="completed" if result.success else "failed",
            error=result.error,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost=result.cost,
        )
        db.add(trial)
        
        # GenerationLog
        gen_log = GenerationLog(
            id=generate_uuid(),
            project_id=project.id,
            operation=f"eval_single_{result.role}",
            prompt_input=f"Single Eval Trial: {result.role}",
            prompt_output=result.result.get("summary", "")[:500],
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost=result.cost,
            model="default",
            duration_ms=0,
            status="success" if result.success else "failed",
        )
        db.add(gen_log)
        
        db.commit()
        db.refresh(trial)
        
        return _to_trial_response(trial)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trial 运行失败: {str(e)}")


@router.post("/run/{run_id}/diagnose")
async def run_diagnosis(run_id: str, db: Session = Depends(get_db)):
    """对已完成的评估运行执行跨角色诊断"""
    eval_run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not eval_run:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    
    trials = (
        db.query(EvalTrial)
        .filter(EvalTrial.eval_run_id == run_id, EvalTrial.status == "completed")
        .all()
    )
    
    if not trials:
        raise HTTPException(status_code=400, detail="没有已完成的 Trial")
    
    # 构建 TrialResult 列表
    trial_results = []
    for t in trials:
        tr = TrialResult(
            role=t.role,
            interaction_mode=t.interaction_mode,
            nodes=t.nodes or [],
            result=t.result or {},
            grader_outputs=t.grader_outputs or [],
            overall_score=t.overall_score or 0,
            success=True,
        )
        trial_results.append(tr)
    
    # 获取意图
    project = db.query(Project).filter(Project.id == eval_run.project_id).first()
    intent = _get_project_intent(project, db) if project else ""
    
    # 运行诊断
    diagnosis = await run_diagnoser(
        trial_results=trial_results,
        intent=intent,
    )
    
    # 更新 EvalRun
    eval_run.summary = diagnosis.get("summary", "")
    eval_run.overall_score = diagnosis.get("overall_score", eval_run.overall_score)
    db.commit()
    
    return diagnosis


@router.post("/generate-for-block/{block_id}")
async def generate_eval_for_block(block_id: str, db: Session = Depends(get_db)):
    """
    为 ContentBlock 生成评估内容
    
    当用户在 special_handler=eval_* 的字段上点击生成时调用。
    将评估结果写入 block.content。
    """
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    
    handler = block.special_handler
    if not handler or not handler.startswith("eval_"):
        raise HTTPException(status_code=400, detail="此内容块不是评估字段")
    
    project = db.query(Project).filter(Project.id == block.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 收集项目内容（排除评估阶段本身的内容）
    content, field_names = _collect_content(project.id, None, db, exclude_eval=True)
    if not content:
        raise HTTPException(status_code=400, detail="项目中没有可评估的内容")
    
    creator_profile = _get_creator_profile(project, db)
    intent = _get_project_intent(project, db)
    personas = _get_project_personas(project, db)
    
    block.status = "in_progress"
    db.commit()
    
    try:
        role = handler.replace("eval_", "")
        
        if role == "container":
            # 容器不生成内容
            block.content = "请分别点击各评估字段进行评估，或使用「综合诊断」汇总结果。"
            block.status = "completed"
            db.commit()
            return {"message": "容器字段已更新", "content": block.content}
        
        elif role == "diagnoser":
            # 诊断器：收集同项目的其他 eval 字段结果
            trial_results = []
            sibling_blocks = db.query(ContentBlock).filter(
                ContentBlock.project_id == project.id,
                ContentBlock.special_handler.like("eval_%"),
                ContentBlock.special_handler != "eval_container",
                ContentBlock.special_handler != "eval_diagnoser",
                ContentBlock.status == "completed",
                ContentBlock.deleted_at == None,
            ).all()
            
            for sb in sibling_blocks:
                if sb.content:
                    # 尝试从 content 中提取评分信息
                    trial_results.append(TrialResult(
                        role=sb.special_handler.replace("eval_", ""),
                        interaction_mode="review",
                        result={"summary": sb.content[:500]},
                        overall_score=_extract_score_from_content(sb.content),
                        success=True,
                    ))
            
            if not trial_results:
                raise HTTPException(status_code=400, detail="请先完成其他评估角色的评估")
            
            diagnosis = await run_diagnoser(
                trial_results=trial_results,
                intent=intent,
            )
            
            block.content = format_diagnosis_markdown(diagnosis)
            block.status = "completed"
            db.commit()
            
            return {"message": "综合诊断完成", "content": block.content}
        
        elif role in ("coach", "editor", "expert"):
            result = await run_review_trial(
                role=role,
                content=content,
                creator_profile=creator_profile,
                intent=intent,
            )
        
        elif role == "consumer":
            if personas:
                result = await run_consumer_dialogue_trial(
                    content=content,
                    persona=personas[0],
                    content_field_names=field_names,
                )
            else:
                result = await run_review_trial(
                    role="consumer",
                    content=content,
                )
        
        elif role == "seller":
            result = await run_seller_dialogue_trial(
                content=content,
                persona=personas[0] if personas else {"name": "典型用户", "background": "对该领域有兴趣的读者"},
            )
        
        else:
            raise HTTPException(status_code=400, detail=f"未知评估角色: {role}")
        
        # 将结果写入 block.content
        md = format_trial_result_markdown(result)
        block.content = md
        block.status = "completed" if result.success else "failed"
        db.commit()
        
        # 记录 GenerationLog
        gen_log = GenerationLog(
            id=generate_uuid(),
            project_id=project.id,
            operation=f"eval_block_{role}",
            prompt_input=f"Eval Block: {block.name}",
            prompt_output=md[:500],
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost=result.cost,
            model="default",
            duration_ms=0,
            status="success" if result.success else "failed",
        )
        db.add(gen_log)
        db.commit()
        
        return {
            "message": f"{EVAL_ROLES.get(role, {}).get('name', role)}评估完成",
            "content": md,
            "score": result.overall_score,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        block.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"评估失败: {str(e)}")


@router.delete("/run/{run_id}")
def delete_eval_run(run_id: str, db: Session = Depends(get_db)):
    """删除评估运行及其所有 Trial"""
    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    
    # 级联删除 Trial
    db.query(EvalTrial).filter(EvalTrial.eval_run_id == run_id).delete()
    db.delete(run)
    db.commit()
    
    return {"message": "已删除"}


# ============== Helpers ==============

def _collect_content(
    project_id: str,
    block_ids: list = None,
    db: Session = None,
    exclude_eval: bool = False,
) -> tuple:
    """收集项目的已完成内容"""
    from core.models import ProjectField
    
    all_content = []
    field_names = []
    
    # 从 ContentBlock 收集
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
    
    # 也从 ProjectField 收集
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
    """获取项目的创作者特质"""
    if project.creator_profile_id:
        profile = db.query(CreatorProfile).filter(
            CreatorProfile.id == project.creator_profile_id
        ).first()
        if profile:
            traits = profile.traits or {}
            return f"**{profile.name}**\n语调: {traits.get('tone', '')}\n词汇: {traits.get('vocabulary', '')}\n性格: {traits.get('personality', '')}"
    return ""


def _get_project_intent(project, db) -> str:
    """获取项目意图"""
    from core.models import ProjectField
    
    # 从 ContentBlock 找
    intent_block = db.query(ContentBlock).filter(
        ContentBlock.project_id == project.id,
        ContentBlock.name.in_(["意图分析", "项目意图", "Intent"]),
        ContentBlock.deleted_at == None,
    ).first()
    
    if intent_block and intent_block.content:
        return intent_block.content
    
    # 从 ProjectField 找
    intent_field = db.query(ProjectField).filter(
        ProjectField.project_id == project.id,
        ProjectField.phase == "intent",
    ).first()
    
    if intent_field and intent_field.content:
        return intent_field.content
    
    return project.name or ""


def _get_project_personas(project, db) -> list:
    """获取项目的消费者画像"""
    from core.models import SimulationRecord
    
    # 尝试从模拟记录中获取
    sim_records = db.query(SimulationRecord).filter(
        SimulationRecord.project_id == project.id,
    ).limit(3).all()
    
    personas = []
    for sr in sim_records:
        if sr.persona:
            personas.append(sr.persona)
    
    # 默认 persona
    if not personas:
        personas = [{
            "name": "目标用户",
            "background": f"对「{project.name}」话题感兴趣的读者",
            "story": "希望获取有价值的信息和指导来解决实际问题。",
        }]
    
    return personas


def _extract_score_from_content(content: str) -> float:
    """从 Markdown 内容中提取评分"""
    import re
    # 寻找 "综合评分: X/10" 或 "**X/10**" 模式
    match = re.search(r'(\d+(?:\.\d+)?)/10', content)
    if match:
        return float(match.group(1))
    return 5.0  # 默认中等评分


def _to_run_response(r: EvalRun) -> EvalRunResponse:
    return EvalRunResponse(
        id=r.id,
        project_id=r.project_id,
        name=r.name or "",
        status=r.status or "pending",
        summary=r.summary or "",
        overall_score=r.overall_score,
        role_scores=r.role_scores or {},
        trial_count=r.trial_count or 0,
        content_block_id=r.content_block_id,
        created_at=r.created_at.isoformat() if r.created_at else "",
    )


def _to_trial_response(t: EvalTrial) -> EvalTrialResponse:
    return EvalTrialResponse(
        id=t.id,
        eval_run_id=t.eval_run_id,
        role=t.role or "",
        role_config=t.role_config or {},
        interaction_mode=t.interaction_mode or "review",
        input_block_ids=t.input_block_ids or [],
        persona=t.persona or {},
        nodes=t.nodes or [],
        result=t.result or {},
        grader_outputs=t.grader_outputs or [],
        overall_score=t.overall_score,
        status=t.status or "pending",
        error=t.error or "",
        tokens_in=t.tokens_in or 0,
        tokens_out=t.tokens_out or 0,
        cost=t.cost or 0.0,
        created_at=t.created_at.isoformat() if t.created_at else "",
    )
