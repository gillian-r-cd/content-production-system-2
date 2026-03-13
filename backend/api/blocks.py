# backend/api/blocks.py
# 功能: 统一内容块 API，支持 CRUD、移动、生成
# 主要路由: /api/blocks
# 数据结构: ContentBlock 的树形操作

"""
内容块 API
统一管理项目中的所有内容块（阶段、字段、方案等）
支持无限层级、拖拽排序、依赖引用
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
from core.localization import DEFAULT_LOCALE, locale_fallback_chain, normalize_locale
from core.llm_compat import normalize_content, resolve_model
from datetime import datetime

logger = logging.getLogger("blocks")
from core.models import (
    ContentBlock,
    ContentVersion,
    BlockHistory,
    Project,
    PhaseTemplate,
    FieldTemplate,
    generate_uuid,
    BLOCK_TYPES,
    BLOCK_STATUS,
)
from core.prompt_engine import PromptEngine, GoldenContext
from core.locale_text import rt
from core.template_schema import instantiate_template_nodes, normalize_field_template_payload
from core.dependency_regeneration_service import (
    DependencyUpdateSummary,
    enqueue_project_auto_trigger,
    finalize_block_content_change,
    schedule_project_auto_trigger,
)
from core.block_generation_service import (
    build_generation_system_prompt,
    ensure_required_pre_questions_answered,
    generate_block_content_sync,
    list_ready_block_ids,
    resolve_dependencies,
    update_parent_status,
)
from core.pre_question_utils import normalize_pre_answers, normalize_pre_questions
from core.project_run_service import run_project_blocks


def _normalize_block_type(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw in {"phase", "group"}:
        return "group"
    if raw in {"field", "proposal"}:
        return "field"
    return "field"


def _save_content_version(block: ContentBlock, source: str, db: Session, source_detail: str = None):
    """保存内容块当前内容为一个历史版本 — 代理到 version_service"""
    from core.version_service import save_content_version
    save_content_version(db, block.id, block.content, source, source_detail)

router = APIRouter(prefix="/api/blocks", tags=["content-blocks"])

# ========== Pydantic 模型 ==========

class BlockCreate(BaseModel):
    """创建内容块请求"""
    project_id: str
    parent_id: Optional[str] = None
    name: str
    block_type: str = "field"
    content: str = ""
    ai_prompt: str = ""
    constraints: Optional[Dict] = None
    depends_on: List[str] = Field(default_factory=list)
    special_handler: Optional[str] = None
    need_review: bool = True
    auto_generate: bool = False  # 是否自动生成（依赖就绪时自动触发）
    model_override: Optional[str] = None  # 模型覆盖（来自模板或用户手动设置）
    order_index: Optional[int] = None
    pre_questions: List[Any] = Field(default_factory=list)  # 生成前提问


class BlockUpdate(BaseModel):
    """更新内容块请求"""
    name: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    ai_prompt: Optional[str] = None
    constraints: Optional[Dict] = None
    pre_questions: Optional[List[Any]] = None
    pre_answers: Optional[Dict] = None
    depends_on: Optional[List[str]] = None
    need_review: Optional[bool] = None
    auto_generate: Optional[bool] = None  # 是否自动生成
    is_collapsed: Optional[bool] = None
    model_override: Optional[str] = None


class BlockMove(BaseModel):
    """移动内容块请求"""
    new_parent_id: Optional[str] = None  # None = 移动到顶级
    new_order_index: int


class BlockResponse(BaseModel):
    """内容块响应"""
    id: str
    project_id: str
    parent_id: Optional[str]
    name: str
    block_type: str
    depth: int
    order_index: int
    content: str
    status: str
    ai_prompt: str
    constraints: Dict
    pre_questions: List[Dict[str, Any]] = Field(default_factory=list)
    pre_answers: Dict[str, str] = Field(default_factory=dict)
    depends_on: List[str]
    special_handler: Optional[str]
    need_review: bool
    auto_generate: bool = False  # 是否自动生成
    needs_regeneration: bool = False
    is_collapsed: bool
    model_override: Optional[str] = None
    children: List["BlockResponse"] = Field(default_factory=list)
    created_at: Optional[str]
    updated_at: Optional[str]
    # 版本提示信息
    version_warning: Optional[str] = None
    affected_blocks: Optional[List[str]] = None

    class Config:
        from_attributes = True


class BlockTreeResponse(BaseModel):
    """项目内容块树响应"""
    project_id: str
    blocks: List[BlockResponse]
    total_count: int


class SaveBlockAsFieldTemplateRequest(BaseModel):
    """保存单个内容块/分组为内容块模板请求"""
    name: str
    description: str = ""
    category: str = "通用"


# ========== 辅助函数 ==========

def _block_to_response(
    block: ContentBlock,
    version_warning: Optional[str] = None,
    affected_blocks: Optional[List[str]] = None,
    include_children: bool = False,
) -> BlockResponse:
    """转换 ContentBlock 为响应模型（排除已删除的子块）"""
    children = []
    if include_children and block.children:
        # 过滤已删除的子块
        active_children = [c for c in block.children if c.deleted_at is None]
        children = [_block_to_response(c, include_children=True) for c in active_children]
    
    normalized_questions = normalize_pre_questions(block.pre_questions or [])
    normalized_answers = normalize_pre_answers(block.pre_answers or {}, normalized_questions)

    return BlockResponse(
        id=block.id,
        project_id=block.project_id,
        parent_id=block.parent_id,
        name=block.name,
        block_type=_normalize_block_type(block.block_type),
        depth=block.depth,
        order_index=block.order_index,
        content=block.content or "",
        status=block.status or "pending",
        ai_prompt=block.ai_prompt or "",
        constraints=block.constraints or {},
        pre_questions=normalized_questions,  # 生成前提问
        pre_answers=normalized_answers,      # 用户回答（按 question.id 存储）
        depends_on=block.depends_on or [],
        special_handler=block.special_handler,
        need_review=block.need_review,
        auto_generate=getattr(block, 'auto_generate', False),
        needs_regeneration=bool(getattr(block, 'needs_regeneration', False)),
        is_collapsed=block.is_collapsed,
        model_override=getattr(block, 'model_override', None),
        children=children,
        created_at=block.created_at.isoformat() if block.created_at else None,
        updated_at=block.updated_at.isoformat() if block.updated_at else None,
        version_warning=version_warning,
        affected_blocks=affected_blocks,
    )


def _calculate_depth(block: ContentBlock, db: Session) -> int:
    """计算内容块的层级深度"""
    if not block.parent_id:
        return 0
    parent = db.query(ContentBlock).filter(ContentBlock.id == block.parent_id).first()
    if not parent:
        return 0
    return parent.depth + 1


def _deprecated_update_parent_status(parent_id: str, db: Session):
    """
    根据子级状态自动更新父级（阶段/组）状态：
    - 所有子级都 completed → 父级 completed
    - 任一子级 in_progress → 父级 in_progress
    - 否则 → 父级 pending
    递归向上更新。
    """
    parent = db.query(ContentBlock).filter(
        ContentBlock.id == parent_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not parent:
        return
    
    children = db.query(ContentBlock).filter(
        ContentBlock.parent_id == parent_id,
        ContentBlock.deleted_at == None,
    ).all()
    
    if not children:
        return
    
    all_completed = all(c.status == "completed" for c in children)
    any_in_progress = any(c.status == "in_progress" for c in children)
    
    if all_completed:
        parent.status = "completed"
    elif any_in_progress:
        parent.status = "in_progress"
    else:
        # 部分完成
        completed_count = sum(1 for c in children if c.status == "completed")
        if completed_count > 0:
            parent.status = "in_progress"
        else:
            parent.status = "pending"
    
    db.commit()
    
    # 递归向上更新
    if parent.parent_id:
        _deprecated_update_parent_status(parent.parent_id, db)


def _get_next_order_index(project_id: str, parent_id: Optional[str], db: Session) -> int:
    """获取下一个排序索引"""
    query = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.parent_id == parent_id,
    )
    max_order = query.count()
    return max_order


def _reorder_siblings(project_id: str, parent_id: Optional[str], db: Session):
    """重新排序同级内容块（排除已删除）"""
    siblings = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.parent_id == parent_id,
        ContentBlock.deleted_at == None,
    ).order_by(ContentBlock.order_index).all()
    
    for idx, sibling in enumerate(siblings):
        sibling.order_index = idx


# ========== API 路由 ==========

@router.get("/project/{project_id}", response_model=BlockTreeResponse)
def get_project_blocks(
    project_id: str,
    db: Session = Depends(get_db),
):
    """获取项目的所有内容块（树形结构，排除已删除）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 自动修复卡住的块：in_progress 但无内容且超过 5 分钟 → 重置为 pending
    # 注意：刚开始生成的块也是 in_progress + 无内容，不能立即重置，否则会干扰正常生成！
    stuck_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,
        ContentBlock.status == "in_progress",
        (ContentBlock.content == None) | (ContentBlock.content == ""),
    ).all()
    if stuck_blocks:
        now = datetime.utcnow()
        for sb in stuck_blocks:
            # 只重置超过 5 分钟的卡住块（给正在生成的块足够时间）
            updated = sb.updated_at or sb.created_at
            if updated and (now - updated).total_seconds() > 300:
                print(f"[RECOVERY] 重置卡住的块: {sb.name} (in_progress → pending, 卡住 {(now - updated).total_seconds():.0f}s)")
                sb.status = "pending"
        db.commit()
    
    # 获取所有顶级块（parent_id = None，排除已删除）
    top_level_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.parent_id == None,
        ContentBlock.deleted_at == None,
    ).order_by(ContentBlock.order_index).all()
    
    # 转换为响应（包含子块）
    blocks = [_block_to_response(b, include_children=True) for b in top_level_blocks]
    
    # 统计总数（排除已删除）
    total = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,
    ).count()
    
    return BlockTreeResponse(
        project_id=project_id,
        blocks=blocks,
        total_count=total,
    )


