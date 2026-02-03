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
    GenerationLog,
    SystemPrompt,
    AgentSettings,
    generate_uuid,
)


router = APIRouter()


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


# ============== Agent Settings ==============

class AgentSettingsUpdate(BaseModel):
    tools: Optional[list] = None
    skills: Optional[list] = None
    autonomy_defaults: Optional[dict] = None


class AgentSettingsResponse(BaseModel):
    id: str
    name: str
    tools: list
    skills: list
    autonomy_defaults: dict

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
            tools=["deep_research", "generate_field", "simulate_consumer", "evaluate_content"],
            skills=[],
            autonomy_defaults={
                "intent": True,
                "research": True,
                "design_inner": True,
                "produce_inner": True,
                "design_outer": True,
                "produce_outer": True,
                "simulate": True,
                "evaluate": True,
            },
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
    profile = db.query(CreatorProfile).filter(CreatorProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(profile, key, value)
    
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
    template = db.query(FieldTemplate).filter(FieldTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)
    
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
    interaction_type: str = "reading"
    prompt_template: str = ""
    evaluation_dimensions: list = []
    max_turns: int = 10


class SimulatorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    interaction_type: Optional[str] = None
    prompt_template: Optional[str] = None
    evaluation_dimensions: Optional[list] = None
    max_turns: Optional[int] = None


class SimulatorResponse(BaseModel):
    id: str
    name: str
    description: str
    interaction_type: str
    prompt_template: str
    evaluation_dimensions: list
    max_turns: int
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
        interaction_type=simulator.interaction_type,
        prompt_template=simulator.prompt_template,
        evaluation_dimensions=simulator.evaluation_dimensions,
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
    simulator = db.query(Simulator).filter(Simulator.id == simulator_id).first()
    if not simulator:
        raise HTTPException(status_code=404, detail="Not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(simulator, key, value)
    
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
    return SimulatorResponse(
        id=s.id,
        name=s.name,
        description=s.description or "",
        interaction_type=s.interaction_type or "reading",
        prompt_template=s.prompt_template or "",
        evaluation_dimensions=s.evaluation_dimensions or [],
        max_turns=s.max_turns or 10,
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
