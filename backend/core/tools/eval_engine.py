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

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage

from core.llm import llm, get_chat_model
from core.llm_compat import normalize_content
from core.config import settings
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
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    
    start_time = time.time()
    llm_t = get_chat_model(temperature=temperature)  # 自动选择 provider 对应的默认模型
    response = await llm_t.ainvoke(messages)
    duration_ms = int((time.time() - start_time) * 1000)
    
    # 提取 token 用量（如可用）
    usage = getattr(response, "usage_metadata", {}) or {}
    
    output = normalize_content(response.content)
    
    call = LLMCall(
        step=step,
        input_system=system_prompt,
        input_user=user_message,
        output=output,
        tokens_in=usage.get("input_tokens", 0),
        tokens_out=usage.get("output_tokens", 0),
        cost=0.0,  # LangChain 不直接提供 cost
        duration_ms=duration_ms,
        timestamp=datetime.now().isoformat(),
    )
    
    return output, call


async def _call_llm_multi(
    messages: List[BaseMessage],
    step: str,
    temperature: float = 0.6,
) -> Tuple[str, LLMCall]:
    """多消息版本的 LLM 调用（用于多轮对话）"""
    start_time = time.time()
    llm_t = get_chat_model(temperature=temperature)  # 自动选择 provider 对应的默认模型
    response = await llm_t.ainvoke(messages)
    duration_ms = int((time.time() - start_time) * 1000)
    
    # 提取完整对话历史用于日志
    system_prompt = ""
    conversation_parts = []
    for m in messages:
        if isinstance(m, SystemMessage):
            system_prompt = normalize_content(m.content)
        elif isinstance(m, AIMessage):
            conversation_parts.append(f"[我方(assistant)]: {normalize_content(m.content)}")
        elif isinstance(m, HumanMessage):
            conversation_parts.append(f"[对方(user)]: {normalize_content(m.content)}")
    
    full_history = "\n---\n".join(conversation_parts) if conversation_parts else ""
    
    usage = getattr(response, "usage_metadata", {}) or {}
    
    output = normalize_content(response.content)
    
    call = LLMCall(
        step=step,
        input_system=system_prompt,
        input_user=full_history,
        output=output,
        tokens_in=usage.get("input_tokens", 0),
        tokens_out=usage.get("output_tokens", 0),
        cost=0.0,
        duration_ms=duration_ms,
        timestamp=datetime.now().isoformat(),
    )
    
    return output, call


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
    
    # ===== 兼容旧版 interaction_type → 新版 interaction_mode 映射 =====
    # reading → review（阅读式 = 一次性审查）
    # decision → scenario（决策式 = 场景对话）
    # exploration → exploration（探索式 = 自主探索路径）
    MODE_COMPAT = {
        "reading": "review",
        "decision": "scenario",
        "exploration": "exploration",
    }
    effective_mode = MODE_COMPAT.get(interaction_mode, interaction_mode)
    
    if effective_mode == "review":
        result = await _run_review(
            simulator_type, content, creator_profile, intent, persona, config, grader_cfg
        )
    elif effective_mode == "exploration":
        result = await _run_exploration(
            simulator_type, content, creator_profile, intent, persona, config, grader_cfg, content_field_names
        )
    elif effective_mode in ("dialogue", "scenario"):
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
    persona_text = json.dumps(persona, ensure_ascii=False) if persona else ""
    
    if custom_prompt:
        # 自定义模板：{content} 占位符指向 user_message，不在 system 里展开
        base_prompt = custom_prompt.replace("{content}", "（见下方待评估内容）").replace("{persona}", persona_text)
    else:
        base_prompt = type_info.get("system_prompt", "请评估以下内容。")
    
    # 注入上下文（角色背景放 system，内容放 user）
    system_prompt = base_prompt
    if creator_profile:
        system_prompt += f"\n\n【创作者特质】\n{creator_profile}"
    if intent:
        system_prompt += f"\n\n【项目意图】\n{intent}"
    if persona:
        system_prompt += f"\n\n【目标消费者】\n{persona_text}"
    
    # 获取评分维度
    dimensions = grader_cfg.get("dimensions", []) or type_info.get("default_dimensions", ["综合评价"])
    dim_str = ", ".join([f'"{d}": 分数(1-10)' for d in dimensions])
    dim_comment_str = ", ".join([f'"{d}": "具体评语（至少2句话）"' for d in dimensions])
    
    # user_message: 只在这里传内容（唯一一次）
    user_message = f"""【待评估内容】
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


async def _run_exploration(
    simulator_type: str,
    content: str,
    creator_profile: str,
    intent: str,
    persona: dict,
    config: dict,
    grader_cfg: dict,
    content_field_names: list = None,
) -> TrialResult:
    """
    探索模式：模拟消费者自主制定探索流程，在内容中寻找答案。
    
    流程：
    1. 消费者规划探索路径（根据自身痛点决定先看什么）
    2. 逐步执行探索，记录每一步的发现和感受
    3. 最终给出结构化评价
    """
    llm_calls = []
    
    persona = persona or {"name": "典型用户", "background": "对该领域感兴趣的读者"}
    user_name = persona.get("name", "消费者")
    persona_text = json.dumps(persona, ensure_ascii=False, indent=2)
    
    content_name = "内容"
    if content_field_names:
        content_name = f"《{content_field_names[0]}》" if len(content_field_names) == 1 else f"《{content_field_names[0]}》等{len(content_field_names)}篇"
    
    # 根据 persona 的痛点推导探索任务
    pain_points = persona.get("pain_points", [])
    task_hint = ""
    if pain_points:
        task_hint = f"你最想解决的问题：{'; '.join(pain_points[:3])}"
    else:
        task_hint = f"你想了解 {content_name} 是否对你有用"
    
    custom_prompt = config.get("system_prompt", "")
    
    # ===== 第一步：消费者制定探索计划 =====
    if custom_prompt:
        plan_system = custom_prompt.replace("{persona}", persona_text).replace("{content}", "（见下方）").replace("{task}", task_hint)
        if persona_text not in plan_system:
            plan_system += f"\n\n【你扮演的角色】\n{persona_text}"
    else:
        plan_system = f"""你正在扮演一位真实用户。

