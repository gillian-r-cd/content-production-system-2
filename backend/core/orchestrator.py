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
from core.tools.architecture_reader import (
    get_project_architecture, 
    format_architecture_for_llm,
    get_field_content,
)


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
    
    # ===== @ 引用相关（新增）=====
    # @ 引用的字段名列表
    references: List[str]
    
    # 引用字段的实际内容 {字段名: 内容}
    referenced_contents: Dict[str, str]
    
    # ===== 解析后的意图（新增）=====
    # 意图类型: modify/generate/query/chat/phase_action/tool_call
    parsed_intent_type: str
    
    # 目标字段名（如果有）
    parsed_target_field: Optional[str]
    
    # 操作描述
    parsed_operation: str
    
    # 修改操作的目标字段（用于保存修改后的内容）
    modify_target_field: Optional[str]


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
    意图路由器（重构版）
    
    核心原则：意图优先，不被阶段锁定
    
    路由逻辑：
    1. 如果有 @ 引用 → 分析是修改还是查询
    2. 如果是阶段推进触发词 → advance_phase
    3. 如果是阶段开始触发词 + 阶段未完成 → phase_current
    4. 其他情况 → LLM 意图分类
    """
    user_input = state.get("user_input", "")
    current_phase = state.get("current_phase", "intent")
    phase_status = state.get("phase_status", {})
    references = state.get("references", [])
    referenced_contents = state.get("referenced_contents", {})
    
    current_phase_status = phase_status.get(current_phase, "pending")
    
    # ===== 规则 1: 有 @ 引用时，优先分析引用意图 =====
    if references and referenced_contents:
        # 检查是否是修改意图
        modify_keywords = ["修改", "改成", "改为", "调整", "变成", "替换", "更新", "重写"]
        if any(kw in user_input for kw in modify_keywords):
            target_field = references[0]  # 取第一个引用作为目标
            return {
                **state, 
                "route_target": "modify",
                "parsed_intent_type": "modify",
                "parsed_target_field": target_field,
                "parsed_operation": user_input,
            }
        
        # 检查是否是查询意图
        query_keywords = ["是什么", "什么意思", "解释", "总结", "看看", "分析"]
        if any(kw in user_input for kw in query_keywords):
            target_field = references[0]
            return {
                **state, 
                "route_target": "query",
                "parsed_intent_type": "query",
                "parsed_target_field": target_field,
                "parsed_operation": user_input,
            }
        
        # 默认有 @ 引用但意图不明确 → 使用 LLM 判断
    
    # ===== 规则 2: 阶段推进触发词 =====
    advance_triggers = ["继续", "下一步", "进入下一阶段", "确认", "好的", "可以", "开始下一"]
    if any(t in user_input for t in advance_triggers) and current_phase_status == "completed":
        return {**state, "route_target": "advance_phase", "parsed_intent_type": "advance_phase"}
    
    # ===== 规则 3: 阶段开始触发词 + 阶段未完成 =====
    start_triggers = ["开始", "开始吧", "start", "go", "执行"]
    is_start_trigger = any(t in user_input.lower() for t in start_triggers)
    
    if is_start_trigger and current_phase_status != "completed":
        return {**state, "route_target": "phase_current", "parsed_intent_type": "phase_action"}
    
    # ===== 规则 4: 意图分析阶段的问答流程 =====
    # 只有当项目包含 intent 阶段时才进入意图分析流程
    phase_order = state.get("phase_order", PROJECT_PHASES)
    if "intent" in phase_order and current_phase == "intent" and current_phase_status != "completed":
        return {**state, "route_target": "phase_current", "parsed_intent_type": "phase_action"}
    
    # ===== 规则 5: LLM 智能意图分类（带架构感知和工具选择）=====
    # 获取项目架构信息
    project_id = state.get("project_id", "")
    arch_info = ""
    if project_id:
        try:
            arch = get_project_architecture(project_id)
            if arch:
                arch_info = f"\n\n项目架构:\n{format_architecture_for_llm(arch)}"
        except Exception as e:
            arch_info = f"\n\n(架构信息获取失败: {str(e)})"
    
    # 构建上下文信息
    ref_info = ""
    if references:
        ref_info = f"\n用户引用的字段: {', '.join(references)}"
        ref_contents = "\n".join([f"- {name}: {content[:100]}..." for name, content in referenced_contents.items()])
        ref_info += f"\n引用内容预览:\n{ref_contents}"
    
    messages = [
        ChatMessage(
            role="system",
            content=f"""你是一个精准的意图分类器。根据用户输入，判断是否需要调用工具来执行实际操作。

