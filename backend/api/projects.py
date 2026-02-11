# backend/api/projects.py
# 功能: 项目管理API
# 主要路由: CRUD操作、版本管理、导入导出
# 数据结构: ProjectCreate, ProjectUpdate, ProjectResponse

"""
项目管理 API
"""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any
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


# ============== 项目导入导出 ==============

@router.get("/{project_id}/export")
def export_project(
    project_id: str,
    include_logs: bool = False,
    db: Session = Depends(get_db),
):
    """
    导出项目完整数据（JSON）

    包含：项目本身、内容块、字段、对话记录、版本历史、
    评估记录、模拟记录、生成日志（可选）
    """
    from core.models import (
        ProjectField, ContentBlock, GenerationLog,
        SimulationRecord, EvaluationReport,
        EvalRun, EvalTask, EvalTrial,
    )
    from core.models.chat_history import ChatMessage
    from core.models.content_version import ContentVersion
    from core.models.block_history import BlockHistory

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # --- 辅助：把 ORM 对象序列化为 dict ---
    def _ser(obj, exclude=None):
        """序列化 SQLAlchemy 模型为 dict"""
        exclude = set(exclude or [])
        d = {}
        for col in obj.__table__.columns:
            if col.name in exclude:
                continue
            val = getattr(obj, col.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            d[col.name] = val
        return d

    # 项目本体
    project_data = _ser(project)

    # 创作者特质
    creator_profile_data = None
    if project.creator_profile_id:
        cp = db.query(CreatorProfile).filter(
            CreatorProfile.id == project.creator_profile_id
        ).first()
        if cp:
            creator_profile_data = _ser(cp)

    # ContentBlocks
    blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
    ).order_by(ContentBlock.order_index).all()
    blocks_data = [_ser(b) for b in blocks]

    # ProjectFields（旧架构）
    fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
    ).all()
    fields_data = [_ser(f) for f in fields]

    # ChatMessages
    messages = db.query(ChatMessage).filter(
        ChatMessage.project_id == project_id,
    ).order_by(ChatMessage.created_at).all()
    messages_data = [_ser(m) for m in messages]

    # ContentVersions（通过 block_id 关联）
    block_ids = [b.id for b in blocks]
    field_ids = [f.id for f in fields]
    all_versioned_ids = block_ids + field_ids
    versions_data = []
    if all_versioned_ids:
        versions = db.query(ContentVersion).filter(
            ContentVersion.block_id.in_(all_versioned_ids),
        ).order_by(ContentVersion.version_number).all()
        versions_data = [_ser(v) for v in versions]

    # BlockHistory
    history = db.query(BlockHistory).filter(
        BlockHistory.project_id == project_id,
    ).order_by(BlockHistory.created_at).all()
    history_data = [_ser(h) for h in history]

    # SimulationRecords
    sim_records = db.query(SimulationRecord).filter(
        SimulationRecord.project_id == project_id,
    ).all()
    sim_data = [_ser(s) for s in sim_records]

    # EvaluationReports
    eval_reports = db.query(EvaluationReport).filter(
        EvaluationReport.project_id == project_id,
    ).all()
    eval_reports_data = [_ser(r) for r in eval_reports]

    # EvalRuns + Tasks + Trials
    eval_runs = db.query(EvalRun).filter(
        EvalRun.project_id == project_id,
    ).all()
    eval_runs_data = [_ser(r) for r in eval_runs]

    run_ids = [r.id for r in eval_runs]
    tasks_data = []
    trials_data = []
    if run_ids:
        tasks = db.query(EvalTask).filter(
            EvalTask.eval_run_id.in_(run_ids),
        ).all()
        tasks_data = [_ser(t) for t in tasks]

        trials = db.query(EvalTrial).filter(
            EvalTrial.eval_run_id.in_(run_ids),
        ).all()
        trials_data = [_ser(t) for t in trials]

    # GenerationLogs（可选，可能很大）
    logs_data = []
    if include_logs:
        logs = db.query(GenerationLog).filter(
            GenerationLog.project_id == project_id,
        ).order_by(GenerationLog.created_at).all()
        logs_data = [_ser(l) for l in logs]

    return {
        "export_version": "1.0",
        "exported_at": datetime.now().isoformat(),
        "project": project_data,
        "creator_profile": creator_profile_data,
        "content_blocks": blocks_data,
        "project_fields": fields_data,
        "chat_messages": messages_data,
        "content_versions": versions_data,
        "block_history": history_data,
        "simulation_records": sim_data,
        "evaluation_reports": eval_reports_data,
        "eval_runs": eval_runs_data,
        "eval_tasks": tasks_data,
        "eval_trials": trials_data,
        "generation_logs": logs_data,
    }


