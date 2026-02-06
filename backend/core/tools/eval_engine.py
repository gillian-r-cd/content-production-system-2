# backend/core/tools/eval_engine.py
# 功能: Eval V2 评估执行引擎
# 主要函数:
#   - run_task_trial(): 执行单个 EvalTask 的一次 Trial（核心）
#   - run_grader(): 对 Trial 结果进行评分（内容/过程/综合）
#   - run_diagnoser(): 跨 Trial 诊断
#   - run_eval_run(): 执行整个 EvalRun（并行执行所有 Task）
#   - format_*(): 格式化输出
# 数据结构:
#   - LLMCall: 一次 LLM 调用的完整记录（输入/输出/token/耗时）
#   - TrialResult: Trial 执行结果（含 llm_calls 列表）

"""
Eval V2 引擎
Task-based 评估体系：
  EvalRun → EvalTask[] → EvalTrial[]
  每个 Trial 记录完整的 LLM 调用日志
  Grader 分离：内容评分 + 过程评分
"""

import json
import time
import asyncio
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from core.ai_client import ai_client, ChatMessage
from core.models.eval_task import SIMULATOR_TYPES


# ============== 数据结构 ==============

@dataclass
class LLMCall:
    """一次 LLM 调用的完整记录"""
    step: str           # "simulator_review" / "consumer_turn_1" / "content_rep_turn_1" / "grader_content" / "grader_process" / "diagnoser"
    input_system: str   # 系统提示词
    input_user: str     # 用户消息
    output: str         # AI 响应
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    duration_ms: int = 0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "input": {"system_prompt": self.input_system, "user_message": self.input_user},
            "output": self.output,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost": self.cost,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp or datetime.now().isoformat(),
        }


@dataclass
class TrialResult:
    """Trial 执行结果"""
    role: str
    interaction_mode: str
    role_display_name: str = ""  # 用户配置的模拟器显示名称
    nodes: list = field(default_factory=list)          # 交互节点
    result: dict = field(default_factory=dict)          # 评分结果
    grader_outputs: list = field(default_factory=list)  # Grader 输出
    llm_calls: list = field(default_factory=list)       # 完整 LLM 调用日志
    overall_score: float = 0.0
    success: bool = True
    error: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0


# ============== LLM 调用封装（带日志） ==============

async def _call_llm(
    system_prompt: str,
    user_message: str,
    step: str,
    temperature: float = 0.6,
) -> Tuple[str, LLMCall]:
    """
    封装 LLM 调用，返回 (响应文本, LLMCall 日志)
    所有 eval 相关的 LLM 调用都走这个函数，确保每次调用都被记录
    """
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_message),
    ]
    
    start_time = time.time()
    response = await ai_client.async_chat(messages, temperature=temperature)
    duration_ms = int((time.time() - start_time) * 1000)
    
    call = LLMCall(
        step=step,
        input_system=system_prompt,
        input_user=user_message,
        output=response.content,
        tokens_in=response.tokens_in,
        tokens_out=response.tokens_out,
        cost=response.cost,
        duration_ms=duration_ms,
        timestamp=datetime.now().isoformat(),
    )
    
    return response.content, call


async def _call_llm_multi(
    messages: List[ChatMessage],
    step: str,
    temperature: float = 0.6,
) -> Tuple[str, LLMCall]:
    """多消息版本的 LLM 调用（用于多轮对话）"""
    start_time = time.time()
    response = await ai_client.async_chat(messages, temperature=temperature)
    duration_ms = int((time.time() - start_time) * 1000)
    
    # 提取系统和用户消息用于日志
    system_prompt = ""
    user_messages = []
    for m in messages:
        if m.role == "system":
            system_prompt = m.content
        elif m.role == "user":
            user_messages.append(m.content)
    
    call = LLMCall(
        step=step,
        input_system=system_prompt,
        input_user="\n---\n".join(user_messages[-2:]) if user_messages else "",  # 最近2条
        output=response.content,
        tokens_in=response.tokens_in,
        tokens_out=response.tokens_out,
        cost=response.cost,
        duration_ms=duration_ms,
        timestamp=datetime.now().isoformat(),
    )
    
    return response.content, call


# ============== 核心执行函数 ==============