@router.post("/project/{project_id}/check-auto-triggers")
def check_auto_triggers(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    纯扫描：找出所有满足自动触发条件的块，返回它们的 ID。
    不做任何生成！生成由前端逐个调用 generateStream 完成。
    
    自动触发条件：
    1. auto_generate = True（与 need_review 正交：auto_generate 控制是否自动开始，need_review 控制生成后是否需人工确认）
    2. 要么是空块首次生成，要么是 `needs_regeneration=True` 的已有内容块
    3. 有依赖时，所有依赖都必须 `completed` 且自身不处于待重新生成状态
    4. pre_questions 都已回答
    """
    eligible_ids = list_ready_block_ids(project_id=project_id, db=db, mode="auto_trigger")

    return {
        "eligible_ids": eligible_ids,
    }


class ProjectRunRequest(BaseModel):
    mode: str = "auto_trigger"
    max_concurrency: int = 4


@router.post("/project/{project_id}/run")
async def run_project(
    project_id: str,
    request: ProjectRunRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    return await run_project_blocks(
        project_id=project_id,
        mode=request.mode,
        max_concurrency=request.max_concurrency,
    )


@router.get("/{block_id}", response_model=BlockResponse)
def get_block(
    block_id: str,
    include_children: bool = False,
    db: Session = Depends(get_db),
):
    """获取单个内容块（排除已删除）"""
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    return _block_to_response(block, include_children=include_children)


@router.get("/{block_id}/export-markdown")
def export_block_markdown(
    block_id: str,
    db: Session = Depends(get_db),
):
    """导出指定内容块子树为 Markdown。"""
    from core.content_tree_export_service import export_block_markdown as export_block_markdown_payload

    try:
        return export_block_markdown_payload(db, block_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{block_id}/export-json")
def export_block_json(
    block_id: str,
    db: Session = Depends(get_db),
):
    """导出指定内容块子树为范围 JSON。"""
    from core.content_tree_export_service import export_block_bundle

    try:
        return export_block_bundle(db, block_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{block_id}/save-as-field-template")
def save_block_as_field_template(
    block_id: str,
    request: SaveBlockAsFieldTemplateRequest,
    db: Session = Depends(get_db),
):
    """将指定内容块子树保存为内容块模板。"""
    from core.content_tree_export_service import build_field_template_from_block
    from core.template_schema import normalize_field_template_payload

    try:
        result = build_field_template_from_block(db, block_id)
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


@router.post("/", response_model=BlockResponse)
def create_block(
    data: BlockCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """创建内容块"""
    # 验证项目存在
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 验证父块存在（如果指定）
    depth = 0
    if data.parent_id:
        parent = db.query(ContentBlock).filter(ContentBlock.id == data.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="父内容块不存在")
        depth = parent.depth + 1
    
    # 验证块类型
    normalized_block_type = _normalize_block_type(data.block_type)
    if normalized_block_type not in BLOCK_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的块类型: {data.block_type}")
    
    # 计算排序索引
    order_index = data.order_index
    if order_index is None:
        order_index = _get_next_order_index(data.project_id, data.parent_id, db)
    
    # 有预置内容时自动推导状态：need_review → in_progress(待确认), 否则 completed
    if data.content:
        initial_status = "in_progress" if data.need_review else "completed"
    else:
        initial_status = "pending"

    block = ContentBlock(
        id=generate_uuid(),
        project_id=data.project_id,
        parent_id=data.parent_id,
        name=data.name,
        block_type=normalized_block_type,
        depth=depth,
        order_index=order_index,
        content=data.content,
        status=initial_status,
        ai_prompt=data.ai_prompt,
        constraints=data.constraints or {},
        depends_on=data.depends_on,
        special_handler=data.special_handler,
        need_review=data.need_review,
        auto_generate=data.auto_generate,
        model_override=data.model_override,
        pre_questions=normalize_pre_questions(data.pre_questions),  # 保存生成前提问
    )
    
    db.add(block)
    db.commit()
    db.refresh(block)

    if block.block_type == "field" and bool(getattr(block, "auto_generate", False)):
        schedule_project_auto_trigger(block.project_id, background_tasks=background_tasks)
    
    return _block_to_response(block)


@router.put("/{block_id}", response_model=BlockResponse)
def update_block(
    block_id: str,
    data: BlockUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """更新内容块"""
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")

    project = db.query(Project).filter(Project.id == block.project_id).first()
    project_locale = normalize_locale(getattr(project, "locale", DEFAULT_LOCALE))
    
    # 记录内容是否发生变化（用于版本警告）
    content_changed = (
        data.content is not None
        and data.content != (block.content or "")
    )
    pre_questions_changed = data.pre_questions is not None
    pre_answers_changed = data.pre_answers is not None
    depends_on_changed = data.depends_on is not None and data.depends_on != (block.depends_on or [])
    need_review_changed = data.need_review is not None and data.need_review != bool(getattr(block, "need_review", True))
    auto_generate_changed = data.auto_generate is not None and data.auto_generate != bool(getattr(block, "auto_generate", False))
    status_changed = data.status is not None and data.status != (block.status or "")
    
    # ===== 内容变更前保存旧版本 =====
    if content_changed:
        _save_content_version(block, "manual", db, source_detail="用户手动编辑")
    
    # 更新字段
    from sqlalchemy.orm.attributes import flag_modified
    
    if data.name is not None:
        block.name = data.name
    if data.content is not None:
        block.content = data.content
        # ===== 保存内容时的状态逻辑 =====
        # 如果没有显式传 status，根据 need_review 判断：
        # - need_review=True: 有内容 → in_progress（等用户确认），无内容 → pending
        # - need_review=False: 有内容 → completed，无内容 → pending
        if data.status is None:  # 没有显式传 status 时才自动设置
            if block.content and block.content.strip():
                block.status = "completed" if not block.need_review else "in_progress"
            else:
                block.status = "pending"
    if data.status is not None:
        if data.status not in BLOCK_STATUS:
            raise HTTPException(status_code=400, detail=f"无效的状态: {data.status}")
        block.status = data.status
    if data.ai_prompt is not None:
        block.ai_prompt = data.ai_prompt
    if data.constraints is not None:
        block.constraints = data.constraints
        flag_modified(block, "constraints")
    if data.pre_questions is not None:
        block.pre_questions = normalize_pre_questions(data.pre_questions)
        flag_modified(block, "pre_questions")
        current_answers = normalize_pre_answers(block.pre_answers or {}, block.pre_questions)
        block.pre_answers = normalize_pre_answers(current_answers, block.pre_questions)
        flag_modified(block, "pre_answers")
    if data.pre_answers is not None:
        block.pre_answers = normalize_pre_answers(data.pre_answers or {}, block.pre_questions or [])
        flag_modified(block, "pre_answers")
    if data.depends_on is not None:
        block.depends_on = data.depends_on
        flag_modified(block, "depends_on")
    if data.need_review is not None:
        block.need_review = data.need_review
    if data.auto_generate is not None:
        block.auto_generate = data.auto_generate
    if data.is_collapsed is not None:
        block.is_collapsed = data.is_collapsed
    if data.model_override is not None:
        # 空字符串表示清除覆盖（恢复使用全局默认）
        block.model_override = data.model_override if data.model_override else None

    dependency_update = DependencyUpdateSummary()
    if content_changed and block.block_type == "field":
        dependency_update = finalize_block_content_change(block=block, db=db)

    db.commit()
    db.refresh(block)
    
    # ===== 关键修复：更新父级（阶段/组）的状态 =====
    # 当字段状态变化时，检查父级的所有子级是否全部完成
    if block.parent_id and block.block_type == "field":
        update_parent_status(block.parent_id, db)
    
    version_warning = None
    affected_blocks = None

    if dependency_update.manual_attention_block_names:
        version_warning = rt(
            project_locale,
            "block.dependency_update.manual_attention",
            name=block.name,
            affected_names="、".join(dependency_update.manual_attention_block_names),
        )
        affected_blocks = dependency_update.manual_attention_block_names

    should_schedule_auto_trigger = any([
        content_changed,
        pre_questions_changed,
        pre_answers_changed,
        depends_on_changed,
        need_review_changed,
        auto_generate_changed,
        status_changed,
    ])
    if should_schedule_auto_trigger and block.block_type == "field":
        schedule_project_auto_trigger(block.project_id, background_tasks=background_tasks)

    return _block_to_response(block, version_warning, affected_blocks)


@router.post("/{block_id}/confirm", response_model=BlockResponse)
def confirm_block(
    block_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    用户手动确认内容块 → 状态变为 completed
    只有用户点确认按钮才走这里，AI 生成后不会自动调用
    """
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")

    project = db.query(Project).filter(Project.id == block.project_id).first()
    project_locale = normalize_locale(getattr(project, "locale", DEFAULT_LOCALE))
    
    if not block.content or not block.content.strip():
        raise HTTPException(status_code=400, detail="内容为空，无法确认")

    if bool(getattr(block, "needs_regeneration", False)):
        raise HTTPException(
            status_code=409,
            detail=rt(project_locale, "block.confirm.stale", name=block.name),
        )
    
    block.status = "completed"
    db.commit()
    db.refresh(block)
    
    # 更新父级状态
    if block.parent_id:
        update_parent_status(block.parent_id, db)

    schedule_project_auto_trigger(block.project_id, background_tasks=background_tasks)
    
    return _block_to_response(block)


@router.delete("/{block_id}")
def delete_block(
    block_id: str,
    db: Session = Depends(get_db),
):
    """
    软删除内容块（级联软删除子块）
    保存历史记录，支持撤回
    """
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    project_id = block.project_id
    parent_id = block.parent_id
    
    # 1. 保存块快照
    block_snapshot = block.to_tree_dict()
    # 移除 children 避免重复
    block_snapshot.pop("children", None)
    
    # 2. 收集并保存所有子块快照
    def collect_descendants(parent: ContentBlock):
        """递归收集所有后代"""
        descendants = []
        children = db.query(ContentBlock).filter(
            ContentBlock.parent_id == parent.id,
            ContentBlock.deleted_at == None,
        ).all()
        for child in children:
            snapshot = child.to_tree_dict()
            snapshot.pop("children", None)
            descendants.append(snapshot)
            descendants.extend(collect_descendants(child))
        return descendants
    
    children_snapshots = collect_descendants(block)
    
    # 3. 创建历史记录
    history = BlockHistory(
        id=generate_uuid(),
        project_id=project_id,
        action="delete",
        block_id=block.id,
        block_snapshot=block_snapshot,
        children_snapshots=children_snapshots,
        undone=False,
    )
    db.add(history)
    
    # 4. 软删除主块和所有子块
    now = datetime.utcnow()
    block.deleted_at = now
    
    def soft_delete_children(parent_id: str):
        children = db.query(ContentBlock).filter(
            ContentBlock.parent_id == parent_id,
            ContentBlock.deleted_at == None,
        ).all()
        for child in children:
            child.deleted_at = now
            soft_delete_children(child.id)
    
    soft_delete_children(block_id)
    
    # 5. 重新排序同级
    _reorder_siblings(project_id, parent_id, db)
    
    db.commit()
    
    return {
        "message": "删除成功",
        "history_id": history.id,
        "can_undo": True,
    }


@router.post("/{block_id}/duplicate", response_model=BlockResponse)
def duplicate_block(
    block_id: str,
    db: Session = Depends(get_db),
):
    """
    深拷贝内容块（含所有子块）
    
    - 递归复制目标块及其全部后代
    - 为所有新块生成新 ID
    - 内部 depends_on 引用自动重映射到新 ID
    - 副本插入到原块同级的下一个位置
    """
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    # 收集原始块及所有后代，建立 old_id → new_id 映射
    id_mapping: Dict[str, str] = {}
    
    def _collect_tree(node: ContentBlock) -> list:
        """递归收集节点及所有后代（BFS/DFS 均可，这里用 DFS）"""
        nodes = [node]
        children = db.query(ContentBlock).filter(
            ContentBlock.parent_id == node.id,
            ContentBlock.deleted_at == None,
        ).order_by(ContentBlock.order_index).all()
        for child in children:
            nodes.extend(_collect_tree(child))
        return nodes
    
    all_nodes = _collect_tree(block)
    
    # 为所有节点生成新 ID
    for node in all_nodes:
        id_mapping[node.id] = generate_uuid()
    
    # 创建副本
    new_blocks = []
    for node in all_nodes:
        new_id = id_mapping[node.id]
        
        # 重映射 parent_id
        if node.id == block.id:
            # 根节点：parent 不变（和原块同级）
            new_parent_id = block.parent_id
        else:
            new_parent_id = id_mapping.get(node.parent_id, node.parent_id)
        
        # 重映射 depends_on 中的内部引用
        new_depends_on = []
        for dep_id in (node.depends_on or []):
            new_depends_on.append(id_mapping.get(dep_id, dep_id))
        
        new_block = ContentBlock(
            id=new_id,
            project_id=node.project_id,
            parent_id=new_parent_id,
            name=f"{node.name} (副本)" if node.id == block.id else node.name,
            block_type=_normalize_block_type(node.block_type),
            depth=node.depth,
            order_index=node.order_index if node.id != block.id else (block.order_index + 1),
            content=node.content or "",
            status="pending",  # 副本从 pending 开始
            ai_prompt=node.ai_prompt or "",
            constraints=node.constraints.copy() if node.constraints else {},
            pre_questions=normalize_pre_questions(node.pre_questions or []),
            pre_answers=normalize_pre_answers(node.pre_answers or {}, node.pre_questions or []),
            depends_on=new_depends_on,
            special_handler=node.special_handler,
            need_review=node.need_review,
            auto_generate=getattr(node, 'auto_generate', False),
            needs_regeneration=False,
            is_collapsed=node.is_collapsed,
            model_override=getattr(node, 'model_override', None),
        )
        new_blocks.append(new_block)
        db.add(new_block)
    
    # 重新排序同级（根副本插入后需要调整）
    _reorder_siblings(block.project_id, block.parent_id, db)
    
    db.commit()
    
    # 返回根副本
    root_copy = new_blocks[0]
    db.refresh(root_copy)
    return _block_to_response(root_copy, include_children=True)


@router.post("/{block_id}/move", response_model=BlockResponse)
def move_block(
    block_id: str,
    data: BlockMove,
    db: Session = Depends(get_db),
):
    """移动内容块（改变父级或排序）"""
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    old_parent_id = block.parent_id
    
    # 验证新父块（如果指定）
    new_depth = 0
    if data.new_parent_id:
        new_parent = db.query(ContentBlock).filter(
            ContentBlock.id == data.new_parent_id
        ).first()
        if not new_parent:
            raise HTTPException(status_code=404, detail="目标父内容块不存在")
        
        # 防止移动到自己的子孙节点下
        ancestors = []
        current = new_parent
        while current:
            if current.id == block_id:
                raise HTTPException(status_code=400, detail="不能移动到自己的子节点下")
            ancestors.append(current.id)
            current = current.parent
        
        new_depth = new_parent.depth + 1
    
    # 更新父级和深度
    block.parent_id = data.new_parent_id
    block.depth = new_depth
    block.order_index = data.new_order_index
    
    # 递归更新子块深度
    def update_children_depth(parent_block: ContentBlock):
        for child in parent_block.children:
            child.depth = parent_block.depth + 1
            update_children_depth(child)
    
    update_children_depth(block)
    
    # 重新排序旧位置的同级
    if old_parent_id != data.new_parent_id:
        _reorder_siblings(block.project_id, old_parent_id, db)
    
    # 调整新位置的同级排序（排除已删除）
    siblings = db.query(ContentBlock).filter(
        ContentBlock.project_id == block.project_id,
        ContentBlock.parent_id == data.new_parent_id,
        ContentBlock.id != block_id,
        ContentBlock.deleted_at == None,
    ).order_by(ContentBlock.order_index).all()
    
    # 插入到指定位置
    for idx, sibling in enumerate(siblings):
        if idx >= data.new_order_index:
            sibling.order_index = idx + 1
        else:
            sibling.order_index = idx
    
    db.commit()
    db.refresh(block)
    
    return _block_to_response(block)


def _deprecated_resolve_dependencies(block: ContentBlock, db: Session) -> tuple:
    """
    智能解析依赖关系，处理以下场景：
    1. depends_on 中的 ID 指向已删除的块 → 按名称在同项目中查找替代
    2. depends_on 中的 ID 不存在 → 按名称查找
    3. 自动修复 block.depends_on（将过期 ID 更新为正确 ID）
    
    Returns:
        (resolved_deps: List[ContentBlock], dependency_content: str, error_msg: Optional[str])
    """
    if not block.depends_on:
        return [], "", None
    
    # 获取项目中所有活跃的块（未删除）
    active_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == block.project_id,
        ContentBlock.deleted_at == None,
    ).all()
    active_by_id = {b.id: b for b in active_blocks}
    active_by_name = {}
    for b in active_blocks:
        if b.id != block.id:  # 排除自己
            active_by_name[b.name] = b
    
    resolved_deps = []
    updated_depends_on = []
    needs_update = False
    
    for dep_id in block.depends_on:
        # 1. 先尝试用 ID 在活跃块中查找
        dep_block = active_by_id.get(dep_id)
        if dep_block:
            resolved_deps.append(dep_block)
            updated_depends_on.append(dep_id)
            continue
        
        # 2. ID 未找到（已删除或不存在），尝试查找该 ID 对应的旧块获取名称
        old_block = db.query(ContentBlock).filter(
            ContentBlock.id == dep_id,
        ).first()
        
        dep_name = old_block.name if old_block else dep_id  # dep_id 本身可能就是名称
        
        # 3. 按名称在活跃块中查找替代
        replacement = active_by_name.get(dep_name)
        if replacement:
            resolved_deps.append(replacement)
            updated_depends_on.append(replacement.id)
            needs_update = True
            print(f"[依赖修复] {block.name}: 依赖 '{dep_name}' 的 ID 已更新 {dep_id} -> {replacement.id}")
        else:
            # 彻底找不到，跳过（不再把无效 ID 留在 depends_on 中）
            needs_update = True
            print(f"[依赖修复] {block.name}: 依赖 ID '{dep_id}' (名称: {dep_name}) 已不存在，已移除")
    
    # 4. 自动修复 depends_on
    if needs_update:
        block.depends_on = updated_depends_on
        db.flush()
        print(f"[依赖修复] {block.name}: depends_on 已自动修复为 {updated_depends_on}")
    
    # 5. 检查依赖内容
    incomplete = [d for d in resolved_deps if not d.content or not d.content.strip()]
    if incomplete:
        return resolved_deps, "", f"依赖内容为空: {', '.join([d.name for d in incomplete])}"
    
    # 6. 构建依赖内容文本
    context_parts = []
    for dep in resolved_deps:
        if dep.content:
            context_parts.append(f"## {dep.name}\n{dep.content}")
    dependency_content = "\n\n".join(context_parts)
    
    return resolved_deps, dependency_content, None


