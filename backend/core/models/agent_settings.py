# backend/core/models/agent_settings.py
# 功能: Agent设置模型
# 主要类: AgentSettings
# 数据结构: 存储Agent可用工具、技能、工具提示词

"""
Agent设置模型
管理Agent的工具、技能和默认行为配置
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from core.models.base import BaseModel


class AgentSettings(BaseModel):
    """
    Agent设置（全局单例）
    
    Attributes:
        name: 配置名称（默认"default"）
        tools: 启用的工具列表
        skills: 自定义技能列表
        tool_prompts: 各工具的自定义提示词 {tool_id: prompt}
    """
    __tablename__ = "agent_settings"

    name: Mapped[str] = mapped_column(String(50), default="default", unique=True)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    # [已废弃] 自主权默认设置，不再使用，保留用于数据库兼容
    autonomy_defaults: Mapped[dict] = mapped_column(JSON, default=dict)
    tool_prompts: Mapped[dict] = mapped_column(JSON, default=dict)


