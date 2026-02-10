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
import re
import json

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from core.ai_client import ai_client, ChatMessage
from core.prompt_engine import prompt_engine, GoldenContext, PromptContext
from core.models import PROJECT_PHASES
from core.models.project_field import ProjectField
from core.tools.architecture_reader import (
    get_project_architecture, 
    format_architecture_for_llm,
    get_field_content,
    get_intent_and_research,
    get_dependency_contents,
)
import json as json_module  # 避免与局部变量冲突


# ============== 辅助函数 ==============

def normalize_intent(raw_intent) -> str:
    """
    将项目意图规范化为字符串格式
    
    意图可能是：
    - 字典 {"做什么": "...", "给谁看": "...", "核心价值": "..."}
    - 字符串
    - None 或空值
    
    返回：格式化的字符串
    """
    if not raw_intent:
        return ""
    
    if isinstance(raw_intent, dict):
        # 转换为结构化的 JSON 字符串
        return json_module.dumps(raw_intent, ensure_ascii=False, indent=2)
    
    return str(raw_intent)


def normalize_consumer_personas(raw_personas) -> str:
    """
    将消费者画像规范化为字符串格式
    
    可能是：
    - JSON 字符串
    - 字典对象
    - None
    """
    if not raw_personas:
        return ""
    
    if isinstance(raw_personas, dict):
        return json_module.dumps(raw_personas, ensure_ascii=False, indent=2)
    
    return str(raw_personas)


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
    
    # 创作者特质（全局注入到每个 LLM 调用）
    creator_profile: str
    
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
    
    # ===== 多意图支持（新增）=====
    # 待处理的意图队列
    pending_intents: List[dict]


# ============== 意图路由 ==============

ROUTE_OPTIONS = Literal[
    "advance_phase",  # 推进到下一阶段
    "generate",       # 生成内容
    "modify",         # 修改内容
    "research",       # 调研
    "generic_research",  # 通用深度调研
    "evaluate",       # 评估
    "query",          # 查询
    "chat",           # 自由对话
]


def _detect_modify_target(user_input: str, references: list) -> str:
    """
    当有多个 @ 引用时，智能识别哪个是修改目标字段。
    
    策略：找到修改类关键词后最近的 @引用 → 那个就是目标。
    若无法判断，退回最后一个引用（自然语言通常把目标放在最后）。
    
    示例:
      "参考 @逐字稿1 修改 @逐字稿2" → 逐字稿2（"修改"后面的引用）
      "修改 @逐字稿2 参考 @逐字稿1" → 逐字稿2（"修改"后面的引用）
      "帮我改一下 @逐字稿1"         → 逐字稿1（单引用直接返回）
    """
    if len(references) <= 1:
        return references[0] if references else ""
    
    import re as _re
    
    # 修改类关键词（按长度降序，避免"改"误匹配"修改"的尾部）
    modify_keywords = ["帮我修改", "帮我改写", "帮我重写", "帮我调整", "帮我更新",
                        "修改", "改写", "重写", "调整", "更新", "改一下", "改成", "改"]
    
    # 构建 引用→位置 映射
    ref_positions = {}
    for ref in references:
        pos = user_input.find(f"@{ref}")
        if pos >= 0:
            ref_positions[ref] = pos
    
    # 找修改关键词后面最近的引用
    best_target = None
    best_distance = float('inf')
    
    for keyword in modify_keywords:
        # 搜索所有出现位置
        start = 0
        while True:
            kw_pos = user_input.find(keyword, start)
            if kw_pos < 0:
                break
            kw_end = kw_pos + len(keyword)
            
            # 找该关键词后面最近的引用
            for ref, ref_pos in ref_positions.items():
                if ref_pos >= kw_pos:  # 引用在关键词之后（或重叠位置）
                    distance = ref_pos - kw_end
                    if 0 <= distance < best_distance:
                        best_distance = distance
                        best_target = ref
            
            start = kw_pos + 1  # 继续搜索下一个位置
    
    if best_target:
        return best_target
    
    # 兜底：返回最后一个引用（自然语言通常把动作对象放在最后）
    return references[-1]


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
    # 通用原则: 用户引用了具体内容并给出指令 → 修改; 只想了解 → 查询
    if references and referenced_contents:
        # 检查是否是查询意图（用户想看/了解引用的内容）
        query_keywords = ["是什么", "什么意思", "解释", "总结", "看看", "分析", "怎么样"]
        if any(kw in user_input for kw in query_keywords):
            target_field = references[0]
            return {
                **state, 
                "route_target": "query",
                "parsed_intent_type": "query",
                "parsed_target_field": target_field,
                "parsed_operation": user_input,
            }
        
        # 默认: @ 引用 + 任何非查询指令 = 修改意图
        # 关键修复：多个 @ 引用时，智能识别哪个是修改目标
        # 例如 "参考 @逐字稿1 修改 @逐字稿2" → 目标是逐字稿2
        target_field = _detect_modify_target(user_input, references)
        print(f"[route_intent] 规则1: @引用 + 指令 → modify, target={target_field}")
        return {
            **state, 
            "route_target": "modify",
            "parsed_intent_type": "modify",
            "parsed_target_field": target_field,
            "parsed_operation": user_input,
        }
    
    # ===== 规则 2 & 3: 已移除硬编码触发词 =====
    # 现在完全依靠 LLM 理解用户意图（规则5）
    # 这样可以正确处理：
    # - "进入外延设计阶段" → advance_phase (而不是 tool_architecture)
    # - "在内涵生产部分补充字段" → tool_architecture
    # 硬编码的问题是无法区分这两种情况
    
    # ===== 规则 4: 意图分析阶段的问答流程（重构：智能判断）=====
    # 关键改进：不再强制锁定，而是智能判断用户是否在回答意图问题
    phase_order = state.get("phase_order", PROJECT_PHASES)
    if "intent" in phase_order and current_phase == "intent" and current_phase_status != "completed":
        chat_history = state.get("messages", [])
        
        # 检查是否有待回答的意图分析问题
        has_pending_question = False
        for m in reversed(chat_history[-10:]):  # 只检查最近10条
            if isinstance(m, AIMessage):
                content = m.content if hasattr(m, 'content') else str(m)
                if "【问题" in content and "/3】" in content:
                    has_pending_question = True
                    break
                # 如果遇到已完成的分析，停止检查
                if "✅ 已生成" in content or ('"做什么"' in content and '"给谁看"' in content):
                    break
        
        # 判断用户输入是否是"问问题"（而非"回答问题"）
        # 问问题的特征：以"？"结尾、包含疑问词、询问 agent 能力等
        question_indicators = ["？", "?", "什么", "怎么", "如何", "能不能", "可以吗", "是不是", "吗？", "呢？", "能做", "有什么", "你是"]
        is_asking_question = any(qi in user_input for qi in question_indicators)
        
        # 只有在有待回答的问题 且 用户不是在问其他问题时，才进入意图分析流程
        if has_pending_question and not is_asking_question:
            print(f"[route_intent] 规则4命中: 用户回答意图问题")
            return {**state, "route_target": "phase_current", "parsed_intent_type": "phase_action"}
        
        # 如果用户是在问问题（比如问 agent 能做什么），则进入 LLM 判断
        if is_asking_question:
            print(f"[route_intent] 规则4跳过: 用户在问问题，交给 LLM 判断")
    
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
当用户提到这些概念时选择：加字段、添加字段、补充字段、新增字段、删字段、加阶段、删阶段、移动、拆分、合并、调整结构、新增模块
例如：
- "帮我加一个新字段" → tool_architecture
- "把这个阶段删掉" → tool_architecture  
- "我想拆分一下内涵设计" → tool_architecture
- "在内容里加一个关键洞察" → tool_architecture
- "在内涵生产部分补充字段" → tool_architecture
- "给内涵设计添加一个字段" → tool_architecture

