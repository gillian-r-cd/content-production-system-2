# backend/core/orchestrator.py
# 功能: LangGraph Agent核心编排器
# 主要类: ContentProductionAgent
# 主要函数: create_graph(), run(), stream()
# 数据结构: ContentProductionState

"""
LangGraph Agent 核心编排器

实现真正的Agent架构（非if/else），使用LangGraph状态图实现：
1. 意图路由器 - 判断用户意图并路由到相应节点
2. 阶段节点 - 各个内容生产阶段
3. 工具节点 - 调研、生成、模拟、评估
4. 检查点 - Agent自主权控制
"""

from typing import TypedDict, Literal, Optional, Any, Annotated, List, Dict, Tuple
from dataclasses import dataclass, field
import operator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from core.ai_client import ai_client, ChatMessage
from core.prompt_engine import prompt_engine, GoldenContext, PromptContext
from core.models import PROJECT_PHASES


# ============== 状态定义 ==============

class ContentProductionState(TypedDict):
    """
    内容生产状态
    
    在整个Agent执行过程中传递和更新
    """
    # 项目标识
    project_id: str
    
    # 当前阶段
    current_phase: str
    
    # 阶段顺序（可调整）
    phase_order: List[str]
    
    # 每阶段状态
    phase_status: Dict[str, str]
    
    # Agent自主权设置
    autonomy_settings: Dict[str, bool]
    
    # Golden Context
    golden_context: Dict
    
    # 已生成的字段 {field_id: content}
    fields: Dict[str, str]
    
    # 对话历史（用于右栏Agent对话）
    messages: Annotated[List[BaseMessage], operator.add]
    
    # 当前用户输入
    user_input: str
    
    # Agent输出（流式输出用）
    agent_output: str
    
    # 是否等待人工确认
    waiting_for_human: bool
    
    # 路由目标
    route_target: str
    
    # 是否使用DeepResearch
    use_deep_research: bool
    
    # 是否是产出模式（用于判断是否保存为字段）
    is_producing: bool
    
    # 错误信息
    error: Optional[str]
    
    # API 调用统计（用于日志记录）
    tokens_in: int
    tokens_out: int
    duration_ms: int
    cost: float
    
    # 完整的 prompt（用于日志记录，包含系统提示词）
    full_prompt: str


# ============== 意图路由 ==============

ROUTE_OPTIONS = Literal[
    "advance_phase",  # 推进到下一阶段
    "generate",       # 生成内容
    "modify",         # 修改内容
    "research",       # 调研
    "simulate",       # 模拟
    "evaluate",       # 评估
    "query",          # 查询
    "chat",           # 自由对话
]


async def route_intent(state: ContentProductionState) -> ContentProductionState:
    """
    意图路由器
    
    分析用户输入，判断意图类型并路由
    
    关键逻辑：
    - 意图分析阶段未完成时，所有输入都路由到 intent_analysis_node
    - 意图分析完成后，检查是否要进入下一阶段
    """
    user_input = state.get("user_input", "")
    current_phase = state.get("current_phase", "intent")
    phase_status = state.get("phase_status", {})
    
    # ===== 核心路由逻辑 =====
    # 规则1：当前阶段未完成 → 路由到当前阶段节点（执行阶段任务）
    # 规则2：当前阶段已完成 → 允许对话或推进下一阶段
    
    current_phase_status = phase_status.get(current_phase, "pending")
    
    # 检查是否是开始当前阶段的触发词
    start_triggers = ["开始", "开始吧", "start", "go", "执行", "生成"]
    is_start_trigger = any(t in user_input.lower() for t in start_triggers)
    
    # 如果当前阶段未完成（pending 或 in_progress）
    if current_phase_status != "completed":
        # 用户输入开始触发词，或者当前阶段是意图分析（需要问答）
        if is_start_trigger or current_phase == "intent":
            return {**state, "route_target": "phase_current"}
        # 其他情况也路由到当前阶段（让阶段节点决定如何处理）
        return {**state, "route_target": "phase_current"}
    
    # 当前阶段已完成，检查是否要推进
    advance_triggers = ["继续", "下一步", "进入下一阶段", "确认", "好的", "可以"]
    if any(t in user_input for t in advance_triggers):
        return {**state, "route_target": "advance_phase"}
    
    # 已完成但用户想做其他操作 → 使用LLM判断意图
    # ===== LLM意图分类（仅用于已完成阶段的自由对话） =====
    messages = [
        ChatMessage(
            role="system",
            content=f"""你是一个意图分类器。根据用户输入和当前阶段，判断用户的意图。

当前阶段: {current_phase}

意图类型:
- advance_phase: 用户想推进到下一阶段（如"继续"、"下一步"）
- generate: 用户想生成内容（如"生成xxx"、"写xxx"）
- modify: 用户想修改已有内容（如"修改xxx"、"调整xxx"）
- research: 用户想进行调研（如"调研xxx"、"分析用户"）
- simulate: 用户想模拟测试（如"模拟一下"、"测试效果"）
- evaluate: 用户想评估内容（如"评估一下"、"打分"）
- query: 用户想查询信息（如"看看xxx"、"@xxx"）
- chat: 其他自由对话或回答问题

只输出一个词，不要解释："""
        ),
        ChatMessage(role="user", content=user_input),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.3)
    intent = response.content.strip().lower()
    
    # 标准化意图
    valid_intents = ["advance_phase", "generate", "modify", "research", 
                     "simulate", "evaluate", "query", "chat"]
    if intent not in valid_intents:
        intent = "chat"
    
    return {**state, "route_target": intent}


