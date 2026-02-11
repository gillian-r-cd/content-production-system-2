# Agent 架构迁移方案：正确使用 LangGraph

> 创建时间: 2026-02-11
> 状态: 方案已确认，待实施

---

## 一、共识回顾

经过详细讨论，我们达成以下共识：

1. **删除 `ai_client`**：自定义的 `AIClient` 不支持 LangChain 消息类型、不支持 Tool Calling、无法融入 LangGraph 生态。所有 LLM 调用统一走 LangChain 的 `BaseChatModel`。
2. **正确使用 LangGraph**：当前代码定义了 LangGraph 图，但前端唯一使用的 `/stream` 端点完全绕开了这个图，手动调用 `route_intent()` 再用 `if/elif` 分发。这是"伪 LangGraph"。
3. **LLM 驱动路由**：用 OpenAI Tool Calling（`bind_tools`）替代手写的意图分类 prompt + JSON 解析，让 LLM 原生地选择调用哪个工具。
4. **多 API 切换**：利用 LangChain 的 `BaseChatModel` 抽象层，在配置层支持多个 LLM Provider（OpenAI / Gemini / Qwen / DeepSeek），用户可在后台切换。
5. **Token 级流式输出**：统一用 `graph.astream_events(version="v2")` 实现所有路由的 token-by-token 流式输出，而非只有 `chat` 路由支持。

---

## 二、现有架构问题诊断

### 2.1 双轨路由（核心缺陷）

```
前端 → POST /api/agent/stream
         │
         ├── agent.py: 手动调用 route_intent()
         ├── agent.py: if route_target == "chat": ... elif "generic_research": ...
         ├── agent.py: node_map[route_target] = tool_node  ← 手动分发
         │
         └── LangGraph 图（定义了 ~20 个节点 + 条件边）← 从未被 /stream 调用

前端 → POST /api/agent/chat  ← 前端不用
         │
         └── content_agent.run() → graph.ainvoke()  ← LangGraph 图被调用，但无流式
```

**问题**：LangGraph 图是死代码。所有实际流量走 `/stream`，完全手动分发。这意味着 LangGraph 的条件边、多意图处理（`continue_pending`）、状态检查点等能力全部未使用。

### 2.2 意图路由的两阶段 LLM 调用

```
请求 → route_intent() [LLM调用1: 意图分类 JSON] → 解析 intent/target/operation
     → 节点函数 [LLM调用2: 执行任务]
```

**问题**：每次请求都需要 2 次 LLM 调用（一次分类、一次执行）。正确的做法是用 Tool Calling，让 LLM 在一次调用中同时决定意图和参数。

### 2.3 ai_client 的局限性

| 能力 | ai_client | ChatOpenAI (LangChain) |
|------|-----------|----------------------|
| 纯文本对话 | ✅ | ✅ |
| 流式输出 | ✅ `stream_chat()` | ✅ `astream()` |
| Tool Calling | ❌ 不支持 | ✅ `bind_tools()` |
| 结构化输出 | ⚠️ 手动 JSON schema 注入 | ✅ `with_structured_output()` |
| LangChain 消息类型 | ❌ 自定义 `ChatMessage` | ✅ `HumanMessage/AIMessage/ToolMessage` |
| LangGraph 兼容 | ❌ | ✅ 原生兼容 |
| API 切换 | ❌ 硬编码 OpenAI | ✅ `BaseChatModel` 多 provider |

### 2.4 State 膨胀

当前 `ContentProductionState` 有 **27 个字段**，其中大部分是为了在手动分发中传递信息。正确使用 LangGraph 后，状态可以大幅简化。

### 2.5 流式输出不一致

- `chat` 路由：通过 `ai_client.stream_chat()` 实现 token 级流式
- 其他所有路由：等待节点函数执行完毕，一次性发送 `content` 事件

---

## 三、目标架构

### 3.1 架构总览

```
前端 → POST /api/agent/stream
         │
         └── agent.py:
               1. 构建 AgentState（messages + metadata）
               2. graph.astream_events(input, version="v2")
               3. 遍历事件流：
                  - on_chat_model_stream → yield SSE token
                  - on_tool_start → yield SSE status
                  - on_tool_end → yield SSE result
                  - 图结束 → yield SSE done + 保存DB
```

### 3.2 LLM 层：统一 ChatModel + 多 Provider 切换

**新文件 `backend/core/llm.py`**：