## 核心判断原则
**如果用户想要"做"某事（创建/添加/删除/修改/生成），优先选择工具执行！**
**如果用户只是"问"或"聊"，才选择 chat。**

## 当前上下文
- 当前阶段: {current_phase}
- 阶段状态: {current_phase_status}{ref_info}{arch_info}

## 工具清单（优先考虑）

### tool_architecture - 项目结构操作
当用户提到这些概念时选择：加字段、删字段、加阶段、删阶段、移动、拆分、合并、调整结构、新增模块
例如：
- "帮我加一个新字段" → tool_architecture
- "把这个阶段删掉" → tool_architecture  
- "我想拆分一下内涵设计" → tool_architecture
- "在内容里加一个关键洞察" → tool_architecture

### tool_outline - 内容规划
当用户想规划内容结构时选择：设计大纲、内容框架、怎么组织、课程结构、文章架构
例如：
- "帮我设计一下大纲" → tool_outline
- "这个内容怎么组织比较好" → tool_outline

### tool_persona - 人物管理
当用户想管理用户画像时选择：生成人物、创建用户、查看人物、选中、取消选中
例如：
- "再生成一个程序员用户" → tool_persona
- "看看有哪些人物" → tool_persona

### tool_skill - 技能使用
当用户想用特定风格/技能时选择：用专业方式、用故事化方式、简化内容、批判分析、有什么技能
例如：
- "用专业的方式帮我写" → tool_skill
- "有什么技能可以用" → tool_skill

## 其他意图类型
- modify: 修改已有字段内容（配合@引用）
- query: 查询信息（是什么、有哪些阶段）
- generate: 生成字段内容
- advance_phase: 进入下一阶段
- phase_action: 开始当前阶段
- research/simulate/evaluate: 执行对应阶段
- chat: **仅当上述都不匹配时**

## 输出格式（JSON）
{{"intent": "意图类型", "target": "目标对象", "operation": "操作描述"}}

