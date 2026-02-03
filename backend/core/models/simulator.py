# backend/core/models/simulator.py
# 功能: 模拟器模型，用于消费者模拟
# 主要类: Simulator
# 数据结构: 存储模拟器配置、交互类型、评估维度

"""
模拟器模型
定义不同类型的消费者模拟方式
"""

from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import BaseModel


# 预置交互类型
INTERACTION_TYPES = {
    "dialogue": {
        "name": "对话式",
        "description": "多轮对话模拟，适用于Chatbot、客服场景",
        "evaluation_dimensions": ["响应相关性", "问题解决率", "交互体验"],
    },
    "reading": {
        "name": "阅读式",
        "description": "全盘阅读后给出反馈，适用于文章、课程材料",
        "evaluation_dimensions": ["理解难度", "价值感知", "行动意愿"],
    },
    "decision": {
        "name": "决策式",
        "description": "模拟购买/转化决策过程，适用于销售页、落地页",
        "evaluation_dimensions": ["转化意愿", "顾虑点", "信任度"],
    },
    "exploration": {
        "name": "探索式",
        "description": "带目的的内容探索，适用于产品文档、帮助中心",
        "evaluation_dimensions": ["找到答案效率", "信息完整性", "满意度"],
    },
    "experience": {
        "name": "体验式",
        "description": "任务完成模拟，适用于交互产品、工具",
        "evaluation_dimensions": ["易用性", "效率", "愉悦度"],
    },
}


class Simulator(BaseModel):
    """
    模拟器
    
    Attributes:
        name: 模拟器名称
        description: 描述
        interaction_type: 交互类型（dialogue/reading/decision/exploration/experience）
        prompt_template: 模拟器系统提示词模板
        evaluation_dimensions: 评估维度列表
        max_turns: 最大交互轮数（对话式）
    """
    __tablename__ = "simulators"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    interaction_type: Mapped[str] = mapped_column(String(50), default="reading")
    prompt_template: Mapped[str] = mapped_column(Text, default="")
    evaluation_dimensions: Mapped[list] = mapped_column(JSON, default=list)
    max_turns: Mapped[int] = mapped_column(default=10)

    @classmethod
    def get_default_template(cls, interaction_type: str) -> str:
        """获取交互类型的默认提示词模板"""
        templates = {
            "dialogue": """你是一位真实的用户，具有以下特征：
{persona}

你正在与一个AI助手/客服对话。请基于你的背景和需求，自然地提出问题和反馈。
在对话过程中，请评估：
1. AI的回答是否解决了你的问题
2. 交互体验如何
3. 是否愿意继续使用""",
            
            "reading": """你是一位真实的读者，具有以下特征：
{persona}

请阅读以下内容，然后给出你的真实反馈：
{content}

请从以下维度评价：
1. 内容是否易于理解（1-10分）
2. 你觉得这些内容有价值吗？为什么？
3. 阅读后你会采取什么行动？""",
            
            "decision": """你是一位潜在客户，具有以下特征：
{persona}

你正在浏览以下销售/产品页面：
{content}

请模拟你的真实决策过程：
1. 你的第一印象是什么？
2. 什么内容最吸引你？
3. 你有什么顾虑？
4. 你会购买/注册吗？为什么？""",
            
            "exploration": """你是一位用户，具有以下特征：
{persona}

你有一个具体的问题需要解决：{task}

请在以下文档中寻找答案：
{content}

请记录：
1. 你是如何找到答案的
2. 找到答案花了多长时间
3. 答案是否完整解决了你的问题""",
            
            "experience": """你是一位用户，具有以下特征：
{persona}

你需要完成以下任务：{task}

请使用提供的工具/产品完成任务，并记录：
1. 完成任务的步骤
2. 遇到的困难
3. 整体体验评分（1-10分）""",
        }
        return templates.get(interaction_type, templates["reading"])

