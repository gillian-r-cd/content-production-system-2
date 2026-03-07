# backend/core/tools/architecture_reader.py
# 功能: 项目架构感知工具，让 Agent 能够读取和理解项目结构
# 主要函数: get_project_architecture(), get_phase_fields(), get_field_content()
# 数据结构: ProjectArchitecture, PhaseInfo, FieldInfo
# P0-1: 统一使用 ContentBlock，已移除所有 ProjectField 依赖

"""
项目架构感知工具

提供 Agent 读取项目结构的能力：
1. 获取项目的阶段列表和状态
2. 获取某阶段下的所有字段
3. 读取字段内容
4. 获取 ContentBlocks 层级结构
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from sqlalchemy.orm import Session

from core.content_block_reference import (
    build_block_path,
    build_block_reference_label,
    build_blocks_by_id,
    find_block_by_identifier,
    list_active_project_blocks,
)
from core.database import get_db
from core.models import Project
from core.models.content_block import ContentBlock
from core.project_structure_draft_service import (
    get_or_create_auto_split_draft,
    summarize_draft,
)


@dataclass
class FieldInfo:
    """字段信息"""
    id: str
    name: str
    phase: str
    status: str
    content_preview: str  # 内容预览（前200字符）
    has_content: bool
    ai_prompt: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)


@dataclass
class PhaseInfo:
    """阶段信息"""
    name: str
    display_name: str
    status: str
    order_index: int
    fields: List[FieldInfo] = field(default_factory=list)
    field_count: int = 0


@dataclass
class ContentBlockInfo:
    """内容块信息"""
    id: str
    name: str
    block_type: str  # phase, field, proposal
    status: str
    content_preview: str
    depth: int
    children_count: int
    path: str = ""
    reference_key: str = ""
    

@dataclass
class ProjectArchitecture:
    """项目架构"""
    project_id: str
    project_name: str
    current_phase: str
    phases: List[PhaseInfo]
    total_fields: int
    completed_fields: int
    # 内容块结构
    content_blocks: Optional[List[ContentBlockInfo]] = None
    auto_split_draft: Optional[Dict[str, Any]] = None


# 阶段显示名称映射（从统一配置导入）
from core.phase_config import PHASE_DISPLAY_NAMES


def get_project_architecture(project_id: str, db: Optional[Session] = None) -> Optional[ProjectArchitecture]:
    """
    获取项目的完整架构信息（统一使用 ContentBlock）
    
    Args:
        project_id: 项目ID
        db: 数据库会话（可选）
    
    Returns:
        ProjectArchitecture 或 None
    """
    if db is None:
        db = next(get_db())
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None
    
    # 获取所有未删除的 ContentBlock
    all_blocks = list_active_project_blocks(db, project_id)
    blocks_by_id = build_blocks_by_id(all_blocks)
    
    # 分离阶段块和字段块
    phase_blocks = [b for b in all_blocks if b.block_type == "phase" and b.parent_id is None]
    field_blocks = [b for b in all_blocks if b.block_type == "field"]
    
    # 建立 parent_id → children 映射
    children_map: Dict[str, List[ContentBlock]] = {}
    for b in all_blocks:
        if b.parent_id:
            children_map.setdefault(b.parent_id, []).append(b)
    
    # 构建阶段信息
    phases = []
    for idx, phase_name in enumerate(project.phase_order):
        # 根据 special_handler 或名称匹配阶段块
        phase_block = None
        display_name = PHASE_DISPLAY_NAMES.get(phase_name, phase_name)
        for pb in phase_blocks:
            if pb.special_handler == phase_name or pb.name == display_name or pb.name == phase_name:
                phase_block = pb
                break
        
        phase_children = children_map.get(phase_block.id, []) if phase_block else []
        child_fields = [c for c in phase_children if c.block_type == "field"]
        
        field_infos = [
            FieldInfo(
                id=f.id,
                name=f.name,
                phase=phase_name,
                status=f.status or "pending",
                content_preview=(f.content[:200] + "..." if f.content and len(f.content) > 200 else f.content or ""),
                has_content=bool(f.content and f.content.strip()),
                ai_prompt=f.ai_prompt[:100] + "..." if f.ai_prompt and len(f.ai_prompt) > 100 else f.ai_prompt,
                dependencies=f.depends_on or [],
            )
            for f in child_fields
        ]
        
        phases.append(PhaseInfo(
            name=phase_name,
            display_name=display_name,
            status=project.phase_status.get(phase_name, "pending"),
            order_index=idx,
            fields=field_infos,
            field_count=len(field_infos),
        ))
    
    # 统计完成情况
    total_fields = len(field_blocks)
    completed_fields = sum(1 for f in field_blocks if f.status == "completed")
    
    # 获取顶层 ContentBlocks
    top_blocks = [b for b in all_blocks if b.parent_id is None]
    content_blocks = [
        ContentBlockInfo(
            id=b.id,
            name=b.name,
            block_type=b.block_type,
            status=b.status,
            content_preview=(b.content[:200] + "..." if b.content and len(b.content) > 200 else b.content or ""),
            depth=b.depth,
            children_count=len(children_map.get(b.id, [])),
            path=build_block_path(b, blocks_by_id),
            reference_key=build_block_reference_label(b, blocks_by_id=blocks_by_id),
        )
        for b in top_blocks
    ]

    auto_split_draft = None
    try:
        auto_split_draft = summarize_draft(get_or_create_auto_split_draft(project_id, db))
    except ValueError:
        auto_split_draft = None
    
    return ProjectArchitecture(
        project_id=project.id,
        project_name=project.name,
        current_phase=project.current_phase,
        phases=phases,
        total_fields=total_fields,
        completed_fields=completed_fields,
        content_blocks=content_blocks,
        auto_split_draft=auto_split_draft,
    )


def get_phase_fields(project_id: str, phase: str, db: Optional[Session] = None) -> List[FieldInfo]:
    """
    获取某阶段的所有字段（通过 ContentBlock 阶段块的子节点）
    
    Args:
        project_id: 项目ID
        phase: 阶段代码（如 "intent", "research"）
        db: 数据库会话
    
    Returns:
        字段信息列表
    """
    if db is None:
        db = next(get_db())
    
    display_name = PHASE_DISPLAY_NAMES.get(phase, phase)
    
    # 查找阶段块
    phase_block = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.block_type == "phase",
        ContentBlock.deleted_at == None,  # noqa: E711
    ).filter(
        (ContentBlock.special_handler == phase) |
        (ContentBlock.name == display_name) |
        (ContentBlock.name == phase)
    ).first()
    
    if not phase_block:
        return []
    
    # 获取阶段块的子字段
    child_fields = db.query(ContentBlock).filter(
        ContentBlock.parent_id == phase_block.id,
        ContentBlock.block_type == "field",
        ContentBlock.deleted_at == None,  # noqa: E711
    ).order_by(ContentBlock.order_index).all()
    
    return [
        FieldInfo(
            id=f.id,
            name=f.name,
            phase=phase,
            status=f.status or "pending",
            content_preview=(f.content[:200] + "..." if f.content and len(f.content) > 200 else f.content or ""),
            has_content=bool(f.content and f.content.strip()),
            ai_prompt=f.ai_prompt,
            dependencies=f.depends_on or [],
        )
        for f in child_fields
    ]


def get_field_content(
    project_id: str,
    field_name: str = "",
    field_id: str = "",
    db: Optional[Session] = None,
) -> Optional[Dict[str, Any]]:
    """
    根据字段名获取字段完整内容（统一搜索 ContentBlock）
    
    Args:
        project_id: 项目ID
        field_name: 字段名称
        field_id: 字段 ID（优先于名称）
        db: 数据库会话
    
    Returns:
        字段详情字典或 None
    """
    if db is None:
        db = next(get_db())
    
    block = find_block_by_identifier(db, project_id, f"id:{field_id}" if field_id else field_name)
    
    if block:
        blocks_by_id = build_blocks_by_id(list_active_project_blocks(db, project_id))
        # 推断 phase：通过父级阶段块
        phase = ""
        if block.parent_id:
            parent = db.query(ContentBlock).filter(
                ContentBlock.id == block.parent_id,
                ContentBlock.block_type == "phase",
            ).first()
            if parent:
                phase = parent.special_handler or parent.name
        
        return {
            "id": block.id,
            "name": block.name,
            "phase": phase,
            "status": block.status,
            "content": block.content,
            "ai_prompt": block.ai_prompt,
            "dependencies": {"depends_on": block.depends_on or []},
            "need_review": block.need_review,
            "auto_generate": getattr(block, 'auto_generate', False),
            "source": "content_block",
            "path": build_block_path(block, blocks_by_id),
            "reference_key": build_block_reference_label(block, blocks_by_id=blocks_by_id),
        }
    
    return None


def get_content_block_tree(project_id: str, db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """
    获取项目的 ContentBlock 树形结构
    
    Args:
        project_id: 项目ID
        db: 数据库会话
    
    Returns:
        嵌套的块结构列表
    """
    if db is None:
        db = next(get_db())
    
    all_blocks = list_active_project_blocks(db, project_id)
    blocks_by_id = build_blocks_by_id(all_blocks)
    root_blocks = [block for block in all_blocks if block.parent_id is None]
    
    def block_to_dict(block: ContentBlock) -> Dict[str, Any]:
        return {
            "id": block.id,
            "name": block.name,
            "block_type": block.block_type,
            "status": block.status,
            "content_preview": (block.content[:100] + "..." if block.content and len(block.content) > 100 else block.content or ""),
            "depth": block.depth,
            "path": build_block_path(block, blocks_by_id),
            "reference_key": build_block_reference_label(block, blocks_by_id=blocks_by_id),
            "auto_generate": getattr(block, "auto_generate", False),
            "special_handler": getattr(block, "special_handler", None),
            "children": [block_to_dict(child) for child in block.children] if block.children else [],
        }
    
    return [block_to_dict(b) for b in root_blocks]


def get_dependency_contents(
    project_id: str, 
    dependency_names: List[str],
    db: Optional[Session] = None
) -> Dict[str, str]:
    """
    获取多个依赖字段的内容（统一搜索 ContentBlock）
    
    Args:
        project_id: 项目ID
        dependency_names: 依赖字段名称列表，如 ["意图分析", "消费者调研"]
        db: 数据库会话
    
    Returns:
        {字段名: 字段内容} 字典
    """
    if db is None:
        db = next(get_db())
    
    result = {}
    for name in dependency_names:
        block = find_block_by_identifier(db, project_id, name)

        if block and block.content:
            result[name] = block.content
    
    return result


def get_intent_and_research(project_id: str, db: Optional[Session] = None) -> Dict[str, str]:
    """
    获取意图分析和消费者调研结果（统一使用 ContentBlock）
    
    搜索策略：
    1. 按名称查找具体字段块（做什么/给谁看/核心价值）
    2. 按名称查找聚合字段块（意图分析/项目意图）
    3. 按 special_handler="intent" 的阶段块下的所有子字段
    
    Returns:
        {"intent": ..., "research": ...} 字典，缺失的字段为空字符串
    """
    if db is None:
        db = next(get_db())
    
    # === 1. 获取意图分析 ===
    intent_parts = []
    
    # 策略A: 查找3个独立字段块 (做什么/给谁看/核心价值)
    intent_field_names = ["做什么", "给谁看", "核心价值"]
    for fname in intent_field_names:
        block = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.name == fname,
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        if block and block.content:
            intent_parts.append(f"**{fname}**: {block.content}")
    
    # 策略B: 查找聚合字段块 (意图分析/项目意图/Intent)
    if not intent_parts:
        fallback_names = ["意图分析", "项目意图", "Intent"]
        intent_block = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.name.in_(fallback_names),
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        if intent_block and intent_block.content:
            intent_parts.append(intent_block.content)
    
    # 策略C: 查找 special_handler="intent" 阶段块的所有子字段（兜底）
    if not intent_parts:
        intent_phase = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.special_handler == "intent",
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        if intent_phase:
            children = db.query(ContentBlock).filter(
                ContentBlock.parent_id == intent_phase.id,
                ContentBlock.deleted_at == None,  # noqa: E711
            ).all()
            for c in children:
                if c.content:
                    intent_parts.append(f"**{c.name}**: {c.content}")
    
    intent_str = "\n".join(intent_parts)
    
    # === 2. 获取消费者调研 ===
    research_str = ""
    research_names = ["消费者调研报告", "消费者调研"]
    
    research_block = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.name.in_(research_names),
        ContentBlock.deleted_at == None,  # noqa: E711
    ).first()
    if research_block and research_block.content:
        research_str = research_block.content
    
    # 兜底：查找 special_handler="research" 的块
    if not research_str:
        research_phase = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.special_handler == "research",
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        if research_phase and research_phase.content:
            research_str = research_phase.content
    
    return {
        "intent": intent_str,
        "research": research_str,
    }


def format_architecture_for_llm(arch: ProjectArchitecture) -> str:
    """
    将架构信息格式化为 LLM 可读的文本
    
    Args:
        arch: 项目架构
    
    Returns:
        格式化的文本描述
    """
    lines = [
        f"## 项目架构: {arch.project_name}",
        f"当前阶段: {arch.current_phase}",
        f"进度: {arch.completed_fields}/{arch.total_fields} 字段已完成",
        "",
    ]

    if arch.auto_split_draft:
        draft = arch.auto_split_draft
        lines.extend([
            "### 自动拆分草稿概览:",
            f"- 状态: {draft.get('status', 'draft')}",
            f"- chunks: {draft.get('chunk_count', 0)}",
            f"- plans: {draft.get('plan_count', 0)}",
            f"- shared_root_nodes: {draft.get('shared_root_node_count', 0)}",
            f"- aggregate_root_nodes: {draft.get('aggregate_root_node_count', 0)}",
            "",
        ])
    
    # 展示完整的块树形结构，包含所有字段名
    lines.append("### 内容块结构:")
    if arch.content_blocks:
        for block in arch.content_blocks:
            lines.append(f"  - {block.path or block.name} [{block.block_type}]: {block.status} ({block.reference_key})")
    
    # 从数据库获取完整的嵌套结构（包含所有字段名）
    try:
        block_tree = get_content_block_tree(arch.project_id)
        if block_tree:
            lines.append("")
            lines.append("### 所有字段列表（可用 @ 引用的名称）:")
            def list_fields(blocks, indent=0):
                for b in blocks:
                    prefix = "  " * indent
                    has_content_icon = "📝" if b.get("content_preview") else "📄"
                    status = b.get("status", "pending")
                    if b.get("block_type") == "field":
                        lines.append(f"{prefix}{has_content_icon} 「{b['name']}」 ({status}) [{b.get('reference_key', b['id'])}]")
                    else:
                        lines.append(f"{prefix}📁 {b['name']} [{b.get('block_type', 'unknown')}] [{b.get('reference_key', b['id'])}]")
                    if b.get("children"):
                        list_fields(b["children"], indent + 1)
            list_fields(block_tree)
    except Exception as e:
        lines.append(f"  (获取详细结构失败: {str(e)})")
    
    return "\n".join(lines)


def get_auto_split_draft_overview(project_id: str, db: Optional[Session] = None) -> Dict[str, Any]:
    if db is None:
        db = next(get_db())
    draft = get_or_create_auto_split_draft(project_id, db)
    return summarize_draft(draft)