```python
"""
统一的 LLM 实例管理
支持多 Provider 切换（OpenAI / Gemini / Qwen / DeepSeek）
"""
from langchain_openai import ChatOpenAI
from core.config import settings

# Provider 配置映射
# 每个 provider 对应一组 (ChatModel类, 默认模型, 额外参数)
PROVIDER_REGISTRY = {
    "openai": {
        "class": "langchain_openai.ChatOpenAI",
        "default_model": "gpt-5.1",
        "env_key": "OPENAI_API_KEY",
    },
    # 未来扩展：
    # "gemini": {
    #     "class": "langchain_google_genai.ChatGoogleGenerativeAI",
    #     "default_model": "gemini-2.0-flash",
    #     "env_key": "GOOGLE_API_KEY",
    # },
    # "qwen": {
    #     "class": "langchain_community.chat_models.ChatTongyi",
    #     "default_model": "qwen-max",
    #     "env_key": "DASHSCOPE_API_KEY",
    # },
    # "deepseek": {
    #     "class": "langchain_openai.ChatOpenAI",  # DeepSeek 兼容 OpenAI API
    #     "default_model": "deepseek-chat",
    #     "env_key": "DEEPSEEK_API_KEY",
    #     "base_url": "https://api.deepseek.com/v1",
    # },
}

def get_chat_model(
    provider: str = "openai",
    model: str | None = None,
    temperature: float = 0.7,
    streaming: bool = True,
    **kwargs,
) -> ChatOpenAI:
    """
    获取 ChatModel 实例。

    Args:
        provider: LLM 提供商名称（openai/gemini/qwen/deepseek）
        model: 模型名称，None 则使用 provider 默认模型
        temperature: 温度
        streaming: 是否启用流式（LangGraph astream_events 需要）
        **kwargs: 传递给 ChatModel 构造函数的额外参数

    Returns:
        BaseChatModel 实例
    """
    # 当前阶段只实现 OpenAI，其他 provider 后续按需添加
    model = model or settings.openai_model or "gpt-5.1"
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        streaming=streaming,
        api_key=settings.openai_api_key,
        organization=settings.openai_org_id or None,
        base_url=settings.openai_api_base or None,
        timeout=120,
        **kwargs,
    )

# 默认实例（Agent 主模型）
llm = get_chat_model()

# 小模型实例（摘要生成等轻量任务）
llm_mini = get_chat_model(model="gpt-4o-mini", temperature=0)
```

**Settings 扩展（`backend/core/config.py`）**：

```python
class Settings(BaseSettings):
    # 当前使用的 LLM Provider
    llm_provider: str = "openai"

    # OpenAI
    openai_api_key: str = ""
    openai_org_id: str = ""
    openai_model: str = "gpt-5.1"
    openai_api_base: str = ""

    # 未来扩展（暂不实现）
    # google_api_key: str = ""
    # dashscope_api_key: str = ""
    # deepseek_api_key: str = ""

    # ... 其他配置不变
```

### 3.3 工具层：LangChain `@tool`

**新文件 `backend/core/agent_tools.py`**：

所有现有的"节点函数"中涉及实际操作的部分（修改字段、生成内容、调研、管理架构等），转化为 LangChain `@tool` 函数。

```python
"""
Agent 工具定义
使用 LangChain @tool 装饰器，让 LLM 通过 Tool Calling 自动选择
"""
from langchain_core.tools import tool
from typing import Optional

@tool
def modify_field(field_name: str, instruction: str, reference_fields: list[str] = []) -> str:
    """修改指定字段的内容。当用户要求修改、调整、重写某个字段时使用。

    Args:
        field_name: 要修改的目标字段名称
        instruction: 用户的修改指令（如"把5个模块改成7个"）
        reference_fields: 需要参考的其他字段名称列表
    """
    # 实现：读取字段内容 → 构建 prompt → LLM 生成 edits → apply_edits
    ...

@tool
def generate_field_content(field_name: str, instruction: str = "") -> str:
    """生成指定字段的内容。当用户要求生成、创建某个字段的内容时使用。

    Args:
        field_name: 要生成内容的字段名称
        instruction: 额外的生成指令（可选）
    """
    ...

@tool
def query_field(field_name: str, question: str) -> str:
    """查询字段内容并回答问题。当用户询问某个字段的内容或想了解相关信息时使用。

    Args:
        field_name: 要查询的字段名称
        question: 用户的问题
    """
    ...

@tool
def manage_architecture(operation: str, target: str, details: str = "") -> str:
    """管理项目架构（添加/删除/移动字段或阶段）。

    Args:
        operation: 操作类型（add_field/remove_field/add_phase/remove_phase/move_field）
        target: 操作目标（字段名或阶段名）
        details: 操作详情（如新字段的描述、目标位置等）
    """
    ...

@tool
def advance_to_phase(target_phase: str = "") -> str:
    """推进项目到下一阶段或指定阶段。

    Args:
        target_phase: 目标阶段名称（空字符串表示下一阶段）
    """
    ...

@tool
def run_research(query: str, research_type: str = "consumer") -> str:
    """执行调研。consumer=消费者调研，generic=通用深度调研。

    Args:
        query: 调研主题或查询
        research_type: 调研类型（consumer/generic）
    """
    ...

@tool
def manage_persona(operation: str, persona_data: str = "") -> str:
    """管理用户画像/角色。

    Args:
        operation: 操作类型（list/create/update/delete/generate）
        persona_data: 角色数据（JSON 格式，创建/更新时需要）
    """
    ...

@tool
def run_evaluation() -> str:
    """对项目内容执行全面评估，生成评估报告。"""
    ...

@tool
def read_field(field_name: str) -> str:
    """读取指定字段的完整内容。当用户想查看某个字段的内容时使用。

    Args:
        field_name: 要读取的字段名称
    """
    ...

@tool
def update_field(field_name: str, content: str) -> str:
    """直接用给定内容覆写指定字段。当用户提供了完整内容要求直接替换时使用。

    Args:
        field_name: 要更新的字段名称
        content: 新内容（完整替换）
    """
    ...

@tool
def generate_outline(topic: str = "") -> str:
    """生成内容大纲/规划。

    Args:
        topic: 大纲主题（为空则基于项目意图自动生成）
    """
    ...
```