@router.post("/{block_id}/generate")
async def generate_block_content(
    block_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """生成内容块内容"""
    result = await generate_block_content_sync(block_id=block_id, db=db)
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()
    if block and block.block_type == "field":
        schedule_project_auto_trigger(block.project_id, background_tasks=background_tasks)
    return result


@router.post("/{block_id}/generate/stream")
async def generate_block_content_stream(
    block_id: str,
    db: Session = Depends(get_db),
):
    """流式生成内容块内容"""
    import json
    import time
    import traceback
    from fastapi.responses import StreamingResponse
    from core.config import validate_llm_config
    
    # ===== 前置校验：API Key 是否已正确配置 =====
    config_error = validate_llm_config()
    if config_error:
        raise HTTPException(status_code=422, detail=config_error)
    
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    # 如果是 eval 特殊字段，重定向到 eval API
    if block.special_handler and block.special_handler.startswith("eval_"):
        from api.eval import generate_eval_for_block
        result = await generate_eval_for_block(block_id, db)
        # 将结果包装为 SSE 格式
        async def eval_stream():
            content = result.get("content", "")
            yield f"data: {json.dumps({'chunk': content}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True, 'content': content}, ensure_ascii=False)}\n\n"
        return StreamingResponse(eval_stream(), media_type="text/event-stream")
    
    project = db.query(Project).filter(Project.id == block.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    project_locale = normalize_locale(getattr(project, "locale", DEFAULT_LOCALE))

    ensure_required_pre_questions_answered(block, locale=project_locale)
    
    # 智能解析依赖（自动修复过期 ID、按名称查找替代）
    resolved_deps, dependency_content, dep_error = resolve_dependencies(
        block,
        db,
        locale=project_locale,
    )
    if dep_error:
        raise HTTPException(status_code=400, detail=dep_error)
    
    system_prompt = build_generation_system_prompt(
        block=block,
        project=project,
        dependency_content=dependency_content,
    )
    
    from core.llm import get_chat_model
    from langchain_core.messages import SystemMessage, HumanMessage
    
    effective_model = resolve_model(model_override=getattr(block, 'model_override', None))
    chat_model = get_chat_model(model=effective_model)
    
    # ===== 流式生成前保存旧版本 =====
    was_stale = bool(getattr(block, "needs_regeneration", False))
    _save_content_version(block, "ai_regenerate", db, source_detail="重新生成前的版本")
    
    block.status = "in_progress"
    block.needs_regeneration = False
    db.commit()
    
    start_time = time.time()
    
    async def stream_generator():
        content_parts = []
        stream_completed = False  # 标记流式生成是否完整完成
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=rt(project_locale, "block.generate.human", name=block.name)),
            ]
            
            from core.llm import astream_with_retry
            async for chunk in astream_with_retry(chat_model, messages):
                piece = normalize_content(chunk.content)
                if piece:
                    content_parts.append(piece)
                    data = json.dumps({"chunk": piece}, ensure_ascii=False)
                    yield f"data: {data}\n\n"
            
            # AI 流完整结束
            stream_completed = True
            
            # 保存完整内容
            full_content = "".join(content_parts)
            block.content = full_content
            # 关键逻辑：need_review=True 时等待用户确认，否则自动完成
            block.status = "completed" if not block.need_review else "in_progress"
            finalize_block_content_change(block=block, db=db)
            
            # 计算耗时和tokens（估算）
            duration_ms = int((time.time() - start_time) * 1000)
            tokens_in = len(system_prompt) // 4
            tokens_out = len(full_content) // 4
            
            # 创建日志记录
            from core.models import GenerationLog, generate_uuid
            gen_log = GenerationLog(
                id=generate_uuid(),
                project_id=block.project_id,
                field_id=block.id,
                phase=block.parent_id or "content_block",
                operation=f"block_generate_stream_{block.name}",
                model=effective_model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                duration_ms=duration_ms,
                prompt_input=system_prompt,
                prompt_output=full_content,
                cost=GenerationLog.calculate_cost(effective_model, tokens_in, tokens_out),
                status="success",
            )
            db.add(gen_log)
            db.commit()
            
            # 更新父级状态（递归向上）
            if block.parent_id:
                update_parent_status(block.parent_id, db)

            asyncio.create_task(asyncio.to_thread(enqueue_project_auto_trigger, block.project_id))
            
            # 发送完成事件
            done_data = json.dumps({
                "done": True,
                "block_id": block.id,
                "content": full_content,
                "status": block.status,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            }, ensure_ascii=False)
            yield f"data: {done_data}\n\n"
            
        except Exception as e:
            block.status = "failed"
            block.needs_regeneration = was_stale
            db.commit()
            # 详细日志：记录完整异常信息便于排查
            logger.error(
                "[STREAM] 生成失败: block=%s, error_type=%s, error=%s\n%s",
                block.name, type(e).__name__, e, traceback.format_exc(),
            )
            from core.llm import parse_llm_error
            friendly_msg = parse_llm_error(e)
            error_data = json.dumps({"error": friendly_msg}, ensure_ascii=False)
            yield f"data: {error_data}\n\n"
            
        except BaseException:
            # ===== 关键修复 =====
            # 当用户导航离开时，ASGI 取消 generator，抛出 GeneratorExit（继承 BaseException）
            # 必须在这里保存已积累的内容，否则内容会丢失！
            if content_parts and not stream_completed:
                try:
                    from core.database import get_session_maker
                    SessionLocal = get_session_maker()
                    save_db = SessionLocal()
                    try:
                        save_block = save_db.query(ContentBlock).filter(
                            ContentBlock.id == block_id
                        ).first()
                        if save_block:
                            partial_content = "".join(content_parts)
                            save_block.content = partial_content
                            save_block.status = "completed"
                            
                            # 记录日志
                            from core.models import GenerationLog, generate_uuid
                            duration_ms = int((time.time() - start_time) * 1000)
                            gen_log = GenerationLog(
                                id=generate_uuid(),
                                project_id=save_block.project_id,
                                field_id=save_block.id,
                                phase=save_block.parent_id or "content_block",
                                operation=f"block_generate_stream_interrupted_{save_block.name}",
                                model=effective_model,
                                tokens_in=len(system_prompt) // 4,
                                tokens_out=len(partial_content) // 4,
                                duration_ms=duration_ms,
                                prompt_input=system_prompt,
                                prompt_output=partial_content,
                                cost=0,
                                status="interrupted",
                            )
                            save_db.add(gen_log)
                            save_db.commit()
                            print(f"[STREAM] [WARN] 客户端断开，已保存 {len(partial_content)} 字符的部分内容")
                    finally:
                        save_db.close()
                except Exception as save_err:
                    print(f"[STREAM] [FAIL] 保存中断内容失败: {save_err}")
            raise  # 重新抛出 BaseException，让 ASGI 正常处理
    
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/project/{project_id}/apply-template")
def apply_template_to_project(
    project_id: str,
    template_id: str,
    parent_id: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """
    将模板树实例化到项目内容树中。

    - `PhaseTemplate` 先转换为统一模板树，再实例化为 `ContentBlock`
    - `FieldTemplate` 优先使用 `root_nodes`，旧 `fields[]` 自动兼容升级
    - 支持实例化到现有项目任意父节点下（`parent_id` 可选）
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    parent_block = None
    base_depth = 0
    if parent_id:
        parent_block = db.query(ContentBlock).filter(
            ContentBlock.id == parent_id,
            ContentBlock.project_id == project_id,
            ContentBlock.deleted_at == None,
        ).first()
        if not parent_block:
            raise HTTPException(status_code=404, detail="目标父内容块不存在")
        base_depth = parent_block.depth + 1

    start_order_index = _get_next_order_index(project_id, parent_id, db)
    project_locale = normalize_locale(getattr(project, "locale", DEFAULT_LOCALE))

    template = db.query(PhaseTemplate).filter(PhaseTemplate.id == template_id).first()
    template_name = ""
    if template:
        template_locale = normalize_locale(getattr(template, "locale", DEFAULT_LOCALE))
        if template_locale != project_locale and getattr(template, "stable_key", ""):
            localized_template = db.query(PhaseTemplate).filter(
                PhaseTemplate.stable_key == template.stable_key,
                PhaseTemplate.locale == project_locale,
            ).first()
            if localized_template:
                template = localized_template
        root_nodes = template.to_template_nodes()
        template_name = template.name
    else:
        field_template = db.query(FieldTemplate).filter(FieldTemplate.id == template_id).first()
        if not field_template:
            raise HTTPException(status_code=404, detail="模板不存在")
        template_locale = normalize_locale(getattr(field_template, "locale", DEFAULT_LOCALE))
        if template_locale != project_locale and getattr(field_template, "stable_key", ""):
            localized_template = db.query(FieldTemplate).filter(
                FieldTemplate.stable_key == field_template.stable_key,
                FieldTemplate.locale == project_locale,
            ).first()
            if localized_template:
                field_template = localized_template
        normalized, errors = normalize_field_template_payload(
            template_name=field_template.name,
            fields=field_template.fields or [],
            root_nodes=getattr(field_template, "root_nodes", None) or [],
        )
        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        root_nodes = normalized["root_nodes"]
        template_name = field_template.name

    blocks_to_create = instantiate_template_nodes(
        project_id=project_id,
        root_nodes=root_nodes,
        parent_id=parent_id,
        base_depth=base_depth,
        start_order_index=start_order_index,
    )

    for block_data in blocks_to_create:
        db.add(ContentBlock(**block_data))

    db.commit()
    schedule_project_auto_trigger(project_id, background_tasks=background_tasks)
    
    return {
        "message": rt(project_locale, "phase_template.apply.success", name=template_name),
        "blocks_created": len(blocks_to_create),
    }


@router.post("/project/{project_id}/migrate")
def migrate_project_to_blocks(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    将传统项目的 project_fields 迁移到 content_blocks 架构
    
    这会：
    1. 为每个阶段创建一个 group 类型的 ContentBlock
    2. 将每个 ProjectField 转换为 field 类型的 ContentBlock
    3. 保持原有的依赖关系
    """
    from core.models import ProjectField
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 如果已经是灵活架构，无需迁移
    if project.use_flexible_architecture:
        raise HTTPException(
            status_code=400,
            detail="项目已使用灵活架构，无需迁移"
        )
    
    # 清理可能存在的旧内容块（重新迁移）
    existing_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id
    ).all()
    
    if existing_blocks:
        for block in existing_blocks:
            db.delete(block)
        db.flush()  # 确保删除生效
    
    # 获取所有传统字段
    fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id
    ).all()
    
    # 阶段到特殊处理器的映射
    phase_handler_map = {
        "intent": "intent",
        "research": "research",
        "produce_inner": "produce_inner",
        "produce_outer": "produce_outer",
        "simulate": "simulate",
        "evaluate": "evaluate",
    }
    
    # 阶段显示名称映射
    display_names = {
        "intent": "意图分析",
        "research": "消费者调研",
        "design_inner": "内涵设计",
        "produce_inner": "内涵生产",
        "design_outer": "外延设计",
        "produce_outer": "外延生产",
        "simulate": "消费者模拟",
        "evaluate": "评估",
    }
    
    # 创建阶段块
    phase_blocks = {}
    for idx, phase_name in enumerate(project.phase_order):
        phase_id = generate_uuid()
        
        phase_block = ContentBlock(
            id=phase_id,
            project_id=project.id,
            parent_id=None,
            name=display_names.get(phase_name, phase_name),
            block_type="group",
            depth=0,
            order_index=idx,
            status=project.phase_status.get(phase_name, "pending"),
            special_handler=phase_handler_map.get(phase_name),
            need_review=False,  # 自主权设置已移除，phase block 默认不需要人工确认
        )
        db.add(phase_block)
        phase_blocks[phase_name] = phase_id
    
    db.flush()  # 确保阶段块有 ID
    
    # 字段 ID 映射（旧 ProjectField.id -> 新 ContentBlock.id）
    field_id_map = {}
    
    # 按阶段分组统计字段顺序
    phase_field_counters = {phase: 0 for phase in phase_blocks.keys()}
    
    # 创建字段块
    for field in fields:
        parent_phase_id = phase_blocks.get(field.phase)
        if not parent_phase_id:
            continue
        
        new_id = generate_uuid()
        field_id_map[field.id] = new_id
        
        # 获取当前阶段的字段顺序
        order_idx = phase_field_counters.get(field.phase, 0)
        phase_field_counters[field.phase] = order_idx + 1
        
        field_block = ContentBlock(
            id=new_id,
            project_id=project.id,
            parent_id=parent_phase_id,
            name=field.name,
            block_type="field",
            depth=1,
            order_index=order_idx,
            content=field.content or "",
            status=field.status or "pending",
            ai_prompt=field.ai_prompt or "",
            constraints=field.constraints or {},
            pre_questions=normalize_pre_questions(getattr(field, "pre_questions", []) or []),
            pre_answers=normalize_pre_answers(
                getattr(field, "pre_answers", {}) or {},
                getattr(field, "pre_questions", []) or [],
            ),
            depends_on=[],  # 稍后更新
            need_review=getattr(field, 'need_review', True),
        )
        db.add(field_block)
    
    db.flush()
    
    # 更新依赖关系
    for field in fields:
        new_id = field_id_map.get(field.id)
        if not new_id:
            continue
        
        old_depends = []
        if field.dependencies and isinstance(field.dependencies, dict):
            old_depends = field.dependencies.get("depends_on", [])
        
        new_depends = [field_id_map[old_id] for old_id in old_depends if old_id in field_id_map]
        
        if new_depends:
            block = db.query(ContentBlock).filter(ContentBlock.id == new_id).first()
            if block:
                block.depends_on = new_depends
    
    # 更新项目为灵活架构
    project.use_flexible_architecture = True
    
    db.commit()
    
    return {
        "message": "迁移成功",
        "phases_created": len(phase_blocks),
        "fields_migrated": len(field_id_map),
    }