【你的角色】
{persona_text}

【背景】
你面前有一份内容（{content_name}），你需要根据自己的背景和需求来探索它。
{task_hint}

【行为要求】
1. 像真实用户一样思考：你会先看哪个部分？为什么？
2. 每一步探索都要记录你的真实感受
3. 如果发现内容有缺失或不清楚的地方，要指出来
4. 最终判断这个内容是否对你有帮助"""

    if creator_profile:
        plan_system += f"\n\n【创作者特质】\n{creator_profile}"
    if intent:
        plan_system += f"\n\n【项目意图】\n{intent}"
    
    type_info = SIMULATOR_TYPES.get(simulator_type, {})
    dimensions = grader_cfg.get("dimensions", []) or type_info.get("default_dimensions", ["找到答案效率", "信息完整性", "满意度"])
    dim_str = ", ".join([f'"{d}": 分数(1-10)' for d in dimensions])
    dim_comment_str = ", ".join([f'"{d}": "具体评语（至少2句话）"' for d in dimensions])
    
    plan_user = f"""以下是你要探索的内容：

=== 内容开始 ===
{content}
=== 内容结束 ===

请以你的角色身份，模拟你的完整探索过程。

**输出JSON格式**（严格遵循，不要输出其他内容）：
{{
    "exploration_plan": "你打算怎么浏览这个内容（1-2句话）",
    "exploration_steps": [
        {{
            "step": 1,
            "action": "先看了什么部分",
            "reason": "为什么先看这个",
            "finding": "发现了什么",
            "feeling": "感受如何（有用/困惑/惊喜/失望等）"
        }},
        {{
            "step": 2,
            "action": "接着看了什么",
            "reason": "为什么",
            "finding": "发现了什么",
            "feeling": "感受"
        }}
    ],
    "attention_points": ["特别吸引注意力的内容1", "内容2"],
    "found_answer": true,
    "answer_quality": "找到的答案质量如何（详细/部分/不够用）",
    "difficulties": ["遇到的困难1", "困难2"],
    "missing_info": ["希望内容中包含但没有的信息1", "信息2"],
    "scores": {{{dim_str}}},
    "comments": {{{dim_comment_str}}},
    "would_recommend": true,
    "summary": "作为{user_name}，总体评价这个内容对我的帮助程度（100-200字）"
}}"""

    try:
        response_text, call = await _call_llm(
            plan_system, plan_user,
            step=f"explorer_{simulator_type}_exploration",
            temperature=0.7,
        )
        llm_calls.append(call)
        
        result_data = _parse_json_response(response_text)
        
        # 构建 exploration nodes（可视化探索过程）
        exploration_nodes = []
        
        # 探索计划
        plan = result_data.get("exploration_plan", "")
        if plan:
            exploration_nodes.append({
                "role": "consumer", "content": f"📋 探索计划：{plan}", "turn": 0,
            })
        
        # 每一步探索
        for step_data in result_data.get("exploration_steps", []):
            step_num = step_data.get("step", "?")
            action = step_data.get("action", "")
            reason = step_data.get("reason", "")
            finding = step_data.get("finding", "")
            feeling = step_data.get("feeling", "")
            
            step_content = f"🔍 步骤 {step_num}：{action}"
            if reason:
                step_content += f"\n💭 原因：{reason}"
            if finding:
                step_content += f"\n📝 发现：{finding}"
            if feeling:
                step_content += f"\n😊 感受：{feeling}"
            
            exploration_nodes.append({
                "role": "consumer", "content": step_content, "turn": step_num,
            })
        
        # 注意力焦点
        attention = result_data.get("attention_points", [])
        if attention:
            exploration_nodes.append({
                "role": "system", "content": "⭐ 特别关注的内容：\n" + "\n".join(f"• {a}" for a in attention),
            })
        
        # 困难与缺失
        difficulties = result_data.get("difficulties", [])
        missing = result_data.get("missing_info", [])
        if difficulties or missing:
            gap_text = ""
            if difficulties:
                gap_text += "❌ 遇到的困难：\n" + "\n".join(f"• {d}" for d in difficulties)
            if missing:
                gap_text += "\n⚠️ 缺失的信息：\n" + "\n".join(f"• {m}" for m in missing)
            exploration_nodes.append({
                "role": "system", "content": gap_text.strip(),
            })
        
        # 最终评价
        found = result_data.get("found_answer", False)
        quality = result_data.get("answer_quality", "")
        summary = result_data.get("summary", "")
        exploration_nodes.append({
            "role": "consumer",
            "content": f"{'✅' if found else '❌'} 是否找到答案：{'是' if found else '否'}"
                       + (f"\n📊 答案质量：{quality}" if quality else "")
                       + (f"\n\n{summary}" if summary else ""),
        })
        
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
            interaction_mode="exploration",
            nodes=exploration_nodes,
            result={
                "scores": scores,
                "comments": result_data.get("comments", {}),
                "exploration_plan": plan,
                "exploration_steps": result_data.get("exploration_steps", []),
                "attention_points": attention,
                "found_answer": found,
                "answer_quality": quality,
                "difficulties": difficulties,
                "missing_info": missing,
                "strengths": attention,
                "weaknesses": difficulties + missing,
                "suggestions": missing,
                "outcome": "found_answer" if found else "not_found",
                "would_recommend": result_data.get("would_recommend", False),
                "summary": summary,
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
            role=simulator_type, interaction_mode="exploration",
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
    
    # 根据 simulator_type 或 interaction_type 确定对话方向
    # decision 类型模拟器 = 销售方主动 → prompt_template 是卖方提示词
    # 必须路由到 _run_seller_dialogue，否则角色会倒置
    interaction_type = config.get("interaction_type", "")
    if simulator_type == "seller" or interaction_type == "decision":
        # 销售/决策模式：内容代表主动，消费者回应
        return await _run_seller_dialogue(
            content, persona, config, grader_cfg, llm_calls, content_field_names
        )
    
    # 用户自定义的 simulator 提示词（来自后台配置）
    custom_sim_prompt = config.get("system_prompt", "")
    sim_name = config.get("simulator_name", simulator_type)
    
    # ===== 消费者/第一方提示词 =====
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
5. 如果觉得已经了解足够了，说"好的，我了解了"结束对话
6. 每次发言不超过50字"""

    # ===== 内容代表/第二方提示词 =====
    custom_secondary = config.get("secondary_prompt", "")
    if custom_secondary:
        # 用后台配置的提示词，替换占位符
        content_system = custom_secondary.replace("{content}", content).replace("{persona}", persona_text)
        # ===== 防御性检查：如果模板中没有 {content} 占位符，内容未被注入 =====
        # 这是最关键的修复：确保内容代表一定能看到项目内容
        if "{content}" not in custom_secondary and content and content.strip():
            content_system += f"\n\n=== 你必须严格基于以下内容回答 ===\n{content}\n=== 内容结束 ==="
    else:
        content_system = f"""你是{content_name}的内容代表，严格基于以下内容回答问题。

=== 内容开始 ===
{content}
=== 内容结束 ===

【回答规则】
1. 严格基于内容回答，不要编造
2. 如果内容中没有涉及，必须明确回复“内容未覆盖”，禁止臆测
3. 尽量引用内容中的原话或核心观点
4. 每次回复推进一个决策节点（需求/异议/价值映射/决定）
5. 回复简洁，不超过50字"""

    try:
        for turn in range(max_turns):
            # 消费者提问
            user_messages = [SystemMessage(content=consumer_system)]
            for log in interaction_log:
                if log["role"] == "consumer":
                    user_messages.append(AIMessage(content=log["content"]))
                else:
                    user_messages.append(HumanMessage(content=log["content"]))
            
            prompt = "请基于你的背景，提出你最想解决的第一个问题。" if turn == 0 else "请基于之前的对话，继续你的咨询。"
            user_messages.append(HumanMessage(content=prompt))
            
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
            content_messages = [SystemMessage(content=content_system)]
            for log in interaction_log:
                if log["role"] == "consumer":
                    content_messages.append(HumanMessage(content=log["content"]))
                else:
                    content_messages.append(AIMessage(content=log["content"]))
            
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
        # 防御性检查：销售方必须知道内容
        if "{content}" not in custom_primary and content and content.strip():
            seller_system += f"\n\n=== 你掌握的内容（必须基于此销售）===\n{content}\n=== 内容结束 ==="
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

