# 模型选择功能设计方案
# 创建时间: 2026-02-26
# 功能: 用户可在后台设置全局默认模型，每个内容块可独立覆盖模型
# 关联: core/llm.py, core/llm_compat.py, core/config.py, core/models/agent_settings.py, core/models/content_block.py
# 前置: M4 LLM Provider 兼容性修复已完成（0225-compatible 分支）

---

## 一、需求本质

### 1.1 为什么需要模型选择

当前系统的 LLM 模型由 `.env` 环境变量一次性写死，进程生命周期内不可变。这带来三个问题：

1. **用户无法通过 UI 切换模型** -- 换模型需要改 `.env` 并重启后端
2. **所有内容块使用同一模型** -- 不同内容块的复杂度不同，简单的字段用顶级模型是浪费，复杂的字段用轻量模型则质量不够
3. **无法混用 Provider** -- 用户可能想在同一项目中，对某些块用 OpenAI GPT-5.2，对另一些块用 Anthropic Opus 4.6

### 1.2 设计原则

**两级覆盖链，不多不少：**

```
.env 默认 ← 用户全局默认（AgentSettings）← 内容块覆盖（ContentBlock.model_override）
```

- **内容块有 `model_override`** -- 用它
- **内容块没有** -- 用用户在设置页配的全局默认
- **用户没配全局默认** -- 回退到 `.env` 中的模型

模板（FieldTemplate / PhaseTemplate）**不设模型字段**。模板定义的是内容结构和提示词，模型选择在内容块实例化后由用户决定。如果模板包含多个内容块，每个块可以独立设置。

### 1.3 可用模型清单

根据实际 API 测试（2026-02-26），当前可用模型：

| Provider | 模型 ID | 显示名 | 可用 | Tool Calling | 适用场景 |
|----------|---------|--------|------|-------------|---------|
| OpenAI | `gpt-5.1` | GPT-5.1 | 可用 | 支持 | 主力模型 |
| OpenAI | `gpt-5.2` | GPT-5.2 | 可用 | 支持 | 主力模型 |
| OpenAI | `gpt-4o-mini` | GPT-4o Mini | 可用 | 支持 | 轻量任务 |
| Anthropic | `claude-opus-4-6` | Claude Opus 4.6 | 可用 | 支持 | 主力模型 |
| Anthropic | `claude-sonnet-4-6` | Claude Sonnet 4.6 | 可用 | 支持 | 主力/轻量 |
| Anthropic | `claude-sonnet-4-5` | Claude Sonnet 4.5 | 可用 | 支持 | 轻量任务 |

不可用：`gpt-5.3`（只有 codex 版本，非 chat 模型）、`gpt-5.2-pro`（非 chat 模型）。

---

## 二、当前架构分析

### 2.1 现状

```
.env
  LLM_PROVIDER=anthropic
  OPENAI_MODEL=gpt-5.1
  ANTHROPIC_MODEL=claude-opus-4-6
      |
      v
config.py (Settings 单例, lru_cache)
      |
      v
llm.py
  llm = get_chat_model()            # 模块级全局单例, import 时创建
  llm_mini = get_chat_model(mini)   # 同上
      |
      v
20+ 文件 from core.llm import llm  # 全部用同一个实例
```

### 2.2 问题点

| 问题 | 当前代码 | 影响 |
|------|---------|------|
| `llm` 是全局单例 | `llm.py` L91: `llm = get_chat_model()` | 进程内不可变 |
| `get_chat_model()` 只看全局 provider | `llm.py` L53: `provider = settings.llm_provider` | 不能按模型名自动判断 provider |
| `AgentSettings` 无模型字段 | `agent_settings.py`: 只有 tools/skills/tool_prompts | 用户无处配默认模型 |
| `ContentBlock` 无模型字段 | `content_block.py`: 无 `model_override` | 每个块无法独立选模型 |
| `sanitize_messages` 只看全局 provider | `llm_compat.py` L104 | 跨 provider 调用时判断错误 |
| `get_model_name()` 无 override 入口 | `llm_compat.py` L72 | 日志/计费无法反映实际模型 |