**关键设计要点**：

1. 每个 `@tool` 的 docstring 就是 LLM 看到的工具描述，必须写清楚"什么时候用"
2. 参数通过 `Args` 描述，LLM 会自动提取
3. 工具函数内部可以访问 DB（通过闭包或全局 session），不需要从 State 传递
4. 工具函数返回字符串（LLM 会看到返回值并决定下一步）

### 3.4 Graph 定义

**`backend/core/orchestrator.py`（重写）**：

```python
"""
LangGraph Agent 核心编排器（重写版）

架构：Custom StateGraph + Tool Calling
- 入口节点: agent_node（LLM 决策 + Tool Calling）
- 工具节点: tool_node（执行被选中的工具）
- 条件边: should_continue（检查是否有 tool_calls）
"""
from typing import TypedDict, Annotated, Optional
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
import operator

from core.llm import llm
from core.agent_tools import AGENT_TOOLS  # 所有 @tool 的列表


# ============== State 定义 ==============

class AgentState(TypedDict):
    """
    Agent 状态（精简版）
    只保留 LangGraph 运转必需的字段。

    设计原则：
    - DB 操作在 @tool 函数内完成，不通过 State 传递
    - field_updated / is_producing 等信息通过 tool_end 事件的工具名推断，不放 State
    """
    # 消息历史（LangGraph 核心：包含 HumanMessage, AIMessage, ToolMessage）
    messages: Annotated[list[BaseMessage], operator.add]

    # 项目上下文（注入到 system prompt，不参与图路由）
    project_id: str
    current_phase: str
    creator_profile: str


# ============== 节点函数 ==============

def build_system_prompt(state: AgentState) -> str:
    """
    构建 system prompt。
    包含：角色定义 + 创作者特质 + 字段索引 + 阶段上下文
    """
    creator_profile = state.get("creator_profile", "")
    current_phase = state.get("current_phase", "intent")
    project_id = state.get("project_id", "")

    # 字段索引（平台记忆 — 需要 implementation_plan_v3 中的 digest_service 模块）
    # 注意：digest_service 是新建模块，初始迁移时可跳过此段
    field_index_section = ""
    if project_id:
        try:
            from core.digest_service import build_field_index
        except ImportError:
            build_field_index = None  # digest_service 尚未实现时的降级
        fi = build_field_index(project_id) if build_field_index else None
        if fi:
            field_index_section = f"""

## 项目字段索引
以下是本项目所有字段及其摘要。
用途：帮你定位与用户指令相关的字段。
注意：摘要只是索引，不是完整内容。不要基于摘要猜测或编造内容。

{fi}
"""

    return f"""你是一个智能的内容生产 Agent。

## 你的能力
你可以通过工具来执行各种操作。LLM 会根据用户指令自动选择合适的工具。
如果用户只是聊天或提问（不需要执行操作），直接回复即可，不要调用工具。

## 创作者信息
{creator_profile or '（暂无创作者信息）'}

## 当前阶段
{current_phase}
{field_index_section}

## 交互规则
1. 用户要求"做"某事 → 调用对应工具
2. 用户在问问题或闲聊 → 直接回复
3. 一次可以调用多个工具（如果用户有多个要求）
4. 工具返回结果后，用简洁的语言告诉用户结果
"""


async def agent_node(state: AgentState) -> dict:
    """
    Agent 决策节点。
    用 bind_tools 的 LLM 决定：直接回复 or 调用工具。
    """
    system_prompt = build_system_prompt(state)

    # 将 system prompt 作为第一条消息注入
    # 注意：每次调用都重新生成 system prompt（因为字段索引可能变化）
    messages_with_system = [SystemMessage(content=system_prompt)] + state["messages"]

    # LLM 调用（已 bind_tools，LLM 会自动决定是否调用工具）
    llm_with_tools = llm.bind_tools(AGENT_TOOLS)
    response = await llm_with_tools.ainvoke(messages_with_system)

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
    创建 Agent 图。

    结构：
        agent_node ──(有tool_calls)──→ tool_node ──→ agent_node（循环）
            │
            └──(无tool_calls)──→ END
    """
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

    return graph.compile()


# 全局实例
agent_graph = create_agent_graph()
```

### 3.5 API 层：统一流式输出

**`backend/api/agent.py`（重写 stream endpoint）**：

