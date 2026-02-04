# backend/core/models/content_block.py
# 功能: 统一的内容块模型，替代固定的阶段结构
# 主要类: ContentBlock
# 数据结构: 支持无限层级的树形内容结构

"""
ContentBlock 模型
统一抽象所有流程阶段和字段为可配置的内容块
支持无限层级、依赖引用、拖拽排序
"""

from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

from sqlalchemy import String, Text, JSON, ForeignKey, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.project import Project


# 内容块类型
BLOCK_TYPES = {
    "phase": "阶段",        # 顶级流程阶段
    "field": "字段",        # 具体内容字段
    "proposal": "方案",     # 设计方案（如内涵设计的多个方案）
    "group": "分组",        # 纯分组，无内容
}

# 特殊处理器类型
SPECIAL_HANDLERS = {
    "intent": "意图分析",
    "research": "消费者调研",
    "simulate": "消费者模拟",
    "evaluate": "项目评估",
}

# 内容块状态
BLOCK_STATUS = {
    "pending": "待处理",
    "in_progress": "进行中",
    "completed": "已完成",
    "failed": "失败",
}


class ContentBlock(BaseModel):
    """
    统一内容块模型
    
    用于表示项目中的任何内容单元：
    - 流程阶段（如意图分析、消费者调研）
    - 内容字段（如核心论点、案例故事）
    - 设计方案（如内涵设计的方案一、方案二）
    
    Attributes:
        project_id: 所属项目
        parent_id: 父级内容块ID（null=顶级阶段）
        name: 内容块名称
        block_type: 类型（phase/field/proposal/group）
        depth: 层级深度（0=顶级）
        order_index: 同级排序索引
        content: 实际内容
        status: 状态
        ai_prompt: AI生成提示词
        constraints: 生成约束配置
        depends_on: 依赖的其他内容块ID列表
        special_handler: 特殊处理器（intent/research/simulate/evaluate）
        need_review: 是否需要人工确认
        is_collapsed: UI是否折叠显示
    """
    __tablename__ = "content_blocks"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("content_blocks.id"), nullable=True
    )
    
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    block_type: Mapped[str] = mapped_column(String(50), default="field")
    
    # 层级与排序
    depth: Mapped[int] = mapped_column(Integer, default=0)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    
    # 内容
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    
    # AI 配置
    ai_prompt: Mapped[str] = mapped_column(Text, default="")
    constraints: Mapped[dict] = mapped_column(
        JSON, default=lambda: {
            "max_length": None,
            "output_format": "markdown",
            "structure": None,
            "example": None,
        }
    )
    
    # 依赖关系
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    
    # 特殊处理
    special_handler: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    
    # 控制
    need_review: Mapped[bool] = mapped_column(Boolean, default=True)
    is_collapsed: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # 软删除：deleted_at 有值表示已删除
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, default=None
    )
    
    # 关联
    project: Mapped["Project"] = relationship(
        "Project", back_populates="content_blocks"
    )
    
    # 自关联：父子关系
    parent: Mapped[Optional["ContentBlock"]] = relationship(
        "ContentBlock",
        remote_side="ContentBlock.id",
        back_populates="children",
        foreign_keys=[parent_id],
    )
    children: Mapped[List["ContentBlock"]] = relationship(
        "ContentBlock",
        back_populates="parent",
        foreign_keys=[parent_id],
        order_by="ContentBlock.order_index",
    )

    def is_phase(self) -> bool:
        """是否是顶级阶段"""
        return self.block_type == "phase" and self.parent_id is None
    
    def is_special(self) -> bool:
        """是否有特殊处理器"""
        return self.special_handler is not None
    
    def get_ancestors(self) -> List["ContentBlock"]:
        """获取所有祖先节点（从直接父级到根）"""
        ancestors = []
        current = self.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors
    
    def get_all_descendants(self) -> List["ContentBlock"]:
        """获取所有后代节点（深度优先）"""
        descendants = []
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_all_descendants())
        return descendants
    
    def get_dependency_content(self, blocks_by_id: dict) -> str:
        """
        获取依赖内容块的内容作为上下文
        
        Args:
            blocks_by_id: {block_id: ContentBlock} 映射
        
        Returns:
            依赖内容的格式化字符串
        """
        if not self.depends_on:
            return ""
        
        context_parts = []
        for dep_id in self.depends_on:
            if dep_id in blocks_by_id:
                dep_block = blocks_by_id[dep_id]
                if dep_block.content:
                    context_parts.append(
                        f"## {dep_block.name}\n{dep_block.content}"
                    )
        
        return "\n\n".join(context_parts)
    
    def can_generate(self, completed_block_ids: set) -> bool:
        """
        检查是否可以生成（依赖是否满足）
        
        Args:
            completed_block_ids: 已完成的内容块ID集合
        """
        if not self.depends_on:
            return True
        return all(dep_id in completed_block_ids for dep_id in self.depends_on)
    
    def to_tree_dict(self) -> dict:
        """转换为树形字典（用于 API 响应）"""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "block_type": self.block_type,
            "depth": self.depth,
            "order_index": self.order_index,
            "content": self.content,
            "status": self.status,
            "ai_prompt": self.ai_prompt,
            "constraints": self.constraints,
            "depends_on": self.depends_on,
            "special_handler": self.special_handler,
            "need_review": self.need_review,
            "is_collapsed": self.is_collapsed,
            "children": [child.to_tree_dict() for child in self.children],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