# ============== 阶段节点 ==============

async def intent_analysis_node(state: ContentProductionState) -> ContentProductionState:
    """
    意图分析节点
    
    严格流程：
    1. 问题1（固定）：做什么项目
    2. 问题2（AI生成）：根据用户回答的个性化跟进
    3. 问题3（AI生成）：根据用户回答的个性化跟进
    4. 问完严格3个问题后，才生成意图分析
    
    关键：只统计【最近一轮】的问题，遇到意图分析结果就重置
    """
    gc = state.get("golden_context", {})
    user_input = state.get("user_input", "")
    chat_history = state.get("messages", [])
    
    MAX_QUESTIONS = 3
    
    # ===== 关键：只统计【当前轮次】的问题 =====
    # 停止条件：遇到意图分析结果、确认消息、或非问题的AI消息
    question_count = 0
    found_questions = []  # 记录找到的问题编号
    
    for m in reversed(chat_history):
        if isinstance(m, AIMessage):
            content = m.content if hasattr(m, 'content') else str(m)
            
            # 停止条件1：确认消息（上一轮已完成）
            if "✅ 已生成" in content or "已生成【意图分析】" in content:
                break
            
            # 停止条件2：意图分析JSON结果
            if ('"做什么"' in content and '"给谁看"' in content) or \
               ("做什么" in content and "给谁看" in content and "期望行动" in content and "【问题" not in content):
                break
            
            # 统计问题消息
            if "【问题" in content and "/3】" in content:
                # 提取问题编号
                import re
                match = re.search(r'【问题\s*(\d)/3】', content)
                if match:
                    q_num = int(match.group(1))
                    if q_num not in found_questions:
                        found_questions.append(q_num)
                        question_count += 1
    
    # 本次应该问第几个问题
    next_question_num = question_count + 1
    
    # ===== 判断是否进入产出模式 =====
    # 条件：已经问完3个问题
    all_questions_done = question_count >= MAX_QUESTIONS
    is_producing = all_questions_done
    
    # 构建对话历史上下文（只保留最后一轮有效对话）
    # 找到最后一个"开始"或"问题 1/3"的位置，只使用那之后的历史
    last_start_idx = 0
    for idx, msg in enumerate(chat_history):
        content = msg.content if hasattr(msg, 'content') else str(msg)
        if isinstance(msg, HumanMessage) and content.strip() in ["开始", "开始吧", "start", "Start"]:
            last_start_idx = idx
        elif isinstance(msg, AIMessage) and "【问题 1/3】" in content:
            last_start_idx = idx
    
    # 只使用最后一轮对话（从最后一个起点开始）
    relevant_history = chat_history[last_start_idx:]
    
    # 去重：过滤掉重复的问答
    seen_contents = set()
    deduped_history = []
    for msg in relevant_history:
        content = msg.content if hasattr(msg, 'content') else str(msg)
        # 跳过单纯的"开始"
        if isinstance(msg, HumanMessage) and content.strip() in ["开始", "开始吧", "start", "Start"]:
            continue
        # 去重
        if content not in seen_contents:
            seen_contents.add(content)
            deduped_history.append(msg)
    
    history_context = ""
    for msg in deduped_history[-10:]:
        if isinstance(msg, HumanMessage):
            history_context += f"用户: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            history_context += f"助手: {msg.content}\n"
    
    new_phase_status = {**state.get("phase_status", {})}
    
    if is_producing:
        # ===== 产出模式：生成意图分析 =====
        system_prompt = prompt_engine.INTENT_PRODUCING_PROMPT
        user_prompt = f"""项目背景:
{gc.get('creator_profile', '')}

完整对话历史:
{history_context}

用户最新输入: {user_input}

请根据以上3个问题的回答，生成结构化的意图分析。"""
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        
        response = await ai_client.async_chat(messages, temperature=0.7)
        new_phase_status["intent"] = "completed"
        
        # 构建完整的 prompt 用于日志记录
        full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{user_prompt}"
        
        # ===== 关键：更新 Golden Context =====
        # 将意图分析结果写入 golden_context，供后续阶段使用
        new_gc = {
            **gc,
            "intent": response.content,  # 意图分析结果
        }
        
        # 构建简洁的确认消息（实际内容保存到字段）
        confirm_message = "✅ 已生成【意图分析】，请在左侧工作台查看。输入「继续」进入消费者调研阶段。"
        
        return {
            **state,
            "agent_output": response.content,  # 完整内容用于保存字段
            "display_output": confirm_message,  # 对话区显示简洁确认
            "messages": [AIMessage(content=confirm_message)],
            "phase_status": new_phase_status,
            "golden_context": new_gc,  # 更新 golden_context
            "is_producing": True,
            "waiting_for_human": True,  # 关键：等待用户确认，不自动推进
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "duration_ms": response.duration_ms,
            "cost": response.cost,
            "full_prompt": full_prompt,  # 完整 prompt 用于日志
        }
    
    # ===== 提问模式 =====
    new_phase_status["intent"] = "in_progress"
    
    if next_question_num == 1:
        # 第一个问题：固定内容，不调用AI
        question_text = "【问题 1/3】你这次想做什么内容？请简单描述一下（比如：一篇文章、一个视频脚本、一份产品介绍、一套培训课件等），并补充一句说明它的大致主题或方向。"
        
        return {
            **state,
            "agent_output": question_text,
            "messages": [AIMessage(content=question_text)],
            "phase_status": new_phase_status,
            "is_producing": False,
            "tokens_in": 0,
            "tokens_out": 0,
            "duration_ms": 0,
            "cost": 0.0,
            "full_prompt": "[固定问题，无AI调用]",
        }
    
    elif next_question_num == 2:
        # 第二个问题：基于用户第一个回答，AI生成个性化问题
        system_prompt = f"""你是内容策略顾问。用户刚刚描述了他想做的内容项目。

你现在要问第2个问题，了解目标受众。

对话历史:
{history_context}
用户最新回答: {user_input}

请输出一个针对性的问题，格式必须是：
【问题 2/3】（问题内容）

问题应该关于：这个内容主要给谁看？目标读者是谁？他们有什么痛点？

只输出问题，不要有其他内容。"""
        
        messages = [ChatMessage(role="system", content=system_prompt)]
        
        response = await ai_client.async_chat(messages, temperature=0.7)
        output = response.content
        
        # 确保格式正确
        if "【问题 2/3】" not in output:
            output = f"【问题 2/3】{output}"
        
        return {
            **state,
            "agent_output": output,
            "messages": [AIMessage(content=output)],
            "phase_status": new_phase_status,
            "is_producing": False,
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "duration_ms": response.duration_ms,
            "cost": response.cost,
            "full_prompt": f"[System]\n{system_prompt}",
        }
    
    else:  # next_question_num == 3
        # 第三个问题：基于前两个回答，AI生成个性化问题
        system_prompt = f"""你是内容策略顾问。用户已经描述了内容项目和目标受众。

你现在要问第3个也是最后一个问题，了解期望的用户行动。

对话历史:
{history_context}
用户最新回答: {user_input}

请输出一个针对性的问题，格式必须是：
【问题 3/3】（问题内容）

问题应该关于：看完这个内容后，你最希望读者采取什么具体行动？

只输出问题，不要有其他内容。"""
        
        messages = [ChatMessage(role="system", content=system_prompt)]
        
        response = await ai_client.async_chat(messages, temperature=0.7)
        output = response.content
        
        # 确保格式正确
        if "【问题 3/3】" not in output:
            output = f"【问题 3/3】{output}"
        
        return {
            **state,
            "agent_output": output,
            "messages": [AIMessage(content=output)],
            "phase_status": new_phase_status,
            "is_producing": False,
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "duration_ms": response.duration_ms,
            "cost": response.cost,
            "full_prompt": f"[System]\n{system_prompt}",
        }


