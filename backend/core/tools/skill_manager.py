# backend/core/tools/skill_manager.py
# 功能: 技能管理工具，管理可复用的提示词模板
# 主要函数: manage_skill(), create_skill(), apply_skill()
# 数据结构: Skill, SkillOperation

"""
技能管理工具

提供 Agent 管理和应用可复用技能的能力：
1. 创建技能（保存提示词模板）
2. 列出可用技能
3. 应用技能生成内容
4. 更新/删除技能
"""

import json
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import Column, String, Text, Integer, Boolean, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base

from core.database import get_db, Base
from langchain_core.messages import SystemMessage, HumanMessage

from core.llm import llm


class SkillOperation(str, Enum):
    """技能操作类型"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    GET = "get"
    APPLY = "apply"


# 技能数据库模型
class SkillModel(Base):
    """技能数据库模型"""
    __tablename__ = "skills"
    __table_args__ = {'extend_existing': True}
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, default="")
    category = Column(String(50), default="general")  # 类别：generation/analysis/evaluation
    prompt_template = Column(Text, nullable=False)
    input_schema = Column(JSON, default=dict)  # 输入参数定义
    output_format = Column(Text, default="")
    examples = Column(JSON, default=list)
    is_system = Column(Boolean, default=False)  # 是否系统预置
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


@dataclass
class Skill:
    """技能数据结构"""
    id: str = ""
    name: str = ""
    description: str = ""
    category: str = "general"
    prompt_template: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_format: str = ""
    examples: List[Dict] = field(default_factory=list)
    is_system: bool = False
    usage_count: int = 0
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "prompt_template": self.prompt_template,
            "input_schema": self.input_schema,
            "output_format": self.output_format,
            "examples": self.examples,
            "is_system": self.is_system,
            "usage_count": self.usage_count,
        }
    
    @classmethod
    def from_model(cls, model: SkillModel) -> "Skill":
        return cls(
            id=model.id,
            name=model.name,
            description=model.description,
            category=model.category,
            prompt_template=model.prompt_template,
            input_schema=model.input_schema or {},
            output_format=model.output_format,
            examples=model.examples or [],
            is_system=model.is_system,
            usage_count=model.usage_count,
        )


@dataclass
class SkillResult:
    """操作结果"""
    success: bool
    message: str
    skill: Optional[Skill] = None
    skills: Optional[List[Skill]] = None
    output: Optional[str] = None
    error: Optional[str] = None


# ============== 系统预置技能 ==============

SYSTEM_SKILLS = [
    {
        "name": "专业文案",
        "description": "生成专业、权威的文案内容",
        "category": "generation",
        "prompt_template": """你是一个专业的文案撰写专家。

## 风格要求
- 语言专业、权威、有深度
- 使用行业术语，但保持可读性
- 结构清晰，逻辑严密
- 数据和案例支撑观点

## 任务
{task}

## 输出要求
{output_requirements}""",
        "input_schema": {
            "task": {"type": "string", "description": "具体任务描述"},
            "output_requirements": {"type": "string", "description": "输出格式要求", "default": "Markdown格式"},
        },
    },
    {
        "name": "故事化表达",
        "description": "将内容转化为故事形式",
        "category": "generation",
        "prompt_template": """你是一个讲故事高手。

## 故事化技巧
- 以人物和场景开头，建立代入感
- 使用具体细节而非抽象描述
- 设置冲突和转折
- 以情感共鸣结尾

## 原始内容
{content}

## 目标受众
{audience}

请将上述内容改写为一个引人入胜的故事。""",
        "input_schema": {
            "content": {"type": "string", "description": "要故事化的内容"},
            "audience": {"type": "string", "description": "目标受众"},
        },
    },
    {
        "name": "内容简化",
        "description": "将复杂内容简化为易懂版本",
        "category": "analysis",
        "prompt_template": """你是一个内容简化专家。

## 简化原则
- 用简单词汇替代专业术语
- 用类比解释抽象概念
- 保留核心信息，删除细节
- 控制句子长度（不超过20字）

## 原始内容
{content}

## 目标阅读水平
{reading_level}

请简化以上内容。""",
        "input_schema": {
            "content": {"type": "string", "description": "要简化的内容"},
            "reading_level": {"type": "string", "description": "目标阅读水平", "default": "初中生"},
        },
    },
    {
        "name": "批判性分析",
        "description": "对内容进行批判性分析",
        "category": "evaluation",
        "prompt_template": """你是一个批判性思考专家。

