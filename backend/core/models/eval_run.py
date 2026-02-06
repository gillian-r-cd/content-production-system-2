# backend/core/models/eval_run.py
# 功能: 评估运行模型，追踪一次完整的评估
# 主要类: EvalRun
# 数据结构: 存储评估配置、状态、综合结果

"""
EvalRun 模型
一次完整的评估运行，包含多个 EvalTrial
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Text, JSON, ForeignKey, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.project import Project
    from core.models.eval_trial import EvalTrial


# 评估运行状态
EVAL_RUN_STATUS = {
    "pending": "待运行",
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
}

# 可用的评估角色
EVAL_ROLES = {
    "coach": {
        "name": "教练",
        "description": "策略视角：内容方向是否正确？意图是否对齐？",
        "icon": "🎯",
        "default_dimensions": ["策略对齐度", "定位清晰度", "差异化程度"],
    },
    "editor": {
        "name": "编辑",
        "description": "手艺视角：内容质量是否过关？结构是否合理？",
        "icon": "✍️",
        "default_dimensions": ["结构合理性", "语言质量", "可读性", "一致性"],
    },
    "expert": {
        "name": "领域专家",
        "description": "专业视角：内容是否准确？是否具有专业性？",
        "icon": "🔬",
        "default_dimensions": ["事实准确性", "专业深度", "数据支撑", "市场相关性"],
    },
    "consumer": {
        "name": "消费者",
        "description": "用户视角：内容对我有用吗？能解决我的问题吗？",
        "icon": "👤",
        "default_dimensions": ["需求匹配度", "理解难度", "价值感知", "行动意愿"],
    },
    "seller": {
        "name": "内容销售",
        "description": "转化视角：能把这个内容卖出去吗？",
        "icon": "💰",
        "default_dimensions": ["价值传达", "需求匹配", "异议处理", "转化结果"],
    },
}


class EvalRun(BaseModel):
    """
    评估运行
    
    Attributes:
        project_id: 所属项目
        name: 评估名称
        config: 运行配置
            - model: AI模型
            - max_turns: 最大对话轮数
            - roles: 使用的角色列表
            - input_scope: 评估范围 ("all" / 具体 block_ids)
        status: 运行状态
        summary: AI 综合诊断
        overall_score: 综合评分 (1-10)
        role_scores: 各角色评分 {role: score}
        trial_count: Trial 总数
        content_block_id: 关联的 ContentBlock ID（eval结果写入到block）
    """
    __tablename__ = "eval_runs"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), default="评估运行")
    
    config: Mapped[dict] = mapped_column(
        JSON, default=lambda: {
            "model": "default",
            "max_turns": 8,
            "roles": ["coach", "editor", "expert", "consumer", "seller"],
            "input_scope": "all",  # "all" or list of block_ids
        }
    )
    
    status: Mapped[str] = mapped_column(String(20), default="pending")
    summary: Mapped[str] = mapped_column(Text, default="")
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    role_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    trial_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 关联到 ContentBlock（评估结果写入此块）
    content_block_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )

    # 关联
    project: Mapped["Project"] = relationship("Project")
    trials: Mapped[List["EvalTrial"]] = relationship(
        "EvalTrial", back_populates="eval_run",
        cascade="all, delete-orphan"
    )

    def get_completed_trials(self) -> List["EvalTrial"]:
        """获取已完成的 Trial"""
        return [t for t in self.trials if t.status == "completed"]
    
    def calculate_overall_score(self) -> float:
        """计算综合评分"""
        completed = self.get_completed_trials()
        if not completed:
            return 0.0
        
        total = sum(t.overall_score or 0 for t in completed)
        return round(total / len(completed), 2)
