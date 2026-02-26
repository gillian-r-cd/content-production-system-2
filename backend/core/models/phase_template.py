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

from core.models.base import BaseModel


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
    description: Mapped[str] = mapped_column(Text, default="")
    
    # 阶段定义：包含每个阶段的配置
    # 格式参考 DEFAULT_PHASE_TEMPLATE["phases"]
    phases: Mapped[list] = mapped_column(JSON, default=list)
    
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    def apply_to_project(self, project_id: str) -> list:
        """
        将模板应用到项目，生成 ContentBlock 创建参数列表
        
        Args:
            project_id: 目标项目ID
        
        Returns:
            ContentBlock 创建参数列表
        """
        from core.models.base import generate_uuid
        
        blocks_to_create = []
        
        for phase in self.phases:
            phase_id = generate_uuid()
            
            # 创建阶段块
            phase_block = {
                "id": phase_id,
                "project_id": project_id,
                "parent_id": None,
                "name": phase["name"],
                "block_type": phase["block_type"],
                "depth": 0,
                "order_index": phase["order_index"],
                "special_handler": phase.get("special_handler"),
                "status": "pending",
            }
            blocks_to_create.append(phase_block)
            
            # 创建默认字段（继承父 phase 的 special_handler）
            phase_handler = phase.get("special_handler")
            for idx, field in enumerate(phase.get("default_fields", [])):
                template_content = field.get("content", "")
                field_block = {
                    "id": generate_uuid(),
                    "project_id": project_id,
                    "parent_id": phase_id,
                    "name": field["name"],
                    "block_type": field["block_type"],
                    "depth": 1,
                    "order_index": idx,
                    "ai_prompt": field.get("ai_prompt", ""),
                    "content": template_content,
                    "special_handler": field.get("special_handler", phase_handler),
                    "pre_questions": field.get("pre_questions", []),
                    "depends_on": field.get("depends_on", []),
                    "constraints": field.get("constraints", {}),
                    "need_review": field.get("need_review", True),
                    "auto_generate": field.get("auto_generate", False),
                    "status": (
                        ("in_progress" if field.get("need_review", True) else "completed")
                        if template_content else "pending"
                    ),
                }
                blocks_to_create.append(field_block)
        
        return blocks_to_create