只输出JSON。"""
        ),
        ChatMessage(role="user", content=user_input),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.3)
    
    # 解析 JSON 响应
    import json
    try:
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content)
        intent = result.get("intent", "chat")
        target = result.get("target", "")
        operation = result.get("operation", user_input)
        print(f"[route_intent] LLM分类结果: intent={intent}, target={target}")
    except Exception as e:
        # 解析失败，尝试直接匹配意图
        print(f"[route_intent] JSON解析失败: {e}, 原始响应: {response.content[:200]}")
        intent = response.content.strip().lower()
        target = ""
        operation = user_input
    
    # 标准化意图（支持简写映射）
    intent_mapping = {
        # 简写 → 完整形式
        "architecture": "tool_architecture",
        "outline": "tool_outline", 
        "persona": "tool_persona",
        "skill": "tool_skill",
        # 完整形式保持不变
        "tool_architecture": "tool_architecture",
        "tool_outline": "tool_outline",
        "tool_persona": "tool_persona",
        "tool_skill": "tool_skill",
        # 其他意图
        "advance_phase": "advance_phase",
        "generate": "generate",
        "modify": "modify",
        "research": "research",
        "simulate": "simulate",
        "evaluate": "evaluate",
        "query": "query",
        "phase_action": "phase_action",
        "chat": "chat",
    }
    intent = intent_mapping.get(intent, "chat")
    print(f"[route_intent] 标准化后: intent={intent}")
    
    # 工具意图直接使用具体的工具类型，以便正确路由
    if intent.startswith("tool_"):
        route_target = intent  # 保留具体类型: tool_architecture, tool_persona 等
    elif intent == "phase_action":
        route_target = "phase_current"
    else:
        route_target = intent
    
    # 如果是 modify/query 但没有目标字段，尝试从引用或解析结果中获取
    target_field = target if target else None
    if intent in ["modify", "query"] and references and not target_field:
        target_field = references[0]
    
    return {
        **state, 
        "route_target": route_target,
        "parsed_intent_type": intent,
        "parsed_target_field": target_field,
        "parsed_operation": operation,
    }


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
        # 注意：不自动设置 completed，需要用户点击确认按钮后由 advance 接口设置
        new_phase_status["intent"] = "in_progress"
        
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
            # 注意：不自动设置 completed，需要用户确认
            "phase_status": {**state.get("phase_status", {}), "research": "in_progress"},
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
        # 注意：不自动设置 completed，需要用户确认
        "phase_status": {**state.get("phase_status", {}), "produce_inner": "in_progress"},
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
        # 注意：不自动设置 completed，需要用户确认
        "phase_status": {**state.get("phase_status", {}), "design_outer": "in_progress"},
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
        # 注意：不自动设置 completed，需要用户确认
        "phase_status": {**state.get("phase_status", {}), "produce_outer": "in_progress"},
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
        # 注意：不自动设置 completed，需要用户确认
        "phase_status": {**state.get("phase_status", {}), "simulate": "in_progress"},
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
        # 注意：不自动设置 completed，需要用户确认
        "phase_status": {**state.get("phase_status", {}), "evaluate": "in_progress"},
        "current_phase": "evaluate",
        "is_producing": True,
        "waiting_for_human": True,  # 流程结束，等待用户
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
    }


# ============== 修改和查询节点 ==============

async def modify_node(state: ContentProductionState) -> ContentProductionState:
    """
    字段修改节点
    
    根据用户指令修改已有字段内容
    """
    gc = state.get("golden_context", {})
    target_field = state.get("parsed_target_field", "")
    operation = state.get("parsed_operation", "")
    referenced_contents = state.get("referenced_contents", {})
    
    # 获取目标字段的原始内容
    original_content = referenced_contents.get(target_field, "")
    
    if not original_content:
        return {
            **state,
            "agent_output": f"未找到字段「{target_field}」的内容，无法修改。",
            "is_producing": False,
            "waiting_for_human": False,
        }
    
    # 构建修改提示词
    system_prompt = f"""你是一个专业的内容编辑。请根据用户的修改指令，对原始内容进行修改。

项目上下文:
{gc.get('creator_profile', '')}
{gc.get('intent', '')}

原始内容（字段名：{target_field}）:
{original_content}

用户修改指令: {operation}

规则：
1. 严格按照用户的修改指令进行修改
2. 保持内容的专业性和一致性
3. 只输出修改后的完整内容，不要添加任何解释
4. 保持原有的格式风格"""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=f"请修改「{target_field}」的内容"),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.5)
    modified_content = response.content
    
    # 返回修改后的内容（is_producing=True 会触发保存）
    return {
        **state,
        "agent_output": modified_content,
        "is_producing": True,  # 标记为产出模式，触发字段保存
        "waiting_for_human": False,
        "current_phase": state.get("current_phase", "intent"),  # 保持当前阶段
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
        "full_prompt": system_prompt,
        # 特殊标记：这是修改操作，需要更新指定字段
        "modify_target_field": target_field,
    }


async def query_node(state: ContentProductionState) -> ContentProductionState:
    """
    字段/架构查询节点
    
    回答关于已有字段或项目架构的问题
    支持：
    1. 字段内容查询
    2. 项目架构查询（阶段列表、字段列表等）
    """
    gc = state.get("golden_context", {})
    project_id = state.get("project_id", "")
    target_field = state.get("parsed_target_field", "")
    operation = state.get("parsed_operation", "")
    referenced_contents = state.get("referenced_contents", {})
    
    # 判断是否是架构级别的查询
    arch_keywords = ["阶段", "字段", "目录", "结构", "架构", "有哪些", "列表", "进度"]
    is_architecture_query = any(kw in operation for kw in arch_keywords)
    
    # 获取架构信息
    arch_info = ""
    if is_architecture_query and project_id:
        try:
            arch = get_project_architecture(project_id)
            if arch:
                arch_info = f"\n\n## 项目架构信息\n{format_architecture_for_llm(arch)}"
        except Exception as e:
            arch_info = f"\n\n(架构信息获取失败: {str(e)})"
    
    # 获取目标字段的内容
    field_content = referenced_contents.get(target_field, "")
    
    # 如果没有引用但指定了字段名，尝试直接获取
    if target_field and not field_content and project_id:
        try:
            field_data = get_field_content(project_id, target_field)
            if field_data:
                field_content = field_data.get("content", "")
                referenced_contents[target_field] = field_content
        except Exception:
            pass
    
    # 构建查询上下文
    all_refs = "\n\n".join([
        f"### {name}\n{content}" 
        for name, content in referenced_contents.items()
    ])
    
    system_prompt = f"""你是一个专业的内容分析师。请根据用户的问题，分析和解释已有的内容或项目结构。

