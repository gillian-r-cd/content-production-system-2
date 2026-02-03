# backend/core/models/project.py
# 功能: 项目模型，内容生产的核心实体
# 主要类: Project
# 数据结构: 存储项目配置、阶段状态、Agent自主权设置等

"""
项目模型
每个项目代表一次完整的内容生产过程
支持版本管理：修改前面字段时创建新版本
"""

from sqlalchemy import String, Text, Integer, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel


# 项目阶段定义
PROJECT_PHASES = [
    "intent",        # 意图分析
    "research",      # 消费者调研
    "design_inner",  # 内涵设计
    "produce_inner", # 内涵生产
    "design_outer",  # 外延设计
    "produce_outer", # 外延生产
    "simulate",      # 消费者模拟
    "evaluate",      # 评估
]

# 阶段状态
PHASE_STATUS = {
    "pending": "未开始",
    "in_progress": "进行中",
    "completed": "已完成",
}


class Project(BaseModel):
    """
    内容生产项目
    
    Attributes:
        creator_profile_id: 关联的创作者特质
        name: 项目名称
        version: 版本号（从1开始）
        version_note: 版本说明
        parent_version_id: 父版本ID（用于版本追溯）
        current_phase: 当前阶段
        phase_order: 阶段顺序（可拖拽调整内涵/外延的顺序）
        phase_status: 每个阶段的状态
        agent_autonomy: Agent自主权设置，每阶段是否需人工确认
        golden_context: 缓存的Golden Context（意图+用户画像）
        use_deep_research: 是否使用DeepResearch进行调研
    """
    __tablename__ = "projects"

    creator_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("creator_profiles.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    version_note: Mapped[str] = mapped_column(Text, default="")
    parent_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True
    )
    
    current_phase: Mapped[str] = mapped_column(
        String(50), default="intent"
    )
    phase_order: Mapped[list] = mapped_column(
        JSON, default=lambda: PROJECT_PHASES.copy()
    )
    phase_status: Mapped[dict] = mapped_column(
        JSON, default=lambda: {phase: "pending" for phase in PROJECT_PHASES}
    )
    agent_autonomy: Mapped[dict] = mapped_column(
        JSON, default=lambda: {phase: True for phase in PROJECT_PHASES}  # 默认都需要确认
    )
    golden_context: Mapped[dict] = mapped_column(JSON, default=dict)
    use_deep_research: Mapped[bool] = mapped_column(default=True)

    # 关联
    creator_profile: Mapped["CreatorProfile"] = relationship(
        "CreatorProfile", back_populates="projects"
    )
    fields: Mapped[list["ProjectField"]] = relationship(
        "ProjectField", back_populates="project", cascade="all, delete-orphan"
    )
    simulation_records: Mapped[list["SimulationRecord"]] = relationship(
        "SimulationRecord", back_populates="project", cascade="all, delete-orphan"
    )
    evaluation_reports: Mapped[list["EvaluationReport"]] = relationship(
        "EvaluationReport", back_populates="project", cascade="all, delete-orphan"
    )
    generation_logs: Mapped[list["GenerationLog"]] = relationship(
        "GenerationLog", back_populates="project", cascade="all, delete-orphan"
    )

    def get_phase_index(self, phase: str) -> int:
        """获取阶段在顺序中的索引"""
        try:
            return self.phase_order.index(phase)
        except ValueError:
            return -1

    def get_next_phase(self) -> str | None:
        """获取下一个阶段"""
        current_idx = self.get_phase_index(self.current_phase)
        if current_idx < 0 or current_idx >= len(self.phase_order) - 1:
            return None
        return self.phase_order[current_idx + 1]

    def needs_human_confirm(self, phase: str = None) -> bool:
        """检查指定阶段是否需要人工确认"""
        phase = phase or self.current_phase
        return self.agent_autonomy.get(phase, True)

