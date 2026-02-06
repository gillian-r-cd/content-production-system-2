# backend/core/tools/eval_engine.py
# 功能: 评估执行引擎，包含5种角色评估 + Grader + Diagnoser
# 主要函数: run_eval(), run_trial(), run_diagnoser()

"""
Eval 引擎
角色驱动的内容评估体系，支持5种评估角色 + 三级Grader + 跨Trial诊断
"""

import json
import asyncio
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

from core.ai_client import ai_client, ChatMessage
from core.models.eval_run import EVAL_ROLES


# ============== 数据结构 ==============

@dataclass
class TrialResult:
    """Trial 执行结果"""
    role: str
    interaction_mode: str
    nodes: list = field(default_factory=list)
    result: dict = field(default_factory=dict)
    grader_outputs: list = field(default_factory=list)
    overall_score: float = 0.0
    success: bool = True
    error: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0


# ============== 角色系统提示词 ==============

ROLE_PROMPTS = {
    "coach": """你是一位资深的内容策略教练。你的视角是**战略层面**：

【你的身份】
你拥有丰富的内容策略经验，擅长判断内容方向是否正确、定位是否清晰。

【创作者信息】
{creator_profile}

【项目意图】
{intent}

【你的评估任务】
从策略视角审查以下内容，评估：
1. 内容方向是否与项目意图一致？
2. 定位是否清晰？目标受众是否明确？
3. 与同类内容相比，差异化在哪？
4. 是否有战略性的遗漏或偏差？

请给出具体的、有建设性的反馈。""",

    "editor": """你是一位资深的内容编辑。你的视角是**手艺层面**：

【你的身份】
你有多年编辑经验，对内容的结构、语言、节奏有极高的标准。

【创作者风格】
{creator_profile}

【你的评估任务】
从编辑专业视角审查以下内容，评估：
1. 结构是否合理？逻辑是否连贯？
2. 语言质量如何？是否有表达不清、冗余或矛盾？
3. 风格是否一致？是否符合创作者特质？
4. 开头是否吸引人？结尾是否有力？
5. 是否有改进空间？

请像一位严格但有建设性的编辑一样给出具体意见。""",

    "expert": """你是一位该领域的资深专家。你的视角是**专业层面**：

【你的身份】
你在这个领域有深厚的知识积累和实践经验。

【项目意图】
{intent}

【你的评估任务】
从专业视角审查以下内容，评估：
1. 内容是否准确？有没有事实性错误？
2. 专业深度是否足够？
3. 是否有数据/案例支撑关键论点？
4. 在市场/行业背景下，内容是否具有相关性？
5. 有没有遗漏的重要方面？

请以专业人士的标准给出评价。""",

    "consumer": """你是一位真实的目标消费者。请完全代入以下角色：

【你的身份】
{persona}

【你的需求和痛点】
你有一些困惑和问题想要解决。你正在阅读/体验以下内容，看它是否能帮到你。

【行为要求】
1. 完全代入角色，基于你的背景和真实需求做出判断
2. 如果内容对你有帮助，具体说明是哪些部分
3. 如果有困惑或不满，诚实表达
4. 最终判断：你会推荐这个内容给朋友吗？""",

    "seller": """你是这个内容的销售顾问。你的目标是向目标消费者推介这个内容。

【你的身份】
你深入了解内容的每个细节，是这个内容最专业的推介者。

【你掌握的内容】
{content}

【你的目标消费者】
{persona}

【你的销售策略】
1. 先了解消费者的具体需求（2-3个问题）
2. 根据需求匹配内容中的价值点
3. 如果消费者有疑虑，用内容中的具体事实回应
4. 争取让消费者认可内容的价值

【行为要求】
- 主动引导对话，不要被动等待
- 引用内容中的具体段落/数据/案例
- 诚实但有说服力
- 如果内容确实没有覆盖某个问题，诚实说明""",
}


# ============== 评估维度 ==============

ROLE_DIMENSIONS = {
    "coach": ["策略对齐度", "定位清晰度", "差异化程度", "完整性"],
    "editor": ["结构合理性", "语言质量", "风格一致性", "可读性"],
    "expert": ["事实准确性", "专业深度", "数据支撑", "行业相关性"],
    "consumer": ["需求匹配度", "理解难度", "价值感知", "行动意愿"],
    "seller": ["价值传达", "需求匹配", "异议处理", "转化结果"],
}


