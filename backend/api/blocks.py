# backend/api/blocks.py
# 功能: 统一内容块 API，支持 CRUD、移动、生成
# 主要路由: /api/blocks
# 数据结构: ContentBlock 的树形操作

"""
内容块 API
统一管理项目中的所有内容块（阶段、字段、方案等）
支持无限层级、拖拽排序、依赖引用
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
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


def _save_content_version(block: ContentBlock, source: str, db: Session, source_detail: str = None):
    """保存内容块当前内容为一个历史版本 — 代理到 version_service"""
    from core.version_service import save_content_version
    save_content_version(db, block.id, block.content, source, source_detail)

router = APIRouter(prefix="/api/blocks", tags=["content-blocks"])


# 所有内容块生成时注入的 Markdown 格式指令（系统级约束，非用户配置）
# 前端统一使用 ReactMarkdown 渲染，因此输出格式固定为 Markdown。
MARKDOWN_FORMAT_INSTRUCTIONS = """# 输出格式（必须遵守）
使用 Markdown 格式输出。
- 标题使用 # ## ### 格式
- 列表使用 - 或 1. 格式
- 重点内容使用 **粗体** 或 *斜体*
- 表格必须包含表头分隔行（如 | --- | --- |），且每行列数与表头一致
- 若一个单元格需要多条内容，用 <br> 换行，不要增加 | 列分隔符"""


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
    order_index: Optional[int] = None
    pre_questions: List[str] = Field(default_factory=list)  # 生成前提问


class BlockUpdate(BaseModel):
    """更新内容块请求"""
    name: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    ai_prompt: Optional[str] = None
    constraints: Optional[Dict] = None
    pre_questions: Optional[List[str]] = None
    pre_answers: Optional[Dict] = None
    depends_on: Optional[List[str]] = None
    need_review: Optional[bool] = None
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
    pre_questions: List[str] = Field(default_factory=list)
    pre_answers: Dict = Field(default_factory=dict)
    depends_on: List[str]
    special_handler: Optional[str]
    need_review: bool
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
    
    return BlockResponse(
        id=block.id,
        project_id=block.project_id,
        parent_id=block.parent_id,
        name=block.name,
        block_type=block.block_type,
        depth=block.depth,
        order_index=block.order_index,
        content=block.content or "",
        status=block.status or "pending",
        ai_prompt=block.ai_prompt or "",
        constraints=block.constraints or {},
        pre_questions=block.pre_questions or [],  # 生成前提问
        pre_answers=block.pre_answers or {},      # 用户回答
        depends_on=block.depends_on or [],
        special_handler=block.special_handler,
        need_review=block.need_review,
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


def _update_parent_status(parent_id: str, db: Session):
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
        _update_parent_status(parent.parent_id, db)


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
    1. need_review = False
    2. status 是 pending/failed（或 in_progress 但无内容）
    3. 没有已有内容
    4. 有依赖且所有依赖都有内容
    5. pre_questions 都已回答
    """
    all_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,
    ).all()
    blocks_by_id = {b.id: b for b in all_blocks}
    
    eligible_ids = []
    for block in all_blocks:
        # need_review=True 的块需要人工确认，不自动触发
        if block.need_review:
            continue
        # 只触发 pending 和 failed 的块；in_progress 的块说明正在生成中，不重复触发
        if block.status not in ("pending", "failed"):
            continue
        if block.content and block.content.strip():
            continue
        deps = block.depends_on or []
        if not deps:
            continue
        # 核心改动：依赖检查同时要求「有内容」且「status=completed」
        # 这样 need_review=True 的依赖块必须经过人工确认才算 ready
        all_deps_ready = True
        for dep_id in deps:
            dep = blocks_by_id.get(dep_id)
            if not dep or not dep.content or not dep.content.strip():
                all_deps_ready = False
                break
            if dep.status != "completed":
                all_deps_ready = False
                break
        if not all_deps_ready:
            continue
        if block.pre_questions and len(block.pre_questions) > 0:
            answers = block.pre_answers or {}
            if any(not answers.get(q, "").strip() for q in block.pre_questions):
                continue
        eligible_ids.append(block.id)
    
    return {
        "eligible_ids": eligible_ids,
    }


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