**重要：区分"添加字段"和"修改字段内容"**
- "在XX阶段加/添加/补充一个字段" → tool_architecture（创建新字段）
- "修改XX字段的内容" → modify（修改已有字段的内容，需要@引用）

### tool_outline - 内容规划
当用户想规划内容结构时选择：设计大纲、内容框架、怎么组织、课程结构、文章架构
例如：
- "帮我设计一下大纲" → tool_outline
- "这个内容怎么组织比较好" → tool_outline

### tool_persona - 人物管理
当用户想管理用户画像/角色时选择：生成人物、创建用户、查看人物、选中、取消选中、补充角色、添加用户、新增人物
例如：
- "再生成一个程序员用户" → tool_persona
- "看看有哪些人物" → tool_persona
- "补充一个角色，22岁应届毕业生" → tool_persona
- "添加一个新用户画像" → tool_persona

### tool_skill - 技能使用
当用户想用特定风格/技能时选择：用专业方式、用故事化方式、简化内容、批判分析、有什么技能
例如：
- "用专业的方式帮我写" → tool_skill
- "有什么技能可以用" → tool_skill

## 阶段流转意图（非常重要！优先判断）

### advance_phase - 进入下一阶段或指定阶段
当用户想推进项目进度、进入某个阶段时选择。
例如：
- "进入下一阶段" → advance_phase
- "继续" / "下一步" → advance_phase
- "开始外延设计" / "进入外延设计阶段" → advance_phase (target: "design_outer")
- "开始消费者调研" → advance_phase (target: "research")
- "可以了，进入下一步" → advance_phase

**关键区分**：
- "进入XX阶段" → advance_phase（推进流程）
- "在XX阶段添加字段" → tool_architecture（修改结构）

### phase_action - 执行当前阶段
当用户想在当前阶段执行操作时选择。
例如：
- "开始" / "开始吧" / "执行" → phase_action
- "开始生成" → phase_action

## 其他意图类型
- modify: 修改已有字段内容（配合@引用）
- query: 查询信息（有哪些阶段、当前进度等）
- generate: 生成字段内容
- research: 执行消费者调研阶段（仅当用户明确要做消费者调研/用户调研时）
- generic_research: 用户要求对某个主题做深度调研/资料搜集（非消费者调研，比如"帮我调研一下X市场"、"帮我查一下Y的资料"、"对Z做个调研"）
- evaluate: 执行评估阶段
- **chat**: 当用户在闲聊、询问 agent 能力、问通用问题时选择

**关键区分 research vs generic_research**:
- "开始消费者调研" / "做用户调研" → research（消费者调研阶段）
- "帮我调研一下X" / "搜索一下Y的资料" / "帮我查一下Z" → generic_research（通用深度调研，结果以标准字段呈现）

## chat 意图示例（重要！这些必须路由到 chat）
- "你能做什么？" → chat
- "你是谁？" → chat
- "帮我解释一下这个系统" → chat
- "作为 agent 你有什么能力？" → chat
- "hello" / "你好" → chat
- 任何询问性的问题（不涉及具体操作）→ chat

## 复合意图处理（非常重要！）
用户的一句话可能包含多个意图，你必须**全部识别**并按**正确的执行顺序**排列。

例如：
- "清空外延设计的所有字段，重新开展外延设计" → 两个意图：
  1. tool_architecture（删除 design_outer 的字段）
  2. advance_phase（重新开始 design_outer）