# ========== 撤回功能 ==========

@router.post("/undo/{history_id}")
def undo_delete(
    history_id: str,
    db: Session = Depends(get_db),
):
    """
    撤回删除操作
    恢复被软删除的内容块及其子块
    """
    history = db.query(BlockHistory).filter(
        BlockHistory.id == history_id,
        BlockHistory.undone == False,
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="历史记录不存在或已撤回")
    
    if history.action != "delete":
        raise HTTPException(status_code=400, detail="仅支持撤回删除操作")
    
    # 恢复主块
    block = db.query(ContentBlock).filter(
        ContentBlock.id == history.block_id
    ).first()
    
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    if block.deleted_at is None:
        raise HTTPException(status_code=400, detail="内容块未被删除")
    
    # 恢复主块
    block.deleted_at = None
    
    # 恢复所有子块
    for child_snapshot in history.children_snapshots:
        child_id = child_snapshot.get("id")
        if child_id:
            child = db.query(ContentBlock).filter(
                ContentBlock.id == child_id
            ).first()
            if child:
                child.deleted_at = None
    
    # 标记历史已撤回
    history.undone = True
    
    # 重新排序同级（插入恢复的块）
    _reorder_siblings(block.project_id, block.parent_id, db)
    
    db.commit()
    
    return {
        "message": "撤回成功",
        "restored_block_id": block.id,
        "restored_children_count": len(history.children_snapshots),
    }


