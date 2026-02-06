# backend/core/models/eval_trial.py
# 功能: 评估试验模型，一次角色评估的完整记录
# 主要类: EvalTrial
# 数据结构: 存储角色配置、交互日志、评分结果

"""
EvalTrial 模型
一个 Trial = 一个角色对一组内容的一次评估
"""

from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, JSON, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.eval_run import EvalRun


# Trial 状态
EVAL_TRIAL_STATUS = {
    "pending": "待运行",
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
}


class EvalTrial(BaseModel):
    """
    评估试验
    
    Attributes:
        eval_run_id: 关联的 EvalRun
        role: 角色类型 (coach/editor/expert/consumer/seller)
        role_config: 角色配置
            - system_prompt: 系统提示词
            - knowledge_boundary: 知识边界描述
        interaction_mode: 交互模式 (review/dialogue/scenario)
        input_block_ids: 评估的内容块 ID 列表
        persona: 使用的人物画像 (消费者/销售角色)
            - name: 名称
            - background: 背景
            - story: 故事
        nodes: 交互节点列表
            - [{ role, content, timestamp, node_score? }]
        result: 评分结果
            - scores: {维度: 分数}
            - comments: {维度: 评语}
            - outcome: 结果判定
            - summary: 总结
        grader_outputs: Grader 输出
            - [{ grader_type, level, scores, analysis }]
        overall_score: 综合评分 (1-10)
        status: 状态
        error: 错误信息
        tokens_in: 输入 tokens
        tokens_out: 输出 tokens
        cost: 费用
    """
    __tablename__ = "eval_trials"

    eval_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_runs.id"), nullable=False
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

    def get_average_score(self) -> float:
        """计算平均评分"""
        scores = self.result.get("scores", {})
        if not scores:
            return 0.0
        numeric_scores = [v for v in scores.values() if isinstance(v, (int, float))]
        return sum(numeric_scores) / len(numeric_scores) if numeric_scores else 0.0
