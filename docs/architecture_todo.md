# 架构优化 TODO List

创建时间：2026-02-13
最后更新：2026-02-14
状态：旧评估系统完全清除 — Eval V2 (EvalRun/EvalTask/EvalTrial) 统一
目标：消除项目中非本质和有明显断裂的架构问题，按优先级逐步推进

---

## 🔴 P0：根本性结构问题（影响全局，必须最先解决）

### P0-1. ProjectField / ContentBlock 双轨数据模型统一

**问题描述**

系统中存在两套几乎完全平行的数据抽象：
- 旧架构：`ProjectField`（`backend/core/models/project_field.py`）+ `api/fields.py` + 前端 `Field` interface
- 新架构：`ContentBlock`（`backend/core/models/content_block.py`）+ `api/blocks.py` + 前端 `ContentBlock` interface

两者通过 `use_flexible_architecture` 布尔标志在运行时做条件分支。这导致**系统的每一层**都在做双倍工作：

**具体影响清单**

| 层级 | 旧架构文件 | 新架构文件 | 重复点 |
|------|-----------|-----------|--------|
| 后端模型 | `models/project_field.py` | `models/content_block.py` | 字段定义近似（content, status, ai_prompt, depends_on, constraints, pre_questions, need_review, digest） |
| 后端 API | `api/fields.py` | `api/blocks.py` | 完整 CRUD + generate + stream 两套路由 |
| Agent 工具 | `agent_tools.py` `_find_block_or_field()` | 同一函数 | 每次操作查两张表（先 ContentBlock 再 ProjectField） |
| Agent 调研保存 | `run_research` 中保存到 ProjectField | 同一函数中也保存到 ContentBlock | 两条保存路径 |
| 摘要索引 | `digest_service.py` 查 ProjectField | 同一函数查 ContentBlock | `build_field_index` 分别查两张表合并结果 |
| 前端类型 | `lib/api.ts` `Field` interface | `lib/api.ts` `ContentBlock` interface | 两套 TypeScript 类型 |
| 前端 API | `fieldAPI` 对象 | `blockAPI` 对象 | 两套 API 调用方法 |
| 前端组件 | `FieldCard`（content-panel.tsx 内） | `ContentBlockCard` + `ContentBlockEditor` | 两套编辑/展示组件 |
| 前端数据流 | `fields` prop | `allBlocks` prop | WorkspacePage 同时管理两套数据，所有子组件同时接收 |
| 前端虚拟块 | `progress-panel.tsx` 将 Field 转为虚拟 ContentBlock | — | `isVirtual` / `virtual_phase_*` 前缀到处判断 |
| 控制标志 | `use_flexible_architecture` | — | 14+ 个文件中做条件判断 |

**目标方案**
- 全面迁移到 `ContentBlock` 单一模型
- 废弃 `ProjectField`、`api/fields.py`、`fieldAPI`、`Field` interface
- 废弃 `use_flexible_architecture` 标志
- 所有旧项目执行数据迁移（已有 `scripts/migrate_content_blocks.py`）

**子任务**

- [ ] P0-1a. 确保所有旧项目的 ProjectField 数据已迁移到 ContentBlock
- [x] P0-1b. 修改 Agent 工具层：`_find_block_or_field()` 改为只查 ContentBlock ✅ 2026-02-14
- [x] P0-1c. 修改 `run_research` 工具：去除 ProjectField 保存路径 ✅ 2026-02-14
- [x] P0-1d. 修改 `digest_service.py`：去除 ProjectField 查询 ✅ 2026-02-14
- [x] P0-1e. `architecture_reader.py` 5 个函数改为只查 ContentBlock ✅ 2026-02-14
- [x] P0-1f. `api/agent.py` `_resolve_references` 去除 ProjectField ✅ 2026-02-14
- [x] P0-1g. `api/eval.py` + `api/simulation.py` + `persona_manager.py` + `evaluator.py` + `simulator.py` + `field_generator.py` 去除 ProjectField ✅ 2026-02-14
- [x] P0-1h-1. `architecture_writer.py` 所有函数改为只用 ContentBlock（去除 use_flexible_architecture 分支）✅ 2026-02-14
- [x] P0-1h-2. `outline_generator.py` 改为创建 ContentBlock 而非 ProjectField ✅ 2026-02-14
- [x] P0-1i. `api/fields.py` 所有路由标记 `deprecated=True` ✅ 2026-02-14
- [x] P0-1j. 前端：WorkspacePage 去除 `fields` state 和 `loadFields()`，统一用 `allBlocks` ✅ 2026-02-14
  - 删除 `handleSendMessage`、`fieldVersionWarning`、`handleFieldUpdate`
  - 删除传给子组件的 `fields` prop
