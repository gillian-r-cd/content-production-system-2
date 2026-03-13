# backend/api/projects.py
# 功能: 项目管理API — CRUD、版本管理、完整导入/导出、复制、全局搜索替换
# 主要路由: CRUD, /export, /import, /duplicate, /versions, /search, /replace
# 导出/导入范围: Project, CreatorProfile, ContentBlock, ProjectField, ChatMessage,
#   ContentVersion, BlockHistory, SimulationRecord, EvalRun/Task/Trial,
#   MemoryItem, Grader, GenerationLog(可选)
# 数据结构: ProjectCreate, ProjectUpdate, ProjectResponse, ProjectImportRequest

"""
项目管理 API
"""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.localization import DEFAULT_LOCALE, normalize_locale
from core.locale_text import rt
from core.models import Project, CreatorProfile, PROJECT_PHASES, generate_uuid
from core.llm_compat import get_model_name
from core.project_mode_bootstrap import ensure_project_agent_modes
from core.pre_question_utils import normalize_pre_answers, normalize_pre_questions


router = APIRouter()


def _project_locale(project: Project) -> str:
    return normalize_locale(getattr(project, "locale", DEFAULT_LOCALE))


def _rewrite_embedded_project_asset_ids(
    value: Any,
    *,
    block_id_mapping: Dict[str, str],
    mode_id_mapping: Dict[str, str],
) -> Any:
    if isinstance(value, list):
        return [
            _rewrite_embedded_project_asset_ids(
                item,
                block_id_mapping=block_id_mapping,
                mode_id_mapping=mode_id_mapping,
            )
            for item in value
        ]
    if isinstance(value, dict):
        rewritten: Dict[str, Any] = {}
        for key, item in value.items():
            if key == "mode_id" and isinstance(item, str):
                rewritten[key] = mode_id_mapping.get(item, item)
                continue
            if key in {"block_id", "target_entity_id"} and isinstance(item, str):
                rewritten[key] = block_id_mapping.get(item, item)
                continue
            rewritten[key] = _rewrite_embedded_project_asset_ids(
                item,
                block_id_mapping=block_id_mapping,
                mode_id_mapping=mode_id_mapping,
            )
        return rewritten
    return value


def _rewrite_chat_message_metadata_for_project(
    message_metadata: Dict[str, Any] | None,
    *,
    block_id_mapping: Dict[str, str],
    mode_id_mapping: Dict[str, str],
) -> Dict[str, Any]:
    cloned = json.loads(json.dumps(message_metadata or {}))
    return _rewrite_embedded_project_asset_ids(
        cloned,
        block_id_mapping=block_id_mapping,
        mode_id_mapping=mode_id_mapping,
    )


# ============== Schemas ==============

class ProjectCreate(BaseModel):
    """创建项目请求"""
    name: str
    creator_profile_id: Optional[str] = None
    use_deep_research: bool = True
    use_flexible_architecture: bool = True  # [已废弃] 统一为 True
    locale: str = DEFAULT_LOCALE
    phase_order: Optional[List[str]] = None  # 自定义阶段顺序，None 使用默认，[] 表示从零开始


class ProjectUpdate(BaseModel):
    """更新项目请求"""
    name: Optional[str] = None
    current_phase: Optional[str] = None
    phase_order: Optional[List[str]] = None
    agent_autonomy: Optional[Dict[str, bool]] = None  # [已废弃] 不再使用，保留兼容旧API客户端
    golden_context: Optional[dict] = None  # [已废弃] P3-2: 不再使用，保留兼容旧API客户端
    use_deep_research: Optional[bool] = None
    use_flexible_architecture: Optional[bool] = None
    locale: Optional[str] = None


class ProjectResponse(BaseModel):
    """项目响应"""
    id: str
    name: str
    version: int
    version_note: str
    parent_version_id: Optional[str] = None  # 父版本 ID，用于版本族谱分组
    creator_profile_id: Optional[str]
    current_phase: str
    phase_order: List[str]
    phase_status: Dict[str, str]
    agent_autonomy: Dict[str, bool]  # [已废弃] 保留兼容旧数据，新项目为空dict
    golden_context: dict  # [已废弃] P3-2: 保留兼容旧数据，新项目为空dict
    use_deep_research: bool
    use_flexible_architecture: bool = True  # [已废弃] 统一为 True
    locale: str = DEFAULT_LOCALE
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class NewVersionRequest(BaseModel):
    """创建新版本请求"""
    version_note: str


class SaveAsFieldTemplateRequest(BaseModel):
    """保存为内容块模板请求"""
    name: str
    description: str = ""
    category: str = "通用"


class ImportContentTreeJsonRequest(BaseModel):
    """项目级内容树追加导入请求"""
    data: Dict[str, Any]


class MarkdownImportFileRequest(BaseModel):
    """单个 Markdown 文件载荷"""
    name: str
    path: Optional[str] = None
    content: str


class ImportMarkdownFilesRequest(BaseModel):
    """项目级 Markdown 批量导入请求"""
    import_mode: Literal["heading_tree", "raw_file"] = "heading_tree"
    files: List[MarkdownImportFileRequest]


class BatchDeleteProjectsRequest(BaseModel):
    """批量删除项目请求"""
    project_ids: List[str]


def _rewrite_draft_dependency_refs(value: Any, block_id_mapping: Dict[str, str]) -> Any:
    if isinstance(value, list):
        return [_rewrite_draft_dependency_refs(item, block_id_mapping) for item in value]
    if isinstance(value, dict):
        rewritten = {}
        for key, item in value.items():
            if key == "ref_type" and value.get("ref_type") == "project_block":
                rewritten[key] = item
                continue
            if (
                value.get("ref_type") == "project_block"
                and key == "block_id"
                and isinstance(item, str)
            ):
                rewritten[key] = block_id_mapping.get(item, item)
                continue
            rewritten[key] = _rewrite_draft_dependency_refs(item, block_id_mapping)
        return rewritten
    return value


def _clone_draft_payload_for_project(
    payload: Dict[str, Any] | None,
    *,
    block_id_mapping: Dict[str, str],
) -> Dict[str, Any]:
    cloned = json.loads(json.dumps(payload or {}))
    return _rewrite_draft_dependency_refs(cloned, block_id_mapping)


def _clone_structure_draft_for_project(
    old_draft,
    *,
    new_project_id: str,
    block_id_mapping: Dict[str, str],
):
    from core.models import ProjectStructureDraft

    return ProjectStructureDraft(
        id=generate_uuid(),
        project_id=new_project_id,
        draft_type=old_draft.draft_type,
        name=old_draft.name,
        status="draft",
        source_text=old_draft.source_text or "",
        split_config=json.loads(json.dumps(old_draft.split_config or {})),
        draft_payload=_clone_draft_payload_for_project(
            old_draft.draft_payload,
            block_id_mapping=block_id_mapping,
        ),
        validation_errors=[],
        last_validated_at=None,
        apply_count=0,
        last_applied_at=None,
    )


