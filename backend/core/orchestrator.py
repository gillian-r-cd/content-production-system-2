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

from typing import TypedDict, Literal, Optional, Any, Annotated
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
    phase_order: list[str]
    
    # 每阶段状态
    phase_status: dict[str, str]
    
    # Agent自主权设置
    autonomy_settings: dict[str, bool]
    
    # Golden Context
    golden_context: dict
    
    # 已生成的字段 {field_id: content}
    fields: dict[str, str]
    
    # 对话历史（用于右栏Agent对话）
    messages: Annotated[list[BaseMessage], operator.add]
    
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
    - 意图分析阶段：用户大多是在回答问题，默认保持在当前阶段
    - 只有明确的操作请求才路由到其他节点
    """
    user_input = state.get("user_input", "")
    current_phase = state.get("current_phase", "intent")
    
    # ===== 意图分析阶段特殊处理 =====
    # 在意图分析阶段，用户的输入大多是在回答问题，不应该被错误路由
    if current_phase == "intent":
        # 只有这些明确的关键词才触发其他操作
        explicit_triggers = {
            "research": ["开始调研", "消费者调研", "用户调研", "市场调研"],
            "simulate": ["开始模拟", "模拟一下", "测试效果"],
            "evaluate": ["开始评估", "评估一下", "打分"],
            "advance_phase": ["继续", "下一步", "进入下一阶段"],
        }
        
        for intent, triggers in explicit_triggers.items():
            if any(t in user_input for t in triggers):
                return {**state, "route_target": intent}
        
        # 其他所有输入都保持在意图分析阶段
        # intent_analysis_node 会判断是提问还是产出
        return {**state, "route_target": "phase_current"}
    
    # ===== 其他阶段：使用LLM判断意图 =====
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
    
    两种模式：
    1. 引导提问：用户还在回答问题，AI 继续提问（不保存为字段）
    2. 产出生成：用户触发生成，AI 输出结构化意图分析（保存为字段）
    
    规则：最多问3个问题，每个问题标注 "问题 X/3"
    """
    gc = state.get("golden_context", {})
    user_input = state.get("user_input", "")
    chat_history = state.get("messages", [])
    
    # 统计已经问了几个问题（AI发送的消息数 = 问题数）
    ai_question_count = sum(1 for m in chat_history if isinstance(m, AIMessage))
    MAX_QUESTIONS = 3
    current_question = ai_question_count + 1  # 本次是第几个问题
    
    # 判断是否触发产出生成模式
    trigger_keywords = ["生成", "总结", "分析一下", "开始生成", "确定", "可以了", "就这些", "没有了", "继续"]
    is_producing = (
        any(kw in user_input for kw in trigger_keywords) or
        current_question > MAX_QUESTIONS  # 已问完3个问题，自动生成
    )
    
    # 构建对话历史上下文
    history_context = ""
    for msg in chat_history[-10:]:  # 最近10条消息
        if isinstance(msg, HumanMessage):
            history_context += f"用户: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            history_context += f"助手: {msg.content}\n"
    
    # 选择提示词
    if is_producing:
        system_prompt = prompt_engine.INTENT_PRODUCING_PROMPT
    else:
        # 提问模式：告知当前是第几个问题
        system_prompt = f"""{prompt_engine.INTENT_QUESTIONING_PROMPT}

重要规则：
- 这是第 {current_question} 个问题（共3个）
- 请在问题开头标注【问题 {current_question}/3】
- 本次只问1个最关键的问题，简洁明了"""
    
    messages = [
        ChatMessage(
            role="system",
            content=system_prompt
        ),
        ChatMessage(
            role="user",
            content=f"""项目背景:
{gc.get('creator_profile', '')}

对话历史:
{history_context}

用户最新输入: {user_input}"""
        ),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    # 更新状态
    new_messages = [AIMessage(content=response.content)]
    
    return {
        **state,
        "agent_output": response.content,
        "messages": new_messages,
        "phase_status": {**state.get("phase_status", {}), "intent": "in_progress"},
        # 标记是否是产出模式，用于 agent.py 判断是否保存字段
        "is_producing": is_producing,
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
    
    try:
        if use_deep:
            report = await deep_research(query, intent)
        else:
            report = await quick_research(query, intent)
        
        # 格式化报告
        report_text = f"""# 消费者调研报告

## 总体概述
{report.summary}

## 消费者画像
{report.consumer_profile}

## 核心痛点
{chr(10).join(f"- {p}" for p in report.pain_points)}

## 价值主张
{chr(10).join(f"- {v}" for v in report.value_propositions)}

## 典型用户小传
"""
        for persona in report.personas:
            report_text += f"""
### {persona.name}
**背景**: {persona.background}
**故事**: {persona.story}
**痛点**: {', '.join(persona.pain_points)}
"""
        
        # 更新Golden Context
        new_gc = {
            **gc,
            "consumer_personas": report_text,
        }
        
        return {
            **state,
            "agent_output": report_text,
            "messages": [AIMessage(content=report_text)],
            "golden_context": new_gc,
            "phase_status": {**state.get("phase_status", {}), "research": "completed"},
        }
        
    except Exception as e:
        return {
            **state,
            "error": str(e),
            "agent_output": f"调研失败: {str(e)}",
            "messages": [AIMessage(content=f"调研失败: {str(e)}")],
        }


async def design_inner_node(state: ContentProductionState) -> ContentProductionState:
    """
    内涵设计节点
    
    设计内容生产方案和大纲
    """
    gc = state.get("golden_context", {})
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["design_inner"],
    )
    
    messages = [
        ChatMessage(role="system", content=context.to_system_prompt()),
        ChatMessage(role="user", content="请设计内涵生产方案。"),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    return {
        **state,
        "agent_output": response.content,
        "messages": [AIMessage(content=response.content)],
        "phase_status": {**state.get("phase_status", {}), "design_inner": "completed"},
    }


async def produce_inner_node(state: ContentProductionState) -> ContentProductionState:
    """
    内涵生产节点
    
    根据设计方案生产内容
    """
    gc = state.get("golden_context", {})
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["produce_inner"],
    )
    
    messages = [
        ChatMessage(role="system", content=context.to_system_prompt()),
        ChatMessage(role="user", content=state.get("user_input", "请生产内涵内容。")),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    return {
        **state,
        "agent_output": response.content,
        "messages": [AIMessage(content=response.content)],
        "phase_status": {**state.get("phase_status", {}), "produce_inner": "completed"},
    }


async def design_outer_node(state: ContentProductionState) -> ContentProductionState:
    """外延设计节点"""
    gc = state.get("golden_context", {})
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["design_outer"],
    )
    
    messages = [
        ChatMessage(role="system", content=context.to_system_prompt()),
        ChatMessage(role="user", content="请设计外延传播方案。"),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    return {
        **state,
        "agent_output": response.content,
        "messages": [AIMessage(content=response.content)],
        "phase_status": {**state.get("phase_status", {}), "design_outer": "completed"},
    }


async def produce_outer_node(state: ContentProductionState) -> ContentProductionState:
    """外延生产节点"""
    gc = state.get("golden_context", {})
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["produce_outer"],
    )
    
    messages = [
        ChatMessage(role="system", content=context.to_system_prompt()),
        ChatMessage(role="user", content=state.get("user_input", "请生产外延内容。")),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    return {
        **state,
        "agent_output": response.content,
        "messages": [AIMessage(content=response.content)],
        "phase_status": {**state.get("phase_status", {}), "produce_outer": "completed"},
    }


async def simulate_node(state: ContentProductionState) -> ContentProductionState:
    """消费者模拟节点"""
    gc = state.get("golden_context", {})
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["simulate"],
    )
    
    messages = [
        ChatMessage(role="system", content=context.to_system_prompt()),
        ChatMessage(role="user", content="请模拟用户体验并给出反馈。"),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.8)
    
    return {
        **state,
        "agent_output": response.content,
        "messages": [AIMessage(content=response.content)],
        "phase_status": {**state.get("phase_status", {}), "simulate": "completed"},
    }


async def evaluate_node(state: ContentProductionState) -> ContentProductionState:
    """评估节点"""
    gc = state.get("golden_context", {})
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=gc.get("creator_profile", ""),
            intent=gc.get("intent", ""),
            consumer_personas=gc.get("consumer_personas", ""),
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["evaluate"],
    )
    
    messages = [
        ChatMessage(role="system", content=context.to_system_prompt()),
        ChatMessage(role="user", content="请对项目进行全面评估。"),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.5)
    
    return {
        **state,
        "agent_output": response.content,
        "messages": [AIMessage(content=response.content)],
        "phase_status": {**state.get("phase_status", {}), "evaluate": "completed"},
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
    }