@router.post("/", response_model=BlockResponse)
def create_block(
    data: BlockCreate,
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
    if data.block_type not in BLOCK_TYPES:
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
        block_type=data.block_type,
        depth=depth,
        order_index=order_index,
        content=data.content,
        status=initial_status,
        ai_prompt=data.ai_prompt,
        constraints=data.constraints or {},
        depends_on=data.depends_on,
        special_handler=data.special_handler,
        need_review=data.need_review,
        pre_questions=data.pre_questions,  # 保存生成前提问
    )
    
    db.add(block)
    db.commit()
    db.refresh(block)
    
    return _block_to_response(block)


@router.put("/{block_id}", response_model=BlockResponse)
def update_block(
    block_id: str,
    data: BlockUpdate,
    db: Session = Depends(get_db),
):
    """更新内容块"""
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    # 记录内容是否发生变化（用于版本警告）
    content_changed = (
        data.content is not None
        and data.content != (block.content or "")
    )
    
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
        block.pre_questions = data.pre_questions
        flag_modified(block, "pre_questions")
    if data.pre_answers is not None:
        block.pre_answers = data.pre_answers
        flag_modified(block, "pre_answers")
    if data.depends_on is not None:
        block.depends_on = data.depends_on
        flag_modified(block, "depends_on")
    if data.need_review is not None:
        block.need_review = data.need_review
    if data.is_collapsed is not None:
        block.is_collapsed = data.is_collapsed
    if data.model_override is not None:
        # 空字符串表示清除覆盖（恢复使用全局默认）
        block.model_override = data.model_override if data.model_override else None
    
    db.commit()
    db.refresh(block)
    
    # ===== 关键修复：更新父级（阶段/组）的状态 =====
    # 当字段状态变化时，检查父级的所有子级是否全部完成
    if block.parent_id and block.block_type == "field":
        _update_parent_status(block.parent_id, db)
    
    # ===== 版本警告：检查是否有下游已完成内容依赖于此块 =====
    version_warning = None
    affected_blocks = None
    
    if content_changed and block.block_type == "field":
        # 找到同项目所有未删除的 field 块
        all_blocks = db.query(ContentBlock).filter(
            ContentBlock.project_id == block.project_id,
            ContentBlock.id != block.id,
            ContentBlock.deleted_at == None,
            ContentBlock.block_type == "field",
            ContentBlock.status.in_(["completed", "in_progress"]),
        ).all()
        
        affected = []
        for other in all_blocks:
            deps = other.depends_on or []
            if block.id in deps and other.content and other.content.strip():
                affected.append(other.name)
        
        if affected:
            version_warning = (
                f"您修改了「{block.name}」的内容，以下内容块依赖于它且已有内容，"
                f"可能需要重新生成或创建新版本：{', '.join(affected)}"
            )
            affected_blocks = affected
    
    return _block_to_response(block, version_warning, affected_blocks)