【行为要求】- 主动引导对话 - 引用具体信息 - 诚实但有说服力 - 每次发言不超过50字

【强约束】
1) 仅可使用给定内容进行价值陈述，若内容没有依据，不得补充“外部事实”。
2) 每轮必须推进一个决策节点：需求确认/异议澄清/价值映射/促成决定。"""

    # 消费者方提示词：优先用后台配置的 secondary_prompt
    custom_secondary = config.get("secondary_prompt", "")
    if custom_secondary:
        consumer_system = custom_secondary.replace("{persona}", persona_text).replace("{content}", content)
    else:
        consumer_system = f"""你是一位真实的潜在用户。有人正在向你推介内容/产品。

【你的身份】
{persona_text}

【你的态度】- 有真实需求，但不轻易被说服 - 会提出真实质疑 - 如果确实有价值，愿意接受 - 不适合就明确拒绝

【行为要求】基于真实背景回应，适当质疑，最后做出明确决定。每次发言不超过50字。"""

    try:
        for turn in range(max_turns):
            # 销售发言
            seller_messages = [SystemMessage(content=seller_system)]
            for log in interaction_log:
                if log["role"] == "seller":
                    seller_messages.append(AIMessage(content=log["content"]))
                else:
                    seller_messages.append(HumanMessage(content=log["content"]))
            seller_messages.append(HumanMessage(content="请开始你的销售开场白。" if turn == 0 else "请继续。"))
            
            seller_text, seller_call = await _call_llm_multi(
                seller_messages, step=f"seller_turn_{turn+1}", temperature=0.7
            )
            llm_calls.append(seller_call)
            interaction_log.append({"role": "seller", "name": "销售顾问", "content": seller_text, "turn": turn + 1, "phase": _get_sales_phase(turn)})
            
            # 消费者回应
            consumer_messages = [SystemMessage(content=consumer_system)]
            for log in interaction_log:
                if log["role"] == "consumer":
                    consumer_messages.append(AIMessage(content=log["content"]))
                else:
                    consumer_messages.append(HumanMessage(content=log["content"]))
            
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
            "你是一位销售效果评估专家。请分析以下销售对话的效果。先列证据，再给分。",
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

async def run_individual_grader(
    grader_name: str,
    grader_type: str,
    prompt_template: str,
    dimensions: list,
    content: str,
    trial_result_data: dict,
    process_transcript: str = "",
) -> Tuple[dict, Optional[LLMCall]]:
    """
    运行单个 Grader。
    
    核心原则：prompt_template 就是发送给 LLM 的完整 system_prompt。
    引擎只负责替换占位符 {content} / {process}，不额外拼接任何内容。
    用户在后台看到的提示词 = LLM 实际收到的提示词。
    
    Args:
        grader_name: 评分器名称
        grader_type: "content_only" / "content_and_process"
        prompt_template: 完整的评分提示词，支持 {content} 和 {process} 占位符
        dimensions: 评分维度列表（用于解析结果）
        content: 被评估的内容
        trial_result_data: 试验结果（备用，模板中无引用则不使用）
        process_transcript: 互动过程记录
    
    Returns:
        (grader_output_dict, LLMCall_or_None)
    """
    dims = dimensions or ["综合评价"]
    
    # ===== 核心：模板就是最终提示词，只做占位符替换 =====
    raw_template = prompt_template or ""
    
    if raw_template:
        # 直接替换占位符
        system_prompt = raw_template
        # 评估报告需要可追溯完整输入，禁止在此处截断内容。
        system_prompt = system_prompt.replace("{content}", content if content else "（无内容）")
        
        # {process}: content_and_process 类型才填充，否则标注无
        if grader_type == "content_and_process" and process_transcript:
            system_prompt = system_prompt.replace("{process}", process_transcript)
        else:
            system_prompt = system_prompt.replace("{process}", "（无互动过程）")
    else:
        # 无模板时的兜底（不应发生，预置评分器都有模板）
        dim_score_str = ", ".join([f'"{d}": 分数(1-10)' for d in dims])
        dim_comment_str = ", ".join([f'"{d}": "评语"' for d in dims])
        
        process_section = ""
        if grader_type == "content_and_process" and process_transcript:
            process_section = f"\n\n【互动过程记录】\n{process_transcript}"
        
        system_prompt = f"""你是「{grader_name}」，请对以下内容进行客观、严谨的评分。