async def research_node(state: ContentProductionState) -> ContentProductionState:
    """
    消费者调研节点
    
    根据设置使用DeepResearch或快速生成
    """
    from core.tools import deep_research, quick_research
    
    gc = state.get("golden_context", {})
    use_deep = state.get("use_deep_research", True)
    
    query = "消费者调研"
    intent = gc.get("intent", state.get("user_input", ""))
    
    import json
    import uuid
    
    try:
        if use_deep:
            report = await deep_research(query, intent)
        else:
            report = await quick_research(query, intent)
        
        # 为每个 persona 生成唯一ID
        personas_data = []
        for i, persona in enumerate(report.personas):
            persona_dict = {
                "id": f"persona_{i+1}_{uuid.uuid4().hex[:8]}",
                "name": persona.name,
                "basic_info": persona.basic_info if hasattr(persona, 'basic_info') and persona.basic_info else {
                    "age_range": "25-45岁",
                    "industry": "未知",
                    "position": "未知",
                },
                "background": persona.background,
                "pain_points": persona.pain_points,
                "selected": True,  # 默认选中
            }
            personas_data.append(persona_dict)
        
        # 构建结构化的调研报告（JSON格式，便于前端解析）
        report_json = {
            "summary": report.summary,
            "consumer_profile": report.consumer_profile,
            "pain_points": report.pain_points,
            "value_propositions": report.value_propositions,
            "personas": personas_data,
            "sources": report.sources if hasattr(report, 'sources') else [],
        }
        
        # JSON格式存储（给中间栏字段用）
        report_content = json.dumps(report_json, ensure_ascii=False, indent=2)
        
        # 简洁展示文本（给右侧对话区）
        display_text = f"✅ 已生成消费者调研报告，请在左侧工作台查看。\n\n"
        display_text += f"**总体概述**: {report.summary[:100]}...\n\n"
        display_text += f"**典型用户**: {', '.join([p['name'] for p in personas_data[:3]])}"
        
        # 更新Golden Context（保存结构化数据）
        new_gc = {
            **gc,
            "consumer_personas": report_content,  # JSON格式
        }
        
        # 构建 full_prompt 用于日志 - 记录完整上下文
        full_prompt = f"""[消费者调研 - 完整上下文]

=== 1. 调研参数 ===
查询主题: {query}
使用深度调研: {use_deep}

=== 2. 创作者特质 ===
{gc.get('creator_profile', '未设置')}

=== 3. 项目意图 (完整) ===
{intent if intent else '未设置'}

=== 4. DeepResearch 流程 ===
步骤1: 规划搜索查询 (LLM生成3-5个搜索词)
步骤2: DuckDuckGo 搜索 (每个查询5条结果)
步骤3: Jina Reader 读取网页内容
步骤4: 综合分析生成报告

=== 5. 综合分析提示词 ===
[System]
你是一个资深的用户研究专家。请基于搜索结果，生成一份详细的消费者调研报告。

输出JSON格式，包含以下字段：
- summary: 总体概述（200字以内）
- consumer_profile: 消费者画像对象 {{age_range, occupation, characteristics, behaviors}}
- pain_points: 核心痛点列表（3-5个）
- value_propositions: 价值主张列表（3-5个）
- personas: 3个典型用户小传，每个包含 {{name, background, story, pain_points}}

[User]
# 调研主题
{query}

# 项目意图
{intent if intent else '未设置'}

# 搜索结果
[... 实际搜索结果内容（最多15000字符）...]

=== 6. 生成结果 ===
报告已生成，包含 {len(personas_data)} 个用户画像
来源: {len(report.sources) if hasattr(report, 'sources') else 0} 个网页
搜索查询: {report.search_queries if hasattr(report, 'search_queries') else '未记录'}
内容长度: {report.content_length if hasattr(report, 'content_length') else '未记录'} 字符"""
        
        # 确认消息
        confirm_text = "✅ 已生成【消费者调研报告】，请在左侧工作台查看。输入「继续」进入内涵设计阶段。"
        
        return {
            **state,
            "agent_output": report_content,  # JSON格式，保存到字段
            "display_output": confirm_text,   # 对话区显示确认消息
            "full_prompt": full_prompt,
            "messages": [AIMessage(content=confirm_text)],
            "golden_context": new_gc,
            "phase_status": {**state.get("phase_status", {}), "research": "completed"},
            "current_phase": "research",
            "is_producing": True,  # 调研结果应保存到工作台
            "waiting_for_human": True,  # 关键：等待用户确认，不自动推进
            # token 信息
            "tokens_in": getattr(report, 'tokens_in', 0),
            "tokens_out": getattr(report, 'tokens_out', 0),
            "duration_ms": getattr(report, 'duration_ms', 0),
            "cost": getattr(report, 'cost', 0.0),
        }
        
    except Exception as e:
        return {
            **state,
            "error": str(e),
            "agent_output": f"调研失败: {str(e)}",
            "is_producing": False,
            "messages": [AIMessage(content=f"调研失败: {str(e)}")],
        }