class ProjectImportRequest(BaseModel):
    """导入项目请求"""
    data: Dict[str, Any]
    # 是否尝试匹配已有的创作者特质（按名称）
    match_creator_profile: bool = True


@router.post("/import")
def import_project(
    request: ProjectImportRequest,
    db: Session = Depends(get_db),
):
    """
    导入项目（从 JSON）

    自动为所有实体生成新 ID，维护内部引用关系。
    """
    from core.models import (
        ProjectField, ContentBlock, GenerationLog,
        SimulationRecord, EvaluationReport,
        EvalRun, EvalTask, EvalTrial,
    )
    from core.models.chat_history import ChatMessage
    from core.models.content_version import ContentVersion
    from core.models.block_history import BlockHistory

    data = request.data
    if "project" not in data:
        raise HTTPException(status_code=400, detail="缺少 project 字段")

    # ============ ID 映射 ============
    id_map: Dict[str, str] = {}

    def _new_id(old_id: str) -> str:
        """为旧 ID 生成新 ID 并缓存"""
        if not old_id:
            return ""
        if old_id not in id_map:
            id_map[old_id] = generate_uuid()
        return id_map[old_id]

    def _map_id(old_id: Optional[str]) -> Optional[str]:
        """映射可选 ID"""
        if not old_id:
            return None
        return id_map.get(old_id, old_id)

    def _map_list(old_ids: list) -> list:
        """映射 ID 列表"""
        if not old_ids:
            return []
        return [id_map.get(oid, oid) for oid in old_ids]

    try:
        # ============ 1. 创作者特质 ============
        cp_data = data.get("creator_profile")
        new_cp_id = None
        if cp_data:
            old_cp_id = cp_data.get("id", "")
            if request.match_creator_profile and cp_data.get("name"):
                # 尝试按名称匹配已有特质
                existing = db.query(CreatorProfile).filter(
                    CreatorProfile.name == cp_data["name"]
                ).first()
                if existing:
                    new_cp_id = existing.id
                    id_map[old_cp_id] = existing.id

            if not new_cp_id:
                new_cp_id = _new_id(old_cp_id)
                cp = CreatorProfile(
                    id=new_cp_id,
                    name=cp_data.get("name", "导入的创作者"),
                    description=cp_data.get("description", ""),
                    style_tags=cp_data.get("style_tags", []),
                    tone=cp_data.get("tone", ""),
                    values=cp_data.get("values", []),
                    target_audience=cp_data.get("target_audience", ""),
                    content_principles=cp_data.get("content_principles", []),
                    brand_voice=cp_data.get("brand_voice", ""),
                    avoid_patterns=cp_data.get("avoid_patterns", []),
                )
                db.add(cp)

        # ============ 2. 项目 ============
        proj_data = data["project"]
        old_proj_id = proj_data.get("id", "")
        new_proj_id = _new_id(old_proj_id)

        new_project = Project(
            id=new_proj_id,
            name=proj_data.get("name", "导入的项目"),
            creator_profile_id=new_cp_id,
            version=proj_data.get("version", 1),
            version_note=proj_data.get("version_note", "从导出文件导入"),
            current_phase=proj_data.get("current_phase", "intent"),
            phase_order=proj_data.get("phase_order", PROJECT_PHASES.copy()),
            phase_status=proj_data.get("phase_status", {}),
            agent_autonomy=proj_data.get("agent_autonomy", {}),
            golden_context=proj_data.get("golden_context", {}),
            use_deep_research=proj_data.get("use_deep_research", True),
            use_flexible_architecture=proj_data.get("use_flexible_architecture", False),
        )
        db.add(new_project)

        # ============ 3. ContentBlocks ============
        for b in data.get("content_blocks", []):
            old_id = b.get("id", "")
            _new_id(old_id)  # 预先注册所有 block ID

        for b in data.get("content_blocks", []):
            old_id = b.get("id", "")
            new_block = ContentBlock(
                id=id_map[old_id],
                project_id=new_proj_id,
                parent_id=_map_id(b.get("parent_id")),
                name=b.get("name", ""),
                block_type=b.get("block_type", "field"),
                depth=b.get("depth", 0),
                order_index=b.get("order_index", 0),
                content=b.get("content", ""),
                status=b.get("status", "pending"),
                ai_prompt=b.get("ai_prompt", ""),
                constraints=b.get("constraints", {}),
                pre_questions=b.get("pre_questions", []),
                pre_answers=b.get("pre_answers", {}),
                depends_on=_map_list(b.get("depends_on", [])),
                special_handler=b.get("special_handler"),
                need_review=b.get("need_review", True),
                is_collapsed=b.get("is_collapsed", False),
            )
            db.add(new_block)

        # ============ 4. ProjectFields ============
        for f in data.get("project_fields", []):
            old_id = f.get("id", "")
            _new_id(old_id)

        for f in data.get("project_fields", []):
            old_id = f.get("id", "")
            old_deps = f.get("dependencies", {})
            new_deps = {
                **old_deps,
                "depends_on": _map_list(old_deps.get("depends_on", [])),
            }
            new_field = ProjectField(
                id=id_map[old_id],
                project_id=new_proj_id,
                template_id=f.get("template_id"),
                phase=f.get("phase", "intent"),
                name=f.get("name", ""),
                field_type=f.get("field_type", "text"),
                content=f.get("content", ""),
                status=f.get("status", "pending"),
                ai_prompt=f.get("ai_prompt", ""),
                pre_questions=f.get("pre_questions", []),
                pre_answers=f.get("pre_answers", {}),
                dependencies=new_deps,
                constraints=f.get("constraints", {}),
                need_review=f.get("need_review", True),
            )
            db.add(new_field)

        # ============ 5. ChatMessages ============
        for m in data.get("chat_messages", []):
            old_id = m.get("id", "")
            _new_id(old_id)

        for m in data.get("chat_messages", []):
            old_id = m.get("id", "")
            new_msg = ChatMessage(
                id=id_map[old_id],
                project_id=new_proj_id,
                role=m.get("role", "user"),
                content=m.get("content", ""),
                original_content=m.get("original_content", ""),
                is_edited=m.get("is_edited", False),
                message_metadata=m.get("message_metadata", {}),
                parent_message_id=_map_id(m.get("parent_message_id")),
            )
            db.add(new_msg)

        # ============ 6. ContentVersions ============
        for v in data.get("content_versions", []):
            old_id = v.get("id", "")
            new_ver = ContentVersion(
                id=_new_id(old_id),
                block_id=_map_id(v.get("block_id")) or "",
                version_number=v.get("version_number", 1),
                content=v.get("content", ""),
                source=v.get("source", "manual"),
                source_detail=v.get("source_detail"),
            )
            db.add(new_ver)

        # ============ 7. BlockHistory ============
        for h in data.get("block_history", []):
            old_id = h.get("id", "")
            snap = h.get("block_snapshot", {})
            # 映射快照中的 ID
            if snap.get("id"):
                snap["id"] = _map_id(snap["id"]) or snap["id"]
            if snap.get("parent_id"):
                snap["parent_id"] = _map_id(snap["parent_id"])
            children_snaps = h.get("children_snapshots", [])
            for cs in children_snaps:
                if cs.get("id"):
                    cs["id"] = _map_id(cs["id"]) or cs["id"]
                if cs.get("parent_id"):
                    cs["parent_id"] = _map_id(cs["parent_id"])

            new_hist = BlockHistory(
                id=_new_id(old_id),
                project_id=new_proj_id,
                action=h.get("action", "create"),
                block_id=_map_id(h.get("block_id")) or "",
                block_snapshot=snap,
                children_snapshots=children_snaps,
                undone=h.get("undone", False),
            )
            db.add(new_hist)

        # ============ 8. SimulationRecords ============
        for s in data.get("simulation_records", []):
            old_id = s.get("id", "")
            new_sim = SimulationRecord(
                id=_new_id(old_id),
                project_id=new_proj_id,
                simulator_id=s.get("simulator_id", ""),
                target_field_ids=_map_list(s.get("target_field_ids", [])),
                persona=s.get("persona", {}),
                interaction_log=s.get("interaction_log", []),
                feedback=s.get("feedback", {}),
                status=s.get("status", "completed"),
            )
            db.add(new_sim)

        # ============ 9. EvaluationReports ============
        for r in data.get("evaluation_reports", []):
            old_id = r.get("id", "")
            new_report = EvaluationReport(
                id=_new_id(old_id),
                project_id=new_proj_id,
                template_id=r.get("template_id"),
                scores=r.get("scores", {}),
                overall_score=r.get("overall_score"),
                suggestions=r.get("suggestions", []),
                summary=r.get("summary", ""),
            )
            db.add(new_report)

        # ============ 10. EvalRuns + Tasks + Trials ============
        for run in data.get("eval_runs", []):
            old_id = run.get("id", "")
            new_run = EvalRun(
                id=_new_id(old_id),
                project_id=new_proj_id,
                name=run.get("name", "评估运行"),
                config=run.get("config", {}),
                status=run.get("status", "completed"),
                summary=run.get("summary", ""),
                overall_score=run.get("overall_score"),
                role_scores=run.get("role_scores", {}),
                trial_count=run.get("trial_count", 0),
                content_block_id=_map_id(run.get("content_block_id")),
            )
            db.add(new_run)

        for task in data.get("eval_tasks", []):
            old_id = task.get("id", "")
            new_task = EvalTask(
                id=_new_id(old_id),
                eval_run_id=_map_id(task.get("eval_run_id")) or "",
                name=task.get("name", ""),
                simulator_type=task.get("simulator_type", "coach"),
                interaction_mode=task.get("interaction_mode", "review"),
                simulator_config=task.get("simulator_config", {}),
                persona_config=task.get("persona_config", {}),
                target_block_ids=_map_list(task.get("target_block_ids", [])),
                grader_config=task.get("grader_config", {}),
                order_index=task.get("order_index", 0),
                status=task.get("status", "completed"),
            )
            db.add(new_task)

        for trial in data.get("eval_trials", []):
            old_id = trial.get("id", "")
            new_trial = EvalTrial(
                id=_new_id(old_id),
                eval_run_id=_map_id(trial.get("eval_run_id")) or "",
                eval_task_id=_map_id(trial.get("eval_task_id")),
                role=trial.get("role", "coach"),
                role_config=trial.get("role_config", {}),
                interaction_mode=trial.get("interaction_mode", "review"),
                input_block_ids=_map_list(trial.get("input_block_ids", [])),
                persona=trial.get("persona", {}),
                nodes=trial.get("nodes", []),
                result=trial.get("result", {}),
                grader_outputs=trial.get("grader_outputs", []),
                llm_calls=trial.get("llm_calls", []),
                overall_score=trial.get("overall_score"),
                status=trial.get("status", "completed"),
                error=trial.get("error", ""),
                tokens_in=trial.get("tokens_in", 0),
                tokens_out=trial.get("tokens_out", 0),
                cost=trial.get("cost", 0.0),
            )
            db.add(new_trial)

        # ============ 11. GenerationLogs ============
        for log in data.get("generation_logs", []):
            old_id = log.get("id", "")
            new_log = GenerationLog(
                id=_new_id(old_id),
                project_id=new_proj_id,
                field_id=_map_id(log.get("field_id")),
                phase=log.get("phase", ""),
                operation=log.get("operation", ""),
                model=log.get("model", "gpt-5.1"),
                prompt_input=log.get("prompt_input", ""),
                prompt_output=log.get("prompt_output", ""),
                tokens_in=log.get("tokens_in", 0),
                tokens_out=log.get("tokens_out", 0),
                duration_ms=log.get("duration_ms", 0),
                cost=log.get("cost", 0.0),
                status=log.get("status", "success"),
                error_message=log.get("error_message", ""),
            )
            db.add(new_log)

        db.commit()
        db.refresh(new_project)

        return {
            "message": f"项目「{new_project.name}」导入成功",
            "project": _project_to_response(new_project),
            "stats": {
                "content_blocks": len(data.get("content_blocks", [])),
                "project_fields": len(data.get("project_fields", [])),
                "chat_messages": len(data.get("chat_messages", [])),
                "content_versions": len(data.get("content_versions", [])),
                "simulation_records": len(data.get("simulation_records", [])),
                "eval_runs": len(data.get("eval_runs", [])),
                "generation_logs": len(data.get("generation_logs", [])),
            },
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


# ============== Global Search & Replace ==============


class SearchRequest(BaseModel):
    """全局搜索请求"""
    query: str
    case_sensitive: bool = False


class ReplaceRequest(BaseModel):
    """全局替换请求"""
    query: str
    replacement: str
    case_sensitive: bool = False
    # 指定要替换的位置：[{"type": "field"|"block", "id": "xxx", "indices": [0,1,2]}]
    # indices 表示该字段中第几个匹配项（0-based），不传则替换该字段所有匹配
    targets: Optional[List[Dict[str, Any]]] = None


@router.post("/{project_id}/search")
def search_project(
    project_id: str,
    request: SearchRequest,
    db: Session = Depends(get_db),
):
    """
    全局搜索：在项目的所有字段和内容块中搜索内容。
    返回每个匹配的字段/块名称、匹配片段（含上下文）、位置信息。
    """
    from core.models import ProjectField, ContentBlock
    import re

    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    query = request.query
    if not query:
        return {"results": [], "total_matches": 0}

    flags = 0 if request.case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(query), flags)

    results = []

    # 搜索 ProjectField
    fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
    ).all()
    for f in fields:
        if not f.content:
            continue
        matches = list(pattern.finditer(f.content))
        if matches:
            snippets = _build_search_snippets(f.content, matches, query)
            results.append({
                "type": "field",
                "id": f.id,
                "name": f.name,
                "phase": f.phase or "",
                "match_count": len(matches),
                "snippets": snippets,
            })

    # 搜索 ContentBlock
    blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,
    ).all()
    for b in blocks:
        if not b.content:
            continue
        matches = list(pattern.finditer(b.content))
        if matches:
            snippets = _build_search_snippets(b.content, matches, query)
            results.append({
                "type": "block",
                "id": b.id,
                "name": b.name,
                "phase": "",
                "parent_id": b.parent_id,
                "match_count": len(matches),
                "snippets": snippets,
            })

    total_matches = sum(r["match_count"] for r in results)

    return {"results": results, "total_matches": total_matches}


