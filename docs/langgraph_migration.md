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


### 术语映射（前端显示 ↔ 后端代码）

> 为了对创作者友好，前端和用户面向的文本使用以下术语。后端代码中的变量名保持不变。

| 前端显示（用户看到的） | 后端代码/变量名 | 说明 |
|----------------------|---------------|------|
| **内容块** | `field_name`, `ProjectField`, `ContentBlock` | 项目中的一个内容单元（如"场景库"、"人物设定"） |
| **组** | `phase`, `current_phase` | 组织内容块的分组（如 intent、inner、outer） |

> **注意**：工具参数名（如 `field_name`、`target_phase`）保持英文不变，但工具的 docstring 描述和 LLM 系统提示中使用"内容块"和"组"。


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

所有现有的"节点函数"中涉及实际操作的部分（修改内容块、生成内容、调研、管理架构等），转化为 LangChain `@tool` 函数。

> **docstring 设计原则**：docstring 是 LLM 选择工具的唯一依据（通过 `bind_tools` 转化为 JSON Schema 中的 `description` 字段）。
> 必须包含：① 做什么（一句话）② 什么时候用 ③ 与易混淆工具的区分 ④ 参数说明 + 示例值。
> 与 `build_system_prompt` 中的消歧规则互补——system prompt 提供全局规则，docstring 提供工具级指引。

```python
"""
Agent 工具定义
使用 LangChain @tool 装饰器，让 LLM 通过 Tool Calling 自动选择。

每个工具的 docstring 会被 bind_tools() 提取为 function calling 的 description，
是 LLM 决定"什么时候调什么工具"的核心依据。

工具函数内部通过 RunnableConfig 获取 project_id 等上下文，
通过 DB session 读写数据，不依赖 AgentState 传递。
"""
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from typing import Optional


@tool
def modify_field(
    field_name: str,
    instruction: str,
    reference_fields: list[str] = [],
    config: RunnableConfig = None,
) -> str:
    """修改指定内容块的已有内容。当用户要求修改、调整、重写、优化某个内容块的文本时使用。

    ⚠️ 这是修改【已有内容】（改文字），不是创建新内容块（改结构）。
    - 创建/删除/移动内容块 → 请用 manage_architecture
    - 内容块为空需要首次生成 → 请用 generate_field_content

    修改流程：读取当前内容 → 根据指令生成修改方案 → 返回预览（含 Track Changes 标记）。
    如果修改较大，会返回 status="need_confirm" 等待用户确认。

    Args:
        field_name: 要修改的目标内容块名称（如"场景库"、"逐字稿1"）
        instruction: 用户的具体修改指令（如"把5个模块改成7个"、"语气更专业一些"）
        reference_fields: 需要参考的其他内容块名称列表（如用户说"参考@用户画像来修改"）
    """
    # 实现：读取内容块 → 构建 prompt → LLM 生成 edits → apply_edits
    ...


@tool
def generate_field_content(
    field_name: str,
    instruction: str = "",
    config: RunnableConfig = None,
) -> str:
    """为指定内容块生成内容。当内容块为空、或用户要求重新生成全部内容时使用。

    与 modify_field 的区别：
    - generate = 从零生成（内容块为空或需要全部重写）
    - modify = 在已有内容基础上局部修改

    Args:
        field_name: 要生成内容的内容块名称（如"场景库"、"用户画像"）
        instruction: 额外的生成指令或要求（可选，如"要包含3个案例"、"用故事化风格"）
    """
    ...


@tool
def query_field(field_name: str, question: str, config: RunnableConfig = None) -> str:
    """查询内容块并回答相关问题。当用户想了解、分析、总结某个内容块时使用。

    典型场景：
    - "@场景库 这个内容怎么样" → query_field("场景库", "怎么样")
    - "帮我总结一下用户画像的核心洞察" → query_field("用户画像", "核心洞察是什么")

    与 read_field 的区别：query_field 会用 LLM 分析并回答，read_field 只返回原文。

    Args:
        field_name: 要查询的内容块名称
        question: 用户的具体问题
    """
    ...


@tool
def read_field(field_name: str, config: RunnableConfig = None) -> str:
    """读取指定内容块的完整原始内容并返回。当你需要查看内容块的完整文本时使用。

    典型场景：
    - 在修改前先读取当前内容
    - 用户说"看看场景库" → read_field("场景库")
    - 需要判断内容块是否为空（为空则用 generate_field_content）

    Args:
        field_name: 要读取的内容块名称
    """
    ...


@tool
def update_field(field_name: str, content: str, config: RunnableConfig = None) -> str:
    """直接用给定内容完整覆写指定内容块。仅当用户提供了完整的新内容要求直接替换时使用。

    ⚠️ 这会直接覆盖全部内容，没有预览和确认流程。
    - 局部修改（保留大部分原文，改动部分）→ 请用 modify_field
    - 从零生成（让 AI 写）→ 请用 generate_field_content
    - 此工具适用于：用户自己写好了内容，要你直接保存

    Args:
        field_name: 要更新的内容块名称
        content: 新的完整内容（将替换全部现有内容）
    """
    ...


@tool
def manage_architecture(
    operation: str, target: str, details: str = "", config: RunnableConfig = None
) -> str:
    """管理项目结构：添加/删除/移动内容块或组。当用户要求改变项目的结构时使用。

    ⚠️ 这是改【项目结构】（增删内容块/组），不是改内容块里的文字。
    - 改文字内容 → 请用 modify_field
    - 改结构 → 用此工具

    典型场景：
    - "帮我加一个新字段" → manage_architecture("add_field", "新字段名", "字段描述")
    - "把这个阶段删掉" → manage_architecture("remove_phase", "design_outer")
    - "把场景库移到用户画像后面" → manage_architecture("move_field", "场景库", "after:用户画像")
    - "在内涵设计补充一个内容块" → manage_architecture("add_field", "新内容块名", "phase:design_inner")

    Args:
        operation: 操作类型 — add_field / remove_field / move_field / add_phase / remove_phase
        target: 操作目标（内容块名或组名）
        details: 操作详情（如新内容块的描述、目标位置、所属组等）
    """
    ...


@tool
def advance_to_phase(target_phase: str = "", config: RunnableConfig = None) -> str:
    """推进项目到下一组或跳转到指定组。

    当用户说这些话时使用：
    - "继续" / "下一步" / "进入下一阶段" → advance_to_phase("")（自动下一组）
    - "进入外延设计" / "开始消费者调研" → advance_to_phase("design_outer") / advance_to_phase("research")

    ⚠️ 与 manage_architecture 的区别：
    - "进入XX" = 推进流程 → advance_to_phase
    - "在XX里加字段" = 改结构 → manage_architecture

    Args:
        target_phase: 目标组名称（如 "research"、"design_inner"、"produce_outer"）。
                      为空字符串表示自动进入下一组。
    """
    ...


@tool
def run_research(
    query: str, research_type: str = "consumer", config: RunnableConfig = None
) -> str:
    """执行调研。

    两种类型：
    - consumer（消费者调研）：分析目标用户画像、痛点、需求。
      触发词："开始消费者调研"、"做用户调研"
    - generic（通用深度调研）：搜索并整理特定主题的资料。
      触发词："帮我调研一下X市场"、"搜索Y的资料"、"对Z做个调研"

    Args:
        query: 调研主题或查询内容（如"目标用户痛点分析"、"中国教育培训市场趋势"）
        research_type: "consumer"（消费者调研）或 "generic"（通用深度调研）
    """
    ...


@tool
def manage_persona(
    operation: str, persona_data: str = "", config: RunnableConfig = None
) -> str:
    """管理消费者画像/角色。生成、查看、编辑用户画像。

    典型场景：
    - "看看有哪些人物" → manage_persona("list")
    - "再生成一个程序员用户" → manage_persona("generate", "程序员")
    - "补充一个角色，22岁应届毕业生" → manage_persona("create", "22岁应届毕业生")

    Args:
        operation: list（查看全部）/ create（手动创建）/ generate（AI 生成）/ update（更新）/ delete（删除）
        persona_data: 角色描述或数据（创建/生成/更新时需要）
    """
    ...


@tool
def run_evaluation(config: RunnableConfig = None) -> str:
    """对项目内容执行全面质量评估，生成评估报告。

    当用户说"评估一下"、"检查内容质量"、"帮我评一下"时使用。
    """
    ...


@tool
def generate_outline(topic: str = "", config: RunnableConfig = None) -> str:
    """生成内容大纲/结构规划。帮助创作者规划内容的整体架构。

    典型场景：
    - "帮我设计一下大纲" → generate_outline()
    - "这个内容怎么组织比较好" → generate_outline()
    - "做一个关于AI培训的课程大纲" → generate_outline("AI培训课程")

    Args:
        topic: 大纲主题（为空则基于项目意图自动规划）
    """
    ...


@tool
def manage_skill(
    operation: str,
    skill_name: str = "",
    target_field: str = "",
    config: RunnableConfig = None,
) -> str:
    """管理和使用写作技能/风格。查看可用技能、用特定风格重写内容。

    典型场景：
    - "有什么技能可以用" → manage_skill("list")
    - "用专业文案帮我写场景库" → manage_skill("apply", "专业文案", "场景库")
    - "用故事化方式重写" → manage_skill("apply", "故事化", "目标内容块名")

    Args:
        operation: list（查看可用技能）/ apply（应用技能到内容）
        skill_name: 技能名称（如"专业文案"、"故事化"、"批判分析"）
        target_field: 要应用技能的内容块名称
    """
    ...


# ============== 工具列表（注册到 Agent） ==============

AGENT_TOOLS = [
    modify_field,
    generate_field_content,
    query_field,
    read_field,
    update_field,
    manage_architecture,
    advance_to_phase,
    run_research,
    manage_persona,
    run_evaluation,
    generate_outline,
    manage_skill,
]
```

