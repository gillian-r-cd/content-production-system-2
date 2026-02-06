# backend/core/models/eval_trial.py
# 功能: 评估试验模型，一次 EvalTask 的实际执行记录
# 主要类: EvalTrial
# 数据结构:
#   - eval_task_id: 关联的 EvalTask（新增）
#   - llm_calls: 完整的 LLM 调用日志（新增，每次调用的输入/输出/token/耗时）
#   - nodes: 交互节点列表（对话记录）
#   - result: 评分结果
#   - grader_outputs: Grader 输出（内容评分 + 过程评分）

"""
EvalTrial 模型
一个 Trial = 一个 EvalTask 的一次实际执行
记录完整的交互过程和每一次 LLM 调用的输入输出
"""

from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, JSON, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.eval_run import EvalRun
    from core.models.eval_task import EvalTask


# Trial 状态
EVAL_TRIAL_STATUS = {
    "pending": "待运行",
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
}


class EvalTrial(BaseModel):
    """
    评估试验 - 一次 EvalTask 的实际执行
    
    Attributes:
        eval_run_id: 关联的 EvalRun（保留向后兼容）
        eval_task_id: 关联的 EvalTask（新增）
        role: 角色类型 (coach/editor/expert/consumer/seller)
        role_config: 角色配置
        interaction_mode: 交互模式 (review/dialogue/scenario)
        input_block_ids: 评估的内容块 ID 列表
        persona: 使用的人物画像
        nodes: 交互节点列表
            - [{ role, content, timestamp, turn, node_score? }]
        result: 评分结果
            - scores: {维度: 分数}
            - comments: {维度: 评语}
            - outcome: 结果判定
            - summary: 总结
        grader_outputs: Grader 输出列表
            - [{ grader_type: "content"/"process", scores, analysis, ... }]
        llm_calls: 完整的 LLM 调用日志（新增）
            - [{
                step: "simulator" / "grader_content" / "grader_process" / "consumer_turn_1" / ...
                input: { system_prompt, user_message },
                output: "AI 响应内容",
                tokens_in, tokens_out, cost, duration_ms,
                timestamp
              }]
        overall_score: 综合评分 (1-10)
        status: 状态
        error: 错误信息
        tokens_in: 总输入 tokens
        tokens_out: 总输出 tokens
        cost: 总费用
    """
    __tablename__ = "eval_trials"

    eval_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_runs.id"), nullable=False
    )
    
    # 新增：关联到 EvalTask
    eval_task_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("eval_tasks.id"), nullable=True
    )
    
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    role_config: Mapped[dict] = mapped_column(JSON, default=dict)
    interaction_mode: Mapped[str] = mapped_column(String(50), default="review")
    
    input_block_ids: Mapped[list] = mapped_column(JSON, default=list)
    persona: Mapped[dict] = mapped_column(JSON, default=dict)
    
    nodes: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict] = mapped_column(
        JSON, default=lambda: {
            "scores": {},
            "comments": {},
            "outcome": "",
            "summary": "",
        }
    )
    grader_outputs: Mapped[list] = mapped_column(JSON, default=list)
    
    # 新增：完整的 LLM 调用日志
    llm_calls: Mapped[list] = mapped_column(JSON, default=list)
    
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")
    
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)

    # 关联
    eval_run: Mapped["EvalRun"] = relationship(
        "EvalRun", back_populates="trials"
    )
    eval_task: Mapped[Optional["EvalTask"]] = relationship(
        "EvalTask", back_populates="trials"
    )

    def get_average_score(self) -> float:
        """计算平均评分"""
        scores = self.result.get("scores", {})
        if not scores:
            return 0.0
        numeric_scores = [v for v in scores.values() if isinstance(v, (int, float))]
        return sum(numeric_scores) / len(numeric_scores) if numeric_scores else 0.0
