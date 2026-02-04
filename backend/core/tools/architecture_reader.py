# backend/core/tools/architecture_reader.py
# 功能: 项目架构感知工具，让 Agent 能够读取和理解项目结构
# 主要函数: get_project_architecture(), get_phase_fields(), get_field_content()
# 数据结构: ProjectArchitecture, PhaseInfo, FieldInfo

"""
项目架构感知工具

提供 Agent 读取项目结构的能力：
1. 获取项目的阶段列表和状态
2. 获取某阶段下的所有字段
3. 读取字段内容
4. 获取 ContentBlocks 层级结构（灵活架构）
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Project, ProjectField
from core.models.content_block import ContentBlock


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
    """内容块信息（灵活架构）"""
    id: str
    name: str
    block_type: str  # phase, field, proposal
    status: str
    content_preview: str
    depth: int
    children_count: int
    

@dataclass
class ProjectArchitecture:
    """项目架构"""
    project_id: str
    project_name: str
    current_phase: str
    use_flexible_architecture: bool
    phases: List[PhaseInfo]
    total_fields: int
    completed_fields: int
    # 灵活架构专用
    content_blocks: Optional[List[ContentBlockInfo]] = None


# 阶段显示名称映射
PHASE_DISPLAY_NAMES = {
    "intent": "意图分析",
    "research": "消费者调研",
    "design_inner": "内涵设计",
    "produce_inner": "内涵生产",
    "design_outer": "外延设计",
    "produce_outer": "外延生产",
    "simulate": "消费者模拟",
    "evaluate": "评估",
}


def get_project_architecture(project_id: str, db: Optional[Session] = None) -> Optional[ProjectArchitecture]:
    """
    获取项目的完整架构信息
    
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
    
    # 获取所有字段
    fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id
    ).all()
    
    # 按阶段分组
    fields_by_phase: Dict[str, List[ProjectField]] = {}
    for f in fields:
        if f.phase not in fields_by_phase:
            fields_by_phase[f.phase] = []
        fields_by_phase[f.phase].append(f)
    
    # 构建阶段信息
    phases = []
    for idx, phase_name in enumerate(project.phase_order):
        phase_fields = fields_by_phase.get(phase_name, [])
        
        field_infos = [
            FieldInfo(
                id=f.id,
                name=f.name,
                phase=f.phase,
                status=f.status or "pending",
                content_preview=(f.content[:200] + "..." if f.content and len(f.content) > 200 else f.content or ""),
                has_content=bool(f.content and f.content.strip()),
                ai_prompt=f.ai_prompt[:100] + "..." if f.ai_prompt and len(f.ai_prompt) > 100 else f.ai_prompt,
                dependencies=f.dependencies.get("depends_on", []) if f.dependencies else [],
            )
            for f in phase_fields
        ]
        
        phases.append(PhaseInfo(
            name=phase_name,
            display_name=PHASE_DISPLAY_NAMES.get(phase_name, phase_name),
            status=project.phase_status.get(phase_name, "pending"),
            order_index=idx,
            fields=field_infos,
            field_count=len(field_infos),
        ))
    
    # 统计完成情况
    total_fields = len(fields)
    completed_fields = sum(1 for f in fields if f.status == "completed")
    
    # 如果是灵活架构，获取 ContentBlocks
    content_blocks = None
    if project.use_flexible_architecture:
        blocks = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.parent_id == None  # 只获取顶层块
        ).order_by(ContentBlock.order_index).all()
        
        content_blocks = [
            ContentBlockInfo(
                id=b.id,
                name=b.name,
                block_type=b.block_type,
                status=b.status,
                content_preview=(b.content[:200] + "..." if b.content and len(b.content) > 200 else b.content or ""),
                depth=b.depth,
                children_count=len(b.children) if hasattr(b, 'children') else 0,
            )
            for b in blocks
        ]
    
    return ProjectArchitecture(
        project_id=project.id,
        project_name=project.name,
        current_phase=project.current_phase,
        use_flexible_architecture=project.use_flexible_architecture,
        phases=phases,
        total_fields=total_fields,
        completed_fields=completed_fields,
        content_blocks=content_blocks,
    )


def get_phase_fields(project_id: str, phase: str, db: Optional[Session] = None) -> List[FieldInfo]:
    """
    获取某阶段的所有字段
    
    Args:
        project_id: 项目ID
        phase: 阶段名称
        db: 数据库会话
    
    Returns:
        字段信息列表
    """
    if db is None:
        db = next(get_db())
    
    fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
        ProjectField.phase == phase
    ).all()
    
    return [
        FieldInfo(
            id=f.id,
            name=f.name,
            phase=f.phase,
            status=f.status or "pending",
            content_preview=(f.content[:200] + "..." if f.content and len(f.content) > 200 else f.content or ""),
            has_content=bool(f.content and f.content.strip()),
            ai_prompt=f.ai_prompt,
            dependencies=f.dependencies.get("depends_on", []) if f.dependencies else [],
        )
        for f in fields
    ]


def get_field_content(project_id: str, field_name: str, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
    """
    根据字段名获取字段完整内容
    
    Args:
        project_id: 项目ID
        field_name: 字段名称
        db: 数据库会话
    
    Returns:
        字段详情字典或 None
    """
    if db is None:
        db = next(get_db())
    
    field = db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
        ProjectField.name == field_name
    ).first()
    
    if not field:
        return None
    
    return {
        "id": field.id,
        "name": field.name,
        "phase": field.phase,
        "status": field.status,
        "content": field.content,
        "ai_prompt": field.ai_prompt,
        "constraints": field.constraints,
        "dependencies": field.dependencies,
        "need_review": field.need_review,
    }


def get_content_block_tree(project_id: str, db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """
    获取项目的 ContentBlock 树形结构（灵活架构专用）
    
    Args:
        project_id: 项目ID
        db: 数据库会话
    
    Returns:
        嵌套的块结构列表
    """
    if db is None:
        db = next(get_db())
    
    # 获取所有顶层块
    root_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.parent_id == None
    ).order_by(ContentBlock.order_index).all()
    
    def block_to_dict(block: ContentBlock) -> Dict[str, Any]:
        return {
            "id": block.id,
            "name": block.name,
            "block_type": block.block_type,
            "status": block.status,
            "content_preview": (block.content[:100] + "..." if block.content and len(block.content) > 100 else block.content or ""),
            "depth": block.depth,
            "children": [block_to_dict(child) for child in block.children] if block.children else [],
        }
    
    return [block_to_dict(b) for b in root_blocks]


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
        f"架构类型: {'灵活架构' if arch.use_flexible_architecture else '传统流程'}",
        f"进度: {arch.completed_fields}/{arch.total_fields} 字段已完成",
        "",
        "### 阶段列表:",
    ]
    
    for phase in arch.phases:
        status_icon = "✅" if phase.status == "completed" else "🔄" if phase.status == "in_progress" else "⏳"
        lines.append(f"{status_icon} {phase.display_name} ({phase.field_count} 个字段)")
        
        if phase.fields:
            for field in phase.fields:
                field_icon = "📝" if field.has_content else "📄"
                lines.append(f"    {field_icon} {field.name}: {field.status}")
    
    if arch.content_blocks:
        lines.append("")
        lines.append("### 内容块结构（灵活架构）:")
        for block in arch.content_blocks:
            lines.append(f"  - {block.name} [{block.block_type}]: {block.status}")
    
    return "\n".join(lines)
