# backend/core/models/conversation.py
# 功能: Agent 会话模型（按 project + mode 维护可切换会话）
# 主要类: Conversation
# 数据结构: 会话元数据（标题、状态、启动策略、最后消息时间、消息数）

"""
Agent 会话模型。

用于支持 Agent Panel 的历史会话列表、会话切换与继续旧会话对话。
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, ForeignKey, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.project import Project
    from core.models.chat_history import ChatMessage


class Conversation(BaseModel):
    """
    Agent 会话。

    Attributes:
        project_id: 所属项目 ID
        mode: 所属模式（assistant / critic / strategist ...）
        title: 会话标题（可由前端重命名）
        status: 会话状态（active | archived）
        bootstrap_policy: 新会话上下文启动策略（当前支持 memory_only）
        last_message_at: 最近一条消息时间（用于列表排序）
        message_count: 会话消息数（列表展示优化）
    """

    __tablename__ = "conversations"
    __table_args__ = (
        Index("idx_conversations_project_mode_lastmsg", "project_id", "mode", "last_message_at"),
        Index("idx_conversations_project_mode_status", "project_id", "mode", "status"),
    )

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(50), nullable=False, default="assistant")
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    bootstrap_policy: Mapped[str] = mapped_column(String(30), nullable=False, default="memory_only")
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 关联
    project: Mapped["Project"] = relationship("Project")
    messages: Mapped[list["ChatMessage"]] = relationship("ChatMessage", back_populates="conversation")