项目上下文:
{gc.get('creator_profile', '')}
{gc.get('intent', '')}{arch_info}

引用的字段内容:
{all_refs if all_refs else '(无引用字段)'}

规则：
1. 准确回答用户的问题
2. 如果问的是架构/阶段/字段列表，根据架构信息回答
3. 如果是总结，简明扼要
4. 如果是解释，通俗易懂
5. 如果是分析，逻辑清晰"""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=operation),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    return {
        **state,
        "agent_output": response.content,
        "is_producing": False,  # 查询不产出新内容
        "waiting_for_human": False,
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
        "full_prompt": system_prompt,
    }


async def chat_node(state: ContentProductionState) -> ContentProductionState:
    """
    自由对话节点（重构版）
    
    处理自由对话，注入 @ 引用的内容
    """
    gc = state.get("golden_context", {})
    history = state.get("messages", [])
    referenced_contents = state.get("referenced_contents", {})
    references = state.get("references", [])
    
    # 构建引用内容上下文
    ref_context = ""
    if references and referenced_contents:
        ref_parts = []
        for name in references:
            content = referenced_contents.get(name, "")
            if content:
                ref_parts.append(f"### {name}\n{content}")
        if ref_parts:
            ref_context = f"""
用户引用的字段内容:
{chr(10).join(ref_parts)}
"""
    
    # 构建对话上下文
    system_prompt = f"""你是一个专业的内容策略顾问。当前正在进行内容生产项目。

项目上下文:
{gc.get('creator_profile', '')}
{gc.get('intent', '')}

当前阶段: {state.get('current_phase', 'intent')}{ref_context}

请帮助用户解答问题或提供建议。你可以：
1. 回答关于项目的任何问题
2. 根据引用的内容提供分析和建议
3. 帮助用户规划下一步行动
4. 解释当前进度和状态"""
    
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


async def tool_node(state: ContentProductionState) -> ContentProductionState:
    """
    统一工具调用节点
    
    使用 LLM 解析用户意图，提取工具参数并执行
    """
    from core.tools.architecture_writer import (
        add_phase, remove_phase, add_field, remove_field, 
        update_field, move_field, reorder_phases
    )
    from core.tools.outline_generator import generate_outline, apply_outline_to_project
    from core.tools.persona_manager import (
        list_personas, create_persona, generate_persona,
        select_persona, delete_persona, update_persona
    )
    from core.tools.skill_manager import list_skills, apply_skill, get_skill, create_skill
    
    intent_type = state.get("parsed_intent_type", "")
    project_id = state.get("project_id", "")
    user_input = state.get("user_input", "")
    operation = state.get("parsed_operation", user_input)
    
    output = ""
    
    try:
        if intent_type == "tool_architecture":
            output = await _llm_handle_architecture(project_id, user_input, state)
        
        elif intent_type == "tool_outline":
            output = await _llm_handle_outline(project_id, user_input, state)
        
        elif intent_type == "tool_persona":
            output = await _llm_handle_persona(project_id, user_input, state)
        
        elif intent_type == "tool_skill":
            output = await _llm_handle_skill(user_input, state)
        
        else:
            output = f"未知工具类型: {intent_type}"
            
    except Exception as e:
        import traceback
        output = f"工具执行错误: {str(e)}\n\n```\n{traceback.format_exc()}\n```"
    
    return {
        **state,
        "agent_output": output,
        "messages": [AIMessage(content=output)],
        "is_producing": False,
    }


async def _llm_handle_architecture(project_id: str, user_input: str, state: dict) -> str:
    """使用 LLM 解析架构操作意图并执行"""
    from core.tools.architecture_writer import (
        add_phase, remove_phase, add_field, remove_field,
        update_field, move_field
    )
    from core.tools.architecture_reader import get_project_architecture, format_architecture_for_llm
    
    # 获取当前架构
    arch = get_project_architecture(project_id)
    arch_context = format_architecture_for_llm(arch) if arch else "无法获取架构信息"
    
    # 让 LLM 解析操作
    parse_prompt = f"""你是一个架构操作解析器。根据用户请求，解析出具体的架构操作。

