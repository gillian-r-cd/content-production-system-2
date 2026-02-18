# backend/api/settings.py
# 功能: 后台设置API
# 主要路由: 系统提示词、创作者特质、字段模板、渠道、模拟器、Agent设置管理
# 数据结构: 完整的CRUD操作

"""
后台设置 API
管理系统提示词、创作者特质、字段模板、渠道、模拟器、Agent设置等
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import (
    CreatorProfile,
    FieldTemplate,
    Channel,
    Simulator,
    Grader,
    GenerationLog,
    SystemPrompt,
    AgentSettings,
    generate_uuid,
)
from core.models.grader import PRESET_GRADERS


router = APIRouter()

EVAL_PROMPT_PRESETS = [
    {
        "name": "探索规划提示词",
        "phase": "eval_experience_plan",
        "description": "消费体验步骤1：规划阅读顺序与目标",
        "content": "你是一位真实消费者。\n\n【你的身份】\n{persona}\n\n{probe_section}\n\n请基于以下章节列表制定探索计划：\n{block_list}\n\n请输出 JSON：{\"plan\":[{\"block_id\":\"id\",\"reason\":\"...\"}],\"overall_goal\":\"...\"}",
    },
    {
        "name": "逐块探索提示词",
        "phase": "eval_experience_per_block",
        "description": "消费体验步骤2：逐块评价",
        "content": "你是一位真实消费者。\n\n【你的身份】\n{persona}\n\n{probe_section}\n\n【之前的阅读记忆】\n{exploration_memory}\n\n【当前章节】\n{block_title}\n{block_content}\n\n输出 JSON：{\"concern_match\":\"...\",\"discovery\":\"...\",\"doubt\":\"...\",\"missing\":\"...\",\"feeling\":\"...\",\"score\":1}",
    },
    {
        "name": "探索总结提示词",
        "phase": "eval_experience_summary",
        "description": "消费体验步骤3：综合总结",
        "content": "你是一位真实消费者。\n\n【你的身份】\n{persona}\n\n{probe_section}\n\n以下是逐块结果：\n{all_block_results}\n\n输出 JSON：{\"overall_impression\":\"...\",\"concerns_addressed\":[],\"concerns_unaddressed\":[],\"would_recommend\":false,\"summary\":\"...\"}",
    },
    {
        "name": "场景角色A提示词",
        "phase": "eval_scenario_role_a",
        "description": "场景模拟角色A模板",
        "content": "{persona}\n\n你掌握以下内容：\n{content}\n\n{probe_section}\n\n规则：每次回复不超过50字。基于内容回答，不编造信息。",
    },
    {
        "name": "场景角色B提示词",
        "phase": "eval_scenario_role_b",
        "description": "场景模拟角色B模板",
        "content": "{persona}\n\n{probe_section}\n\n规则：每次回复不超过50字。带着顾虑主动追问，不轻易被说服。",
    },
    {
        "name": "跨Trial分析提示词",
        "phase": "eval_cross_trial_analysis",
        "description": "Task级跨Trial模式分析模板",
        "content": "请分析以下Task下所有Trial结果：\n{all_trial_results}\n\n输出 JSON：{\"patterns\":[],\"suggestions\":[],\"strengths\":[],\"summary\":\"...\"}",
    },
]

EVAL_SIMULATOR_PRESETS = [
    {
        "name": "预置-直接判定模拟器",
        "description": "assessment 形态占位模拟器（主要由 Grader 执行）",
        "simulator_type": "expert",
        "interaction_type": "reading",
        "interaction_mode": "review",
        "prompt_template": "你是评估辅助角色。请按规则返回结构化结果。",
        "secondary_prompt": "",
        "grader_template": "",
        "evaluation_dimensions": ["结构合理性", "语言质量", "信息准确性", "可读性"],
        "feedback_mode": "structured",
        "max_turns": 1,
    },
    {
        "name": "预置-视角审查模拟器",
        "description": "review 形态默认模拟器",
        "simulator_type": "editor",
        "interaction_type": "reading",
        "interaction_mode": "review",
        "prompt_template": "你是一位专业审查者，请基于内容给出结构化审查反馈。",
        "secondary_prompt": "",
        "grader_template": "",
        "evaluation_dimensions": ["策略清晰度", "问题严重度", "可执行性"],
        "feedback_mode": "structured",
        "max_turns": 1,
    },
    {
        "name": "预置-消费体验模拟器",
        "description": "experience 形态默认模拟器",
        "simulator_type": "consumer",
        "interaction_type": "exploration",
        "interaction_mode": "review",
        "prompt_template": "你是消费者，按探索流程输出分块反馈。",
        "secondary_prompt": "",
        "grader_template": "",
        "evaluation_dimensions": ["需求匹配度", "信息完整性", "价值感知", "内容结构"],
        "feedback_mode": "structured",
        "max_turns": 1,
    },
    {
        "name": "预置-场景对话模拟器",
        "description": "scenario 形态默认模拟器（双角色对话）",
        "simulator_type": "seller",
        "interaction_type": "dialogue",
        "interaction_mode": "scenario",
        "prompt_template": "你是场景角色A。每次回复不超过50字。",
        "secondary_prompt": "你是场景角色B。每次回复不超过50字。",
        "grader_template": "",
        "evaluation_dimensions": ["价值传达", "需求匹配", "异议处理", "信任建立"],
        "feedback_mode": "structured",
        "max_turns": 5,
    },
]


# ============== System Prompts ==============

class SystemPromptUpdate(BaseModel):
    name: Optional[str] = None
    phase: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None


class SystemPromptResponse(BaseModel):
    id: str
    name: str
    phase: str
    content: str
    description: str
    created_at: str

    model_config = {"from_attributes": True}


class EvalPromptUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None


class EvalPresetSyncResponse(BaseModel):
    imported_graders: int
    updated_graders: int
    imported_simulators: int
    updated_simulators: int


@router.get("/system-prompts", response_model=list[SystemPromptResponse])
def list_system_prompts(db: Session = Depends(get_db)):
    """获取系统提示词列表"""
    prompts = db.query(SystemPrompt).all()
    return [_to_prompt_response(p) for p in prompts]


@router.put("/system-prompts/{prompt_id}", response_model=SystemPromptResponse)
def update_system_prompt(
    prompt_id: str,
    update: SystemPromptUpdate,
    db: Session = Depends(get_db),
):
    """更新系统提示词"""
    prompt = db.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(prompt, key, value)
    
    db.commit()
    db.refresh(prompt)
    return _to_prompt_response(prompt)


@router.get("/eval-prompts", response_model=list[SystemPromptResponse])
def list_eval_prompts(db: Session = Depends(get_db)):
    """获取评估提示词模板，若不存在则自动初始化预置模板。"""
    _ensure_eval_prompt_presets(db)
    rows = (
        db.query(SystemPrompt)
        .filter(SystemPrompt.phase.like("eval_%"))
        .order_by(SystemPrompt.phase.asc())
        .all()
    )
    return [_to_prompt_response(p) for p in rows]


@router.put("/eval-prompts/{prompt_id}", response_model=SystemPromptResponse)
def update_eval_prompt(prompt_id: str, update: EvalPromptUpdate, db: Session = Depends(get_db)):
    """更新评估提示词模板。"""
    prompt = db.query(SystemPrompt).filter(SystemPrompt.id == prompt_id, SystemPrompt.phase.like("eval_%")).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Not found")

    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(prompt, key, value)
    db.commit()
    db.refresh(prompt)
    return _to_prompt_response(prompt)


@router.post("/eval-presets/sync", response_model=EvalPresetSyncResponse)
def sync_eval_presets(db: Session = Depends(get_db)):
    """
    同步 Eval 预置模板（Grader + Simulator），幂等可重复执行。
    """
    imported_graders, updated_graders = _sync_preset_graders(db)
    imported_simulators, updated_simulators = _sync_preset_simulators(db)
    db.commit()
    return EvalPresetSyncResponse(
        imported_graders=imported_graders,
        updated_graders=updated_graders,
        imported_simulators=imported_simulators,
        updated_simulators=updated_simulators,
    )


# ============== Agent Settings ==============

class AgentSettingsUpdate(BaseModel):
    tools: Optional[list] = None
    skills: Optional[list] = None
    tool_prompts: Optional[dict] = None


class AgentSettingsResponse(BaseModel):
    id: str
    name: str
    tools: list
    skills: list
    autonomy_defaults: dict = {}  # [已废弃] 保留兼容旧数据
    tool_prompts: dict

    model_config = {"from_attributes": True}


@router.get("/agent", response_model=AgentSettingsResponse)
def get_agent_settings(db: Session = Depends(get_db)):
    """获取Agent设置"""
    settings = db.query(AgentSettings).filter(AgentSettings.name == "default").first()
    if not settings:
        # 创建默认设置
        settings = AgentSettings(
            id=generate_uuid(),
            name="default",
            tools=[
                "rewrite_field", "propose_edit", "generate_field_content", "query_field",
                "read_field", "update_field", "manage_architecture",
                "advance_to_phase", "run_research", "manage_persona",
                "run_evaluation", "generate_outline", "manage_skill",
            ],
            skills=[],
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return _to_agent_settings_response(settings)


@router.put("/agent", response_model=AgentSettingsResponse)
def update_agent_settings(
    update: AgentSettingsUpdate,
    db: Session = Depends(get_db),
):
    """更新Agent设置"""
    settings = db.query(AgentSettings).filter(AgentSettings.name == "default").first()
    if not settings:
        settings = AgentSettings(id=generate_uuid(), name="default")
        db.add(settings)
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(settings, key, value)
    
    db.commit()
    db.refresh(settings)
    return _to_agent_settings_response(settings)


# ============== Creator Profile ==============

class CreatorProfileCreate(BaseModel):
    name: str
    description: str = ""
    traits: dict = {}


class CreatorProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    traits: Optional[dict] = None


class CreatorProfileResponse(BaseModel):
    id: str
    name: str
    description: str
    traits: dict
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/creator-profiles", response_model=list[CreatorProfileResponse])
def list_creator_profiles(db: Session = Depends(get_db)):
    """获取创作者特质列表"""
    profiles = db.query(CreatorProfile).all()
    return [_to_profile_response(p) for p in profiles]


@router.post("/creator-profiles", response_model=CreatorProfileResponse)
def create_creator_profile(
    profile: CreatorProfileCreate,
    db: Session = Depends(get_db),
):
    """创建创作者特质"""
    db_profile = CreatorProfile(
        id=generate_uuid(),
        name=profile.name,
        description=profile.description,
        traits=profile.traits,
    )
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    return _to_profile_response(db_profile)


@router.put("/creator-profiles/{profile_id}", response_model=CreatorProfileResponse)
def update_creator_profile(
    profile_id: str,
    update: CreatorProfileUpdate,
    db: Session = Depends(get_db),
):
    """更新创作者特质"""
    from sqlalchemy.orm.attributes import flag_modified
    
    profile = db.query(CreatorProfile).filter(CreatorProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(profile, key, value)
        # 对于 JSON 字段（如 traits），需要标记为已修改
        if key == "traits":
            flag_modified(profile, "traits")
    
    db.commit()
    db.refresh(profile)
    return _to_profile_response(profile)


@router.delete("/creator-profiles/{profile_id}")
def delete_creator_profile(profile_id: str, db: Session = Depends(get_db)):
    """删除创作者特质"""
    profile = db.query(CreatorProfile).filter(CreatorProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(profile)
    db.commit()
    return {"message": "Deleted"}


# ============== Field Template ==============

class FieldTemplateCreate(BaseModel):
    name: str
    description: str = ""
    category: str = "通用"
    fields: list = []


class FieldTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    fields: Optional[list] = None


class FieldTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    category: str
    fields: list
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/field-templates", response_model=list[FieldTemplateResponse])
def list_field_templates(db: Session = Depends(get_db)):
    """获取字段模板列表"""
    templates = db.query(FieldTemplate).all()
    return [_to_template_response(t) for t in templates]


@router.post("/field-templates", response_model=FieldTemplateResponse)
def create_field_template(
    template: FieldTemplateCreate,
    db: Session = Depends(get_db),
):
    """创建字段模板"""
    db_template = FieldTemplate(
        id=generate_uuid(),
        name=template.name,
        description=template.description,
        category=template.category,
        fields=template.fields,
    )
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return _to_template_response(db_template)


@router.put("/field-templates/{template_id}", response_model=FieldTemplateResponse)
def update_field_template(
    template_id: str,
    update: FieldTemplateUpdate,
    db: Session = Depends(get_db),
):
    """更新字段模板"""
    from sqlalchemy.orm.attributes import flag_modified
    
    template = db.query(FieldTemplate).filter(FieldTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)
        # 对于 JSON 字段（如 fields），需要标记为已修改
        if key == "fields":
            flag_modified(template, "fields")
    
    db.commit()
    db.refresh(template)
    return _to_template_response(template)


@router.delete("/field-templates/{template_id}")
def delete_field_template(template_id: str, db: Session = Depends(get_db)):
    """删除字段模板"""
    template = db.query(FieldTemplate).filter(FieldTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(template)
    db.commit()
    return {"message": "Deleted"}


# ============== Channel ==============

class ChannelCreate(BaseModel):
    name: str
    description: str = ""
    platform: str = "other"
    prompt_template: str = ""
    constraints: dict = {}


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    platform: Optional[str] = None
    prompt_template: Optional[str] = None
    constraints: Optional[dict] = None


class ChannelResponse(BaseModel):
    id: str
    name: str
    description: str
    platform: str
    prompt_template: str
    constraints: dict
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/channels", response_model=list[ChannelResponse])
def list_channels(db: Session = Depends(get_db)):
    """获取渠道列表"""
    channels = db.query(Channel).all()
    return [_to_channel_response(c) for c in channels]


@router.post("/channels", response_model=ChannelResponse)
def create_channel(channel: ChannelCreate, db: Session = Depends(get_db)):
    """创建渠道"""
    db_channel = Channel(
        id=generate_uuid(),
        name=channel.name,
        description=channel.description,
        platform=channel.platform,
        prompt_template=channel.prompt_template,
        constraints=channel.constraints,
    )
    db.add(db_channel)
    db.commit()
    db.refresh(db_channel)
    return _to_channel_response(db_channel)


@router.put("/channels/{channel_id}", response_model=ChannelResponse)
def update_channel(
    channel_id: str,
    update: ChannelUpdate,
    db: Session = Depends(get_db),
):
    """更新渠道"""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(channel, key, value)
    
    db.commit()
    db.refresh(channel)
    return _to_channel_response(channel)


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str, db: Session = Depends(get_db)):
    """删除渠道"""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(channel)
    db.commit()
    return {"message": "Deleted"}


# ============== Simulator ==============

class SimulatorCreate(BaseModel):
    name: str
    description: str = ""
    simulator_type: str = "custom"
    interaction_type: str = "reading"
    interaction_mode: str = "review"
    prompt_template: str = ""
    secondary_prompt: str = ""
    grader_template: str = ""
    evaluation_dimensions: list = []
    feedback_mode: str = "structured"
    max_turns: int = 10


class SimulatorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    simulator_type: Optional[str] = None
    interaction_type: Optional[str] = None
    interaction_mode: Optional[str] = None
    prompt_template: Optional[str] = None
    secondary_prompt: Optional[str] = None
    grader_template: Optional[str] = None
    evaluation_dimensions: Optional[list] = None
    feedback_mode: Optional[str] = None
    max_turns: Optional[int] = None


class SimulatorResponse(BaseModel):
    id: str
    name: str
    description: str
    simulator_type: str
    interaction_type: str
    interaction_mode: str
    prompt_template: str
    secondary_prompt: str
    grader_template: str
    evaluation_dimensions: list
    feedback_mode: str
    max_turns: int
    is_preset: bool
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/simulators", response_model=list[SimulatorResponse])
def list_simulators(db: Session = Depends(get_db)):
    """获取模拟器列表"""
    simulators = db.query(Simulator).all()
    return [_to_simulator_response(s) for s in simulators]


@router.post("/simulators", response_model=SimulatorResponse)
def create_simulator(simulator: SimulatorCreate, db: Session = Depends(get_db)):
    """创建模拟器"""
    db_simulator = Simulator(
        id=generate_uuid(),
        name=simulator.name,
        description=simulator.description,
        simulator_type=simulator.simulator_type,
        interaction_type=simulator.interaction_type,
        interaction_mode=simulator.interaction_mode,
        prompt_template=simulator.prompt_template,
        secondary_prompt=simulator.secondary_prompt,
        grader_template=simulator.grader_template,
        evaluation_dimensions=simulator.evaluation_dimensions,
        feedback_mode=simulator.feedback_mode,
        max_turns=simulator.max_turns,
    )
    db.add(db_simulator)
    db.commit()
    db.refresh(db_simulator)
    return _to_simulator_response(db_simulator)


@router.put("/simulators/{simulator_id}", response_model=SimulatorResponse)
def update_simulator(
    simulator_id: str,
    update: SimulatorUpdate,
    db: Session = Depends(get_db),
):
    """更新模拟器"""
    from sqlalchemy.orm.attributes import flag_modified
    
    simulator = db.query(Simulator).filter(Simulator.id == simulator_id).first()
    if not simulator:
        raise HTTPException(status_code=404, detail="Not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(simulator, key, value)
        # 对于 JSON 字段（如 evaluation_dimensions），需要标记为已修改
        if key == "evaluation_dimensions":
            flag_modified(simulator, "evaluation_dimensions")
    
    db.commit()
    db.refresh(simulator)
    return _to_simulator_response(simulator)


@router.delete("/simulators/{simulator_id}")
def delete_simulator(simulator_id: str, db: Session = Depends(get_db)):
    """删除模拟器"""
    simulator = db.query(Simulator).filter(Simulator.id == simulator_id).first()
    if not simulator:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(simulator)
    db.commit()
    return {"message": "Deleted"}


# ============== Generation Logs ==============

class LogResponse(BaseModel):
    id: str
    project_id: str
    field_id: Optional[str]
    phase: str
    operation: str
    model: str
    prompt_input: str  # 输入内容
    prompt_output: str  # 输出内容
    tokens_in: int
    tokens_out: int
    duration_ms: int
    cost: float
    status: str
    error_message: str
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/logs", response_model=list[LogResponse])
def list_logs(
    project_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """获取生成日志"""
    query = db.query(GenerationLog)
    if project_id:
        query = query.filter(GenerationLog.project_id == project_id)
    
    logs = query.order_by(GenerationLog.created_at.desc()).offset(skip).limit(limit).all()
    return [_to_log_response(log) for log in logs]


@router.get("/logs/export")
def export_logs(
    project_id: Optional[str] = None,
    include_prompts: bool = False,
    format: str = "json",
    db: Session = Depends(get_db),
):
    """
    导出日志
    
    Args:
        project_id: 筛选项目
        include_prompts: 是否包含完整的输入输出（prompt_input/prompt_output）
        format: 导出格式 "json" 或 "csv"
    """
    query = db.query(GenerationLog)
    if project_id:
        query = query.filter(GenerationLog.project_id == project_id)
    
    logs = query.order_by(GenerationLog.created_at.desc()).all()
    
    log_data = []
    for log in logs:
        item = {
            "id": log.id,
            "project_id": log.project_id,
            "field_id": log.field_id,
            "phase": log.phase,
            "operation": log.operation,
            "model": log.model,
            "tokens_in": log.tokens_in,
            "tokens_out": log.tokens_out,
            "duration_ms": log.duration_ms,
            "cost": log.cost,
            "status": log.status,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat() if log.created_at else "",
        }
        
        if include_prompts:
            item["prompt_input"] = log.prompt_input
            item["prompt_output"] = log.prompt_output
        
        log_data.append(item)
    
    if format == "csv":
        # 返回CSV格式
        import csv
        import io
        from fastapi.responses import StreamingResponse
        
        output = io.StringIO()
        if log_data:
            writer = csv.DictWriter(output, fieldnames=log_data[0].keys())
            writer.writeheader()
            writer.writerows(log_data)
        
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=generation_logs.csv"}
        )
    
    return {
        "logs": log_data,
        "total_cost": sum(log.cost or 0 for log in logs),
        "total_tokens": sum((log.tokens_in or 0) + (log.tokens_out or 0) for log in logs),
        "count": len(logs),
    }


# ============== Helpers ==============

def _ensure_eval_prompt_presets(db: Session) -> None:
    changed = False
    for preset in EVAL_PROMPT_PRESETS:
        existing = db.query(SystemPrompt).filter(SystemPrompt.phase == preset["phase"]).first()
        if existing:
            continue
        db.add(SystemPrompt(
            id=generate_uuid(),
            name=preset["name"],
            phase=preset["phase"],
            content=preset["content"],
            description=preset["description"],
        ))
        changed = True
    if changed:
        db.commit()


def _sync_preset_graders(db: Session) -> tuple[int, int]:
    imported = 0
    updated = 0
    for item in PRESET_GRADERS:
        name = item.get("name", "")
        if not name:
            continue
        existing = db.query(Grader).filter(Grader.name == name, Grader.is_preset == True).first()  # noqa: E712
        if existing:
            existing.grader_type = item.get("grader_type", existing.grader_type)
            existing.prompt_template = item.get("prompt_template", existing.prompt_template)
            existing.dimensions = item.get("dimensions", existing.dimensions)
            existing.scoring_criteria = item.get("scoring_criteria", existing.scoring_criteria)
            existing.is_preset = True
            existing.project_id = None
            updated += 1
            continue
        db.add(Grader(
            id=generate_uuid(),
            name=name,
            grader_type=item.get("grader_type", "content_only"),
            prompt_template=item.get("prompt_template", ""),
            dimensions=item.get("dimensions", []),
            scoring_criteria=item.get("scoring_criteria", {}),
            is_preset=True,
            project_id=None,
        ))
        imported += 1
    return imported, updated


def _sync_preset_simulators(db: Session) -> tuple[int, int]:
    imported = 0
    updated = 0
    for item in EVAL_SIMULATOR_PRESETS:
        name = item.get("name", "")
        if not name:
            continue
        existing = db.query(Simulator).filter(Simulator.name == name, Simulator.is_preset == True).first()  # noqa: E712
        if existing:
            existing.description = item.get("description", existing.description)
            existing.simulator_type = item.get("simulator_type", existing.simulator_type)
            existing.interaction_type = item.get("interaction_type", existing.interaction_type)
            existing.interaction_mode = item.get("interaction_mode", existing.interaction_mode)
            existing.prompt_template = item.get("prompt_template", existing.prompt_template)
            existing.secondary_prompt = item.get("secondary_prompt", existing.secondary_prompt)
            existing.grader_template = item.get("grader_template", existing.grader_template)
            existing.evaluation_dimensions = item.get("evaluation_dimensions", existing.evaluation_dimensions)
            existing.feedback_mode = item.get("feedback_mode", existing.feedback_mode)
            existing.max_turns = item.get("max_turns", existing.max_turns)
            existing.is_preset = True
            updated += 1
            continue
        db.add(Simulator(
            id=generate_uuid(),
            name=name,
            description=item.get("description", ""),
            simulator_type=item.get("simulator_type", "custom"),
            interaction_type=item.get("interaction_type", "reading"),
            interaction_mode=item.get("interaction_mode", "review"),
            prompt_template=item.get("prompt_template", ""),
            secondary_prompt=item.get("secondary_prompt", ""),
            grader_template=item.get("grader_template", ""),
            evaluation_dimensions=item.get("evaluation_dimensions", []),
            feedback_mode=item.get("feedback_mode", "structured"),
            max_turns=item.get("max_turns", 10),
            is_preset=True,
        ))
        imported += 1
    return imported, updated


def _to_prompt_response(p: SystemPrompt) -> SystemPromptResponse:
    return SystemPromptResponse(
        id=p.id,
        name=p.name,
        phase=p.phase or "",
        content=p.content or "",
        description=p.description or "",
        created_at=p.created_at.isoformat() if p.created_at else "",
    )


def _to_agent_settings_response(s: AgentSettings) -> AgentSettingsResponse:
    return AgentSettingsResponse(
        id=s.id,
        name=s.name,
        tools=s.tools or [],
        skills=s.skills or [],
        autonomy_defaults=s.autonomy_defaults or {},
        tool_prompts=s.tool_prompts or {},
    )


def _to_profile_response(p: CreatorProfile) -> CreatorProfileResponse:
    return CreatorProfileResponse(
        id=p.id,
        name=p.name,
        description=p.description or "",
        traits=p.traits or {},
        created_at=p.created_at.isoformat() if p.created_at else "",
    )


def _to_template_response(t: FieldTemplate) -> FieldTemplateResponse:
    return FieldTemplateResponse(
        id=t.id,
        name=t.name,
        description=t.description or "",
        category=t.category or "通用",
        fields=t.fields or [],
        created_at=t.created_at.isoformat() if t.created_at else "",
    )


def _to_channel_response(c: Channel) -> ChannelResponse:
    return ChannelResponse(
        id=c.id,
        name=c.name,
        description=c.description or "",
        platform=c.platform or "other",
        prompt_template=c.prompt_template or "",
        constraints=c.constraints or {},
        created_at=c.created_at.isoformat() if c.created_at else "",
    )


def _to_simulator_response(s: Simulator) -> SimulatorResponse:
    # 从 interaction_type（旧版，实际源数据）正确推导 interaction_mode（新版）
    # 避免 interaction_mode 始终为 DB 默认值 "review" 的问题
    itype = s.interaction_type or "reading"
    raw_mode = getattr(s, 'interaction_mode', None) or ""
    # 如果 interaction_mode 未被显式设置（仍是默认 review），从 interaction_type 推导
    _TYPE_TO_MODE = {"reading": "review", "dialogue": "dialogue", "decision": "scenario", "exploration": "exploration"}
    if not raw_mode or raw_mode == "review":
        derived_mode = _TYPE_TO_MODE.get(itype, "review")
    else:
        derived_mode = raw_mode
    
    return SimulatorResponse(
        id=s.id,
        name=s.name,
        description=s.description or "",
        simulator_type=getattr(s, 'simulator_type', 'custom') or "custom",
        interaction_type=itype,
        interaction_mode=derived_mode,
        prompt_template=s.prompt_template or "",
        secondary_prompt=getattr(s, 'secondary_prompt', '') or "",
        grader_template=getattr(s, 'grader_template', '') or "",
        evaluation_dimensions=s.evaluation_dimensions or [],
        feedback_mode=getattr(s, 'feedback_mode', 'structured') or "structured",
        max_turns=s.max_turns or 10,
        is_preset=getattr(s, 'is_preset', False),
        created_at=s.created_at.isoformat() if s.created_at else "",
    )


def _to_log_response(log: GenerationLog) -> LogResponse:
    return LogResponse(
        id=log.id,
        project_id=log.project_id,
        field_id=log.field_id,
        phase=log.phase or "",
        operation=log.operation or "",
        model=log.model or "",
        prompt_input=log.prompt_input or "",
        prompt_output=log.prompt_output or "",
        tokens_in=log.tokens_in or 0,
        tokens_out=log.tokens_out or 0,
        duration_ms=log.duration_ms or 0,
        cost=log.cost or 0.0,
        status=log.status or "",
        error_message=log.error_message or "",
        created_at=log.created_at.isoformat() if log.created_at else "",
    )


# ============== 导入导出 API ==============

class ImportRequest(BaseModel):
    """导入请求"""
    data: list


# --- 字段模板导入导出 ---

@router.get("/field-templates/export")
def export_field_templates(
    template_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    导出字段模板
    
    Args:
        template_id: 单个模板ID（不传则导出全部）
    """
    if template_id:
        template = db.query(FieldTemplate).filter(FieldTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        templates = [template]
    else:
        templates = db.query(FieldTemplate).all()
    
    export_data = []
    for t in templates:
        export_data.append({
            "name": t.name,
            "description": t.description or "",
            "category": t.category or "通用",
            "fields": t.fields or [],
        })
    
    return {"type": "field_templates", "data": export_data, "count": len(export_data)}


@router.post("/field-templates/import")
def import_field_templates(
    request: ImportRequest,
    db: Session = Depends(get_db),
):
    """导入字段模板"""
    imported = 0
    for item in request.data:
        db_template = FieldTemplate(
            id=generate_uuid(),
            name=item.get("name", "导入模板"),
            description=item.get("description", ""),
            category=item.get("category", "通用"),
            fields=item.get("fields", []),
        )
        db.add(db_template)
        imported += 1
    
    db.commit()
    return {"message": f"成功导入 {imported} 个字段模板", "imported": imported}


# --- 创作者特质导入导出 ---

@router.get("/creator-profiles/export")
def export_creator_profiles(
    profile_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    导出创作者特质
    
    Args:
        profile_id: 单个特质ID（不传则导出全部）
    """
    if profile_id:
        profile = db.query(CreatorProfile).filter(CreatorProfile.id == profile_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        profiles = [profile]
    else:
        profiles = db.query(CreatorProfile).all()
    
    export_data = []
    for p in profiles:
        export_data.append({
            "name": p.name,
            "description": p.description or "",
            "traits": p.traits or {},
        })
    
    return {"type": "creator_profiles", "data": export_data, "count": len(export_data)}


@router.post("/creator-profiles/import")
def import_creator_profiles(
    request: ImportRequest,
    db: Session = Depends(get_db),
):
    """导入创作者特质"""
    imported = 0
    for item in request.data:
        db_profile = CreatorProfile(
            id=generate_uuid(),
            name=item.get("name", "导入特质"),
            description=item.get("description", ""),
            traits=item.get("traits", {}),
        )
        db.add(db_profile)
        imported += 1
    
    db.commit()
    return {"message": f"成功导入 {imported} 个创作者特质", "imported": imported}


# --- 模拟器导入导出 ---

@router.get("/simulators/export")
def export_simulators(
    simulator_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    导出模拟器
    
    Args:
        simulator_id: 单个模拟器ID（不传则导出全部）
    """
    if simulator_id:
        simulator = db.query(Simulator).filter(Simulator.id == simulator_id).first()
        if not simulator:
            raise HTTPException(status_code=404, detail="Simulator not found")
        simulators = [simulator]
    else:
        simulators = db.query(Simulator).all()
    
    export_data = []
    for s in simulators:
        export_data.append({
            "name": s.name,
            "description": s.description or "",
            "simulator_type": getattr(s, 'simulator_type', 'custom') or "custom",
            "interaction_type": s.interaction_type or "reading",
            "interaction_mode": getattr(s, 'interaction_mode', 'review') or "review",
            "prompt_template": s.prompt_template or "",
            "secondary_prompt": getattr(s, 'secondary_prompt', '') or "",
            "grader_template": getattr(s, 'grader_template', '') or "",
            "evaluation_dimensions": s.evaluation_dimensions or [],
            "feedback_mode": getattr(s, 'feedback_mode', 'structured') or "structured",
            "max_turns": s.max_turns or 10,
        })
    
    return {"type": "simulators", "data": export_data, "count": len(export_data)}


@router.post("/simulators/import")
def import_simulators(
    request: ImportRequest,
    db: Session = Depends(get_db),
):
    """导入模拟器（同名 → 更新，新名 → 创建）"""
    imported = 0
    updated = 0
    for item in request.data:
        name = item.get("name", "")
        if not name:
            continue
        
        # 检查同名
        existing = db.query(Simulator).filter(Simulator.name == name).first()
        if existing:
            existing.description = item.get("description", existing.description)
            existing.simulator_type = item.get("simulator_type", getattr(existing, 'simulator_type', 'custom'))
            existing.interaction_type = item.get("interaction_type", existing.interaction_type)
            existing.interaction_mode = item.get("interaction_mode", getattr(existing, 'interaction_mode', 'review'))
            existing.prompt_template = item.get("prompt_template", existing.prompt_template)
            existing.secondary_prompt = item.get("secondary_prompt", getattr(existing, 'secondary_prompt', ''))
            existing.grader_template = item.get("grader_template", getattr(existing, 'grader_template', ''))
            existing.evaluation_dimensions = item.get("evaluation_dimensions", existing.evaluation_dimensions)
            existing.feedback_mode = item.get("feedback_mode", getattr(existing, 'feedback_mode', 'structured'))
            existing.max_turns = item.get("max_turns", existing.max_turns)
            updated += 1
        else:
            db_simulator = Simulator(
                id=generate_uuid(),
                name=name,
                description=item.get("description", ""),
                simulator_type=item.get("simulator_type", "custom"),
                interaction_type=item.get("interaction_type", "reading"),
                interaction_mode=item.get("interaction_mode", "review"),
                prompt_template=item.get("prompt_template", ""),
                secondary_prompt=item.get("secondary_prompt", ""),
                grader_template=item.get("grader_template", ""),
                evaluation_dimensions=item.get("evaluation_dimensions", []),
                feedback_mode=item.get("feedback_mode", "structured"),
                max_turns=item.get("max_turns", 10),
            )
            db.add(db_simulator)
            imported += 1
    
    db.commit()
    return {
        "message": f"成功导入 {imported} 个、更新 {updated} 个模拟器",
        "imported": imported,
        "updated": updated,
    }


# --- 系统提示词导入导出 ---

@router.get("/system-prompts/export")
def export_system_prompts(
    prompt_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    导出系统提示词
    
    Args:
        prompt_id: 单个提示词ID（不传则导出全部）
    """
    if prompt_id:
        prompt = db.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        prompts = [prompt]
    else:
        prompts = db.query(SystemPrompt).all()
    
    export_data = []
    for p in prompts:
        export_data.append({
            "name": p.name,
            "phase": p.phase or "",
            "content": p.content or "",
            "description": p.description or "",
        })
    
    return {"type": "system_prompts", "data": export_data, "count": len(export_data)}


@router.post("/system-prompts/import")
def import_system_prompts(
    request: ImportRequest,
    db: Session = Depends(get_db),
):
    """导入系统提示词（会覆盖同 phase 的已有提示词）"""
    imported = 0
    updated = 0
    
    for item in request.data:
        phase = item.get("phase", "")
        
        # 检查是否已存在同 phase 的提示词
        existing = db.query(SystemPrompt).filter(SystemPrompt.phase == phase).first()
        
        if existing:
            # 更新现有的
            existing.name = item.get("name", existing.name)
            existing.content = item.get("content", existing.content)
            existing.description = item.get("description", existing.description)
            updated += 1
        else:
            # 创建新的
            db_prompt = SystemPrompt(
                id=generate_uuid(),
                name=item.get("name", "导入提示词"),
                phase=phase,
                content=item.get("content", ""),
                description=item.get("description", ""),
            )
            db.add(db_prompt)
            imported += 1
    
    db.commit()
    return {
        "message": f"成功导入 {imported} 个、更新 {updated} 个系统提示词",
        "imported": imported,
        "updated": updated,
    }