async def run_task_trial(
    simulator_type: str,
    interaction_mode: str,
    content: str,
    creator_profile: str = "",
    intent: str = "",
    persona: dict = None,
    simulator_config: dict = None,
    grader_config: dict = None,
    content_field_names: list = None,
) -> TrialResult:
    """
    执行单个 EvalTask 的一次 Trial
    
    这是 eval 引擎的核心函数。根据 simulator_type 和 interaction_mode 
    选择执行策略，所有 LLM 调用都被完整记录。
    
    Args:
        simulator_type: 模拟器角色 (coach/editor/expert/consumer/seller/custom)
        interaction_mode: 交互模式 (review/dialogue/scenario)
        content: 要评估的内容
        creator_profile: 创作者特质
        intent: 项目意图
        persona: 消费者画像
        simulator_config: 模拟器自定义配置
        grader_config: 评分器配置
        content_field_names: 内容字段名列表
    
    Returns:
        TrialResult
    """
    config = simulator_config or {}
    grader_cfg = grader_config or {}
    
    # 获取模拟器显示名称（优先用后台配置的名称，其次用硬编码名称）
    display_name = config.get("simulator_name", "") or SIMULATOR_TYPES.get(simulator_type, {}).get("name", simulator_type)
    
    if interaction_mode == "review":
        result = await _run_review(
            simulator_type, content, creator_profile, intent, persona, config, grader_cfg
        )
    elif interaction_mode == "dialogue":
        result = await _run_dialogue(
            simulator_type, content, creator_profile, intent, persona, config, grader_cfg, content_field_names
        )
    elif interaction_mode == "scenario":
        result = await _run_dialogue(
            simulator_type, content, creator_profile, intent, persona, config, grader_cfg, content_field_names
        )
    else:
        return TrialResult(
            role=simulator_type, interaction_mode=interaction_mode,
            success=False, error=f"不支持的交互模式: {interaction_mode}"
        )
    
    result.role_display_name = display_name
    return result