【被评估内容】
{content if content else '（无内容）'}{process_section}

【评估维度】
{chr(10).join([f'{i+1}. {d} (1-10)' for i, d in enumerate(dims)])}

请严格输出以下 JSON 格式，不要输出其他内容：
{{"scores": {{{dim_score_str}}}, "comments": {{{dim_comment_str}}}, "feedback": "整体评价和改进建议（100-200字）"}}"""

    # user_message: 简单指令即可，所有信息已在 system_prompt 中
    user_message = (
        "请根据上述要求进行评分，严格按照指定的 JSON 格式输出。"
        "先给出每个维度的证据再评分，无证据不得给高分。"
        "其中 feedback 只保留需要修改的要点和可执行改法，不要写正面表扬；"
        "feedback 按独立建议句输出，每句只表达一个改动点。"
    )

    try:
        text, call = await _call_llm(
            system_prompt, user_message,
            step=f"grader_{grader_name}",
            temperature=0.4,
        )
        result = _parse_json_response(text)
        
        scores = result.get("scores", {})
        valid_scores = [v for v in scores.values() if isinstance(v, (int, float))]
        overall = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0
        
        return {
            "grader_name": grader_name,
            "grader_type": grader_type,
            "overall": overall,
            "scores": scores,
            "comments": result.get("comments", {}),
            "feedback": result.get("feedback", result.get("analysis", "")),
        }, call
    except Exception as e:
        return {
            "grader_name": grader_name,
            "grader_type": grader_type,
            "overall": None,
            "scores": {},
            "feedback": f"评分失败: {str(e)}",
            "error": str(e),
        }, None


async def _run_content_grader(
    content: str,
    trial_result_data: dict,
    dimensions: list,
    grader_cfg: dict,
) -> Tuple[dict, Optional[LLMCall]]:
    """
    内容评分器 - 直接评价内容本身的质量（兼容旧逻辑）
    """
    custom_prompt = grader_cfg.get("custom_prompt", "")
    grader_type = grader_cfg.get("type", "content")
    
    if grader_type not in ("content", "combined"):
        return {}, None
    
    # 转为新的 run_individual_grader
    return await run_individual_grader(
        grader_name="内容质量评分",
        grader_type="content_only",
        prompt_template=custom_prompt,
        dimensions=dimensions or ["综合评价"],
        content=content,
        trial_result_data=trial_result_data,
    )


async def _run_process_grader(
    dialogue_transcript: str,
    dimensions: list,
    grader_cfg: dict,
) -> Tuple[dict, Optional[LLMCall]]:
    """
    过程评分器 - 评价互动过程的质量（兼容旧逻辑）
    """
    grader_type = grader_cfg.get("type", "content")
    
    if grader_type not in ("process", "combined"):
        return {}, None
    
    return await run_individual_grader(
        grader_name="互动过程评分",
        grader_type="content_and_process",
        prompt_template="",
        dimensions=["对话流畅性", "问题解决效率", "信息传递有效性", "用户体验"],
        content="",
        trial_result_data={},
        process_transcript=dialogue_transcript,
    )


# ============== Diagnoser ==============

async def run_diagnoser(
    trial_results: List[TrialResult],
    content_summary: str = "",
    intent: str = "",
) -> Tuple[dict, Optional[LLMCall]]:
    """
    跨 Trial 综合诊断 - 不给分数，只做定性分析：
    评估了哪些内容块、用了什么方法、好在哪、哪里需要提升。
    
    Returns:
        (diagnosis_dict, LLMCall_or_None)
    """
    if not trial_results:
        return {"summary": "无可分析的Trial结果", "content_blocks_evaluated": [], "improvements": []}, None
    
    trials_summary = []
    for tr in trial_results:
        if not tr.success:
            continue
        display_name = tr.role_display_name or SIMULATOR_TYPES.get(tr.role, {}).get("name", tr.role)
        mode_label = {"review": "审查模式", "dialogue": "对话模式", "scenario": "情景模式"}.get(tr.interaction_mode, tr.interaction_mode)
        summary_text = f"""### {display_name}（{mode_label}）