**关键设计要点**：

1. **docstring 就是 LLM 的"使用说明书"**：`bind_tools()` 会将每个工具的 docstring + Args 转化为 OpenAI function calling 的 JSON Schema，LLM 据此决定调用哪个工具、传什么参数
2. **与 system prompt 互补**：system prompt 提供全局消歧规则（4 对消歧）和特殊流程指南；docstring 提供工具级的"什么时候用 / 不要用"指引
3. **参数通过 `Args` 描述**：LLM 自动提取参数名和类型
4. **`config: RunnableConfig`**：LangChain 标准参数，从中提取 `project_id` 等上下文（通过 `config["configurable"]["project_id"]`）
5. **工具函数内部可以访问 DB**（通过 `get_db()`），不需要从 State 传递
6. **工具函数返回字符串**：LLM 会看到返回值并决定下一步（继续调工具 or 回复用户）
7. **添加新工具**只需定义 `@tool` 函数并加入 `AGENT_TOOLS` 列表

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
    构建 system prompt — Agent 行为的「宪法」。
    
    设计原则（以终为始）：
    - 取代原 route_intent() 中的 5000 字意图分类 prompt
    - 取代原 chat_node() 中的能力介绍 prompt
    - 取代原硬编码规则（@ 引用路由、意图阶段检测）
    - 与 @tool docstrings 互补：system prompt 提供上下文和规则，
      docstrings 提供"什么时候用这个工具"的说明
    """
    creator_profile = state.get("creator_profile", "")
    current_phase = state.get("current_phase", "intent")
    project_id = state.get("project_id", "")

    # ---- 动态段落 1: 内容块索引 ----
    # 来自 digest_service（impl_v3 话题二），初始迁移时可跳过
    field_index_section = ""
    if project_id:
        try:
            from core.digest_service import build_field_index
        except ImportError:
            build_field_index = None
        fi = build_field_index(project_id) if build_field_index else None
        if fi:
            field_index_section = f"""