# ============== 检查点 ==============

def check_autonomy(state: ContentProductionState) -> str:
    """
    检查是否需要人工确认
    
    Returns:
        "wait_human" 或 "continue"
    """
    current_phase = state.get("current_phase", "intent")
    autonomy = state.get("autonomy_settings", {})
    
    # 默认需要确认
    needs_confirm = autonomy.get(current_phase, True)
    
    if needs_confirm:
        return "wait_human"
    else:
        return "continue"


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
    
    # 从各阶段节点到等待/继续
    for phase in PROJECT_PHASES:
        graph.add_edge(f"phase_{phase}", "wait_human")
    
    # 从research到等待
    graph.add_edge("research", "wait_human")
    
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
        
        Returns:
            最终状态
        """
        initial_state: ContentProductionState = {
            "project_id": project_id,
            "current_phase": current_phase,
            "phase_order": PROJECT_PHASES.copy(),
            "phase_status": {p: "pending" for p in PROJECT_PHASES},
            "autonomy_settings": autonomy_settings or {p: True for p in PROJECT_PHASES},
            "golden_context": golden_context or {},
            "fields": {},
            "messages": [HumanMessage(content=user_input)],
            "user_input": user_input,
            "agent_output": "",
            "waiting_for_human": False,
            "route_target": "",
            "use_deep_research": use_deep_research,
            "is_producing": False,  # 默认不是产出模式
            "error": None,
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

