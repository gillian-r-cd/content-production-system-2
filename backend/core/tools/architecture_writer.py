# backend/core/tools/architecture_writer.py
# 功能: 项目架构修改工具，让 Agent 能够修改项目结构
# 主要函数: modify_architecture(), add_phase(), remove_phase(), add_field(), remove_field(), move_field()
# 数据结构: ArchitectureOperation, OperationResult

"""
项目架构修改工具

提供 Agent 修改项目结构的能力：
1. 添加/删除阶段
2. 重排阶段顺序
3. 添加/删除/移动字段
4. 更新字段属性
"""

from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid

from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Project, FieldTemplate, PhaseTemplate
from core.models.content_block import ContentBlock
from core.phase_config import PHASE_DISPLAY_NAMES, PHASE_ALIAS
from core.template_schema import instantiate_template_nodes, normalize_field_template_payload


class ArchitectureOperation(str, Enum):
    """架构操作类型"""
    ADD_PHASE = "add_phase"
    REMOVE_PHASE = "remove_phase"
    REORDER_PHASES = "reorder_phases"
    ADD_FIELD = "add_field"
    REMOVE_FIELD = "remove_field"
    MOVE_FIELD = "move_field"
    UPDATE_FIELD = "update_field"
    ADD_NODE = "add_node"
    REMOVE_NODE = "remove_node"
    MOVE_NODE = "move_node"
    UPDATE_NODE_META = "update_node_meta"
    INSTANTIATE_TEMPLATE = "instantiate_template"


@dataclass
class OperationResult:
    """操作结果"""
    success: bool
    message: str
    operation: str
    affected_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None


def _find_active_block_by_id(project_id: str, block_id: Optional[str], db: Session) -> Optional[ContentBlock]:
    """按 ID 查找未删除内容块。"""
    if not block_id:
        return None
    return db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.id == block_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()


def _find_top_level_phase_block(
    project_id: str,
    db: Session,
    phase_name: Optional[str] = None,
    phase_block_id: Optional[str] = None,
) -> Optional[ContentBlock]:
    """优先按 phase_block_id 查找顶层阶段块，失败后再按名称/别名查找。"""
    block = _find_active_block_by_id(project_id, phase_block_id, db)
    if block and block.block_type == "phase" and block.parent_id is None:
        return block
    if not phase_name:
        return None
    display_name = PHASE_DISPLAY_NAMES.get(phase_name, phase_name)
    return db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.block_type == "phase",
        ContentBlock.parent_id == None,  # noqa: E711
        ContentBlock.name.in_([display_name, phase_name]),
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()


def _find_field_block(
    project_id: str,
    db: Session,
    field_name: Optional[str] = None,
    field_id: Optional[str] = None,
) -> Optional[ContentBlock]:
    """优先按 field_id 查找字段块，失败后按名称兜底。"""
    block = _find_active_block_by_id(project_id, field_id, db)
    if block and block.block_type == "field":
        return block
    if not field_name:
        return None
    return db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.name == field_name,
        ContentBlock.block_type == "field",
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()


def _find_node(
    project_id: str,
    db: Session,
    node_id: Optional[str] = None,
    node_name: Optional[str] = None,
) -> Optional[ContentBlock]:
    """优先按 ID 查找任意未删除节点，失败后按名称兜底。"""
    block = _find_active_block_by_id(project_id, node_id, db)
    if block:
        return block
    if not node_name:
        return None
    return db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.name == node_name,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()


def _resequence_children(project_id: str, parent_id: Optional[str], db: Session) -> None:
    """重排同级节点的 order_index。"""
    siblings = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.parent_id == parent_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).order_by(ContentBlock.order_index, ContentBlock.created_at, ContentBlock.id).all()
    for index, sibling in enumerate(siblings):
        sibling.order_index = index


def _insert_block_at_order(
    project_id: str,
    parent_id: Optional[str],
    block: ContentBlock,
    target_index: Optional[int],
    db: Session,
) -> None:
    """将 block 插入到指定同级位置并重排。"""
    siblings = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.parent_id == parent_id,
        ContentBlock.deleted_at == None,  # noqa: E711
        ContentBlock.id != block.id,
    ).order_by(ContentBlock.order_index, ContentBlock.created_at, ContentBlock.id).all()
    insert_at = len(siblings) if target_index is None else max(0, min(target_index, len(siblings)))
    siblings.insert(insert_at, block)
    for index, sibling in enumerate(siblings):
        sibling.order_index = index


