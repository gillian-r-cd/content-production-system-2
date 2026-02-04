# backend/core/models/block_history.py
# 功能: 内容块操作历史模型，用于撤回/重做
# 主要类: BlockHistory
# 数据结构: 保存操作快照，支持撤回删除等操作

"""
BlockHistory 模型
记录内容块的操作历史，支持撤回功能
"""

from typing import Optional, List

from sqlalchemy import String, Text, JSON, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import BaseModel


# 操作类型
HISTORY_ACTIONS = {
    "create": "创建",
    "update": "更新",
    "delete": "删除",
    "move": "移动",
}


class BlockHistory(BaseModel):
    """
    内容块操作历史
    
    用于记录每次操作，支持撤回功能：
    - 删除操作：保存完整快照，撤回时恢复
    - 更新操作：保存更新前快照，撤回时还原
    - 移动操作：保存原位置信息，撤回时复位
    
    Attributes:
        project_id: 所属项目 ID
        action: 操作类型（create/update/delete/move）
        block_id: 操作的内容块 ID
        block_snapshot: 操作前的完整块数据（JSON）
        children_snapshots: 子块快照列表（删除阶段时保存）
        undone: 是否已撤回
    """
    __tablename__ = "block_history"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False
    )
    
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    
    block_id: Mapped[str] = mapped_column(String(36), nullable=False)
    
    # 操作前的块快照
    block_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # 子块快照（删除时保存所有子块）
    children_snapshots: Mapped[list] = mapped_column(JSON, default=list)
    
    # 是否已撤回
    undone: Mapped[bool] = mapped_column(Boolean, default=False)
    
    def __repr__(self):
        return f"<BlockHistory {self.action} block={self.block_id[:8]}...>"