async def _run_review(
    simulator_type: str,
    content: str,
    creator_profile: str,
    intent: str,
    persona: dict,
    config: dict,
    grader_cfg: dict,
) -> TrialResult:
    """审查模式：AI 一次性阅读全部内容，给出结构化反馈"""
    llm_calls = []
    
    # 获取系统提示词（优先后台配置 > 硬编码 SIMULATOR_TYPES）
    type_info = SIMULATOR_TYPES.get(simulator_type, {})
    custom_prompt = config.get("system_prompt", "")
    if custom_prompt:
        # 替换占位符
        persona_text_for_sub = json.dumps(persona, ensure_ascii=False) if persona else ""
        base_prompt = custom_prompt.replace("{content}", content).replace("{persona}", persona_text_for_sub)
    else:
        base_prompt = type_info.get("system_prompt", "请评估以下内容。")
    
    # 注入上下文
    system_prompt = base_prompt
    if creator_profile:
        system_prompt += f"\n\n【创作者特质】\n{creator_profile}"
    if intent:
        system_prompt += f"\n\n【项目意图】\n{intent}"
    if persona:
        persona_text = json.dumps(persona, ensure_ascii=False)
        system_prompt += f"\n\n【目标消费者】\n{persona_text}"
    
    # 获取评分维度
    dimensions = grader_cfg.get("dimensions", []) or type_info.get("default_dimensions", ["综合评价"])
    dim_str = ", ".join([f'"{d}": 分数(1-10)' for d in dimensions])
    dim_comment_str = ", ".join([f'"{d}": "具体评语（至少2句话）"' for d in dimensions])
    
    user_message = f"""以下是要评估的内容：

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

    try:
        response_text, call = await _call_llm(
            system_prompt, user_message,
            step=f"simulator_{simulator_type}_review",
            temperature=0.6,
        )
        llm_calls.append(call)
        
        result_data = _parse_json_response(response_text)
        scores = result_data.get("scores", {})
        avg_score = sum(v for v in scores.values() if isinstance(v, (int, float))) / len(scores) if scores else 0
        
        # 运行 Grader
        grader_outputs = []
        grader_result, grader_call = await _run_content_grader(
            content, result_data, dimensions, grader_cfg
        )
        if grader_call:
            llm_calls.append(grader_call)
            grader_outputs.append(grader_result)
        
        total_tokens_in = sum(c.tokens_in for c in llm_calls)
        total_tokens_out = sum(c.tokens_out for c in llm_calls)
        total_cost = sum(c.cost for c in llm_calls)
        
        return TrialResult(
            role=simulator_type,
            interaction_mode="review",
            nodes=[
                {"role": "system", "content": system_prompt[:500] + "..."},
                {"role": "user", "content": user_message[:500] + "..."},
                {"role": "assistant", "content": response_text},
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
            grader_outputs=grader_outputs,
            llm_calls=[c.to_dict() for c in llm_calls],
            overall_score=round(avg_score, 2),
            success=True,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            cost=total_cost,
        )
    except Exception as e:
        return TrialResult(
            role=simulator_type, interaction_mode="review",
            llm_calls=[c.to_dict() for c in llm_calls],
            success=False, error=str(e),
        )


async def _run_dialogue(
    simulator_type: str,
    content: str,
    creator_profile: str,
    intent: str,
    persona: dict,
    config: dict,
    grader_cfg: dict,
    content_field_names: list = None,
) -> TrialResult:
    """对话模式：多轮交互，模拟真实用户与内容的互动"""
    llm_calls = []
    interaction_log = []
    max_turns = config.get("max_turns", 5)
    
    persona = persona or {"name": "典型用户", "background": "对该领域感兴趣的读者"}
    user_name = persona.get("name", "消费者")
    persona_text = json.dumps(persona, ensure_ascii=False, indent=2)
    
    content_name = "内容"
    if content_field_names:
        content_name = f"《{content_field_names[0]}》" if len(content_field_names) == 1 else f"《{content_field_names[0]}》等{len(content_field_names)}篇"
    
    # 根据 simulator_type 确定对话方向
    if simulator_type == "seller":
        # 销售模式：销售方主动，消费者回应
        return await _run_seller_dialogue(
            content, persona, config, grader_cfg, llm_calls, content_field_names
        )
    
    # 用户自定义的 simulator 提示词（来自后台配置）
    custom_sim_prompt = config.get("system_prompt", "")
    sim_name = config.get("simulator_name", simulator_type)
    
    # 通用对话模式：消费者提问，内容代表回答
    if custom_sim_prompt:
        # 用后台配置的提示词，替换占位符
        consumer_system = custom_sim_prompt.replace("{persona}", persona_text).replace("{content}", content)
        if persona_text not in consumer_system and "{persona}" not in custom_sim_prompt:
            consumer_system += f"\n\n【你扮演的消费者角色】\n{persona_text}"
    else:
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

    # 内容代表/第二方的提示词：优先用后台配置的 secondary_prompt
    custom_secondary = config.get("secondary_prompt", "")
    if custom_secondary:
        # 用后台配置的提示词，替换 {content} 占位符
        content_system = custom_secondary.replace("{content}", content).replace("{persona}", persona_text)
    else:
        content_system = f"""你是{content_name}的内容代表，严格基于以下内容回答问题。

=== 内容开始 ===
{content}
=== 内容结束 ===

【回答规则】
1. 严格基于内容回答，不要编造
2. 如果内容中没有涉及，诚实说明
3. 尽量引用内容中的原话或核心观点"""

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
            
            user_response_text, user_call = await _call_llm_multi(
                user_messages, step=f"consumer_turn_{turn+1}", temperature=0.8
            )
            llm_calls.append(user_call)
            
            interaction_log.append({
                "role": "consumer", "name": user_name,
                "content": user_response_text, "turn": turn + 1,
            })
            
            # 检查是否结束
            end_signals = ["了解了", "明白了", "好的谢谢", "谢谢", "再见", "不需要了", "足够了", "清楚了"]
            if any(s in user_response_text for s in end_signals):
                break
            
            # 内容代表回复
            content_messages = [ChatMessage(role="system", content=content_system)]
            for log in interaction_log:
                if log["role"] == "consumer":
                    content_messages.append(ChatMessage(role="user", content=log["content"]))
                else:
                    content_messages.append(ChatMessage(role="assistant", content=log["content"]))
            
            content_response_text, content_call = await _call_llm_multi(
                content_messages, step=f"content_rep_turn_{turn+1}", temperature=0.5
            )
            llm_calls.append(content_call)
            
            interaction_log.append({
                "role": "content_rep", "name": content_name,
                "content": content_response_text, "turn": turn + 1,
            })
        
        # 评估阶段 - 内容评分 (Grader)
        dialogue_transcript = "\n".join([
            f"[{log.get('name', log['role'])}]: {log['content']}"
            for log in interaction_log
        ])
        
        type_info = SIMULATOR_TYPES.get(simulator_type, {})
        dimensions = grader_cfg.get("dimensions", []) or type_info.get("default_dimensions", ["综合评价"])
        dim_str = ", ".join([f'"{d}": 分数(1-10)' for d in dimensions])
        
        eval_system = f"""你是{user_name}，刚刚完成了一次咨询对话。
