# backend/api/projects.py
# 功能: 项目管理API
# 主要路由: CRUD操作、版本管理
# 数据结构: ProjectCreate, ProjectUpdate, ProjectResponse

"""
项目管理 API
"""

from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Project, CreatorProfile, PROJECT_PHASES, generate_uuid


router = APIRouter()


# ============== Schemas ==============

class ProjectCreate(BaseModel):
    """创建项目请求"""
    name: str
    creator_profile_id: Optional[str] = None
    use_deep_research: bool = True
    use_flexible_architecture: bool = False  # 是否使用灵活的 ContentBlock 架构
    phase_order: Optional[List[str]] = None  # 自定义阶段顺序，None 使用默认，[] 表示从零开始


class ProjectUpdate(BaseModel):
    """更新项目请求"""
    name: Optional[str] = None
    current_phase: Optional[str] = None
    phase_order: Optional[List[str]] = None
    agent_autonomy: Optional[Dict[str, bool]] = None
    golden_context: Optional[dict] = None
    use_deep_research: Optional[bool] = None
    use_flexible_architecture: Optional[bool] = None


class ProjectResponse(BaseModel):
    """项目响应"""
    id: str
    name: str
    version: int
    version_note: str
    creator_profile_id: Optional[str]
    current_phase: str
    phase_order: List[str]
    phase_status: Dict[str, str]
    agent_autonomy: Dict[str, bool]
    golden_context: dict
    use_deep_research: bool
    use_flexible_architecture: bool = False  # 是否使用灵活的 ContentBlock 架构
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class NewVersionRequest(BaseModel):
    """创建新版本请求"""
    version_note: str


# ============== Routes ==============

@router.get("/", response_model=List[ProjectResponse])
def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """获取项目列表"""
    projects = db.query(Project).offset(skip).limit(limit).all()
    return [_project_to_response(p) for p in projects]


@router.post("/", response_model=ProjectResponse)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
):
    """创建新项目"""
    # 获取创作者特质内容，用于 golden_context
    golden_context = {}
    if project.creator_profile_id:
        creator_profile = db.query(CreatorProfile).filter(
            CreatorProfile.id == project.creator_profile_id
        ).first()
        if creator_profile:
            golden_context["creator_profile"] = creator_profile.to_prompt_context()
    
    # ===== 确定阶段顺序 =====
    # 如果传入了 phase_order 参数：
    #   - None: 使用默认的 PROJECT_PHASES
    #   - []: 从零开始（空白项目，无任何阶段）
    #   - [...]: 使用指定的阶段列表
    if project.phase_order is not None:
        actual_phase_order = project.phase_order
    else:
        actual_phase_order = PROJECT_PHASES.copy()
    
    # 确定初始阶段：如果有阶段则使用第一个，否则为空字符串
    initial_phase = actual_phase_order[0] if actual_phase_order else ""
    
    # ===== 关键：从AgentSettings读取默认自主权 =====
    from core.models.agent_settings import AgentSettings
    agent_settings = db.query(AgentSettings).filter(AgentSettings.name == "default").first()
    
    # 根据实际阶段列表设置自主权
    if agent_settings and agent_settings.autonomy_defaults:
        default_autonomy = agent_settings.autonomy_defaults
        agent_autonomy = {p: default_autonomy.get(p, True) for p in actual_phase_order}
    else:
        agent_autonomy = {p: True for p in actual_phase_order}
    
    db_project = Project(
        id=generate_uuid(),
        name=project.name,
        creator_profile_id=project.creator_profile_id,
        use_deep_research=project.use_deep_research,
        use_flexible_architecture=project.use_flexible_architecture,
        version=1,
        current_phase=initial_phase,
        phase_order=actual_phase_order,
        phase_status={p: "pending" for p in actual_phase_order},
        agent_autonomy=agent_autonomy,  # 使用默认自主权
        golden_context=golden_context,
    )
    
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    
    return _project_to_response(db_project)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
):
    """获取项目详情"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_to_response(project)


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    update: ProjectUpdate,
    db: Session = Depends(get_db),
):
    """更新项目"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)
    
    db.commit()
    db.refresh(project)
    
    return _project_to_response(project)


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
):
    """删除项目（包括所有关联数据）"""
    from core.models import ProjectField, ContentBlock, BlockHistory
    from core.models.chat_history import ChatMessage
    from core.models.generation_log import GenerationLog
    from core.models.simulation_record import SimulationRecord
    from core.models.evaluation import EvaluationReport
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 删除关联的生成日志
    db.query(GenerationLog).filter(GenerationLog.project_id == project_id).delete()
    
    # 删除关联的块历史记录
    db.query(BlockHistory).filter(BlockHistory.project_id == project_id).delete()
    
    # 删除关联的模拟记录
    db.query(SimulationRecord).filter(SimulationRecord.project_id == project_id).delete()
    
    # 删除关联的评估记录
    db.query(EvaluationReport).filter(EvaluationReport.project_id == project_id).delete()
    
    # 删除关联的内容块（灵活架构）
    db.query(ContentBlock).filter(ContentBlock.project_id == project_id).delete()
    
    # 删除关联的对话记录
    db.query(ChatMessage).filter(ChatMessage.project_id == project_id).delete()
    
    # 删除关联的字段（传统架构）
    db.query(ProjectField).filter(ProjectField.project_id == project_id).delete()
    
    # 删除项目本身
    db.delete(project)
    db.commit()
    
    return {"message": "Project deleted"}