## 当前项目架构
{arch_context}

## 可用操作
1. add_phase: 添加阶段 (参数: phase_code, display_name, position)
2. remove_phase: 删除阶段 (参数: phase_name)
3. add_field: 添加字段 (参数: phase, name, ai_prompt)
4. remove_field: 删除字段 (参数: field_name)
5. move_field: 移动字段 (参数: field_name, target_phase)
6. update_field: 更新字段 (参数: field_name, updates)

## 阶段代码映射
- intent = 意图分析
- research = 消费者调研
- design_inner = 内涵设计
- produce_inner = 内涵生产
- design_outer = 外延设计
- produce_outer = 外延生产
- simulate = 消费者模拟
- evaluate = 评估

## 用户请求
{user_input}

## 输出格式（JSON）
{{"action": "操作名", "params": {{参数对象}}}}

只输出 JSON，不要解释。如果无法解析，输出 {{"action": "unknown", "reason": "原因"}}"""

    messages = [
        ChatMessage(role="system", content=parse_prompt),
        ChatMessage(role="user", content="请解析操作"),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.2)
    
    import json
    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content)
        action = result.get("action", "unknown")
        params = result.get("params", {})
    except:
        return f"无法解析操作请求。请尝试更明确的描述，例如：\n- 在内涵生产阶段添加一个「核心论点」字段\n- 删除「意图分析」阶段"
    
    # 执行操作
    if action == "add_phase":
        op_result = add_phase(
            project_id,
            params.get("phase_code", f"custom_{params.get('display_name', 'new')}"),
            params.get("display_name", "新阶段"),
            params.get("position")
        )
        return op_result.message
    
    elif action == "remove_phase":
        op_result = remove_phase(project_id, params.get("phase_name", ""))
        return op_result.message
    
    elif action == "add_field":
        op_result = add_field(
            project_id,
            params.get("phase", "produce_inner"),
            params.get("name", "新字段"),
            params.get("ai_prompt", ""),
        )
        return op_result.message
    
    elif action == "remove_field":
        op_result = remove_field(project_id, params.get("field_name", ""))
        return op_result.message
    
    elif action == "move_field":
        op_result = move_field(
            project_id,
            params.get("field_name", ""),
            params.get("target_phase", ""),
        )
        return op_result.message
    
    elif action == "update_field":
        op_result = update_field(
            project_id,
            params.get("field_name", ""),
            params.get("updates", {}),
        )
        return op_result.message
    
    else:
        reason = result.get("reason", "无法识别的操作")
        return f"无法执行操作: {reason}\n\n支持的操作：添加/删除阶段、添加/删除/移动字段"


async def _llm_handle_outline(project_id: str, user_input: str, state: dict) -> str:
    """使用 LLM 处理大纲相关请求"""
    from core.tools.outline_generator import generate_outline
    
    # 解析用户是要生成还是确认大纲
    if "确认" in user_input:
        # TODO: 应用大纲到项目
        return "大纲确认功能开发中。目前请手动在左侧添加字段。"
    
    # 生成大纲
    content_type = ""
    if "课程" in user_input:
        content_type = "课程"
    elif "文章" in user_input:
        content_type = "文章"
    elif "视频" in user_input:
        content_type = "视频脚本"
    
    outline = await generate_outline(project_id, content_type, user_input)
    
    if "失败" in outline.title:
        return f"## 大纲生成遇到问题\n\n{outline.summary}"
    
    output = f"## 📋 {outline.title}\n\n{outline.summary}\n\n"
    for i, node in enumerate(outline.nodes, 1):
        output += f"### {i}. {node.name}\n{node.description}\n"
        if node.ai_prompt:
            output += f"*AI提示：{node.ai_prompt[:80]}...*\n"
        if node.children:
            for j, child in enumerate(node.children, 1):
                output += f"   {i}.{j} **{child.name}**: {child.description}\n"
        output += "\n"
    
    output += f"\n---\n*预计生成 {outline.estimated_fields} 个字段*"
    return output


async def _llm_handle_persona(project_id: str, user_input: str, state: dict) -> str:
    """使用 LLM 解析人物操作意图并执行"""
    from core.tools.persona_manager import (
        list_personas, generate_persona, select_persona, 
        delete_persona, update_persona
    )
    
    # 让 LLM 解析操作
    parse_prompt = f"""你是一个人物操作解析器。根据用户请求，解析出具体的操作。