async def design_inner_node(state: ContentProductionState) -> ContentProductionState:
    """
    内涵设计节点
    
    生成3个方案供用户选择
    
    输出结构化的JSON方案，包含：
    - 3个不同的方案
    - 每个方案包含字段列表和依赖关系
    - 用户选择后才进入内涵生产
    """
    import json
    import re
    
    gc = state.get("golden_context", {})
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["design_inner"],
    )
    
    system_prompt = context.to_system_prompt()
    
    # 注意：Golden Context（项目意图、消费者画像）已经在 system_prompt 中
    # user_prompt 只需要发出任务指令
    user_prompt = """请基于上述项目意图和消费者画像，设计3个内容生产方案。

请输出严格的JSON格式（不要添加```json标记）。"""
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    raw_output = response.content
    
    # 解析JSON（处理可能的markdown代码块）
    json_content = raw_output
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw_output)
    if json_match:
        json_content = json_match.group(1)
    
    try:
        proposals_data = json.loads(json_content)
    except json.JSONDecodeError:
        # 如果解析失败，返回错误提示
        proposals_data = {
            "proposals": [],
            "error": "AI输出格式错误，请重试"
        }
    
    # 构建用于前端展示的内容
    # 方案存储为结构化JSON，前端负责渲染
    output_content = json.dumps(proposals_data, ensure_ascii=False, indent=2)
    
    # 构建简洁的展示文本（给右侧对话区）
    display_text = "✅ 已生成3个内涵设计方案，请在左侧工作台查看并选择。\n\n"
    if "proposals" in proposals_data and proposals_data["proposals"]:
        for i, p in enumerate(proposals_data["proposals"][:3], 1):
            display_text += f"**方案{i}**：{p.get('name', '未命名')}\n"
            display_text += f"  {p.get('description', '')[:100]}\n\n"
    
    full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{user_prompt}"
    
    return {
        **state,
        "agent_output": output_content,  # JSON格式，存入字段
        "display_output": display_text,   # 简洁展示，给对话区
        "messages": [AIMessage(content=display_text)],
        "phase_status": {**state.get("phase_status", {}), "design_inner": "in_progress"},  # 等待用户选择
        "current_phase": "design_inner",
        "is_producing": True,
        "waiting_for_human": True,  # 需要用户选择方案
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
        "full_prompt": full_prompt,
    }