- [x] P0-1k. 前端主组件去除 `fields`/`fieldAPI`/`isVirtual`/`useFlexibleArchitecture` ✅ 2026-02-14
  - `agent-panel.tsx`：去除 `fields` 和 `useFlexibleArchitecture` prop
  - `progress-panel.tsx`：去除 `fields` prop、`buildVirtualBlocksFromFields`、统一用 `blockAPI`
  - `eval-phase-panel.tsx`：去除 `fields` prop
  - `content-block-editor.tsx`：去除所有 `if (useFieldAPI)` 分支和 `isVirtual` prop
  - `content-block-card.tsx`：去除 `isVirtual` prop
  - `content-panel.tsx`：去除传给 Editor/Card 的 `isVirtual` prop
  - `useBlockGeneration.ts`：去除 `useFieldAPI` prop，统一用 `blockAPI`
- [x] P0-1l. 前端：`Field` interface 和 `fieldAPI` 标记 `@deprecated`（FieldCard 经典视图仍编译引用，待 P2-5a 移除后删除） ✅ 2026-02-14
- [x] P0-1m. 前端遗留清理：`channel-selector.tsx`、`research-panel.tsx`、`proposal-selector.tsx`、`eval-field-editors.tsx` 已改用 `blockAPI` ✅ 2026-02-14
- [x] P0-1n. 后端：`fields.router` 保留注册但标记 deprecated 注释 ✅ 2026-02-14
- [x] P0-1o. 清理 `use_flexible_architecture`：后端默认值改为 True、前端所有组件移除条件分支 ✅ 2026-02-14
  - `progress-panel.tsx`：移除传统视图、ViewMode、视图切换按钮，统一树形视图
  - `create-project-modal.tsx`：移除架构选择开关，默认创建 ContentBlock 架构
  - `content-panel.tsx`：移除 `useFlexibleArchitecture` prop 和条件分支
  - `agent-panel.tsx`：移除 `useFlexibleArchitecture` prop
  - `workspace/page.tsx`：移除 `useFlexibleArchitecture` prop 传递
  - 后端 `models/project.py`：默认值改为 True，标记已废弃
  - 后端 `api/projects.py`：所有 schema 默认值改为 True、clone/fork 固定为 True

**审计修复**（2026-02-14 二次审计发现并修复的残留问题）
- [x] `agent_tools.py`: `_find_block_or_field` → `_find_block`，去除 `etype` 返回值和所有调用处解包 ✅
- [x] `api/blocks.py`: 5 处硬编码 `"gpt-5.1"` → `settings.openai_model` ✅
- [x] `api/agent.py`: `getattr(llm, "model_name", "gpt-4o")` → `settings.openai_model` ✅
- [x] `version_service.py`: docstring 残留 "ProjectField.id" 引用已清理 ✅
- [x] `content_version.py`: docstring 残留 ProjectField 引用已清理 ✅
- [x] `field_generator.py`: 鸭子类型注释 "ProjectField 或 ContentBlock" → "ContentBlock" ✅
- [x] `evaluator.py`: 鸭子类型注释 "ContentBlock 或 ProjectField" → "ContentBlock" ✅
- [x] `prompt_engine.py`: 类型注解 `ProjectField` → `ContentBlock`（import + 3 处函数签名 + 1 处 docstring） ✅
- [x] `models/project.py`: `fields` relationship 添加废弃注释标记 ✅

**预估工时**：✅ 全面完成。后端统一 + 前端主组件 + 辅助组件 + `use_flexible_architecture` 清理 + FieldCard 物理删除 + 残留引用审计修复全部完成。
**剩余**：`Field` interface / `fieldAPI` 物理删除（已标记 @deprecated，当前无活跃调用方；可在确认无残留引用后安全删除）
**风险**：涉及所有组件，需要充分测试

---

### P0-2. LangGraph Checkpointer 从 MemorySaver 升级为持久化存储

**问题描述**

当前 Agent 的对话状态存储方式：
1. LangGraph 用 `MemorySaver`（纯内存）做 checkpoint → 重启后全部丢失
2. `api/agent.py` 另外将每条消息存入 `ChatMessage` 表
3. 重启后通过 `_load_seed_history()` 从 DB 读取消息"Bootstrap"回 LangGraph

**根本问题**：
- ChatMessage DB 只存了 Human/AI 消息的 `content` 字段，**不包含** ToolMessage、tool_calls 元数据
- Bootstrap 恢复的对话上下文**本质上是残缺的**（LLM 看不到之前的工具调用链）
- Bootstrap 逻辑复杂、容易出 bug（需要判断 has_checkpoint、拼接历史、去重）

