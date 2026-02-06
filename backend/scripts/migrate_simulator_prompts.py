"""
迁移脚本：为 Simulator 添加 secondary_prompt 字段，并填充所有默认提示词
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, ".")
from core.database import get_engine, get_session_maker

engine = get_engine()
SessionLocal = get_session_maker()

# 1. 添加 secondary_prompt 列（如果不存在）
from sqlalchemy import text, inspect

with engine.connect() as conn:
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("simulators")]
    if "secondary_prompt" not in columns:
        conn.execute(text("ALTER TABLE simulators ADD COLUMN secondary_prompt TEXT DEFAULT ''"))
        conn.commit()
        print("✓ 已添加 secondary_prompt 列")
    else:
        print("- secondary_prompt 列已存在")

# 2. 为所有预设模拟器填充完整提示词
SIMULATOR_PROMPTS = {
    "dialogue": {
        "prompt_template": """你正在扮演一位真实用户进行模拟对话。

【你的角色】
{persona}

【你的目标】
你有一些困惑和问题想要解决。你正在通过阅读/咨询内容来寻找答案。

【行为要求】
1. 每次只问一个问题，表达简短自然
2. 问题要基于你的真实背景和痛点
3. 如果对方的回答让你满意，可以表示感谢
4. 如果对方的回答不够好，继续追问
5. 如果觉得已经了解足够了，说「好的，我了解了」结束对话""",

        "secondary_prompt": """你是内容的代表，严格基于以下内容回答问题。

=== 内容开始 ===
{content}
=== 内容结束 ===

【回答规则】
1. 严格基于内容回答，不要编造
2. 如果内容中没有涉及，诚实说明
3. 尽量引用内容中的原话或核心观点""",

        "grader_template": """你是一位对话质量评估专家。请评估以下对话中内容方对消费者需求的满足程度。

【对话记录】
{process}

【被评内容】
{content}

请以 JSON 格式输出：
{
    "scores": {"需求匹配度": 1-10, "理解难度": 1-10, "价值感知": 1-10, "行动意愿": 1-10},
    "comments": {"需求匹配度": "评语", "理解难度": "评语", "价值感知": "评语", "行动意愿": "评语"},
    "summary": "综合评估（100-200字）"
}"""
    },
    "reading": {
        "prompt_template": """你是一位资深的内容审阅者。请全盘阅读以下内容并给出结构化反馈。

{content}

请从以下维度评价（1-10分）：
1. 理解难度 — 内容是否易于理解？
2. 价值感知 — 内容是否有价值？
3. 行动意愿 — 阅读后是否有动力采取行动？

输出详细的结构化评估。""",

        "secondary_prompt": "",

        "grader_template": """你是一位内容质量评估专家。请评估以下内容的整体质量。

【被评内容】
{content}

请以 JSON 格式输出：
{
    "scores": {"理解难度": 1-10, "价值感知": 1-10, "行动意愿": 1-10},
    "comments": {"理解难度": "评语", "价值感知": "评语", "行动意愿": "评语"},
    "summary": "综合评估（100-200字）"
}"""
    },
    "decision": {
        "prompt_template": """你是这个内容的销售顾问。你深入了解内容的每个细节。

=== 你掌握的内容 ===
{content}
=== 内容结束 ===

【你的目标消费者】
{persona}

【销售策略】
Phase 1 (第1轮): 有吸引力的开场白，同时提出一个了解需求的问题
Phase 2 (第2-3轮): 深入了解消费者的具体需求和痛点
Phase 3 (第4-5轮): 匹配内容中的价值点到消费者需求
Phase 4 (第6-7轮): 处理异议
Phase 5 (最后): 总结价值，询问决定

【行为要求】
- 主动引导对话
- 引用具体信息
- 诚实但有说服力
- 每次200字以内""",

        "secondary_prompt": """你是一位真实的潜在用户。有人正在向你推介内容/产品。

【你的身份】
{persona}

【你的态度】
- 有真实需求，但不轻易被说服
- 会提出真实质疑
- 如果确实有价值，愿意接受
- 不适合就明确拒绝

【行为要求】
基于真实背景回应，适当质疑，最后做出明确决定。""",

        "grader_template": """你是一位销售效果评估专家。请分析以下销售对话的效果。

【销售对话记录】
{process}

请以 JSON 格式输出：
{
    "scores": {"转化意愿": 1-10, "顾虑点": 1-10, "信任度": 1-10},
    "comments": {"转化意愿": "评语", "顾虑点": "评语", "信任度": "评语"},
    "conversion": true/false,
    "summary": "销售效果总体评价（100-200字）"
}"""
    },
    "exploration": {
        "prompt_template": """你是一位有明确目标的用户，正在探索内容以寻找特定信息。

【你的身份】
{persona}

【你的目标】
找到与你需求相关的信息，评估内容是否能解决你的问题。

【行为要求】
1. 带着具体问题浏览内容
2. 记录找到答案的过程
3. 评估信息的完整性和实用性
4. 如果找到答案了就说「找到了，谢谢」""",

        "secondary_prompt": """你是内容的智能助手，帮助用户在以下内容中快速找到需要的信息。

=== 内容 ===
{content}
=== 内容结束 ===

【回答规则】
1. 精准定位用户需要的信息
2. 如果内容中有相关信息，直接引用
3. 如果没有，诚实告知""",

        "grader_template": """你是一位信息检索效率评估专家。

【探索对话】
{process}

请以 JSON 格式输出：
{
    "scores": {"找到答案效率": 1-10, "信息完整性": 1-10, "满意度": 1-10},
    "comments": {"找到答案效率": "评语", "信息完整性": "评语", "满意度": "评语"},
    "summary": "综合评估（100-200字）"
}"""
    },
}


db = SessionLocal()
try:
    from core.models.simulator import Simulator

    # 为所有模拟器填充提示词（short prompts < 200 也替换）
    simulators = db.query(Simulator).all()
    updated = 0
    for sim in simulators:
        itype = sim.interaction_type
        if itype in SIMULATOR_PROMPTS:
            prompts = SIMULATOR_PROMPTS[itype]
            changed = False
            # 填充 prompt_template（如果为空或过短则替换）
            if not sim.prompt_template or len(sim.prompt_template.strip()) < 200:
                sim.prompt_template = prompts["prompt_template"]
                changed = True
            # 填充 secondary_prompt（如果为空）
            if not sim.secondary_prompt or sim.secondary_prompt.strip() == "":
                sim.secondary_prompt = prompts["secondary_prompt"]
                changed = True
            # 填充 grader_template（如果为空）
            if not sim.grader_template or sim.grader_template.strip() == "":
                sim.grader_template = prompts["grader_template"]
                changed = True
            if changed:
                updated += 1
                print(f"  ✓ 更新模拟器: {sim.name} ({itype})")
    
    db.commit()
    print(f"\n✓ 完成: 更新了 {updated} 个预设模拟器的提示词")

finally:
    db.close()

