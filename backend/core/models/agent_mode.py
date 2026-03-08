# backend/core/models/agent_mode.py
# 功能: Agent 角色/模式定义 — 控制 Agent 的身份段和行为偏好
# 主要类: AgentMode
# 数据结构: agent_modes 表，统一承载系统模板和项目级角色实例
# 关联: orchestrator.py (build_system_prompt), api/agent.py (stream_chat), api/modes.py (CRUD)

"""
Agent 模式模型

模式 = System Prompt 的身份段 + 行为偏好指令。
它不改变 Agent 的能力边界（工具集不变），只改变 Agent 的视角、语气、侧重点。
系统模板和项目级角色实例共用同一张表：
- project_id IS NULL 且 is_template=True: 系统模板
- project_id IS NOT NULL 且 is_template=False: 项目角色实例
"""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text, Boolean, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.project import Project


class AgentMode(BaseModel):
    """Agent 运行模式/角色定义"""
    __tablename__ = "agent_modes"

    project_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("projects.id"),
        nullable=True,
        index=True,
        comment="所属项目；NULL 表示系统模板",
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="内部稳定键；用户不直接编辑")
    display_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="显示名，如 助手, 策略顾问, 审稿人")
    description: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="简短描述（前端 tooltip 用）")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="身份段 prompt（替换 build_system_prompt 的开头）")
    icon: Mapped[str] = mapped_column(String(10), nullable=False, default="🤖", comment="emoji 图标")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否系统内置（不可删除）")
    is_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否模板；模板不直接作为项目运行时角色")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="前端排列顺序")

    project: Mapped[Optional["Project"]] = relationship("Project")