@router.post("/{project_id}/duplicate", response_model=ProjectResponse)
def duplicate_project(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    复制项目（完整复刻）
    
    复制内容包括：
    - 项目本身（新名称加 "(副本)" 后缀）
    - 所有字段 (ProjectField)
    - 所有对话记录 (ChatMessage)
    """
    from core.models import ProjectField
    from core.models.chat_history import ChatMessage
    
    # 获取原项目
    old_project = db.query(Project).filter(Project.id == project_id).first()
    if not old_project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 创建新项目
    new_project = Project(
        id=generate_uuid(),
        name=f"{old_project.name} (副本)",
        creator_profile_id=old_project.creator_profile_id,
        version=1,
        version_note="从项目复制",
        current_phase=old_project.current_phase,
        phase_order=old_project.phase_order.copy() if old_project.phase_order else PROJECT_PHASES.copy(),
        phase_status=old_project.phase_status.copy() if old_project.phase_status else {},
        agent_autonomy=old_project.agent_autonomy.copy() if old_project.agent_autonomy else {},
        golden_context=old_project.golden_context.copy() if old_project.golden_context else {},
        use_deep_research=old_project.use_deep_research,
        use_flexible_architecture=old_project.use_flexible_architecture if hasattr(old_project, 'use_flexible_architecture') else False,
    )
    
    db.add(new_project)
    db.flush()  # 获取新项目ID
    
    # 复制所有字段
    old_fields = db.query(ProjectField).filter(
        ProjectField.project_id == old_project.id
    ).all()
    
    # 创建字段ID映射（旧ID -> 新ID）用于更新依赖关系
    field_id_mapping = {}
    new_fields = []
    
    for old_field in old_fields:
        new_field_id = generate_uuid()
        field_id_mapping[old_field.id] = new_field_id
        
        new_field = ProjectField(
            id=new_field_id,
            project_id=new_project.id,
            template_id=old_field.template_id,
            phase=old_field.phase,
            name=old_field.name,
            field_type=old_field.field_type,
            content=old_field.content,
            status=old_field.status,
            ai_prompt=old_field.ai_prompt,
            pre_questions=old_field.pre_questions.copy() if old_field.pre_questions else [],
            pre_answers=old_field.pre_answers.copy() if old_field.pre_answers else {},
            dependencies=old_field.dependencies.copy() if old_field.dependencies else {"depends_on": [], "dependency_type": "all"},
            constraints=old_field.constraints.copy() if hasattr(old_field, 'constraints') and old_field.constraints else None,
            need_review=old_field.need_review if hasattr(old_field, 'need_review') else True,
            order=old_field.order if hasattr(old_field, 'order') else 0,
        )
        new_fields.append(new_field)
    
    # 更新依赖关系中的字段ID
    for new_field in new_fields:
        if new_field.dependencies and new_field.dependencies.get("depends_on"):
            old_deps = new_field.dependencies["depends_on"]
            new_deps = [field_id_mapping.get(dep_id, dep_id) for dep_id in old_deps]
            new_field.dependencies = {
                **new_field.dependencies,
                "depends_on": new_deps,
            }
        db.add(new_field)
    
    # 复制对话记录
    old_messages = db.query(ChatMessage).filter(
        ChatMessage.project_id == old_project.id
    ).order_by(ChatMessage.created_at).all()
    
    message_id_mapping = {}
    for old_msg in old_messages:
        new_msg_id = generate_uuid()
        message_id_mapping[old_msg.id] = new_msg_id
        
        new_msg = ChatMessage(
            id=new_msg_id,
            project_id=new_project.id,
            role=old_msg.role,
            content=old_msg.content,
            original_content=old_msg.original_content,
            is_edited=old_msg.is_edited,
            message_metadata=old_msg.message_metadata.copy() if old_msg.message_metadata else {},
            parent_message_id=message_id_mapping.get(old_msg.parent_message_id) if old_msg.parent_message_id else None,
        )
        db.add(new_msg)
    
    db.commit()
    db.refresh(new_project)
    
    return _project_to_response(new_project)


@router.post("/{project_id}/versions", response_model=ProjectResponse)
def create_new_version(
    project_id: str,
    request: NewVersionRequest,
    db: Session = Depends(get_db),
):
    """创建项目新版本"""
    old_project = db.query(Project).filter(Project.id == project_id).first()
    if not old_project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 创建新版本
    new_project = Project(
        id=generate_uuid(),
        name=old_project.name,
        creator_profile_id=old_project.creator_profile_id,
        version=old_project.version + 1,
        version_note=request.version_note,
        parent_version_id=old_project.id,
        current_phase=old_project.current_phase,
        phase_order=old_project.phase_order.copy() if old_project.phase_order else PROJECT_PHASES.copy(),
        phase_status=old_project.phase_status.copy() if old_project.phase_status else {},
        agent_autonomy=old_project.agent_autonomy.copy() if old_project.agent_autonomy else {},
        golden_context=old_project.golden_context.copy() if old_project.golden_context else {},
        use_deep_research=old_project.use_deep_research,
    )
    
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    
    # 复制所有字段到新版本
    from core.models import ProjectField
    old_fields = db.query(ProjectField).filter(
        ProjectField.project_id == old_project.id
    ).all()
    
    # 创建字段ID映射（旧ID -> 新ID）用于更新依赖关系
    field_id_mapping = {}
    new_fields = []
    
    for old_field in old_fields:
        new_field_id = generate_uuid()
        field_id_mapping[old_field.id] = new_field_id
        
        new_field = ProjectField(
            id=new_field_id,
            project_id=new_project.id,
            template_id=old_field.template_id,
            phase=old_field.phase,
            name=old_field.name,
            field_type=old_field.field_type,
            content=old_field.content,
            status=old_field.status,
            ai_prompt=old_field.ai_prompt,
            pre_questions=old_field.pre_questions.copy() if old_field.pre_questions else [],
            pre_answers=old_field.pre_answers.copy() if old_field.pre_answers else {},
            dependencies=old_field.dependencies.copy() if old_field.dependencies else {"depends_on": [], "dependency_type": "all"},
        )
        new_fields.append(new_field)
    
    # 更新依赖关系中的字段ID
    for new_field in new_fields:
        if new_field.dependencies and new_field.dependencies.get("depends_on"):
            old_deps = new_field.dependencies["depends_on"]
            new_deps = [field_id_mapping.get(dep_id, dep_id) for dep_id in old_deps]
            new_field.dependencies = {
                **new_field.dependencies,
                "depends_on": new_deps,
            }
        db.add(new_field)
    
    db.commit()
    
    return _project_to_response(new_project)


@router.get("/{project_id}/versions", response_model=list[ProjectResponse])
def list_project_versions(
    project_id: str,
    db: Session = Depends(get_db),
):
    """获取项目的所有版本"""
    # 获取当前项目
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 获取所有相关版本（相同名称）
    versions = db.query(Project).filter(
        Project.name == project.name
    ).order_by(Project.version.desc()).all()
    
    return [_project_to_response(p) for p in versions]


# ============== Helpers ==============

def _project_to_response(project: Project) -> ProjectResponse:
    """转换为响应格式"""
    return ProjectResponse(
        id=project.id,
        name=project.name,
        version=project.version,
        version_note=project.version_note or "",
        creator_profile_id=project.creator_profile_id,
        current_phase=project.current_phase,
        phase_order=project.phase_order if project.phase_order is not None else PROJECT_PHASES.copy(),
        phase_status=project.phase_status or {},
        agent_autonomy=project.agent_autonomy or {},
        golden_context=project.golden_context or {},
        use_deep_research=project.use_deep_research if hasattr(project, 'use_deep_research') else True,
        use_flexible_architecture=project.use_flexible_architecture if hasattr(project, 'use_flexible_architecture') else False,
        created_at=project.created_at.isoformat() if project.created_at else "",
        updated_at=project.updated_at.isoformat() if project.updated_at else "",
    )