## 可用操作
1. list: 列出所有人物
2. generate: 生成新人物 (参数: hint - 生成提示)
3. select: 选中人物用于模拟 (参数: name)
4. deselect: 取消选中 (参数: name)
5. delete: 删除人物 (参数: name)

## 用户请求
{user_input}

## 输出格式（JSON）
{{"action": "操作名", "params": {{参数对象}}}}

只输出 JSON。"""

    messages = [
        ChatMessage(role="system", content=parse_prompt),
        ChatMessage(role="user", content="请解析操作"),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.2)
    
    import json
    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content)
        action = result.get("action", "list")
        params = result.get("params", {})
    except:
        action = "list"
        params = {}
    
    if action == "list":
        op_result = list_personas(project_id)
        if op_result.personas:
            output = "## 👥 当前人物列表\n\n"
            for p in op_result.personas:
                status = "✅ 已选中" if p.selected else "⬜ 未选中"
                output += f"### {p.name} {status}\n"
                output += f"**背景**: {p.background[:100]}...\n"
                if p.pain_points:
                    output += f"**痛点**: {', '.join(p.pain_points[:3])}\n"
                output += "\n"
            return output
        return "暂无人物。请先完成消费者调研，或说「生成一个技术背景的用户」来创建人物。"
    
    elif action == "generate":
        hint = params.get("hint", user_input)
        op_result = await generate_persona(project_id, hint)
        if op_result.success and op_result.persona:
            p = op_result.persona
            return f"## ✨ 已创建人物「{p.name}」\n\n**背景**: {p.background}\n\n**痛点**:\n" + "\n".join([f"- {pt}" for pt in p.pain_points])
        return op_result.message
    
    elif action == "select":
        op_result = select_persona(project_id, params.get("name", ""), True)
        return op_result.message
    
    elif action == "deselect":
        op_result = select_persona(project_id, params.get("name", ""), False)
        return op_result.message
    
    elif action == "delete":
        op_result = delete_persona(project_id, params.get("name", ""))
        return op_result.message
    
    return "无法识别人物操作。试试说：「查看人物」「生成一个程序员用户」「选中李明」"


async def _llm_handle_skill(user_input: str, state: dict) -> str:
    """使用 LLM 解析技能操作意图并执行"""
    from core.tools.skill_manager import list_skills, apply_skill, get_skill
    
    # 让 LLM 解析操作
    parse_prompt = f"""你是一个技能操作解析器。根据用户请求，解析出具体的操作。

## 可用操作
1. list: 列出所有技能
2. apply: 应用技能 (参数: skill_name, task - 要执行的任务描述)
3. get: 查看技能详情 (参数: skill_name)

## 预置技能
- 专业文案: 生成专业、权威的文案
- 故事化表达: 将内容转化为故事
- 内容简化: 简化复杂内容
- 批判性分析: 批判性分析内容

## 用户请求
{user_input}

## 输出格式（JSON）
{{"action": "操作名", "params": {{参数对象}}}}

