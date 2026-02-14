# backend/core/orchestrator.py
# 功能: LangGraph Agent 核心编排器（重写版）
# 架构: Custom StateGraph + Tool Calling
# 主要导出: agent_graph, AgentState, build_system_prompt
# 设计原则:
#   1. LLM 通过 bind_tools 自动选择工具（不再手动 if/elif 路由）
#   2. State 只保留 4 个字段（messages + 3 个上下文）
#   3. 所有 DB 操作在 @tool 函数内完成，不通过 State 传递
#   4. Checkpointer (SqliteSaver) 跨请求/跨重启保持对话状态（含 ToolMessage）
#   5. trim_messages 管理 context window，防止超限

"""
LangGraph Agent 核心编排器

架构：
    agent_node ──(有tool_calls)──→ tool_node ──→ agent_node（循环）
        │
        └──(无tool_calls)──→ END

核心思想：
- 一个 system prompt 定义 Agent 的全部行为规则
- @tool docstrings 告诉 LLM 每个工具何时使用
- LLM 自主决定：直接回复 or 调用工具
- 不再需要手动意图分类 + if/elif 路由
"""


import logging
import operator
from typing import TypedDict, Annotated, Optional, List, Dict

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage,
)
from langchain_core.runnables import RunnableConfig

from core.llm import llm
from core.agent_tools import AGENT_TOOLS

logger = logging.getLogger("orchestrator")


# P3-1e: normalize_intent() 和 normalize_consumer_personas() 已删除（无调用方）


# ============== State 定义 ==============

class AgentState(TypedDict):
    """
    Agent 状态（精简版）。

    只保留 LangGraph 运转必需的字段：
    - messages: 对话历史（LangGraph 核心，包含 Human/AI/Tool Messages）
    - project_id: 项目 ID（传递给工具，通过 configurable）
    - current_phase: 当前组（注入到 system prompt）
    - creator_profile: 创作者画像（注入到 system prompt）

    设计原则：
    - DB 操作在 @tool 函数内完成，不通过 State 传递
    - field_updated / is_producing 等信息从 tool_end 事件推断
    - phase_order / phase_status 在 @tool 函数内从 DB 读取
    """
    messages: Annotated[list[BaseMessage], operator.add]
    project_id: str
    current_phase: str
    creator_profile: str


# ============== System Prompt 构建 ==============