### 2.3 不需要改的部分

以下模块使用全局默认模型，**本次不改**：

| 模块 | 理由 |
|------|------|
| `orchestrator.py` Agent 对话 | Agent 对话不操作特定内容块，用全局默认 |
| `eval_engine.py` / `eval_v2_executor.py` | 评估引擎用全局默认 |
| `simulator.py` | 模拟器用全局默认 |
| `digest_service.py` / `memory_service.py` | 辅助功能用 mini 模型 |
| `outline_generator.py` / `persona_manager.py` / `deep_research.py` | 用全局默认 |
| `skill_manager.py` | 用全局默认 |

---

## 三、改动方案

### Phase A: 基础设施（无行为变化）

#### A1: 数据模型 -- AgentSettings 加 `default_model` / `default_mini_model`

**文件:** `backend/core/models/agent_settings.py`

```python
# 新增两个字段
default_model: Mapped[Optional[str]] = mapped_column(
    String(100), nullable=True, default=None
)
default_mini_model: Mapped[Optional[str]] = mapped_column(
    String(100), nullable=True, default=None
)
```

语义：
- `default_model = None` -- 回退到 `.env` 的模型（当前行为不变）
- `default_model = "gpt-5.2"` -- 所有未指定模型的内容块使用 GPT-5.2
- 支持跨 provider：用户全局默认可以是 Anthropic，但某个块可以用 OpenAI

#### A2: 数据模型 -- ContentBlock 加 `model_override`

**文件:** `backend/core/models/content_block.py`

```python
# 新增一个字段（AI 配置区域）
model_override: Mapped[Optional[str]] = mapped_column(
    String(100), nullable=True, default=None
)
```

语义：
- `model_override = None` -- 回退到用户全局默认
- `model_override = "claude-sonnet-4-6"` -- 此块生成时用 Sonnet 4.6

同时更新 `to_tree_dict()` 输出 `model_override` 字段。

#### A3: DB Migration

**文件:** `backend/scripts/init_db.py`

两张表各加一列。对已有数据库，通过 `ALTER TABLE` 增量添加（带 `IF NOT EXISTS` 防重）。

#### A4: `get_chat_model()` 按模型名自动选 provider

**文件:** `backend/core/llm.py`

当前 `get_chat_model()` 只看全局 `settings.llm_provider` 决定构造 `ChatOpenAI` 还是 `ChatAnthropic`。
改为：**如果传入了 `model` 参数，根据模型名前缀自动判断 provider**。

```python
def get_chat_model(model: str = None, ...) -> BaseChatModel:
    if model and model.startswith("claude-"):
        provider = "anthropic"
    elif model:
        provider = "openai"
    else:
        # 无 model 参数时，沿用全局 provider（现有行为不变）
        provider = (settings.llm_provider or "openai").lower().strip()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model or settings.anthropic_model or "claude-opus-4-6",
            api_key=settings.anthropic_api_key,
            ...
        )
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or settings.openai_model or "gpt-5.1",
            api_key=settings.openai_api_key,
            ...
        )
```

**关键点:** 不传 `model` 时行为与现在完全一致（向后兼容）。传 `model` 时自动判断，
支持同一进程内同时使用 OpenAI 和 Anthropic。

#### A5: `resolve_model()` 覆盖链函数

**文件:** `backend/core/llm_compat.py`

新增核心函数，实现两级覆盖链解析：