def _import_structure_draft_for_project(
    draft_data: Dict[str, Any],
    *,
    new_project_id: str,
    id_map: Dict[str, str],
):
    from core.models import ProjectStructureDraft

    return ProjectStructureDraft(
        id=id_map.get(draft_data.get("id", ""), generate_uuid()),
        project_id=new_project_id,
        draft_type=draft_data.get("draft_type", "auto_split"),
        name=draft_data.get("name", "自动拆分内容"),
        status="draft",
        source_text=draft_data.get("source_text", ""),
        split_config=json.loads(json.dumps(draft_data.get("split_config", {}))),
        draft_payload=_clone_draft_payload_for_project(
            draft_data.get("draft_payload", {}),
            block_id_mapping=id_map,
        ),
        validation_errors=[],
        last_validated_at=None,
        apply_count=0,
        last_applied_at=None,
    )


def _dedupe_project_ids(project_ids: List[str]) -> List[str]:
    """保留原顺序去重，避免重复删除同一项目。"""
    seen: set[str] = set()
    unique_ids: List[str] = []
    for project_id in project_ids:
        if not project_id or project_id in seen:
            continue
        seen.add(project_id)
        unique_ids.append(project_id)
    return unique_ids


def _resolve_surviving_parent_version_id(
    parent_version_id: Optional[str],
    *,
    parent_map: Dict[str, Optional[str]],
    deleting_ids: set[str],
) -> Optional[str]:
    """沿版本链向上找到最近一个未被删除的父版本。"""
    current_id = parent_version_id
    visited: set[str] = set()
    while current_id and current_id in deleting_ids:
        if current_id in visited:
            return None
        visited.add(current_id)
        current_id = parent_map.get(current_id)
    return current_id


def _relink_project_version_children_before_delete(
    db: Session,
    *,
    deleting_ids: set[str],
) -> None:
    """删除前重连版本链，避免父版本删除后剩余项目或待删子版本触发外键冲突。"""
    if not deleting_ids:
        return

    parent_map = {
        row.id: row.parent_version_id
        for row in db.query(Project.id, Project.parent_version_id).all()
    }
    direct_children = db.query(Project).filter(Project.parent_version_id.in_(deleting_ids)).all()
    for child in direct_children:
        child.parent_version_id = _resolve_surviving_parent_version_id(
            child.parent_version_id,
            parent_map=parent_map,
            deleting_ids=deleting_ids,
        )
    if direct_children:
        db.flush()


def _delete_project_with_related_data(db: Session, project: Project) -> None:
    """删除单个项目及其所有关联数据，但不在内部提交事务。"""
    from core.models import (
        ProjectField,
        ContentBlock,
        BlockHistory,
        MemoryItem,
        ProjectStructureDraft,
        AgentMode,
        Conversation,
    )
    from core.models.chat_history import ChatMessage
    from core.models.generation_log import GenerationLog
    from core.models.simulation_record import SimulationRecord
    from core.models.eval_run import EvalRun
    from core.models.eval_task import EvalTask
    from core.models.eval_trial import EvalTrial
    from core.models.content_version import ContentVersion
    from core.models.grader import Grader

    project_id = project.id

    # 收集所有 block/field ID，用于清理 ContentVersion
    block_ids = [b.id for b in db.query(ContentBlock.id).filter(
        ContentBlock.project_id == project_id
    ).all()]
    field_ids = [f.id for f in db.query(ProjectField.id).filter(
        ProjectField.project_id == project_id
    ).all()]
    all_versioned_ids = block_ids + field_ids

    # 删除 ContentVersion（通过 block_id 关联 block 和 field）
    if all_versioned_ids:
        db.query(ContentVersion).filter(
            ContentVersion.block_id.in_(all_versioned_ids)
        ).delete(synchronize_session=False)

    # 删除 EvalTrial + EvalTask（通过 EvalRun 关联项目）
    run_ids = [r.id for r in db.query(EvalRun.id).filter(
        EvalRun.project_id == project_id
    ).all()]
    if run_ids:
        db.query(EvalTrial).filter(EvalTrial.eval_run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(EvalTask).filter(EvalTask.eval_run_id.in_(run_ids)).delete(synchronize_session=False)
    db.query(EvalRun).filter(EvalRun.project_id == project_id).delete()

    # 删除关联的生成日志
    db.query(GenerationLog).filter(GenerationLog.project_id == project_id).delete()

    # 删除关联的块历史记录
    db.query(BlockHistory).filter(BlockHistory.project_id == project_id).delete()

    # 删除关联的模拟记录
    db.query(SimulationRecord).filter(SimulationRecord.project_id == project_id).delete()

    # 删除项目记忆（仅项目级记忆，全局记忆不删）
    db.query(MemoryItem).filter(MemoryItem.project_id == project_id).delete()

    # 删除项目角色
    db.query(AgentMode).filter(AgentMode.project_id == project_id).delete()

    # 删除项目级结构草稿
    db.query(ProjectStructureDraft).filter(ProjectStructureDraft.project_id == project_id).delete()

    # 删除项目专用评分器
    db.query(Grader).filter(Grader.project_id == project_id).delete()

    # 删除关联的内容块
    db.query(ContentBlock).filter(ContentBlock.project_id == project_id).delete()

    # 删除关联的对话记录
    db.query(ChatMessage).filter(ChatMessage.project_id == project_id).delete()
    db.query(Conversation).filter(Conversation.project_id == project_id).delete()

    # 删除关联的字段（传统架构）
    db.query(ProjectField).filter(ProjectField.project_id == project_id).delete()

    # 删除项目本身
    db.delete(project)


def _delete_projects_atomically(
    db: Session,
    *,
    project_ids: List[str],
) -> List[str]:
    """批量删除项目并保持版本链与事务一致性。"""
    unique_ids = _dedupe_project_ids(project_ids)
    if not unique_ids:
        return []

    projects = db.query(Project).filter(Project.id.in_(unique_ids)).all()
    project_by_id = {project.id: project for project in projects}
    missing_ids = [project_id for project_id in unique_ids if project_id not in project_by_id]
    if missing_ids:
        missing_text = ", ".join(missing_ids)
        raise HTTPException(status_code=404, detail=f"Projects not found: {missing_text}")

    _relink_project_version_children_before_delete(db, deleting_ids=set(unique_ids))
    for project_id in unique_ids:
        _delete_project_with_related_data(db, project_by_id[project_id])
    return unique_ids


# ============== Routes ==============

@router.get("/", response_model=List[ProjectResponse])
def list_projects(
    skip: int = 0,
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """获取项目列表。

    默认返回完整列表，并按最近更新时间倒序排列。
    工作台项目选择器没有分页能力，因此这里不能静默截断前 100 条，
    否则新建项目可能已经成功落库，却在前端列表中不可见。
    """
    query = db.query(Project).order_by(Project.updated_at.desc(), Project.created_at.desc())
    if skip:
        query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)
    projects = query.all()
    return [_project_to_response(p) for p in projects]


@router.post("/", response_model=ProjectResponse)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
):
    """创建新项目"""
    # P3-2: golden_context 已废弃，创作者特质通过 creator_profile 关系获取，
    # 意图/调研结果通过 ContentBlock 依赖链传递
    
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
    
    db_project = Project(
        id=generate_uuid(),
        name=project.name,
        creator_profile_id=project.creator_profile_id,
        use_deep_research=project.use_deep_research,
        use_flexible_architecture=project.use_flexible_architecture,
        locale=normalize_locale(project.locale),
        version=1,
        current_phase=initial_phase,
        phase_order=actual_phase_order,
        phase_status={p: "pending" for p in actual_phase_order},
        golden_context={},  # P3-2: 已废弃，保留空dict兼容DB
    )
    
    db.add(db_project)
    ensure_project_agent_modes(db, db_project.id, locale=db_project.locale)
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
    if "locale" in update_data:
        update_data["locale"] = normalize_locale(update_data["locale"])
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
    """
    删除项目（包括所有关联数据）

    按依赖顺序删除：先删子表/关联表，再删主表。
    """
    try:
        deleted_ids = _delete_projects_atomically(db, project_ids=[project_id])
        if not deleted_ids:
            raise HTTPException(status_code=404, detail="Project not found")
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"message": "Project deleted"}


