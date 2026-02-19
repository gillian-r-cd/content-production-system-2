# backend/core/models/eval_suggestion_state.py
# 功能: 持久化 Eval 报告中“让Agent修改”建议的处理状态

from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import BaseModel


class EvalSuggestionState(BaseModel):
    __tablename__ = "eval_suggestion_states"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_tasks_v2.id"), nullable=False, index=True
    )
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    source: Mapped[str] = mapped_column(String(300), default="")
    suggestion: Mapped[str] = mapped_column(Text, default="")
    suggestion_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="applied")