只输出 JSON。"""

    messages = [
        ChatMessage(role="system", content=parse_prompt),
        ChatMessage(role="user", content="请解析操作"),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.2)
    
    import json
    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content)
        action = result.get("action", "list")
        params = result.get("params", {})
    except:
        action = "list"
        params = {}
    
    if action == "list":
        op_result = list_skills()
        if op_result.skills:
            output = "## 🛠️ 可用技能列表\n\n"
            for s in op_result.skills:
                tag = "🔧 系统" if s.is_system else "👤 自定义"
                output += f"- **{s.name}** ({tag})\n  {s.description}\n\n"
            output += "\n*使用方式：用「专业文案」帮我写一段关于XX的介绍*"
            return output
        return "暂无可用技能"
    
    elif action == "apply":
        skill_name = params.get("skill_name", "")
        task = params.get("task", user_input)
        
        if not skill_name:
            return "请指定要使用的技能，例如：用「专业文案」写一段产品介绍"
        
        op_result = await apply_skill(skill_name, {"task": task, "content": task})
        if op_result.success:
            return f"## 🎯 技能「{skill_name}」输出\n\n{op_result.output}"
        return op_result.message
    
    elif action == "get":
        skill_name = params.get("skill_name", "")
        op_result = get_skill(skill_name)
        if op_result.success and op_result.skill:
            s = op_result.skill
            return f"## 📖 技能详情: {s.name}\n\n{s.description}\n\n**类别**: {s.category}\n**使用次数**: {s.usage_count}\n\n**提示词模板**:\n```\n{s.prompt_template}\n```"
        return op_result.message
    
    return "无法识别技能操作。试试说：「有哪些技能」「用专业文案帮我写XX」"


# ============== 路由函数 ==============

def route_by_intent(state: ContentProductionState) -> str:
    """根据意图路由到相应节点"""
    target = state.get("route_target", "chat")
    phase_order = state.get("phase_order", PROJECT_PHASES)
    current_phase = state.get("current_phase", phase_order[0] if phase_order else "intent")
    
    # 如果 current_phase 不在 phase_order 中，使用第一个阶段
    if current_phase not in phase_order and phase_order:
        current_phase = phase_order[0]
    
    if target == "phase_current":
        # 保持在当前阶段
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
        # 路由到新的 modify_node（处理 @ 引用字段修改）
        return "modify"
    elif target == "query":
        # 路由到新的 query_node（处理 @ 引用字段查询）
        return "query"
    elif target == "simulate":
        return "phase_simulate"
    elif target == "evaluate":
        return "phase_evaluate"
    elif target == "tool" or target in ("tool_architecture", "tool_outline", "tool_persona", "tool_skill"):
        # 路由到工具节点
        return "tool"
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
    
    # @ 引用相关节点（新增）
    graph.add_node("modify", modify_node)
    graph.add_node("query", query_node)
    
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
    graph.add_node("tool", tool_node)  # 统一工具调用节点
    
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
            # @ 引用节点（新增）
            "modify": "modify",
            "query": "query",
            # 工具节点
            "research": "research",
            "generate_field": "generate_field",
            "read_field": "read_field",
            "update_field": "update_field",
            "tool": "tool",  # 统一工具节点
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
    graph.add_edge("tool", END)  # 统一工具节点
    
    # @ 引用节点到结束
    graph.add_edge("modify", END)
    graph.add_edge("query", END)
    
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
        chat_history: Optional[list] = None,
        phase_status: Optional[dict] = None,
        phase_order: Optional[List[str]] = None,  # 新增：项目实际的阶段顺序
        references: Optional[List[str]] = None,  # @ 引用的字段名
        referenced_contents: Optional[Dict[str, str]] = None,  # 引用字段的内容
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
            phase_order: 项目实际的阶段顺序（灵活架构可能不同于默认）
            references: @ 引用的字段名列表
            referenced_contents: 引用字段的实际内容
        
        Returns:
            最终状态
        """
        # 使用传入的 phase_order，否则使用默认
        actual_phase_order = phase_order if phase_order else PROJECT_PHASES.copy()
        
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
        existing_phase_status = phase_status or {p: "pending" for p in actual_phase_order}
        
        initial_state: ContentProductionState = {
            "project_id": project_id,
            "current_phase": current_phase,
            "phase_order": actual_phase_order,  # 使用项目实际的阶段顺序！
            "phase_status": existing_phase_status,
            "autonomy_settings": autonomy_settings or {p: True for p in actual_phase_order},
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
            # @ 引用相关
            "references": references or [],
            "referenced_contents": referenced_contents or {},
            # 解析后的意图
            "parsed_intent_type": "",
            "parsed_target_field": None,
            "parsed_operation": "",
            # 修改操作目标字段
            "modify_target_field": None,
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

