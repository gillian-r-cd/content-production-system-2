# backend/core/models/__init__.py
# 功能: 模型包入口，导出所有SQLAlchemy模型
# 包含: 所有数据模型类

"""
数据模型包
导出所有SQLAlchemy模型供其他模块使用
"""

from core.models.base import BaseModel, generate_uuid
from core.models.creator_profile import CreatorProfile
from core.models.project import Project, PROJECT_PHASES, PHASE_STATUS
from core.models.field_template import FieldTemplate
from core.models.project_field import ProjectField, FIELD_STATUS
from core.models.channel import Channel
from core.models.simulator import Simulator, INTERACTION_TYPES
from core.models.simulation_record import SimulationRecord
from core.models.evaluation import EvaluationTemplate, EvaluationReport
from core.models.generation_log import GenerationLog
from core.models.system_prompt import SystemPrompt
from core.models.agent_settings import AgentSettings
from core.models.chat_history import ChatMessage

__all__ = [
    # 基础
    "BaseModel",
    "generate_uuid",
    
    # 系统设置
    "SystemPrompt",
    "AgentSettings",
    "ChatMessage",
    
    # 创作者
    "CreatorProfile",
    
    # 项目
    "Project",
    "PROJECT_PHASES",
    "PHASE_STATUS",
    
    # 字段
    "FieldTemplate",
    "ProjectField",
    "FIELD_STATUS",
    
    # 渠道
    "Channel",
    
    # 模拟
    "Simulator",
    "INTERACTION_TYPES",
    "SimulationRecord",
    
    # 评估
    "EvaluationTemplate",
    "EvaluationReport",
    
    # 日志
    "GenerationLog",
]