@router.post("/{project_id}/replace")
def replace_in_project(
    project_id: str,
    request: ReplaceRequest,
    db: Session = Depends(get_db),
):
    """
    全局替换：在项目的指定字段/块中替换内容。
    支持指定替换哪些匹配项（targets），也支持全部替换。
    """
    from core.models import ProjectField, ContentBlock
    from core.models.content_version import ContentVersion
    import re

    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    query = request.query
    replacement = request.replacement
    if not query:
        raise HTTPException(400, "Search query cannot be empty")

    flags = 0 if request.case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(query), flags)

    replaced_count = 0
    affected_items = []

    if request.targets:
        # 精确替换：只替换指定的匹配项
        for target in request.targets:
            item_type = target.get("type")
            item_id = target.get("id")
            indices = target.get("indices")  # None = 全部替换

            if item_type == "field":
                item = db.query(ProjectField).filter_by(id=item_id).first()
            elif item_type == "block":
                item = db.query(ContentBlock).filter_by(id=item_id).first()
            else:
                continue

            if not item or not item.content:
                continue

            old_content = item.content
            new_content, count = _replace_content(old_content, pattern, replacement, indices)
            if count > 0:
                # 保存版本
                _save_search_replace_version(db, item.id, old_content, item.name if hasattr(item, 'name') else "")
                item.content = new_content
                replaced_count += count
                affected_items.append({
                    "type": item_type,
                    "id": item.id,
                    "name": item.name if hasattr(item, 'name') else "",
                    "count": count,
                })
    else:
        # 全量替换：在项目所有字段和块中替换
        fields = db.query(ProjectField).filter(
            ProjectField.project_id == project_id,
        ).all()
        for f in fields:
            if not f.content:
                continue
            old_content = f.content
            new_content, count = _replace_content(old_content, pattern, replacement, None)
            if count > 0:
                _save_search_replace_version(db, f.id, old_content, f.name)
                f.content = new_content
                replaced_count += count
                affected_items.append({"type": "field", "id": f.id, "name": f.name, "count": count})

        blocks = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.deleted_at == None,
        ).all()
        for b in blocks:
            if not b.content:
                continue
            old_content = b.content
            new_content, count = _replace_content(old_content, pattern, replacement, None)
            if count > 0:
                _save_search_replace_version(db, b.id, old_content, b.name)
                b.content = new_content
                replaced_count += count
                affected_items.append({"type": "block", "id": b.id, "name": b.name, "count": count})

    db.commit()
    return {
        "replaced_count": replaced_count,
        "affected_items": affected_items,
    }