```python
@router.post("/stream")
async def stream_chat(request: ChatRequest, db: Session = Depends(get_db)):
    """
    与 Agent 对话（SSE 流式输出）

    架构：
    1. 构建 AgentState
    2. graph.astream_events(version="v2") 遍历事件流
    3. 根据事件类型 yield SSE 事件
    """
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    current_phase = request.current_phase or project.current_phase

    # 保存用户消息
    user_msg = ChatMessage(...)
    db.add(user_msg)
    db.commit()

    # 加载对话历史 → LangChain Message 列表
    chat_history = _load_chat_history(db, request.project_id, current_phase)

    # 构建 AgentState（只有 4 个字段）
    input_state = {
        "messages": chat_history + [HumanMessage(content=request.message)],
        "project_id": request.project_id,
        "current_phase": current_phase,
        "creator_profile": project.creator_profile.to_prompt_context() if project.creator_profile else "",
    }

    # 产出类工具列表（这些工具执行后前端需刷新左侧面板）
    PRODUCE_TOOLS = {"modify_field", "generate_field_content", "manage_architecture", "advance_to_phase"}

    async def event_generator():
        yield sse_event({"type": "user_saved", "message_id": user_msg.id})

        full_content = ""
        current_tool = None
        is_producing = False   # 是否有字段产出（从工具名推断）

        # config 传递 project_id 等信息给 @tool 函数
        config = {"configurable": {"project_id": request.project_id}}

        async for event in agent_graph.astream_events(input_state, config=config, version="v2"):
            kind = event["event"]

            # Token 级流式（所有路由统一）
            # 注意：只转发 agent 节点的 LLM stream，工具内部 LLM 调用不转发
            if kind == "on_chat_model_stream":
                # 通过 tags 或 name 判断事件来源，只转发 agent 节点
                tags = event.get("tags", [])
                if "agent" in tags or event.get("name") == "agent":
                    chunk = event["data"]["chunk"]
                    if chunk.content:
                        full_content += chunk.content
                        yield sse_event({"type": "token", "content": chunk.content})

            # 工具开始
            elif kind == "on_tool_start":
                tool_name = event["name"]
                current_tool = tool_name
                yield sse_event({"type": "tool_start", "tool": tool_name})

            # 工具结束
            elif kind == "on_tool_end":
                tool_output = event["data"].get("output", "")
                field_updated = current_tool in PRODUCE_TOOLS
                if field_updated:
                    is_producing = True
                yield sse_event({
                    "type": "tool_end",
                    "tool": current_tool,
                    "output": tool_output[:500],
                    "field_updated": field_updated,
                })
                current_tool = None

        # 图执行完毕 → 保存响应 + 发送 done
        agent_msg = ChatMessage(
            id=generate_uuid(),
            project_id=request.project_id,
            role="assistant",
            content=full_content,
            message_metadata={"phase": current_phase},
        )
        db.add(agent_msg)
        db.commit()

        yield sse_event({
            "type": "done",
            "message_id": agent_msg.id,
            "is_producing": is_producing,
        })

    return StreamingResponse(event_generator(), media_type="text/event-stream", ...)
```

### 3.6 SSE 事件类型映射

| 现有事件 | 新架构事件 | 说明 |
|----------|-----------|------|
| `user_saved` | `user_saved` | 不变 |
| `route` | `tool_start` | 路由信息改为工具开始事件 |
| `token` | `token` | 不变，但现在所有路由都支持 |
| `content` | _(删除)_ | 不再需要，所有内容通过 token 流式 |
| `done` | `done` | 不变 |
| `error` | `error` | 不变 |
| _(新增)_ | `tool_start` | 工具开始执行 |
| _(新增)_ | `tool_end` | 工具执行完毕 |

**前端兼容策略**：

前端的 `agent-panel.tsx` 需要适配新事件类型，但改动不大：
- `route` 事件 → 替换为 `tool_start`（显示"正在执行XX..."）
- `content` 事件 → 删除（不再需要，所有内容通过 `token`）
- 新增 `tool_start` / `tool_end` 处理
- `token` / `done` / `error` 保持不变

---

## 四、详细迁移计划

### Phase 1: 基础设施层

#### Step 1.1 — 新建 `backend/core/llm.py`

**类型**: 新建文件
**内容**: 统一的 ChatModel 工厂 + 默认实例
**关键函数**: `get_chat_model(provider, model, temperature, streaming, **kwargs)`
**全局实例**: `llm`（主模型）, `llm_mini`（小模型，摘要等轻量任务）

**验证**: `cd backend && python -c "from core.llm import llm, llm_mini; print(type(llm))"`

#### Step 1.2 — 扩展 `backend/core/config.py`

**类型**: 修改文件
**改动**: `Settings` 新增 `llm_provider: str = "openai"`
**影响范围**: 仅配置层，无业务逻辑变化

#### Step 1.3 — 新建 `backend/core/agent_tools.py`

**类型**: 新建文件
**内容**: 所有 `@tool` 定义 + `AGENT_TOOLS` 列表
**工具清单**（初始版本）:

| 工具名 | 对应现有功能 | 优先级 |
|--------|-------------|--------|
| `modify_field` | `modify_node` | P0 |
| `generate_field_content` | `generate_field_node` | P0 |
| `query_field` | `query_node` | P0 |
| `manage_architecture` | `tool_node` (architecture) | P0 |
| `advance_to_phase` | `_do_advance_phase` | P0 |
| `run_research` | `research_node` + `_do_generic_research` | P0 |
| `run_evaluation` | `evaluate_node` | P1 |
| `manage_persona` | `tool_node` (persona) | P1 |
| `generate_outline` | `tool_node` (outline) | P1 |
| `read_field` | `read_field_node` | P1 |
| `update_field` | `update_field_node` | P1 |
| `manage_skill` | `tool_node` (skill) | P2 |

**验证**: `cd backend && python -c "from core.agent_tools import AGENT_TOOLS; print(f'{len(AGENT_TOOLS)} tools loaded')"`

#### Step 1.4 — 更新 `backend/requirements.txt`

**改动**:
```diff
 # LangChain / LangGraph
 langchain>=1.2.0
+langchain-openai>=0.3.0
 langgraph>=1.0.0
```

**说明**: `langchain-openai` 提供 `ChatOpenAI`，目前通过 `langchain` 间接依赖，但显式声明更安全。