# ============== 角色执行函数 ==============

async def run_review_trial(
    role: str,
    content: str,
    creator_profile: str = "",
    intent: str = "",
    persona: dict = None,
) -> TrialResult:
    """
    运行审查模式 Trial（Coach / Editor / Expert 使用）
    
    AI一次性阅读全部内容，给出结构化反馈
    """
    dimensions = ROLE_DIMENSIONS.get(role, ["综合评价"])
    
    # 构建系统提示词
    prompt_template = ROLE_PROMPTS.get(role, "请评估以下内容。")
    system_prompt = prompt_template.format(
        creator_profile=creator_profile or "未提供",
        intent=intent or "未提供",
        persona=json.dumps(persona, ensure_ascii=False) if persona else "未提供",
        content="（见下方用户消息）",
    )
    
    # 构建评估指令
    dim_str = ", ".join([f'"{d}": 分数(1-10)' for d in dimensions])
    dim_comment_str = ", ".join([f'"{d}": "具体评语（至少2句话）"' for d in dimensions])
    
    eval_instruction = f"""以下是要评估的内容：

{content}

请以你的专业身份进行评估。

**输出JSON格式**（严格遵循，不要输出其他内容）：
{{
    "scores": {{{dim_str}}},
    "comments": {{{dim_comment_str}}},
    "strengths": ["优点1", "优点2", "优点3"],
    "weaknesses": ["问题1", "问题2", "问题3"],
    "suggestions": ["具体改进建议1", "具体改进建议2", "具体改进建议3"],
    "summary": "总体评价（100-200字）"
}}"""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=eval_instruction),
    ]
    
    try:
        response = await ai_client.async_chat(messages, temperature=0.6)
        
        # 解析结果
        result_data = _parse_json_response(response.content)
        
        scores = result_data.get("scores", {})
        avg_score = sum(scores.values()) / len(scores) if scores else 0
        
        return TrialResult(
            role=role,
            interaction_mode="review",
            nodes=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": eval_instruction},
                {"role": "assistant", "content": response.content},
            ],
            result={
                "scores": scores,
                "comments": result_data.get("comments", {}),
                "strengths": result_data.get("strengths", []),
                "weaknesses": result_data.get("weaknesses", []),
                "suggestions": result_data.get("suggestions", []),
                "outcome": "reviewed",
                "summary": result_data.get("summary", ""),
            },
            overall_score=round(avg_score, 2),
            success=True,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost=response.cost,
        )
        
    except Exception as e:
        return TrialResult(
            role=role,
            interaction_mode="review",
            success=False,
            error=str(e),
        )