def _refresh_descendant_depths(block: ContentBlock, db: Session) -> None:
    """递归刷新后代 depth，保持树结构一致。"""
    children = db.query(ContentBlock).filter(
        ContentBlock.parent_id == block.id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).all()
    for child in children:
        child.depth = block.depth + 1
        _refresh_descendant_depths(child, db)


def _resolve_phase_code(phase: str, phase_order: List[str]) -> Optional[str]:
    """将 phase 参数（可能是内部 code、display_name 或 alias）解析为内部 code。
    
    解析优先级:
    1. 完全匹配 phase_order 中的 code（如 "research"）
    2. PHASE_ALIAS 匹配（display_name→code，如 "消费者调研"→"research"）
    3. PHASE_DISPLAY_NAMES 反查（如 display_name 值 → code）
    
    返回 None 表示无法解析。
    """
    # 1. 已经是有效的内部 code
    if phase in phase_order:
        return phase
    # 2. PHASE_ALIAS（包含 display_name→code 和用户自定义别名→code）
    resolved = PHASE_ALIAS.get(phase)
    if resolved and resolved in phase_order:
        return resolved
    # 3. PHASE_DISPLAY_NAMES 反查（遍历，兜底）
    for code, display in PHASE_DISPLAY_NAMES.items():
        if display == phase and code in phase_order:
            return code
    return None


# ============== 阶段操作 ==============

def add_phase(
    project_id: str,
    phase_name: str,
    display_name: str,
    position: Optional[int] = None,
    db: Optional[Session] = None,
) -> OperationResult:
    """
    添加新阶段
    
    Args:
        project_id: 项目ID
        phase_name: 阶段代码名（如 custom_phase_1）
        display_name: 显示名称（如 "自定义阶段"）
        position: 插入位置（默认末尾）
        db: 数据库会话
    
    Returns:
        OperationResult
    """
    if db is None:
        db = next(get_db())
    
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return OperationResult(
                success=False,
                message="项目不存在",
                operation="add_phase",
                error="Project not found"
            )
        
        # 检查阶段是否已存在
        if phase_name in project.phase_order:
            return OperationResult(
                success=False,
                message=f"阶段 '{phase_name}' 已存在",
                operation="add_phase",
                error="Phase already exists"
            )
        
        # 更新 phase_order
        new_order = list(project.phase_order)
        if position is None or position >= len(new_order):
            new_order.append(phase_name)
        else:
            new_order.insert(position, phase_name)
        
        project.phase_order = new_order
        
        # 初始化阶段状态
        new_status = dict(project.phase_status or {})
        new_status[phase_name] = "pending"
        project.phase_status = new_status
        
        # 创建阶段对应的 ContentBlock
        block = ContentBlock(
            id=str(uuid.uuid4()),
            project_id=project_id,
            parent_id=None,
            name=display_name,
            block_type="phase",
            depth=0,
            order_index=position if position else len(new_order) - 1,
            status="pending",
        )
        db.add(block)
        
        db.commit()
        
        return OperationResult(
            success=True,
            message=f"已添加阶段「{display_name}」",
            operation="add_phase",
            affected_ids=[block.id]
        )
        
    except Exception as e:
        db.rollback()
        return OperationResult(
            success=False,
            message=f"添加阶段失败: {str(e)}",
            operation="add_phase",
            error=str(e)
        )