**相关代码**
- `backend/core/orchestrator.py` L341-364：`MemorySaver()` 创建
- `backend/api/agent.py` L617-629：Bootstrap 逻辑
- `backend/api/agent.py` L153-175：`_load_seed_history()` 函数

**目标方案**
- 将 `MemorySaver()` 替换为 `SqliteSaver`（代码注释已经指明路径）
- 删除 `_load_seed_history()` 函数和 Bootstrap 逻辑
- `ChatMessage` 表退化为纯展示用（前端对话历史列表），不再承担"恢复上下文"的职责

**子任务**

- [x] P0-2a. 替换 `MemorySaver` 为 `SqliteSaver`（`data/agent_checkpoints.db`）✅ 2026-02-13
- [x] P0-2b. 删除 `_load_seed_history()` 函数 ✅ 2026-02-13
- [x] P0-2c. 删除 `stream_chat()` 中的 Bootstrap 条件判断 ✅ 2026-02-13
- [x] P0-2d. 验证 SqliteSaver 正确创建和 setup，测试通过 ✅ 2026-02-13
- [ ] P0-2e. 评估是否还需要在 `ChatMessage` 存储 tools_used 等元数据（可能只需 content 和 role）— 低优先级，不阻塞

**预估工时**：小（核心改动 ~10 行代码，主要是测试验证）

---

## 🟠 P1：明显的代码重复和职责混乱

### P1-1. 版本保存逻辑三处重复 → 提取公共服务

**问题描述**

"保存旧内容为 ContentVersion"的逻辑在三个文件中各写了一遍：

| 文件 | 函数名 | 代码位置 |
|------|--------|---------|
| `backend/core/agent_tools.py` | `_save_version()` | L73-93 |
| `backend/api/agent.py` | `_save_version_before_overwrite()` | L42-66 |
| `backend/api/blocks.py` | `_save_content_version()` | L36-67 |

三个函数逻辑几乎完全相同：查最大 version_number → +1 → 创建 ContentVersion → flush。唯一差异是 `api/agent.py` 版本多了一个 `source_detail` 参数。

**子任务**

- [x] P1-1a. 创建 `backend/core/version_service.py`，实现 `save_content_version()` ✅ 2026-02-13
- [x] P1-1b. `agent_tools.py` 的 `_save_version` 改为调用公共方法 ✅ 2026-02-13
- [x] P1-1c. `api/agent.py` 的 `_save_version_before_overwrite` 改为调用公共方法 ✅ 2026-02-13
- [x] P1-1d. `api/blocks.py` 的 `_save_content_version` 改为调用公共方法 ✅ 2026-02-13

**预估工时**：小

---

### P1-2. 前端 SSE 流式读取逻辑三处重复 → 提取工具函数

**问题描述**

以下三个组件都写了几乎完全相同的 SSE 读取循环：`reader.read()` → `decode` → `split("\n")` → `startsWith("data: ")` → `JSON.parse`

| 组件 | 文件 | 代码行 |
|------|------|--------|
| ContentBlockEditor | `content-block-editor.tsx` | L502-545 |
| ContentBlockCard | `content-block-card.tsx` | L319-356 |
| ContentPanel (自动生成) | `content-panel.tsx` | L191-207 |
| AgentPanel (agent stream) | `agent-panel.tsx` | L440-585 |

此外 `lib/api.ts` 中的 `runAutoTriggerChain` 里的 `_generateSingleBlock` 也有一份。

**子任务**

- [x] P1-2a. 创建 `frontend/lib/sse.ts`，实现 `readSSEStream()` async generator（含跨 chunk 行缓冲修复） ✅ 2026-02-13
- [x] P1-2b. `ContentBlockEditor` 的 handleGenerate SSE 循环 → `for await (readSSEStream)` ✅ 2026-02-13
- [x] P1-2c. `ContentBlockCard` 的 handleGenerate SSE 循环 → `for await (readSSEStream)` ✅ 2026-02-13
- [x] P1-2d. `ContentPanel` 的 checkAndAutoGenerate → `for await (readSSEStream)` drain ✅ 2026-02-13
- [x] P1-2e. `lib/api.ts` 的 `_generateSingleBlock` → `for await (readSSEStream)` ✅ 2026-02-13
- [x] P1-2f. `lib/api.ts` 的 `agentAPI.stream()` → `yield* readSSEStream()` ✅ 2026-02-13

**预估工时**：小

---

### P1-3. ContentBlockCard 和 ContentBlockEditor 的生成逻辑完全重复 → 提取自定义 Hook

**问题描述**

`ContentBlockCard`（卡片视图）和 `ContentBlockEditor`（详情编辑器）实现了完全相同的业务逻辑：
- 依赖检查（检查 depends_on 的内容是否已生成）
- 流式生成调用（`blockAPI.generateStream`）
- 生成过程中的内容累积
- 停止生成（AbortController）
- 生成完成后触发自动链（`runAutoTriggerChain`）
- 前端通知（`sendNotification`）