```python
def resolve_model(model_override: Optional[str] = None, use_mini: bool = False) -> str:
    """
    解析最终模型名。覆盖链优先级：
      1. model_override（内容块级）
      2. AgentSettings.default_model（用户全局级）
      3. settings.xxx_model（.env 级）

    Args:
        model_override: 内容块的 model_override 值（可能为 None）
        use_mini: 是否使用轻量模型

    Returns:
        最终模型名（如 "gpt-5.2" 或 "claude-opus-4-6"）
    """
    # 级别 1: 内容块覆盖
    if model_override:
        return model_override

    # 级别 2: 用户全局默认（从 DB 读取）
    db_default = _get_agent_settings_model(use_mini)
    if db_default:
        return db_default

    # 级别 3: .env 默认
    return get_model_name(mini=use_mini)
```

`_get_agent_settings_model` 是内部辅助函数，查询 `AgentSettings` 单例的 `default_model` / `default_mini_model`。
为避免每次 LLM 调用都 hit DB，使用 `functools.lru_cache` + TTL 缓存（或进程内简单缓存变量）。

#### A6: `sanitize_messages()` 按实际模型名判断 provider

**文件:** `backend/core/llm_compat.py`

当前 `sanitize_messages` 根据全局 `settings.llm_provider` 判断是否需要合并 SystemMessage。
当内容块使用跨 provider 模型时（如全局是 OpenAI 但某块用 Anthropic），这个判断会出错。

改为接受 `model` 参数：

```python
def sanitize_messages(messages: list, model: str = None) -> list:
    provider = _infer_provider(model) if model else (settings.llm_provider or "openai").lower().strip()
    if provider != "anthropic":
        return messages
    # ... 合并 SystemMessage 逻辑不变 ...

def _infer_provider(model: str) -> str:
    """根据模型名推断 provider"""
    if model.startswith("claude-"):
        return "anthropic"
    return "openai"
```

#### A7: `/api/models` 可用模型列表端点

**文件:** `backend/api/models.py`（新建）

返回当前可用的模型列表，基于已配置的 API Key 动态判断。

```python
@router.get("/")
def list_available_models():
    """返回当前可用的 LLM 模型列表"""
    models = []

    if settings.openai_api_key:
        models.extend([
            {"id": "gpt-5.1", "provider": "openai", "name": "GPT-5.1", "tier": "main"},
            {"id": "gpt-5.2", "provider": "openai", "name": "GPT-5.2", "tier": "main"},
            {"id": "gpt-4o-mini", "provider": "openai", "name": "GPT-4o Mini", "tier": "mini"},
        ])

    if settings.anthropic_api_key:
        models.extend([
            {"id": "claude-opus-4-6", "provider": "anthropic", "name": "Claude Opus 4.6", "tier": "main"},
            {"id": "claude-sonnet-4-6", "provider": "anthropic", "name": "Claude Sonnet 4.6", "tier": "main"},
            {"id": "claude-sonnet-4-5", "provider": "anthropic", "name": "Claude Sonnet 4.5", "tier": "mini"},
        ])

    # 查询 AgentSettings 获取当前默认
    ...

    return {
        "models": models,
        "current_default": {
            "main": resolve_model(),
            "mini": resolve_model(use_mini=True),
        },
    }
```

在 `main.py` 中注册路由。

#### A8: `calculate_cost()` 增加新模型定价

**文件:** `backend/core/models/generation_log.py`

在定价表中增加 `gpt-5.2` 和 `claude-sonnet-4-5`：

```python
pricing = {
    # OpenAI
    "gpt-5.1": {"input": 5.00, "output": 15.00},
    "gpt-5.2": {"input": 5.00, "output": 15.00},   # 新增
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    # Anthropic
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},  # 新增
    "claude-haiku-3-5": {"input": 0.80, "output": 4.00},
}
```

#### A9: 单元测试

**文件:** `backend/tests/test_model_selection.py`（新建）

覆盖以下核心场景：