def remove_phase(
    project_id: str,
    phase_name: str,
    db: Optional[Session] = None,
) -> OperationResult:
    """
    删除阶段
    
    Args:
        project_id: 项目ID
        phase_name: 阶段代码名
        db: 数据库会话
    
    Returns:
        OperationResult
    """
    if db is None:
        db = next(get_db())
    
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return OperationResult(
                success=False,
                message="项目不存在",
                operation="remove_phase",
                error="Project not found"
            )
        
        if phase_name not in project.phase_order:
            return OperationResult(
                success=False,
                message=f"阶段 '{phase_name}' 不存在",
                operation="remove_phase",
                error="Phase not found"
            )
        
        # 删除该阶段对应的 ContentBlock 及其子块
        deleted_ids = []
        display_name = PHASE_DISPLAY_NAMES.get(phase_name, phase_name)
        
        phase_blocks = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.block_type == "phase",
            ContentBlock.parent_id == None,  # noqa: E711
            ContentBlock.name.in_([display_name, phase_name]),
            ContentBlock.deleted_at == None,  # noqa: E711
        ).all()
        
        child_count = 0
        for block in phase_blocks:
            # 软删除子块
            children = db.query(ContentBlock).filter(
                ContentBlock.parent_id == block.id,
                ContentBlock.deleted_at == None,  # noqa: E711
            ).all()
            for child in children:
                child_count += 1
                deleted_ids.append(child.id)
                db.delete(child)
            deleted_ids.append(block.id)
            db.delete(block)
        
        # 更新 phase_order
        new_order = [p for p in project.phase_order if p != phase_name]
        project.phase_order = new_order
        
        # 更新 phase_status
        new_status = dict(project.phase_status or {})
        if phase_name in new_status:
            del new_status[phase_name]
        project.phase_status = new_status
        
        # 如果当前阶段被删除，切换到第一个阶段
        if project.current_phase == phase_name and new_order:
            project.current_phase = new_order[0]
        
        db.commit()
        
        return OperationResult(
            success=True,
            message=f"已删除阶段「{phase_name}」及其 {child_count} 个内容块",
            operation="remove_phase",
            affected_ids=deleted_ids
        )
        
    except Exception as e:
        db.rollback()
        return OperationResult(
            success=False,
            message=f"删除阶段失败: {str(e)}",
            operation="remove_phase",
            error=str(e)
        )


def reorder_phases(
    project_id: str,
    new_order: List[str],
    db: Optional[Session] = None,
) -> OperationResult:
    """
    重排阶段顺序
    
    Args:
        project_id: 项目ID
        new_order: 新的阶段顺序
        db: 数据库会话
    
    Returns:
        OperationResult
    """
    if db is None:
        db = next(get_db())
    
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return OperationResult(
                success=False,
                message="项目不存在",
                operation="reorder_phases",
                error="Project not found"
            )
        
        # 验证新顺序包含所有现有阶段
        existing = set(project.phase_order)
        new_set = set(new_order)
        
        if existing != new_set:
            missing = existing - new_set
            extra = new_set - existing
            error_parts = []
            if missing:
                error_parts.append(f"缺少: {missing}")
            if extra:
                error_parts.append(f"多余: {extra}")
            return OperationResult(
                success=False,
                message=f"阶段列表不匹配: {', '.join(error_parts)}",
                operation="reorder_phases",
                error="Phase list mismatch"
            )
        
        project.phase_order = new_order
        
        # 同步更新 ContentBlock 的 order_index
        for idx, phase_name in enumerate(new_order):
            display_name = PHASE_DISPLAY_NAMES.get(phase_name, phase_name)
            block = db.query(ContentBlock).filter(
                ContentBlock.project_id == project_id,
                ContentBlock.block_type == "phase",
                ContentBlock.parent_id == None,  # noqa: E711
                ContentBlock.name.in_([display_name, phase_name]),
                ContentBlock.deleted_at == None,  # noqa: E711
            ).first()
            if block:
                block.order_index = idx
        
        db.commit()
        
        return OperationResult(
            success=True,
            message=f"已重新排序阶段: {' → '.join(new_order)}",
            operation="reorder_phases",
        )
        
    except Exception as e:
        db.rollback()
        return OperationResult(
            success=False,
            message=f"重排阶段失败: {str(e)}",
            operation="reorder_phases",
            error=str(e)
        )


# ============== 字段操作 ==============

