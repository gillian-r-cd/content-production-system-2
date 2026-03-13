<!--
功能: 分析“上游内容块变更后，下游依赖块自动覆盖重生成”需求的现状、实现条件、关联代码与 locale 覆盖点
主要章节: 需求结论、当前阻塞点、改造所需条件、密切关联代码、中文/日文 locale 约束、测试建议
数据结构: 以 ContentBlock 依赖链、项目级调度器、前端触发入口、locale 文本入口为主的分析清单
-->

# 内容块依赖更新后自动重生成需求分析

## 结论先行

这个需求可以改，而且现有代码里“覆盖重生成”的底层能力其实已经存在，真正拦住需求的不是生成函数本身，而是这两层逻辑：

1. 上游内容块改动后，系统没有把这件事当成“下游需要自动重跑”的事件。
2. 项目级自动调度器只会挑“空内容 + `pending/failed`”的块，不会把“已有内容的下游块”重新放进自动生成队列。

所以，当前行为更像是“提示你下游可能过期，请手动重生成或建版本”，而不是“依赖一变就自动覆盖重跑”。

## 需求定义

目标场景：

- 有 3 个相互依赖的内容块，记为 `A -> B -> C`，或 `A -> B`、`A -> C`。
- `B`、`C` 已经配置为：
  - `auto_generate = true`
  - `need_review = false`
- 当 `A` 的内容被手动编辑、AI 重新生成、确认完成，或者通过其他正式入口发生有效更新后：
  - `B`、`C` 不再只是收到“可能过期”的提醒；
  - 而是允许覆盖现有内容，直接自动重生成；
  - 且链式传播要继续生效，也就是 `B` 完成后还能继续触发 `C`。

本分析默认主链路是新架构的 `ContentBlock`，不是旧的 `ProjectField`。

## 当前为什么做不到

### 1. 上游手动保存内容时，没有触发自动链

当前手动保存内容的入口主要在：

- `frontend/components/content-block-editor.tsx`
- `frontend/components/content-block-card.tsx`

这两个组件的 `handleSaveContent()` 在保存后只做了两件事：

- 更新当前块内容
- 如果后端返回了 `version_warning`，就弹出“上游内容变更提醒”

但它们**不会**像“保存 pre_questions 回答”“确认内容块”“AI 生成完成”那样调用 `runAutoTriggerChain()`。

也就是说，用户手动改了上游块以后，前端根本没有发起“请检查有哪些下游块该自动跑”的动作。

### 2. 即使触发了自动链，已有内容的下游块也不会入队

核心阻塞在：

- `backend/core/block_generation_service.py`
- 具体函数：`list_ready_block_ids()`

当前 ready 判定有两个关键门槛：

- `status` 只能是 `pending` 或 `failed`
- 只要 `block.content` 非空，就直接跳过

这就意味着：

- 下游块即使 `auto_generate = true`
- 即使所有依赖已经完成
- 即使 `need_review = false`
- 只要它已经有内容并且状态通常是 `completed`

它就不会再被项目级自动调度器选中。

### 3. 当前产品语义是“警告”，不是“失效并重跑”

核心入口在：

- `backend/api/blocks.py`
- 具体函数：`update_block()`

上游内容变化后，后端会扫描哪些下游块依赖了当前块，如果这些下游块已有内容，就返回：

- `version_warning`
- `affected_blocks`

也就是说，当前系统设计是：

- 告诉用户“这些下游块可能需要重新生成或建版本”
- 但不会把这些下游块标记成“待重跑”
- 也不会后端直接调度自动覆盖重生

### 4. 前端 UI 也是围绕“提醒 + 建版本”设计的

核心位置：

- `frontend/components/content-block-editor.tsx`
- 组件：`VersionWarningDialog`

现在的弹窗重点是：

- 展示上游变更提醒
- 列出受影响的下游块
- 允许创建一个“变更前快照”

这与“符合条件时直接自动覆盖重生成”是两套产品语义。

### 5. 但底层生成函数本身已经支持覆盖现有内容

这点很关键。

核心位置：

- `backend/core/block_generation_service.py`
- 具体函数：`generate_block_content_sync()`

以及：

- `backend/api/blocks.py`
- 具体函数：`generate_block_content_stream()`

这两条路径在生成前都会：

- 先保存旧版本，来源是 `ai_regenerate`
- 然后覆盖写回 `block.content`

所以这次需求**不是**“生成器不会覆盖”，而是“调度器从来没有把已有下游块重新送进生成器”。