async def run_consumer_dialogue_trial(
    content: str,
    persona: dict,
    max_turns: int = 5,
    content_field_names: list = None,
) -> TrialResult:
    """
    运行消费者对话模式 Trial
    
    消费者（Persona）带着问题与内容进行对话。
    """
    user_name = persona.get('name', '消费者')
    content_name = "内容"
    if content_field_names:
        content_name = f"《{content_field_names[0]}》" if len(content_field_names) == 1 else f"《{content_field_names[0]}》等{len(content_field_names)}篇"
    
    persona_text = f"姓名: {user_name}\n背景: {persona.get('background', '')}\n详细情况: {persona.get('story', '')}"
    
    # 消费者系统提示词
    consumer_system = f"""你正在扮演一位真实用户进行模拟对话。

【你的角色】
{persona_text}

【你的目标】
你有一些困惑和问题想要解决。你正在通过阅读/咨询{content_name}来寻找答案。

【行为要求】
1. 每次只问一个问题，表达简短自然
2. 问题要基于你的真实背景和痛点
3. 如果对方的回答让你满意，可以表示感谢
4. 如果对方的回答不够好，继续追问
5. 如果觉得已经了解足够了，说"好的，我了解了"结束对话"""

    # 内容代表系统提示词
    content_system = f"""你是{content_name}的内容代表，严格基于以下内容回答问题。

=== 内容开始 ===
{content}
=== 内容结束 ===

【回答规则】
1. 严格基于内容回答，不要编造
2. 如果内容中没有涉及，诚实说明
3. 尽量引用内容中的原话或核心观点"""

    interaction_log = []
    total_tokens_in = 0
    total_tokens_out = 0
    total_cost = 0.0
    
    try:
        for turn in range(max_turns):
            # 消费者提问
            user_messages = [ChatMessage(role="system", content=consumer_system)]
            for log in interaction_log:
                if log["role"] == "consumer":
                    user_messages.append(ChatMessage(role="assistant", content=log["content"]))
                else:
                    user_messages.append(ChatMessage(role="user", content=log["content"]))
            
            prompt = "请基于你的背景，提出你最想解决的第一个问题。" if turn == 0 else "请基于之前的对话，继续你的咨询。"
            user_messages.append(ChatMessage(role="user", content=prompt))
            
            user_response = await ai_client.async_chat(user_messages, temperature=0.8)
            total_tokens_in += user_response.tokens_in
            total_tokens_out += user_response.tokens_out
            total_cost += user_response.cost
            
            interaction_log.append({
                "role": "consumer",
                "name": user_name,
                "content": user_response.content,
                "turn": turn + 1,
            })
            
            # 检查是否结束
            end_signals = ["了解了", "明白了", "好的谢谢", "谢谢", "再见", "不需要了", "足够了", "清楚了"]
            if any(s in user_response.content for s in end_signals):
                break
            
            # 内容代表回复
            content_messages = [ChatMessage(role="system", content=content_system)]
            for log in interaction_log:
                if log["role"] == "consumer":
                    content_messages.append(ChatMessage(role="user", content=log["content"]))
                else:
                    content_messages.append(ChatMessage(role="assistant", content=log["content"]))
            
            content_response = await ai_client.async_chat(content_messages, temperature=0.5)
            total_tokens_in += content_response.tokens_in
            total_tokens_out += content_response.tokens_out
            total_cost += content_response.cost
            
            interaction_log.append({
                "role": "content_rep",
                "name": content_name,
                "content": content_response.content,
                "turn": turn + 1,
            })
        
        # 评估阶段
        dialogue_transcript = "\n".join([
            f"[{log.get('name', log['role'])}]: {log['content']}"
            for log in interaction_log
        ])
        
        dimensions = ROLE_DIMENSIONS["consumer"]
        dim_str = ", ".join([f'"{d}": 分数(1-10)' for d in dimensions])
        
        eval_messages = [
            ChatMessage(role="system", content=f"""你是{user_name}，刚刚完成了一次咨询对话。
你的背景：{persona_text}
请评估内容对你的帮助程度。"""),
            ChatMessage(role="user", content=f"""对话记录：
{dialogue_transcript}

请以JSON格式输出：
{{
    "scores": {{{dim_str}}},
    "comments": {{{", ".join([f'"{d}": "评语"' for d in dimensions])}}},
    "problems_solved": ["被解决的问题"],
    "problems_unsolved": ["未被解决的问题"],
    "content_gaps": ["内容缺失的部分"],
    "would_recommend": true/false,
    "summary": "总体评价（100字以内）"
}}"""),
        ]
        
        eval_response = await ai_client.async_chat(eval_messages, temperature=0.5)
        total_tokens_in += eval_response.tokens_in
        total_tokens_out += eval_response.tokens_out
        total_cost += eval_response.cost
        
        result_data = _parse_json_response(eval_response.content)
        scores = result_data.get("scores", {})
        avg_score = sum(scores.values()) / len(scores) if scores else 0
        
        return TrialResult(
            role="consumer",
            interaction_mode="dialogue",
            nodes=[{"role": log["role"], "content": log["content"], "turn": log.get("turn")} for log in interaction_log],
            result={
                "scores": scores,
                "comments": result_data.get("comments", {}),
                "strengths": result_data.get("problems_solved", []),
                "weaknesses": result_data.get("problems_unsolved", []),
                "suggestions": result_data.get("content_gaps", []),
                "outcome": "recommended" if result_data.get("would_recommend") else "not_recommended",
                "summary": result_data.get("summary", ""),
            },
            overall_score=round(avg_score, 2),
            success=True,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            cost=total_cost,
        )
    except Exception as e:
        return TrialResult(
            role="consumer",
            interaction_mode="dialogue",
            nodes=[{"role": log["role"], "content": log["content"]} for log in interaction_log],
            success=False,
            error=str(e),
        )