两者唯一的区别是 UI 布局：Card 是紧凑卡片，Editor 是完整编辑区。

**子任务**

- [x] P1-3a. 创建 `frontend/lib/hooks/useBlockGeneration.ts` 自定义 Hook ✅ 2026-02-13
  - 输入：`block, projectId, allBlocks, useFieldAPI, preAnswers, hasPreQuestions, onUpdate, onContentReady`
  - 输出：`{ isGenerating, generatingContent, canGenerate, unmetDependencies, handleGenerate, handleStop }`
  - 内部通过 `generatingBlockIdRef` 追踪块切换，自动过滤非当前块的生成状态
- [x] P1-3b. `ContentBlockEditor` 的生成相关状态和逻辑替换为 Hook 调用 ✅ 2026-02-13
  - 删除 ~80 行重复的 SSE 生成/停止逻辑，替换为 Hook 的 `handleGenerate` + `handleStop`
- [x] P1-3c. `ContentBlockCard` 的生成相关状态和逻辑替换为 Hook 调用 ✅ 2026-02-13
  - 删除 ~80 行重复的 SSE 生成/停止逻辑 + `generatingRef` + `abortControllerRef`

**预估工时**：中

---

### P1-4. 自动触发生成存在两套不同的实现

**问题描述**

- **旧架构**（ProjectField）：`content-panel.tsx` 中的 `checkAndAutoGenerate`，基于 `phaseFields` 查找 pending + need_review=false + 依赖已满足的字段，调用 `api/fields/{id}/generate/stream`，且硬编码只在 `produce_inner` 阶段触发
- **新架构**（ContentBlock）：`lib/api.ts` 中的 `runAutoTriggerChain`，调用后端 `/api/blocks/project/{id}/check-auto-triggers`，由后端判断可触发的块，支持并行生成和递归触发下游

两套逻辑分别从 `content-panel.tsx`、`content-block-editor.tsx`、`content-block-card.tsx`、`progress-panel.tsx` 调用。

**子任务**

- [x] P1-4a. `content-panel.tsx` 中的 `checkAndAutoGenerate` 已移除 ✅ 2026-02-14
- [x] P1-4b. 统一使用 `runAutoTriggerChain` 作为唯一的自动触发入口 ✅ 2026-02-14
  - 调用点：`progress-panel.tsx`、`useBlockGeneration.ts`、`content-block-editor.tsx`、`content-block-card.tsx`
- [x] P1-4c. 审查所有调用点，确认 `_autoChainLocks` 全局锁在 JS 单线程模型下安全防止竞态 ✅ 2026-02-14

**预估工时**：中（依赖 P0-1 完成）

---

### P1-5. advance_to_phase 逻辑在两处重复

**问题描述**

推进项目到下一组的逻辑存在两处独立实现：

| 位置 | 触发方 | 代码 |
|------|--------|------|
| `backend/core/agent_tools.py` L503-573 | LLM 通过 tool call 调用 | `advance_to_phase` tool |
| `backend/api/agent.py` L985-1051 | 前端按钮直接调用 | `POST /api/agent/advance` |

两者的核心逻辑相同（读 phase_order → 找当前位置 → 设下一个 → 更新 phase_status），但有细微差异：
- API endpoint 额外创建一条 ChatMessage
- tool 版本有 PHASE_ALIAS 中文→代码映射
- API endpoint 没有跳转指定阶段的能力

**子任务**

- [x] P1-5a. 创建 `backend/core/phase_service.py`，含 `advance_phase()` + `PHASE_ALIAS` + `PHASE_DISPLAY_NAMES` ✅ 2026-02-13
- [x] P1-5b. `agent_tools.py` 的 `advance_to_phase` tool 改为调用 phase_service ✅ 2026-02-13
- [x] P1-5c. `api/agent.py` 的 `advance_phase` endpoint 改为调用 phase_service ✅ 2026-02-13
- [x] P1-5d. 删除 `api/agent.py` 中的 `_get_phase_field_name()`，映射统一到 phase_service ✅ 2026-02-13

**预估工时**：小

---

## 🟡 P2：架构设计可优化

### P2-1. 前端状态管理过度依赖 refreshKey 计数器和 prop drilling

**问题描述**

WorkspacePage（`app/workspace/page.tsx`）是整个前端的状态枢纽，管理了 15+ 个 useState：
- `projects`, `currentProject`, `fields`, `allBlocks`, `selectedBlock`
- `refreshKey`, `blocksRefreshKey`
- `showCreateModal`, `showSearch`, `showProjectMenu`, `isBatchMode` 等 UI 状态