## 改掉这个逻辑所需要的条件

## 1. 明确允许自动覆盖的下游块范围

如果严格按这次需求，最小条件应当是：

- `block_type == "field"`
- `auto_generate == true`
- `need_review == false`
- 未被软删除
- 当前不处于真正执行中的状态
- 所有依赖块都已经 `completed`
- 所有必答 `pre_questions` 都已回答

这里的关键点是：

- `auto_generate` 决定“依赖变更后要不要自动跑”
- `need_review = false` 决定“自动跑完后是否可以直接视为完成并继续向下游传播”

如果下游块是 `need_review = true`，自动重跑后通常会停在 `in_progress`，后续链会被它卡住。这不符合本次需求描述。

## 2. 明确哪些事件算“依赖发生有效更新”

至少要覆盖这些入口：

- 手动保存上游内容
- AI 手动重新生成上游内容
- `need_review = true` 的上游块被用户确认完成
- 版本回滚导致上游内容变化

如果只覆盖“某一个前端按钮”，后续从别的 API、Agent、导入、回滚进入时还会漏掉。

因此更稳妥的做法是：

- 在后端把“上游内容发生有效变化”统一收敛成一个事件
- 再由这个事件去驱动下游自动重跑判断

## 3. 需要显式区分“首次生成”与“依赖变更重生成”

当前 `list_ready_block_ids()` 的 ready 条件，本质上只适用于“空块首次生成”。

要支持这次需求，必须新增一种语义，至少二选一：

- 方案 A：调度时允许传入“强制重跑候选块列表”，这些块即使已有内容也可入队
- 方案 B：给下游块增加持久化的 `needs_regeneration` / `stale` 标记，再由调度器识别

不建议用“先把下游内容清空，再复用空块逻辑”的方式硬绕过去，因为这会带来几个问题：

- 页面上会短暂出现空白内容
- 失败后容易留下不一致状态
- 会把“首次生成”和“覆盖重生成”混成一套语义

## 4. 调度器要支持“已有内容但允许重跑”的 ready 判定

当前项目级调度器已经有多轮扫描能力：

- `backend/core/project_run_service.py`
- 具体函数：`run_project_blocks()`

这个函数本身可以复用，因为它已经支持：

- 多轮扫描
- 上一轮完成后继续拉起新解锁的块
- 并发上限控制

真正需要改的是它底层调用的 ready 判定：

- `backend/core/block_generation_service.py:list_ready_block_ids()`

这里要让调度器有能力识别：

- 这是“首次生成候选”
- 还是“依赖变更后的自动重生成候选”

## 5. 需要保留现有版本安全措施

这一点现有实现已经有基础能力，不应破坏：

- 自动覆盖前保存旧内容版本
- 版本来源标记为 `ai_regenerate`

因此这次改造最好沿用现有：

- `backend/core/block_generation_service.py:generate_block_content_sync()`
- `backend/api/blocks.py:generate_block_content_stream()`

换句话说，这次改造重点应放在“谁能被送去重跑”，而不是改写“重跑时如何覆盖”。

## 6. 需要统一 special handler 的适用范围

这一点要提前确认，否则有潜在风险。

当前流式生成入口 `generate_block_content_stream()` 对 `eval_*` 会特殊转发到 `api/eval.py`，但项目级调度器调用的是 `generate_block_content_sync()`，它本身没有同样的特殊分流。

所以要先明确：

- 这次“依赖变更后自动覆盖重生”是否只作用于普通文本类 `field`
- 还是也要覆盖 `special_handler` 内容块

如果要覆盖 `special_handler`，就需要先保证项目级同步生成链路与流式手动生成链路在行为上对齐。

## 7. 最好把触发权重心放回后端，而不是继续依赖前端补丁

如果只做前端修补，例如：

- 在 `handleSaveContent()` 后调用一次 `runAutoTriggerChain()`

那只能解决“当前这个页面上的手动保存”。

但未来这些入口仍然会漏：

- API 直接调用
- Agent 工具更新
- 版本回滚
- 导入/应用模板后的补写

因此更稳的方案是：

- 后端负责识别上游内容变化
- 后端负责决定哪些下游块进入“自动重生成候选”
- 前端只负责展示结果和刷新树

## 哪些代码和这个功能密切关联

## 1. 后端主链路