async def run_seller_dialogue_trial(
    content: str,
    persona: dict,
    max_turns: int = 8,
) -> TrialResult:
    """
    运行内容销售对话模式 Trial
    
    Sales Rep 主动向 Consumer 推介内容，测试内容的转化能力。
    """
    consumer_name = persona.get('name', '消费者')
    persona_text = f"姓名: {consumer_name}\n背景: {persona.get('background', '')}\n详细情况: {persona.get('story', '')}"
    
    # 销售系统提示词
    seller_system = f"""你是这个内容的销售顾问。你深入了解内容的每个细节。

=== 你掌握的内容 ===
{content}
=== 内容结束 ===

【你的目标消费者】
{persona_text}

【销售策略】
Phase 1 (第1轮): 用一个有吸引力的开场白引起消费者兴趣，同时提出一个了解需求的问题
Phase 2 (第2-3轮): 深入了解消费者的具体需求和痛点
Phase 3 (第4-5轮): 匹配内容中的价值点到消费者需求，引用具体段落/数据
Phase 4 (第6-7轮): 处理异议，回应消费者的顾虑
Phase 5 (最后): 总结价值，询问消费者的决定

【行为要求】
- 主动引导对话，不要被动
- 引用内容中的具体信息（不要编造）
- 诚实但有说服力
- 每次发言控制在200字以内"""

    # 消费者系统提示词
    consumer_system = f"""你是一位真实的潜在用户。有人正在向你推介一个内容/产品。

【你的身份】
{persona_text}

【你的态度】
- 你有真实的需求，但不会轻易被说服
- 你会提出真实的质疑和顾虑
- 如果确实有价值，你愿意接受
- 如果觉得不适合你，你会明确拒绝

【行为要求】
1. 基于你的真实背景回应
2. 适当提出质疑和顾虑
3. 如果被说服了，具体说明原因
4. 最后做出明确决定：接受或拒绝"""

    interaction_log = []
    total_tokens_in = 0
    total_tokens_out = 0
    total_cost = 0.0
    
    try:
        for turn in range(max_turns):
            # 销售方发言
            seller_messages = [ChatMessage(role="system", content=seller_system)]
            for log in interaction_log:
                if log["role"] == "seller":
                    seller_messages.append(ChatMessage(role="assistant", content=log["content"]))
                else:
                    seller_messages.append(ChatMessage(role="user", content=log["content"]))
            
            if turn == 0:
                seller_messages.append(ChatMessage(role="user", content="请开始你的销售开场白。"))
            else:
                seller_messages.append(ChatMessage(role="user", content="请继续你的销售对话。"))
            
            seller_response = await ai_client.async_chat(seller_messages, temperature=0.7)
            total_tokens_in += seller_response.tokens_in
            total_tokens_out += seller_response.tokens_out
            total_cost += seller_response.cost
            
            interaction_log.append({
                "role": "seller",
                "name": "销售顾问",
                "content": seller_response.content,
                "turn": turn + 1,
                "phase": _get_sales_phase(turn),
            })
            
            # 消费者回应
            consumer_messages = [ChatMessage(role="system", content=consumer_system)]
            for log in interaction_log:
                if log["role"] == "consumer":
                    consumer_messages.append(ChatMessage(role="assistant", content=log["content"]))
                else:
                    consumer_messages.append(ChatMessage(role="user", content=log["content"]))
            
            consumer_response = await ai_client.async_chat(consumer_messages, temperature=0.8)
            total_tokens_in += consumer_response.tokens_in
            total_tokens_out += consumer_response.tokens_out
            total_cost += consumer_response.cost
            
            interaction_log.append({
                "role": "consumer",
                "name": consumer_name,
                "content": consumer_response.content,
                "turn": turn + 1,
            })
            
            # 检查是否决定了
            decision_signals = ["我决定", "我接受", "我不需要", "我拒绝", "我考虑", "可以", "好的"]
            if turn >= 3 and any(s in consumer_response.content for s in decision_signals):
                break
        
        # 评估阶段
        dialogue_transcript = "\n".join([
            f"[{log.get('name', log['role'])}]: {log['content']}"
            for log in interaction_log
        ])
        
        dimensions = ROLE_DIMENSIONS["seller"]
        dim_str = ", ".join([f'"{d}": 分数(1-10)' for d in dimensions])
        
        eval_messages = [
            ChatMessage(role="system", content=f"""你是一位销售效果评估专家。请分析以下销售对话的效果。

评估要点：
- 销售是否有效传达了内容的核心价值？
- 销售是否准确匹配了消费者的需求？
- 面对异议，销售处理得如何？
- 消费者最终是否被说服？"""),
            ChatMessage(role="user", content=f"""销售对话记录：
{dialogue_transcript}

请以JSON格式输出：
{{
    "scores": {{{dim_str}}},
    "comments": {{{", ".join([f'"{d}": "评语"' for d in dimensions])}}},
    "conversion": true/false,
    "conversion_factors": ["促成转化的因素"],
    "rejection_factors": ["阻碍转化的因素"],
    "content_strengths": ["内容的销售优势"],
    "content_gaps": ["内容需要补充的部分"],
    "summary": "销售效果总体评价（100-200字）"
}}"""),
        ]
        
        eval_response = await ai_client.async_chat(eval_messages, temperature=0.5)
        total_tokens_in += eval_response.tokens_in
        total_tokens_out += eval_response.tokens_out
        total_cost += eval_response.cost
        
        result_data = _parse_json_response(eval_response.content)
        scores = result_data.get("scores", {})
        avg_score = sum(scores.values()) / len(scores) if scores else 0
        
        return TrialResult(
            role="seller",
            interaction_mode="dialogue",
            nodes=[{"role": log["role"], "content": log["content"], "turn": log.get("turn"), "phase": log.get("phase")} for log in interaction_log],
            result={
                "scores": scores,
                "comments": result_data.get("comments", {}),
                "strengths": result_data.get("content_strengths", []),
                "weaknesses": result_data.get("content_gaps", []),
                "suggestions": result_data.get("rejection_factors", []),
                "conversion_factors": result_data.get("conversion_factors", []),
                "outcome": "converted" if result_data.get("conversion") else "not_converted",
                "summary": result_data.get("summary", ""),
            },
            overall_score=round(avg_score, 2),
            success=True,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            cost=total_cost,
        )
    except Exception as e:
        return TrialResult(
            role="seller",
            interaction_mode="dialogue",
            nodes=[{"role": log["role"], "content": log["content"]} for log in interaction_log],
            success=False,
            error=str(e),
        )