你的背景：{persona_text}
请评估内容对你的帮助程度。"""
        
        eval_user = f"""对话记录：
{dialogue_transcript}

请以JSON格式输出：
{{
    "scores": {{{dim_str}}},
    "comments": {{{", ".join([f'"{d}": "评语"' for d in dimensions])}}},
    "problems_solved": ["被解决的问题"],
    "problems_unsolved": ["未被解决的问题"],
    "content_gaps": ["内容缺失的部分"],
    "would_recommend": true,
    "summary": "总体评价（100字以内）"
}}"""
        
        eval_text, eval_call = await _call_llm(
            eval_system, eval_user,
            step=f"grader_content_{simulator_type}",
            temperature=0.5,
        )
        llm_calls.append(eval_call)
        
        result_data = _parse_json_response(eval_text)
        scores = result_data.get("scores", {})
        avg_score = sum(v for v in scores.values() if isinstance(v, (int, float))) / len(scores) if scores else 0
        
        # 过程评分 (Process Grader)
        grader_outputs = []
        process_grader, process_call = await _run_process_grader(
            dialogue_transcript, dimensions, grader_cfg
        )
        if process_call:
            llm_calls.append(process_call)
            grader_outputs.append(process_grader)
        
        total_tokens_in = sum(c.tokens_in for c in llm_calls)
        total_tokens_out = sum(c.tokens_out for c in llm_calls)
        total_cost = sum(c.cost for c in llm_calls)
        
        return TrialResult(
            role=simulator_type,
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
            grader_outputs=grader_outputs,
            llm_calls=[c.to_dict() for c in llm_calls],
            overall_score=round(avg_score, 2),
            success=True,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            cost=total_cost,
        )
    except Exception as e:
        return TrialResult(
            role=simulator_type, interaction_mode="dialogue",
            nodes=[{"role": log["role"], "content": log["content"]} for log in interaction_log],
            llm_calls=[c.to_dict() for c in llm_calls],
            success=False, error=str(e),
        )


async def _run_seller_dialogue(
    content: str,
    persona: dict,
    config: dict,
    grader_cfg: dict,
    llm_calls: list,
    content_field_names: list = None,
) -> TrialResult:
    """销售对话：销售顾问主动推介，消费者回应"""
    max_turns = config.get("max_turns", 8)
    consumer_name = persona.get("name", "消费者")
    persona_text = json.dumps(persona, ensure_ascii=False, indent=2)
    interaction_log = []
    
    # 销售方提示词：优先用后台配置
    custom_primary = config.get("system_prompt", "")
    if custom_primary:
        seller_system = custom_primary.replace("{content}", content).replace("{persona}", persona_text)
    else:
        seller_system = f"""你是这个内容的销售顾问。你深入了解内容的每个细节。

=== 你掌握的内容 ===
{content}
=== 内容结束 ===

【你的目标消费者】
{persona_text}

【销售策略】
Phase 1 (第1轮): 有吸引力的开场白，同时提出一个了解需求的问题
Phase 2 (第2-3轮): 深入了解消费者的具体需求和痛点
Phase 3 (第4-5轮): 匹配内容中的价值点到消费者需求
Phase 4 (第6-7轮): 处理异议
Phase 5 (最后): 总结价值，询问决定