## 分析维度
1. 论点是否清晰？
2. 论据是否充分？
3. 逻辑是否严密？
4. 是否有遗漏或偏见？
5. 改进建议

## 待分析内容
{content}

请提供详细的批判性分析。""",
        "input_schema": {
            "content": {"type": "string", "description": "要分析的内容"},
        },
    },
]


def _ensure_system_skills(db: Session):
    """确保系统技能已创建"""
    for skill_data in SYSTEM_SKILLS:
        existing = db.query(SkillModel).filter(SkillModel.name == skill_data["name"]).first()
        if not existing:
            skill = SkillModel(
                name=skill_data["name"],
                description=skill_data["description"],
                category=skill_data["category"],
                prompt_template=skill_data["prompt_template"],
                input_schema=skill_data["input_schema"],
                is_system=True,
            )
            db.add(skill)
    db.commit()


def list_skills(
    category: str = None,
    db: Optional[Session] = None,
) -> SkillResult:
    """列出所有技能"""
    if db is None:
        db = next(get_db())
    
    _ensure_system_skills(db)
    
    query = db.query(SkillModel)
    if category:
        query = query.filter(SkillModel.category == category)
    
    skills = [Skill.from_model(s) for s in query.all()]
    
    return SkillResult(
        success=True,
        message=f"共 {len(skills)} 个技能",
        skills=skills,
    )


def get_skill(
    skill_name: str,
    db: Optional[Session] = None,
) -> SkillResult:
    """获取单个技能"""
    if db is None:
        db = next(get_db())
    
    _ensure_system_skills(db)
    
    skill = db.query(SkillModel).filter(
        (SkillModel.name == skill_name) | (SkillModel.id == skill_name)
    ).first()
    
    if not skill:
        return SkillResult(
            success=False,
            message=f"技能「{skill_name}」不存在",
            error="Skill not found",
        )
    
    return SkillResult(
        success=True,
        message=f"技能: {skill.name}",
        skill=Skill.from_model(skill),
    )


def create_skill(
    skill_data: Dict[str, Any],
    db: Optional[Session] = None,
) -> SkillResult:
    """创建新技能"""
    if db is None:
        db = next(get_db())
    
    name = skill_data.get("name", "")
    if not name:
        return SkillResult(
            success=False,
            message="技能名称不能为空",
            error="Name required",
        )
    
    # 检查是否已存在
    existing = db.query(SkillModel).filter(SkillModel.name == name).first()
    if existing:
        return SkillResult(
            success=False,
            message=f"技能「{name}」已存在",
            error="Skill already exists",
        )
    
    try:
        skill = SkillModel(
            name=name,
            description=skill_data.get("description", ""),
            category=skill_data.get("category", "general"),
            prompt_template=skill_data.get("prompt_template", ""),
            input_schema=skill_data.get("input_schema", {}),
            output_format=skill_data.get("output_format", ""),
            examples=skill_data.get("examples", []),
            is_system=False,
        )
        db.add(skill)
        db.commit()
        
        return SkillResult(
            success=True,
            message=f"已创建技能「{name}」",
            skill=Skill.from_model(skill),
        )
        
    except Exception as e:
        db.rollback()
        return SkillResult(
            success=False,
            message=f"创建技能失败: {str(e)}",
            error=str(e),
        )


def update_skill(
    skill_name: str,
    updates: Dict[str, Any],
    db: Optional[Session] = None,
) -> SkillResult:
    """更新技能"""
    if db is None:
        db = next(get_db())
    
    skill = db.query(SkillModel).filter(
        (SkillModel.name == skill_name) | (SkillModel.id == skill_name)
    ).first()
    
    if not skill:
        return SkillResult(
            success=False,
            message=f"技能「{skill_name}」不存在",
            error="Skill not found",
        )
    
    if skill.is_system:
        return SkillResult(
            success=False,
            message="系统预置技能不能修改",
            error="Cannot modify system skill",
        )
    
    try:
        if "name" in updates:
            skill.name = updates["name"]
        if "description" in updates:
            skill.description = updates["description"]
        if "category" in updates:
            skill.category = updates["category"]
        if "prompt_template" in updates:
            skill.prompt_template = updates["prompt_template"]
        if "input_schema" in updates:
            skill.input_schema = updates["input_schema"]
        if "output_format" in updates:
            skill.output_format = updates["output_format"]
        if "examples" in updates:
            skill.examples = updates["examples"]
        
        db.commit()
        
        return SkillResult(
            success=True,
            message=f"已更新技能「{skill.name}」",
            skill=Skill.from_model(skill),
        )
        
    except Exception as e:
        db.rollback()
        return SkillResult(
            success=False,
            message=f"更新技能失败: {str(e)}",
            error=str(e),
        )


def delete_skill(
    skill_name: str,
    db: Optional[Session] = None,
) -> SkillResult:
    """删除技能"""
    if db is None:
        db = next(get_db())
    
    skill = db.query(SkillModel).filter(
        (SkillModel.name == skill_name) | (SkillModel.id == skill_name)
    ).first()
    
    if not skill:
        return SkillResult(
            success=False,
            message=f"技能「{skill_name}」不存在",
            error="Skill not found",
        )
    
    if skill.is_system:
        return SkillResult(
            success=False,
            message="系统预置技能不能删除",
            error="Cannot delete system skill",
        )
    
    try:
        db.delete(skill)
        db.commit()
        
        return SkillResult(
            success=True,
            message=f"已删除技能「{skill_name}」",
        )
        
    except Exception as e:
        db.rollback()
        return SkillResult(
            success=False,
            message=f"删除技能失败: {str(e)}",
            error=str(e),
        )


async def apply_skill(
    skill_name: str,
    params: Dict[str, Any],
    db: Optional[Session] = None,
) -> SkillResult:
    """应用技能生成内容"""
    if db is None:
        db = next(get_db())
    
    _ensure_system_skills(db)
    
    skill = db.query(SkillModel).filter(
        (SkillModel.name == skill_name) | (SkillModel.id == skill_name)
    ).first()
    
    if not skill:
        return SkillResult(
            success=False,
            message=f"技能「{skill_name}」不存在",
            error="Skill not found",
        )
    
    try:
        # 填充模板
        template = skill.prompt_template
        for key, value in params.items():
            template = template.replace(f"{{{key}}}", str(value))
        
        # 检查是否有未填充的变量
        import re
        unfilled = re.findall(r'\{(\w+)\}', template)
        if unfilled:
            # 用默认值填充
            for var in unfilled:
                schema = skill.input_schema.get(var, {})
                default = schema.get("default", "")
                template = template.replace(f"{{{var}}}", str(default))
        
        # 调用 AI
        messages = [
            SystemMessage(content=template),
            HumanMessage(content="请执行任务"),
        ]
        
        response = await llm.ainvoke(messages)
        
        # 更新使用次数
        skill.usage_count += 1
        db.commit()
        
        return SkillResult(
            success=True,
            message=f"已使用技能「{skill.name}」",
            skill=Skill.from_model(skill),
            output=response.content,
        )
        
    except Exception as e:
        return SkillResult(
            success=False,
            message=f"应用技能失败: {str(e)}",
            error=str(e),
        )


async def manage_skill(
    operation: SkillOperation,
    params: Dict[str, Any] = None,
    db: Optional[Session] = None,
) -> SkillResult:
    """
    技能管理统一入口
    
    Args:
        operation: 操作类型
        params: 操作参数
        db: 数据库会话
    
    Returns:
        SkillResult
    """
    params = params or {}
    
    if operation == SkillOperation.LIST:
        return list_skills(params.get("category"), db)
    
    elif operation == SkillOperation.GET:
        return get_skill(params.get("name", ""), db)
    
    elif operation == SkillOperation.CREATE:
        return create_skill(params, db)
    
    elif operation == SkillOperation.UPDATE:
        return update_skill(
            params.get("name", ""),
            params.get("updates", {}),
            db,
        )
    
    elif operation == SkillOperation.DELETE:
        return delete_skill(params.get("name", ""), db)
    
    elif operation == SkillOperation.APPLY:
        return await apply_skill(
            params.get("name", ""),
            params.get("apply_params", {}),
            db,
        )
    
    else:
        return SkillResult(
            success=False,
            message=f"未知操作: {operation}",
            error="Unknown operation",
        )
