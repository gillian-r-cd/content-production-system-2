# LLM Provider 兼容性优化方案
# 创建时间: 2026-02-25
# 更新时间: 2026-02-25（合并 0224-openai + 0220-Anthropic 后全面更新）
# 功能: 定义 OpenAI / Anthropic 双 Provider 兼容的系统性修复方案
# 关联: core/llm.py, core/llm_compat.py(待建), 所有调用 LLM 的文件
# 前置: 已完成 LLM_PROVIDER 切换基础设施（config.py, llm.py, env_example.txt）
# 代码库基准: 0225-compatible 分支（合并 0224-openai 会话体系/预算控制 + 0220-Anthropic LLM 兼容修复）

---

## 一、问题本质

### 1.1 LangChain 抽象泄漏

LangChain 提供了 `BaseChatModel` 抽象，`ChatOpenAI` 和 `ChatAnthropic` 都实现了相同的接口：
`ainvoke()`, `astream()`, `bind_tools()`, `astream_events()`。

**表面上**，切换 Provider 只需换构造函数：

```python
# 看似只要换一行
llm = ChatOpenAI(model="gpt-4o")
llm = ChatAnthropic(model="claude-opus-4-6")
# 后续代码不用改？
```

**实际上**，`BaseChatModel` 只统一了方法签名，没有统一返回值的内部结构。两个 Provider 的底层 API
在以下维度存在根本差异，LangChain 不做归一化，直接透传给调用方：

| 维度 | OpenAI (ChatOpenAI) | Anthropic (ChatAnthropic) |
|------|---------------------|---------------------------|
| `AIMessage.content` 类型 | 始终 `str` | `str` 或 `list[dict]`（含 text/tool_use 块） |
| 流式 `chunk.content` 类型 | 始终 `str` | `str` 或 `list[dict]` |
| 停止原因字段名 | `response_metadata["finish_reason"]` | `response_metadata["stop_reason"]` |
| 停止原因值 | `"stop"`, `"length"`, `"tool_calls"` | `"end_turn"`, `"max_tokens"`, `"tool_use"` |
| System Message 规则 | 可多条、可非连续 | 必须单条、必须在首位、必须连续 |
| 构造参数 | `api_key`, `base_url`, `organization` | `api_key`（无 base_url/org） |
| `max_tokens` 默认值 | 可选（有服务端默认值） | **必填**（不传会报错） |
| `llm_output` 结构 | `{"token_usage": {"prompt_tokens": N, ...}, "model_name": "..."}` | 结构不同，依赖 `usage_metadata` |

### 1.2 为什么不是"小修小补"

这不是几个 bug，而是一个系统性问题：**项目中所有直接读取 `response.content` 的代码都隐含了
"content 一定是 str" 的假设**。这个假设在 OpenAI Provider 下恒成立，在 Anthropic Provider 下不成立。

受影响的代码散布在 17 个文件、50+ 个调用点中。逐点修复会导致：
1. 重复代码（每个调用点都写一遍 `isinstance` 判断）
2. 容易遗漏（新增调用点时忘记归一化）
3. 维护成本高（如果未来加第三个 Provider，要改所有点）

**本质解法：在抽象层统一归一化，让下游代码永远拿到 `str`。**

---

## 二、五类兼容性问题详解

### 问题 A：`AIMessage.content` 类型多态

**根因：** Anthropic API 的 `content` 字段是一个 Block 数组，每个 Block 有 `type` 字段
（`"text"` / `"tool_use"` / `"tool_result"`）。LangChain `ChatAnthropic` 在以下情况返回 `list`：
- 响应同时包含文本和 tool_use（如 "让我查一下" + 调用工具）
- 纯 tool_use 响应（无文本）

OpenAI API 的 `content` 始终是 `str`（tool_calls 放在独立字段 `tool_calls` 中）。

**症状：**