问题包括：
1. **`key={refreshKey}` 导致 AgentPanel 完全销毁重建**（L661），丢失对话历史加载状态、输入框内容等内部状态
2. **7+ 个回调函数** (`onContentUpdate`, `onFieldsChange`, `onPhaseAdvance`, `onBlockSelect`, `onBlocksChange`, `onProjectChange`, `onFieldUpdate`) 层层传递，每个子组件都要接收大量 callback props
3. **刷新时机散落**：同一个"内容更新"事件，在不同组件中用不同方式触发刷新（`setBlocksRefreshKey(prev=>prev+1)` vs `loadFields()` vs `projectAPI.get()`）

**子任务**

- [ ] P2-1a. 引入 Zustand 或 React Context 做项目级状态管理
  - 核心状态：`currentProject`, `allBlocks`, `selectedBlock`
  - 核心方法：`refreshBlocks()`, `refreshProject()`, `selectBlock()`
- [ ] P2-1b. 消除 `refreshKey` —— AgentPanel 通过订阅 store 变化来刷新，而不是被 key 重建
- [ ] P2-1c. 消除 `blocksRefreshKey` —— 各组件直接调用 store 的 `refreshBlocks()`
- [ ] P2-1d. 简化 WorkspacePage 的 callback props 传递

**预估工时**：中

---

### P2-2. Agent system prompt 每次 agent_node 执行都做 DB 查询

**问题描述**

`orchestrator.py` 的 `build_system_prompt()` 在每次 `agent_node` 执行时被调用，内部做两次 DB 查询：
1. `build_field_index(project_id)` — 查 ProjectField + ContentBlock 两张表
2. 查 Project 获取 phase_status

在一次对话中如果 LLM 调用了 3 个工具，agent_node 会执行 4 次（初始 + 每次工具返回后重新进入），即做 **8 次 DB 查询**来构建本质上相同的 system prompt（项目状态在一次对话中极少变化）。

**子任务**

- [x] P2-2a. 对 `build_field_index()` 的结果添加 30s TTL 缓存 ✅ 2026-02-13
  - 在 `digest_service.py` 中实现 `_field_index_cache` + `invalidate_field_index_cache()`
  - 同一对话轮次中多次 agent_node 执行不再重复查 DB
- [x] P2-2b. 工具执行后自动使缓存失效 ✅ 2026-02-13
  - 在 `orchestrator.py` 的 `agent_node` 中检测 ToolMessage → 调用 `invalidate_field_index_cache()`
  - 确保工具修改内容块后，下一轮 agent_node 看到最新索引

**预估工时**：小

---

### P2-3. 阶段名称映射（中文↔代码）散落在多处

**问题描述**

"阶段名称"的中文↔代码映射至少存在于以下 5 个位置：

| 文件 | 变量/函数 |
|------|----------|
| `backend/core/models/project.py` | `PROJECT_PHASES` 列表 |
| `backend/core/agent_tools.py` L529-534 | `PHASE_ALIAS` 字典（中文→代码） |
| `backend/api/agent.py` L183-195 | `_get_phase_field_name()` 函数（代码→中文） |
| `frontend/lib/utils.ts` L33-45 | `PROJECT_PHASES` + `PHASE_NAMES` |
| `frontend/components/progress-panel.tsx` L33-42 | `PHASE_SPECIAL_HANDLERS` + `FIXED_TOP_PHASES` 等 |

每次新增或修改阶段时需要改 5+ 个位置，极易遗漏。

**子任务**

- [x] P2-3a. 后端：创建 `core/phase_config.py` 统一定义 `PHASE_DEFINITIONS` ✅ 2026-02-13
  - 包含 code、display_name、special_handler、position
  - 自动派生 PHASE_ORDER、PHASE_DISPLAY_NAMES、PHASE_ALIAS 等
- [x] P2-3b. 后端：`phase_service.py`、`models/project.py`、`architecture_reader.py` 引用 phase_config ✅ 2026-02-13
- [ ] P2-3c. 考虑通过 API endpoint 暴露阶段配置，前端从接口获取而非硬编码 — 暂不需要，前端已与后端手工同步
- [x] P2-3d. 前端：`lib/utils.ts` 统一定义 `PHASE_DEFINITIONS`，`progress-panel.tsx` 引用而非重复定义 ✅ 2026-02-13
  - `PHASE_NAMES`、`PROJECT_PHASES`、`PHASE_SPECIAL_HANDLERS`、`FIXED_TOP_PHASES`、`DRAGGABLE_PHASES` 均从 utils 导入

**预估工时**：小

---

### P2-4. content-panel.tsx 内硬编码 `http://localhost:8000`

**问题描述**