- "删掉这个字段，然后帮我生成一个新的" → 两个意图：
  1. tool_architecture（删除字段）
  2. generate（生成内容）
- "先调研一下，再生成内容" → 两个意图：
  1. research
  2. generate

## 输出格式（JSON）
如果只有一个意图：
{{"intents": [{{"type": "意图类型", "target": "目标对象", "operation": "操作描述"}}]}}

如果有多个意图，按执行顺序排列：
{{"intents": [
  {{"type": "第一个意图", "target": "目标1", "operation": "描述1"}},
  {{"type": "第二个意图", "target": "目标2", "operation": "描述2"}}
]}}

只输出JSON。"""
        ),
        ChatMessage(role="user", content=user_input),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.3)
    
    # 解析 JSON 响应 - 支持多意图列表
    import json
    intents_list = []
    try:
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content)
        
        # 新格式：intents 列表
        if "intents" in result and isinstance(result["intents"], list):
            intents_list = result["intents"]
            print(f"[route_intent] LLM返回 {len(intents_list)} 个意图")
        # 兼容旧格式：单个意图
        elif "intent" in result:
            intents_list = [{
                "type": result.get("intent", "chat"),
                "target": result.get("target", ""),
                "operation": result.get("operation", user_input)
            }]
        else:
            intents_list = [{"type": "chat", "target": "", "operation": user_input}]
            
    except Exception as e:
        print(f"[route_intent] JSON解析失败: {e}, 原始响应: {response.content[:200]}")
        intents_list = [{"type": "chat", "target": "", "operation": user_input}]
    
    # 取第一个意图作为当前意图，其余放入 pending_intents
    current_intent = intents_list[0] if intents_list else {"type": "chat", "target": "", "operation": user_input}
    pending_intents = intents_list[1:] if len(intents_list) > 1 else []
    
    intent = current_intent.get("type", "chat")
    target = current_intent.get("target", "")
    operation = current_intent.get("operation", user_input)
    print(f"[route_intent] 当前意图: {intent}, target={target}, 待处理意图: {len(pending_intents)} 个")
    
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
        "generic_research": "generic_research",
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
    
    # 标准化 pending_intents 中的意图类型
    normalized_pending = []
    for pi in pending_intents:
        pi_type = intent_mapping.get(pi.get("type", "chat"), "chat")
        normalized_pending.append({
            "type": pi_type,
            "target": pi.get("target", ""),
            "operation": pi.get("operation", "")
        })
    
    return {
        **state, 
        "route_target": route_target,
        "parsed_intent_type": intent,
        "parsed_target_field": target_field,
        "parsed_operation": operation,
        "pending_intents": normalized_pending,  # 新增：待处理的意图列表
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
    creator_profile = state.get("creator_profile", "")
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
{creator_profile}

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
        
        # 构建简洁的确认消息（实际内容保存到字段）
        # 注意：意图分析结果通过 agent_output 保存到 ProjectField
        # 后续阶段通过字段依赖获取，不再存入全局 golden_context
        confirm_message = "✅ 已生成【意图分析】，请在左侧工作台查看。输入「继续」进入消费者调研阶段。"
        
        return {
            **state,
            "agent_output": response.content,  # 完整内容用于保存字段
            "display_output": confirm_message,  # 对话区显示简洁确认
            "messages": [AIMessage(content=confirm_message)],
            "phase_status": new_phase_status,
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
    
    creator_profile = state.get("creator_profile", "")
    project_id = state.get("project_id", "")
    use_deep = state.get("use_deep_research", True)
    
    # 从字段获取意图分析结果（通过字段依赖，而非 golden_context）
    deps = get_intent_and_research(project_id)
    intent = deps.get("intent", "")
    
    if not intent:
        # fallback：使用用户输入（这不应该发生，意图分析应该先完成）
        intent = state.get("user_input", "")
        print(f"[research_node] 警告：未找到项目意图，使用用户输入: {intent[:50]}...")
    
    print(f"[research_node] 获取到意图分析结果 ({len(intent)} 字符): {intent[:200]}...")
    
    # 从意图中提取简洁的调研主题（不嵌入完整 intent，避免在 synthesize_report 中重复）
    # intent 格式: "**做什么**: ...\n**给谁看**: ...\n**核心价值**: ..."
    import re as _re
    _do_match = _re.search(r"\*\*做什么\*\*[:：]\s*(.+?)(?:\n|$)", intent)
    if _do_match:
        # 从 "做什么" 提取核心主题（截取前80字，保持简洁）
        topic = _do_match.group(1).strip()[:80]
        query = f"目标用户调研: {topic}"
    elif intent:
        query = f"目标用户调研: {intent[:80]}"
    else:
        query = "消费者调研"
    
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
            "search_queries": report.search_queries if hasattr(report, 'search_queries') else [],
            "is_deep_research": use_deep,
        }
        
        # JSON格式存储（给中间栏字段用）
        report_content = json.dumps(report_json, ensure_ascii=False, indent=2)
        
        # 简洁展示文本（给右侧对话区）
        display_text = f"✅ 已生成消费者调研报告，请在左侧工作台查看。\n\n"
        display_text += f"**总体概述**: {report.summary[:100]}...\n\n"
        display_text += f"**典型用户**: {', '.join([p['name'] for p in personas_data[:3]])}"
        
        # 注意：消费者调研结果通过 agent_output 保存到 ProjectField
        # 后续阶段通过字段依赖获取，不再存入全局 golden_context
        
        # 构建 full_prompt 用于日志 - 记录完整上下文
        full_prompt = f"""[消费者调研 - 完整上下文]