### Phase 2: Agent Graph 重写

#### Step 2.1 — 重写 `backend/core/orchestrator.py`

**类型**: 大幅重写（保留辅助函数，删除旧图）
**保留**:
- `normalize_intent()`, `normalize_consumer_personas()` — 辅助函数
- `_detect_modify_target()` — 可移入工具函数内部

**删除**:
- `ContentProductionState`（27 字段）→ 替换为 `AgentState`（4 字段）
- `route_intent()` — 不再需要，LLM 通过 Tool Calling 自动路由
- `create_content_production_graph()` — 替换为 `create_agent_graph()`
- `ContentProductionAgent` 类 — 替换为简单的 `agent_graph` 模块级实例
- `continue_pending_node()`, `route_after_phase()`, `route_after_tool()`, `route_by_intent()` — 不再需要

**改造的节点函数** → 移入 `agent_tools.py` 作为 `@tool`：
- `intent_analysis_node` → 特殊处理（意图分析是对话式多轮，不适合做工具，保留为特殊节点或用 interrupt 机制）
- `research_node` → `run_research` @tool
- `design_inner_node` / `produce_inner_node` / `design_outer_node` / `produce_outer_node` → 合并为 `generate_field_content` @tool（根据字段名和阶段自动选择 prompt）
- `evaluate_node` → `run_evaluation` @tool
- `modify_node` → `modify_field` @tool
- `query_node` → `query_field` @tool
- `tool_node` → 拆分为多个 @tool（manage_architecture, manage_persona, generate_outline, manage_skill）
- `read_field_node` → `read_field` @tool
- `update_field_node` → `update_field` @tool
- `chat_node` → 删除（LLM 不调用工具时直接回复就是 chat）
- `continue_pending_node` → 删除（LLM 单次调用可返回多个 tool_calls，不再需要手动队列）

**意图分析（intent phase）的特殊处理**：

意图分析是一个 3 轮问答流程，不适合用单次 Tool Calling。解决方案：

1. 意图分析阶段的逻辑放在 `build_system_prompt()` 中：当 `current_phase == "intent"` 且未完成时，system prompt 指导 LLM 执行问答流程。
2. 不需要单独的节点或工具，LLM 在 system prompt 引导下自然地进行多轮对话。
3. 当 LLM 认为收集够信息时，调用 `generate_field_content(field_name="意图分析")` 工具来生成和保存结果。

#### Step 2.2 — 更新 AgentState 定义

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    project_id: str
    current_phase: str
    creator_profile: str