| # | 测试 | 验证内容 |
|---|------|---------|
| 1 | `test_resolve_model_block_override` | `model_override` 非空时直接返回 |
| 2 | `test_resolve_model_global_default` | `model_override` 为空时回退到 AgentSettings |
| 3 | `test_resolve_model_env_fallback` | AgentSettings 也为空时回退到 `.env` |
| 4 | `test_get_chat_model_auto_provider_openai` | 传 `model="gpt-5.2"` 时返回 `ChatOpenAI` |
| 5 | `test_get_chat_model_auto_provider_anthropic` | 传 `model="claude-sonnet-4-6"` 时返回 `ChatAnthropic` |
| 6 | `test_get_chat_model_no_model_uses_global` | 不传 `model` 时使用全局 provider（向后兼容） |
| 7 | `test_sanitize_messages_with_model` | 传 `model="claude-..."` 时执行合并；传 `model="gpt-..."` 时不合并 |
| 8 | `test_infer_provider` | `claude-*` -> anthropic, `gpt-*` -> openai |

---

### Phase B: 后端集成（改变生成行为）

#### B1: Settings API 支持 `default_model`

**文件:** `backend/api/settings.py`

- `AgentSettingsUpdate` 增加 `default_model: Optional[str]` 和 `default_mini_model: Optional[str]`
- `AgentSettingsResponse` 增加对应字段
- `get_agent_settings` / `update_agent_settings` 自然支持新字段（通过 `model_dump(exclude_unset=True)` 已自动处理）

#### B2: Blocks API 支持 `model_override`

**文件:** `backend/api/blocks.py`

- 已有 `BlockUpdate` schema（通过 `update_block` 端点）应自动传递 `model_override`
  -- 检查 update 逻辑是否已处理该字段
- `BlockCreate` 如需创建时指定模型（从前端创建），也加上

#### B3: `generate_block_content` / `generate_block_content_stream` 使用 `resolve_model`

**文件:** `backend/api/blocks.py`

当前代码：
```python
# L973 / L1111
response = await llm.ainvoke(messages)
async for chunk in llm.astream(messages):
```

改为：
```python
from core.llm_compat import resolve_model
from core.llm import get_chat_model

# 解析此内容块应使用的模型
model_name = resolve_model(model_override=block.model_override)
block_llm = get_chat_model(model=model_name)

# 如果模型是 Anthropic，需要清理 SystemMessage
from core.llm_compat import sanitize_messages
messages = sanitize_messages(messages, model=model_name)

response = await block_llm.ainvoke(messages)
```

同样修改 `generate_ai_prompt`（L1668 的 `await llm.ainvoke(messages)`）。

#### B4: Agent 工具使用 `resolve_model`

**文件:** `backend/core/agent_tools.py`

`_rewrite_field_impl` / `_generate_field_impl` / `_query_field_impl` 这三个函数操作具体内容块，
当前直接用全局 `llm`：

```python
# 当前
from core.llm import llm
response = await llm.ainvoke(messages, config=config)
```

改为根据 block 的 `model_override` 解析模型：

```python
from core.llm_compat import resolve_model, sanitize_messages
from core.llm import get_chat_model

model_name = resolve_model(model_override=block.model_override)
block_llm = get_chat_model(model=model_name)
messages = sanitize_messages(messages, model=model_name)
response = await block_llm.ainvoke(messages, config=config)
```

#### B5: `field_generator.py` 接受 model 参数

**文件:** `backend/core/tools/field_generator.py`

`generate_field` / `generate_field_stream` 当前直接用全局 `llm`。
需要增加 `model: Optional[str] = None` 参数，在内部调用 `get_chat_model(model=model)` 替代全局 `llm`。

#### B6: 集成测试

| # | 测试项 | 验证方式 | 预期 |
|---|--------|---------|------|
| 1 | Agent 对话（无 override） | curl / 前端 | 使用全局默认模型，行为不变 |
| 2 | 内容块生成（无 override） | 前端触发 | 使用全局默认模型 |
| 3 | 内容块生成（有 override） | 设 model_override 后触发 | 使用指定模型 |
| 4 | 跨 provider 生成 | 全局 Anthropic + 块 override 为 GPT | GPT 模型生成，无 SystemMessage 报错 |
| 5 | 设置全局默认后生效 | 改 AgentSettings.default_model 后生成 | 使用新默认 |
| 6 | 回退链 | 全部为空 | 回退到 .env |
| 7 | 现有 pytest | pytest | 全部通过（回归） |
| 8 | 前端构建 | npm run build | 零错误 |

