# Google Gemini Provider 支持方案
# 创建时间: 2026-03-03
# 更新时间: 2026-03-03（全部完成：代码修改 + 测试通过 + 前端模型选择联通；模型升级至 3.x 系列）
# 功能: 在现有 OpenAI / Anthropic 双 Provider 架构上，以最小改动添加 Google Gemini 直连支持
# 关联: core/config.py, core/llm.py, core/llm_compat.py, core/models/generation_log.py, api/models.py, env_example.txt
# 前置: M4 LLM Provider 兼容性修复已完成（llm_compat.py 归一化体系已就位）

---

## 一、问题本质

### 1.1 现有 Provider 分发架构

系统在 `llm.py` 和 `llm_compat.py` 中各有一个 `_infer_provider()` 函数，基于**模型名前缀**进行分发：

```
模型名以 claude- 开头  → anthropic → ChatAnthropic
模型名以 gemini- 开头  → google    → ChatGoogleGenerativeAI
其他（含 gpt-* 等）    → openai    → ChatOpenAI
```

全局 provider 也可通过 `.env` 中 `LLM_PROVIDER=openai|anthropic|google` 控制。

### 1.2 为什么 LangChain 封装层已解决大部分问题

`langchain-google-genai` 的 `ChatGoogleGenerativeAI` 完整实现了 `BaseChatModel` 接口：
- `bind_tools()` + Tool Calling: 支持（Gemini 3.x 全系）
- `astream_events` 流式: 支持
- `with_structured_output()`: 支持
- `AIMessage.content`: **Gemini 3.x 可能返回 `list[dict]`**（同 Anthropic），需通过 `normalize_content()` 转为 str

因此 `sanitize_messages()` 无需改动（Google 走 pass-through），`normalize_content()` 已有的 list 处理逻辑天然兼容 Gemini 3.x。

### 1.3 可用模型（2026-03-03 API 验证）

| 模型 ID | 显示名 | tier | Tool Calling | 适用场景 |
|---------|--------|------|-------------|---------|
| `gemini-3.1-pro-preview` | Gemini 3.1 Pro | main | 支持 | **主力模型**，质量最高 |
| `gemini-3-pro-preview` | Gemini 3 Pro | main | 支持 | 稳定主力备选 |
| `gemini-3-flash-preview` | Gemini 3 Flash | mini | 支持 | 轻量低成本任务 |

> **策略**: 最低使用 3.x 系列，不使用 2.x。默认主力 = `gemini-3.1-pro-preview`，默认 mini = `gemini-3-flash-preview`。

---

## 二、改动范围（7 个文件）

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `requirements.txt` | 新增 1 行 | `langchain-google-genai>=2.0.0` |
| `backend/core/config.py` | 新增 3 个字段 | `google_api_key`, `google_model`=gemini-3.1-pro-preview, `google_mini_model`=gemini-3-flash-preview |
| `backend/core/llm.py` | 扩展 3 处 | `_infer_provider` 加 gemini；`get_chat_model` 加 google 分支；`llm_mini` 加 google 判断 |
| `backend/core/llm_compat.py` | 扩展 2 处 | `_infer_provider` 加 gemini；`get_model_name` 加 google 分支 |
| `backend/core/models/generation_log.py` | 新增 3 行 | 定价表加 Gemini 3.x 模型 |
| `backend/api/models.py` | 新增 3 行模型 + 3 行过滤 | AVAILABLE_MODELS 加 Google 3.x 模型；过滤逻辑加 `has_google` |
| `backend/env_example.txt` | 新增示例 | 方式四：Google AI 直连 |

### 前端无需修改

前端 5 个组件（`content-block-editor.tsx`, `content-block-card.tsx`, `model-settings-section.tsx`,
`templates-section.tsx`, `phase-templates-section.tsx`）全部通过 `modelsAPI.list()` 从 `GET /api/models/` 
动态获取模型列表。后端 `api/models.py` 修复后，前端自动联通。

---

## 三、测试结果

### 3.1 单元测试（全部通过）

| 测试类 | 数量 | 覆盖内容 |
|--------|------|---------|
| `TestInferProviderGoogle` | 5 | `_infer_provider` 对 gemini-* 前缀识别 + llm.py/llm_compat.py 一致性 |
| `TestGetModelNameGoogle` | 3 | `get_model_name` 对 google provider 的 main/mini/fallback |
| `TestGetChatModelGoogle` | 4 | `get_chat_model` 实例化正确类型 + 不影响其他 provider |
| `TestSanitizeMessagesGoogle` | 2 | google provider pass-through，不合并 SystemMessage |
| `TestCalculateCostGemini` | 4 | Gemini 3.x 定价计算 + Flash 比 Pro 便宜 |
| `TestListModelsGoogleFiltering` | 4 | API Key 过滤 + AVAILABLE_MODELS 包含 Google + tier 正确 |