## 项目内容块索引
以下是本项目所有内容块及其摘要，按组归类。
用途：帮你定位与用户指令相关的内容块，选择正确的工具参数（field_name）。
**注意**：摘要只是索引，不代表完整内容。需要完整内容时请使用 read_field 工具。

{fi}
"""

    # ---- 动态段落 2: 组状态 ----
    phase_context = ""
    if project_id:
        try:
            from core.models.database import get_db
            from core.models.project import Project
            db = next(get_db())
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                ps = project.phase_status or {}
                po = project.phase_order or []
                current_status = ps.get(current_phase, "pending")
                phase_context = f"组状态: {current_status}\n项目组顺序: {' → '.join(po)}"
            db.close()
        except Exception:
            pass

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

## 你的能力
1. **意图分析** — 通过 3 个问题帮创作者明确内容目标（做什么、给谁看、期望行动）
2. **消费者调研** — 使用 DeepResearch 深度分析目标用户画像和痛点
3. **内容规划** — 设计内容大纲和架构（组、内容块的组织方式）
4. **内容生成** — 根据设计方案为各内容块生成具体内容
5. **内容修改** — 根据指令修改已有内容，支持 Track Changes 预览
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
- 「帮我加/新增/补充一个字段/内容块」→ **manage_architecture**（创建新的结构）
- 「修改/调整/重写场景库的内容」「把5个改成7个」→ **modify_field**（改已有文本）
- **判断标准**：用户想改变项目结构（增删内容块/组）→ manage_architecture；想改文字内容 → modify_field

### 2. "进入阶段" vs "在阶段里操作"
- 「进入外延设计」「开始下一阶段」「继续」→ **advance_to_phase**
- 「在外延设计加一个字段」→ **manage_architecture**
- **判断标准**：有"进入/开始/继续/下一步"且没有具体操作词 → advance_to_phase

### 3. "消费者调研" vs "通用调研"
- 「开始消费者调研」「做用户调研」→ run_research(research_type="consumer")
- 「帮我调研一下X市场」「搜索Y的资料」→ run_research(research_type="generic")

### 4. "生成" vs "修改"
- 内容块为空（索引中无摘要或标记为空）→ **generate_field_content**
- 内容块已有内容 → **modify_field**
- 不确定时，先用 read_field 查看内容块是否为空

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
2. 一次对话中可以调用多个工具（如「删掉这个字段，再帮我生成一个新的」→ manage_architecture + generate_field_content）
3. 工具执行完成后，用简洁友好的中文告诉用户结果
4. 使用中文回复，语气专业但亲切
5. 如果不确定用户意图，先确认再操作，不要猜测
"""