```

**只有 4 个字段**（比原来 27 个字段减少 85%）。

**对比**:

| 现有字段 | 新状态中 | 去向 |
|----------|---------|------|
| `project_id` | ✅ 保留 | — |
| `current_phase` | ✅ 保留 | — |
| `creator_profile` | ✅ 保留 | — |
| `messages` | ✅ 保留 | — |
| `phase_order` | ❌ 删除 | 工具函数内从 DB 读取 |
| `phase_status` | ❌ 删除 | 工具函数内从 DB 读取 |
| `autonomy_settings` | ❌ 删除 | 暂不使用 |
| `fields` | ❌ 删除 | 工具函数内从 DB 读取 |
| `user_input` | ❌ 删除 | 已在 messages 中 |
| `agent_output` | ❌ 删除 | 已在 messages 中 |
| `waiting_for_human` | ❌ 删除 | 用 LangGraph interrupt 机制 |
| `route_target` | ❌ 删除 | LLM 通过 Tool Calling 自动路由 |
| `is_producing` | ❌ 删除 | 从 tool_end 事件的工具名推断（`PRODUCE_TOOLS`） |
| `use_deep_research` | ❌ 删除 | 工具函数参数 |
| `error` | ❌ 删除 | 异常处理在工具函数内 |
| `tokens_in/out/duration_ms/cost` | ❌ 删除 | LangSmith 或 callback 追踪 |
| `full_prompt` | ❌ 删除 | LangSmith 自动记录 |
| `references` | ❌ 删除 | 前端解析 @ 引用后作为工具参数传递 |
| `referenced_contents` | ❌ 删除 | 工具函数内按需读取 DB |
| `parsed_intent_type` | ❌ 删除 | Tool Calling 自动路由 |
| `parsed_target_field` | ❌ 删除 | 工具参数 |
| `parsed_operation` | ❌ 删除 | 工具参数 |
| `modify_target_field` | ❌ 删除 | 工具返回值 |
| `pending_intents` | ❌ 删除 | LLM 单次调用可返回多个 tool_calls |

### Phase 3: API 层重写

#### Step 3.1 — 重写 `/stream` endpoint

**核心变化**:
1. 删除 `route_intent()` 调用
2. 删除 `if/elif` 分发链（~200 行）
3. 替换为 `graph.astream_events(version="v2")` 循环（~50 行）
4. 所有路由统一 token 级流式

**保留**:
- `_resolve_references()` — 仍需解析 @ 引用，但结果注入到 messages 而非 state
- `_save_result_to_field()` — 移入工具函数内部
- `_build_chat_display()` — 简化或删除（LLM 直接生成用户看到的文本）

#### Step 3.2 — 重写 `/chat` endpoint

**改动**: 使用 `graph.ainvoke()` 替代 `content_agent.run()`
**简化**: 不再需要手动构建 27 字段的 initial_state，只需 4 字段

#### Step 3.3 — 删除或精简的 endpoint

| Endpoint | 处理方式 |
|----------|---------|
| `POST /chat` | 简化，用 graph.ainvoke() |
| `POST /stream` | 重写，用 graph.astream_events() |
| `POST /tool` | 删除，工具调用已内化到 Agent Loop |
| `POST /advance` | 保留，但改为调用 `advance_to_phase` @tool |
| `POST /retry` | 简化 |
| `GET /history` | 不变 |
| `PUT /message` | 不变 |
| `DELETE /message` | 不变 |

### Phase 4: 删除旧代码

#### Step 4.1 — 删除 `backend/core/ai_client.py`

整个文件删除（329 行）。所有对 `ai_client` 的引用替换为 `llm` 或 `llm_mini`。

**影响的文件**:

| 文件 | 引用方式 | 替换为 |
|------|---------|--------|
| `orchestrator.py` | `from core.ai_client import ai_client, ChatMessage` | `from core.llm import llm` + `from langchain_core.messages import HumanMessage, SystemMessage` |
| `api/agent.py` | `from core.ai_client import ai_client, ChatMessage as AIChatMessage` | `from core.llm import llm` |
| `tools/deep_research.py` | `from core.ai_client import ai_client` | `from core.llm import llm` |
| `tools/eval_engine.py` | `from core.ai_client import ai_client, ChatMessage` | `from core.llm import llm` |
| `tools/simulator.py` | `from core.ai_client import ai_client, ChatMessage` | `from core.llm import llm` |
| `tools/field_generator.py` | `from core.ai_client import ai_client, ChatMessage` | `from core.llm import llm` |
| `tools/evaluator.py` | `from core.ai_client import ai_client, ChatMessage` | `from core.llm import llm` |
| `tools/outline_generator.py` | `from core.ai_client import ai_client, ChatMessage` | `from core.llm import llm` |
| `tools/persona_manager.py` | `from core.ai_client import ai_client, ChatMessage` | `from core.llm import llm` |
| `tools/skill_manager.py` | `from core.ai_client import ai_client, ChatMessage` | `from core.llm import llm` |
| `api/blocks.py` (3处) | `from core.ai_client import AIClient, ChatMessage` / `ai_client` | `from core.llm import llm` 或 `get_chat_model()` |

**`blocks.py` 特殊情况**：
`blocks.py` 中有些地方使用 `AIClient()` 构造新实例（而非单例 `ai_client`），这些地方改为 `get_chat_model()` 调用或直接使用 `llm`。

**ChatMessage 替换规则**:
```python
# 旧
ChatMessage(role="system", content="...")
ChatMessage(role="user", content="...")
ChatMessage(role="assistant", content="...")

# 新
SystemMessage(content="...")
HumanMessage(content="...")
AIMessage(content="...")
```

**LLM 调用替换规则**:
```python
# 旧
response = await ai_client.async_chat(messages, temperature=0.7)
content = response.content
tokens_in = response.tokens_in

# 新
response = await llm.ainvoke(messages)  # messages 是 LangChain Message 列表
content = response.content
# token 追踪通过 LangSmith 或 callback 实现
```

**流式调用替换规则**:
```python
# 旧
async for token in ai_client.stream_chat(messages):
    yield token

# 新
async for chunk in llm.astream(messages):
    if chunk.content:
        yield chunk.content
```

#### Step 4.2 — 清理 orchestrator.py

删除的代码（约 2500 行）：
- 旧的 `ContentProductionState`（27 字段）
- `route_intent()` 函数（~320 行）
- 所有阶段节点函数（各 ~80-150 行 × 7 个 ≈ ~800 行）
- `modify_node`, `query_node`, `chat_node` 等（各 ~50-200 行）
- `tool_node`, `generate_field_node`, `read_field_node`, `update_field_node`
- `continue_pending_node`, `route_after_phase`, `route_after_tool`, `route_by_intent`
- 旧的 `create_content_production_graph()`（~150 行）
- `ContentProductionAgent` 类（~100 行）

新增的代码（约 150 行）：
- `AgentState`（4 字段）
- `build_system_prompt()`
- `agent_node()`
- `should_continue()`
- `create_agent_graph()`

**净减少**: ~2000+ 行

### Phase 5: 工具函数中的 DB 操作模式

工具函数需要访问数据库，但 LangChain `@tool` 不直接支持 DI。解决方案：

```python
# 方案：在工具函数内使用 get_db()
from core.database import get_db

@tool
def modify_field(field_name: str, instruction: str, reference_fields: list[str] = []) -> str:
    """修改指定字段的内容。"""
    db = next(get_db())
    try:
        # ... 读取字段、调用 LLM、apply_edits、保存 ...
        db.commit()
        return f"已修改字段「{field_name}」"
    except Exception as e:
        db.rollback()
        return f"修改失败: {str(e)}"
    finally:
        db.close()
