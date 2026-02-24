# backend/core/models/chat_history.py
# 功能: Agent对话历史模型
# 主要类: ChatMessage
# 数据结构: 存储每条对话消息、角色、时间、是否编辑过

"""
Agent对话历史模型
记录与Agent的每条对话，支持历史加载、编辑重发
"""

from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, JSON, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.project import Project
    from core.models.conversation import Conversation


class ChatMessage(BaseModel):
    """
    对话消息
    
    Attributes:
        project_id: 所属项目
        role: 角色 ("user" | "assistant")
        content: 消息内容
        original_content: 原始内容（编辑重发时保留）
        is_edited: 是否被编辑过
        metadata: 附加信息
            - phase: 当前阶段
            - tool_used: 使用的工具
            - skill_used: 使用的技能
            - references: @引用的字段
        parent_message_id: 父消息ID（重新生成时指向原消息）
    """
    __tablename__ = "chat_messages"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("conversations.id"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    original_content: Mapped[str] = mapped_column(Text, default="")
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    message_metadata: Mapped[dict] = mapped_column(
        JSON, default=lambda: {
            "phase": "",
            "tool_used": None,
            "skill_used": None,
            "references": [],
        }
    )
    parent_message_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("chat_messages.id"), nullable=True
    )

    # 关联
    project: Mapped["Project"] = relationship("Project")
    conversation: Mapped[Optional["Conversation"]] = relationship("Conversation", back_populates="messages")