---

### Phase C: 前端 UI

#### C1: 设置页新增"模型配置" Tab

**文件:**
- `frontend/app/settings/page.tsx` -- 新增 `"models"` tab
- `frontend/components/settings/model-settings-section.tsx` -- 新建

UI 结构：
```
模型配置
├── 当前 Provider: anthropic (来自 .env, 仅展示)
├── 可用模型列表 (从 /api/models 加载, 只读展示)
├── 默认主模型: [下拉选择]  (当前: claude-opus-4-6)
└── 默认轻量模型: [下拉选择]  (当前: claude-sonnet-4-6)
    [保存]
```

下拉选项从 `/api/models` 加载，只显示已配置 API Key 的 provider 的模型。
保存时调用 `PUT /api/settings/agent` 更新 `default_model` / `default_mini_model`。

#### C2: 内容块编辑器增加"模型覆盖"选择

**文件:** `frontend/components/content-block-editor.tsx`

在 AI 配置区域（`ai_prompt` / `constraints` 旁边）增加一个下拉选择：

```
AI 配置
├── AI 生成提示词: [textarea]
├── 使用模型: [下拉]  选项: "跟随全局默认 (claude-opus-4-6)" | "gpt-5.1" | "gpt-5.2" | ...
└── 约束: [...]
```

"跟随全局默认" 选项对应 `model_override = null`。
选择具体模型时，保存 `model_override = "gpt-5.2"` 到 `ContentBlock`。

#### C3: API 层对接

**文件:** `frontend/lib/api.ts`

新增：
- `modelsAPI.list()` -- 调用 `GET /api/models`
- `settingsAPI.getAgentSettings()` 已有，response 新增 `default_model` / `default_mini_model`
- `settingsAPI.updateAgentSettings()` 已有，request 新增 `default_model` / `default_mini_model`
- `blockAPI.update()` 已有，payload 中可传 `model_override`

`ContentBlock` 类型定义中增加 `model_override?: string | null`。

#### C4: 端到端测试

| # | 测试项 | 操作 | 预期 |
|---|--------|------|------|
| 1 | 设置页加载模型列表 | 打开设置页 > 模型配置 | 显示可用模型 |
| 2 | 修改全局默认 | 选择新模型 > 保存 | API 返回成功，后续生成用新模型 |
| 3 | 内容块选择模型 | 编辑块 > 选择具体模型 > 保存 | `model_override` 持久化 |
| 4 | 内容块生成用覆盖模型 | 点击生成 | 使用指定模型，日志记录正确模型名 |
| 5 | 内容块选择"跟随全局" | 选择回默认 > 保存 | `model_override = null`，回退到全局 |

---

## 四、文件改动清单

### 后端

| # | 文件 | 改动类型 | 说明 |
|---|------|---------|------|
| 1 | `core/models/agent_settings.py` | 修改 | 加 `default_model`, `default_mini_model` 字段 |
| 2 | `core/models/content_block.py` | 修改 | 加 `model_override` 字段，更新 `to_tree_dict()` |
| 3 | `scripts/init_db.py` | 修改 | 增量 migration 逻辑 |
| 4 | `core/llm.py` | 修改 | `get_chat_model()` 按模型名自动选 provider |
| 5 | `core/llm_compat.py` | 修改 | 加 `resolve_model()`, `_infer_provider()`, `_get_agent_settings_model()`; 修改 `sanitize_messages()` 接受 `model` 参数 |
| 6 | `core/models/generation_log.py` | 修改 | `calculate_cost` 增加 gpt-5.2, claude-sonnet-4-5 定价 |
| 7 | `api/models.py` | **新建** | `/api/models` 可用模型列表端点 |
| 8 | `main.py` | 修改 | 注册 models router |
| 9 | `api/settings.py` | 修改 | `AgentSettingsUpdate/Response` 加 model 字段 |
| 10 | `api/blocks.py` | 修改 | `generate/stream` 使用 `resolve_model` + `get_chat_model` |
| 11 | `core/agent_tools.py` | 修改 | `_rewrite/_generate/_query_field_impl` 使用 `resolve_model` |
| 12 | `core/tools/field_generator.py` | 修改 | 接受 `model` 参数 |
| 13 | `tests/test_model_selection.py` | **新建** | 单元测试 |