# ============== Diagnoser ==============

async def run_diagnoser(
    trial_results: List[TrialResult],
    content_summary: str = "",
    intent: str = "",
) -> dict:
    """
    跨 Trial 诊断器
    
    分析多个 Trial 的结果，找出系统性问题和改进优先级
    """
    if not trial_results:
        return {"summary": "无可分析的Trial结果", "patterns": [], "priorities": []}
    
    # 汇总各 Trial 结果
    trials_summary = []
    for tr in trial_results:
        if not tr.success:
            continue
        role_info = EVAL_ROLES.get(tr.role, {})
        summary_text = f"""## {role_info.get('name', tr.role)} ({role_info.get('icon', '')})
- 评分: {tr.overall_score}/10
- 模式: {tr.interaction_mode}
- 结果: {tr.result.get('outcome', 'N/A')}
- 总结: {tr.result.get('summary', 'N/A')}
- 优点: {', '.join(tr.result.get('strengths', []))}
- 问题: {', '.join(tr.result.get('weaknesses', []))}
- 建议: {', '.join(tr.result.get('suggestions', []))}
- 各维度评分: {json.dumps(tr.result.get('scores', {}), ensure_ascii=False)}"""
        trials_summary.append(summary_text)
    
    trials_text = "\n\n---\n\n".join(trials_summary)
    
    messages = [
        ChatMessage(role="system", content="""你是一位内容评估诊断专家。你需要分析多个评估角色的反馈，找出：
1. **跨角色一致性**: 多个角色是否指出了相同的问题？哪些角色的评价互相矛盾？
2. **系统性内容缺陷**: 被多个角色反复提到的问题是什么？
3. **改进优先级**: 哪些问题最值得优先修复？（基于影响面和修复成本）
4. **核心发现**: 最重要的3-5个发现

请输出严格的JSON格式。"""),
        ChatMessage(role="user", content=f"""# 项目意图
{intent or '未提供'}

# 各角色评估结果

{trials_text}

请进行跨角色诊断分析，输出JSON格式：
{{
    "overall_score": 综合评分(1-10),
    "consistency_analysis": "跨角色一致性分析（哪些评价一致，哪些矛盾）",
    "patterns": [
        {{
            "pattern": "被发现的模式/问题",
            "mentioned_by": ["提到这个问题的角色"],
            "severity": "high/medium/low",
            "description": "详细描述"
        }}
    ],
    "priorities": [
        {{
            "priority": 1,
            "issue": "最需要修复的问题",
            "suggested_action": "具体改进建议",
            "expected_impact": "预期影响"
        }}
    ],
    "key_findings": ["核心发现1", "核心发现2", "核心发现3"],
    "summary": "综合诊断总结（200-300字）"
}}"""),
    ]
    
    try:
        response = await ai_client.async_chat(messages, temperature=0.5)
        return _parse_json_response(response.content)
    except Exception as e:
        return {
            "overall_score": 0,
            "summary": f"诊断失败: {str(e)}",
            "patterns": [],
            "priorities": [],
            "key_findings": [],
            "error": str(e),
        }