@router.post("/{block_id}/confirm", response_model=BlockResponse)
def confirm_block(
    block_id: str,
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
    
    if not block.content or not block.content.strip():
        raise HTTPException(status_code=400, detail="内容为空，无法确认")
    
    block.status = "completed"
    db.commit()
    db.refresh(block)
    
    # 更新父级状态
    if block.parent_id:
        _update_parent_status(block.parent_id, db)
    
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
            block_type=node.block_type,
            depth=node.depth,
            order_index=node.order_index if node.id != block.id else (block.order_index + 1),
            content=node.content or "",
            status="pending",  # 副本从 pending 开始
            ai_prompt=node.ai_prompt or "",
            constraints=node.constraints.copy() if node.constraints else {},
            pre_questions=node.pre_questions.copy() if node.pre_questions else [],
            pre_answers=node.pre_answers.copy() if node.pre_answers else {},
            depends_on=new_depends_on,
            special_handler=node.special_handler,
            need_review=node.need_review,
            is_collapsed=node.is_collapsed,
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


def _resolve_dependencies(block: ContentBlock, db: Session) -> tuple:
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
    db: Session = Depends(get_db),
):
    """生成内容块内容"""
    block = db.query(ContentBlock).filter(
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="内容块不存在")
    
    project = db.query(Project).filter(Project.id == block.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 智能解析依赖（自动修复过期 ID、按名称查找替代）
    resolved_deps, dependency_content, dep_error = _resolve_dependencies(block, db)
    if dep_error:
        raise HTTPException(status_code=400, detail=dep_error)
    
    # 获取创作者特质（从关系获取，转换为提示词格式）
    creator_profile_text = ""
    if project.creator_profile:
        creator_profile_text = project.creator_profile.to_prompt_context()
    
    # 构建 Golden Context（只包含 creator_profile）
    gc = GoldenContext(
        creator_profile=creator_profile_text,
    )
    
    # 构建预提问答案文本
    pre_answers_text = ""
    if block.pre_answers:
        answers = [f"- {q}: {a}" for q, a in block.pre_answers.items() if a]
        if answers:
            pre_answers_text = "\n---\n# 用户补充信息（生成前提问的回答）\n" + "\n".join(answers)
    
    ai_prompt = block.ai_prompt or "请生成内容。"
    
    # 检查 ai_prompt 是否包含占位符（新格式：所见即所得）
    has_placeholders = (
        "{creator_profile}" in ai_prompt
        or "{dependencies}" in ai_prompt
    )
    
    if has_placeholders:
        # 新格式：ai_prompt 就是完整模板，直接替换占位符
        system_prompt = ai_prompt
        system_prompt = system_prompt.replace("{creator_profile}", creator_profile_text or "（暂无创作者特质）")
        system_prompt = system_prompt.replace("{dependencies}", dependency_content or "（无依赖内容）")
        system_prompt += pre_answers_text
        system_prompt += f"\n\n---\n{MARKDOWN_FORMAT_INSTRUCTIONS}"
    else:
        # 标准格式：引擎拼接各段
        system_prompt = f"""{gc.to_prompt()}

---

# 当前任务
{ai_prompt}
{pre_answers_text}

{f'---{chr(10)}# 参考内容{chr(10)}{dependency_content}' if dependency_content else ''}

---
{MARKDOWN_FORMAT_INSTRUCTIONS}
"""
    
    # 调用 AI（按 block.model_override → AgentSettings → .env 覆盖链选模型）
    from core.llm import get_chat_model
    from langchain_core.messages import SystemMessage, HumanMessage
    
    effective_model = resolve_model(model_override=getattr(block, 'model_override', None))
    chat_model = get_chat_model(model=effective_model)
    
    # ===== 生成前保存旧版本 =====
    _save_content_version(block, "ai_regenerate", db, source_detail="重新生成前的版本")
    
    block.status = "in_progress"
    db.commit()
    
    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请生成「{block.name}」的内容。"),
        ]
        response = await chat_model.ainvoke(messages)
        
        gen_content = normalize_content(response.content)

        block.content = gen_content
        # 关键逻辑：need_review=True 时，生成完成后状态为 in_progress（等待用户确认）
        # need_review=False 时，才自动设为 completed
        block.status = "completed" if not block.need_review else "in_progress"
        
        # 创建 GenerationLog 记录
        from core.models import GenerationLog, generate_uuid
        usage = getattr(response, "usage_metadata", {}) or {}
        gen_log = GenerationLog(
            id=generate_uuid(),
            project_id=block.project_id,
            field_id=block.id,
            phase=block.parent_id or "content_block",
            operation=f"block_generate_{block.name}",
            model=effective_model,
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
            duration_ms=0,
            prompt_input=system_prompt,
            prompt_output=gen_content,
            cost=GenerationLog.calculate_cost(effective_model, usage.get("input_tokens", 0), usage.get("output_tokens", 0)),
            status="success",
        )
        db.add(gen_log)
        db.commit()
        
        # 更新父级状态（递归向上）
        if block.parent_id:
            _update_parent_status(block.parent_id, db)
        
        # 注意：不在后端触发下游块，由前端调用 check-auto-triggers 自行处理
        
        return {
            "block_id": block.id,
            "content": gen_content,
            "status": block.status,
            "tokens_in": usage.get("input_tokens", 0),
            "tokens_out": usage.get("output_tokens", 0),
            "cost": 0.0,
        }
        
    except Exception as e:
        block.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{block_id}/generate/stream")