### 前端

| # | 文件 | 改动类型 | 说明 |
|---|------|---------|------|
| 14 | `lib/api.ts` | 修改 | 加 `modelsAPI`, ContentBlock 类型加 `model_override` |
| 15 | `app/settings/page.tsx` | 修改 | 加 `"models"` tab |
| 16 | `components/settings/model-settings-section.tsx` | **新建** | 全局默认模型选择 UI |
| 17 | `components/content-block-editor.tsx` | 修改 | 内容块模型覆盖下拉 |

**总计: 17 个文件（3 个新建 + 14 个修改）**

---

## 五、不涉及的部分（明确排除）

| 排除项 | 理由 |
|--------|------|
| 模板级模型配置（FieldTemplate / PhaseTemplate） | 已与用户确认合并到全局级 |
| Agent 对话模型切换 | Agent 对话不操作特定内容块，用全局默认即可 |
| 评估/模拟器模型切换 | 用全局默认即可 |
| 删除 `.env` 的 `LLM_PROVIDER` 变量 | 保留作为无 DB 配置时的回退 |
| 动态探测 API 可用模型 | 模型列表硬编码即可，避免启动时 API 调用延迟 |

---

## 六、设计决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 模型列表来源 | A. 调用 OpenAI/Anthropic API 动态获取 / B. 硬编码已验证的模型 | **B. 硬编码** | API 动态获取需要网络调用，启动慢，且返回的模型不一定都适合 chat（如 gpt-5.3-codex）。硬编码已验证模型更可靠 |
| 覆盖链层数 | A. 三级（全局+模板+块）/ B. 两级（全局+块） | **B. 两级** | 用户确认模板不需要独立模型配置 |
| 跨 provider 支持 | A. 限制同一 provider / B. 允许混用 | **B. 允许混用** | 两个 API Key 已同时配置，技术上已支持，只需 `get_chat_model` 按模型名自动判断 |
| AgentSettings 缓存 | A. 每次查 DB / B. lru_cache + 手动失效 / C. 进程内变量 + 写入时更新 | **C. 进程内变量** | 最简单，单进程部署（uvicorn single worker），写入时同步更新缓存变量即可 |
| 全局 `llm` 单例保留 | A. 删除全局单例，全部动态创建 / B. 保留全局单例，仅内容块生成动态创建 | **B. 保留** | 20+ 处 import 全局 `llm`，全部改动风险大。仅内容块生成（3-4 个函数）需要动态模型，其余用全局单例即可 |

---

## 七、里程碑与 TODO

### M5: 模型选择功能

**目标:** 用户可在 UI 选择全局默认模型，每个内容块可独立覆盖。
**前置依赖:** M4 完成。
**优先级:** 用户体验提升，不阻塞核心功能。