def _build_search_snippets(content: str, matches: list, query: str, context_chars: int = 60) -> list:
    """构建搜索结果片段，带上下文"""
    snippets = []
    for i, m in enumerate(matches[:20]):  # 每个字段最多展示20个匹配
        start = max(0, m.start() - context_chars)
        end = min(len(content), m.end() + context_chars)

        prefix = ("..." if start > 0 else "") + content[start:m.start()]
        matched = content[m.start():m.end()]
        suffix = content[m.end():end] + ("..." if end < len(content) else "")

        snippets.append({
            "index": i,
            "offset": m.start(),
            "prefix": prefix,
            "match": matched,
            "suffix": suffix,
            "line": content[:m.start()].count("\n") + 1,
        })
    return snippets


def _replace_content(content: str, pattern, replacement: str, indices: list | None) -> tuple[str, int]:
    """
    替换内容。如果 indices 为 None，替换所有匹配；否则只替换指定索引的匹配。
    返回 (新内容, 替换次数)
    """
    if indices is None:
        new_content, count = pattern.subn(replacement, content)
        return new_content, count

    matches = list(pattern.finditer(content))
    if not matches:
        return content, 0

    indices_set = set(indices)
    count = 0
    parts = []
    last_end = 0
    for i, m in enumerate(matches):
        parts.append(content[last_end:m.start()])
        if i in indices_set:
            parts.append(replacement)
            count += 1
        else:
            parts.append(m.group())
        last_end = m.end()
    parts.append(content[last_end:])
    return "".join(parts), count


def _save_search_replace_version(db, item_id: str, old_content: str, item_name: str):
    """保存替换前的版本"""
    from core.models.content_version import ContentVersion
    max_ver = db.query(ContentVersion).filter(
        ContentVersion.block_id == item_id,
    ).count()
    ver = ContentVersion(
        id=generate_uuid(),
        block_id=item_id,
        version_number=max_ver + 1,
        content=old_content,
        source="search_replace",
        source_detail=f"search_replace:{item_name}",
    )
    db.add(ver)


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