```

**project_id 传递问题**：

`@tool` 函数无法直接访问 `AgentState`。解决方案：

1. **方案 A: 闭包注入**（推荐）— 在 API 层创建工具时注入 project_id：
   ```python
   def create_tools_for_project(project_id: str) -> list:
       @tool
       def modify_field(field_name: str, instruction: str) -> str:
           """修改指定字段的内容。"""
           # 这里可以直接使用外层的 project_id
           ...
       return [modify_field, ...]
   ```
   每次请求创建新的工具列表，图也需要重新创建（或使用 `configurable`）。

2. **方案 B: RunnableConfig 传递**（LangGraph 原生方式）：
   ```python
   from langchain_core.runnables import RunnableConfig

   @tool
   def modify_field(field_name: str, instruction: str, config: RunnableConfig) -> str:
       """修改指定字段的内容。"""
       project_id = config["configurable"]["project_id"]
       ...
   ```
   调用图时通过 `config={"configurable": {"project_id": "..."}}` 传入。

**推荐方案 B**：不需要每次重建图，LangGraph 原生支持，性能更好。

---

## 五、@ 引用机制的变化

### 现有机制
前端解析 `@字段名` → 传入 `references: ["字段名"]` → 后端 `_resolve_references()` 查内容 → 注入到 `referenced_contents` state 字段。

### 新机制
@ 引用仍然由前端解析，但注入方式改变：

```python
# API 层：将 @ 引用内容作为用户消息的一部分
if references:
    ref_contents = _resolve_references(db, project_id, references)
    ref_text = "\n".join(f"【{name}】\n{content}" for name, content in ref_contents.items())
    # 附加到用户消息中
    augmented_message = f"{request.message}\n\n---\n以下是用户引用的字段内容：\n{ref_text}"
    input_messages.append(HumanMessage(content=augmented_message))
else:
    input_messages.append(HumanMessage(content=request.message))
```

这样 LLM 自然地看到引用内容，无需在 State 中传递。

---

## 六、非 Agent 场景的 LLM 调用

以下场景不走 Agent Graph，但也要用 `llm` / `llm_mini` 替代 `ai_client`：

| 场景 | 文件 | 调用方式 |
|------|------|---------|
| 字段独立生成（内容块生成按钮） | `api/blocks.py`, `tools/field_generator.py` | `llm.ainvoke()` / `llm.astream()` |
| 摘要生成 | `core/digest_service.py` | `llm_mini.ainvoke()` |
| DeepResearch 综合分析 | `tools/deep_research.py` | `llm.ainvoke()` |
| Eval 引擎（模拟器/评审） | `tools/eval_engine.py` | `llm.ainvoke()` |
| 模拟器（消费者模拟） | `tools/simulator.py` | `llm.ainvoke()` |

替换模式统一：
```python
# 旧
from core.ai_client import ai_client, ChatMessage
messages = [ChatMessage(role="system", content=sp), ChatMessage(role="user", content=up)]
response = await ai_client.async_chat(messages, temperature=0.7)
text = response.content

# 新
from core.llm import llm  # 或 llm_mini
from langchain_core.messages import SystemMessage, HumanMessage
messages = [SystemMessage(content=sp), HumanMessage(content=up)]
response = await llm.ainvoke(messages)
text = response.content
```

---

## 七、设计考量：工具内部的 LLM 流式

### 问题

在 Agent Loop 中，只有 `agent_node` 的 LLM 调用会被直接流式输出给用户。当工具函数（如 `generate_field_content`）内部也调用 LLM 时，这些内部调用的 token 不会自动流式输出。

`astream_events(version="v2")` 实际上**会**捕获嵌套 runnable 的事件。但问题是：
- 工具内部 LLM 生成的内容是"工具结果"（保存到 DB），不应作为"聊天内容"流式输出
- Agent 在工具返回后的总结才是用户在聊天区看到的内容

### 策略

1. **只流式转发 agent 节点的 LLM 输出**（通过 event tags/name 区分来源）
2. **工具执行期间**发送 `tool_start` 事件让用户知道在处理
3. **工具内部 LLM** 的进度可以通过 SSE heartbeat 或 progress 事件体现
4. **未来优化**：对于长时间工具（>10s），可在工具内部通过 callback 发送进度事件

这与 Cursor 的 Agent 模式一致：工具执行时用户看到 "正在执行..." 的状态指示，工具完成后 Agent 用自然语言总结结果。

---

## 八、迁移风险与 Fallback

| 风险 | 影响 | Fallback |
|------|------|---------|
| LLM 不调用工具（该调用时直接回复） | 用户说"修改XX"但 LLM 只是聊天 | system prompt 强化工具使用引导；兜底检测关键词 |
| LLM 调用错误的工具 | 用户说"看看XX"但调用了 modify_field | 工具 docstring 精确描述使用场景；每个工具加入安全检查 |
| Tool Calling 不支持的模型 | 切换到不支持 function calling 的模型 | `get_chat_model()` 检查 provider 是否支持，不支持则降级为 prompt 方式 |
| astream_events 事件格式变化 | LangGraph 版本升级导致事件名变化 | 锁定 langgraph 版本；事件处理加 try/except |
| 工具执行超时 | 深度调研、字段生成可能超过 60s | 工具内部加 timeout；SSE 定期发送 heartbeat |
| project_id 获取失败 | RunnableConfig 传递丢失 | 工具函数内检查，缺失则返回错误信息 |

---

## 九、实施顺序与依赖关系

```
Phase 1: 基础设施（可独立执行，不影响现有功能）
  Step 1.1 新建 llm.py          ← 无依赖
  Step 1.2 扩展 config.py       ← 无依赖
  Step 1.3 新建 agent_tools.py  ← 依赖 Step 1.1
  Step 1.4 更新 requirements.txt ← 无依赖