```python
# 原始代码（仅 OpenAI 兼容）
text = response.content.strip()        # TypeError: list has no attribute strip
json.loads(response.content)            # TypeError: list is not str
full_content += chunk.content           # TypeError: can only concatenate str to str
```

**影响范围：** 所有 `response.content` 和 `chunk.content` 的直接使用点。

| 文件 | 未修复调用点数 | 用途 |
|------|-------------|------|
| `core/tools/simulator.py` | 12 | 模拟评估：`json.loads(response.content)`、对话消息拼接 |
| `core/memory_service.py` | 3 | 记忆提炼/合并/筛选：`response.content.strip()` |
| `core/tools/outline_generator.py` | 2 | 大纲生成：`response.content.strip()`、错误回退 |
| `core/tools/persona_manager.py` | 1 | 画像生成：`response.content.strip()` |
| `core/tools/deep_research.py` | 1 | 搜索词生成：`response.content.strip().split("\n")` |
| `core/tools/field_generator.py` | 1+1 | 字段生成：`response.content` + `chunk.content` 流式 |
| `core/digest_service.py` | 1 | 摘要生成：`response.content.strip()[:200]` |
| `core/tools/skill_manager.py` | 1 | 技能执行：`output=response.content` |
| `api/agent.py` | 1 | inline-edit L1820：`response.content.strip()` |
| **小计** | **24** | |

**已修复文件（供参考，均为内联 `isinstance` 判断，待统一为 `normalize_content()` 调用）：**

| 文件 | 已修复调用点数 | 修复方式 |
|------|-------------|---------|
| `api/agent.py` | 5 | `_normalize_content()` 辅助函数（L44 定义，L608/L743/L1026/L1284 调用） |
| `api/blocks.py` | 3 | 内联 `isinstance` 判断（L977/L1678 + 流式 L1096/L1127） |
| `api/eval.py` | 2 | 内联 `isinstance` 判断（L2363/L2417） |
| `core/orchestrator.py` | 2 | 内联 `isinstance` 判断（L600 agent_node + L489 _compress_if_needed） |
| `core/llm_logger.py` | 2 | 内联 `isinstance` 判断（L57/L157） |
| `core/agent_tools.py` | 3 | 内联 `isinstance` 判断（L391/L551/L629） |
| `core/tools/eval_engine.py` | 2 | 内联 `isinstance` 判断（L107/L153） |
| `core/tools/eval_v2_executor.py` | 1 | 内联 `isinstance` 判断（L46） |

### 问题 B：`response_metadata` 停止原因差异

**根因：** OpenAI 和 Anthropic 使用不同的字段名和值来标识 LLM 停止生成的原因。

| 场景 | OpenAI | Anthropic |
|------|--------|-----------|
| 正常结束 | `finish_reason = "stop"` | `stop_reason = "end_turn"` |
| 达到 max_tokens | `finish_reason = "length"` | `stop_reason = "max_tokens"` |
| 调用工具 | `finish_reason = "tool_calls"` | `stop_reason = "tool_use"` |