`content-panel.tsx` L191：
```typescript
const response = await fetch(`http://localhost:8000/api/fields/${candidate.id}/generate/stream`, { ... });
```

而 `lib/api.ts` 已定义了 `API_BASE` 常量（从 `NEXT_PUBLIC_BACKEND_URL` 读取）。硬编码会导致部署环境下自动生成功能失效。

**子任务**

- [x] P2-4a. 将 `http://localhost:8000` 替换为 `API_BASE` 引用（2处） ✅ 2026-02-13
- [x] P2-4b. 全局搜索确认前端 components 无其他硬编码 localhost URL ✅ 2026-02-13

**预估工时**：极小

---

### P2-5. 前端 `content-panel.tsx` 过于臃肿（2200+ 行）

**问题描述**

`content-panel.tsx` 是前端最大的组件文件，超过 2200 行，包含：
- FieldCard 内嵌组件（旧架构的卡片展示，~400 行）
- 消费者调研阶段的 JSON 格式判断和特殊渲染
- 意图分析阶段的特殊处理
- 外延设计阶段的渠道选择集成
- 评估阶段的 EvalPhasePanel 集成
- 自动生成逻辑（旧架构）
- 阶段推进按钮逻辑
- 模板选择弹窗
- 大量条件分支（根据 selectedBlock 的 block_type、special_handler 做不同渲染）

**子任务**

- [x] P2-5a. 删除 FieldCard / DependencyModal / ConstraintsModal 死代码（~1756 行），文件从 2138 行降至 382 行 ✅ 2026-02-14
- [x] P2-5b. ✅ 不需要 — 文件已 382 行，各阶段特殊视图（ResearchPanel、ProposalSelector、ChannelSelector、EvalPhasePanel）早已独立组件化
- [x] P2-5c. ✅ 已有 — `TemplateSelector` 已是 `frontend/components/template-selector.tsx` 独立组件

**预估工时**：✅ 全部完成

---

## 🔵 P3：清理和改善（非紧急但有价值）

### P3-1. 向后兼容代码需清理

**问题描述**

`orchestrator.py` L374-415 保留了 `ContentProductionAgent` 向后兼容类和 `content_agent` 全局实例。注释标注"M3 完成后删除"，但 `api/agent.py` 的 `/chat` 和 `/retry` 端点仍在使用 `content_agent.run()`。

**子任务**

- [x] P3-1a. `/chat` 已改为直接用 `agent_graph.ainvoke()`，保留 deprecated 标记 ✅ 2026-02-14
- [x] P3-1b. `/retry` endpoint 改为直接用 `agent_graph.ainvoke()` ✅ 2026-02-14
- [x] P3-1c. 删除 `ContentProductionAgent` 类和 `content_agent` 全局实例 ✅ 2026-02-14
- [x] P3-1d. 删除 `ContentProductionState = AgentState` 别名 ✅ 2026-02-14
- [x] P3-1e. 删除 `normalize_intent()` 和 `normalize_consumer_personas()` 辅助函数（无调用方） ✅ 2026-02-14

**预估工时**：小

---

### P3-2. golden_context 已废弃但残留在多处

**问题描述**

- `Project` 模型保留了 `golden_context` JSON 字段（L95），标注"已废弃"
- 前端 `Project` interface 中保留了 `golden_context: Record<string, string>`
- `agent_design.md` 文档仍描述 `state["golden_context"]` 为核心状态字段
- `orchestrator.py` 的辅助函数 `normalize_intent()` 和 `normalize_consumer_personas()` 似乎是为旧 golden_context 设计的

**子任务**

- [x] P3-2a. 清理所有 `golden_context` 读写点，DB 列保留（default={}）兼容旧数据 ✅ 2026-02-14
  - `persona_manager.py`: 改用 `architecture_reader.get_intent_and_research()` 获取意图
  - `outline_generator.py`: 改用 `get_intent_and_research()` + `creator_profile` 关系获取上下文
  - `api/projects.py`: 创建/克隆/Fork 不再写入 golden_context（设为 {}）
  - `ProjectUpdate`/`ProjectResponse` schema 标记废弃注释
- [x] P3-2b. 前端 `Project` interface 的 `golden_context` 标记 `@deprecated` + 改为可选 ✅ 2026-02-14
- [x] P3-2c. 从 `orchestrator.py` 中移除 `normalize_intent()` 和 `normalize_consumer_personas()`（已确认无调用方） ✅ 2026-02-14（P3-1e 同步完成）
- [x] P3-2d. `agent_design.md` 数据模型章节补充 golden_context 废弃说明 ✅ 2026-02-14

**预估工时**：✅ 全部完成（DB 列保留兼容旧数据，所有功能性读写已切换到 ContentBlock 依赖链）

---