async def produce_inner_node(state: ContentProductionState) -> ContentProductionState:
    """
    内涵生产节点
    
    根据设计方案生产内容
    """
    gc = state.get("golden_context", {})
    user_input = state.get("user_input", "请生产内涵内容。")
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["produce_inner"],
    )
    
    system_prompt = context.to_system_prompt()
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_input),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    confirm_text = "✅ 已生成【内涵生产】，请在左侧工作台查看。输入「继续」进入外延设计阶段。"
    
    # 构建完整提示词用于日志
    full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{user_input}"
    
    return {
        **state,
        "agent_output": response.content,
        "display_output": confirm_text,
        "full_prompt": full_prompt,  # 添加日志记录
        "messages": [AIMessage(content=confirm_text)],
        "phase_status": {**state.get("phase_status", {}), "produce_inner": "completed"},
        "current_phase": "produce_inner",
        "is_producing": True,
        "waiting_for_human": True,  # 等待用户确认
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
    }


async def design_outer_node(state: ContentProductionState) -> ContentProductionState:
    """外延设计节点"""
    gc = state.get("golden_context", {})
    user_input = "请设计外延传播方案。"
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["design_outer"],
    )
    
    system_prompt = context.to_system_prompt()
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_input),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    confirm_text = "✅ 已生成【外延设计】，请在左侧工作台查看。输入「继续」进入外延生产阶段。"
    full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{user_input}"
    
    return {
        **state,
        "agent_output": response.content,
        "display_output": confirm_text,
        "full_prompt": full_prompt,
        "messages": [AIMessage(content=confirm_text)],
        "phase_status": {**state.get("phase_status", {}), "design_outer": "completed"},
        "current_phase": "design_outer",
        "is_producing": True,
        "waiting_for_human": True,
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
    }


async def produce_outer_node(state: ContentProductionState) -> ContentProductionState:
    """外延生产节点"""
    gc = state.get("golden_context", {})
    user_input = state.get("user_input", "请生产外延内容。")
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["produce_outer"],
    )
    
    system_prompt = context.to_system_prompt()
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_input),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    confirm_text = "✅ 已生成【外延生产】，请在左侧工作台查看。输入「继续」进入消费者模拟阶段。"
    full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{user_input}"
    
    return {
        **state,
        "agent_output": response.content,
        "display_output": confirm_text,
        "full_prompt": full_prompt,
        "messages": [AIMessage(content=confirm_text)],
        "phase_status": {**state.get("phase_status", {}), "produce_outer": "completed"},
        "current_phase": "produce_outer",
        "is_producing": True,
        "waiting_for_human": True,
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
    }


async def simulate_node(state: ContentProductionState) -> ContentProductionState:
    """消费者模拟节点"""
    gc = state.get("golden_context", {})
    user_input = "请模拟用户体验并给出反馈。"
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["simulate"],
    )
    
    system_prompt = context.to_system_prompt()
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_input),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.8)
    
    confirm_text = "✅ 已生成【消费者模拟】，请在左侧工作台查看。输入「继续」进入评估阶段。"
    full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{user_input}"
    
    return {
        **state,
        "agent_output": response.content,
        "display_output": confirm_text,
        "full_prompt": full_prompt,
        "messages": [AIMessage(content=confirm_text)],
        "phase_status": {**state.get("phase_status", {}), "simulate": "completed"},
        "current_phase": "simulate",
        "is_producing": True,
        "waiting_for_human": True,
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
    }