| # | 任务 | 文件 | 状态 | 说明 |
|---|------|------|------|------|
| M5-A1 | `AgentSettings` 加 `default_model` / `default_mini_model` | `core/models/agent_settings.py` | ✅ 完成 | 两个 nullable String(100) 字段 |
| M5-A2 | `ContentBlock` 加 `model_override` | `core/models/content_block.py` | ✅ 完成 | 一个 nullable String(100) 字段 + `to_tree_dict()` 更新 |
| M5-A3 | DB migration | `scripts/init_db.py` | ✅ 完成 | ALTER TABLE 增量添加列（幂等） |
| M5-A4 | `get_chat_model()` 按模型名自动选 provider | `core/llm.py` | ✅ 完成 | `claude-*` -> Anthropic, 其余 -> OpenAI |
| M5-A5 | `resolve_model()` 覆盖链函数 | `core/llm_compat.py` | ✅ 完成 | 核心逻辑 + AgentSettings 缓存 (TTL 60s) |
| M5-A6 | `sanitize_messages()` 接受 model 参数 | `core/llm_compat.py` | ✅ 完成 | 按实际模型判断 provider 约束 |
| M5-A7 | `/api/models` 端点 | `api/models.py`（新建）+ `main.py` | ✅ 完成 | 返回可用模型列表 + 当前默认 |
| M5-A8 | `calculate_cost` 扩展定价 | `core/models/generation_log.py` | ✅ 完成 | 增加 gpt-5.2, claude-sonnet-4-5 |
| M5-A9 | 单元测试 Phase A | `tests/test_model_selection.py`（新建） | ✅ 完成 | resolve_model, get_chat_model, sanitize_messages (27 tests) |
| M5-B1 | Settings API 支持 model 字段 | `api/settings.py` | ✅ 完成 | AgentSettingsUpdate/Response 扩展 |
| M5-B2 | Blocks API 支持 model_override | `api/blocks.py` | ✅ 完成 | BlockUpdate 传递 + BlockResponse 输出 |
| M5-B3 | `generate_block_content` 使用 `resolve_model` | `api/blocks.py` | ✅ 完成 | 替换 `await llm.ainvoke()` 为动态模型 |
| M5-B4 | `generate_block_content_stream` 使用 `resolve_model` | `api/blocks.py` | ✅ 完成 | 替换 `async for chunk in llm.astream()` |
| M5-B5 | `generate_ai_prompt` 使用 `resolve_model` | `api/blocks.py` | ✅ 完成 | AI 提示词生成也走用户默认模型 |
| M5-B6 | `agent_tools.py` rewrite/generate/query 使用 `resolve_model` | `core/agent_tools.py` | ✅ 完成 | 3 个函数操作具体内容块 |
| M5-B7 | `field_generator.py` 接受 model 参数 | `core/tools/field_generator.py` | ✅ 完成 | generate_field / generate_field_stream |
| M5-B8 | 后端集成测试 | curl / pytest | ✅ 完成 | 278 tests passed, 覆盖链回退验证 |
| M5-C1 | 前端 `modelsAPI` + ContentBlock 类型更新 | `lib/api.ts` | ✅ 完成 | 新增 API 调用 + 类型定义 |
| M5-C2 | 设置页"模型配置" Tab | `settings/page.tsx` + `model-settings-section.tsx`（新建） | ✅ 完成 | 全局默认模型选择 UI |
| M5-C3 | 内容块编辑器模型覆盖下拉 | `content-block-editor.tsx` | ✅ 完成 | "跟随全局" + 具体模型列表 |
| M5-C4 | 前端构建验证 | npm run build | ✅ 完成 | 零错误 |
| M5-C5 | 端到端测试 | curl + 前端 build | ✅ 完成 | 覆盖链、API 读写、model_override 清除 |

---

## 八、向后兼容

| 场景 | 行为 |
|------|------|
| 不配全局默认、不配块覆盖 | 与改动前完全一致（回退到 .env） |
| 旧 ContentBlock 无 `model_override` 列 | migration 自动加列，默认 NULL，回退到全局 |
| 旧 AgentSettings 无 `default_model` 列 | migration 自动加列，默认 NULL，回退到 .env |
| `from core.llm import llm` 的 20+ 处调用 | 不变，全局单例行为不变 |
| 切回 `LLM_PROVIDER=openai` | 所有行为回退到 OpenAI 默认模型 |
| `resolve_model()` 无参调用 | 等同于 `get_model_name()`，返回全局默认 |