# ============== 主入口 ==============

async def run_eval(
    content: str,
    roles: List[str] = None,
    creator_profile: str = "",
    intent: str = "",
    personas: List[dict] = None,
    max_turns: int = 5,
    content_field_names: list = None,
) -> Tuple[List[TrialResult], dict]:
    """
    运行完整评估
    
    Args:
        content: 要评估的内容
        roles: 要使用的角色列表 (默认全部5个)
        creator_profile: 创作者特质
        intent: 项目意图
        personas: 消费者画像列表（用于 consumer 和 seller 角色）
        max_turns: 对话模式最大轮数
        content_field_names: 内容来源字段名
    
    Returns:
        (trial_results, diagnosis)
    """
    if roles is None:
        roles = ["coach", "editor", "expert", "consumer", "seller"]
    
    if personas is None:
        personas = [{
            "name": "典型用户",
            "background": "对该领域感兴趣的普通读者",
            "story": "希望通过内容获取有价值的信息和指导。",
        }]
    
    trial_results = []
    tasks = []
    
    for role in roles:
        if role in ("coach", "editor", "expert"):
            # 审查模式
            tasks.append(run_review_trial(
                role=role,
                content=content,
                creator_profile=creator_profile,
                intent=intent,
            ))
        elif role == "consumer":
            # 消费者对话模式（对每个 persona 运行一次）
            for persona in personas[:2]:  # 最多2个persona
                tasks.append(run_consumer_dialogue_trial(
                    content=content,
                    persona=persona,
                    max_turns=max_turns,
                    content_field_names=content_field_names,
                ))
        elif role == "seller":
            # 销售对话模式（对每个 persona 运行一次）
            for persona in personas[:2]:  # 最多2个persona
                tasks.append(run_seller_dialogue_trial(
                    content=content,
                    persona=persona,
                    max_turns=max_turns,
                ))
    
    # 并行执行所有 Trial
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, Exception):
            trial_results.append(TrialResult(
                role="unknown",
                interaction_mode="unknown",
                success=False,
                error=str(result),
            ))
        else:
            trial_results.append(result)
    
    # 运行诊断器
    diagnosis = await run_diagnoser(
        trial_results=trial_results,
        content_summary=content[:500] if content else "",
        intent=intent,
    )
    
    return trial_results, diagnosis


# ============== 工具函数 ==============

