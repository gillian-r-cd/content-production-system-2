# backend/core/orchestrator.py
# 功能: LangGraph Agent 核心编排器（重写版）
# 架构: Custom StateGraph + Tool Calling + AsyncSqliteSaver
# 主要导出: get_agent_graph(), AgentState, build_system_prompt
# 设计原则:
#   1. LLM 通过 bind_tools 自动选择工具（不再手动 if/elif 路由）
#   2. State 保留 7 个字段（messages + 3 上下文 + 3 模式/记忆）
#   3. 所有 DB 操作在 @tool 函数内完成，不通过 State 传递
#   4. Checkpointer (AsyncSqliteSaver) 跨请求/跨重启保持对话状态（含 ToolMessage）
#   5. trim_messages 管理 context window，防止超限
#   6. Graph 延迟编译（get_agent_graph() 异步首次初始化 checkpointer）

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
    Agent 状态。

    核心字段：
    - messages: 对话历史（LangGraph 核心，包含 Human/AI/Tool Messages）
    - project_id: 项目 ID（传递给工具，通过 configurable）
    - current_phase: 当前组（注入到 system prompt）
    - creator_profile: 创作者画像（注入到 system prompt）

    模式与记忆字段（Memory & Mode System）：
    - mode: 当前模式名（如 "critic", "strategist"），默认 "assistant"
    - mode_prompt: 当前模式的 system_prompt（身份段），替换 build_system_prompt 的开头
    - memory_context: 全量 MemoryItem 拼接文本（记忆层，M2 阶段启用）

    设计原则：
    - DB 操作在 @tool 函数内完成，不通过 State 传递
    - field_updated / is_producing 等信息从 tool_end 事件推断
    - phase_order / phase_status 在 @tool 函数内从 DB 读取
    """
    messages: Annotated[list[BaseMessage], operator.add]
    project_id: str
    current_phase: str
    creator_profile: str
    mode: str               # 当前模式名（如 "assistant", "critic", "strategist"）
    mode_prompt: str         # 当前模式的 system_prompt（身份段）
    memory_context: str      # 全量 MemoryItem 拼接（记忆层，M2 启用）


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

    模式系统：
    - mode_prompt 有值时替换身份段（开头），否则使用默认身份
    - memory_context 有值时注入「项目记忆」段落
    """
    creator_profile = state.get("creator_profile", "")
    current_phase = state.get("current_phase", "intent")
    project_id = state.get("project_id", "")
    mode_prompt = state.get("mode_prompt", "")
    memory_context = state.get("memory_context", "")

    # ---- 动态段落 1: 内容块索引（简化前缀，6.8 节） ----
    field_index_section = ""
    if project_id:
        try:
            from core.digest_service import build_field_index
            fi = build_field_index(project_id)
            if fi:
                field_index_section = fi
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

    # ---- 身份段：来自模式配置 ----
    if mode_prompt:
        identity = mode_prompt
    else:
        identity = "你是一个智能内容生产 Agent，帮助创作者完成从意图分析到内容发布的全流程。"

    # ---- 记忆段：全量注入（M2 启用后生效） ----
    memory_section = ""
    if memory_context:
        memory_section = f"""<memory>
## 项目记忆
以下是跨模式、跨阶段积累的关键信息。

使用规则:
- 做内容修改时，检查是否与记忆中的偏好或约束冲突。
- NEVER 在回复中复述记忆内容。
- 记忆可能过时。如果用户当前指令与记忆矛盾，以当前指令为准。
{memory_context}
</memory>"""

    return f"""<identity>
{identity}
</identity>

<output_rules>
ALWAYS: 输出格式规则
- 用主谓宾结构完整的句子、段落和正常的标点符号进行输出。
- 可以使用 Markdown 格式（标题、列表、加粗等）让内容更清晰。
- 长内容适当分段，保持可读性。
- 使用中文回复，语气专业但亲切。
</output_rules>

<action_guide>
## 行动指南

根据用户的意图选择正确的行动。

### 用户想修改内容
CRITICAL: 修改已有内容时，ALWAYS 使用 propose_edit 展示修改预览供确认。
CRITICAL: 只有用户消息中明确包含"直接改""不用确认""直接修改"等关键词时才可使用 modify_field。
- 用户说"帮我改一下 XX" -> propose_edit（默认！没说"直接"就走 propose_edit）
- 用户说"把XX改成YY" -> propose_edit（有具体修改意图，但没说"直接"）
- 用户说"suggestion card""修改建议""给我看看修改方案" -> propose_edit
- 用户说"直接改""不用确认""直接帮我修改" -> modify_field（仅此情况跳过确认）
- 内容块为空 -> generate_field_content（不是修改，是首次生成）
- 用户说"重写""从头写" -> generate_field_content 或 modify_field（全文替换）
- 用户提供了完整的替换内容 -> update_field

### 用户想了解内容
- 用户说"看看 XX""读一下 XX" -> read_field
- 用户说"XX 怎么样""分析一下 XX" -> query_field

### 用户想改项目结构
- 用户说"加一个内容块""删掉 XX""新增一个组" -> manage_architecture

### 用户想推进项目
- 用户说"继续""下一步""进入 XX" -> advance_to_phase

### 用户想做调研
- 用户说"做消费者调研" -> run_research(research_type="consumer")
- 用户说"调研一下 XX 市场" -> run_research(research_type="generic")

### 用户想评估内容
- 用户说"评估一下""检查质量" -> run_evaluation

### 保存对话输出到内容块
- 用户说"把上面的内容保存到XX""写到XX里" -> update_field(field_name="XX", content=提取的内容)

### 不需要调用工具
- 用户打招呼、问你是谁、问通用问题 -> 直接回复
- 用户在意图分析中回答你的提问 -> 不要当成指令
- 用户在讨论方向、还没决定怎么改 -> 文本对话

### 错误用法示例（NEVER 这样做）

1. 把讨论当成修改请求:
   用户: "我觉得开头有点弱"
   错误: 立即调用 propose_edit
   正确: 回复"你希望往哪个方向加强？比如增加数据支撑、讲一个故事、还是提出一个引发好奇的问题？"
   原因: "有点弱"是评价，不是修改指令。用户还没决定"往哪个方向改"。

2. 跳过确认直接修改:
   用户: "帮我改一下场景库"
   错误: 调用 modify_field 直接生成新内容覆写
   正确: 调用 propose_edit 展示具体的修改建议和 diff 预览
   原因: "帮我改一下"没有说"直接改不用确认"。没有"直接"二字就必须走 propose_edit。

2b. 有具体修改指令但没说"直接":
   用户: "把 @课程内容 的字母改成数字"
   错误: 调用 modify_field（认为指令很明确所以直接执行）
   正确: 调用 propose_edit（先展示修改预览）
   原因: 指令明确≠用户想跳过确认。判断标准是有没有"直接"关键词，不是修改是否简单。

2c. 用户要求看修改建议:
   用户: "你用 suggestion card 给我看一下修改思路" 或 "给我修改建议"
   错误: 用文本回复描述修改思路
   正确: 调用 propose_edit 生成带 diff 预览的修改建议卡片
   原因: "suggestion card""修改建议" = 用户在要求你使用 propose_edit 工具。

3. 猜测内容块名称:
   用户: "修改那个关于场景的内容"
   错误: propose_edit(target_field="场景分析", ...)（猜测了名称，实际可能叫"场景库"）
   正确: 查看索引确认，或回复"你指的是'场景库'还是'场景分析'？"
   原因: 用错名称会导致找不到内容块。

4. anchor 不精确:
   错误: propose_edit(edits=[{{"anchor": "第三段讲了一些关于用户的内容", ...}}])
   正确: propose_edit(edits=[{{"anchor": "本场景库包含5个核心场景", ...}}])
   原因: anchor 必须是原文中精确存在的文本片段，否则 edit_engine 无法定位。

5. 用 propose_edit 做全文重写:
   用户: "帮我把场景库整个重写"
   错误: propose_edit 但 edits 覆盖了整篇内容
   正确: generate_field_content("场景库", "重写")
   原因: 全文重写不适合 anchor-based edits，应该用从零生成。
</action_guide>

<modification_rules>
## 修改操作规则

CRITICAL: 用户说"帮我改""修改""把XX改成YY"时，ALWAYS 使用 propose_edit。这是默认且唯一的修改路径。
CRITICAL: modify_field 仅在用户消息明确包含"直接改""不用确认""直接修改"时才允许使用。没看到这些关键词就用 propose_edit。
CRITICAL: 用户说"suggestion card""修改建议""给我看看修改方案" → 就是在要求你使用 propose_edit 工具。
CRITICAL: propose_edit 中的 anchor 必须是原文中精确存在的文本片段。不确定时先用 read_field 查看原文。
CRITICAL: 不要猜测内容块名称。不确定时查看项目内容块索引。

ALWAYS: 修改前使用 read_field 确认当前内容（除非本轮对话中刚读取过）。
ALWAYS: 多字段关联修改使用相同的 group_id。
ALWAYS: 工具执行完成后，用简洁的中文告知结果。

NEVER: 不要在用户要求修改时使用 modify_field（除非用户明确说了"直接"）。
NEVER: 不要在用户没有要求修改时自主调用 modify_field 或 propose_edit。
NEVER: 不要在只有模糊方向（如"可能需要改进"）时输出 propose_edit -- 先文本讨论，明确后再 propose。
NEVER: 不要在意图分析流程中把用户对问题的回答当成操作指令。
NEVER: 不要在回复中复述记忆内容。

DEFAULT: 所有修改操作走 propose_edit 确认流程。只有"直接改""不用确认"才可覆盖为 modify_field。
DEFAULT: 不确定内容块是否为空时，先 read_field 确认。
</modification_rules>

<disambiguation>
## 关键消歧规则

### 1. "添加内容块" vs "修改内容"
- 「帮我加/新增/补充一个内容块」-> manage_architecture（创建新的结构）
- 「修改/调整/优化场景库的内容」-> propose_edit（改已有文本，展示预览）
- 「直接修改/直接重写」-> modify_field（跳过确认）
- 判断标准：改项目结构 -> manage_architecture；改文字内容（默认） -> propose_edit

### 2. "进入阶段" vs "在阶段里操作"
- 「进入外延设计」「开始下一阶段」「继续」-> advance_to_phase
- 「在外延设计加一个内容块」-> manage_architecture
- 判断标准：有"进入/开始/继续/下一步"且没有具体操作词 -> advance_to_phase

### 3. "消费者调研" vs "通用调研"
- 「开始消费者调研」「做用户调研」-> run_research(research_type="consumer")
- 「帮我调研一下X市场」「搜索Y的资料」-> run_research(research_type="generic")

### 4. "生成" vs "修改"
- 内容块为空（索引中无摘要或标记为空）-> generate_field_content
- 内容块已有内容 -> propose_edit（默认）或 modify_field（用户说直接改）
- 不确定时，先用 read_field 查看内容块是否为空

### 5. propose_edit vs modify_field（核心判断规则）
判断标准：用户消息是否包含"直接""不用确认"等跳过确认的关键词。
- 没有"直接" → propose_edit（默认且必须）
- 有"直接""不用确认" → modify_field（可跳过确认）
- "suggestion card""修改建议""修改方案""帮我看看怎么改" → propose_edit
- Agent 自主判断需要修改 → propose_edit
- 大范围重写 → generate_field_content 或 modify_field

### @ 引用约定
用户消息中的 @内容块名 表示引用了项目中的某个内容块。引用内容会附在用户消息末尾。
- @场景库 帮我改一下开头 -> propose_edit（默认确认流程）
- @逐字稿1 这个怎么样 -> query_field
- 参考 @用户画像 修改 @场景库 -> propose_edit(target_field="场景库")，先 read_field 两个块
</disambiguation>

<project_context>
## 创作者信息
{creator_profile or '（暂无创作者信息）'}

## 当前项目上下文
当前组: {current_phase}
{phase_context}

<field_index>
ALWAYS: 以下为摘要索引。需要完整内容时用 read_field 读取。
{field_index_section}
</field_index>

{memory_section}
</project_context>

<interaction_rules>
意图判断策略：
1. 意图清晰 + 非修改操作 -> 立即行动，不做多余确认。
2. 意图清晰 + 修改操作 -> propose_edit 展示方案（这不是"犹豫"，是"展示"）。
3. 意图模糊但可合理推断 -> 给出你的理解并执行，附一句"如果意图不同请告诉我"。
4. 完全无法判断 -> 列出 2-3 种可能的理解，请用户选择。

NEVER 空泛地问"你想做什么？"——至少给出你的判断。

一次对话中可以调用多个工具（如「删掉这个内容块，再帮我生成一个新的」-> manage_architecture + generate_field_content）。
</interaction_rules>

{intent_guide}
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

    # 返回未编译的 graph builder（checkpointer 在异步上下文中延迟绑定）
    return graph


# ---- 延迟编译的 Agent Graph（支持 AsyncSqliteSaver） ----
_graph_builder = create_agent_graph()
_compiled_graph = None
_async_checkpointer = None


async def get_agent_graph():
    """
    获取编译后的 Agent Graph（带 AsyncSqliteSaver checkpointer）。
    首次调用时异步初始化 checkpointer 并编译；后续直接返回缓存实例。
    """
    global _compiled_graph, _async_checkpointer

    if _compiled_graph is not None:
        return _compiled_graph

    import os
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "agent_checkpoints.db")

    conn = await aiosqlite.connect(db_path)
    _async_checkpointer = AsyncSqliteSaver(conn)

    # 手动建表（兼容 aiosqlite 0.22 没有 is_alive 方法）
    async with conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            parent_checkpoint_id TEXT,
            type TEXT,
            checkpoint BLOB,
            metadata BLOB,
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        );
        CREATE TABLE IF NOT EXISTS writes (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            idx INTEGER NOT NULL,
            channel TEXT NOT NULL,
            type TEXT,
            value BLOB,
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        );
    """):
        await conn.commit()
    _async_checkpointer.is_setup = True

    _compiled_graph = _graph_builder.compile(checkpointer=_async_checkpointer)
    return _compiled_graph


# 兼容性别名（旧代码可能直接引用 agent_graph）
agent_graph = None  # 已废弃，请使用 await get_agent_graph()


# P3-1: ContentProductionAgent、content_agent、ContentProductionState 已删除
# api/agent.py 的 /chat 和 /retry 已直接使用 agent_graph.ainvoke()