=== 1. 调研参数 ===
查询主题: {query}
使用深度调研: {use_deep}

=== 2. 创作者特质 ===
{creator_profile or '未设置'}

=== 3. 项目意图 (完整) ===
{intent if intent else '未设置'}

=== 4. DeepResearch 流程 ===
步骤1: 规划搜索查询 (LLM生成3-5个搜索词)
步骤2: Tavily Search API 搜索+内容提取 (每个查询5条结果)
步骤3: 综合分析生成报告 (含引用标注)

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
    
    creator_profile = state.get("creator_profile", "")
    project_id = state.get("project_id", "")
    
    # 从字段获取依赖内容（意图分析、消费者调研）
    deps = get_intent_and_research(project_id)
    intent_str = normalize_intent(deps.get("intent", ""))
    personas_str = normalize_consumer_personas(deps.get("research", ""))
    
    # 获取用户的设计偏好（如果有）
    design_preference = ""
    try:
        from core.database import get_session_maker
        SessionLocal = get_session_maker()
        with SessionLocal() as _db:
            pref_field = _db.query(ProjectField).filter(
                ProjectField.project_id == project_id,
                ProjectField.phase == "design_inner",
                ProjectField.name == "设计偏好",
            ).first()
            if pref_field and pref_field.content:
                design_preference = pref_field.content.strip()
    except Exception as e:
        print(f"[design_inner] 读取设计偏好失败: {e}")
    
    # 构建依赖内容（作为参考内容注入，而非全局上下文）
    field_context = ""
    if intent_str:
        field_context += f"## 项目意图\n{intent_str}\n\n"
    if personas_str:
        field_context += f"## 目标用户画像\n{personas_str}\n\n"
    if design_preference:
        field_context += f"## 用户的设计偏好\n{design_preference}\n\n"
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=creator_profile,
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["design_inner"],
        field_context=field_context.strip(),  # 依赖内容作为参考
    )
    
    system_prompt = context.to_system_prompt()
    
    # 注意：Golden Context（项目意图、消费者画像）已经在 system_prompt 中
    # user_prompt 只需要发出任务指令
    pref_instruction = ""
    if design_preference:
        pref_instruction = f"\n\n用户特别要求：{design_preference}\n请确保3个方案都充分考虑用户的设计偏好。"
    
    user_prompt = f"""请基于上述项目意图和消费者画像，设计3个内容生产方案。{pref_instruction}

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
    creator_profile = state.get("creator_profile", "")
    project_id = state.get("project_id", "")
    user_input = state.get("user_input", "请生产内涵内容。")
    
    # 从字段获取依赖内容（意图分析、消费者调研）
    deps = get_intent_and_research(project_id)
    intent_str = normalize_intent(deps.get("intent", ""))
    personas_str = normalize_consumer_personas(deps.get("research", ""))
    
    field_context = ""
    if intent_str:
        field_context += f"## 项目意图\n{intent_str}\n\n"
    if personas_str:
        field_context += f"## 目标用户画像\n{personas_str}\n\n"
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=creator_profile,
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["produce_inner"],
        field_context=field_context.strip(),
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
    """
    外延设计节点
    
    类似内涵设计，生成多个渠道方案供用户选择。
    每个渠道是一个独立的字段，用户可以选择/增删渠道。
    """
    creator_profile = state.get("creator_profile", "")
    project_id = state.get("project_id", "")
    
    # 从字段获取依赖内容
    deps = get_intent_and_research(project_id)
    intent_str = normalize_intent(deps.get("intent", ""))
    personas_str = normalize_consumer_personas(deps.get("research", ""))
    
    field_context = ""
    if intent_str:
        field_context += f"## 项目意图\n{intent_str}\n\n"
    if personas_str:
        field_context += f"## 目标用户画像\n{personas_str}\n\n"
    
    # 外延设计的系统提示词
    system_prompt = f"""你是一个专业的内容传播策略师。

{creator_profile}

{field_context}

你的任务是为这个内容项目推荐适合的传播渠道。"""

    # 用户提示词：生成渠道方案
    user_prompt = """请推荐5-8个适合的传播渠道，每个渠道包含：
1. 渠道名称（如：小红书、抖音、公众号、知乎、B站等）
2. 适合原因（1-2句话，为什么这个项目适合这个渠道）
3. 内容形式建议（该渠道适合的内容形式，如：短视频、图文、长文等）