Phase 2: Agent Graph（核心改造）
  Step 2.1 重写 orchestrator.py  ← 依赖 Phase 1
  Step 2.2 更新 AgentState       ← 包含在 Step 2.1 中

Phase 3: API 层（对外接口改造）
  Step 3.1 重写 /stream          ← 依赖 Phase 2
  Step 3.2 重写 /chat            ← 依赖 Phase 2
  Step 3.3 清理旧 endpoint       ← 依赖 Step 3.1, 3.2

Phase 4: 清理旧代码
  Step 4.1 删除 ai_client.py     ← 依赖 Phase 3（所有引用已替换）
  Step 4.2 清理 orchestrator.py  ← 包含在 Phase 2 中

Phase 5: 工具函数内部 ai_client → llm 替换
  （可与 Phase 2-4 并行，按文件逐个替换）
```

**估算**:
- Phase 1: 新增 ~350 行
- Phase 2: 删除 ~2500 行（orchestrator.py 2733行中绝大部分），新增 ~200 行
- Phase 3: 删除 ~300 行（agent.py 中 stream_chat + 旧辅助函数），新增 ~120 行
- Phase 4: 删除 ~330 行（ai_client.py 整文件）
- Phase 5: 每个文件改动 ~10-30 行（11 个文件 ≈ ~250 行改动）

**总计**: 删除 ~3100 行，新增 ~670 行，净减少 ~2400 行

---

## 十、前端适配

### 10.1 agent-panel.tsx SSE 事件处理

```typescript
// 现有事件处理（保留）
case "user_saved": ...  // 不变
case "token": ...       // 不变
case "done": ...        // 不变
case "error": ...       // 不变

// 需要修改
case "route": ...       // 删除或替换为 tool_start

// 新增事件处理
case "tool_start":
  // 显示 "🔧 正在执行 {tool_name}..."
  setStatusMessage(`🔧 正在${toolNameMap[data.tool]}...`);
  break;

case "tool_end":
  // 更新状态，触发字段刷新
  if (data.field_updated) {
    onContentUpdate?.();
  }
  break;
```

### 10.2 工具名称映射（前端显示友好名称）

```typescript
const toolNameMap: Record<string, string> = {
  "modify_field": "修改字段内容",
  "generate_field_content": "生成字段内容",
  "query_field": "查询字段信息",
  "manage_architecture": "管理项目架构",
  "advance_to_phase": "推进阶段",
  "run_research": "执行调研",
  "run_evaluation": "执行评估",
  "manage_persona": "管理用户画像",
  "generate_outline": "生成大纲",
  "read_field": "读取字段内容",
  "update_field": "更新字段内容",
};
```

### 10.3 PRODUCE_ROUTES 的变化

现有 `PRODUCE_ROUTES` 通过 route_target 判断是否为产出路由。新架构中，这个判断改为通过 `tool_end` 事件的 `field_updated` 字段：

```typescript
// 旧：通过 route 事件判断
if (PRODUCE_ROUTES.includes(currentRoute)) { ... }

// 新：通过 tool_end 事件判断
case "tool_end":
  if (data.field_updated) {
    // 字段已更新，触发左侧工作台刷新
    onContentUpdate?.();
  }
  break;
```

---

## 十一、执行前检查清单

| 检查项 | 说明 |
|--------|------|
| `langchain-openai` 已安装 | `pip install langchain-openai` |
| `.env` 中 `OPENAI_API_KEY` 有效 | LangChain 的 ChatOpenAI 也需要 |
| 所有 `ai_client` 引用已替换 | `grep -r "ai_client" backend/` 结果为空 |
| 所有 `ChatMessage` (自定义) 已替换 | `grep -r "from core.ai_client import" backend/` 结果为空 |
| `AGENT_TOOLS` 列表完整 | 覆盖现有所有操作类型 |
| 工具 docstring 清晰 | LLM 能根据描述正确选择工具 |
| `RunnableConfig` 传递 `project_id` | 所有工具函数能获取 project_id |
| SSE 事件类型对齐 | 前端能处理新的 `tool_start` / `tool_end` 事件 |
| 前端 `route` 事件处理降级 | 过渡期兼容旧的 `route` 事件 |

---

## 十二、执行后验证清单

| 阶段 | 验证方法 |
|------|----------|
| Phase 1 | 1. `from core.llm import llm, llm_mini` 成功 2. `from core.agent_tools import AGENT_TOOLS` 成功 3. `len(AGENT_TOOLS) >= 8` |
| Phase 2 | 1. `from core.orchestrator import agent_graph` 成功 2. `agent_graph.get_graph().nodes` 包含 "agent" 和 "tools" |
| Phase 3 | 1. `/stream` 请求返回 SSE 流 2. 纯聊天返回 `token` 事件 3. "修改@字段" 返回 `tool_start` → `token` → `tool_end` → `done` 4. `content` 事件不再出现 |
| Phase 4 | 1. `grep -r "ai_client" backend/` 无结果 2. `backend/core/ai_client.py` 不存在 |
| Phase 5 | 1. 字段独立生成仍正常 2. 摘要生成正常 3. DeepResearch 正常 4. Eval 引擎正常 |