async def evaluate_node(state: ContentProductionState) -> ContentProductionState:
    """评估节点"""
    gc = state.get("golden_context", {})
    user_input = "请对项目进行全面评估。"
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["evaluate"],
    )
    
    system_prompt = context.to_system_prompt()
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_input),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.5)
    
    confirm_text = "✅ 已生成【评估报告】，请在左侧工作台查看。内容生产流程已完成！"
    full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{user_input}"
    
    return {
        **state,
        "agent_output": response.content,
        "display_output": confirm_text,
        "full_prompt": full_prompt,
        "messages": [AIMessage(content=confirm_text)],
        "phase_status": {**state.get("phase_status", {}), "evaluate": "completed"},
        "current_phase": "evaluate",
        "is_producing": True,
        "waiting_for_human": True,  # 流程结束，等待用户
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
    }


async def chat_node(state: ContentProductionState) -> ContentProductionState:
    """
    自由对话节点
    
    处理不属于特定阶段的对话
    """
    gc = state.get("golden_context", {})
    history = state.get("messages", [])
    
    # 构建对话上下文
    system_prompt = f"""你是一个专业的内容策略顾问。当前正在进行内容生产项目。

项目上下文:
{gc.get('creator_profile', '')}
{gc.get('intent', '')}

当前阶段: {state.get('current_phase', 'intent')}

请帮助用户解答问题或提供建议。"""
    
    messages = [ChatMessage(role="system", content=system_prompt)]
    
    # 添加历史消息
    for msg in history[-10:]:  # 只取最近10条
        if isinstance(msg, HumanMessage):
            messages.append(ChatMessage(role="user", content=msg.content))
        elif isinstance(msg, AIMessage):
            messages.append(ChatMessage(role="assistant", content=msg.content))
    
    # 添加当前输入
    messages.append(ChatMessage(role="user", content=state.get("user_input", "")))
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    return {
        **state,
        "agent_output": response.content,
        "messages": [AIMessage(content=response.content)],
        "is_producing": False,  # 对话模式不保存为字段
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
    }


# ============== 检查点 ==============

def check_autonomy(state: ContentProductionState) -> str:
    """
    检查是否需要人工确认
    
    语义：autonomy[phase] = True 表示该阶段自动执行（不需要确认）
          autonomy[phase] = False 表示该阶段需要人工确认
    
    Returns:
        "wait_human" 或 "continue"
    """
    current_phase = state.get("current_phase", "intent")
    autonomy = state.get("autonomy_settings", {})
    
    # 自主权：True = 自动执行，False = 需要确认
    # 默认需要确认（autonomy 为 False 或不存在时）
    is_autonomous = autonomy.get(current_phase, False)
    
    if is_autonomous:
        # 自动执行，不需要等待
        return "continue"
    else:
        # 需要人工确认
        return "wait_human"


def get_next_phase(state: ContentProductionState) -> str:
    """获取下一个阶段"""
    current = state.get("current_phase", "intent")
    order = state.get("phase_order", PROJECT_PHASES)
    
    try:
        idx = order.index(current)
        if idx < len(order) - 1:
            return order[idx + 1]
    except ValueError:
        pass
    
    return "end"


# ============== 工具节点 ==============