@router.get("/project/{project_id}/history")
def get_project_undo_history(
    project_id: str,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """
    获取项目的可撤回操作历史
    """
    histories = db.query(BlockHistory).filter(
        BlockHistory.project_id == project_id,
        BlockHistory.undone == False,
        BlockHistory.action == "delete",
    ).order_by(BlockHistory.created_at.desc()).limit(limit).all()
    
    return {
        "project_id": project_id,
        "undo_available": [
            {
                "history_id": h.id,
                "action": h.action,
                "block_name": h.block_snapshot.get("name", "未知"),
                "block_type": h.block_snapshot.get("block_type", "未知"),
                "children_count": len(h.children_snapshots),
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in histories
        ],
    }


# ============== AI 提示词生成 ==============


class GeneratePromptRequest(BaseModel):
    """AI 生成提示词请求"""
    purpose: str = Field(..., description="用户描述的字段目的/需求")
    field_name: str = Field(default="", description="字段名称（可选，用于给 AI 更多上下文）")
    project_id: str = Field(default="", description="项目 ID（可选，用于获取项目上下文）")


@router.post("/generate-prompt")
async def generate_ai_prompt(
    request: GeneratePromptRequest,
    db: Session = Depends(get_db),
):
    """
    AI 生成提示词：根据用户描述的目的，生成高质量的字段提示词
    
    - 从后台系统提示词中读取「AI生成提示词」模板
    - 调用 LLM 生成提示词
    - 记录日志
    """
    from core.models import SystemPrompt, GenerationLog
    from core.llm import get_chat_model
    from langchain_core.messages import SystemMessage, HumanMessage
    
    # 提示词生成使用轻量模型（无 block 级覆盖，走全局默认 mini）
    effective_model = resolve_model(use_mini=True)
    chat_model = get_chat_model(model=effective_model)
    
    locale = DEFAULT_LOCALE
    project = None
    if request.project_id:
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if project:
            locale = normalize_locale(getattr(project, "locale", DEFAULT_LOCALE))

    # 1. 从后台获取「AI生成提示词」的系统提示词
    prompt_template = None
    for candidate in locale_fallback_chain(locale):
        prompt_template = db.query(SystemPrompt).filter(
            SystemPrompt.phase == "utility",
            SystemPrompt.locale == candidate,
        ).first()
        if prompt_template:
            break
    
    if prompt_template:
        system_content = prompt_template.content
    else:
        # 降级：使用默认提示词
        system_content = rt(locale, "blocks.generate_prompt.fallback_system")
    
    # 2. 构建用户消息
    field_line = f"字段名称: {request.field_name}\n" if request.field_name else ""
    project_line = f"\n项目名称: {project.name}" if project else ""
    user_msg = rt(
        locale,
        "blocks.generate_prompt.user",
        field_line=field_line,
        purpose=request.purpose,
        project_line=project_line,
    )
    
    # 3. 调用 LLM
    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_msg),
    ]
    
    try:
        from core.llm import ainvoke_with_retry, parse_llm_error
        response = await ainvoke_with_retry(chat_model, messages)
    except Exception as llm_err:
        raise HTTPException(status_code=502, detail=parse_llm_error(llm_err))
    
    generated_prompt = normalize_content(response.content).strip()
    
    # 从 AIMessage.usage_metadata 提取 token 用量（langchain 标准字段）
    usage = getattr(response, "usage_metadata", None) or {}
    tokens_in = usage.get("input_tokens", 0) or 0
    tokens_out = usage.get("output_tokens", 0) or 0
    
    # 4. 记录日志
    gen_log = GenerationLog(
        id=generate_uuid(),
        project_id=request.project_id or "global",
        phase="utility",
        operation="generate_ai_prompt",
        model=effective_model,
        prompt_input=f"[System]\n{system_content}\n\n[User]\n{user_msg}",
        prompt_output=generated_prompt,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        duration_ms=0,
        cost=GenerationLog.calculate_cost(effective_model, tokens_in, tokens_out),
        status="success",
    )
    db.add(gen_log)
    db.commit()
    
    return {
        "prompt": generated_prompt,
        "model": effective_model,
        "tokens_used": tokens_in + tokens_out,
    }
