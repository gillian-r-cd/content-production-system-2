# backend/core/models/phase_template.py
# 功能: 阶段模板模型，用于预设流程结构
# 主要类: PhaseTemplate
# 数据结构: 存储模板名称、描述和阶段定义列表

"""
阶段模板模型
用于存储预设的流程模板，用户可以选择应用到项目中
"""

from sqlalchemy import String, Text, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from core.localization import DEFAULT_LOCALE
from core.models.base import BaseModel
from core.template_schema import instantiate_template_nodes, phase_template_to_root_nodes


# 默认流程模板定义
DEFAULT_PHASE_TEMPLATE = {
    "id": "default_content_production",
    "name": "标准内容生产流程",
    "description": "适用于大多数内容生产场景的完整流程，包含意图分析、消费者调研、内涵设计与生产、外延设计与生产和评估。",
    "phases": [
        {
            "name": "意图分析",
            "block_type": "phase",
            "special_handler": "intent",
            "order_index": 0,
            "default_fields": [
                {
                    "name": "项目意图",
                    "block_type": "field",
                    "ai_prompt": "根据用户的三轮提问回答，生成结构化的意图分析。",
                }
            ]
        },
        {
            "name": "消费者调研",
            "block_type": "phase",
            "special_handler": "research",
            "order_index": 1,
            "default_fields": [
                {
                    "name": "消费者调研报告",
                    "block_type": "field",
                    "ai_prompt": "基于项目意图进行深度消费者调研。",
                }
            ]
        },
        {
            "name": "内涵设计",
            "block_type": "phase",
            "special_handler": None,
            "order_index": 2,
            "default_fields": []  # 内涵设计的字段由AI生成
        },
        {
            "name": "内涵生产",
            "block_type": "phase",
            "special_handler": "produce_inner",
            "order_index": 3,
            "default_fields": []  # 从内涵设计继承
        },
        {
            "name": "外延设计",
            "block_type": "phase",
            "special_handler": None,
            "order_index": 4,
            "default_fields": []
        },
        {
            "name": "外延生产",
            "block_type": "phase",
            "special_handler": "produce_outer",
            "order_index": 5,
            "default_fields": []
        },
        {
            "name": "评估",
            "block_type": "phase",
            "special_handler": "evaluate",
            "order_index": 6,
            "default_fields": []
        },
    ]
}


class PhaseTemplate(BaseModel):
    """
    阶段模板
    
    用于存储预设的流程模板，用户可以选择应用到项目中。
    
    Attributes:
        name: 模板名称
        description: 模板描述
        phases: 阶段定义列表（JSON）
        is_default: 是否为默认模板
        is_system: 是否为系统模板（不可删除）
    """
    __tablename__ = "phase_templates"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    stable_key: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    locale: Mapped[str] = mapped_column(String(20), default=DEFAULT_LOCALE, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    
    # 阶段定义：包含每个阶段的配置
    # 格式参考 DEFAULT_PHASE_TEMPLATE["phases"]
    phases: Mapped[list] = mapped_column(JSON, default=list)
    
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    def to_template_nodes(self) -> list:
        """将阶段模板转换为统一模板树节点。"""
        root_nodes, _ = phase_template_to_root_nodes(self.phases or [])
        return root_nodes

    def apply_to_project(self, project_id: str) -> list:
        """
        将模板应用到项目，生成 ContentBlock 创建参数列表
        
        Args:
            project_id: 目标项目ID
        
        Returns:
            ContentBlock 创建参数列表
        """
        return instantiate_template_nodes(
            project_id=project_id,
            root_nodes=self.to_template_nodes(),
            parent_id=None,
            base_depth=0,
            start_order_index=0,
        )