### 3.2 集成测试（真实 API 调用，全部通过）

| 测试 | 模型 | 验证内容 | 结果 |
|------|------|---------|------|
| `test_integration_ainvoke` | gemini-3-flash-preview | 基本对话，返回 str | PASSED |
| `test_integration_streaming` | gemini-3-flash-preview | 流式输出 | PASSED |
| `test_integration_bind_tools` | gemini-3.1-pro-preview | tool calling | PASSED |
| `test_integration_normalize_content_compatibility` | gemini-3-flash-preview | normalize_content 兼容性 | PASSED |
| `test_integration_3_1_pro_preview_main_model` | gemini-3.1-pro-preview | 主力模型基本对话 | PASSED |

---

## 四、关键设计决策

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 接入方式 | A. OpenRouter 中转 / B. langchain-google-genai 直连 | **B. 直连** | 无额外延迟和成本 |
| content 类型 | 是否需要 normalize_content 特殊处理 | **不需要额外改动** | Gemini 3.x 返回 list[dict]，现有 normalize_content 已兼容 |
| sanitize_messages | 是否需要 Gemini 特殊处理 | **不需要** | 现有逻辑对非 anthropic 是 pass-through |
| max_tokens 参数名 | `max_tokens` vs `max_output_tokens` | **`max_output_tokens`** | ChatGoogleGenerativeAI 的参数名 |
| api_key 参数名 | `api_key` vs `google_api_key` | **`google_api_key`** | ChatGoogleGenerativeAI 的参数名 |
| 默认模型 | 2.x vs 3.x | **gemini-3.1-pro-preview / gemini-3-flash-preview** | 3.x 系列是最新版，最低使用 3.0 |

---

## 五、TODO（执行清单）

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| S1 | 新增 langchain-google-genai 依赖 | `requirements.txt` | 已完成 |
| S2 | 新增 Google 配置项 | `backend/core/config.py` | 已完成 |
| S3a | `_infer_provider` 加 gemini 识别 | `backend/core/llm.py` | 已完成 |
| S3b | `get_chat_model` 加 google 分支 | `backend/core/llm.py` | 已完成 |
| S3c | `llm_mini` 加 google 判断 | `backend/core/llm.py` | 已完成 |
| S4a | `_infer_provider` 同步更新 | `backend/core/llm_compat.py` | 已完成 |
| S4b | `get_model_name` 加 google 分支 | `backend/core/llm_compat.py` | 已完成 |
| S5 | 定价表加 Gemini 3.x 模型 | `backend/core/models/generation_log.py` | 已完成 |
| S6 | AVAILABLE_MODELS 加 Google 3.x + 过滤逻辑 | `backend/api/models.py` | 已完成 |
| S7 | 新增 Gemini 配置示例 | `backend/env_example.txt` | 已完成 |
| S8 | 单元测试 | `tests/test_gemini_provider.py` | 已完成 |
| S9 | 集成测试（真实 API 调用） | `tests/test_gemini_provider.py` | 已完成 |

---

## 六、向后兼容保证

- 切换回 `LLM_PROVIDER=openai` 或 `anthropic`：行为与改动前完全一致
- `_infer_provider` 对非 `claude-`、非 `gemini-` 前缀仍回退 `openai`
- `get_model_name()` 对 `openai`/`anthropic` 的返回值不变
- `generate_log.py` 新增定价行，不修改任何已有定价
- `sanitize_messages` 对 google provider 走 `provider != "anthropic"` 分支，是 pass-through
- `AVAILABLE_MODELS` 新增 Google 条目，不修改已有 OpenAI/Anthropic 条目
- 前端代码零修改

---

## 七、使用方式

`.env` 中设置：

```
LLM_PROVIDER=google
GOOGLE_API_KEY=AIzaSy-xxxx
GOOGLE_MODEL=gemini-3.1-pro-preview          # 可选，默认 gemini-3.1-pro-preview
GOOGLE_MINI_MODEL=gemini-3-flash-preview     # 可选，默认 gemini-3-flash-preview
```

然后启动后端即可。前端设置页和内容块编辑器的模型选择下拉会自动显示 Gemini 模型。
