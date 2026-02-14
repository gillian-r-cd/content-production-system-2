# backend/core/models/agent_mode.py
# 功能: Agent 运行模式定义 — 控制 Agent 的身份段和行为偏好
# 主要类: AgentMode
# 数据结构: agent_modes 表，存储系统预置和用户自定义的 Agent 模式
# 关联: orchestrator.py (build_system_prompt), api/agent.py (stream_chat), api/modes.py (CRUD)

"""
Agent 模式模型

模式 = System Prompt 的身份段 + 行为偏好指令。
模式不改变 Agent 的能力边界（工具集不变），只改变 Agent 的视角、语气、侧重点。
所有模式走同一个 Agent Graph。
"""

from sqlalchemy import String, Text, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import BaseModel


class AgentMode(BaseModel):
    """Agent 运行模式"""
    __tablename__ = "agent_modes"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="唯一标识，如 assistant, strategist, critic")
    display_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="显示名，如 助手, 策略顾问, 审稿人")
    description: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="简短描述（前端 tooltip 用）")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="身份段 prompt（替换 build_system_prompt 的开头）")
    icon: Mapped[str] = mapped_column(String(10), nullable=False, default="🤖", comment="emoji 图标")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否系统内置（不可删除）")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="前端排列顺序")