def add_field(
    project_id: str,
    phase: str,
    name: str,
    ai_prompt: str = "",
    depends_on: Optional[List[str]] = None,
    parent_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> OperationResult:
    """
    添加新字段
    
    Args:
        project_id: 项目ID
        phase: 所属阶段
        name: 字段名称
        ai_prompt: AI 生成提示词
        depends_on: 依赖字段列表
        db: 数据库会话
    
    Returns:
        OperationResult
    """
    if db is None:
        db = next(get_db())
    
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return OperationResult(
                success=False,
                message="项目不存在",
                operation="add_field",
                error="Project not found"
            )
        
        # 解析 phase 参数：支持内部 code、display_name、alias。
        # 若已显式传 parent_id，则允许 phase 为空。
        if phase:
            resolved_phase = _resolve_phase_code(phase, project.phase_order)
            if not resolved_phase:
                return OperationResult(
                    success=False,
                    message=f"阶段 '{phase}' 不存在（已尝试别名解析）",
                    operation="add_field",
                    error="Phase not found"
                )
            phase = resolved_phase
        
        # 检查字段是否已存在（在 ContentBlock 中查找）
        existing = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.name == name,
            ContentBlock.block_type == "field",
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        if existing:
            return OperationResult(
                success=False,
                message=f"字段「{name}」已存在",
                operation="add_field",
                error="Field already exists"
            )
        
        # 优先挂到明确指定的父节点；没有则回退到顶层阶段块
        parent_block = _find_active_block_by_id(project_id, parent_id, db)
        if parent_block and parent_block.block_type == "field":
            return OperationResult(
                success=False,
                message="不能将内容块添加到字段块下面",
                operation="add_field",
                error="Invalid parent block"
            )
        if not parent_block:
            parent_block = _find_top_level_phase_block(project_id, db, phase_name=phase)
        
        parent_id = parent_block.id if parent_block else None
        
        # 获取当前最大 order_index
        max_order = 0
        if parent_id:
            max_order = db.query(ContentBlock).filter(
                ContentBlock.parent_id == parent_id,
                ContentBlock.deleted_at == None,  # noqa: E711
            ).count()
        
        # 创建 ContentBlock（默认 need_review=True，新建块需人工确认后才生成）
        block = ContentBlock(
            id=str(uuid.uuid4()),
            project_id=project_id,
            parent_id=parent_id,
            name=name,
            block_type="field",
            depth=1,
            order_index=max_order,
            status="pending",
            ai_prompt=ai_prompt,
            depends_on=depends_on or [],
            constraints={},
            need_review=True,
        )
        db.add(block)
        
        db.commit()
        
        return OperationResult(
            success=True,
            message=f"已添加字段「{name}」",
            operation="add_field",
            affected_ids=[block.id]
        )
        
    except Exception as e:
        db.rollback()
        return OperationResult(
            success=False,
            message=f"添加字段失败: {str(e)}",
            operation="add_field",
            error=str(e)
        )


def remove_field(
    project_id: str,
    field_name: Optional[str] = None,
    field_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> OperationResult:
    """
    删除字段
    
    Args:
        project_id: 项目ID
        field_name: 字段名称
        db: 数据库会话
    
    Returns:
        OperationResult
    """
    if db is None:
        db = next(get_db())
    
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return OperationResult(
                success=False,
                message="项目不存在",
                operation="remove_field",
                error="Project not found"
            )
        
        # 查找 ContentBlock 字段
        block = _find_field_block(project_id, db, field_name=field_name, field_id=field_id)
        
        if not block:
            return OperationResult(
                success=False,
                message=f"字段「{field_name or field_id}」不存在",
                operation="remove_field",
                error="Field not found"
            )
        
        block_id = block.id
        db.delete(block)
        
        db.commit()
        
        return OperationResult(
            success=True,
            message=f"已删除字段「{block.name}」",
            operation="remove_field",
            affected_ids=[block_id]
        )
        
    except Exception as e:
        db.rollback()
        return OperationResult(
            success=False,
            message=f"删除字段失败: {str(e)}",
            operation="remove_field",
            error=str(e)
        )


def update_field(
    project_id: str,
    field_name: Optional[str],
    updates: Dict[str, Any],
    field_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> OperationResult:
    """
    更新字段属性
    
    Args:
        project_id: 项目ID
        field_name: 字段名称
        updates: 更新内容 {name, ai_prompt, depends_on, content}
        db: 数据库会话
    
    Returns:
        OperationResult
    """
    if db is None:
        db = next(get_db())
    
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return OperationResult(
                success=False,
                message="项目不存在",
                operation="update_field",
                error="Project not found"
            )
        
        # 查找 ContentBlock 字段
        block = _find_field_block(project_id, db, field_name=field_name, field_id=field_id)
        
        if not block:
            return OperationResult(
                success=False,
                message=f"字段「{field_name or field_id}」不存在",
                operation="update_field",
                error="Field not found"
            )
        
        # 更新 ContentBlock 属性
        updated_attrs = []
        if "name" in updates and updates["name"]:
            block.name = updates["name"]
            updated_attrs.append("名称")
        if "ai_prompt" in updates:
            block.ai_prompt = updates["ai_prompt"]
            updated_attrs.append("AI提示词")
        if "depends_on" in updates:
            block.depends_on = updates["depends_on"]
            updated_attrs.append("依赖")
        if "content" in updates:
            block.content = updates["content"]
            updated_attrs.append("内容")
        if "status" in updates:
            block.status = updates["status"]
            updated_attrs.append("状态")
        
        db.commit()
        
        return OperationResult(
            success=True,
            message=f"已更新字段「{block.name}」的 {', '.join(updated_attrs)}",
            operation="update_field",
            affected_ids=[block.id]
        )
        
    except Exception as e:
        db.rollback()
        return OperationResult(
            success=False,
            message=f"更新字段失败: {str(e)}",
            operation="update_field",
            error=str(e)
        )


def move_field(
    project_id: str,
    field_name: Optional[str],
    target_phase: str,
    field_id: Optional[str] = None,
    target_parent_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> OperationResult:
    """
    移动字段到另一个阶段
    
    Args:
        project_id: 项目ID
        field_name: 字段名称
        target_phase: 目标阶段
        db: 数据库会话
    
    Returns:
        OperationResult
    """
    if db is None:
        db = next(get_db())
    
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return OperationResult(
                success=False,
                message="项目不存在",
                operation="move_field",
                error="Project not found"
            )
        
        # 解析 target_phase 参数：支持内部 code、display_name、alias。
        # 若已显式传 target_parent_id，则允许 target_phase 为空。
        if target_phase:
            resolved_phase = _resolve_phase_code(target_phase, project.phase_order)
            if not resolved_phase:
                return OperationResult(
                    success=False,
                    message=f"目标阶段「{target_phase}」不存在（已尝试别名解析）",
                    operation="move_field",
                    error="Target phase not found"
                )
            target_phase = resolved_phase
        
        # 查找 ContentBlock 字段
        block = _find_field_block(project_id, db, field_name=field_name, field_id=field_id)
        
        if not block:
            return OperationResult(
                success=False,
                message=f"字段「{field_name or field_id}」不存在",
                operation="move_field",
                error="Field not found"
            )
        
        # 记录旧阶段（从父 block 推断）
        old_phase = "unknown"
        if block.parent_id:
            old_parent = db.query(ContentBlock).filter_by(id=block.parent_id).first()
            if old_parent:
                old_phase = old_parent.name
        
        # 找到目标阶段的 ContentBlock
        target_block = _find_active_block_by_id(project_id, target_parent_id, db)
        if target_block and target_block.block_type == "field":
            return OperationResult(
                success=False,
                message="目标父节点不能是字段块",
                operation="move_field",
                error="Invalid target parent"
            )
        if not target_block:
            target_block = _find_top_level_phase_block(project_id, db, phase_name=target_phase)
        
        if not target_block:
            return OperationResult(
                success=False,
                message=f"目标阶段「{target_phase}」的内容块不存在",
                operation="move_field",
                error="Target phase block not found"
            )
        
        block.parent_id = target_block.id
        # 更新 order_index
        max_order = db.query(ContentBlock).filter(
            ContentBlock.parent_id == target_block.id,
            ContentBlock.deleted_at == None,  # noqa: E711
        ).count()
        block.order_index = max_order
        
        db.commit()
        
        return OperationResult(
            success=True,
            message=f"已将字段「{block.name}」从「{old_phase}」移动到「{target_phase or (target_block.name if target_block else '目标位置')}」",
            operation="move_field",
            affected_ids=[block.id]
        )
        
    except Exception as e:
        db.rollback()
        return OperationResult(
            success=False,
            message=f"移动字段失败: {str(e)}",
            operation="move_field",
            error=str(e)
        )


def add_node(
    project_id: str,
    name: str,
    block_type: str = "field",
    parent_id: Optional[str] = None,
    phase: str = "",
    ai_prompt: str = "",
    depends_on: Optional[List[str]] = None,
    content: str = "",
    special_handler: Optional[str] = None,
    need_review: bool = True,
    auto_generate: bool = False,
    model_override: Optional[str] = None,
    guidance_input: str = "",
    guidance_output: str = "",
    constraints: Optional[Dict[str, Any]] = None,
    order_index: Optional[int] = None,
    db: Optional[Session] = None,
) -> OperationResult:
    """通用树节点新增。顶层 phase 自动委派给 add_phase 以保持 phase_order 同步。"""
    if db is None:
        db = next(get_db())

    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return OperationResult(False, "项目不存在", "add_node", error="Project not found")

        # 顶层 phase 自动委派给 add_phase，确保 phase_order / phase_status 同步
        if block_type == "phase" and parent_id is None:
            phase_name = special_handler or name.lower().replace(" ", "_")
            return add_phase(
                project_id=project_id,
                phase_name=phase_name,
                display_name=name,
                position=order_index,
                db=db,
            )

        parent_block = _find_active_block_by_id(project_id, parent_id, db)
        if not parent_block and phase:
            parent_block = _find_top_level_phase_block(project_id, db, phase_name=phase)
        if parent_block and parent_block.block_type == "field":
            return OperationResult(False, "字段块不能作为父节点", "add_node", error="Invalid parent")

        if block_type == "field":
            existing = db.query(ContentBlock).filter(
                ContentBlock.project_id == project_id,
                ContentBlock.name == name,
                ContentBlock.block_type == "field",
                ContentBlock.deleted_at == None,  # noqa: E711
            ).first()
            if existing:
                return OperationResult(False, f"字段「{name}」已存在", "add_node", error="Field already exists")

        depth = (parent_block.depth + 1) if parent_block else 0
        initial_status = "in_progress" if content and need_review else ("completed" if content else "pending")

        block = ContentBlock(
            id=str(uuid.uuid4()),
            project_id=project_id,
            parent_id=parent_block.id if parent_block else None,
            name=name,
            block_type=block_type,
            depth=depth,
            order_index=0,
            status=initial_status,
            content=content,
            ai_prompt=ai_prompt,
            depends_on=depends_on or [],
            constraints=constraints or {},
            special_handler=special_handler,
            need_review=need_review,
            auto_generate=auto_generate,
            model_override=model_override,
            guidance_input=guidance_input,
            guidance_output=guidance_output,
        )
        db.add(block)
        db.flush()
        _insert_block_at_order(project_id, block.parent_id, block, order_index, db)
        db.commit()

        return OperationResult(
            success=True,
            message=f"已新增{block_type}节点「{name}」",
            operation="add_node",
            affected_ids=[block.id]
        )
    except Exception as e:
        db.rollback()
        return OperationResult(False, f"新增节点失败: {str(e)}", "add_node", error=str(e))


def remove_node(
    project_id: str,
    node_name: Optional[str] = None,
    node_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> OperationResult:
    """删除任意节点及其整个子树。顶层 phase 自动委派给 remove_phase 以保持 phase_order 同步。"""
    if db is None:
        db = next(get_db())

    try:
        block = _find_node(project_id, db, node_id=node_id, node_name=node_name)
        if not block:
            return OperationResult(False, f"节点「{node_name or node_id}」不存在", "remove_node", error="Node not found")
        # 顶层 phase 自动委派给 remove_phase，确保 phase_order / phase_status 同步
        if block.block_type == "phase" and block.parent_id is None:
            # 推断 phase_name：优先用 special_handler，再反查 PHASE_DISPLAY_NAMES
            phase_name = block.special_handler or block.name
            for code, display in PHASE_DISPLAY_NAMES.items():
                if display == block.name or code == block.name:
                    phase_name = code
                    break
            return remove_phase(project_id=project_id, phase_name=phase_name, db=db)

        old_parent_id = block.parent_id
        affected_ids = [desc.id for desc in block.get_all_descendants()] + [block.id]
        db.delete(block)
        db.flush()
        _resequence_children(project_id, old_parent_id, db)
        db.commit()
        return OperationResult(True, f"已删除节点「{block.name}」及其子树", "remove_node", affected_ids=affected_ids)
    except Exception as e:
        db.rollback()
        return OperationResult(False, f"删除节点失败: {str(e)}", "remove_node", error=str(e))


def move_node(
    project_id: str,
    node_name: Optional[str] = None,
    node_id: Optional[str] = None,
    new_parent_id: Optional[str] = None,
    new_order_index: Optional[int] = None,
    db: Optional[Session] = None,
) -> OperationResult:
    """移动任意节点到新的父节点下。顶层 phase 排序需使用 reorder_phases（需要完整顺序列表）。"""
    if db is None:
        db = next(get_db())

    try:
        block = _find_node(project_id, db, node_id=node_id, node_name=node_name)
        if not block:
            return OperationResult(False, f"节点「{node_name or node_id}」不存在", "move_node", error="Node not found")
        if block.block_type == "phase" and block.parent_id is None:
            return OperationResult(
                success=False,
                message="顶层阶段排序需要使用 reorder_phases 并传入完整顺序列表，无法通过 move_node 单点移动",
                operation="move_node",
                error="Use reorder_phases for top-level phase reordering"
            )

        new_parent = _find_active_block_by_id(project_id, new_parent_id, db)
        if new_parent and new_parent.block_type == "field":
            return OperationResult(False, "字段块不能作为父节点", "move_node", error="Invalid parent")

        descendant_ids = {desc.id for desc in block.get_all_descendants()}
        if new_parent and new_parent.id in descendant_ids:
            return OperationResult(False, "不能移动到自己的后代节点下", "move_node", error="Cycle detected")

        old_parent_id = block.parent_id
        block.parent_id = new_parent.id if new_parent else None
        block.depth = (new_parent.depth + 1) if new_parent else 0
        _refresh_descendant_depths(block, db)
        db.flush()
        _insert_block_at_order(project_id, block.parent_id, block, new_order_index, db)
        _resequence_children(project_id, old_parent_id, db)
        db.commit()

        return OperationResult(
            success=True,
            message=f"已移动节点「{block.name}」",
            operation="move_node",
            affected_ids=[block.id]
        )
    except Exception as e:
        db.rollback()
        return OperationResult(False, f"移动节点失败: {str(e)}", "move_node", error=str(e))


def update_node_meta(
    project_id: str,
    updates: Dict[str, Any],
    node_name: Optional[str] = None,
    node_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> OperationResult:
    """更新任意节点元数据。"""
    if db is None:
        db = next(get_db())

    try:
        block = _find_node(project_id, db, node_id=node_id, node_name=node_name)
        if not block:
            return OperationResult(False, f"节点「{node_name or node_id}」不存在", "update_node_meta", error="Node not found")

        allowed_fields = {
            "name", "content", "ai_prompt", "depends_on", "special_handler", "status",
            "need_review", "auto_generate", "model_override", "guidance_input",
            "guidance_output", "constraints", "is_collapsed",
        }
        updated_attrs = []
        for key, value in updates.items():
            if key not in allowed_fields:
                continue
            setattr(block, key, value)
            updated_attrs.append(key)

        db.commit()
        summary = "、".join(updated_attrs) if updated_attrs else "无变更"
        return OperationResult(True, f"已更新节点「{block.name}」的 {summary}", "update_node_meta", affected_ids=[block.id])
    except Exception as e:
        db.rollback()
        return OperationResult(False, f"更新节点失败: {str(e)}", "update_node_meta", error=str(e))


def instantiate_template(
    project_id: str,
    template_id: str,
    parent_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> OperationResult:
    """将模板实例化到指定父节点下。"""
    if db is None:
        db = next(get_db())

    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return OperationResult(False, "项目不存在", "instantiate_template", error="Project not found")

        parent_block = _find_active_block_by_id(project_id, parent_id, db)
        if parent_block and parent_block.block_type == "field":
            return OperationResult(False, "字段块不能作为模板实例化的父节点", "instantiate_template", error="Invalid parent")

        base_depth = (parent_block.depth + 1) if parent_block else 0
        start_order_index = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.parent_id == parent_id,
            ContentBlock.deleted_at == None,  # noqa: E711
        ).count()

        template_name = ""
        phase_template = db.query(PhaseTemplate).filter(PhaseTemplate.id == template_id).first()
        if phase_template:
            root_nodes = phase_template.to_template_nodes()
            template_name = phase_template.name
        else:
            field_template = db.query(FieldTemplate).filter(FieldTemplate.id == template_id).first()
            if not field_template:
                return OperationResult(False, "模板不存在", "instantiate_template", error="Template not found")
            normalized, errors = normalize_field_template_payload(
                template_name=field_template.name,
                fields=field_template.fields or [],
                root_nodes=getattr(field_template, "root_nodes", None) or [],
            )
            if errors:
                return OperationResult(False, "; ".join(errors), "instantiate_template", error="Invalid template")
            root_nodes = normalized["root_nodes"]
            template_name = field_template.name

        blocks_to_create = instantiate_template_nodes(
            project_id=project_id,
            root_nodes=root_nodes,
            parent_id=parent_id,
            base_depth=base_depth,
            start_order_index=start_order_index,
        )
        created_ids = []
        for block_data in blocks_to_create:
            created_ids.append(block_data["id"])
            db.add(ContentBlock(**block_data))
        db.commit()
        return OperationResult(
            success=True,
            message=f"已实例化模板「{template_name}」",
            operation="instantiate_template",
            affected_ids=created_ids,
        )
    except Exception as e:
        db.rollback()
        return OperationResult(False, f"实例化模板失败: {str(e)}", "instantiate_template", error=str(e))


# ============== 统一入口 ==============

async def modify_architecture(
    project_id: str,
    operation: ArchitectureOperation,
    params: Dict[str, Any],
    db: Optional[Session] = None,
) -> OperationResult:
    """
    架构修改统一入口
    
    Args:
        project_id: 项目ID
        operation: 操作类型
        params: 操作参数
        db: 数据库会话
    
    Returns:
        OperationResult
    """
    if db is None:
        db = next(get_db())
    
    if operation == ArchitectureOperation.ADD_PHASE:
        return add_phase(
            project_id=project_id,
            phase_name=params.get("phase_name", ""),
            display_name=params.get("display_name", ""),
            position=params.get("position"),
            db=db,
        )
    
    elif operation == ArchitectureOperation.REMOVE_PHASE:
        return remove_phase(
            project_id=project_id,
            phase_name=params.get("phase_name", ""),
            db=db,
        )
    
    elif operation == ArchitectureOperation.REORDER_PHASES:
        return reorder_phases(
            project_id=project_id,
            new_order=params.get("new_order", []),
            db=db,
        )
    
    elif operation == ArchitectureOperation.ADD_FIELD:
        return add_field(
            project_id=project_id,
            phase=params.get("phase", ""),
            name=params.get("name", ""),
            ai_prompt=params.get("ai_prompt", ""),
            depends_on=params.get("depends_on"),
            parent_id=params.get("parent_id"),
            db=db,
        )
    
    elif operation == ArchitectureOperation.REMOVE_FIELD:
        return remove_field(
            project_id=project_id,
            field_name=params.get("field_name", ""),
            field_id=params.get("field_id"),
            db=db,
        )
    
    elif operation == ArchitectureOperation.UPDATE_FIELD:
        return update_field(
            project_id=project_id,
            field_name=params.get("field_name", ""),
            updates=params.get("updates", {}),
            field_id=params.get("field_id"),
            db=db,
        )
    
    elif operation == ArchitectureOperation.MOVE_FIELD:
        return move_field(
            project_id=project_id,
            field_name=params.get("field_name", ""),
            target_phase=params.get("target_phase", ""),
            field_id=params.get("field_id"),
            target_parent_id=params.get("target_parent_id"),
            db=db,
        )

    elif operation == ArchitectureOperation.ADD_NODE:
        return add_node(
            project_id=project_id,
            name=params.get("name", ""),
            block_type=params.get("block_type", "field"),
            parent_id=params.get("parent_id"),
            phase=params.get("phase", ""),
            ai_prompt=params.get("ai_prompt", ""),
            depends_on=params.get("depends_on"),
            content=params.get("content", ""),
            special_handler=params.get("special_handler"),
            need_review=params.get("need_review", True),
            auto_generate=params.get("auto_generate", False),
            model_override=params.get("model_override"),
            guidance_input=params.get("guidance_input", ""),
            guidance_output=params.get("guidance_output", ""),
            constraints=params.get("constraints"),
            order_index=params.get("order_index"),
            db=db,
        )

    elif operation == ArchitectureOperation.REMOVE_NODE:
        return remove_node(
            project_id=project_id,
            node_name=params.get("node_name"),
            node_id=params.get("node_id"),
            db=db,
        )

    elif operation == ArchitectureOperation.MOVE_NODE:
        return move_node(
            project_id=project_id,
            node_name=params.get("node_name"),
            node_id=params.get("node_id"),
            new_parent_id=params.get("new_parent_id"),
            new_order_index=params.get("new_order_index"),
            db=db,
        )

    elif operation == ArchitectureOperation.UPDATE_NODE_META:
        return update_node_meta(
            project_id=project_id,
            updates=params.get("updates", {}),
            node_name=params.get("node_name"),
            node_id=params.get("node_id"),
            db=db,
        )

    elif operation == ArchitectureOperation.INSTANTIATE_TEMPLATE:
        return instantiate_template(
            project_id=project_id,
            template_id=params.get("template_id", ""),
            parent_id=params.get("parent_id"),
            db=db,
        )
    
    else:
        return OperationResult(
            success=False,
            message=f"未知操作: {operation}",
            operation=str(operation),
            error="Unknown operation"
        )
