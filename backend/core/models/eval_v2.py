# backend/core/models/eval_v2.py
# 功能: Eval V2 核心数据模型（Task 容器 + TrialConfig + TrialResult + TaskAnalysis）
# 主要类: EvalTaskV2, EvalTrialConfigV2, EvalTrialResultV2, TaskAnalysisV2
# 数据结构:
#   - EvalTaskV2: 项目级任务容器（不绑定 form_type）
#   - EvalTrialConfigV2: Task 下可独立配置的最小执行单元（含 form_type/repeat）
#   - EvalTrialResultV2: TrialConfig 的一次执行结果（含 LLM 调用日志）
#   - TaskAnalysisV2: 单个 Task 下跨 Trial 的模式分析与建议

"""
Eval V2 数据模型（并行新链路）

说明：
1) 该文件使用独立的 *_v2 表，避免破坏现有 EvalRun/EvalTask/EvalTrial 旧链路。
2) 新链路采用 Task 容器 + TrialConfig 最小配置单元，满足一 Task 内混合多 form。
"""

from __future__ import annotations

from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, JSON, ForeignKey, Integer, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.project import Project


EVAL_V2_TASK_STATUS = {
    "pending": "待执行",
    "running": "执行中",
    "completed": "已完成",
    "stale": "内容已变更",
    "failed": "失败",
}

EVAL_V2_FORM_TYPES = {
    "assessment": "直接判定",
    "review": "视角审查",
    "experience": "消费体验",
    "scenario": "场景模拟",
}


class EvalTaskV2(BaseModel):
    """
    评估任务（容器）
    一个 Task 下可包含多个不同 form_type 的 TrialConfig。
    """

    __tablename__ = "eval_tasks_v2"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    # 执行状态
    status: Mapped[str] = mapped_column(String(20), default="pending")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    last_executed_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")

    # 快速读取的最新聚合结果（最新 batch）
    latest_scores: Mapped[dict] = mapped_column(JSON, default=dict)   # {dimensions: {...}}
    latest_overall: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latest_batch_id: Mapped[str] = mapped_column(String(64), default="")

    trial_configs: Mapped[List["EvalTrialConfigV2"]] = relationship(
        "EvalTrialConfigV2",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="EvalTrialConfigV2.order_index",
    )
    trial_results: Mapped[List["EvalTrialResultV2"]] = relationship(
        "EvalTrialResultV2",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    analyses: Mapped[List["TaskAnalysisV2"]] = relationship(
        "TaskAnalysisV2",
        back_populates="task",
        cascade="all, delete-orphan",
    )


class EvalTrialConfigV2(BaseModel):
    """
    Trial 配置（最小执行单元）
    每个 TrialConfig 可独立设置 form_type / persona / grader / repeat_count。
    """

    __tablename__ = "eval_trial_configs_v2"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_tasks_v2.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    form_type: Mapped[str] = mapped_column(String(32), default="assessment")

    # 通用配置
    target_block_ids: Mapped[list] = mapped_column(JSON, default=list)
    grader_ids: Mapped[list] = mapped_column(JSON, default=list)
    grader_weights: Mapped[dict] = mapped_column(JSON, default=dict)  # {grader_id: float}
    repeat_count: Mapped[int] = mapped_column(Integer, default=1)
    probe: Mapped[str] = mapped_column(Text, default="")
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    # 形态特有配置（JSON）
    form_config: Mapped[dict] = mapped_column(JSON, default=dict)

    task: Mapped["EvalTaskV2"] = relationship("EvalTaskV2", back_populates="trial_configs")
    results: Mapped[List["EvalTrialResultV2"]] = relationship(
        "EvalTrialResultV2",
        back_populates="trial_config",
        cascade="all, delete-orphan",
    )


class EvalTrialResultV2(BaseModel):
    """
    Trial 的一次执行结果
    每个 result 对应某个 TrialConfig 的一次 repeat 执行。
    """

    __tablename__ = "eval_trial_results_v2"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_tasks_v2.id"), nullable=False, index=True
    )
    trial_config_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_trial_configs_v2.id"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False, index=True
    )

    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    repeat_index: Mapped[int] = mapped_column(Integer, default=0)
    form_type: Mapped[str] = mapped_column(String(32), default="assessment")

    # 过程数据（scenario 对话节点 / experience 分块探索）
    process: Mapped[list] = mapped_column(JSON, default=list)

    # Grader 评分结果（统一模型）
    grader_results: Mapped[list] = mapped_column(JSON, default=list)
    dimension_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # LLM 调用日志
    llm_calls: Mapped[list] = mapped_column(JSON, default=list)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")

    task: Mapped["EvalTaskV2"] = relationship("EvalTaskV2", back_populates="trial_results")
    trial_config: Mapped["EvalTrialConfigV2"] = relationship(
        "EvalTrialConfigV2",
        back_populates="results",
    )


class TaskAnalysisV2(BaseModel):
    """
    Task 级跨 Trial 分析结果（可选）
    """

    __tablename__ = "task_analyses_v2"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_tasks_v2.id"), nullable=False, index=True
    )
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    patterns: Mapped[list] = mapped_column(JSON, default=list)
    suggestions: Mapped[list] = mapped_column(JSON, default=list)
    strengths: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")

    llm_calls: Mapped[list] = mapped_column(JSON, default=list)
    cost: Mapped[float] = mapped_column(Float, default=0.0)

    task: Mapped["EvalTaskV2"] = relationship("EvalTaskV2", back_populates="analyses")