**影响范围：** `agent_tools.py` 中的截断检测逻辑。

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/agent_tools.py` | 已修复 | `_rewrite_field_impl` 和 `_generate_field_impl` 中同时检查两个字段 |

**潜在遗漏：** 任何其他依赖 `finish_reason` 做流程控制的代码。当前扫描未发现其他位置。

### 问题 C：System Message 约束差异

**根因：** Anthropic API 对 System Message 有严格约束：
1. 只能有一条 System Message
2. 必须是消息列表的第一条
3. 不能和其他消息类型交替出现

OpenAI 没有这些限制——可以在任意位置插入多条 System Message。

**影响场景：**
- LangGraph Checkpointer 恢复的历史消息中，可能包含旧的 System Message
- 如果代码在消息列表中间插入 System Message（如工具执行后的上下文补充）

**当前状态：** 通过清空 Checkpointer 数据库临时解决。`build_system_prompt` 只在 `agent_node`
开头构造一条 System Message 放在消息列表最前面，符合 Anthropic 约束。
但如果 Checkpointer 历史中存在旧格式消息（多条 System Message），恢复时会触发 Anthropic API 报错。

**需要的保护措施：** 在调用 LLM 前，过滤/合并消息列表中的 System Message。

### 问题 D：硬编码模型名

**根因：** 部分代码直接使用 `settings.openai_model` 或字面量 `"gpt-5.1"` 作为模型名，
而不是通过 `get_chat_model()` 的自动选择机制。

**影响范围：**

| 文件 | 位置 | 问题 |
|------|------|------|
| `api/fields.py` | L433, L439 | `model="gpt-5.1"` 硬编码 |
| `api/fields.py` | L609 | `result.response.model or "gpt-5.1"` 回退值 |
| `api/simulation.py` | L231 | `model="gpt-5.1"` 硬编码 |
| `api/eval.py` | L2055 | `model="gpt-5.1"` 硬编码 |
| `api/projects.py` | L1259 | `log.get("model", "gpt-5.1")` 回退值 |
| `core/models/generation_log.py` | L53, L82-90 | 默认值 `"gpt-5.1"` + `calculate_cost` 定价表只有 GPT 系列 |
| `api/blocks.py` | 5 处 | 已改为 `settings.anthropic_model if ... else settings.openai_model`（可用但冗长） |
| `api/eval.py` | L305 | 已改为三元表达式（同上，可简化） |

### 问题 E：成本计算不支持 Anthropic 模型

**根因：** `GenerationLog.calculate_cost()` 内的定价表只包含 GPT 系列模型。传入 Anthropic
模型名时，回退到 `"gpt-5.1"` 定价——**计费不准确**。

```python
pricing = {
    "gpt-5.1": {"input": 5.00, "output": 15.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
}
if model not in pricing:
    model = "gpt-5.1"  # Anthropic 模型会走这里
```

---

## 三、修复方案

### 核心原则

1. **在抽象层解决，不在调用点打补丁** — 提供一个统一的归一化工具，让所有下游代码无需感知 Provider 差异
2. **避免代码重复** — 当前已修复的 8 个文件中有 7 个用内联 `isinstance` 判断，应统一为函数调用
3. **防御性编程** — 未来新增 Provider（如 Google Gemini）时，只需修改抽象层

### M4：LLM Provider 兼容性修复

**目标：** 所有 LLM 调用点在 OpenAI 和 Anthropic Provider 下行为一致，无运行时错误。
**前置依赖：** M1-M3 已完成。

#### M4-1：创建统一归一化工具模块

**文件：** `backend/core/llm_compat.py`（新建）

提供以下工具函数，集中处理 Provider 差异：

```python
# backend/core/llm_compat.py
# 功能: LLM Provider 兼容性工具函数
# 主要导出: normalize_content, get_stop_reason, get_model_name, sanitize_messages
# 设计: 屏蔽 OpenAI / Anthropic 返回值差异，让下游代码无需感知 Provider

def normalize_content(content) -> str:
    """
    将 LLM 返回的 content 归一化为 str。

    ChatOpenAI: content 始终是 str
    ChatAnthropic: content 可能是 str 或 list[dict]（内容块列表）

    下游代码应统一调用此函数，而非直接使用 response.content。
    """

def get_stop_reason(response) -> tuple[str, bool]:
    """
    从 LLM 响应中提取停止原因，返回 (reason, is_truncated)。

    统一 OpenAI 的 finish_reason 和 Anthropic 的 stop_reason。
    """

def get_model_name() -> str:
    """
    获取当前活跃的模型名称（用于日志和计费）。

    根据 settings.llm_provider 返回对应模型名。
    """

def sanitize_messages(messages: list) -> list:
    """
    清理消息列表，确保符合当前 Provider 的约束。

    对 Anthropic：合并多条 SystemMessage 为一条，确保在首位。
    对 OpenAI：不做处理（无约束）。
    """
```

**设计决策：**
- 不修改 `llm.py` 中的 `get_chat_model()`——它负责构造实例，不负责后处理
- 不在 `BaseChatModel` 上做 monkey-patch——侵入性太强，升级 LangChain 时会断
- 独立模块，纯函数，无副作用，易测试

#### M4-2：统一已修复文件的内联归一化

**目标：** 将已修复的 8 个文件中的内联 `isinstance` 判断替换为 `normalize_content()` 调用，
消除重复代码。

| # | 文件 | 改动 |
|---|------|------|
| 1 | `api/agent.py` | 删除 `_normalize_content`，改用 `from core.llm_compat import normalize_content` |
| 2 | `api/blocks.py` | 3 处内联判断 → `normalize_content()` |
| 3 | `api/eval.py` | 3 处内联判断 → `normalize_content()` |
| 4 | `core/orchestrator.py` | 1 处内联判断 → `normalize_content()` |
| 5 | `core/llm_logger.py` | 1 处内联判断 → `normalize_content()` |
| 6 | `core/agent_tools.py` | 2 处内联判断 → `normalize_content()`；截断检测 → `get_stop_reason()` |
| 7 | `core/tools/eval_engine.py` | 2 处内联判断 → `normalize_content()` |
| 8 | `core/tools/eval_v2_executor.py` | 1 处内联判断 → `normalize_content()` |

#### M4-3：修复未归一化的 24 个调用点

**目标：** 为剩余 9 个文件中的 24 个 `response.content` / `chunk.content` 调用点添加归一化。

| # | 文件 | 调用点数 | 典型模式 | 改动 |
|---|------|---------|---------|------|
| 1 | `core/tools/simulator.py` | 12 | `json.loads(response.content)` → `json.loads(normalize_content(response.content))` | 全部 12 处 |
| 2 | `core/memory_service.py` | 3 | `response.content.strip()` → `normalize_content(response.content).strip()` | 3 处 |
| 3 | `core/tools/outline_generator.py` | 2 | 同上 | 2 处 |
| 4 | `core/tools/persona_manager.py` | 1 | 同上 | 1 处 |
| 5 | `core/tools/deep_research.py` | 1 | `response.content.strip().split("\n")` → `normalize_content(...).strip().split("\n")` | 1 处 |
| 6 | `core/tools/field_generator.py` | 2 | `response.content` + `chunk.content` | 2 处 |
| 7 | `core/digest_service.py` | 1 | `response.content.strip()[:200]` | 1 处 |
| 8 | `core/tools/skill_manager.py` | 1 | `output=response.content` | 1 处 |
| 9 | `api/agent.py` | 1 | inline-edit `response.content.strip()` | 1 处 |

#### M4-4：修复硬编码模型名

**目标：** 所有日志和计费记录使用当前实际 Provider 的模型名。

| # | 文件 | 当前值 | 改动 |
|---|------|-------|------|
| 1 | `api/fields.py` L433 | `model="gpt-5.1"` | → `model=get_model_name()` |
| 2 | `api/fields.py` L439 | `calculate_cost("gpt-5.1", ...)` | → `calculate_cost(get_model_name(), ...)` |
| 3 | `api/fields.py` L609 | `result.response.model or "gpt-5.1"` | → `result.response.model or get_model_name()` |
| 4 | `api/simulation.py` L231 | `model="gpt-5.1"` | → `model=get_model_name()` |
| 5 | `api/eval.py` L2055 | `model="gpt-5.1"` | → `model=get_model_name()` |
| 6 | `api/projects.py` L1259 | `log.get("model", "gpt-5.1")` | → `log.get("model", get_model_name())` |
| 7 | `api/blocks.py` 5 处 | `settings.anthropic_model if ... else settings.openai_model` | → `get_model_name()` |
| 8 | `api/eval.py` L305 | `settings.anthropic_model if ... else settings.openai_model` | → `get_model_name()` |

#### M4-5：扩展 `calculate_cost` 支持 Anthropic 模型

**文件：** `backend/core/models/generation_log.py`

在定价表中增加 Anthropic 模型的价格：

```python
pricing = {
    # OpenAI
    "gpt-5.1": {"input": 5.00, "output": 15.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    # Anthropic (2026 pricing per 1M tokens)
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-3-5": {"input": 0.80, "output": 4.00},
}

if model not in pricing:
    # 回退：用当前 provider 的默认主模型定价
    from core.llm_compat import get_model_name
    fallback = get_model_name()
    model = fallback if fallback in pricing else "gpt-4o"
```

#### M4-6：添加 System Message 防护

**文件：** `backend/core/orchestrator.py`（`agent_node` 函数内）

在将消息列表传给 LLM 之前，调用 `sanitize_messages()` 清理：

```python
# agent_node 中，调用 LLM 前
from core.llm_compat import sanitize_messages

messages = sanitize_messages(state["messages"])
response = await llm_with_tools.ainvoke(messages, config=config)
```

`sanitize_messages` 的逻辑：
- 如果 `settings.llm_provider == "anthropic"`：
  - 将所有 `SystemMessage` 的内容合并为一条
  - 确保合并后的 `SystemMessage` 在列表首位
  - 移除其他位置的 `SystemMessage`
- 如果 `settings.llm_provider == "openai"`：不做处理

这是一个**防御性措施**，防止 Checkpointer 恢复的历史消息中混入多条 System Message。

#### M4-7：验证与回归测试

| # | 测试项 | 验证方式 | 预期结果 |
|---|--------|---------|---------|
| 1 | `normalize_content` 单元测试 | pytest | str 输入原样返回；list 输入正确拼接；None 返回空字符串 |
| 2 | `get_stop_reason` 单元测试 | pytest | OpenAI/Anthropic 格式都能正确识别截断 |
| 3 | `sanitize_messages` 单元测试 | pytest | 多条 SystemMessage 合并为一条；位置正确 |
| 4 | `get_model_name` 单元测试 | pytest | 根据 provider 返回正确模型名 |
| 5 | Agent 对话流（assistant 模式） | curl / 前端 | 正常对话、工具调用、流式输出 |
| 6 | Agent 对话流（critic 模式） | curl / 前端 | 模式切换后正常对话 |
| 7 | 字段生成（generate_field_content） | 前端触发 | 内容正确生成，无 TypeError |
| 8 | 字段重写（rewrite_field） | 前端触发 | 截断检测正常工作 |
| 9 | 模拟评估（simulator） | API 调用 | JSON 解析正常，反馈结构完整 |
| 10 | 记忆提炼（memory_service） | 对话后自动 | 记忆正确提取和保存 |
| 11 | 大纲生成（outline_generator） | 工具调用 | 大纲 JSON 正确解析 |
| 12 | 画像生成（persona_manager） | 工具调用 | 画像数据正确 |
| 13 | 深度调研（deep_research） | 工具调用 | 搜索词正确生成 |
| 14 | 摘要生成（digest_service） | 内容保存后 | 摘要字符串正常 |
| 15 | 技能执行（skill_manager） | 工具调用 | 输出为字符串 |
| 16 | 内联编辑（inline-edit） | 前端触发 | 替换内容为字符串 |
| 17 | Eval V2 执行 | API 调用 | 评估结果 JSON 正确 |
| 18 | GenerationLog 计费 | 检查 DB | Anthropic 模型使用正确定价 |
| 19 | 现有 237 个后端测试 | pytest | 全部通过（回归） |
| 20 | 前端构建 | npm run build | 零错误 |

---

## 四、里程碑与 TODO

### M4：LLM Provider 兼容性修复

**目标：** 所有 LLM 调用在 OpenAI 和 Anthropic 下行为一致，无运行时错误。
**前置依赖：** M1-M3 完成。
**优先级：** 阻塞生产使用（Anthropic Provider 下大量功能会 TypeError）。

| # | 任务 | 文件 | 状态 | 说明 |
|---|------|------|------|------|
| M4-1 | 创建 `llm_compat.py` 工具模块 | `core/llm_compat.py`（新建） | 待开始 | `normalize_content`, `get_stop_reason`, `get_model_name`, `sanitize_messages` |
| M4-2 | 单元测试 `llm_compat.py` | `tests/test_llm_compat.py`（新建） | 待开始 | 覆盖所有边界情况 |
| M4-3 | 统一已修复文件（消除内联重复） | 8 个已修复文件 | 待开始 | 内联 `isinstance` → `normalize_content()` |
| M4-4 | 修复 `simulator.py`（12 处） | `core/tools/simulator.py` | 待开始 | 所有 `response.content` 归一化 |
| M4-5 | 修复 `memory_service.py`（3 处） | `core/memory_service.py` | 待开始 | |
| M4-6 | 修复 `outline_generator.py`（2 处） | `core/tools/outline_generator.py` | 待开始 | |
| M4-7 | 修复 `persona_manager.py`（1 处） | `core/tools/persona_manager.py` | 待开始 | |
| M4-8 | 修复 `deep_research.py`（1 处） | `core/tools/deep_research.py` | 待开始 | |
| M4-9 | 修复 `field_generator.py`（2 处） | `core/tools/field_generator.py` | 待开始 | 含 `chunk.content` 流式 |
| M4-10 | 修复 `digest_service.py`（1 处） | `core/digest_service.py` | 待开始 | |
| M4-11 | 修复 `skill_manager.py`（1 处） | `core/tools/skill_manager.py` | 待开始 | |
| M4-12 | 修复 `agent.py` inline-edit（1 处） | `api/agent.py` | 待开始 | |
| M4-13 | 修复硬编码模型名 | `api/fields.py`, `api/simulation.py`, `api/eval.py`, `api/projects.py`, `api/blocks.py` | 待开始 | `"gpt-5.1"` 和三元表达式 → `get_model_name()`（共 8 处） |
| M4-14 | 扩展 `calculate_cost` 定价表 | `core/models/generation_log.py` | 待开始 | 增加 Anthropic 模型定价 |
| M4-15 | System Message 防护 | `core/orchestrator.py` | 待开始 | `sanitize_messages` 在 LLM 调用前清理 |
| M4-16 | 集成测试：Agent 对话全流程 | curl / 前端 | 待开始 | assistant + critic 模式，含工具调用 |
| M4-17 | 集成测试：内容生成全流程 | 前端触发 | 待开始 | generate + rewrite + inline-edit |
| M4-18 | 集成测试：评估全流程 | API 调用 | 待开始 | simulator + eval_v2 + 计费记录 |
| M4-19 | 回归测试 | pytest + npm build | 待开始 | 237 后端测试 + 前端 0 错误构建 |

### 执行顺序

```
M4-1 → M4-2 → M4-3（基础设施就位，有测试保障）
         ↓
    M4-4 ~ M4-12（并行修复所有调用点，每修一个文件验证一次）
         ↓
    M4-13 → M4-14（模型名和计费）
         ↓
    M4-15（System Message 防护）
         ↓
    M4-16 ~ M4-19（集成测试和回归）
```

**预计工作量：** M4-1 到 M4-15 约 2 小时（大部分是机械替换），M4-16 到 M4-19 约 1 小时。

---

## 五、与现有架构的兼容性

| 现有组件 | 影响 | 处理方式 |
|---------|------|---------|
| `core/llm.py` | 不改动 | 仍负责构造 `ChatOpenAI` / `ChatAnthropic` 实例 |
| `core/config.py` | 不改动 | `llm_provider` / 模型名配置已就位 |
| `core/llm_compat.py` | 新增 | 纯工具函数模块，无状态，无副作用 |
| `api/agent.py` | 删除 `_normalize_content`，改用导入 | 减少重复代码 |
| 其他 17 个文件 | 添加 `import` + 替换直接访问 | 最小改动，不影响逻辑 |
| `GenerationLog` | 扩展定价表 | 向后兼容，现有 GPT 定价不变 |
| 前端 | 不改动 | 所有变更在后端 |
| 测试 | 新增 `test_llm_compat.py` | 不影响现有测试 |

### 向后兼容

- 切回 `LLM_PROVIDER=openai` 后，所有行为与改动前完全一致
- `normalize_content` 对 `str` 输入是恒等操作（`return content`），零开销
- `sanitize_messages` 对 OpenAI Provider 是空操作
- `get_model_name()` 根据当前 `settings.llm_provider` 动态返回，不破坏任何既有逻辑
- `calculate_cost` 新增的 Anthropic 定价不影响现有 GPT 模型的计费

---

## 六、设计决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 归一化位置 | A. 在 `get_chat_model` 返回包装类 / B. 独立工具函数 | **B. 独立工具函数** | A 需要包装 `BaseChatModel` 所有方法（`ainvoke/astream/bind_tools/astream_events`），侵入性过高，且 LangGraph 内部也调用这些方法，包装可能导致类型检查失败。B 最小化改动，只在读取 content 的地方调用 |
| 归一化时机 | A. LLM 调用后立即 / B. 在使用 content 的地方 | **B. 在使用点** | 部分场景需要保留原始 list（如 LangGraph 内部的 tool_calls 解析依赖 list 结构）。使用点归一化更安全 |
| 重复代码处理 | A. 保持内联 / B. 统一为函数调用 | **B. 统一函数** | 24 处相同逻辑，DRY 原则。且未来加 Provider 只需改一处 |
| System Message 清理 | A. 在 Checkpointer 层过滤 / B. 在调用 LLM 前过滤 | **B. 调用前过滤** | Checkpointer 是通用组件，不应加业务逻辑。调用前过滤是防御性编程的标准做法 |
| 模型名获取 | A. 每处读 settings / B. 工具函数 | **B. 工具函数 `get_model_name()`** | 消除 `settings.anthropic_model if settings.llm_provider == "anthropic" else settings.openai_model` 的冗长三元表达式 |

---

## 七、合并后状态说明（0225-compatible 分支）

本文档初版基于 `0220-Anthropic` 分支编写。`0225-compatible` 分支合并了 `0224-openai`（会话体系、
预算控制、DeepResearch 工程化）和 `0220-Anthropic`（LLM Provider 切换基础设施、部分兼容修复），
以下是合并后的关键变化：

### 合并引入的新代码（来自 0224-openai）

| 模块 | 新增内容 | 与本方案的关系 |
|------|---------|--------------|
| `core/models/conversation.py` | `Conversation` 会话模型 | 不涉及 LLM 调用，无需兼容处理 |
| `core/orchestrator.py` L489 | `_compress_if_needed` 中 `msg.content` 多态处理 | **0224 已自行处理**：`isinstance(msg.content, str) else str(msg.content)` |
| `core/orchestrator.py` L494-570 | `_resolve_budget_zone` + 预算控制逻辑 | 不涉及 LLM content 读取，无需处理 |
| `api/agent.py` | 会话 CRUD、`_build_thread_id`、`_get_or_create_conversation` | 不涉及新的 LLM content 读取 |
| `core/deepresearch_metrics.py` | DeepResearch 质量指标 | 不调用 LLM，无需处理 |
| 各 `tests/` 新增测试 | 测试数量 33 → 237 | 回归覆盖面更广 |

### 合并后审计确认

- **0 冲突**：Git 自动合并成功
- **237 后端测试全部通过**
- **前端 0 错误构建**
- 未修复的 24 个 `response.content` 调用点清单不变（0224 未引入新的未处理调用点）
- 硬编码模型名增加了 `api/eval.py:2055`、`api/projects.py:1259` 两处（来自 0224，本次补充发现）