async def generate_field_node(state: ContentProductionState) -> ContentProductionState:
    """
    生成字段工具节点
    
    根据用户请求生成指定字段
    """
    from core.tools.field_generator import generate_field
    
    gc = state.get("golden_context", {})
    user_input = state.get("user_input", "")
    current_phase = state.get("current_phase", "intent")
    
    # 从用户输入中提取要生成的字段名
    # 简单实现：直接使用当前阶段的默认字段
    field_names = {
        "intent": "项目意图",
        "research": "消费者调研报告",
        "design_inner": "内涵设计方案",
        "produce_inner": "内涵生产内容",
        "design_outer": "外延设计方案",
        "produce_outer": "外延生产内容",
        "simulate": "消费者模拟结果",
        "evaluate": "项目评估报告",
    }
    field_name = field_names.get(current_phase, "内容")
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS.get(current_phase, ""),
    )
    
    messages = [
        ChatMessage(role="system", content=context.to_system_prompt()),
        ChatMessage(role="user", content=f"请生成{field_name}。用户补充说明：{user_input}"),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    return {
        **state,
        "agent_output": response.content,
        "messages": [AIMessage(content=response.content)],
        "is_producing": True,  # 生成字段一定是产出模式
    }


async def read_field_node(state: ContentProductionState) -> ContentProductionState:
    """
    读取字段工具节点
    
    读取已生成的字段内容（@引用）
    """
    from core.database import SessionLocal
    from core.models import ProjectField
    
    user_input = state.get("user_input", "")
    project_id = state.get("project_id", "")
    
    # 解析@引用
    import re
    refs = re.findall(r'@([\w\u4e00-\u9fff]+)', user_input)
    
    db = SessionLocal()
    try:
        results = []
        for ref in refs:
            field = db.query(ProjectField).filter(
                ProjectField.project_id == project_id,
                ProjectField.name == ref,
            ).first()
            if field:
                results.append(f"## {field.name}\n{field.content}")
            else:
                results.append(f"## {ref}\n（未找到该字段）")
        
        output = "\n\n".join(results) if results else "没有找到引用的字段。"
    finally:
        db.close()
    
    return {
        **state,
        "agent_output": output,
        "messages": [AIMessage(content=output)],
        "is_producing": False,  # 查询不保存字段
    }


async def update_field_node(state: ContentProductionState) -> ContentProductionState:
    """
    更新字段工具节点
    
    修改已有字段内容
    """
    gc = state.get("golden_context", {})
    user_input = state.get("user_input", "")
    
    # 让AI根据用户要求修改内容
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
    )
    
    messages = [
        ChatMessage(role="system", content=f"""{context.to_system_prompt()}

你是一个内容编辑助手。用户想修改已有内容。请根据用户的要求，输出修改后的完整内容。"""),
        ChatMessage(role="user", content=user_input),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    return {
        **state,
        "agent_output": response.content,
        "messages": [AIMessage(content=response.content)],
        "is_producing": True,  # 修改后需要保存
    }


# ============== 路由函数 ==============

def route_by_intent(state: ContentProductionState) -> str:
    """根据意图路由到相应节点"""
    target = state.get("route_target", "chat")
    current_phase = state.get("current_phase", "intent")
    phase_order = state.get("phase_order", PROJECT_PHASES)
    
    if target == "phase_current":
        # 保持在当前阶段（用于意图分析阶段的对话回答）
        return f"phase_{current_phase}"
    elif target == "advance_phase":
        # 推进到下一阶段
        try:
            idx = phase_order.index(current_phase)
            if idx < len(phase_order) - 1:
                next_phase = phase_order[idx + 1]
                return f"phase_{next_phase}"
        except ValueError:
            pass
        return f"phase_{current_phase}"
    elif target == "research":
        return "research"
    elif target == "generate":
        return "generate_field"
    elif target == "modify":
        return "update_field"
    elif target == "query":
        return "read_field"
    elif target == "simulate":
        return "phase_simulate"
    elif target == "evaluate":
        return "phase_evaluate"
    else:
        # chat 和其他 -> 通用对话节点
        return "chat"


def route_after_phase(state: ContentProductionState) -> str:
    """阶段完成后的路由"""
    # ===== 核心检查：如果 is_producing=False（对话模式），结束本轮 =====
    # 意图分析等需要多轮对话的阶段，不会自动推进
    is_producing = state.get("is_producing", False)
    if not is_producing:
        return END  # 对话模式：结束本轮，等待用户下一条消息
    
    # ===== 检查是否明确要求等待人工（优先级最高） =====
    if state.get("waiting_for_human", False):
        return END  # 节点明确要求等待用户确认，结束本轮
    
    # 产出模式：检查自主权决定是否等待人工确认
    if check_autonomy(state) == "wait_human":
        return "wait_human"
    else:
        next_phase = get_next_phase(state)
        if next_phase == "end":
            return END
        return f"phase_{next_phase}"


# ============== 图构建 ==============

def create_content_production_graph():
    """
    创建内容生产Agent图
    
    Returns:
        编译后的LangGraph
    """
    # 创建图
    graph = StateGraph(ContentProductionState)
    
    # 添加节点
    graph.add_node("router", route_intent)
    graph.add_node("chat", chat_node)
    graph.add_node("research", research_node)
    
    # 阶段节点
    graph.add_node("phase_intent", intent_analysis_node)
    graph.add_node("phase_research", research_node)
    graph.add_node("phase_design_inner", design_inner_node)
    graph.add_node("phase_produce_inner", produce_inner_node)
    graph.add_node("phase_design_outer", design_outer_node)
    graph.add_node("phase_produce_outer", produce_outer_node)
    graph.add_node("phase_simulate", simulate_node)
    graph.add_node("phase_evaluate", evaluate_node)
    
    # 工具节点（设计文档中的 Tools）
    graph.add_node("generate_field", generate_field_node)
    graph.add_node("read_field", read_field_node)
    graph.add_node("update_field", update_field_node)
    
    # 等待人工确认节点（实际上只是返回状态）
    graph.add_node("wait_human", lambda s: {**s, "waiting_for_human": True})
    
    # 设置入口
    graph.set_entry_point("router")
    
    # 添加条件边：从router分发
    graph.add_conditional_edges(
        "router",
        route_by_intent,
        {
            # 阶段节点
            "phase_intent": "phase_intent",
            "phase_research": "phase_research",
            "phase_design_inner": "phase_design_inner",
            "phase_produce_inner": "phase_produce_inner",
            "phase_design_outer": "phase_design_outer",
            "phase_produce_outer": "phase_produce_outer",
            "phase_simulate": "phase_simulate",
            "phase_evaluate": "phase_evaluate",
            # 工具节点
            "research": "research",
            "generate_field": "generate_field",
            "read_field": "read_field",
            "update_field": "update_field",
            # 对话节点
            "chat": "chat",
        }
    )
    
    # 构建阶段路由映射（用于自主权判断）
    phase_routing_map = {"wait_human": "wait_human", END: END}
    for p in PROJECT_PHASES:
        phase_routing_map[f"phase_{p}"] = f"phase_{p}"
    
    # 从各阶段节点到等待/继续（根据自主权设置决定）
    for phase in PROJECT_PHASES:
        graph.add_conditional_edges(
            f"phase_{phase}",
            route_after_phase,
            phase_routing_map
        )
    
    # 从research到等待（根据自主权设置）
    graph.add_conditional_edges(
        "research",
        route_after_phase,
        phase_routing_map
    )
    
    # 工具节点到结束（工具执行完直接返回结果）
    graph.add_edge("generate_field", END)
    graph.add_edge("read_field", END)
    graph.add_edge("update_field", END)
    
    # 从chat到结束
    graph.add_edge("chat", END)
    
    # 从等待到结束（用户会在这里继续）
    graph.add_edge("wait_human", END)
    
    # 编译
    memory = MemorySaver()
    compiled = graph.compile(checkpointer=memory)
    
    return compiled


# ============== Agent类 ==============

class ContentProductionAgent:
    """
    内容生产Agent
    
    封装LangGraph，提供简单的接口
    """
    
    def __init__(self):
        self.graph = create_content_production_graph()
    
    async def run(
        self,
        project_id: str,
        user_input: str,
        current_phase: str = "intent",
        golden_context: Optional[dict] = None,
        autonomy_settings: Optional[dict] = None,
        use_deep_research: bool = True,
        thread_id: Optional[str] = None,
        chat_history: Optional[list] = None,  # 新增：传递历史对话
        phase_status: Optional[dict] = None,  # 新增：传递项目现有的阶段状态
    ) -> ContentProductionState:
        """
        运行Agent
        
        Args:
            project_id: 项目ID
            user_input: 用户输入
            current_phase: 当前阶段
            golden_context: Golden Context
            autonomy_settings: 自主权设置
            use_deep_research: 是否使用DeepResearch
            thread_id: 线程ID（用于状态持久化）
            chat_history: 历史对话记录
            phase_status: 项目现有的阶段状态
        
        Returns:
            最终状态
        """
        # 构建消息历史
        messages = []
        if chat_history:
            for msg in chat_history:
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=msg.get("content", "")))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=msg.get("content", "")))
        # 添加当前用户输入
        messages.append(HumanMessage(content=user_input))
        
        # 使用传入的 phase_status，否则初始化为 pending
        existing_phase_status = phase_status or {p: "pending" for p in PROJECT_PHASES}
        
        initial_state: ContentProductionState = {
            "project_id": project_id,
            "current_phase": current_phase,
            "phase_order": PROJECT_PHASES.copy(),
            "phase_status": existing_phase_status,  # 使用项目现有状态！
            "autonomy_settings": autonomy_settings or {p: True for p in PROJECT_PHASES},
            "golden_context": golden_context or {},
            "fields": {},
            "messages": messages,  # 使用完整历史
            "user_input": user_input,
            "agent_output": "",
            "waiting_for_human": False,
            "route_target": "",
            "use_deep_research": use_deep_research,
            "is_producing": False,  # 默认不是产出模式
            "error": None,
            # API 调用统计初始值
            "tokens_in": 0,
            "tokens_out": 0,
            "duration_ms": 0,
            "cost": 0.0,
            # 完整 prompt 初始值
            "full_prompt": "",
        }
        
        config = {"configurable": {"thread_id": thread_id or project_id}}
        
        result = await self.graph.ainvoke(initial_state, config)
        
        return result
    
    async def stream(
        self,
        project_id: str,
        user_input: str,
        **kwargs,
    ):
        """
        流式运行Agent
        
        Yields:
            状态更新
        """
        initial_state: ContentProductionState = {
            "project_id": project_id,
            "current_phase": kwargs.get("current_phase", "intent"),
            "phase_order": PROJECT_PHASES.copy(),
            "phase_status": {p: "pending" for p in PROJECT_PHASES},
            "autonomy_settings": kwargs.get("autonomy_settings", {p: True for p in PROJECT_PHASES}),
            "golden_context": kwargs.get("golden_context", {}),
            "fields": {},
            "messages": [HumanMessage(content=user_input)],
            "user_input": user_input,
            "agent_output": "",
            "waiting_for_human": False,
            "route_target": "",
            "use_deep_research": kwargs.get("use_deep_research", True),
            "is_producing": False,
            "error": None,
        }
        
        config = {"configurable": {"thread_id": kwargs.get("thread_id", project_id)}}
        
        async for event in self.graph.astream(initial_state, config):
            yield event


# 单例
content_agent = ContentProductionAgent()