@router.post("/batch-delete")
def batch_delete_projects(
    request: BatchDeleteProjectsRequest,
    db: Session = Depends(get_db),
):
    """批量删除多个项目，保持事务一致并在删除前重连版本链。"""
    try:
        deleted_ids = _delete_projects_atomically(db, project_ids=request.project_ids)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,
        "deleted_ids": deleted_ids,
        "deleted_count": len(deleted_ids),
    }


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
    - 所有内容块 (ContentBlock) — 灵活架构的核心数据
    - 所有会话与对话记录 (Conversation + ChatMessage)
    - 所有内容版本 (ContentVersion)
    - 所有块操作历史 (BlockHistory)
    - 所有模拟记录 (SimulationRecord)
    - 所有评估数据 (EvalRun/EvalTask/EvalTrial)
    - 所有项目记忆 (MemoryItem)
    - 所有项目专用评分器 (Grader)
    """
    from core.models import ProjectField, MemoryItem, ProjectStructureDraft, AgentMode, Conversation
    from core.models.chat_history import ChatMessage
    from core.models.content_block import ContentBlock
    from core.models.content_version import ContentVersion
    from core.models.block_history import BlockHistory
    from core.models.simulation_record import SimulationRecord
    from core.models.eval_run import EvalRun
    from core.models.eval_task import EvalTask
    from core.models.eval_trial import EvalTrial
    from core.models.grader import Grader
    
    # 获取原项目
    old_project = db.query(Project).filter(Project.id == project_id).first()
    if not old_project:
        raise HTTPException(status_code=404, detail="Project not found")
    source_locale = _project_locale(old_project)
    
    # 创建新项目
    new_project = Project(
        id=generate_uuid(),
        name=rt(source_locale, "project.duplicate.name", name=old_project.name),
        creator_profile_id=old_project.creator_profile_id,
        version=1,
        version_note=rt(source_locale, "project.duplicate.version_note"),
        current_phase=old_project.current_phase,
        phase_order=old_project.phase_order.copy() if old_project.phase_order else PROJECT_PHASES.copy(),
        phase_status=old_project.phase_status.copy() if old_project.phase_status else {},
        agent_autonomy=old_project.agent_autonomy.copy() if old_project.agent_autonomy else {},
        golden_context={},  # P3-2: 已废弃，不再复制
        use_deep_research=old_project.use_deep_research,
        use_flexible_architecture=True,  # P0-1: 统一为 True
        locale=source_locale,
    )
    
    db.add(new_project)
    db.flush()  # 获取新项目ID
    
    # ---- 复制所有字段 (ProjectField) ----
    old_fields = db.query(ProjectField).filter(
        ProjectField.project_id == old_project.id
    ).all()
    
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
            pre_questions=normalize_pre_questions(old_field.pre_questions or []),
            pre_answers=normalize_pre_answers(old_field.pre_answers or {}, old_field.pre_questions or []),
            dependencies=old_field.dependencies.copy() if old_field.dependencies else {"depends_on": [], "dependency_type": "all"},
            constraints=old_field.constraints.copy() if hasattr(old_field, 'constraints') and old_field.constraints else None,
            need_review=old_field.need_review if hasattr(old_field, 'need_review') else True,
            order=old_field.order if hasattr(old_field, 'order') else 0,
            digest=old_field.digest if hasattr(old_field, 'digest') else None,
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
    
    # ---- 复制所有内容块 (ContentBlock) — 灵活架构的核心 ----
    old_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == old_project.id,
        ContentBlock.deleted_at == None,  # noqa: E711 — 跳过已软删除的
    ).order_by(ContentBlock.depth, ContentBlock.order_index).all()
    
    block_id_mapping = {}
    
    # 第一遍：分配新 ID
    for old_block in old_blocks:
        block_id_mapping[old_block.id] = generate_uuid()
    
    # 第二遍：创建副本（parent_id / depends_on 用映射后的 ID）
    for old_block in old_blocks:
        new_block_id = block_id_mapping[old_block.id]
        new_parent_id = block_id_mapping.get(old_block.parent_id) if old_block.parent_id else None
        new_depends_on = [
            block_id_mapping.get(dep, dep) for dep in (old_block.depends_on or [])
        ]
        
        new_block = ContentBlock(
            id=new_block_id,
            project_id=new_project.id,
            parent_id=new_parent_id,
            name=old_block.name,
            block_type=old_block.block_type,
            depth=old_block.depth,
            order_index=old_block.order_index,
            content=old_block.content or "",
            status=old_block.status,
            ai_prompt=old_block.ai_prompt or "",
            constraints=old_block.constraints.copy() if old_block.constraints else {},
            pre_questions=normalize_pre_questions(old_block.pre_questions or []),
            pre_answers=normalize_pre_answers(old_block.pre_answers or {}, old_block.pre_questions or []),
            guidance_input=getattr(old_block, "guidance_input", "") or "",
            guidance_output=getattr(old_block, "guidance_output", "") or "",
            depends_on=new_depends_on,
            special_handler=old_block.special_handler,
            need_review=old_block.need_review,
            auto_generate=getattr(old_block, 'auto_generate', False),
            is_collapsed=old_block.is_collapsed,
            model_override=getattr(old_block, 'model_override', None),
            digest=old_block.digest,
        )
        db.add(new_block)

    # ---- 预构建角色映射（Conversation / ChatMessage / MemoryItem 都会引用 mode_id）----
    old_modes = db.query(AgentMode).filter(
        AgentMode.project_id == old_project.id,
        AgentMode.is_template.is_(False),
    ).order_by(AgentMode.sort_order, AgentMode.created_at).all()
    mode_id_mapping = {
        old_mode.id: generate_uuid()
        for old_mode in old_modes
        if old_mode.id
    }

    # ---- 复制会话 ----
    old_conversations = db.query(Conversation).filter(
        Conversation.project_id == old_project.id,
    ).order_by(
        Conversation.last_message_at.asc(),
        Conversation.created_at.asc(),
    ).all()
    conversation_id_mapping: Dict[str, str] = {}
    for old_conversation in old_conversations:
        new_conversation_id = generate_uuid()
        conversation_id_mapping[old_conversation.id] = new_conversation_id
        new_conversation = Conversation(
            id=new_conversation_id,
            project_id=new_project.id,
            mode_id=mode_id_mapping.get(old_conversation.mode_id, old_conversation.mode_id),
            mode=old_conversation.mode,
            title=old_conversation.title,
            status=old_conversation.status,
            bootstrap_policy=old_conversation.bootstrap_policy,
            last_message_at=old_conversation.last_message_at,
            message_count=old_conversation.message_count,
        )
        db.add(new_conversation)

    # ---- 复制对话消息 ----
    old_messages = db.query(ChatMessage).filter(
        ChatMessage.project_id == old_project.id
    ).order_by(ChatMessage.created_at).all()

    message_id_mapping = {}
    for old_msg in old_messages:
        new_msg_id = generate_uuid()
        message_id_mapping[old_msg.id] = new_msg_id

    for old_msg in old_messages:
        new_msg_id = message_id_mapping[old_msg.id]
        new_msg = ChatMessage(
            id=new_msg_id,
            project_id=new_project.id,
            conversation_id=conversation_id_mapping.get(old_msg.conversation_id) if old_msg.conversation_id else None,
            role=old_msg.role,
            content=old_msg.content,
            original_content=old_msg.original_content,
            is_edited=old_msg.is_edited,
            message_metadata=_rewrite_chat_message_metadata_for_project(
                old_msg.message_metadata,
                block_id_mapping=block_id_mapping,
                mode_id_mapping=mode_id_mapping,
            ),
            parent_message_id=message_id_mapping.get(old_msg.parent_message_id) if old_msg.parent_message_id else None,
        )
        db.add(new_msg)
    
    # ---- 复制内容版本 (ContentVersion) ----
    # 合并 block + field 的 ID 映射用于版本查找
    all_id_mapping = {**block_id_mapping, **field_id_mapping}
    all_old_ids = list(all_id_mapping.keys())
    if all_old_ids:
        old_versions = db.query(ContentVersion).filter(
            ContentVersion.block_id.in_(all_old_ids),
        ).order_by(ContentVersion.version_number).all()
        for old_ver in old_versions:
            new_ver = ContentVersion(
                id=generate_uuid(),
                block_id=all_id_mapping.get(old_ver.block_id, old_ver.block_id),
                version_number=old_ver.version_number,
                content=old_ver.content,
                source=old_ver.source,
                source_detail=old_ver.source_detail,
            )
            db.add(new_ver)
    
    # ---- 复制块操作历史 (BlockHistory) ----
    old_history = db.query(BlockHistory).filter(
        BlockHistory.project_id == old_project.id,
    ).order_by(BlockHistory.created_at).all()
    for old_hist in old_history:
        # 映射快照中的 ID
        import copy
        snap = copy.deepcopy(old_hist.block_snapshot) if old_hist.block_snapshot else {}
        if snap.get("id"):
            snap["id"] = block_id_mapping.get(snap["id"], snap["id"])
        if snap.get("parent_id"):
            snap["parent_id"] = block_id_mapping.get(snap["parent_id"], snap["parent_id"])
        children_snaps = copy.deepcopy(old_hist.children_snapshots) if old_hist.children_snapshots else []
        for cs in children_snaps:
            if cs.get("id"):
                cs["id"] = block_id_mapping.get(cs["id"], cs["id"])
            if cs.get("parent_id"):
                cs["parent_id"] = block_id_mapping.get(cs["parent_id"], cs["parent_id"])
        new_hist = BlockHistory(
            id=generate_uuid(),
            project_id=new_project.id,
            action=old_hist.action,
            block_id=block_id_mapping.get(old_hist.block_id, old_hist.block_id),
            block_snapshot=snap,
            children_snapshots=children_snaps,
            undone=old_hist.undone,
        )
        db.add(new_hist)
    
    # ---- 复制模拟记录 (SimulationRecord) ----
    old_sims = db.query(SimulationRecord).filter(
        SimulationRecord.project_id == old_project.id,
    ).all()
    for old_sim in old_sims:
        new_sim = SimulationRecord(
            id=generate_uuid(),
            project_id=new_project.id,
            simulator_id=old_sim.simulator_id,
            target_field_ids=[all_id_mapping.get(fid, fid) for fid in (old_sim.target_field_ids or [])],
            persona=old_sim.persona.copy() if old_sim.persona else {},
            interaction_log=old_sim.interaction_log.copy() if old_sim.interaction_log else [],
            feedback=old_sim.feedback.copy() if old_sim.feedback else {},
            status=old_sim.status,
        )
        db.add(new_sim)
    
    # ---- 复制评估数据 (EvalRun/EvalTask/EvalTrial) ----
    old_runs = db.query(EvalRun).filter(
        EvalRun.project_id == old_project.id,
    ).all()
    run_id_mapping = {}
    for old_run in old_runs:
        new_run_id = generate_uuid()
        run_id_mapping[old_run.id] = new_run_id
        new_run = EvalRun(
            id=new_run_id,
            project_id=new_project.id,
            name=old_run.name,
            config=old_run.config.copy() if old_run.config else {},
            status=old_run.status,
            summary=old_run.summary,
            overall_score=old_run.overall_score,
            role_scores=old_run.role_scores.copy() if old_run.role_scores else {},
            trial_count=old_run.trial_count,
            content_block_id=block_id_mapping.get(old_run.content_block_id) if old_run.content_block_id else None,
        )
        db.add(new_run)
    
    old_run_ids = list(run_id_mapping.keys())
    task_id_mapping = {}
    if old_run_ids:
        old_tasks = db.query(EvalTask).filter(
            EvalTask.eval_run_id.in_(old_run_ids),
        ).all()
        for old_task in old_tasks:
            new_task_id = generate_uuid()
            task_id_mapping[old_task.id] = new_task_id
            new_task = EvalTask(
                id=new_task_id,
                eval_run_id=run_id_mapping.get(old_task.eval_run_id, old_task.eval_run_id),
                name=old_task.name,
                simulator_type=old_task.simulator_type,
                interaction_mode=old_task.interaction_mode,
                simulator_config=old_task.simulator_config.copy() if old_task.simulator_config else {},
                persona_config=old_task.persona_config.copy() if old_task.persona_config else {},
                target_block_ids=[block_id_mapping.get(bid, bid) for bid in (old_task.target_block_ids or [])],
                grader_config=old_task.grader_config.copy() if old_task.grader_config else {},
                order_index=old_task.order_index,
                status=old_task.status,
            )
            db.add(new_task)
        
        old_trials = db.query(EvalTrial).filter(
            EvalTrial.eval_run_id.in_(old_run_ids),
        ).all()
        for old_trial in old_trials:
            new_trial = EvalTrial(
                id=generate_uuid(),
                eval_run_id=run_id_mapping.get(old_trial.eval_run_id, old_trial.eval_run_id),
                eval_task_id=task_id_mapping.get(old_trial.eval_task_id, old_trial.eval_task_id),
                role=old_trial.role,
                role_config=old_trial.role_config.copy() if old_trial.role_config else {},
                interaction_mode=old_trial.interaction_mode,
                input_block_ids=[block_id_mapping.get(bid, bid) for bid in (old_trial.input_block_ids or [])],
                persona=old_trial.persona.copy() if old_trial.persona else {},
                nodes=old_trial.nodes.copy() if old_trial.nodes else [],
                result=old_trial.result.copy() if old_trial.result else {},
                grader_outputs=old_trial.grader_outputs.copy() if old_trial.grader_outputs else [],
                llm_calls=old_trial.llm_calls.copy() if old_trial.llm_calls else [],
                overall_score=old_trial.overall_score,
                status=old_trial.status,
                error=old_trial.error,
                tokens_in=old_trial.tokens_in,
                tokens_out=old_trial.tokens_out,
                cost=old_trial.cost,
            )
            db.add(new_trial)
    
    # ---- 复制项目记忆 (MemoryItem) ----
    old_memories = db.query(MemoryItem).filter(
        MemoryItem.project_id == old_project.id,
    ).order_by(MemoryItem.created_at).all()
    for old_mem in old_memories:
        new_mem = MemoryItem(
            id=generate_uuid(),
            project_id=new_project.id,
            content=old_mem.content,
            source_mode_id=mode_id_mapping.get(old_mem.source_mode_id, old_mem.source_mode_id),
            source_mode=old_mem.source_mode,
            source_phase=old_mem.source_phase,
            related_blocks=old_mem.related_blocks.copy() if old_mem.related_blocks else [],
        )
        db.add(new_mem)

    # ---- 复制项目角色 ----
    for old_mode in old_modes:
        new_mode = AgentMode(
            id=mode_id_mapping.get(old_mode.id, generate_uuid()),
            project_id=new_project.id,
            name=f"mode_{generate_uuid().replace('-', '')[:12]}",
            stable_key=getattr(old_mode, "stable_key", "") or old_mode.name,
            locale=normalize_locale(getattr(old_mode, "locale", getattr(old_project, "locale", DEFAULT_LOCALE))),
            display_name=old_mode.display_name,
            description=old_mode.description,
            system_prompt=old_mode.system_prompt,
            icon=old_mode.icon,
            is_system=False,
            is_template=False,
            sort_order=old_mode.sort_order,
        )
        db.add(new_mode)
    
    # ---- 复制项目专用评分器 (Grader) ----
    old_graders = db.query(Grader).filter(
        Grader.project_id == old_project.id,
    ).all()
    for old_grader in old_graders:
        new_grader = Grader(
            id=generate_uuid(),
            name=old_grader.name,
            stable_key=getattr(old_grader, "stable_key", "") or old_grader.name,
            locale=normalize_locale(getattr(old_grader, "locale", getattr(old_project, "locale", DEFAULT_LOCALE))),
            grader_type=old_grader.grader_type,
            prompt_template=old_grader.prompt_template,
            dimensions=old_grader.dimensions.copy() if old_grader.dimensions else [],
            scoring_criteria=old_grader.scoring_criteria.copy() if old_grader.scoring_criteria else {},
            is_preset=old_grader.is_preset,
            project_id=new_project.id,
        )
        db.add(new_grader)

    # ---- 复制项目级结构草稿 ----
    old_drafts = db.query(ProjectStructureDraft).filter(
        ProjectStructureDraft.project_id == old_project.id,
    ).all()
    for old_draft in old_drafts:
        new_draft = _clone_structure_draft_for_project(
            old_draft,
            new_project_id=new_project.id,
            block_id_mapping=block_id_mapping,
        )
        db.add(new_draft)
    
    db.commit()
    db.refresh(new_project)
    
    return _project_to_response(new_project)


@router.post("/{project_id}/versions", response_model=ProjectResponse)
def create_new_version(
    project_id: str,
    request: NewVersionRequest,
    db: Session = Depends(get_db),
):
    """
    创建项目新版本

    复制内容包括：
    - 项目本身（版本号 +1）
    - 所有字段 (ProjectField)
    - 所有内容块 (ContentBlock) — 灵活架构的核心数据
    """
    from core.models import ProjectField, ProjectStructureDraft, AgentMode
    from core.models.content_block import ContentBlock

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
        golden_context={},  # P3-2: 已废弃，不再复制
        use_deep_research=old_project.use_deep_research,
        use_flexible_architecture=True,  # P0-1: 统一为 True
        locale=normalize_locale(getattr(old_project, "locale", DEFAULT_LOCALE)),
    )
    
    db.add(new_project)
    db.flush()
    
    # ---- 复制所有字段 (ProjectField) ----
    old_fields = db.query(ProjectField).filter(
        ProjectField.project_id == old_project.id
    ).all()
    
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
            pre_questions=normalize_pre_questions(old_field.pre_questions or []),
            pre_answers=normalize_pre_answers(old_field.pre_answers or {}, old_field.pre_questions or []),
            dependencies=old_field.dependencies.copy() if old_field.dependencies else {"depends_on": [], "dependency_type": "all"},
            constraints=old_field.constraints.copy() if hasattr(old_field, 'constraints') and old_field.constraints else None,
            need_review=old_field.need_review if hasattr(old_field, 'need_review') else True,
            order=old_field.order if hasattr(old_field, 'order') else 0,
            digest=old_field.digest if hasattr(old_field, 'digest') else None,
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

    # ---- 复制所有内容块 (ContentBlock) — 灵活架构的核心 ----
    old_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == old_project.id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).order_by(ContentBlock.depth, ContentBlock.order_index).all()

    block_id_mapping = {}
    for old_block in old_blocks:
        block_id_mapping[old_block.id] = generate_uuid()

    for old_block in old_blocks:
        new_block_id = block_id_mapping[old_block.id]
        new_parent_id = block_id_mapping.get(old_block.parent_id) if old_block.parent_id else None
        new_depends_on = [
            block_id_mapping.get(dep, dep) for dep in (old_block.depends_on or [])
        ]

        new_block = ContentBlock(
            id=new_block_id,
            project_id=new_project.id,
            parent_id=new_parent_id,
            name=old_block.name,
            block_type=old_block.block_type,
            depth=old_block.depth,
            order_index=old_block.order_index,
            content=old_block.content or "",
            status=old_block.status,
            ai_prompt=old_block.ai_prompt or "",
            constraints=old_block.constraints.copy() if old_block.constraints else {},
            pre_questions=normalize_pre_questions(old_block.pre_questions or []),
            pre_answers=normalize_pre_answers(old_block.pre_answers or {}, old_block.pre_questions or []),
            guidance_input=getattr(old_block, "guidance_input", "") or "",
            guidance_output=getattr(old_block, "guidance_output", "") or "",
            depends_on=new_depends_on,
            special_handler=old_block.special_handler,
            need_review=old_block.need_review,
            auto_generate=getattr(old_block, 'auto_generate', False),
            is_collapsed=old_block.is_collapsed,
            model_override=getattr(old_block, 'model_override', None),
            digest=old_block.digest,
        )
        db.add(new_block)

    # ---- 复制项目级结构草稿 ----
    old_drafts = db.query(ProjectStructureDraft).filter(
        ProjectStructureDraft.project_id == old_project.id,
    ).all()
    for old_draft in old_drafts:
        new_draft = _clone_structure_draft_for_project(
            old_draft,
            new_project_id=new_project.id,
            block_id_mapping=block_id_mapping,
        )
        db.add(new_draft)

    # ---- 复制项目角色 ----
    old_modes = db.query(AgentMode).filter(
        AgentMode.project_id == old_project.id,
        AgentMode.is_template.is_(False),
    ).order_by(AgentMode.sort_order, AgentMode.created_at).all()
    for old_mode in old_modes:
        new_mode = AgentMode(
            id=generate_uuid(),
            project_id=new_project.id,
            name=f"mode_{generate_uuid().replace('-', '')[:12]}",
            stable_key=getattr(old_mode, "stable_key", "") or old_mode.name,
            locale=normalize_locale(getattr(old_mode, "locale", getattr(old_project, "locale", DEFAULT_LOCALE))),
            display_name=old_mode.display_name,
            description=old_mode.description,
            system_prompt=old_mode.system_prompt,
            icon=old_mode.icon,
            is_system=False,
            is_template=False,
            sort_order=old_mode.sort_order,
        )
        db.add(new_mode)
    
    db.commit()
    db.refresh(new_project)
    
    return _project_to_response(new_project)


@router.get("/{project_id}/versions", response_model=list[ProjectResponse])
def list_project_versions(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    获取项目的所有版本（沿 parent_version_id 链追溯版本族谱）

    1. 从当前项目向上追溯到根版本（parent_version_id 为空的祖先）
    2. 从根向下收集所有后代版本（BFS）
    3. 按 version 降序返回
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 1. 向上追溯到根版本
    root = project
    visited_up = {root.id}
    while root.parent_version_id:
        parent = db.query(Project).filter(Project.id == root.parent_version_id).first()
        if not parent or parent.id in visited_up:
            break  # 防止循环引用
        visited_up.add(parent.id)
        root = parent

    # 2. 从根向下 BFS 收集所有后代
    all_versions = [root]
    queue = [root.id]
    visited = {root.id}
    while queue:
        pid = queue.pop(0)
        children = db.query(Project).filter(Project.parent_version_id == pid).all()
        for child in children:
            if child.id not in visited:
                visited.add(child.id)
                all_versions.append(child)
                queue.append(child.id)

    all_versions.sort(key=lambda p: p.version, reverse=True)
    return [_project_to_response(p) for p in all_versions]


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
    模拟记录、评估记录（V2）、记忆条目、评分器、生成日志（可选）
    """
    from core.models import (
        ProjectField, ContentBlock, GenerationLog,
        SimulationRecord,
        EvalRun, EvalTask, EvalTrial,
        MemoryItem, ProjectStructureDraft, AgentMode, Conversation,
    )
    from core.models.chat_history import ChatMessage
    from core.models.content_version import ContentVersion
    from core.models.block_history import BlockHistory
    from core.models.grader import Grader

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

    # ContentBlocks（排除已软删除的）
    blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,  # noqa: E711 — 不导出已软删除的块
    ).order_by(ContentBlock.order_index).all()
    blocks_data = [_ser(b) for b in blocks]

    # ProjectFields（旧架构）
    fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
    ).all()
    fields_data = [_ser(f) for f in fields]

    # Conversations + ChatMessages
    conversations = db.query(Conversation).filter(
        Conversation.project_id == project_id,
    ).order_by(
        Conversation.last_message_at.asc(),
        Conversation.created_at.asc(),
    ).all()
    conversations_data = [_ser(c) for c in conversations]

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

    # MemoryItems（项目级记忆）
    from sqlalchemy import or_
    memories = db.query(MemoryItem).filter(
        or_(
            MemoryItem.project_id == project_id,
            MemoryItem.project_id.is_(None),  # 全局记忆也导出，导入时按原 project_id 还原
        )
    ).order_by(MemoryItem.created_at).all()
    memories_data = [_ser(m) for m in memories]

    # AgentModes（项目级角色）
    agent_modes = db.query(AgentMode).filter(
        AgentMode.project_id == project_id,
        AgentMode.is_template.is_(False),
    ).order_by(AgentMode.sort_order, AgentMode.created_at).all()
    agent_modes_data = [_ser(m) for m in agent_modes]

    # Graders（项目专用评分器）
    graders = db.query(Grader).filter(
        Grader.project_id == project_id,
    ).all()
    graders_data = [_ser(g) for g in graders]

    drafts = db.query(ProjectStructureDraft).filter(
        ProjectStructureDraft.project_id == project_id,
    ).all()
    drafts_data = [_ser(d) for d in drafts]

    # GenerationLogs（可选，可能很大）
    logs_data = []
    if include_logs:
        logs = db.query(GenerationLog).filter(
            GenerationLog.project_id == project_id,
        ).order_by(GenerationLog.created_at).all()
        logs_data = [_ser(l) for l in logs]

    return {
        "export_version": "2.0",
        "exported_at": datetime.now().isoformat(),
        "project": project_data,
        "creator_profile": creator_profile_data,
        "content_blocks": blocks_data,
        "project_fields": fields_data,
        "conversations": conversations_data,
        "chat_messages": messages_data,
        "content_versions": versions_data,
        "block_history": history_data,
        "simulation_records": sim_data,
        "eval_runs": eval_runs_data,
        "eval_tasks": tasks_data,
        "eval_trials": trials_data,
        "memory_items": memories_data,
        "agent_modes": agent_modes_data,
        "graders": graders_data,
        "project_structure_drafts": drafts_data,
        "generation_logs": logs_data,
    }