【行为要求】- 主动引导对话 - 引用具体信息 - 诚实但有说服力 - 每次200字以内"""

    # 消费者方提示词：优先用后台配置的 secondary_prompt
    custom_secondary = config.get("secondary_prompt", "")
    if custom_secondary:
        consumer_system = custom_secondary.replace("{persona}", persona_text).replace("{content}", content)
    else:
        consumer_system = f"""你是一位真实的潜在用户。有人正在向你推介内容/产品。

【你的身份】
{persona_text}

【你的态度】- 有真实需求，但不轻易被说服 - 会提出真实质疑 - 如果确实有价值，愿意接受 - 不适合就明确拒绝

【行为要求】基于真实背景回应，适当质疑，最后做出明确决定。"""

    try:
        for turn in range(max_turns):
            # 销售发言
            seller_messages = [ChatMessage(role="system", content=seller_system)]
            for log in interaction_log:
                if log["role"] == "seller":
                    seller_messages.append(ChatMessage(role="assistant", content=log["content"]))
                else:
                    seller_messages.append(ChatMessage(role="user", content=log["content"]))
            seller_messages.append(ChatMessage(role="user", content="请开始你的销售开场白。" if turn == 0 else "请继续。"))
            
            seller_text, seller_call = await _call_llm_multi(
                seller_messages, step=f"seller_turn_{turn+1}", temperature=0.7
            )
            llm_calls.append(seller_call)
            interaction_log.append({"role": "seller", "name": "销售顾问", "content": seller_text, "turn": turn + 1, "phase": _get_sales_phase(turn)})
            
            # 消费者回应
            consumer_messages = [ChatMessage(role="system", content=consumer_system)]
            for log in interaction_log:
                if log["role"] == "consumer":
                    consumer_messages.append(ChatMessage(role="assistant", content=log["content"]))
                else:
                    consumer_messages.append(ChatMessage(role="user", content=log["content"]))
            
            consumer_text, consumer_call = await _call_llm_multi(
                consumer_messages, step=f"consumer_turn_{turn+1}", temperature=0.8
            )
            llm_calls.append(consumer_call)
            interaction_log.append({"role": "consumer", "name": consumer_name, "content": consumer_text, "turn": turn + 1})
            
            # 检查决定
            decision_signals = ["我决定", "我接受", "我不需要", "我拒绝", "可以", "好的"]
            if turn >= 3 and any(s in consumer_text for s in decision_signals):
                break
        
        # 评估
        dialogue_transcript = "\n".join([f"[{log.get('name', log['role'])}]: {log['content']}" for log in interaction_log])
        
        dimensions = grader_cfg.get("dimensions", []) or SIMULATOR_TYPES.get("seller", {}).get("default_dimensions", ["综合评价"])
        dim_str = ", ".join([f'"{d}": 分数(1-10)' for d in dimensions])
        
        eval_text, eval_call = await _call_llm(
            "你是一位销售效果评估专家。请分析以下销售对话的效果。",
            f"""销售对话记录：
{dialogue_transcript}