请输出严格的JSON格式（不要添加```json标记）：
{
    "channels": [
        {
            "id": "channel_1",
            "name": "渠道名称",
            "reason": "为什么适合（1-2句话）",
            "content_form": "建议的内容形式",
            "priority": "high/medium/low"
        }
    ],
    "summary": "一句话概括传播策略方向"
}"""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    raw_output = response.content
    
    # 解析JSON
    json_content = raw_output
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw_output)
    if json_match:
        json_content = json_match.group(1)
    
    try:
        channels_data = json.loads(json_content)
    except json.JSONDecodeError:
        channels_data = {
            "channels": [],
            "error": "AI输出格式错误，请重试"
        }
    
    # 存储结构化JSON
    output_content = json.dumps(channels_data, ensure_ascii=False, indent=2)
    
    # 构建简洁的展示文本
    display_text = "✅ 已生成渠道方案，请在左侧工作台查看并选择要使用的渠道。\n\n"
    if "channels" in channels_data and channels_data["channels"]:
        for ch in channels_data["channels"][:8]:
            priority_icon = "🔴" if ch.get("priority") == "high" else "🟡" if ch.get("priority") == "medium" else "⚪"
            display_text += f"{priority_icon} **{ch.get('name', '未命名')}**：{ch.get('reason', '')[:50]}\n"
    if channels_data.get("summary"):
        display_text += f"\n📌 {channels_data['summary']}"
    
    full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{user_prompt}"
    
    return {
        **state,
        "agent_output": output_content,  # JSON格式，存入字段
        "display_output": display_text,   # 简洁展示
        "messages": [AIMessage(content=display_text)],
        "phase_status": {**state.get("phase_status", {}), "design_outer": "in_progress"},
        "current_phase": "design_outer",
        "is_producing": True,
        "waiting_for_human": True,  # 需要用户选择渠道
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
        "full_prompt": full_prompt,
    }


async def produce_outer_node(state: ContentProductionState) -> ContentProductionState:
    """外延生产节点"""
    creator_profile = state.get("creator_profile", "")
    project_id = state.get("project_id", "")
    user_input = state.get("user_input", "请生产外延内容。")
    
    # 从字段获取依赖内容
    deps = get_intent_and_research(project_id)
    intent_str = normalize_intent(deps.get("intent", ""))
    personas_str = normalize_consumer_personas(deps.get("research", ""))
    
    field_context = ""
    if intent_str:
        field_context += f"## 项目意图\n{intent_str}\n\n"
    if personas_str:
        field_context += f"## 目标用户画像\n{personas_str}\n\n"
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=creator_profile,
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["produce_outer"],
        field_context=field_context.strip(),
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


async def evaluate_node(state: ContentProductionState) -> ContentProductionState:
    """评估节点"""
    creator_profile = state.get("creator_profile", "")
    project_id = state.get("project_id", "")
    user_input = "请对项目进行全面评估。"
    
    # 从字段获取依赖内容
    deps = get_intent_and_research(project_id)
    intent_str = normalize_intent(deps.get("intent", ""))
    personas_str = normalize_consumer_personas(deps.get("research", ""))
    
    field_context = ""
    if intent_str:
        field_context += f"## 项目意图\n{intent_str}\n\n"
    if personas_str:
        field_context += f"## 目标用户画像\n{personas_str}\n\n"
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=creator_profile,
        ),
        phase_context=prompt_engine.PHASE_PROMPTS["evaluate"],
        field_context=field_context.strip(),
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
    creator_profile = state.get("creator_profile", "")
    project_id = state.get("project_id", "")
    target_field = state.get("parsed_target_field", "")
    operation = state.get("parsed_operation", "")
    referenced_contents = state.get("referenced_contents", {})
    
    # 获取目标字段的原始内容
    original_content = referenced_contents.get(target_field, "")
    user_input = state.get("user_input", "")
    
    # 如果引用中没有找到，尝试直接从数据库查找（支持用户直接输入字段名而不用 @）
    if not original_content and target_field and project_id:
        try:
            field_data = get_field_content(project_id, target_field)
            if field_data and field_data.get("content"):
                original_content = field_data["content"]
                referenced_contents[target_field] = original_content
                print(f"[modify_node] 通过数据库直接查找到字段: {target_field}")
        except Exception as e:
            print(f"[modify_node] 查找字段失败: {e}")
    
    if not original_content:
        # 列出所有可用的字段名（同时搜索 ProjectField 和 ContentBlock）
        all_available = list(referenced_contents.keys())
        try:
            from core.database import get_db
            from core.models import ProjectField
            db = next(get_db())
            # 搜索 ProjectField
            pf_names = [f.name for f in db.query(ProjectField).filter(
                ProjectField.project_id == project_id
            ).all() if f.content and f.content.strip()]
            # 搜索 ContentBlock
            from core.models.content_block import ContentBlock
            cb_names = [b.name for b in db.query(ContentBlock).filter(
                ContentBlock.project_id == project_id,
                ContentBlock.block_type == "field",
                ContentBlock.deleted_at == None,
            ).all() if b.content and b.content.strip()]
            all_available = list(set(pf_names + cb_names))
        except Exception:
            pass
        
        references = state.get("references", [])
        debug_prompt = f"""[modify_node 失败调试信息]
目标字段: {target_field}
用户输入: {user_input}
引用解析: {references}
可用字段: {all_available}

解析操作: {operation}
当前阶段: {state.get('current_phase', 'unknown')}
"""
        return {
            **state,
            "agent_output": f"未找到字段「{target_field}」的内容，无法修改。\n\n可用字段: {all_available}",
            "is_producing": False,
            "waiting_for_human": False,
            "full_prompt": debug_prompt,
        }
    
    # 从字段获取依赖内容
    deps = get_intent_and_research(project_id)
    intent_str = normalize_intent(deps.get("intent", ""))
    
    # 检测原始内容是否是 JSON（例如方案结构）
    is_json_content = False
    try:
        json_module.loads(original_content)
        is_json_content = True
    except (json_module.JSONDecodeError, TypeError):
        pass
    
    format_hint = ""
    if is_json_content:
        format_hint = "\n5. 原始内容是 JSON 结构，请输出修改后的完整 JSON（不要用 markdown 代码块包裹）"
    
    # 构建参考内容（其他 @ 引用的字段，不包括目标字段本身）
    reference_section = ""
    other_refs = {name: content for name, content in referenced_contents.items()
                  if name != target_field and content}
    if other_refs:
        ref_parts = []
        for name, content in other_refs.items():
            ref_parts.append(f"### 参考字段「{name}」:\n{content}")
        reference_section = "\n\n参考内容（用户指定的参考材料）:\n" + "\n\n".join(ref_parts)
    
    # 构建修改提示词
    system_prompt = f"""你是一个专业的内容编辑。请根据用户的修改指令，对原始内容进行修改。

项目上下文:
{creator_profile}
{intent_str}

原始内容（字段名：{target_field}）:
{original_content}{reference_section}

规则：
1. 严格按照用户的修改指令进行修改
2. 保持内容的专业性和一致性
3. 只输出修改后的完整内容，不要添加任何解释
4. 保持原有的格式风格{format_hint}

Markdown 格式硬性要求（如输出包含表格，必须严格遵守）：
- 表格每一行的列数（| 的数量）必须与表头完全一致，绝对不能多也不能少
- 如果一个单元格内需要放置多条内容，请在单元格内部使用 <br> 换行或数字编号（1. 2. 3.），不要用 | 增加列
- 表格必须有表头分隔行（如 | --- | --- | --- |）
- 表格每行必须以 | 开头、以 | 结尾
- 示例：在一个单元格中放多条场景的正确写法：| 场景1描述 <br> 场景2描述 <br> 场景3描述 |"""

    # 关键修复：使用用户真实输入作为 user message，而非硬编码模板
    # 之前 "请修改「逐字稿1」的内容" 会传错目标（取了 references[0]），
    # 现在直接传用户原始指令如 "参考 @逐字稿1 修改 @逐字稿2"
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_input),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.5)
    modified_content = response.content
    
    # 构建完整 prompt 用于日志记录
    full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{user_input}"
    
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
        "full_prompt": full_prompt,
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
    creator_profile = state.get("creator_profile", "")
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
    
    # 从字段获取依赖内容
    deps = get_intent_and_research(project_id)
    intent_str = normalize_intent(deps.get("intent", ""))
    
    system_prompt = f"""你是一个专业的内容分析师。请根据用户的问题，分析和解释已有的内容或项目结构。

项目上下文:
{creator_profile}
{intent_str}{arch_info}

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
    
    # 构建完整 prompt 用于日志记录
    full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{operation}"
    
    return {
        **state,
        "agent_output": response.content,
        "is_producing": False,  # 查询不产出新内容
        "waiting_for_human": False,
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
        "cost": response.cost,
        "full_prompt": full_prompt,
    }


async def chat_node(state: ContentProductionState) -> ContentProductionState:
    """
    自由对话节点（重构版）
    
    处理自由对话，注入 @ 引用的内容
    """
    creator_profile = state.get("creator_profile", "")
    project_id = state.get("project_id", "")
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
    
    # 从字段获取依赖内容
    deps = get_intent_and_research(project_id)
    intent_str = normalize_intent(deps.get("intent", ""))
    
    # 构建对话上下文
    current_phase = state.get('current_phase', 'intent')
    system_prompt = f"""你是一个智能的内容生产 Agent。当前正在帮助用户进行内容生产项目。

## 我的能力
1. **意图分析**: 通过 3 个问题帮你明确内容目标（做什么、给谁看、期望行动）
2. **消费者调研**: 使用 DeepResearch 深度分析目标用户画像和痛点
3. **内涵设计**: 规划内容的核心结构和字段
4. **内涵生产**: 根据设计方案生成具体内容
5. **外延设计/生产**: 产出营销和触达相关内容
6. **消费者模拟**: 模拟用户与内容交互，获取反馈
7. **评估**: 多维度评估内容质量

## 可用工具
- **架构操作**: 添加/删除/移动字段和阶段
- **大纲生成**: 帮你规划内容结构
- **人物管理**: 生成和管理用户画像
- **技能应用**: 使用不同写作风格

## 项目上下文
{creator_profile or '（暂无创作者信息）'}
{intent_str or '（暂无项目意图）'}

当前阶段: {current_phase}{ref_context}

请友好地回答用户的问题。如果用户询问你能做什么，请简洁介绍你的能力。"""
    
    messages = [ChatMessage(role="system", content=system_prompt)]
    
    # 添加历史消息
    for msg in history[-10:]:  # 只取最近10条
        if isinstance(msg, HumanMessage):
            messages.append(ChatMessage(role="user", content=msg.content))
        elif isinstance(msg, AIMessage):
            messages.append(ChatMessage(role="assistant", content=msg.content))
    
    # 添加当前输入
    user_input = state.get("user_input", "")
    messages.append(ChatMessage(role="user", content=user_input))
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    
    # 构建完整的 prompt 用于日志记录
    full_prompt = f"[System]\n{system_prompt}\n\n"
    for msg in messages[1:-1]:  # 跳过 system 和最后的 user
        full_prompt += f"[{msg.role}]\n{msg.content}\n\n"
    full_prompt += f"[User]\n{user_input}"
    
    return {
        **state,
        "agent_output": response.content,
        "messages": [AIMessage(content=response.content)],
        "is_producing": False,  # 对话模式不保存为字段
        "full_prompt": full_prompt,  # 记录完整 prompt
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
    
    creator_profile = state.get("creator_profile", "")
    project_id = state.get("project_id", "")
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
        "evaluate": "项目评估报告",
    }
    field_name = field_names.get(current_phase, "内容")
    
    # 从字段获取依赖内容
    deps = get_intent_and_research(project_id)
    intent_str = normalize_intent(deps.get("intent", ""))
    personas_str = normalize_consumer_personas(deps.get("research", ""))
    
    field_context = ""
    if intent_str:
        field_context += f"## 项目意图\n{intent_str}\n\n"
    if personas_str:
        field_context += f"## 目标用户画像\n{personas_str}\n\n"
    
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=creator_profile,
        ),
        phase_context=prompt_engine.PHASE_PROMPTS.get(current_phase, ""),
        field_context=field_context.strip(),
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
    creator_profile = state.get("creator_profile", "")
    user_input = state.get("user_input", "")
    
    # 创作者特质作为唯一的全局上下文
    context = PromptContext(
        golden_context=GoldenContext(
            creator_profile=creator_profile,
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
    full_prompt = f"[Tool Node]\n工具类型: {intent_type}\n用户输入: {user_input}\n"
    
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
        
        full_prompt += f"\n工具输出:\n{output}"
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        output = f"工具执行错误: {str(e)}\n\n```\n{error_trace}\n```"
        full_prompt += f"\n错误:\n{error_trace}"
    
    return {
        **state,
        "agent_output": output,
        "messages": [AIMessage(content=output)],
        "is_producing": False,
        "full_prompt": full_prompt,  # 记录完整的工具调用信息
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

## 阶段代码映射（重要！用户说中文名，你要转成代码）
- intent = 意图分析
- research = 消费者调研
- design_inner = 内涵设计
- produce_inner = 内涵生产 / 生产内涵 / 内容生产
- design_outer = 外延设计
- produce_outer = 外延生产
- simulate = 消费者模拟
- evaluate = 评估

## 用户请求
{user_input}

## 输出格式（JSON）
{{"action": "操作名", "params": {{参数对象}}}}

## 解析规则
1. 用户说"在XX阶段补充/添加字段"→ action="add_field", params.phase=阶段代码
2. 如果用户没说具体字段名，根据上下文生成一个合理的字段名
3. 如果实在无法推断字段名，使用"待命名字段"

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
        print(f"[_llm_handle_architecture] 解析结果: action={action}, params={params}")
    except Exception as parse_error:
        debug_info = f"""[架构操作解析失败]
用户输入: {user_input}
LLM原始响应: {response.content[:500]}
解析错误: {str(parse_error)}"""
        print(debug_info)
        return f"无法解析操作请求。请尝试更明确的描述，例如：\n- 在内涵生产阶段添加一个「核心论点」字段\n- 删除「意图分析」阶段\n\n（调试: LLM响应为 {response.content[:100]}...）"
    
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
        phase = params.get("phase", "produce_inner")
        name = params.get("name", "新字段")
        ai_prompt = params.get("ai_prompt", "")
        print(f"[add_field] phase={phase}, name={name}")
        op_result = add_field(
            project_id,
            phase,
            name,
            ai_prompt,
        )
        if op_result.success:
            return f"✅ {op_result.message}\n\n已在「{phase}」阶段添加字段「{name}」，请刷新页面查看。"
        else:
            return f"❌ {op_result.message}\n\n（尝试添加: phase={phase}, name={name}）"
    
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
            # 使用 LLM 生成自然的回复
            summary_prompt = f"""用一句话自然地告诉用户你完成了什么任务。

用户请求: {user_input}
完成结果: 成功创建了人物「{p.name}」，{p.basic_info.get('age', '')}岁，{p.basic_info.get('occupation', '')}

要求：
- 用友好、口语化的语气
- 提到人物姓名和关键特征
- 提醒用户可以在左侧工作台查看
- 不要用模板化的格式，要自然

只输出这一句话。"""
            
            summary_messages = [ChatMessage(role="user", content=summary_prompt)]
            summary_response = await ai_client.async_chat(summary_messages, temperature=0.8)
            natural_reply = summary_response.content.strip()
            
            # 附带详细信息
            detail = f"\n\n---\n**{p.name}**\n- 背景: {p.background[:150]}...\n- 核心痛点: {', '.join(p.pain_points[:2])}"
            
            return natural_reply + detail
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
    target_field = state.get("parsed_target_field", "")  # 可能包含目标阶段
    
    # 如果 current_phase 不在 phase_order 中，使用第一个阶段
    if current_phase not in phase_order and phase_order:
        current_phase = phase_order[0]
    
    if target == "phase_current":
        # 保持在当前阶段
        return f"phase_{current_phase}"
    elif target == "advance_phase":
        # 推进阶段：可能指定了目标阶段，也可能是下一阶段
        # 先检查是否指定了具体阶段（如 "进入外延设计阶段"）
        if target_field:
            # 阶段名称映射
            phase_name_map = {
                "intent": "intent", "意图分析": "intent", "意图": "intent",
                "research": "research", "消费者调研": "research", "调研": "research",
                "design_inner": "design_inner", "内涵设计": "design_inner",
                "produce_inner": "produce_inner", "内涵生产": "produce_inner",
                "design_outer": "design_outer", "外延设计": "design_outer",
                "produce_outer": "produce_outer", "外延生产": "produce_outer",
                "simulate": "evaluate", "消费者模拟": "evaluate", "模拟": "evaluate",
                "evaluate": "evaluate", "评估": "evaluate",
            }
            target_phase = phase_name_map.get(target_field.lower().strip(), "")
            if target_phase and target_phase in phase_order:
                print(f"[route_by_intent] 跳转到指定阶段: {target_phase}")
                return f"phase_{target_phase}"
        
        # 没有指定目标阶段，推进到下一阶段
        try:
            idx = phase_order.index(current_phase)
            if idx < len(phase_order) - 1:
                next_phase = phase_order[idx + 1]
                print(f"[route_by_intent] 推进到下一阶段: {next_phase}")
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
    # ===== 先检查是否有待处理的意图 =====
    pending = state.get("pending_intents", [])
    if pending:
        print(f"[route_after_phase] 检测到 {len(pending)} 个待处理意图，继续执行")
        return "continue_pending"
    
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


def route_after_tool(state: ContentProductionState) -> str:
    """
    工具执行完成后的路由
    
    检查是否有待处理的意图（多意图顺序执行）
    """
    pending = state.get("pending_intents", [])
    
    if pending:
        print(f"[route_after_tool] 检测到 {len(pending)} 个待处理意图，继续执行")
        return "continue_pending"
    else:
        return END


async def continue_pending_node(state: ContentProductionState) -> ContentProductionState:
    """
    处理待处理意图的节点
    
    从 pending_intents 中取出第一个，设置为当前意图，
    然后重新路由
    """
    pending = state.get("pending_intents", [])
    
    if not pending:
        return {**state, "route_target": "chat"}
    
    # 取出第一个待处理意图
    next_intent = pending[0]
    remaining = pending[1:]
    
    intent_type = next_intent.get("type", "chat")
    target = next_intent.get("target", "")
    operation = next_intent.get("operation", "")
    
    print(f"[continue_pending] 处理下一个意图: type={intent_type}, target={target}")
    
    # 确定路由目标
    if intent_type.startswith("tool_"):
        route_target = intent_type
    elif intent_type == "phase_action":
        route_target = "phase_current"
    elif intent_type == "advance_phase":
        route_target = "advance_phase"
    else:
        route_target = intent_type
    
    return {
        **state,
        "route_target": route_target,
        "parsed_intent_type": intent_type,
        "parsed_target_field": target,
        "parsed_operation": operation,
        "pending_intents": remaining,  # 更新剩余待处理意图
    }


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
    graph.add_node("phase_evaluate", evaluate_node)
    
    # 工具节点（设计文档中的 Tools）
    graph.add_node("generate_field", generate_field_node)
    graph.add_node("read_field", read_field_node)
    graph.add_node("update_field", update_field_node)
    graph.add_node("tool", tool_node)  # 统一工具调用节点
    
    # 等待人工确认节点（实际上只是返回状态）
    graph.add_node("wait_human", lambda s: {**s, "waiting_for_human": True})
    
    # 多意图处理节点（新增）
    graph.add_node("continue_pending", continue_pending_node)
    
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
    phase_routing_map = {
        "wait_human": "wait_human", 
        "continue_pending": "continue_pending",  # 新增：多意图处理
        END: END
    }
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
    
    # 工具节点使用条件边（支持多意图顺序执行）
    tool_routing_map = {"continue_pending": "continue_pending", END: END}
    graph.add_conditional_edges("tool", route_after_tool, tool_routing_map)
    graph.add_conditional_edges("generate_field", route_after_tool, tool_routing_map)
    graph.add_conditional_edges("read_field", route_after_tool, tool_routing_map)
    graph.add_conditional_edges("update_field", route_after_tool, tool_routing_map)
    
    # @ 引用节点使用条件边（支持多意图）
    graph.add_conditional_edges("modify", route_after_tool, tool_routing_map)
    graph.add_conditional_edges("query", route_after_tool, tool_routing_map)
    
    # 从chat到结束（chat 不触发后续意图）
    graph.add_edge("chat", END)
    
    # 从等待到结束（用户会在这里继续）
    graph.add_edge("wait_human", END)
    
    # continue_pending 节点 -> 重新路由到下一个意图
    graph.add_conditional_edges(
        "continue_pending",
        route_by_intent,
        {
            # 阶段节点
            "phase_intent": "phase_intent",
            "phase_research": "phase_research",
            "phase_design_inner": "phase_design_inner",
            "phase_produce_inner": "phase_produce_inner",
            "phase_design_outer": "phase_design_outer",
            "phase_produce_outer": "phase_produce_outer",
            "phase_evaluate": "phase_evaluate",
            # @ 引用节点
            "modify": "modify",
            "query": "query",
            # 工具节点
            "research": "research",
            "generate_field": "generate_field",
            "read_field": "read_field",
            "update_field": "update_field",
            "tool": "tool",
            # 对话节点
            "chat": "chat",
        }
    )
    
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
        creator_profile: str = "",  # 重构：用 creator_profile 替代 golden_context
        autonomy_settings: Optional[dict] = None,
        use_deep_research: bool = True,
        thread_id: Optional[str] = None,
        chat_history: Optional[list] = None,
        phase_status: Optional[dict] = None,
        phase_order: Optional[List[str]] = None,  # 项目实际的阶段顺序
        references: Optional[List[str]] = None,  # @ 引用的字段名
        referenced_contents: Optional[Dict[str, str]] = None,  # 引用字段的内容
    ) -> ContentProductionState:
        """
        运行Agent
        
        Args:
            project_id: 项目ID
            user_input: 用户输入
            current_phase: 当前阶段
            creator_profile: 创作者特质（全局注入到每个 LLM 调用）
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
        
        # 构建消息历史（兼容两种格式：字典 或 LangChain Message 对象）
        messages = []
        if chat_history:
            for msg in chat_history:
                # 如果是 LangChain Message 对象
                if isinstance(msg, (HumanMessage, AIMessage)):
                    messages.append(msg)
                # 如果是字典格式
                elif isinstance(msg, dict):
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
            "creator_profile": creator_profile,  # 创作者特质是唯一的全局上下文
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
            # 多意图支持
            "pending_intents": [],
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
            "creator_profile": kwargs.get("creator_profile", ""),  # 创作者特质
            "fields": {},
            "messages": [HumanMessage(content=user_input)],
            "user_input": user_input,
            "agent_output": "",
            "waiting_for_human": False,
            "route_target": "",
            "use_deep_research": kwargs.get("use_deep_research", True),
            "is_producing": False,
            "error": None,
            # 多意图支持
            "pending_intents": [],
        }
        
        config = {"configurable": {"thread_id": kwargs.get("thread_id", project_id)}}
        
        async for event in self.graph.astream(initial_state, config):
            yield event


# 单例
content_agent = ContentProductionAgent()

