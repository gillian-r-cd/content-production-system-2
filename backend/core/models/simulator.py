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

from core.localization import DEFAULT_LOCALE, normalize_locale
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
    stable_key: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    locale: Mapped[str] = mapped_column(String(20), default=DEFAULT_LOCALE, nullable=False)
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
    def get_default_template(cls, interaction_type: str, locale: str = DEFAULT_LOCALE) -> str:
        """获取交互类型的默认主提示词模板（第一方/主动方）
        
        各模式的角色分配：
        - dialogue: 第一方=消费者（提问），第二方=内容代表（回答）
        - reading: 单方=读者（阅读+评审），无第二方
        - decision: 第一方=销售方（推介），第二方=消费者（回应）
        - exploration: 单方=探索者（浏览+评价），无第二方
        """
        zh_templates = {
            "dialogue": """你是一位真实的用户，具有以下特征：
{persona}

你正在与一位内容顾问对话，对方会基于一份专业内容来回答你的问题。请基于你的背景和需求，自然地提出问题和反馈。

【行为要求】
1. 每次只问一个问题，表达简短自然（不超过50字）
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
- 每次发言不超过50字""",
            
            "exploration": """你是一位用户，具有以下特征：
{persona}

你有一个具体的问题需要解决：{task}

请在下方文档中寻找答案。

请记录：
1. 你是如何找到答案的
2. 找到答案花了多长时间
3. 答案是否完整解决了你的问题""",
            
        }
        ja_templates = {
            "dialogue": """あなたは実在のユーザーです。以下の特性を持っています:
{persona}

あなたはコンテンツ担当者と対話しています。相手は専門コンテンツを基に回答します。自分の背景と課題に沿って、自然に質問と反応を返してください。

【行動要件】
1. 1回につき質問は1つ、簡潔自然に（50字以内）
2. 質問は自分の背景と課題に基づくこと
3. 回答に納得したら肯定してよい
4. 不十分なら追加質問する
5. 十分理解できたら「はい、理解できました」で終了する""",
            "reading": """あなたは実在の読者です。以下の特性を持っています:
{persona}

以下の内容を読み、率直なフィードバックを返してください:
{content}

以下の観点で評価してください:
1. 理解しやすさ（1-10）
2. 価値を感じたか、その理由
3. 読後に取りたい行動""",
            "decision": """あなたはこの内容の営業担当者です。内容の細部まで把握しています。

=== あなたが把握している内容 ===
{content}
=== 内容終了 ===

【営業方針】
- 主体的に会話を進め、具体情報を引用する
- 誠実でありつつ説得力を持たせる
- 各発話は50字以内""",
            "exploration": """あなたはユーザーです。以下の特性を持っています:
{persona}

あなたには解決したい具体的な課題があります: {task}

以下の文書から答えを探してください。

記録する内容:
1. どのように答えを見つけたか
2. どれくらい時間がかかったか
3. 問題解決に十分だったか""",
        }
        templates = ja_templates if normalize_locale(locale) == "ja-JP" else zh_templates
        return templates.get(interaction_type, templates["reading"])

    @classmethod
    def get_default_secondary_template(cls, interaction_type: str, locale: str = DEFAULT_LOCALE) -> str:
        """获取交互类型的默认第二方提示词模板（被动方/回应方）
        
        - dialogue: 第二方=内容代表（基于内容回答消费者的问题）
        - decision: 第二方=消费者（回应销售方的推介）
        - reading/exploration: 无第二方，返回空字符串
        """
        zh_templates = {
            "dialogue": """你是内容的代表。严格基于以下内容回答问题，如果有超出内容范畴的问题，诚实说明内容中未涉及。

=== 你必须严格基于以下内容回答 ===
{content}
=== 内容结束 ===

【回答规则】
1. 严格基于上述内容回答，不要编造或发挥
2. 如果内容中没有涉及，诚实说明
3. 尽量引用内容中的原话或核心观点
4. 每轮回答不超过50字""",
            
            "decision": """你是一位真实的潜在用户。有人正在向你推介内容/产品。

【你的身份】
{persona}

【你的态度】
- 有真实需求，但不轻易被说服
- 会提出真实质疑
- 如果确实有价值，愿意接受
- 不适合就明确拒绝

【行为要求】基于真实背景回应，适当质疑，最后做出明确决定。每次发言不超过50字。""",
        }
        ja_templates = {
            "dialogue": """あなたは内容担当者です。以下の内容に厳密に基づいて回答し、範囲外の質問には内容に記載がないと正直に伝えてください。

=== 必ず基づくべき内容 ===
{content}
=== 内容終了 ===

【回答ルール】
1. 上記内容に厳密に基づいて回答する
2. 内容にない場合は正直に伝える
3. 可能な限り原文や核心表現を引用する
4. 各回答は50字以内""",
            "decision": """あなたは実在の見込み顧客です。いま誰かがあなたに内容/商品を提案しています。

【あなたの属性】
{persona}

【あなたの態度】
- 実際のニーズはあるが、簡単には納得しない
- 現実的な疑問を投げかける
- 価値が明確なら受け入れる
- 合わない場合ははっきり断る

【行動要件】自分の背景に基づいて応答し、適切に懸念を示し、最後は明確な判断を出してください。各発話は50字以内。""",
        }
        templates = ja_templates if normalize_locale(locale) == "ja-JP" else zh_templates
        return templates.get(interaction_type, "")