async def agent_node(state: AgentState) -> dict:
    """
    Agent 决策节点。
    用 bind_tools 的 LLM 决定：直接回复 or 调用工具。
    """
    from langchain_core.messages import trim_messages

    system_prompt = build_system_prompt(state)

    # Token 预算管理：保留最近消息，裁剪过早历史
    # Checkpointer 会累积所有历史（包括 ToolMessage），可能超出 context window
    trimmed = trim_messages(
        state["messages"],
        max_tokens=100_000,    # 为 system prompt (~5K) + 回复 (~10K) 预留
        token_counter=llm,     # 使用 LLM 内置 token 计数
        strategy="last",       # 保留最新消息
        start_on="human",      # 确保从 HumanMessage 开始
        include_system=False,  # system prompt 由我们单独管理
        allow_partial=False,   # 不截断单条消息
    )

    # 将 system prompt 作为第一条消息注入
    # 注意：每次调用都重新生成 system prompt（因为内容块索引可能变化）
    messages_with_system = [SystemMessage(content=system_prompt)] + trimmed

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
    创建 Agent 图（带 Checkpointer）。

    结构：
        agent_node ──(有tool_calls)──→ tool_node ──→ agent_node（循环）
            │
            └──(无tool_calls)──→ END

    Checkpointer 使对话状态在请求间自动累积。
    """
    from langgraph.checkpoint.memory import MemorySaver

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

    # Checkpointer：跨请求保持对话状态（ToolMessage 等）
    # 当前使用 MemorySaver（内存，重启后丢失，自动从 DB Bootstrap）
    # 生产升级（一行切换）：
    #   from langgraph.checkpoint.sqlite import SqliteSaver
    #   checkpointer = SqliteSaver.from_conn_string("agent_checkpoints.db")
    checkpointer = MemorySaver()

    return graph.compile(checkpointer=checkpointer)


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

    # ---- 共创模式分流（详见 implementation_plan_v3.md 5.6-5.7 节）----
    # 共创是纯角色扮演对话，不走 Agent Graph，不使用 Checkpointer
    if getattr(request, 'mode', 'assistant') == "cocreation":
        return StreamingResponse(
            handle_cocreation_stream(request, db, project, user_msg.id),
            media_type="text/event-stream",
        )

    # ---- 助手模式：走 Agent Graph ----

    # 处理 @ 引用
    augmented_message = request.message
    if request.references:
        ref_contents = _resolve_references(db, request.project_id, request.references)
        if ref_contents:
            ref_text = "\n".join(f"【{n}】\n{c}" for n, c in ref_contents.items())
            augmented_message = f"{request.message}\n\n---\n以下是用户引用的内容块：\n{ref_text}"

    # 构建 thread 配置（Checkpointer 通过 thread_id 定位历史）
    thread_id = f"{request.project_id}:assistant"
    config = {
        "configurable": {
            "thread_id": thread_id,
            "project_id": request.project_id,
        }
    }

    # Bootstrap 检查：首次请求（或服务器重启后）从 DB 加载种子历史
    try:
        existing = await agent_graph.aget_state(config)
        has_checkpoint = existing and existing.values and existing.values.get("messages")
    except Exception:
        has_checkpoint = False

    if not has_checkpoint:
        db_history = _load_seed_history(db, request.project_id)
        input_messages = db_history + [HumanMessage(content=augmented_message)]
    else:
        input_messages = [HumanMessage(content=augmented_message)]

    # 构建 AgentState（只有 4 个字段，messages 由 Checkpointer 累积）
    input_state = {
        "messages": input_messages,
        "project_id": request.project_id,
        "current_phase": current_phase,
        "creator_profile": project.creator_profile.to_prompt_context() if project.creator_profile else "",
    }

    # 产出类工具列表（这些工具执行后前端需刷新左侧面板）
    PRODUCE_TOOLS = {"modify_field", "generate_field_content", "manage_architecture", "advance_to_phase", "update_field", "execute_prompt_update"}

    async def event_generator():
        yield sse_event({"type": "user_saved", "message_id": user_msg.id})

        full_content = ""
        current_tool = None
        tools_used = []        # 记录本次调用的工具名
        is_producing = False   # 是否有内容块产出（从工具名推断）

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
                tools_used.append(tool_name)
                yield sse_event({"type": "tool_start", "tool": tool_name})

            # 工具结束
            elif kind == "on_tool_end":
                tool_output = event["data"].get("output", "")
                field_updated = current_tool in PRODUCE_TOOLS
                if field_updated:
                    is_producing = True

                # modify_field 特殊处理：返回 JSON，提取结构化数据给前端
                # 详见 implementation_plan_v3.md Step 3.3
                if current_tool == "modify_field":
                    try:
                        import json as _json
                        result = _json.loads(tool_output)
                        if result.get("status") == "need_confirm":
                            yield sse_event({"type": "modify_confirm_needed", **{k: result[k] for k in ("target_field", "edits", "summary") if k in result}})
                        elif result.get("status") == "applied":
                            yield sse_event({"type": "modify_preview", **{k: result.get(k) for k in ("target_field", "original_content", "new_content", "changes", "summary")}})
                            field_updated = True
                    except Exception:
                        pass  # 降级走通用逻辑
                else:
                    yield sse_event({
                        "type": "tool_end",
                        "tool": current_tool,
                        "output": tool_output[:500],
                        "field_updated": field_updated,
                    })
                current_tool = None

        # 图执行完毕 → 保存用户可见消息到 ChatMessage DB + 发送 done
        # 注意：ToolMessage 和 AIMessage(tool_calls) 由 Checkpointer 保存，不需要存 DB
        agent_msg = ChatMessage(
            id=generate_uuid(),
            project_id=request.project_id,
            role="assistant",
            content=full_content,
            message_metadata={
                "phase": current_phase,
                "mode": "assistant",
                "tools_used": tools_used,  # 记录调用了哪些工具
            },
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

> **扩展说明**：以上是迁移现有功能的初始工具集。`implementation_plan_v3.md` 中定义的新功能会追加新工具：
> - `update_prompt` / `execute_prompt_update`：提示词修改（话题一）
> - 共创模式不使用 @tool，直接走 `llm.astream()`
>
> 添加新工具只需在 `agent_tools.py` 中定义 `@tool` 函数并加入 `AGENT_TOOLS` 列表即可。

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
- `design_inner_node` / `produce_inner_node` / `design_outer_node` / `produce_outer_node` → 合并为 `generate_field_content` @tool（根据内容块名和组自动选择 prompt）
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

1. 意图分析组的逻辑放在 `build_system_prompt()` 中：当 `current_phase == "intent"` 且未完成时，system prompt 指导 LLM 执行问答流程。
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
    """修改指定内容块的内容。"""
    db = next(get_db())
    try:
        # ... 读取内容块、调用 LLM、apply_edits、保存 ...
        db.commit()
        return f"已修改内容块「{field_name}」"
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
           """修改指定内容块的内容。"""
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
       """修改指定内容块的内容。"""
       project_id = config["configurable"]["project_id"]
       ...
   ```
   调用图时通过 `config={"configurable": {"project_id": "..."}}` 传入。

**推荐方案 B**：不需要每次重建图，LangGraph 原生支持，性能更好。

---

## 五、@ 引用机制的变化

### 现有机制
前端解析 `@内容块名` → 传入 `references: ["内容块名"]` → 后端 `_resolve_references()` 查内容 → 注入到 `referenced_contents` state 字段 → 在 `route_intent` 硬编码规则中自动路由到 modify/query。

### 新机制
@ 引用仍然由前端解析，但路由逻辑和注入方式都改变了：

**两层协作**：
1. **API 层**：将 @ 引用内容附加到用户消息中，让 LLM 能**看到**引用内容
2. **system prompt**：`@ 引用约定` 章节告诉 LLM 如何**理解和处理** @ 引用（选择正确的工具 + 参数）

```python
# API 层（stream_chat 端点）：将 @ 引用内容附加到 HumanMessage
references = request.references or []
if references:
    ref_contents = _resolve_references(db, request.project_id, references)
    if ref_contents:
        ref_text = "\n".join(f"【{name}】\n{content[:2000]}" for name, content in ref_contents.items())
        # 附加到用户消息中，LLM 会自然看到引用内容
        augmented_message = f"{request.message}\n\n---\n以下是用户引用的内容块：\n{ref_text}"
    else:
        augmented_message = request.message
else:
    augmented_message = request.message

input_messages = [HumanMessage(content=augmented_message)]
```

**设计要点**：
- 引用内容截断到 2000 字（防止超长内容撑爆 context window）
- 引用名用【】包裹，与 system prompt 中的 `@ 引用约定` 格式一致
- LLM 看到引用内容后，结合 system prompt 的消歧规则，自动选择 `modify_field` / `query_field` / `read_field`
- 引用中的内容块名会被 LLM 提取为工具参数的 `field_name`
- **不再需要硬编码的 `query_keywords` 列表来判断是查询还是修改** — 这完全由 LLM 理解语义来决定

### 为什么取代硬编码规则是更好的

现有硬编码（`orchestrator.py` 第 261-287 行）的问题：
- 用关键词列表 `["是什么", "什么意思", "解释", ...]` 判断是否为查询 — 无法覆盖所有表述
- 默认 @ 引用 = 修改 — 但用户可能在引用内容块时有其他意图（如"参考@A和@B设计大纲"）
- 无法处理复合意图（如"看看@场景库，然后帮我修改一下"）

新方式让 LLM 全语义理解，只需要在 system prompt 中给出几个示例即可。

---

## 六、非 Agent 场景的 LLM 调用

以下场景不走 Agent Graph，但也要用 `llm` / `llm_mini` 替代 `ai_client`：

| 场景 | 文件 | 调用方式 |
|------|------|---------|
| 内容块独立生成（内容块生成按钮） | `api/blocks.py`, `tools/field_generator.py` | `llm.ainvoke()` / `llm.astream()` |
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

## 八、上下文工程（Context Engineering）

### 8.1 现状问题诊断

当前的对话历史处理存在 **5 个根本性缺陷**：

#### 问题 1：ToolMessage 不持久化

LangGraph 的 Agent Loop 在单次请求内产生多条消息：

```
HumanMessage("修改场景库的5个模块改成7个")
→ AIMessage(tool_calls=[{name: "modify_field", args: {field_name: "场景库", instruction: "..."}}])
→ ToolMessage("✅ 已修改内容块「场景库」，共2处修改")
→ AIMessage("我已经帮你把场景库的模块从5个改成了7个...")
```

但当前代码只保存了：
- HumanMessage → `ChatMessage(role="user")`
- 最终 AIMessage → `ChatMessage(role="assistant")`

中间的 **AIMessage(with tool_calls)** 和 **ToolMessage** 完全丢失。下一次请求时，Agent 不知道自己曾经调用过什么工具、用了什么参数。

**后果**：用户说"撤销刚才的修改"或"刚才改少了，再加一个"，Agent 没有上下文。

#### 问题 2：20 条硬截断、无摘要

```python
chat_history = []
for m in current_phase_msgs[-20:]:  # 硬截断，超过直接丢弃
```

超过 20 条的历史直接丢弃，没有任何摘要或压缩。对于频繁对话的项目，Agent 很快就会"失忆"。

#### 问题 3：组过滤过于严格

```python
if msg_phase is None or msg_phase == current_phase:
    current_phase_msgs.append(m)
```

切换组后，之前组的所有对话完全不可见。但在新架构中，Agent 可以跨组操作（如在 inner 组修改 intent 组的内容块），组过滤会导致上下文断裂。

#### 问题 4：工具调用无会话上下文

当前的 `modify_node` 等节点函数在 `/stream` 手动分发中执行时，只收到由 API 层构建的简化 `initial_state`（仅包含最近 10-20 条 user/assistant 消息），不包含 Agent Loop 中间产生的 ToolMessage。每次工具调用都是"无记忆"的独立调用。

#### 问题 5：无持久化 Checkpointer

当前文档中 `create_agent_graph()` 未配置 checkpointer。这意味着即使正确使用 LangGraph，每次 HTTP 请求都是全新的图执行，无法在请求间累积状态（包括 ToolMessage）。

---

### 8.2 目标架构：LangGraph Checkpointer + ChatMessage DB 双层

```
┌────────────────────────────────────────────────────────────┐
│                        数据层                               │
│                                                            │
│  ┌─────────────────────────┐  ┌──────────────────────────┐ │
│  │ MemorySaver (Checkpointer)│  │ ChatMessage 表            │ │
│  │                          │  │ (前端展示 + 审计日志)      │ │
│  │ 存储内容：                │  │                            │ │
│  │ • HumanMessage           │  │ 存储内容：                  │ │
│  │ • AIMessage(含tool_calls)│  │ • user 消息                │ │
│  │ • ToolMessage            │  │ • assistant 最终回复        │ │
│  │ • 完整 AgentState        │  │ • mode/phase/tools_used    │ │
│  │                          │  │                            │ │
│  │ 用途：                    │  │ 用途：                     │ │
│  │ • LLM 推理上下文          │  │ • 前端聊天面板展示          │ │
│  │ • 跨请求状态累积          │  │ • 历史导出 / 编辑重发       │ │
│  │ • ToolMessage 保留        │  │ • 审计日志                 │ │
│  └───────────┬──────────────┘  └─────────────┬────────────┘ │
│              │                                │              │
└──────────────┼────────────────────────────────┼──────────────┘
               │                                │
      ┌────────▼────────┐             ┌─────────▼──────────┐
      │  agent_node       │             │ 前端 agent-panel    │
      │  (LLM 推理)       │             │ (消息展示)           │
      │  看到完整对话链     │             │ 只展示 user/assistant│
      └──────────────────┘             └────────────────────┘
```

**设计原则**：
1. **Checkpointer** = LLM 的"大脑记忆"（完整，包含工具调用链、ToolMessage）
2. **ChatMessage DB** = 给用户看的"对话记录"（精简，只有 user + assistant 最终回复）
3. 两者各司其职，不互相替代
4. **升级路径**：当前用 `MemorySaver`（内存），未来可一行切换到 `SqliteSaver` / `PostgresSaver` 实现持久化

---

### 8.3 Checkpointer 配置

**Graph 构建变化**（`backend/core/orchestrator.py`）：

```python
from langgraph.checkpoint.memory import MemorySaver

def create_agent_graph():
    """
    创建 Agent 图（带 Checkpointer）。
    Checkpointer 使请求间对话状态自动累积。
    """
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(AGENT_TOOLS))
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    # Checkpointer：跨请求保持对话状态
    # 当前使用 MemorySaver（内存，重启丢失）
    # 生产环境升级：
    #   from langgraph.checkpoint.sqlite import SqliteSaver
    #   checkpointer = SqliteSaver.from_conn_string("agent_checkpoints.db")
    checkpointer = MemorySaver()

    return graph.compile(checkpointer=checkpointer)


# 全局实例
agent_graph = create_agent_graph()
```

**Thread ID 策略**：

| 场景 | Thread ID 格式 | 说明 |
|------|---------------|------|
| 助手模式 | `{project_id}:assistant` | 同项目所有助手对话共享线程，跨组累积 |
| 共创模式 | 不走 Graph，不使用 checkpointer | 共创直接用 `llm.astream()`，历史从 DB 加载 |

> **注意**：共创模式不经过 Agent Graph（见 `implementation_plan_v3.md` 5.7 节），因此不使用 checkpointer。共创历史仍从 ChatMessage DB 加载。

---

### 8.4 对话历史加载策略变化

**核心变化**：使用 Checkpointer 后，**不再需要手动从 DB 加载全部历史**。每次请求只传递新消息，Checkpointer 自动提供之前的上下文。

**变化前**（当前代码）：

```python
# 1. 从 DB 加载全部历史
history_msgs = db.query(ChatMessage).filter(...).all()
# 2. 按组过滤（旧逻辑，已删除）
current_phase_msgs = [m for m in history_msgs if m_phase == current_phase]
# 3. 取最近 20 条
chat_history = [convert(m) for m in current_phase_msgs[-20:]]
# 4. 拼接新消息
input_state = {"messages": chat_history + [HumanMessage(content=new_msg)]}
```

**变化后**（新架构）：

```python
# 1. 构建 thread 配置（Checkpointer 通过 thread_id 定位历史）
thread_id = f"{request.project_id}:assistant"
config = {
    "configurable": {
        "thread_id": thread_id,
        "project_id": request.project_id,
    }
}

# 2. 检查是否需要 Bootstrap（首次请求 / 服务器重启后）
try:
    existing = await agent_graph.aget_state(config)
    has_checkpoint = existing and existing.values and existing.values.get("messages")
except Exception:
    has_checkpoint = False

if not has_checkpoint:
    # 首次使用：从 DB 加载历史作为种子
    db_history = _load_seed_history(db, request.project_id)
    input_messages = db_history + [HumanMessage(content=augmented_message)]
else:
    # 已有 checkpoint：只传新消息，Checkpointer 自动补全历史
    input_messages = [HumanMessage(content=augmented_message)]

# 3. 构建精简 input_state
input_state = {
    "messages": input_messages,
    "project_id": request.project_id,
    "current_phase": current_phase,
    "creator_profile": creator_profile_str,
}
```

**`_load_seed_history` 函数**（Bootstrap 用，仅在无 checkpoint 时调用）：

```python
def _load_seed_history(db: Session, project_id: str, limit: int = 30) -> list[BaseMessage]:
    """
    从 ChatMessage DB 加载历史，用于 Checkpointer 的 Bootstrap。
    注意：DB 中只有 user/assistant 消息，没有 ToolMessage。
    Bootstrap 后 Checkpointer 会接管，后续请求不再调用此函数。
    """
    msgs = db.query(ChatMessage).filter(
        ChatMessage.project_id == project_id,
    ).order_by(ChatMessage.created_at.desc()).limit(limit).all()

    msgs.reverse()  # 时间正序
    result = []
    for m in msgs:
        meta = m.message_metadata or {}
        mode = meta.get("mode", "assistant")
        if mode != "assistant":
            continue  # 只加载助手模式消息
        if m.role == "user":
            result.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            result.append(AIMessage(content=m.content))
    return result
```

---

### 8.5 Token 预算管理

即使 Checkpointer 保存了完整历史，也不能把所有消息都发给 LLM（context window 有限）。

**解决方案**：在 `agent_node` 中使用 LangChain 的 `trim_messages`：

```python
from langchain_core.messages import trim_messages

async def agent_node(state: AgentState) -> dict:
    system_prompt = build_system_prompt(state)

    # Token 预算管理：保留最近的消息，裁剪过早的历史
    trimmed = trim_messages(
        state["messages"],
        max_tokens=100_000,    # 为 system prompt (~5K) + 回复 (~10K) 预留空间
        token_counter=llm,     # 使用 LLM 内置 token 计数器
        strategy="last",       # 保留最新消息
        start_on="human",      # 确保从 HumanMessage 开始（不截断到孤立的 ToolMessage）
        include_system=False,  # system prompt 由我们单独管理
        allow_partial=False,   # 不截断单条消息
    )

    messages_with_system = [SystemMessage(content=system_prompt)] + trimmed
    llm_with_tools = llm.bind_tools(AGENT_TOOLS)
    response = await llm_with_tools.ainvoke(messages_with_system)
    return {"messages": [response]}
```

**Token 预算分配**（以 GPT-4o 128K 为例）：

| 组件 | 预算 | 说明 |
|------|------|------|
| System Prompt | ~5,000 tokens | 角色定义 + 内容块索引 + 工具描述 + 交互规则 |
| 对话历史 | ~100,000 tokens | `trim_messages` 管理，包含 ToolMessage |
| LLM 回复 + 工具参数 | ~10,000 tokens | 预留 |
| 安全余量 | ~13,000 tokens | — |
| **总计** | **~128,000 tokens** | — |

> **未来优化方向**：当历史过长时，可在 `trim_messages` 之前增加一步"老消息摘要"：将被裁剪的消息用 `llm_mini` 生成摘要，作为 SystemMessage 的一部分注入。这能在有限 token 内保留更多上下文。当前阶段不实现。

---

### 8.6 消息保存策略

**Agent 执行完毕后**，只保存用户可见的消息到 ChatMessage DB：

```python
# 在 event_generator 结束后（graph 执行完毕）
agent_msg = ChatMessage(
    id=generate_uuid(),
    project_id=request.project_id,
    role="assistant",
    content=full_content,  # 从 token 流收集的 Agent 最终文字回复
    message_metadata={
        "phase": current_phase,
        "mode": "assistant",
        "tools_used": list(tools_used_in_this_request),  # 记录调用了哪些工具名
    },
)
db.add(agent_msg)
db.commit()
```

**不保存到 ChatMessage DB**（但 Checkpointer 中有）：
- AIMessage 中的 `tool_calls` 细节
- ToolMessage（工具返回值）
- Agent Loop 中间的 AIMessage

**对前端的影响**：无。前端仍然只看到 `user` 和 `assistant` 消息。

---

### 8.7 组切换不再丢失上下文

当前的组过滤（`msg_phase == current_phase`）在新架构中 **不再需要**：

1. Checkpointer 的 `thread_id = {project_id}:assistant` 不区分组
2. 所有组的对话都在同一个线程中自然累积
3. `current_phase` 只影响 `build_system_prompt` 中的上下文提示，不影响消息过滤
4. `trim_messages` 按时间顺序保留最新消息，自然覆盖跨组场景

**前端组过滤**：ChatMessage DB 中仍然记录 `phase` metadata，前端可以按需过滤展示（只显示当前组的消息），但这是 **展示层过滤**，不影响 LLM 的上下文。

---

### 8.8 跨模式上下文桥接

已在 `implementation_plan_v3.md` 5.8 节设计。核心要点：

- **助手 → 共创**：不注入（共创角色不知道助手的存在）
- **共创 → 助手**：自动注入最近共创对话摘要到 `build_system_prompt()`
- **桥接数据源**：从 ChatMessage DB 读取（不从 Checkpointer），因为桥接只需要摘要

```python
# build_system_prompt 中追加
cocreation_bridge = build_assistant_context_with_bridge(project_id)
# → 返回最近共创对话的摘要（≤10条消息）
```

---

### 8.9 上下文工程迁移步骤

| 步骤 | 内容 | 所属阶段 |
|------|------|---------|
| 1 | `create_agent_graph()` 添加 `MemorySaver` checkpointer | Phase 2 |
| 2 | `agent_node()` 添加 `trim_messages` token 预算管理 | Phase 2 |
| 3 | `/stream` endpoint 改为只传新消息 + Bootstrap 逻辑 | Phase 3 |
| 4 | `/stream` endpoint 结束后只保存 user-facing 消息 | Phase 3 |
| 5 | 删除旧的组过滤 + 20 条硬截断逻辑 | Phase 3 |
| 6 | 共创桥接函数 `build_assistant_context_with_bridge()` | Phase 5 (共创) |

> **生产升级（可选，当前不实施）**：
> - `pip install langgraph-checkpoint-sqlite`
> - 将 `MemorySaver()` 替换为 `SqliteSaver.from_conn_string("agent_checkpoints.db")`
> - 一行改动，无其他变化

---

## 九、迁移风险与 Fallback

| 风险 | 影响 | Fallback |
|------|------|---------|
| LLM 不调用工具（该调用时直接回复） | 用户说"修改XX"但 LLM 只是聊天 | system prompt 强化工具使用引导；兜底检测关键词 |
| LLM 调用错误的工具 | 用户说"看看XX"但调用了 modify_field | 工具 docstring 精确描述使用场景；每个工具加入安全检查 |
| Tool Calling 不支持的模型 | 切换到不支持 function calling 的模型 | `get_chat_model()` 检查 provider 是否支持，不支持则降级为 prompt 方式 |
| astream_events 事件格式变化 | LangGraph 版本升级导致事件名变化 | 锁定 langgraph 版本；事件处理加 try/except |
| 工具执行超时 | 深度调研、内容块生成可能超过 60s | 工具内部加 timeout；SSE 定期发送 heartbeat |
| project_id 获取失败 | RunnableConfig 传递丢失 | 工具函数内检查，缺失则返回错误信息 |
| 服务器重启丢失 MemorySaver | Checkpointer 中的 ToolMessage 历史丢失 | 自动从 ChatMessage DB Bootstrap 种子历史；升级到 SqliteSaver 彻底解决 |
| 对话历史过长导致 token 超限 | 长期项目累积大量消息 | `trim_messages` 自动裁剪；未来可增加老消息摘要压缩 |

---

## 十、实施顺序与依赖关系

```
Phase 1: 基础设施（可独立执行，不影响现有功能）
  Step 1.1 新建 llm.py          ← 无依赖
  Step 1.2 扩展 config.py       ← 无依赖
  Step 1.3 新建 agent_tools.py  ← 依赖 Step 1.1
  Step 1.4 更新 requirements.txt ← 无依赖

Phase 2: Agent Graph（核心改造）
  Step 2.1 重写 orchestrator.py  ← 依赖 Phase 1
  Step 2.2 更新 AgentState       ← 包含在 Step 2.1 中
  Step 2.3 添加 MemorySaver checkpointer ← 包含在 Step 2.1 中
  Step 2.4 agent_node 添加 trim_messages ← 包含在 Step 2.1 中

Phase 3: API 层（对外接口改造）
  Step 3.1 重写 /stream          ← 依赖 Phase 2
    - 上下文工程：Checkpointer Bootstrap 逻辑
    - 上下文工程：只传新消息，删除旧历史加载
    - 上下文工程：删除组过滤和 20 条硬截断
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

## 十一、前端适配

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
  // 更新状态，触发内容块刷新
  if (data.field_updated) {
    onContentUpdate?.();
  }
  break;
```

### 10.2 工具名称映射（前端显示友好名称）

```typescript
const toolNameMap: Record<string, string> = {
  "modify_field": "修改内容块",
  "generate_field_content": "生成内容块内容",
  "query_field": "查询内容块信息",
  "manage_architecture": "管理项目架构",
  "advance_to_phase": "推进到下一组",
  "run_research": "执行调研",
  "run_evaluation": "执行评估",
  "manage_persona": "管理用户画像",
  "generate_outline": "生成大纲",
  "read_field": "读取内容块内容",
  "update_field": "更新内容块内容",
  "manage_skill": "应用写作技能",
  // 以下是 implementation_plan_v3.md 新增的工具
  "update_prompt": "分析提示词修改",
  "execute_prompt_update": "执行提示词修改",
};
```

### 10.3 PRODUCE_ROUTES 的变化

现有 `PRODUCE_ROUTES` 通过 route_target 判断是否为产出路由。新架构中，这个判断改为通过 `tool_end` 事件的 `field_updated` 标志：

```typescript
// 旧：通过 route 事件判断
if (PRODUCE_ROUTES.includes(currentRoute)) { ... }

// 新：通过 tool_end 事件判断
case "tool_end":
  if (data.field_updated) {
    // 内容块已更新，触发左侧工作台刷新
    onContentUpdate?.();
  }
  break;
```

### 10.4 前端术语更新（"字段"→"内容块"、"阶段"→"组"）

> 为了对创作者友好，前端 UI 中面向用户的中文文本需要统一更新。**后端变量名（`field_name`、`phase`、`current_phase`）保持不变。**

需要修改的前端文件及关键字符串：

| 文件 | 旧文本（示例） | 新文本 |
|------|--------------|--------|
| `agent-panel.tsx` | `"生成字段"` | `"生成内容块"` |
| `agent-panel.tsx` | `"根据上下文生成指定字段内容"` | `"根据上下文生成指定内容块内容"` |
| `agent-panel.tsx` | `"添加/删除/移动阶段和字段"` | `"添加/删除/移动组和内容块"` |
| `agent-panel.tsx` | `"⚙️ 正在生成字段内容..."` | `"⚙️ 正在生成内容块内容..."` |
| `agent-panel.tsx` | `"选择要引用的字段"` | `"选择要引用的内容块"` |
| `agent-panel.tsx` | `` `输入消息... 使用 @ 引用字段` `` | `` `输入消息... 使用 @ 引用内容块` `` |
| `workspace/page.tsx` | `"加载字段失败"` / `"更新字段失败"` | `"加载内容块失败"` / `"更新内容块失败"` |
| `workspace/page.tsx` | `"受影响的字段"` | `"受影响的内容块"` |
| `progress-panel.tsx` | `"迁移后可以自由添加/删除/排序阶段和字段"` | `"迁移后可以自由添加/删除/排序组和内容块"` |
| `progress-panel.tsx` | `"该阶段暂无字段"` | `"该组暂无内容块"` |
| `content-panel.tsx` | `"阶段"` (面向用户的标签) | `"组"` |
| `content-panel.tsx` | `"字段"` (面向用户的标签) | `"内容块"` |
| `global-search-modal.tsx` | `result.type === "field" ? "字段" : "内容块"` | 统一使用 `"内容块"` |
| `settings/page.tsx` | `"传统流程中各阶段的提示词"` | `"传统流程中各组的提示词"` |
| `settings/page.tsx` | `"添加/删除/移动阶段和字段"` | `"添加/删除/移动组和内容块"` |

**执行方式**：全局搜索 `字段` 和 `阶段`，逐个判断是否为面向用户的中文文本（而非代码变量），替换为 `内容块` 和 `组`。注意保留注释中描述后端概念的"字段"不变（如 `// JSON 字段查询`）。

---

## 十二、执行前检查清单

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
| 前端术语已更新 | 面向用户的 "字段" → "内容块"，"阶段" → "组"（见 §10.4） |
| Checkpointer 已配置 | `create_agent_graph()` 中有 `MemorySaver()` |
| `trim_messages` 已添加 | `agent_node()` 中有 token 预算管理 |
| `thread_id` 传递正确 | `config["configurable"]["thread_id"]` 格式为 `{project_id}:assistant` |
| Bootstrap 逻辑存在 | 首次请求从 DB 加载种子历史 |
| 旧的组过滤已删除 | 不再有 `msg_phase == current_phase` 过滤 |
| `ChatMessage.message_metadata` 字段变更 | `tool_used`(str) → `tools_used`(list)，其余不变 |

---

## 十三、执行后验证清单

| 实施阶段 | 验证方法 |
|------|----------|
| Phase 1 | 1. `from core.llm import llm, llm_mini` 成功 2. `from core.agent_tools import AGENT_TOOLS` 成功 3. `len(AGENT_TOOLS) == 12` |
| Phase 2 | 1. `from core.orchestrator import agent_graph` 成功 2. `agent_graph.get_graph().nodes` 包含 "agent" 和 "tools" |
| Phase 3 | 1. `/stream` 请求返回 SSE 流 2. 纯聊天返回 `token` 事件 3. "修改@内容块" 返回 `tool_start` → `token` → `tool_end` → `done` 4. `content` 事件不再出现 5. **上下文连续性**：第二次请求"刚才改了什么？" Agent 能正确回答 6. 服务器重启后首次请求自动 Bootstrap |
| Phase 4 | 1. `grep -r "ai_client" backend/` 无结果 2. `backend/core/ai_client.py` 不存在 |
| Phase 5 | 1. 内容块独立生成仍正常 2. 摘要生成正常 3. DeepResearch 正常 4. Eval 引擎正常 |