### P3-3. 迁移脚本过多且不规范

**问题描述**

`backend/scripts/` 目录下有 17 个迁移脚本：
```
migrate_add_constraints.py
migrate_add_content_versions.py
migrate_add_digest.py
migrate_add_pre_questions.py
migrate_add_tool_prompts.py
migrate_add_undo.py
migrate_content_blocks.py
migrate_eval_tables.py
migrate_eval_v2.py
migrate_grader.py
migrate_simulator_prompts.py
fix_db_schema.py
add_flexible_architecture_field.py
add_special_field_templates.py
init_db.py
diagnose_blocks.py
_test_design_pref.py
```

没有使用 Alembic 等标准数据库迁移工具，手动执行容易遗漏或重复执行。

**子任务**

- [ ] P3-3a. 评估是否引入 Alembic 做后续 schema 变更管理
- [x] P3-3b. 将已执行的迁移脚本归档到 `scripts/archive/`（保留 `__init__.py` 和 `init_db.py`）✅ 2026-02-14
- [x] P3-3c. 在 `init_db.py` 中补充 Grader 预置数据（`PRESET_GRADERS`），新建 DB 无需跑旧迁移 ✅ 2026-02-14

**预估工时**：小

---

### P3-4. 设计文档与实际实现不一致

**问题描述**

`docs/` 目录下有 15+ 个设计文档，部分内容已过时：

| 文档 | 问题 |
|------|------|
| `agent_design.md` | 仍描述旧的 `ContentProductionState`（含 golden_context、fields、autonomy_settings、waiting_for_human），实际已简化为 4 字段的 `AgentState` |
| `agent_design.md` | 意图路由器（route_intent）已废弃，实际使用 LLM Tool Calling |
| `agent_design.md` | 工具列表（deep_research, web_search, export_content）与实际 AGENT_TOOLS 不匹配 |
| `architecture.md` | 文件为空（0 字节） |
| `frontend_agent_integration.md` | 可能与当前 SSE 流式架构不匹配 |

**子任务**

- [x] P3-4a. 更新 `agent_design.md`：State 定义、工具列表、流程图、Checkpointer、已移除旧设计对照表 — 全面与实际代码对齐 ✅ 2026-02-14
- [ ] P3-4b. 为 `architecture.md` 补写实际架构总览
- [ ] P3-4c. 审查其他文档，标记已过时的部分

**预估工时**：中（但不阻塞开发）

---

### P3-5. `/chat` 和 `/stream` 两个 Agent 对话端点并行存在

**问题描述**

- `POST /api/agent/chat` — 非流式，使用 `content_agent.run()`（旧兼容类），同步等待完整回复
- `POST /api/agent/stream` — SSE 流式，使用 `agent_graph.astream_events()`，逐 token 输出

前端实际只使用 `/stream`。`/chat` 端点仅在前端的 `handleSendMessage` 回调中被调用（WorkspacePage L174-198），但该回调似乎未被实际使用（AgentPanel 内部直接调 `/stream`）。

**子任务**

- [x] P3-5a. 确认 `/chat` 端点无前端调用方 ✅ 2026-02-13
- [x] P3-5b. `/chat` endpoint 标记 `deprecated=True` ✅ 2026-02-13
  - `/retry` 仍被前端 AgentPanel 使用，保留（均通过 content_agent，待 P3-1 一并清理）
- [x] P3-5c. WorkspacePage 的 `handleSendMessage` 已删除，AgentPanel 的 `onSendMessage` prop 已移除 ✅ 2026-02-13

**预估工时**：极小

---

### P3-6. 评估系统旧→新（Eval V2）全面置换 ✅

**问题描述**

类似 P0-1 的双轨问题，旧评估体系已全面删除：
- ~~旧评估：`models/evaluation.py` 的 `EvaluationTemplate` + `EvaluationReport`~~ **已删除**
- 新评估：`models/eval_run.py` + `eval_task.py` + `eval_trial.py` + `grader.py`
- ~~API 层：`api/evaluation.py`（旧）~~ **已删除**，仅保留 `api/eval.py`（Eval V2）

**子任务**

