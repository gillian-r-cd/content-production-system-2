# backend/core/models/simulation_record.py
# 功能: 模拟记录模型，存储每次消费者模拟的结果
# 主要类: SimulationRecord
# 数据结构: 存储模拟过程、反馈、评分

"""
模拟记录模型
记录每次消费者模拟的完整过程和结果
"""

from typing import Optional, Union, List, Dict, TYPE_CHECKING

from sqlalchemy import String, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.project import Project
    from core.models.simulator import Simulator


class SimulationRecord(BaseModel):
    """
    模拟记录
    
    Attributes:
        project_id: 所属项目
        simulator_id: 使用的模拟器
        target_field_ids: 被模拟的字段ID列表
        persona: 模拟使用的用户画像
            - source: "research" 或 "custom"
            - name: 人物名称
            - background: 背景描述
            - story: 人物小传
        interaction_log: 交互记录
            - 对话式: [{role: "user"|"assistant", content: "..."}]
            - 其他: {input: "...", output: "..."}
        feedback: 结构化反馈
            - scores: {维度: 分数}
            - comments: {维度: 评语}
            - overall: 总体评价
        status: 状态（pending/running/completed/failed）
    """
    __tablename__ = "simulation_records"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False
    )
    simulator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("simulators.id"), nullable=False
    )
    
    target_field_ids: Mapped[list] = mapped_column(JSON, default=list)
    persona: Mapped[dict] = mapped_column(
        JSON, default=lambda: {
            "source": "custom",
            "name": "",
            "background": "",
            "story": "",
        }
    )
    interaction_log: Mapped[Union[list, dict]] = mapped_column(JSON, default=list)
    feedback: Mapped[dict] = mapped_column(
        JSON, default=lambda: {
            "scores": {},
            "comments": {},
            "overall": "",
        }
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")

    # 关联
    project: Mapped["Project"] = relationship(
        "Project", back_populates="simulation_records"
    )
    simulator: Mapped["Simulator"] = relationship("Simulator")

    def get_average_score(self) -> Optional[float]:
        """计算平均分"""
        scores = self.feedback.get("scores", {})
        if not scores:
            return None
        return sum(scores.values()) / len(scores)