def build_system_prompt(state: AgentState) -> str:
    """
    构建 system prompt — Agent 行为的「宪法」。

    设计原则（以终为始）：
    - 取代原 route_intent() 中的 5000 字意图分类 prompt
    - 取代原 chat_node() 中的能力介绍 prompt
    - 取代原硬编码规则（@ 引用路由、意图阶段检测）
    - 与 @tool docstrings 互补：
      system prompt 提供上下文和规则，docstrings 提供工具级说明
    """
    creator_profile = state.get("creator_profile", "")
    current_phase = state.get("current_phase", "intent")
    project_id = state.get("project_id", "")

    # ---- 动态段落 1: 内容块索引 ----
    field_index_section = ""
    if project_id:
        try:
            from core.digest_service import build_field_index
            fi = build_field_index(project_id)
            if fi:
                field_index_section = f"""
## 项目内容块索引
以下是本项目所有内容块及其摘要，按组归类。
用途：帮你定位与用户指令相关的内容块，选择正确的工具参数（field_name）。
**注意**：摘要只是索引，不代表完整内容。需要完整内容时请使用 read_field 工具。

{fi}
"""
        except ImportError:
            # digest_service 尚未创建（M7），静默跳过
            pass
        except Exception as e:
            logger.warning(f"build_field_index failed: {e}")

    # ---- 动态段落 2: 组状态 ----
    phase_context = ""
    if project_id:
        try:
            from core.database import get_db
            from core.models import Project
            db = next(get_db())
            try:
                project = db.query(Project).filter(Project.id == project_id).first()
                if project:
                    ps = project.phase_status or {}
                    po = project.phase_order or []
                    current_status = ps.get(current_phase, "pending")
                    phase_context = f"组状态: {current_status}\n项目组顺序: {' → '.join(po)}"
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"build phase_context failed: {e}")

    # ---- 动态段落 3: 意图分析阶段专用指南 ----
    intent_guide = ""
    if current_phase == "intent":
        intent_guide = """
## 🎯 意图分析流程（当前组 = intent）
你当前正在帮助创作者明确内容目标。请通过 3 轮对话收集以下信息：

1. **做什么**（主题和目的）— 问法举例：「你这次想做什么内容？请简单描述主题或方向。」
2. **给谁看**（目标受众）— 根据上一个回答个性化提问
3. **期望行动**（看完后希望受众做什么）— 根据之前的回答个性化提问

### 流程规则
- 每次只问一个问题，用编号标记（如【问题 1/3】）
- 用户回答后，先简要确认你的理解，再追问下一个
- 3 个问题都回答后：
  1. 输出结构化的意图分析摘要
  2. 调用 update_field(field_name="意图分析", content=摘要内容) 保存
  3. 告诉用户「✅ 已生成意图分析，请在工作台查看。输入"继续"进入下一组」
- **如果用户在此阶段问其他问题（如"你能做什么"），正常回答，不影响问答流程**
- **如果用户说"继续"/"下一步"且意图分析已保存，调用 advance_to_phase 进入下一组**
"""

    return f"""你是一个智能内容生产 Agent，帮助创作者完成从意图分析到内容发布的全流程。

## ⚠️ 输出格式（最高优先级，必须遵守）
- 用主谓宾结构完整的句子、段落和正常的标点符号进行输出，不要故意去掉标点符号和换行。
- 例如：回复"你好"时，必须写「你好！有什么我可以帮你的？」而不是「你好 有什么可以帮你的」。
- 可以使用 Markdown 格式（标题、列表、加粗等）让内容更清晰。
- 长内容适当分段，保持可读性。

## 你的能力
1. **意图分析** — 通过 3 个问题帮创作者明确内容目标（做什么、给谁看、期望行动）
2. **消费者调研** — 使用 DeepResearch 深度分析目标用户画像和痛点
3. **内容规划** — 设计内容大纲和架构（组、内容块的组织方式）
4. **内容生成** — 根据设计方案为各内容块生成具体内容
5. **内容修改** — 根据指令修改已有内容
6. **架构管理** — 添加/删除/移动内容块和组
7. **人物管理** — 生成和管理消费者画像
8. **评估** — 多维度评估内容质量

## 创作者信息
{creator_profile or '（暂无创作者信息）'}

## 当前项目上下文
当前组: {current_phase}
{phase_context}
{field_index_section}
{intent_guide}

## @ 引用约定
用户消息中的 `@内容块名` 表示引用了项目中的某个内容块。引用内容会附在用户消息末尾。
- `@场景库 把5个模块改成7个` → 用户想修改"场景库" → 使用 modify_field
- `@逐字稿1 这个怎么样` → 用户想了解"逐字稿1"的内容 → 使用 query_field
- `参考 @用户画像 修改 @场景库` → "用户画像"是参考源，"场景库"是修改目标 → modify_field(field_name="场景库", reference_fields=["用户画像"])

## ⚠️ 关键消歧规则

### 1. "添加内容块" vs "修改内容"
- 「帮我加/新增/补充一个内容块」→ **manage_architecture**（创建新的结构）
- 「修改/调整/重写场景库的内容」「把5个改成7个」→ **modify_field**（改已有文本）
- **判断标准**：用户想改变项目结构（增删内容块/组）→ manage_architecture；想改文字内容 → modify_field

### 2. "进入阶段" vs "在阶段里操作"
- 「进入外延设计」「开始下一阶段」「继续」→ **advance_to_phase**
- 「在外延设计加一个内容块」→ **manage_architecture**
- **判断标准**：有"进入/开始/继续/下一步"且没有具体操作词 → advance_to_phase

### 3. "消费者调研" vs "通用调研"
- 「开始消费者调研」「做用户调研」→ run_research(research_type="consumer")
- 「帮我调研一下X市场」「搜索Y的资料」→ run_research(research_type="generic")

### 4. "生成" vs "修改"
- 内容块为空（索引中无摘要或标记为空）→ **generate_field_content**
- 内容块已有内容 → **modify_field**
- 不确定时，先用 read_field 查看内容块是否为空

## 保存对话输出到内容块
当用户说「把上面的内容保存到XX」「写到XX里」「保存到XX」时：
1. 从你之前的对话回复中提取相关内容
2. 使用 update_field(field_name="XX", content=提取的内容) 保存
3. 告诉用户已保存

## 什么时候不调用工具（直接回复）
- 用户打招呼：「你好」「hi」
- 用户问你的能力：「你能做什么？」「你是谁？」
- 用户问通用问题：「帮我解释一下内涵设计是什么」「这个系统怎么用」
- 用户在意图分析流程中回答你的提问（不要把回答当成指令！）
- 任何不涉及具体操作的对话

## 修改确认流程
modify_field 工具可能返回需要用户确认的修改计划：
- 返回 status="need_confirm" → 向用户展示修改计划，等待确认
- 返回 status="applied" → 修改已直接应用，告诉用户结果
- 用户确认后，工具会自动完成修改

## 交互规则
1. 用户要求"做"某事（创建/添加/删除/修改/生成/调研/评估）→ 调用对应工具
2. 一次对话中可以调用多个工具（如「删掉这个内容块，再帮我生成一个新的」→ manage_architecture + generate_field_content）
3. 工具执行完成后，用简洁友好的中文告诉用户结果
4. 使用中文回复，语气专业但亲切
5. 如果不确定用户意图，先确认再操作，不要猜测

"""