请以JSON格式输出：
{{
    "scores": {{{dim_str}}},
    "comments": {{{", ".join([f'"{d}": "评语"' for d in dimensions])}}},
    "conversion": true,
    "conversion_factors": ["因素"],
    "rejection_factors": ["因素"],
    "content_strengths": ["优势"],
    "content_gaps": ["缺失"],
    "summary": "销售效果总体评价（100-200字）"
}}""",
            step="grader_content_seller",
            temperature=0.5,
        )
        llm_calls.append(eval_call)
        
        result_data = _parse_json_response(eval_text)
        scores = result_data.get("scores", {})
        avg_score = sum(v for v in scores.values() if isinstance(v, (int, float))) / len(scores) if scores else 0
        
        # 过程评分
        grader_outputs = []
        process_grader, process_call = await _run_process_grader(dialogue_transcript, dimensions, grader_cfg)
        if process_call:
            llm_calls.append(process_call)
            grader_outputs.append(process_grader)
        
        total_tokens_in = sum(c.tokens_in for c in llm_calls)
        total_tokens_out = sum(c.tokens_out for c in llm_calls)
        total_cost = sum(c.cost for c in llm_calls)
        
        return TrialResult(
            role="seller", interaction_mode="dialogue",
            nodes=[{"role": log["role"], "content": log["content"], "turn": log.get("turn"), "phase": log.get("phase")} for log in interaction_log],
            result={
                "scores": scores, "comments": result_data.get("comments", {}),
                "strengths": result_data.get("content_strengths", []),
                "weaknesses": result_data.get("content_gaps", []),
                "suggestions": result_data.get("rejection_factors", []),
                "conversion_factors": result_data.get("conversion_factors", []),
                "outcome": "converted" if result_data.get("conversion") else "not_converted",
                "summary": result_data.get("summary", ""),
            },
            grader_outputs=grader_outputs,
            llm_calls=[c.to_dict() for c in llm_calls],
            overall_score=round(avg_score, 2),
            success=True,
            tokens_in=total_tokens_in, tokens_out=total_tokens_out, cost=total_cost,
        )
    except Exception as e:
        return TrialResult(
            role="seller", interaction_mode="dialogue",
            nodes=[{"role": log["role"], "content": log["content"]} for log in interaction_log],
            llm_calls=[c.to_dict() for c in llm_calls],
            success=False, error=str(e),
        )


# ============== Grader 系统 ==============

async def _run_content_grader(
    content: str,
    trial_result_data: dict,
    dimensions: list,
    grader_cfg: dict,
) -> Tuple[dict, Optional[LLMCall]]:
    """
    内容评分器 - 直接评价内容本身的质量
    在 review 模式下使用
    """
    custom_prompt = grader_cfg.get("custom_prompt", "")
    grader_type = grader_cfg.get("type", "content")
    
    if grader_type not in ("content", "combined"):
        return {}, None
    
    system_prompt = custom_prompt or """你是一个内容质量评分专家。基于之前角色的评估反馈，
请对内容进行独立的质量评分，关注内容本身的客观质量。
输出JSON格式的评分。"""
    
    user_message = f"""内容摘要（前1000字）：
{content[:1000]}

角色评估反馈摘要：
- 优点: {trial_result_data.get('strengths', [])}
- 问题: {trial_result_data.get('weaknesses', [])}
- 总结: {trial_result_data.get('summary', '')}

请输出JSON：
{{
    "grader_type": "content",
    "quality_score": 分数(1-10),
    "analysis": "内容质量分析（50-100字）",
    "key_issues": ["关键问题1", "关键问题2"]
}}"""

    try:
        text, call = await _call_llm(system_prompt, user_message, step="grader_content", temperature=0.4)
        result = _parse_json_response(text)
        result["grader_type"] = "content"
        return result, call
    except Exception:
        return {"grader_type": "content", "error": "评分失败"}, None


async def _run_process_grader(
    dialogue_transcript: str,
    dimensions: list,
    grader_cfg: dict,
) -> Tuple[dict, Optional[LLMCall]]:
    """
    过程评分器 - 评价互动过程的质量
    在 dialogue/scenario 模式下使用
    """
    grader_type = grader_cfg.get("type", "content")
    
    if grader_type not in ("process", "combined"):
        return {}, None
    
    system_prompt = """你是一个交互过程评估专家。请分析以下对话过程的质量。
关注：对话流畅性、问题解决效率、信息传递有效性、用户体验。"""

    user_message = f"""对话记录：
{dialogue_transcript}

请输出JSON：
{{
    "grader_type": "process",
    "process_score": 分数(1-10),
    "dialogue_quality": "对话质量分析",
    "information_delivery": "信息传递效率评估",
    "user_experience": "用户体验评估",
    "key_moments": ["对话中的关键时刻/转折点"]
}}"""

    try:
        text, call = await _call_llm(system_prompt, user_message, step="grader_process", temperature=0.4)
        result = _parse_json_response(text)
        result["grader_type"] = "process"
        return result, call
    except Exception:
        return {"grader_type": "process", "error": "评分失败"}, None


# ============== Diagnoser ==============

async def run_diagnoser(
    trial_results: List[TrialResult],
    content_summary: str = "",
    intent: str = "",
) -> Tuple[dict, Optional[LLMCall]]:
    """
    跨 Trial 诊断器 - 分析多个 Trial 的结果，找出系统性问题
    
    Returns:
        (diagnosis_dict, LLMCall_or_None)
    """
    if not trial_results:
        return {"summary": "无可分析的Trial结果", "patterns": [], "priorities": []}, None
    
    trials_summary = []
    for tr in trial_results:
        if not tr.success:
            continue
        # 优先使用配置的显示名称，避免用硬编码的 "教练/编辑/专家"
        display_name = tr.role_display_name or SIMULATOR_TYPES.get(tr.role, {}).get("name", tr.role)
        type_icon = SIMULATOR_TYPES.get(tr.role, {}).get("icon", "🔍")
        summary_text = f"""## {display_name} ({type_icon})
