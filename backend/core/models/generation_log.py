# backend/core/models/generation_log.py
# 功能: 生成日志模型，记录每次LLM调用
# 主要类: GenerationLog
# 数据结构: 存储输入输出、token数、耗时、成本

"""
生成日志模型
记录每一次大模型调用的详细信息，用于调试和成本分析
"""

from sqlalchemy import String, Text, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel


class GenerationLog(BaseModel):
    """
    生成日志
    
    Attributes:
        project_id: 所属项目
        field_id: 相关字段ID（如有）
        phase: 所属阶段
        operation: 操作类型（如generate_field, evaluate, simulate等）
        
        model: 使用的模型
        prompt_input: 完整输入（系统提示+用户输入）
        prompt_output: 完整输出
        
        tokens_in: 输入token数
        tokens_out: 输出token数
        duration_ms: 耗时（毫秒）
        cost: 成本（美元）
        
        status: 状态（success/failed）
        error_message: 错误信息（如有）
    """
    __tablename__ = "generation_logs"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False
    )
    field_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    phase: Mapped[str] = mapped_column(String(50), default="")
    operation: Mapped[str] = mapped_column(String(50), default="")

    model: Mapped[str] = mapped_column(String(50), default="gpt-5.1")
    prompt_input: Mapped[str] = mapped_column(Text, default="")
    prompt_output: Mapped[str] = mapped_column(Text, default="")

    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[str] = mapped_column(String(20), default="success")
    error_message: Mapped[str] = mapped_column(Text, default="")

    # 关联
    project: Mapped["Project"] = relationship(
        "Project", back_populates="generation_logs"
    )

    @classmethod
    def calculate_cost(
        cls,
        model: str,
        tokens_in: int,
        tokens_out: int
    ) -> float:
        """
        计算API调用成本
        基于OpenAI定价（2026年）
        """
        # GPT定价（每1M tokens）
        pricing = {
            "gpt-5.1": {"input": 5.00, "output": 15.00},  # GPT-5.1定价（预估）
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        }
        
        if model not in pricing:
            model = "gpt-5.1"  # 默认
        
        cost_in = (tokens_in / 1_000_000) * pricing[model]["input"]
        cost_out = (tokens_out / 1_000_000) * pricing[model]["output"]
        
        return round(cost_in + cost_out, 6)