# ============== 节点函数 ==============

async def agent_node(state: AgentState, config: RunnableConfig) -> dict:
    """
    Agent 决策节点。

    流程：
    1. 构建 system prompt（每次重新生成，反映最新项目状态）
    2. trim_messages 裁剪历史（防止 context window 溢出）
    3. bind_tools 的 LLM 自主决定：直接回复 or 调用工具

    注意：config 参数由 LangGraph 自动注入，包含 astream_events 的
    callback manager。必须传给 LLM 调用，否则 on_chat_model_stream
    事件不会被触发，导致前端无法流式显示。
    """
    from langchain_core.messages import trim_messages

    logger.debug("[agent_node] 开始执行, messages=%d", len(state["messages"]))

    # 工具执行后使 field_index 缓存失效（工具可能修改了内容块）
    if state["messages"] and isinstance(state["messages"][-1], ToolMessage):
        try:
            from core.digest_service import invalidate_field_index_cache
            project_id = state.get("project_id", "")
            if project_id:
                invalidate_field_index_cache(project_id)
        except ImportError:
            pass

    system_prompt = build_system_prompt(state)

    # Token 预算管理：保留最近消息，裁剪过早历史
    trimmed = trim_messages(
        state["messages"],
        max_tokens=100_000,      # 为 system prompt (~5K) + 回复 (~10K) 预留
        token_counter=llm,       # 使用 LLM 内置 token 计数
        strategy="last",         # 保留最新消息
        start_on="human",        # 确保从 HumanMessage 开始
        include_system=False,    # system prompt 由我们单独管理
        allow_partial=False,     # 不截断单条消息
    )

    logger.debug("[agent_node] trimmed messages=%d (from %d)", len(trimmed), len(state["messages"]))

    # 将 system prompt 作为第一条消息注入
    messages_with_system = [SystemMessage(content=system_prompt)] + trimmed

    # LLM 调用（bind_tools 让 LLM 自动决定是否调用工具）
    # ⚠️ 必须传 config，否则 astream_events 的 callback 链断裂，无法流式输出
    llm_with_tools = llm.bind_tools(AGENT_TOOLS)
    response = await llm_with_tools.ainvoke(messages_with_system, config=config)

    has_tool_calls = hasattr(response, "tool_calls") and response.tool_calls
    content_preview = (response.content or "")[:200]
    logger.info(
        "[agent_node] LLM 返回: content=%d chars, tool_calls=%s, preview='%s'",
        len(response.content) if response.content else 0,
        [tc["name"] for tc in response.tool_calls] if has_tool_calls else "none",
        content_preview,
    )

    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """
    条件边：检查最后一条消息是否包含 tool_calls。

    - 有 tool_calls → 去 tools 节点执行
    - 无 tool_calls → 结束（LLM 直接回复了用户）
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


# ============== 图构建 ==============

def create_agent_graph():
    """
    创建 Agent 图（带 Checkpointer）。

    结构：
        agent_node ──(有tool_calls)──→ tool_node ──→ agent_node（循环）
            │
            └──(无tool_calls)──→ END

    Checkpointer 使对话状态在请求间（含服务重启后）自动累积。
    使用 SqliteSaver 持久化到 data/agent_checkpoints.db。
    """
    import sqlite3
    import os

    graph = StateGraph(AgentState)

    # 节点
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(AGENT_TOOLS))

    # 入口
    graph.set_entry_point("agent")

    # 条件边：agent → tools 或 END
    graph.add_conditional_edges("agent", should_continue, {
        "tools": "tools",
        END: END,
    })

    # tools 执行完后回到 agent（让 LLM 看到工具结果，决定下一步）
    graph.add_edge("tools", "agent")

    # Checkpointer — SqliteSaver 持久化（重启后对话状态含 ToolMessage 全部恢复）
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "agent_checkpoints.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()

    return graph.compile(checkpointer=checkpointer)


# 全局实例
agent_graph = create_agent_graph()


# P3-1: ContentProductionAgent、content_agent、ContentProductionState 已删除
# api/agent.py 的 /chat 和 /retry 已直接使用 agent_graph.ainvoke()