| 模块 | 作用 | 与本需求的关系 |
| --- | --- | --- |
| `backend/core/models/content_block.py` | 定义 `ContentBlock` 的 `need_review`、`auto_generate`、`depends_on`、`status` | 需求的核心数据语义都在这里 |
| `backend/api/blocks.py` | 内容块 CRUD、确认、生成、项目级运行 API | 上游内容更新、下游警告、手动生成、项目级调度入口都在这里 |
| `backend/core/block_generation_service.py` | 统一依赖解析、ready 判定、同步生成 | 当前是否允许“已有内容块重新入队”由这里决定 |
| `backend/core/project_run_service.py` | 项目级多轮调度器 | 已具备链式拉起能力，可复用 |

## 2. 当前直接拦住需求的关键函数

### `backend/api/blocks.py:update_block()`

现状：

- 上游内容变化后，只返回 `version_warning` 和 `affected_blocks`
- 没有把下游块转为“待自动重跑”

这是当前“只提醒，不自动覆盖”的核心后端入口。

### `backend/core/block_generation_service.py:list_ready_block_ids()`

现状：

- 只挑 `pending/failed`
- 只挑空内容块

这是当前“下游已有内容就永远不会被自动重跑”的核心门槛。

### `frontend/components/content-block-editor.tsx:handleSaveContent()`

现状：

- 保存后只处理 warning
- 不触发 `runAutoTriggerChain()`

这是当前“手动编辑上游内容后根本没启动自动链”的直接前端入口。

### `frontend/components/content-block-card.tsx:handleSaveContent()`

现状同上，是另一个保存入口。

## 3. 现有可复用能力

| 模块 | 可复用点 |
| --- | --- |
| `backend/core/project_run_service.py:run_project_blocks()` | 已支持多轮扫描和链式传播 |
| `backend/core/block_generation_service.py:generate_block_content_sync()` | 已支持保存旧版本并覆盖写入新内容 |
| `backend/api/blocks.py:generate_block_content_stream()` | 手动流式重生成已有版本保护 |
| `backend/core/template_schema.py` | 已支持模板中的 `need_review` / `auto_generate` / 依赖关系传播 |
| `backend/api/projects.py` | 项目复制、导入时已保留 `auto_generate` 与 `locale` |

## 4. 前端配置与触发入口

| 模块 | 作用 |
| --- | --- |
| `frontend/lib/api.ts` | 定义 `ContentBlock` 类型、`blockAPI.runProject()`、`runAutoTriggerChain()` |
| `frontend/components/content-block-editor.tsx` | 大编辑器里的保存、确认、warning 弹窗、开关切换 |
| `frontend/components/content-block-card.tsx` | 卡片式编辑器里的保存和开关切换 |
| `frontend/lib/hooks/useBlockGeneration.ts` | 手动生成完成后会触发自动链 |
| `frontend/components/progress-panel.tsx` | 初次加载内容块后会触发自动链 |
| `frontend/components/settings/template-tree-editor.tsx` | 模板层 `need_review` / `auto_generate` 开关 UI |

## 5. 模板和结构来源

如果希望这个功能在中文项目和日文项目里都能稳定复用，就不能只盯着运行时，还要确认配置来源链是完整的。当前相关点包括：

- `backend/core/template_schema.py`
- `backend/core/models/phase_template.py`
- `backend/core/models/field_template.py`
- `backend/core/project_structure_apply_service.py`
- `backend/core/content_tree_export_service.py`
- `backend/api/projects.py`

这些位置决定了：

- 模板树里的 `auto_generate`
- 模板树里的 `need_review`
- 模板依赖关系
- 项目复制/导入后的保真

是否能正确落到最终项目的 `ContentBlock` 上。

## 中文和日文两个项目的语种逻辑必须覆盖哪些点

## 1. 生成链路本身已经基本接入项目 locale

现有较好的部分：

- `backend/core/localization.py`
  - `normalize_locale()`
  - `SUPPORTED_PROJECT_LOCALES = ["zh-CN", "ja-JP"]`
- `backend/core/block_generation_service.py`
  - 生成 prompt 时读取 `project.locale`
- `backend/core/locale_text.py`
  - 已有 `zh-CN` / `ja-JP` 的生成提示、依赖未完成提示、pre-question 提示、运行时 surface 文案
- `frontend/lib/project-locale.ts`
  - 前端项目 locale 归一化
- 多个前端组件通过 `useUiIsJa(projectLocale)` 做中日文 UI 切换

这意味着：

- 只要自动重生成最终仍然走正式生成服务，LLM 控制层文本本身是有机会保持中日文分开的。

## 2. 当前这条链路里已经存在 locale 缺口