- 评分: {tr.overall_score}/10 | 模式: {tr.interaction_mode}
- 结果: {tr.result.get('outcome', 'N/A')}
- 总结: {tr.result.get('summary', 'N/A')}
- 优点: {', '.join(tr.result.get('strengths', []))}
- 问题: {', '.join(tr.result.get('weaknesses', []))}
- 建议: {', '.join(tr.result.get('suggestions', []))}
- 评分: {json.dumps(tr.result.get('scores', {}), ensure_ascii=False)}"""
        trials_summary.append(summary_text)
    
    trials_text = "\n\n---\n\n".join(trials_summary)
    
    system_prompt = """你是一位内容评估诊断专家。分析多个评估角色的反馈，找出：
1. **跨角色一致性**: 多个角色是否指出了相同的问题？矛盾在哪？
2. **系统性缺陷**: 被多个角色反复提到的问题是什么？
3. **改进优先级**: 哪些问题最值得先修复？
4. **核心发现**: 最重要的3-5个发现

请输出严格的JSON格式。"""

    user_message = f"""# 项目意图
{intent or '未提供'}

# 各角色评估结果

{trials_text}

请进行跨角色诊断分析，输出JSON格式：
{{
    "overall_score": 综合评分(1-10),
    "consistency_analysis": "跨角色一致性分析",
    "patterns": [
        {{"pattern": "模式", "mentioned_by": ["角色"], "severity": "high/medium/low", "description": "描述"}}
    ],
    "priorities": [
        {{"priority": 1, "issue": "问题", "suggested_action": "建议", "expected_impact": "影响"}}
    ],
    "key_findings": ["发现1", "发现2", "发现3"],
    "summary": "综合诊断总结（200-300字）"
}}"""

    try:
        text, call = await _call_llm(system_prompt, user_message, step="diagnoser", temperature=0.5)
        result = _parse_json_response(text)
        return result, call
    except Exception as e:
        return {
            "overall_score": 0, "summary": f"诊断失败: {str(e)}",
            "patterns": [], "priorities": [], "key_findings": [], "error": str(e),
        }, None


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
    兼容旧接口：运行完整评估（所有角色并行执行）
    
    新代码应使用 run_task_trial() 逐个 Task 执行
    """
    if roles is None:
        roles = ["coach", "editor", "expert", "consumer", "seller"]
    
    if personas is None:
        personas = [{"name": "典型用户", "background": "对该领域感兴趣的普通读者"}]
    
    tasks = []
    
    for role in roles:
        if role in ("coach", "editor", "expert"):
            tasks.append(run_task_trial(
                simulator_type=role, interaction_mode="review",
                content=content, creator_profile=creator_profile, intent=intent,
                grader_config={"type": "content", "dimensions": []},
            ))
        elif role == "consumer":
            for persona in personas[:2]:
                tasks.append(run_task_trial(
                    simulator_type=role, interaction_mode="dialogue",
                    content=content, creator_profile=creator_profile, intent=intent,
                    persona=persona,
                    simulator_config={"max_turns": max_turns},
                    grader_config={"type": "combined", "dimensions": []},
                    content_field_names=content_field_names,
                ))
        elif role == "seller":
            for persona in personas[:2]:
                tasks.append(run_task_trial(
                    simulator_type=role, interaction_mode="dialogue",
                    content=content, creator_profile=creator_profile, intent=intent,
                    persona=persona,
                    simulator_config={"max_turns": max_turns},
                    grader_config={"type": "combined", "dimensions": []},
                    content_field_names=content_field_names,
                ))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    trial_results = []
    for result in results:
        if isinstance(result, Exception):
            trial_results.append(TrialResult(
                role="unknown", interaction_mode="unknown",
                success=False, error=str(result),
            ))
        else:
            trial_results.append(result)
    
    diagnosis, _ = await run_diagnoser(trial_results, content[:500] if content else "", intent)
    
    return trial_results, diagnosis


