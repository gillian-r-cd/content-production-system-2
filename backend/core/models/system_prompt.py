# backend/core/models/system_prompt.py
# 功能: 系统提示词模型
# 主要类: SystemPrompt
# 数据结构: 存储各阶段的系统提示词

"""
系统提示词模型
管理各阶段的系统提示词：意图分析、消费者调研、内涵生产、外延生产等
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import BaseModel


class SystemPrompt(BaseModel):
    """
    系统提示词
    
    Attributes:
        name: 提示词名称
        phase: 所属阶段
        content: 提示词内容
        description: 描述
    """
    __tablename__ = "system_prompts"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phase: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")