async def generate_block_content_stream(
    block_id: str,
    db: Session = Depends(get_db),
):
    """流式生成内容块内容"""
    import json
    import time
    from fastapi.responses import StreamingResponse
    
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
    
    # 智能解析依赖（自动修复过期 ID、按名称查找替代）
    resolved_deps, dependency_content, dep_error = _resolve_dependencies(block, db)
    if dep_error:
        raise HTTPException(status_code=400, detail=dep_error)
    
    # 获取创作者特质
    creator_profile_text = ""
    if project.creator_profile:
        creator_profile_text = project.creator_profile.to_prompt_context()
    
    gc = GoldenContext(creator_profile=creator_profile_text)
    
    # 构建预提问答案文本
    pre_answers_text = ""
    if block.pre_answers:
        answers = [f"- {q}: {a}" for q, a in block.pre_answers.items() if a]
        if answers:
            pre_answers_text = f"---\n# 用户补充信息（生成前提问的回答）\n" + "\n".join(answers)
    
    system_prompt = f"""{gc.to_prompt()}

---

# 当前任务
{block.ai_prompt or '请生成内容。'}

{pre_answers_text}

{f'---{chr(10)}# 参考内容{chr(10)}{dependency_content}' if dependency_content else ''}

---
{MARKDOWN_FORMAT_INSTRUCTIONS}
"""
    
    from core.llm import get_chat_model
    from langchain_core.messages import SystemMessage, HumanMessage
    
    effective_model = resolve_model(model_override=getattr(block, 'model_override', None))
    chat_model = get_chat_model(model=effective_model)
    
    # ===== 流式生成前保存旧版本 =====
    _save_content_version(block, "ai_regenerate", db, source_detail="重新生成前的版本")
    
    block.status = "in_progress"
    db.commit()
    
    start_time = time.time()
    
    async def stream_generator():
        content_parts = []
        stream_completed = False  # 标记流式生成是否完整完成
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"请生成「{block.name}」的内容。"),
            ]
            
            async for chunk in chat_model.astream(messages):
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
                _update_parent_status(block.parent_id, db)
            
            # 注意：不在后端触发下游块生成，由前端调用 check-auto-triggers 后自行触发
            
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
            db.commit()
            error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
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
    db: Session = Depends(get_db),
):
    """
    将模板应用到项目。
    
    优先查找 PhaseTemplate（有完整的组→内容块层级结构）。
    若未找到，降级查找 FieldTemplate（扁平字段列表），
    自动创建一个默认组并将字段放入其中。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 检查项目是否已有内容块
    existing = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id
    ).count()
    
    if existing > 0:
        raise HTTPException(
            status_code=400,
            detail="项目已有内容块，请先清空或创建新项目"
        )
    
    # 优先查找 PhaseTemplate
    template = db.query(PhaseTemplate).filter(PhaseTemplate.id == template_id).first()
    template_name = ""
    
    if template:
        blocks_to_create = template.apply_to_project(project_id)
        template_name = template.name
    else:
        # 降级查找 FieldTemplate（扁平字段列表 → 生成一个默认组 + 字段块）
        field_template = db.query(FieldTemplate).filter(FieldTemplate.id == template_id).first()
        if not field_template:
            raise HTTPException(status_code=404, detail="模板不存在")
        
        template_name = field_template.name
        blocks_to_create = _field_template_to_blocks(field_template, project_id)
    
    # 第一遍：创建所有块，记录 name→id 映射
    name_to_id = {}
    created_blocks = []
    for block_data in blocks_to_create:
        # 暂存 depends_on（可能是名称列表），创建时先设为空
        raw_depends = block_data.pop("depends_on", [])
        block = ContentBlock(**block_data)
        block._raw_depends = raw_depends  # 临时属性
        db.add(block)
        created_blocks.append(block)
        name_to_id[block.name] = block.id
    
    db.flush()  # 确保所有块都有 ID
    
    # 第二遍：将 depends_on 的名称解析为 ID
    for block in created_blocks:
        raw = getattr(block, "_raw_depends", [])
        if raw:
            resolved = []
            for dep_name in raw:
                dep_id = name_to_id.get(dep_name)
                if dep_id:
                    resolved.append(dep_id)
                # 如果名称找不到，忽略（不阻塞创建）
            block.depends_on = resolved
    
    db.commit()
    
    return {
        "message": f"已应用模板「{template_name}」",
        "blocks_created": len(blocks_to_create),
    }


def _field_template_to_blocks(field_template: "FieldTemplate", project_id: str) -> list:
    """
    将扁平的 FieldTemplate 转换为 ContentBlock 创建参数列表。
    自动创建一个以模板名命名的组，字段作为子块。
    """
    blocks = []
    phase_id = generate_uuid()
    
    # 创建一个默认组
    blocks.append({
        "id": phase_id,
        "project_id": project_id,
        "parent_id": None,
        "name": field_template.name,
        "block_type": "phase",
        "depth": 0,
        "order_index": 0,
        "status": "pending",
    })
    
    # 创建字段块
    for idx, field in enumerate(field_template.fields or []):
        template_content = field.get("content", "")
        block_data = {
            "id": generate_uuid(),
            "project_id": project_id,
            "parent_id": phase_id,
            "name": field.get("name", f"内容块 {idx + 1}"),
            "block_type": field.get("type", "field"),
            "depth": 1,
            "order_index": idx,
            "ai_prompt": field.get("ai_prompt", ""),
            "content": template_content,
            "pre_questions": field.get("pre_questions", []),
            "depends_on": field.get("depends_on", []),
            "constraints": field.get("constraints", {}),
            "need_review": field.get("need_review", True),
            "status": (
                ("in_progress" if field.get("need_review", True) else "completed")
                if template_content else "pending"
            ),
        }
        # 传递 special_handler（评估模板等依赖此字段）
        if field.get("special_handler"):
            block_data["special_handler"] = field["special_handler"]
        blocks.append(block_data)
    
    return blocks


@router.post("/project/{project_id}/migrate")
def migrate_project_to_blocks(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    将传统项目的 project_fields 迁移到 content_blocks 架构
    
    这会：
    1. 为每个阶段创建一个 phase 类型的 ContentBlock
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
            block_type="phase",
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
    
    # 1. 从后台获取「AI生成提示词」的系统提示词
    prompt_template = db.query(SystemPrompt).filter(
        SystemPrompt.phase == "utility",
        SystemPrompt.name == "AI生成提示词",
    ).first()
    
    if prompt_template:
        system_content = prompt_template.content
    else:
        # 降级：使用默认提示词
        system_content = """你是一个专业的提示词工程师。用户会告诉你某个字段的目的和需求，你需要为该字段生成一段高质量的 AI 提示词。

生成的提示词应该：
1. 明确指出 AI 的角色定位
2. 清晰描述要生成的内容是什么
3. 给出具体的输出要求（格式、结构、风格等）
4. 如果有依赖上下文，提醒 AI 参考这些信息
5. 包含质量约束

直接输出提示词内容，不需要任何解释或前缀。"""
    
    # 2. 构建用户消息
    user_msg = f"请为以下字段生成 AI 提示词：\n\n"
    if request.field_name:
        user_msg += f"字段名称: {request.field_name}\n"
    user_msg += f"字段目的: {request.purpose}"
    
    # 如果有项目上下文，加入
    if request.project_id:
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if project:
            user_msg += f"\n项目名称: {project.name}"
    
    # 3. 调用 LLM
    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_msg),
    ]
    
    try:
        response = await chat_model.ainvoke(messages)
    except Exception as llm_err:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {str(llm_err)[:200]}")
    
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
