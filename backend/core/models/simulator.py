# backend/core/models/simulator.py
# 功能: 通用模拟器模型，定义交互方式和反馈方式
# 主要类: Simulator
# 数据结构:
#   - simulator_type: 模拟器角色类型 (coach/editor/expert/consumer/seller/custom)
#   - interaction_mode: 交互模式 (review/dialogue/scenario)
#   - prompt_template: 系统提示词模板
#   - grader_template: 评估时的评分提示词模板
#   - evaluation_dimensions: 评估维度列表
#   - is_preset: 是否为系统预设

"""
通用模拟器模型
Simulator = 交互引擎，定义 HOW to interact + HOW to collect feedback
角色类型(WHO) 由 simulator_type 决定，但可完全自定义
"""

from sqlalchemy import String, Text, JSON, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import BaseModel


# 保留旧的交互类型（向后兼容）
INTERACTION_TYPES = {
    "dialogue": {
        "name": "对话式",
        "description": "多轮对话模拟，适用于Chatbot、客服、咨询场景",
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
}


class Simulator(BaseModel):
    """
    通用模拟器
    
    定义了「交互方式 + 反馈方式 + 评估方式」的通用引擎。
    simulator_type 决定了角色视角（WHO），interaction_mode 决定了交互方式（HOW）。
    
    Attributes:
        name: 模拟器名称
        description: 描述
        simulator_type: 角色类型 (coach/editor/expert/consumer/seller/custom)
        interaction_type: 旧版交互类型（向后兼容）
        interaction_mode: 新版交互模式 (review/dialogue/scenario)
        prompt_template: 模拟器系统提示词模板
        grader_template: 评估/评分提示词模板
        evaluation_dimensions: 评估维度列表
        feedback_mode: 反馈方式 (structured/freeform)
        max_turns: 最大交互轮数（对话/场景模式）
        is_preset: 是否为系统预设（预设不可删除）
    """
    __tablename__ = "simulators"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    
    # 角色类型（新增）
    simulator_type: Mapped[str] = mapped_column(String(50), default="custom")
    
    # 旧版兼容
    interaction_type: Mapped[str] = mapped_column(String(50), default="reading")
    
    # 新版交互模式
    interaction_mode: Mapped[str] = mapped_column(String(50), default="review")
    
    prompt_template: Mapped[str] = mapped_column(Text, default="")
    secondary_prompt: Mapped[str] = mapped_column(Text, default="")  # 对话模式：第二方提示词（如内容代表/消费者回应）
    grader_template: Mapped[str] = mapped_column(Text, default="")
    evaluation_dimensions: Mapped[list] = mapped_column(JSON, default=list)
    feedback_mode: Mapped[str] = mapped_column(String(50), default="structured")
    max_turns: Mapped[int] = mapped_column(Integer, default=10)
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False)

    @classmethod
    def get_default_template(cls, interaction_type: str) -> str:
        """获取交互类型的默认主提示词模板（第一方/主动方）
        
        各模式的角色分配：
        - dialogue: 第一方=消费者（提问），第二方=内容代表（回答）
        - reading: 单方=读者（阅读+评审），无第二方
        - decision: 第一方=销售方（推介），第二方=消费者（回应）
        - exploration: 单方=探索者（浏览+评价），无第二方
        """
        templates = {
            "dialogue": """你是一位真实的用户，具有以下特征：
{persona}

你正在与一位内容顾问对话，对方会基于一份专业内容来回答你的问题。请基于你的背景和需求，自然地提出问题和反馈。

【行为要求】
1. 每次只问一个问题，表达简短自然（不超过100字）
2. 问题要基于你的真实背景和痛点
3. 如果对方的回答让你满意，可以表示认可
4. 如果对方的回答不够具体、不够好，继续追问
5. 如果觉得已经了解足够了，说"好的，我了解了"结束对话""",
            
            "reading": """你是一位真实的读者，具有以下特征：
{persona}

请阅读以下内容，然后给出你的真实反馈：
{content}

请从以下维度评价：
1. 内容是否易于理解（1-10分）
2. 你觉得这些内容有价值吗？为什么？
3. 阅读后你会采取什么行动？""",
            
            "decision": """你是这个内容的销售顾问。你深入了解内容的每个细节。

=== 你掌握的内容 ===
{content}
=== 内容结束 ===

【销售策略】
- 主动引导对话，引用具体信息
- 诚实但有说服力
- 每次200字以内""",
            
            "exploration": """你是一位用户，具有以下特征：
{persona}

你有一个具体的问题需要解决：{task}

请在下方文档中寻找答案。

请记录：
1. 你是如何找到答案的
2. 找到答案花了多长时间
3. 答案是否完整解决了你的问题""",
            
        }
        return templates.get(interaction_type, templates["reading"])

    @classmethod
    def get_default_secondary_template(cls, interaction_type: str) -> str:
        """获取交互类型的默认第二方提示词模板（被动方/回应方）
        
        - dialogue: 第二方=内容代表（基于内容回答消费者的问题）
        - decision: 第二方=消费者（回应销售方的推介）
        - reading/exploration: 无第二方，返回空字符串
        """
        templates = {
            "dialogue": """你是内容的代表。严格基于以下内容回答问题，如果有超出内容范畴的问题，诚实说明内容中未涉及。

=== 你必须严格基于以下内容回答 ===
{content}
=== 内容结束 ===

【回答规则】
1. 严格基于上述内容回答，不要编造或发挥
2. 如果内容中没有涉及，诚实说明
3. 尽量引用内容中的原话或核心观点
4. 每轮回答不超过200字""",
            
            "decision": """你是一位真实的潜在用户。有人正在向你推介内容/产品。

【你的身份】
{persona}

【你的态度】
- 有真实需求，但不轻易被说服
- 会提出真实质疑
- 如果确实有价值，愿意接受
- 不适合就明确拒绝

【行为要求】基于真实背景回应，适当质疑，最后做出明确决定。每轮回答不超过100字。""",
        }
        return templates.get(interaction_type, "")