@router.get("/{project_id}/export-markdown")
def export_project_markdown(
    project_id: str,
    db: Session = Depends(get_db),
):
    """导出项目内容树为 Markdown。"""
    from core.content_tree_export_service import export_project_markdown as export_project_markdown_payload

    try:
        return export_project_markdown_payload(db, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/save-as-field-template")
def save_project_as_field_template(
    project_id: str,
    request: SaveAsFieldTemplateRequest,
    db: Session = Depends(get_db),
):
    """将当前项目内容树保存为内容块模板。"""
    from core.content_tree_export_service import build_field_template_from_project
    from core.models import FieldTemplate
    from core.template_schema import normalize_field_template_payload

    try:
        result = build_field_template_from_project(db, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    normalized, errors = normalize_field_template_payload(
        template_name=request.name,
        fields=[],
        root_nodes=result.root_nodes,
    )
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    template = FieldTemplate(
        id=generate_uuid(),
        name=request.name.strip() or "未命名模板",
        stable_key=(request.name.strip() or "未命名模板"),
        locale=normalize_locale(getattr(db.query(Project).filter(Project.id == project_id).first(), "locale", DEFAULT_LOCALE)),
        description=request.description,
        category=request.category or "通用",
        schema_version=normalized["schema_version"],
        fields=normalized["fields"],
        root_nodes=normalized["root_nodes"],
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    return {
        "message": f"已保存为内容块模板「{template.name}」",
        "template": {
            "id": template.id,
            "name": template.name,
            "description": template.description or "",
            "category": template.category or "通用",
            "schema_version": template.schema_version,
            "fields": template.fields or [],
            "root_nodes": template.root_nodes or [],
        },
        "warnings": result.warnings,
        "summary": result.summary,
    }


@router.post("/{project_id}/import-content-tree-json")
def import_content_tree_json(
    project_id: str,
    request: ImportContentTreeJsonRequest,
    db: Session = Depends(get_db),
):
    """从 JSON 文件向当前项目追加导入内容树。"""
    from core.content_tree_import_service import import_content_tree_json as import_content_tree_json_payload

    try:
        return import_content_tree_json_payload(
            db=db,
            project_id=project_id,
            data=request.data,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/import-markdown-files")
def import_markdown_files(
    project_id: str,
    request: ImportMarkdownFilesRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """从多个 Markdown 文件向当前项目追加导入内容树。"""
    from core.content_markdown_import_service import import_markdown_files as import_markdown_files_payload

    # region agent log
    try:
        with open("/Users/rantianshu/Desktop/content-production-system-2/.cursor/debug.log", "a", encoding="utf-8") as debug_file:
            debug_file.write(json.dumps({
                "runId": "markdown-import-initial",
                "hypothesisId": "H4",
                "location": "backend/api/projects.py:1458",
                "message": "backend markdown import route hit",
                "data": {
                    "projectId": project_id,
                    "path": str(http_request.url.path),
                    "method": http_request.method,
                    "fileCount": len(request.files),
                    "importMode": request.import_mode,
                },
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion

    try:
        return import_markdown_files_payload(
            db=db,
            project_id=project_id,
            files=[file.model_dump() for file in request.files],
            import_mode=request.import_mode,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        SimulationRecord,
        EvalRun, EvalTask, EvalTrial,
        MemoryItem, ProjectStructureDraft, AgentMode, Conversation,
    )
    from core.models.chat_history import ChatMessage
    from core.models.content_version import ContentVersion
    from core.models.block_history import BlockHistory
    from core.models.grader import Grader

    data = request.data
    if "project" not in data:
        raise HTTPException(status_code=400, detail="缺少 project 字段")

    def _parse_dt(val) -> Optional[datetime]:
        """解析 ISO datetime 字符串，失败返回 None（让 DB 用 default）"""
        if not val:
            return None
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(str(val))
        except (ValueError, TypeError):
            return None

    def _set_timestamps(obj, data_dict: dict):
        """从导出数据中恢复 created_at / updated_at 时间戳"""
        ca = _parse_dt(data_dict.get("created_at"))
        ua = _parse_dt(data_dict.get("updated_at"))
        if ca:
            obj.created_at = ca
        if ua:
            obj.updated_at = ua

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

    import_locale = DEFAULT_LOCALE

    try:
        # ============ 1. 创作者特质 ============
        cp_data = data.get("creator_profile")
        new_cp_id = None
        if cp_data:
            old_cp_id = cp_data.get("id", "")
            creator_locale = normalize_locale(cp_data.get("locale", DEFAULT_LOCALE))
            if request.match_creator_profile and cp_data.get("name"):
                # 尝试按名称匹配已有特质
                existing = db.query(CreatorProfile).filter(
                    CreatorProfile.name == cp_data["name"],
                    CreatorProfile.locale == creator_locale,
                ).first()
                if existing:
                    new_cp_id = existing.id
                    id_map[old_cp_id] = existing.id

            if not new_cp_id:
                new_cp_id = _new_id(old_cp_id)
                cp = CreatorProfile(
                    id=new_cp_id,
                    name=cp_data.get("name", rt(creator_locale, "project.import.default_creator_name")),
                    stable_key=cp_data.get(
                        "stable_key",
                        cp_data.get("name", rt(creator_locale, "project.import.default_creator_name")),
                    ),
                    locale=creator_locale,
                    description=cp_data.get("description", ""),
                    traits=cp_data.get("traits", {}),
                )
                _set_timestamps(cp, cp_data)
                db.add(cp)

        # ============ 2. 项目 ============
        proj_data = data["project"]
        import_locale = normalize_locale(proj_data.get("locale", DEFAULT_LOCALE))
        old_proj_id = proj_data.get("id", "")
        new_proj_id = _new_id(old_proj_id)

        new_project = Project(
            id=new_proj_id,
            name=proj_data.get("name", rt(import_locale, "project.import.default_project_name")),
            creator_profile_id=new_cp_id,
            locale=import_locale,
            version=proj_data.get("version", 1),
            version_note=proj_data.get("version_note", rt(import_locale, "project.import.default_version_note")),
            current_phase=proj_data.get("current_phase", "intent"),
            phase_order=proj_data.get("phase_order", PROJECT_PHASES.copy()),
            phase_status=proj_data.get("phase_status", {}),
            agent_autonomy=proj_data.get("agent_autonomy", {}),
            golden_context=proj_data.get("golden_context", {}),
            use_deep_research=proj_data.get("use_deep_research", True),
            use_flexible_architecture=True,  # P0-1: 统一为 True
        )
        _set_timestamps(new_project, proj_data)
        db.add(new_project)

        # AgentMode 会被 Conversation / ChatMessage / MemoryItem 引用，先注册 ID 映射。
        for mode_data in data.get("agent_modes", []):
            old_mode_id = mode_data.get("id", "")
            if old_mode_id:
                _new_id(old_mode_id)

        # ============ 3. ContentBlocks ============
        # 过滤掉已软删除的块（安全兜底：正常导出已排除，但旧版导出文件可能包含）
        active_blocks = [
            b for b in data.get("content_blocks", [])
            if not b.get("deleted_at")
        ]
        for b in active_blocks:
            old_id = b.get("id", "")
            _new_id(old_id)  # 预先注册所有 block ID

        for b in active_blocks:
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
                pre_questions=normalize_pre_questions(b.get("pre_questions", [])),
                pre_answers=normalize_pre_answers(b.get("pre_answers", {}), b.get("pre_questions", [])),
                guidance_input=b.get("guidance_input", ""),
                guidance_output=b.get("guidance_output", ""),
                depends_on=_map_list(b.get("depends_on", [])),
                special_handler=b.get("special_handler"),
                need_review=b.get("need_review", True),
                auto_generate=b.get("auto_generate", False),
                is_collapsed=b.get("is_collapsed", False),
                model_override=b.get("model_override"),
                digest=b.get("digest"),
            )
            _set_timestamps(new_block, b)
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
                pre_questions=normalize_pre_questions(f.get("pre_questions", [])),
                pre_answers=normalize_pre_answers(f.get("pre_answers", {}), f.get("pre_questions", [])),
                dependencies=new_deps,
                constraints=f.get("constraints", {}),
                need_review=f.get("need_review", True),
                order=f.get("order", 0),
                digest=f.get("digest"),
            )
            _set_timestamps(new_field, f)
            db.add(new_field)

        # ============ 5. Conversations ============
        conversation_id_mapping: Dict[str, str] = {}
        for conversation_data in data.get("conversations", []):
            old_id = conversation_data.get("id", "")
            if old_id:
                conversation_id_mapping[old_id] = _new_id(old_id)

        for conversation_data in data.get("conversations", []):
            old_id = conversation_data.get("id", "")
            new_conversation = Conversation(
                id=id_map[old_id],
                project_id=new_proj_id,
                mode_id=_map_id(conversation_data.get("mode_id")),
                mode=conversation_data.get("mode", "assistant"),
                title=conversation_data.get("title", ""),
                status=conversation_data.get("status", "active"),
                bootstrap_policy=conversation_data.get("bootstrap_policy", "memory_only"),
                last_message_at=_parse_dt(conversation_data.get("last_message_at")),
                message_count=conversation_data.get("message_count", 0),
            )
            _set_timestamps(new_conversation, conversation_data)
            db.add(new_conversation)

        # ============ 6. ChatMessages ============
        for m in data.get("chat_messages", []):
            old_id = m.get("id", "")
            _new_id(old_id)

        for m in data.get("chat_messages", []):
            old_id = m.get("id", "")
            new_msg = ChatMessage(
                id=id_map[old_id],
                project_id=new_proj_id,
                conversation_id=conversation_id_mapping.get(m.get("conversation_id")) if m.get("conversation_id") else None,
                role=m.get("role", "user"),
                content=m.get("content", ""),
                original_content=m.get("original_content", ""),
                is_edited=m.get("is_edited", False),
                message_metadata=_rewrite_chat_message_metadata_for_project(
                    m.get("message_metadata", {}),
                    block_id_mapping=id_map,
                    mode_id_mapping=id_map,
                ),
                parent_message_id=_map_id(m.get("parent_message_id")),
            )
            _set_timestamps(new_msg, m)
            db.add(new_msg)

        # ============ 7. ContentVersions ============
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
            _set_timestamps(new_ver, v)
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
            _set_timestamps(new_hist, h)
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
            _set_timestamps(new_sim, s)
            db.add(new_sim)

        # ============ 9. EvalRuns + Tasks + Trials ============
        for run in data.get("eval_runs", []):
            old_id = run.get("id", "")
            new_run = EvalRun(
                id=_new_id(old_id),
                project_id=new_proj_id,
                name=run.get("name", rt(import_locale, "project.import.default_eval_run_name")),
                config=run.get("config", {}),
                status=run.get("status", "completed"),
                summary=run.get("summary", ""),
                overall_score=run.get("overall_score"),
                role_scores=run.get("role_scores", {}),
                trial_count=run.get("trial_count", 0),
                content_block_id=_map_id(run.get("content_block_id")),
            )
            _set_timestamps(new_run, run)
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
            _set_timestamps(new_task, task)
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
            _set_timestamps(new_trial, trial)
            db.add(new_trial)

        # ============ 10. MemoryItems ============
        for mem in data.get("memory_items", []):
            old_id = mem.get("id", "")
            # 全局记忆（project_id 为 None）保持全局；项目记忆映射到新项目
            old_mem_proj_id = mem.get("project_id")
            new_mem_proj_id = new_proj_id if old_mem_proj_id else None
            new_mem = MemoryItem(
                id=_new_id(old_id),
                project_id=new_mem_proj_id,
                content=mem.get("content", ""),
                source_mode_id=_map_id(mem.get("source_mode_id")),
                source_mode=mem.get("source_mode", "assistant"),
                source_phase=mem.get("source_phase", ""),
                related_blocks=mem.get("related_blocks", []),
            )
            _set_timestamps(new_mem, mem)
            db.add(new_mem)

        # ============ 10a. AgentModes（项目级角色） ============
        for mode_data in data.get("agent_modes", []):
            old_id = mode_data.get("id", "")
            if old_id:
                _new_id(old_id)
            default_mode_name = rt(import_locale, "project.import.default_mode_display_name")
            new_mode = AgentMode(
                id=_new_id(old_id),
                project_id=new_proj_id,
                name=f"mode_{generate_uuid().replace('-', '')[:12]}",
                stable_key=mode_data.get("stable_key", mode_data.get("name", mode_data.get("display_name", default_mode_name))),
                locale=normalize_locale(mode_data.get("locale", proj_data.get("locale", DEFAULT_LOCALE))),
                display_name=mode_data.get("display_name", default_mode_name),
                description=mode_data.get("description", ""),
                system_prompt=mode_data.get("system_prompt", ""),
                icon=mode_data.get("icon", "🤖"),
                is_system=False,
                is_template=False,
                sort_order=mode_data.get("sort_order", 0),
            )
            _set_timestamps(new_mode, mode_data)
            db.add(new_mode)

        # ============ 10b. ProjectStructureDrafts ============
        for draft_data in data.get("project_structure_drafts", []):
            old_id = draft_data.get("id", "")
            if old_id:
                _new_id(old_id)
            new_draft = _import_structure_draft_for_project(
                draft_data,
                new_project_id=new_proj_id,
                id_map=id_map,
            )
            _set_timestamps(new_draft, draft_data)
            db.add(new_draft)

        # ============ 10c. Graders（项目专用） ============
        for g in data.get("graders", []):
            old_id = g.get("id", "")
            new_grader = Grader(
                id=_new_id(old_id),
                name=g.get("name", ""),
                stable_key=g.get("stable_key", g.get("name", "")),
                locale=normalize_locale(g.get("locale", proj_data.get("locale", DEFAULT_LOCALE))),
                grader_type=g.get("grader_type", "content_only"),
                prompt_template=g.get("prompt_template", ""),
                dimensions=g.get("dimensions", []),
                scoring_criteria=g.get("scoring_criteria", {}),
                is_preset=g.get("is_preset", False),
                project_id=new_proj_id,  # 导入时关联到新项目
            )
            _set_timestamps(new_grader, g)
            db.add(new_grader)

        # ============ 11. GenerationLogs ============
        for log in data.get("generation_logs", []):
            old_id = log.get("id", "")
            new_log = GenerationLog(
                id=_new_id(old_id),
                project_id=new_proj_id,
                field_id=_map_id(log.get("field_id")),
                phase=log.get("phase", ""),
                operation=log.get("operation", ""),
                model=log.get("model", get_model_name()),
                prompt_input=log.get("prompt_input", ""),
                prompt_output=log.get("prompt_output", ""),
                tokens_in=log.get("tokens_in", 0),
                tokens_out=log.get("tokens_out", 0),
                duration_ms=log.get("duration_ms", 0),
                cost=log.get("cost", 0.0),
                status=log.get("status", "success"),
                error_message=log.get("error_message", ""),
            )
            _set_timestamps(new_log, log)
            db.add(new_log)

        if not data.get("agent_modes"):
            ensure_project_agent_modes(db, new_proj_id, locale=new_project.locale)

        db.commit()
        db.refresh(new_project)

        project_response = _project_to_response(new_project).model_dump()
        return {
            "message": rt(import_locale, "project.import.success", name=new_project.name),
            **project_response,
            "project": project_response,
            "stats": {
                "content_blocks": len(active_blocks),
                "project_fields": len(data.get("project_fields", [])),
                "conversations": len(data.get("conversations", [])),
                "chat_messages": len(data.get("chat_messages", [])),
                "content_versions": len(data.get("content_versions", [])),
                "simulation_records": len(data.get("simulation_records", [])),
                "eval_runs": len(data.get("eval_runs", [])),
                "memory_items": len(data.get("memory_items", [])),
                "agent_modes": len(data.get("agent_modes", [])),
                "project_structure_drafts": len(data.get("project_structure_drafts", [])),
                "graders": len(data.get("graders", [])),
                "generation_logs": len(data.get("generation_logs", [])),
            },
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=rt(import_locale, "project.import.failed", message=str(e)))


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


def _replace_content(content: str, pattern, replacement: str, indices: Optional[list] = None) -> tuple:
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
        parent_version_id=project.parent_version_id,
        creator_profile_id=project.creator_profile_id,
        current_phase=project.current_phase,
        phase_order=project.phase_order if project.phase_order is not None else PROJECT_PHASES.copy(),
        phase_status=project.phase_status or {},
        agent_autonomy=project.agent_autonomy or {},
        golden_context=project.golden_context or {},
        use_deep_research=project.use_deep_research if hasattr(project, 'use_deep_research') else True,
        use_flexible_architecture=project.use_flexible_architecture if hasattr(project, 'use_flexible_architecture') else True,  # P0-1: 统一为 True
        locale=normalize_locale(getattr(project, "locale", DEFAULT_LOCALE)),
        created_at=project.created_at.isoformat() if project.created_at else "",
        updated_at=project.updated_at.isoformat() if project.updated_at else "",
    )

