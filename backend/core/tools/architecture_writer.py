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
from core.models import Project
from core.models.content_block import ContentBlock
from core.phase_config import PHASE_DISPLAY_NAMES, PHASE_ALIAS


class ArchitectureOperation(str, Enum):
    """架构操作类型"""
    ADD_PHASE = "add_phase"
    REMOVE_PHASE = "remove_phase"
    REORDER_PHASES = "reorder_phases"
    ADD_FIELD = "add_field"
    REMOVE_FIELD = "remove_field"
    MOVE_FIELD = "move_field"
    UPDATE_FIELD = "update_field"


@dataclass
class OperationResult:
    """操作结果"""
    success: bool
    message: str
    operation: str
    affected_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None


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
        
        # 解析 phase 参数：支持内部 code、display_name、alias
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
        
        # 找到父阶段 ContentBlock
        display_name = PHASE_DISPLAY_NAMES.get(phase, phase)
        parent_block = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.block_type == "phase",
            ContentBlock.parent_id == None,  # noqa: E711
            ContentBlock.name.in_([display_name, phase]),
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        
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
            message=f"已在「{phase}」阶段添加字段「{name}」",
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
    field_name: str,
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
        block = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.name == field_name,
            ContentBlock.block_type == "field",
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        
        if not block:
            return OperationResult(
                success=False,
                message=f"字段「{field_name}」不存在",
                operation="remove_field",
                error="Field not found"
            )
        
        block_id = block.id
        db.delete(block)
        
        db.commit()
        
        return OperationResult(
            success=True,
            message=f"已删除字段「{field_name}」",
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
    field_name: str,
    updates: Dict[str, Any],
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
        block = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.name == field_name,
            ContentBlock.block_type == "field",
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        
        if not block:
            return OperationResult(
                success=False,
                message=f"字段「{field_name}」不存在",
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
            message=f"已更新字段「{field_name}」的 {', '.join(updated_attrs)}",
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
    field_name: str,
    target_phase: str,
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
        
        # 解析 target_phase 参数：支持内部 code、display_name、alias
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
        block = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.name == field_name,
            ContentBlock.block_type == "field",
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        
        if not block:
            return OperationResult(
                success=False,
                message=f"字段「{field_name}」不存在",
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
        target_display = PHASE_DISPLAY_NAMES.get(target_phase, target_phase)
        target_block = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.block_type == "phase",
            ContentBlock.parent_id == None,  # noqa: E711
            ContentBlock.name.in_([target_display, target_phase]),
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        
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
            message=f"已将字段「{field_name}」从「{old_phase}」移动到「{target_phase}」",
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
            db=db,
        )
    
    elif operation == ArchitectureOperation.REMOVE_FIELD:
        return remove_field(
            project_id=project_id,
            field_name=params.get("field_name", ""),
            db=db,
        )
    
    elif operation == ArchitectureOperation.UPDATE_FIELD:
        return update_field(
            project_id=project_id,
            field_name=params.get("field_name", ""),
            updates=params.get("updates", {}),
            db=db,
        )
    
    elif operation == ArchitectureOperation.MOVE_FIELD:
        return move_field(
            project_id=project_id,
            field_name=params.get("field_name", ""),
            target_phase=params.get("target_phase", ""),
            db=db,
        )
    
    else:
        return OperationResult(
            success=False,
            message=f"未知操作: {operation}",
            operation=str(operation),
            error="Unknown operation"
        )