- 结果: {tr.result.get('outcome', 'N/A')}
- 总结: {tr.result.get('summary', 'N/A')}
- 优点: {', '.join(tr.result.get('strengths', []))}
- 问题: {', '.join(tr.result.get('weaknesses', []))}
- 建议: {', '.join(tr.result.get('suggestions', []))}"""
        trials_summary.append(summary_text)
    
    trials_text = "\n\n---\n\n".join(trials_summary)
    
    system_prompt = """你是一位内容评估诊断专家。请基于多个试验的定性反馈，写一份简洁扼要的综合诊断报告。

**重要：不要给出任何分数。** 只做定性分析。

报告结构：
1. 总览：一共评估了多少个内容块，每个用的什么评估方法（审查/对话/情景）
2. 亮点：内容做得好的地方（跨试验共识）
3. 待提升：需要改进的关键问题（按优先级排序）
4. 建议：最值得先行动的 2-3 条改进建议

请输出严格的JSON格式，语言简洁直接。"""

    user_message = f"""# 项目意图
{intent or '未提供'}

# 各试验评估反馈（共 {len(trial_results)} 个试验）

{trials_text}

请输出JSON格式：
{{
    "overview": "总览：评估了X个内容块，分别使用了...",
    "strengths": ["亮点1", "亮点2", "亮点3"],
    "improvements": [
        {{"issue": "问题", "priority": "high/medium/low", "suggested_action": "建议"}}
    ],
    "action_items": ["最优先的行动建议1", "行动建议2"],
    "summary": "综合诊断总结（100-200字，不含分数）"
}}"""

    try:
        text, call = await _call_llm(system_prompt, user_message, step="diagnoser", temperature=0.5)
        result = _parse_json_response(text)
        return result, call
    except Exception as e:
        return {
            "summary": f"诊断失败: {str(e)}",
            "strengths": [], "improvements": [], "action_items": [], "error": str(e),
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
    """安全解析 AI 返回的 JSON（容错：处理 LLM 输出多余的括号、前后缀文本等）"""
    text = text.strip()
    
    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 2. raw_decode：处理 JSON 后面有多余字符（如多余的 } 或解释文本）
    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass
    
    # 3. 提取 Markdown 代码块中的 JSON
    import re
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        inner = json_match.group(1).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            pass
        # 代码块内也可能有多余字符
        try:
            obj, _ = json.JSONDecoder().raw_decode(inner)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass
    
    # 4. 提取第一个 { 到最后一个 } 之间的内容
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        snippet = text[start:end+1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            pass
        # snippet 内部可能也有多余尾部
        try:
            obj, _ = json.JSONDecoder().raw_decode(snippet)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
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
    """将诊断结果格式化为 Markdown（定性分析，无分数）"""
    md = "## 🔍 综合诊断\n\n"
    
    overview = diagnosis.get("overview", "")
    if overview:
        md += f"{overview}\n\n"
    
    strengths = diagnosis.get("strengths", [])
    if strengths:
        md += "### ✅ 亮点\n"
        for s in strengths:
            md += f"- {s}\n"
        md += "\n"
    
    improvements = diagnosis.get("improvements", [])
    if improvements:
        md += "### ⚠️ 待提升\n"
        for imp in improvements:
            if isinstance(imp, dict):
                severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(imp.get("priority", ""), "⚪")
                md += f"- {severity_icon} **{imp.get('issue', '')}**\n"
                if imp.get("suggested_action"):
                    md += f"  → {imp['suggested_action']}\n"
            else:
                md += f"- {imp}\n"
        md += "\n"
    
    action_items = diagnosis.get("action_items", [])
    if action_items:
        md += "### 🎯 优先行动\n"
        for i, a in enumerate(action_items, 1):
            md += f"{i}. {a}\n"
        md += "\n"
    
    summary = diagnosis.get("summary", "")
    if summary:
        md += f"### 总结\n{summary}\n"
    
    return md
