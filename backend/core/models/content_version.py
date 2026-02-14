# backend/core/models/content_version.py
# 功能: 内容版本历史模型，记录字段每次生成/修改前的内容快照
# 主要类: ContentVersion
# 数据结构: block_id + version_number + content + source(手动/AI生成/Agent修改)

"""
ContentVersion 模型
记录 ContentBlock 的内容历史版本
每次「重新生成」或「Agent 修改」前，自动保存当前内容为一个版本
"""

from typing import Optional

from sqlalchemy import String, Text, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import BaseModel


# 版本来源类型
VERSION_SOURCES = {
    "manual": "手动编辑",
    "ai_generate": "AI 生成",
    "ai_regenerate": "重新生成",
    "agent": "Agent 修改",
    "rollback": "版本回滚",
}


class ContentVersion(BaseModel):
    """
    内容版本历史

    每次内容发生变更（重新生成、Agent修改、手动编辑保存）时，
    将变更前的内容保存为一个版本快照。

    Attributes:
        block_id: 关联的 ContentBlock 的 ID
        version_number: 版本号（从 1 开始递增）
        content: 该版本的完整内容
        source: 产生该版本的来源（manual/ai_generate/ai_regenerate/agent）
        source_detail: 来源补充说明（如 Agent 消息摘要）
    """
    __tablename__ = "content_versions"

    block_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )

    version_number: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    content: Mapped[str] = mapped_column(
        Text, default=""
    )

    source: Mapped[str] = mapped_column(
        String(50), default="manual"
    )

    source_detail: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    def __repr__(self):
        return f"<ContentVersion block={self.block_id[:8]}... v{self.version_number} ({self.source})>"