- [x] P3-6a. 确认旧评估体系的活跃使用范围 ✅ 2026-02-14
- [x] P3-6b. `evaluation.router` 标记 deprecated ✅ 2026-02-14
- [x] P3-6c. `SPECIAL_HANDLERS` 删除 10 个旧别名（7 个旧角色 + 3 个旧版别名） ✅ 2026-02-14
- [x] P3-6d. `api/eval.py` 删除 `_handle_legacy_eval()` + `eval_container` 分支 + `_extract_score_from_content()` ✅ 2026-02-14
- [x] P3-6e. `api/evaluation.py`（旧 API）从 main.py 摘除并删除文件 ✅ 2026-02-14
- [x] P3-6f. `core/tools/evaluator.py`（旧评估工具）从 `__init__.py` 摘除并删除文件 ✅ 2026-02-14
- [x] P3-6g. `core/models/evaluation.py`（旧模型）删除，同步清理：✅ 2026-02-14
  - `models/__init__.py` 移除导出
  - `models/project.py` 移除 `evaluation_reports` 关系
  - `api/projects.py` 移除导出/导入/删除中的 EvaluationReport 引用
  - `scripts/init_db.py` 移除旧评估模板种子数据
  - 测试文件更新（test_models, test_e2e_integration, test_prd_complete）
- [x] P3-6h. 前端清理：`content-block-card.tsx` 移除 7 个旧 eval 图标映射；`eval-field-editors.tsx` 移除 3 个旧别名路由 ✅ 2026-02-14
- [x] P3-6i. `api/__init__.py` 移除 eager import 避免 langgraph 链式加载 ✅ 2026-02-14

**预估工时**：✅ 全部完成

---

## 📋 执行建议

### 推荐执行顺序

```
第一批（基础设施）: ✅ 已完成 2026-02-13
  P0-2  Checkpointer 持久化  ✅
  P1-1  版本保存去重  ✅
  P1-5  advance_to_phase 去重  ✅
  P2-4  硬编码 URL 修复  ✅

第二批（前端去重）: ✅ 已完成 2026-02-13
  P1-2  SSE 读取工具函数  ✅
  P1-3  生成逻辑 Hook 提取  ✅

第三批（小型优化）: ✅ 已完成 2026-02-13
  P2-3  阶段名称统一 → phase_config.py  ✅
  P2-2  system prompt 缓存  ✅
  P3-5  /chat endpoint 废弃 + 死代码清理  ✅

第四批（核心架构统一）: ✅ 已完成 2026-02-14
  P0-1  ProjectField/ContentBlock 统一  ✅
        后端统一 + 前端主组件 + 辅助组件 + use_flexible_architecture 清理
        剩余：FieldCard 物理删除 → 随 P2-5a 一并完成
  P1-4  自动触发统一（checkAndAutoGenerate 已移除，统一 runAutoTriggerChain）  ✅

第五批（组件拆分 + 清理）: ✅ 已完成 2026-02-14
  P2-5  content-panel 拆分 + FieldCard 物理删除  ✅
        P2-5a: 删除死代码 ~1756 行
        P2-5b: 不需要（文件已 382 行，阶段视图已独立组件化）
        P2-5c: 已有（TemplateSelector 已是独立组件）
  P1-4c 自动触发竞态审计  ✅（_autoChainLocks 在 JS 单线程下安全）
  P3-3b 迁移脚本归档  ✅
  P3-6a/b 旧评估系统检查  ✅（仍有活跃使用，标记 deprecated）
  P3-4a agent_design.md 与代码对齐  ✅

第六批（清理）: ✅ 已完成 2026-02-14
  P3-1  ContentProductionAgent 清理  ✅
  P3-2  golden_context 全面清理  ✅ — 读写点切换到 ContentBlock 依赖链，DB 列保留兼容
  P3-3c init_db.py 补充 Grader 预置数据  ✅
  P3-2d agent_design.md golden_context 描述更新  ✅

第七批（旧评估系统清除）: ✅ 已完成 2026-02-14
  P3-6  旧评估系统全面置换为 Eval V2  ✅
        删除: evaluation.py(模型), evaluator.py(工具), evaluation.py(API)
        清理: SPECIAL_HANDLERS 10个旧别名, _handle_legacy_eval, 前端旧eval图标
        更新: main.py, __init__.py, projects.py, init_db.py, 3个测试文件

剩余低优先级（不阻塞开发）:
  P0-1a ProjectField 数据迁移验证（旧项目）
  P0-2e ChatMessage 元数据评估（已是纯展示用，暂不紧迫）
  P2-1  前端状态管理（Zustand / Context）— 影响大但风险高
  P3-3a Alembic 评估（当前无紧迫 schema 变更）
  P3-4b/c 其他文档更新
```

### 注意事项

1. **P0-1 是全系统最大的架构债务**，但不建议第一个做 —— 先完成 P0-2、P1-1~P1-3 的小型去重，减少 P0-1 的改动范围
2. **每完成一个 P 级任务后做一次全量功能测试**（创建项目 → 意图分析 → 调研 → 内容生成 → 评估的完整流程）
3. **数据库迁移需要备份**：特别是 P0-1 涉及 ProjectField 到 ContentBlock 的数据迁移
4. P0-1 建议拆分为多个 PR：先后端统一 → 再前端统一 → 最后清理旧代码