# ============== 工具函数 ==============

def _parse_json_response(text: str) -> dict:
    """安全解析 AI 返回的 JSON"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    import re
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass
    
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
    type_info = SIMULATOR_TYPES.get(trial.role, {"name": trial.role, "icon": "📋"})
    
    md = f"## {type_info.get('icon', '📋')} {type_info.get('name', trial.role)}评估\n\n"
    
    if not trial.success:
        md += f"❌ 评估失败: {trial.error}\n"
        return md
    
    md += f"**综合评分: {trial.overall_score}/10** | 模式: {trial.interaction_mode}\n\n"
    
    scores = trial.result.get("scores", {})
    if scores:
        md += "### 各维度评分\n"
        for dim, score in scores.items():
            if isinstance(score, (int, float)):
                bar = "█" * int(score) + "░" * (10 - int(score))
                md += f"- {dim}: **{score}/10** {bar}\n"
                comment = trial.result.get("comments", {}).get(dim, "")
                if comment:
                    md += f"  - {comment}\n"
        md += "\n"
    
    if trial.interaction_mode == "dialogue" and trial.nodes:
        md += "### 对话记录\n"
        for node in trial.nodes:
            role_label = {"consumer": "🗣 消费者", "seller": "💼 销售", "content_rep": "📄 内容"}.get(node.get("role"), node.get("role", ""))
            md += f"**{role_label}** (第{node.get('turn', '?')}轮): {node.get('content', '')}\n\n"
    
    for label, key, icon in [("优点", "strengths", "✅"), ("问题", "weaknesses", "⚠️"), ("改进建议", "suggestions", "💡")]:
        items = trial.result.get(key, [])
        if items:
            md += f"### {icon} {label}\n"
            for s in items:
                md += f"- {s}\n"
            md += "\n"
    
    summary = trial.result.get("summary", "")
    if summary:
        md += f"### 总结\n{summary}\n\n"
    
    outcome = trial.result.get("outcome", "")
    if outcome:
        outcome_map = {
            "converted": "✅ 转化成功", "not_converted": "❌ 未转化",
            "recommended": "👍 推荐", "not_recommended": "👎 不推荐", "reviewed": "📝 已审查",
        }
        md += f"**结果: {outcome_map.get(outcome, outcome)}**\n\n"
    
    # LLM 调用统计
    if trial.llm_calls:
        md += f"---\n📊 共 {len(trial.llm_calls)} 次 LLM 调用 | "
        md += f"Tokens: {trial.tokens_in}↑ {trial.tokens_out}↓ | "
        md += f"费用: ¥{trial.cost:.4f}\n"
    
    return md


def format_diagnosis_markdown(diagnosis: dict) -> str:
    """将诊断结果格式化为 Markdown"""
    md = "## 🔍 综合诊断\n\n"
    
    overall = diagnosis.get("overall_score")
    if overall:
        md += f"**综合评分: {overall}/10**\n\n"
    
    consistency = diagnosis.get("consistency_analysis", "")
    if consistency:
        md += f"### 跨角色一致性\n{consistency}\n\n"
    
    patterns = diagnosis.get("patterns", [])
    if patterns:
        md += "### 系统性问题\n"
        for p in patterns:
            severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(p.get("severity", ""), "⚪")
            md += f"- {severity_icon} **{p.get('pattern', '')}** (提到: {', '.join(p.get('mentioned_by', []))})\n"
            md += f"  {p.get('description', '')}\n"
        md += "\n"
    
    priorities = diagnosis.get("priorities", [])
    if priorities:
        md += "### 改进优先级\n"
        for p in priorities:
            md += f"**{p.get('priority', '?')}. {p.get('issue', '')}**\n"
            md += f"- 建议操作: {p.get('suggested_action', '')}\n"
            md += f"- 预期影响: {p.get('expected_impact', '')}\n\n"
    
    findings = diagnosis.get("key_findings", [])
    if findings:
        md += "### 核心发现\n"
        for f in findings:
            md += f"- {f}\n"
        md += "\n"
    
    summary = diagnosis.get("summary", "")
    if summary:
        md += f"### 总结\n{summary}\n"
    
    return md
