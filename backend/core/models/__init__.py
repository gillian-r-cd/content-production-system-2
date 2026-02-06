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
from core.models.content_block import ContentBlock, BLOCK_TYPES, SPECIAL_HANDLERS, BLOCK_STATUS
from core.models.block_history import BlockHistory, HISTORY_ACTIONS
from core.models.phase_template import PhaseTemplate, DEFAULT_PHASE_TEMPLATE
from core.models.eval_run import EvalRun, EVAL_ROLES, EVAL_RUN_STATUS
from core.models.eval_trial import EvalTrial, EVAL_TRIAL_STATUS

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
    
    # 评估（旧）
    "EvaluationTemplate",
    "EvaluationReport",
    
    # 评估（新 Eval 体系）
    "EvalRun",
    "EVAL_ROLES",
    "EVAL_RUN_STATUS",
    "EvalTrial",
    "EVAL_TRIAL_STATUS",
    
    # 日志
    "GenerationLog",
    
    # 统一内容块（新架构）
    "ContentBlock",
    "BLOCK_TYPES",
    "SPECIAL_HANDLERS",
    "BLOCK_STATUS",
    
    # 内容块操作历史（撤回功能）
    "BlockHistory",
    "HISTORY_ACTIONS",
    
    # 阶段模板
    "PhaseTemplate",
    "DEFAULT_PHASE_TEMPLATE",
]
