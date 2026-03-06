# backend/core/models/project_structure_draft.py
# 功能: 项目级结构草稿模型，持久化自动拆分内容的拆分配置、编排草稿与应用元数据
# 主要类: ProjectStructureDraft
# 数据结构: project_id + draft_type 唯一的正式草稿对象，承载 source_text / split_config / draft_payload / validation_errors

"""
项目级结构草稿模型

这层模型专门承载“拆分 + 编排”阶段的正式持久化状态：
- 运行态项目树仍然统一落到 ContentBlock
- 草稿态结构使用 JSON payload 保存，避免污染 Project / ContentBlock
- 同一项目下，先按 draft_type 保持唯一草稿
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.project import Project


PROJECT_STRUCTURE_DRAFT_TYPES = {
    "auto_split": "项目自动拆分内容",
}

PROJECT_STRUCTURE_DRAFT_STATUS = {
    "draft": "草稿中",
    "validated": "已校验",
    "applied": "已应用",
}


def default_split_config() -> dict:
    return {
        "mode": "count",
        "target_count": 3,
        "max_chars_per_chunk": 1200,
        "overlap_chars": 0,
        "rule_prompt": "",
        "title_prefix": "",
    }


def default_draft_payload() -> dict:
    return {
        "chunks": [],
        "plans": [],
        "shared_root_nodes": [],
        "aggregate_root_nodes": [],
        "ui_state": {},
    }


class ProjectStructureDraft(BaseModel):
    """项目级结构草稿。"""

    __tablename__ = "project_structure_drafts"
    __table_args__ = (
        UniqueConstraint("project_id", "draft_type", name="uq_project_structure_drafts_project_type"),
    )

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False
    )
    draft_type: Mapped[str] = mapped_column(String(50), default="auto_split")
    name: Mapped[str] = mapped_column(String(200), default="自动拆分内容")
    status: Mapped[str] = mapped_column(String(50), default="draft")

    source_text: Mapped[str] = mapped_column(Text, default="")
    split_config: Mapped[dict] = mapped_column(JSON, default=default_split_config)
    draft_payload: Mapped[dict] = mapped_column(JSON, default=default_draft_payload)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    apply_count: Mapped[int] = mapped_column(Integer, default=0)
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped["Project"] = relationship(
        "Project", back_populates="structure_drafts"
    )
