# backend/core/models/memory_item.py
# 功能: 项目记忆条目模型 — 从对话中提炼的可复用知识（跨模式、跨阶段）
# 主要类: MemoryItem
# 数据结构: memory_items 表，project_id 关联项目（NULL=全局通用记忆），全量注入到 system prompt
# 关联: memory_service.py (提炼), api/agent.py (注入), orchestrator.py (build_system_prompt)

"""
项目记忆条目

从 Agent 对话中自动提炼的关键信息，跨模式、跨阶段可见。
设计原则：
- 不设 embedding — 全量注入，不需要向量检索
- 不设硬编码分类 — 让 LLM 自由提炼
- project_id 隔离 — 每个项目独立记忆空间
- project_id 可为 NULL — 表示跨项目通用记忆（如创作者全局偏好）
"""

from typing import Optional

from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from core.models.base import BaseModel


class MemoryItem(BaseModel):
    """项目记忆条目 — 从对话中提炼的可复用知识"""
    __tablename__ = "memory_items"

    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True, index=True,
        comment="所属项目（NULL=全局通用记忆）",
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="记忆内容（一句话，如'用户偏好口语化表达'）",
    )
    source_mode: Mapped[str] = mapped_column(
        String(50), nullable=False, default="assistant",
        comment="提炼来源模式（如 assistant, critic）",
    )
    source_phase: Mapped[str] = mapped_column(
        String(50), nullable=False, default="",
        comment="提炼时所在阶段（如 intent, content_core）",
    )
    related_blocks: Mapped[list] = mapped_column(
        JSON, default=list,
        comment="相关内容块名列表（如 ['场景库', '意图分析']）",
    )