def _parse_json_response(text: str) -> dict:
    """安全解析 AI 返回的 JSON"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 尝试提取 JSON 块
    import re
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 尝试找到第一个 { 和最后一个 }
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass
    
    # 全部失败
    return {"raw_output": text, "parse_error": True}


def _get_sales_phase(turn: int) -> str:
    """获取销售阶段名称"""
    if turn == 0:
        return "opening"
    elif turn <= 2:
        return "need_discovery"
    elif turn <= 4:
        return "value_matching"
    elif turn <= 6:
        return "objection_handling"
    else:
        return "closing"


def format_trial_result_markdown(trial: TrialResult) -> str:
    """将 Trial 结果格式化为 Markdown"""
    role_info = EVAL_ROLES.get(trial.role, {"name": trial.role, "icon": "📋"})
    
    md = f"## {role_info['icon']} {role_info['name']}评估\n\n"
    
    if not trial.success:
        md += f"❌ 评估失败: {trial.error}\n"
        return md
    
    md += f"**综合评分: {trial.overall_score}/10** | 模式: {trial.interaction_mode}\n\n"
    
    # 各维度评分
    scores = trial.result.get("scores", {})
    if scores:
        md += "### 各维度评分\n"
        for dim, score in scores.items():
            bar = "█" * int(score) + "░" * (10 - int(score))
            md += f"- {dim}: **{score}/10** {bar}\n"
            comment = trial.result.get("comments", {}).get(dim, "")
            if comment:
                md += f"  - {comment}\n"
        md += "\n"
    
    # 对话记录（对话模式）
    if trial.interaction_mode == "dialogue" and trial.nodes:
        md += "### 对话记录\n"
        for node in trial.nodes:
            role_label = {"consumer": "🗣 消费者", "seller": "💼 销售", "content_rep": "📄 内容"}.get(node.get("role"), node.get("role", ""))
            md += f"**{role_label}** (第{node.get('turn', '?')}轮): {node.get('content', '')}\n\n"
    
    # 优点
    strengths = trial.result.get("strengths", [])
    if strengths:
        md += "### ✅ 优点\n"
        for s in strengths:
            md += f"- {s}\n"
        md += "\n"
    
    # 问题
    weaknesses = trial.result.get("weaknesses", [])
    if weaknesses:
        md += "### ⚠️ 问题\n"
        for w in weaknesses:
            md += f"- {w}\n"
        md += "\n"
    
    # 建议
    suggestions = trial.result.get("suggestions", [])
    if suggestions:
        md += "### 💡 改进建议\n"
        for s in suggestions:
            md += f"- {s}\n"
        md += "\n"
    
    # 总结
    summary = trial.result.get("summary", "")
    if summary:
        md += f"### 总结\n{summary}\n\n"
    
    # 结果判定
    outcome = trial.result.get("outcome", "")
    if outcome:
        outcome_map = {
            "converted": "✅ 转化成功",
            "not_converted": "❌ 未转化",
            "recommended": "👍 推荐",
            "not_recommended": "👎 不推荐",
            "reviewed": "📝 已审查",
        }
        md += f"**结果: {outcome_map.get(outcome, outcome)}**\n\n"
    
    return md


def format_diagnosis_markdown(diagnosis: dict) -> str:
    """将诊断结果格式化为 Markdown"""
    md = "## 🔍 综合诊断\n\n"
    
    overall = diagnosis.get("overall_score")
    if overall:
        md += f"**综合评分: {overall}/10**\n\n"
    
    # 一致性分析
    consistency = diagnosis.get("consistency_analysis", "")
    if consistency:
        md += f"### 跨角色一致性\n{consistency}\n\n"
    
    # 发现的模式
    patterns = diagnosis.get("patterns", [])
    if patterns:
        md += "### 系统性问题\n"
        for p in patterns:
            severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(p.get("severity", ""), "⚪")
            md += f"- {severity_icon} **{p.get('pattern', '')}** (提到: {', '.join(p.get('mentioned_by', []))})\n"
            md += f"  {p.get('description', '')}\n"
        md += "\n"
    
    # 改进优先级
    priorities = diagnosis.get("priorities", [])
    if priorities:
        md += "### 改进优先级\n"
        for p in priorities:
            md += f"**{p.get('priority', '?')}. {p.get('issue', '')}**\n"
            md += f"- 建议操作: {p.get('suggested_action', '')}\n"
            md += f"- 预期影响: {p.get('expected_impact', '')}\n\n"
    
    # 核心发现
    findings = diagnosis.get("key_findings", [])
    if findings:
        md += "### 核心发现\n"
        for f in findings:
            md += f"- {f}\n"
        md += "\n"
    
    # 总结
    summary = diagnosis.get("summary", "")
    if summary:
        md += f"### 总结\n{summary}\n"
    
    return md