最明显的缺口是：

- `backend/api/blocks.py:update_block()`

这里返回的 `version_warning` 是中文硬编码：

- 中文项目没问题
- 日文项目也会收到中文正文

同样的问题在旧路径里也存在：

- `backend/api/fields.py`

所以如果这次改造仍然保留“受影响块提示”“自动重生成原因”“部分块未满足条件”等文案，必须做这些事：

- 文案进入 `backend/core/locale_text.py`
- 后端按 `project.locale` 返回
- 前端弹窗和通知继续按 `projectLocale` 渲染外层 UI

不能继续靠散落的中文字符串。

## 3. 本次改造新增的任何文案，都应该走统一 locale 文本层

尤其是以下几类文本：

- “由于依赖已更新，系统已自动重新生成”
- “该下游块未开启自动生成，因此仅标记为受影响”
- “该下游块需要人工确认，因此未自动覆盖”
- “以下下游块因必答 pre_questions 未完成而未触发”

这些文本如果需要返回给前端或进入 LLM 控制层，都应该放进：

- `backend/core/locale_text.py`

而不是写死在 API 处理函数里。

## 4. 日文链路要特别注意的点

根据仓库当前 locale 约束，`ja-JP` 需要避免中文控制层提示回流。所以这次改造至少要保证：

- 新增 runtime text 同时补 `zh-CN` / `ja-JP`
- 新增测试覆盖 `ja-JP`
- 如改动了 runtime 文本，静态残留检查不要被破坏

## 建议的实现策略

## 最小可行方案

适合先把需求跑通，不先加新表字段。

做法：

1. 上游内容变化时，在后端计算直接受影响的下游块。
2. 只挑满足本次条件的下游块：
   - `auto_generate = true`
   - `need_review = false`
   - 依赖全完成
   - 必答 pre_questions 已完成
3. 调度器新增“允许已有内容块重跑”的入口参数或运行模式。
4. 调用现有 `run_project_blocks()` 做多轮链式拉起。

优点：

- 不一定需要数据库 schema 变更
- 能最大化复用现有调度器和生成器

限制：

- 要 carefully 设计“本次允许重跑的候选块列表”，避免把所有已完成块都扫进去

## 稳妥方案

适合后续把语义做得更清晰。

做法：

- 给下游块增加明确的失效态，例如 `needs_regeneration` 或等价标记
- 上游变化时由后端写入该标记
- 调度器只消费被标记且满足条件的块

优点：

- 行为更可解释
- 对回滚、导入、Agent 更新、批处理等入口更稳

代价：

- 需要更多状态管理和测试

## 建议补的测试

## 1. 后端核心测试

优先补在这些文件：

- `backend/tests/test_project_run_service.py`
- `backend/tests/test_block_generation_service.py`

建议覆盖：

- 上游块内容变化后，下游块即使已有内容，只要符合条件也会被重新入队
- 多轮链式传播仍然成立
- `auto_generate = true` 但 `need_review = true` 的块不会满足本次“直接自动覆盖到底”的产品预期
- 依赖未完成或必答 pre_questions 未回答时，不会误触发
- `ja-JP` 项目在自动重生成时仍使用日文 `HumanMessage` 和日文 runtime text

## 2. API / locale 测试

建议新增或补强：

- `backend/api/blocks.py:update_block()` 在 `zh-CN` / `ja-JP` 下返回的 warning / result 文案
- 新增的“自动重生成结果”文案必须同时覆盖中日文

## 3. 前端测试

建议覆盖：

- 手动保存上游内容后的触发行为
- 受影响下游块的 UI 刷新
- 日文项目下 warning / notification / 按钮文案不回落成中文

如果做端到端验证，建议在：

- `frontend/e2e/japanese-locale-parity.spec.ts`

基础上扩一条“依赖更新后自动覆盖重生成”的用例，至少覆盖一次 `zh-CN` 和一次 `ja-JP`。

## 最后判断

这个需求的本质不是“让生成器支持覆盖”，因为它已经支持。

真正要改的是三件事：

1. 把“上游内容变化”从 warning 语义升级为可驱动下游重跑的事件。
2. 让 ready 判定支持“已有内容但因依赖更新而允许自动重生成”的块。
3. 把 warning / result / notification 全部纳入 `zh-CN` 与 `ja-JP` 的统一 locale 逻辑。

如果只修前端按钮，不修 ready 判定，这个需求不会真正成立。
如果只修 ready 判定，不修 locale 文案，日文项目会继续混入中文提示。
