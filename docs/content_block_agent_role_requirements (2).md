# 内容块导入 / Agent 引用 / Role 体系需求校正版（2026-03）

适用范围：`ContentBlock`、`Agent`、`AgentMode`、`Conversation`、项目导入导出、自动拆分草稿、项目级 locale

文档状态：

- 本文件替代旧版“单语前提下的一次性冻结实施规格”。
- 本文件基于当前仓库的真实实现、现有测试和日语版接入后的系统形态重新校正。
- 本文件明确区分三类内容：
  - `现状`：代码中已经存在并且应继续保留的能力
  - `目标`：本轮仍然要推进的事项
  - `暂不纳入本期`：旧文档里写过，但在当前项目阶段不应继续当作硬冻结目标推进的事项

---

## 1. 为什么要重写

这份需求最初提出时，系统还没有正式的日语运行时。现在情况已经变了：

1. 项目已经是明确的项目级双 locale 运行时：`zh-CN` 与 `ja-JP`
2. 后端已经存在 locale-aware 的 agent prompt、digest、eval 资产和模板 bootstrap
3. 前端 block 编辑面已经不只是“一个字段编辑器”，而是 `editor/card/special panel` 的组合
4. 旧文档把不少“目标态方案”写成了“当前冻结现实”，但代码里其实还没有落地

因此，这份文档不再以“旧方案必须整体照搬”为原则，而是改为：

- 先冻结已经被真实代码和测试证明成立的系统事实
- 再定义当前阶段仍然值得推进的需求
- 最后把不适合当前阶段的旧要求降级或延期

---

## 2. 一页结论

| 主题 | 旧文档结论 | 2026-03 校正后结论 |
| --- | --- | --- |
| locale 前提 | 默认中文单语 | 明确为项目级双 locale：`zh-CN` / `ja-JP`，不是泛化 i18n |
| Markdown 导入 | 继续做 | 保留为有效需求，但补充 locale 文案、导言节点命名、禁止导入时自动翻译 |
| Agent 无损引用 | 已冻结为 `manifest + read_block_full/read_blocks_full` | 目标仍成立，但要改成分阶段推进；先删除现有截断，再决定是否抽专用工具 |
| Agent / 用户编辑面对齐 | 已冻结为 `read_block_config/update_block_config` | 改为先以当前 `Block API + 已上线 UI` 作为唯一事实；旧工具名不再作为本期硬冻结项 |
| `guidance_input/guidance_output` | 已正式废弃 | 应改为“未纳入当前运行时正式字段面，但仍在模型/导入导出兼容链路中存在” |
| global role + project conversation | 当前唯一推荐方案 | 调整为“暂不切换到 global runtime role”；当前冻结为 `global templates + project runtime roles + project conversations` |
| conversation 生命周期 | 绑定在 role 全局化方案里一起做 | 保留为独立必修项，不再依赖 role 全局化 |

---

## 3. 当前代码基线

## 3.1 Locale 基线

现状冻结如下：

- 后端只支持项目级 `zh-CN` 与 `ja-JP`，定义在 `backend/core/localization.py`
- 前端项目 locale 也只归一化到这两个值，定义在 `frontend/lib/project-locale.ts`
- UI locale 的优先级已经存在正式逻辑，定义在 `frontend/lib/ui-locale.ts`
- Agent runtime、digest、eval 提示词、会话标题、引用包装文案、错误提示都已经进入 locale-aware 路径
- locale 不是“字符串透传后随缘显示”，而是已经进入：
  - `backend/core/orchestrator.py`
  - `backend/core/locale_text.py`
  - `backend/core/digest_service.py`
  - `backend/api/agent.py`
  - `backend/core/project_mode_bootstrap.py`
  - `backend/scripts/init_db.py`

因此本文件明确冻结：

- 当前系统是“项目级双 locale 运行时”
- 不是“默认中文，日语只是部分文案补丁”
- 也不是“已经支持任意语言的通用 i18n 平台”

## 3.2 ContentBlock / 编辑面基线

现状冻结如下：

- 块数据主事实仍然是 `ContentBlock`
- `backend/api/blocks.py` 已经暴露主要块字段：
  - `content`
  - `ai_prompt`
  - `constraints`
  - `pre_questions`
  - `pre_answers`
  - `depends_on`
  - `need_review`
  - `auto_generate`
  - `is_collapsed`
  - `model_override`
- 中栏不是单一编辑器，而是由 `frontend/components/content-panel.tsx` 按 `block_type` / `special_handler` 路由到不同界面
- 常规 field 进入 `frontend/components/content-block-editor.tsx`
- 有子节点的 group 在中栏以 `frontend/components/content-block-card.tsx` 列表呈现
- `intent`、`research`、`eval_*` 等特殊 handler 已有专门界面或空态
- 当前编辑面已经包含：
  - inline AI 选区改写
  - 版本历史
  - 保存前版本快照警告
  - 依赖与 pre-question gating
  - `model_override` 选择

补充事实：

- `frontend/lib/hooks/useBlockGeneration.ts` 已经抽出 card 与 editor 共享的生成前检查和 stop 逻辑
- `frontend/lib/block-ui-text.ts` 只做了部分共享文案，当前并未完成 block UI 全量文案抽象

## 3.3 Agent 工具与安全基线

现状冻结如下：

- `backend/core/agent_tools.py` 已经有明确安全边界
- 结构化块不允许被普通文本改写逻辑直接覆盖
- `rewrite_field` 只接受明确的“全文重写”意图
- 日文项目下的 rewrite intent 检测和错误文案也已经进入正式路径
- `SuggestionCard` 确认流已经存在，不是纸面设计
- `generate_field_content` 不允许覆盖已有非空内容

这意味着本轮调整文档时，不允许把这些已存在的保护能力误删或写丢。

## 3.4 Role / conversation 基线

现状冻结如下：

- 系统模板是全局的，运行时角色不是全局的
- 当前模型是：
  - `global templates`
  - `project runtime roles`
  - `project conversations`
- 项目运行时角色由 `backend/core/project_mode_bootstrap.py` 按 locale 从模板克隆
- `backend/api/modes.py` 仍然是项目级 role CRUD + template import
- `backend/api/agent.py` 的 `_resolve_project_mode()` 仍然只接受项目角色，不直接消费模板

因此旧文档中的“global runtime role 已经是唯一推荐路径”不再成立。

## 3.5 现有缺口

下面这些是当前代码里真实存在的缺口，必须写进文档：

1. `backend/api/agent.py` 仍然存在引用截断：
   - `ai_prompt[:1000]`
   - `content[:2000]`
   - `content[:3000]`
2. 当前仓库不存在以下已冻结实现：
   - `read_block_full`
   - `read_blocks_full`
   - `read_block_config`
   - `update_block_config`
   - `backend/core/agent_reference_context.py`
3. mention 列表当前仍以 `field` 为主，只额外拆出 `design_inner` 的 proposal 引用，不是“全部 group + field”
4. `constraints` 虽然在块 API 中存在，但当前前端并没有正式编辑入口
5. “保存成功但当前 UI 仍显示旧值”的问题只有部分缓解，没有彻底收口
6. conversation 相关接口仍有 project ownership 校验缺口
7. 项目复制 / 导出 / 导入 / 删除 对 conversation 的生命周期处理还没有形成完整闭环

---

## 4. 需求 1：批量导入 Markdown 为内容块

## 4.1 结论

该需求仍然有效，且基本不受 role 架构调整影响，应该继续保留为本轮正式需求。

但相较旧文档，需要补充 locale 与当前产品语义约束。

## 4.2 冻结后的产品语义

用户可以在项目内容树中批量导入 `.md/.markdown` 文件，直接落成当前项目的 `ContentBlock` 树。

保留两种模式：

- `heading_tree`
- `raw_file`

保留“每个文件先形成文件根节点”的决策，不改。

## 4.3 需要新增的校正

1. 导入功能必须是 locale-aware 的，但“locale-aware”只作用于系统文案，不作用于用户文件正文
2. 导入过程中不得自动翻译 Markdown 正文，不得根据项目 locale 擅自改写原文
3. 代码块、表格、列表、引用块、空行都要尽可能原样保留
4. `heading_tree` 中 heading 前的前言节点不能再固定写死为中文 `导言`

推荐冻结：

- `zh-CN` 项目默认名称：`导言`
- `ja-JP` 项目默认名称：`前書き`

## 4.4 保留的解析规则

`heading_tree` 继续采用以下规则：

1. 每个文件先创建一个文件根节点
2. 文件根节点默认是 `group`
3. 文件根节点名称默认取文件名去扩展名
4. heading 层级映射为树
5. 有子 heading 的节点为 `group`
6. 无子 heading 的节点为 `field`
7. heading 下直到下一个同级或更高层 heading 之前的正文，写入该节点 `content`
8. 若文件没有任何 heading，则自动回退到 `raw_file`

`raw_file` 继续采用以下规则：

1. 每个文件创建一个 `field`
2. 名称取文件名去扩展名
3. `content` 为完整 Markdown 原文

## 4.5 API 与实现要求

保留原有方向，但增加以下要求：

- 后端接口仍建议为 `POST /api/projects/{project_id}/import-markdown-files`
- `warnings`、`message` 等系统响应文案应根据项目 locale 生成
- 错误信息里必须原样带上出错文件的 `name` / `path`
- 任一文件解析失败时，默认整个请求失败并回滚
- `parent_id` 仍然只允许挂到 `group`

## 4.6 本期状态

当前仓库里尚未看到这条正式导入链路落地，因此它仍然是 `目标`，不是 `现状`。

---

## 5. 需求 2：Agent 引用内容块必须无损访问全部内容

## 5.1 结论

该需求仍然成立，而且优先级仍然高。

但旧文档把“未来可能的正式协议”写成了“当前已经冻结的唯一实现”，这需要纠正。

## 5.2 当前应冻结的最低要求

本期必须先冻结以下底线：

1. 传给 Agent 的引用内容不得再做静默字符截断
2. 传给 Agent 的引用包装文案可以本地化，但被引用的块内容与配置不得被改写
3. 即使预算不够，也不能用“偷偷截断后继续跑”来兜底
4. 预算不足时，必须走显式降级路径，而不是继续 preview 注入

## 5.3 当前必须先修掉的真实问题

当前至少存在三处硬编码截断，必须先清掉：

- `_build_ref_context()` 中的 `ai_prompt[:1000]`
- `request.references` 组装用户消息时的 `content[:2000]`
- `selection_context` 组装时的 `content[:3000]`

在这些截断还存在时，文档里不应该写“已实现无损访问”。

## 5.4 对旧协议的校正

旧文档中的以下内容，不再作为本期硬冻结实现：

- `ResolvedReference`
- `backend/core/agent_reference_context.py`
- `read_block_full`
- `read_blocks_full`
- “一定要先上 manifest 模式再让 Agent 读工具”

校正后的要求是：

1. 先把当前真实截断移除
2. 先收敛“引用时至少要暴露哪些字段”
3. 再根据实际 token 压力，决定是：
   - 扩展现有 `content_block_reference` / `architecture_reader`
   - 还是新增专门引用读取工具

也就是说：

- `manifest + tool` 仍然可以是未来候选方向
- 但不再是本期唯一冻结的工具命名与文件结构

## 5.5 当前应统一的引用暴露面

普通 `@引用` 至少应让 Agent 拿到：

- `id`
- `reference_label`
- `path`
- `content`
- `ai_prompt`
- `depends_on`
- `pre_questions`
- `pre_answers`
- `need_review`
- `auto_generate`
- `model_override`
- `status`

如果后续进入预算降级模式，也必须保证这组信息仍可被完整读回。

## 5.6 mention 键策略校正

旧文档要求“前端默认插入 `@id:<uuid>`”。

这一点改为：

- 作为可选的未来增强保留
- 不再当作本期硬冻结项

原因：

- 当前前端 mention 仍然是 name-based
- 当前项目更紧急的问题是“引用被截断”，不是“mention 文本形式尚未升级”

## 5.7 本期验收

本期至少满足以下条件才算完成：

1. 代码库中不再存在对 Agent 引用正文的固定字符截断
2. 引用一个超长块后，Agent 能回答块后半段信息
3. 同时引用多个块时，不会因为应用层拼接逻辑丢掉后面的块
4. 选区引用不再只传裁剪后的块正文
5. 若未来引入预算降级，必须是显式协议而不是静默截断

---

## 6. 需求 3：Agent 与用户编辑面对齐

## 6.1 结论

该需求继续保留，但“对齐”的对象要从“数据库里所有字段”改成“当前上线产品中，用户真实能改或能观察的块运行时表面”。

## 6.2 当前正式运行时字段面

本期先冻结为两层：

### A. 当前用户直接可编辑的字段

- `name`
- `content`
- `ai_prompt`
- `depends_on`
- `pre_questions`
- `pre_answers`
- `need_review`
- `auto_generate`
- `model_override`

### B. 当前用户可观察但不是主要手工编辑入口的字段

- `status`
- `block_type`
- `special_handler`
- 版本历史与快照警告结果

### C. 当前不应写进“用户运行时正式字段面”的字段

- `constraints`
- `guidance_input`
- `guidance_output`
- `parent_id`
- `order_index`
- `is_collapsed`

说明：

1. `constraints` 在块 API 中存在，但当前前端没有正式编辑面，因此现在不能写成“用户能改、Agent 必须完全对齐”
2. `parent_id` / `order_index` 仍然属于结构操作，不属于普通块配置
3. `guidance_input / guidance_output` 目前仍在模型和项目导入导出链路中存在，因此不能写成“已彻底废弃完毕”
4. 对它们的准确表述应改为：
   - 仍有兼容存量
   - 但不纳入当前运行时 UI / Agent 正式字段面

## 6.3 工具策略校正

旧文档把 `read_block_config` 与 `update_block_config` 写成了本期新增必做。

这一点改为：

- 本期不冻结这两个工具名
- 本期先冻结“字段语义必须与 `backend/api/blocks.py` 一致”
- 如果后续确实需要新增 Agent 侧配置读写工具：
  - 字段名必须与 `BlockResponse` / `BlockUpdate` 完全一致
  - 不允许再出现 UI、API、Agent 三套不同命名

换句话说：

- 先冻结语义
- 不先冻结工具名

## 6.4 现有安全边界必须保留

以下能力已经真实存在，不能因为“追求 Agent 可编辑”而被弱化：

1. 结构化块防止被普通文本覆盖
2. `rewrite_field` 只接受明确全文重写意图
3. 日文项目下的 rewrite guard 文案必须保持日文
4. `SuggestionCard` 确认流必须保留
5. `generate_field_content` 不得覆盖已有非空内容

## 6.5 当前编辑面的新增现实也必须写进需求

旧文档缺失了以下已经上线的用户能力：

- inline AI 选区改写
- 版本历史
- 保存前创建版本快照
- editor 与 card 共用的生成前依赖 / pre-question 校验

因此“Agent 与用户面对齐”不能只理解成“能改几个字段”，还要理解成：

- 不得绕过现有安全确认机制
- 不得破坏版本可回滚能力
- 不得在日文项目里回退成中文控制文案

## 6.6 mention 范围校正

旧文档要求 mention 列表覆盖所有可引用的 `group` 与 `field`。

当前校正为：

- 现状仍是以 `field` 为主
- 额外兼容 `design_inner` 中拆出的 proposal
- “group 也进入 mention”可以保留为后续增强，但不作为本期硬冻结项

## 6.7 必补 P0：保存成功但 UI 仍显示旧值

这一条仍然必须保留为 P0，但要改成“部分修复，尚未收口”的表述。

当前已存在的缓解：

- `content-block-editor` 在挂载 / 切换 block 时会主动拉一次最新块
- `content-block-editor` 会在块处于 `in_progress` 且当前组件未流式生成时轮询
- `content-block-card` 对后台生成态也有轮询

但以下问题仍未彻底收口：

1. `frontend/components/progress-panel.tsx` 仍用有损签名决定是否向父层同步 blocks
2. 该签名仍然无法覆盖正文等长改写、prompt 非空到非空替换、依赖集合变化但数量不变、`model_override` 变化等场景
3. `frontend/app/workspace/page.tsx` 中 `selectedBlock` 的同步仍然依赖上游 `allBlocks` 是否被成功替换
4. `frontend/components/content-panel.tsx` 仍未把 editor 与 `selectedBlock.id` 显式绑定
5. editor / card 的保存成功路径仍主要依赖 `onUpdate()` 刷新，而不是优先消费接口返回的新块数据做本地权威回写

因此本期必须继续推进以下收口要求：

1. `ProgressPanel` 不得再用有损签名充当“是否真的变化”的唯一判断
2. 成功拉回最新 blocks 后，应默认同步到父层，或者至少基于正式 `updated_at/revision` 决定
3. 保存接口返回最新块数据时，应优先本地回写，而不是只等下一轮刷新
4. `ContentBlockEditor` 建议显式使用 `key={selectedBlock.id}`
5. 回归测试必须覆盖：
   - 正文改了但长度不变
   - `ai_prompt` 非空到非空
   - 依赖集合变化但数量不变
   - 仅改 `model_override`
   - 仅改 `pre_questions` / `pre_answers`

## 6.8 本期验收

本期至少满足以下条件才算完成：

1. Agent 能读到当前用户可见的正式字段面
2. Agent 修改结果与 UI 观察结果一致
3. 保存后当前 UI 必须立即显示新值
4. 已存在的安全保护与 SuggestionCard 确认流不能被破坏
5. 日文项目下相关错误文案、状态文案、空态文案不能回退成中文

---

## 7. 需求 4：Role 与 conversation 体系

## 7.1 本期校正结论

旧文档中的“global role + project conversation”需要拆开处理：

- `conversation 是项目资产`：保留为本期正式要求
- `runtime role 立即改为 global`：调整为 `暂不纳入本期`

## 7.2 本期冻结模型

当前阶段正式冻结为：

- 全局存在的是 `template`
- 运行时存在的是 `project role`
- 对话与消息是 `project conversation` / `project message`

也就是：

- `global templates + project runtime roles + project conversations`

## 7.3 为什么不在本期切 global runtime role

原因不是“不想做”，而是当前系统事实已经变化：

1. 运行时角色 bootstrap 已经和 locale 绑定
2. 模板 reseed、locale fallback、日文模板优先已经有测试约束
3. 前端 `AgentModeManager` 与 `AgentPanel` 仍然以项目 role 为运行时对象
4. 当前真正的安全缺口在 conversation ownership 与生命周期，不在 role 是否全局

如果在这一阶段强行推进 global runtime role，容易出现：

- locale-specific 模板与 runtime 编辑语义重新打架
- 项目级 prompt 微调能力丢失
- 迁移期兼容逻辑远大于当前收益

## 7.4 本期保留的正式要求

虽然不切 global runtime role，但以下要求仍然必须保留：

1. `Conversation` 与 `ChatMessage` 仍然是项目资产
2. conversation 相关接口必须补 project ownership 校验
3. 项目删除时 conversation / message 必须同步删除
4. 项目复制、导出、导入是否保留 conversations，必须形成明确一致规则，不能继续隐式漂移

推荐方向：

- 如果决定复制 / 导出 / 导入 conversations，就必须连同 `conversation_id` 重映射与消息一起完整处理
- 如果决定暂不支持，也必须在 API 与导入导出文档里显式声明，不允许现在这种“部分复制消息、但 conversation 语义不闭环”的状态继续存在

## 7.5 从本期硬冻结项中移除的内容

以下内容不再作为本期冻结要求：

- `scope = global | legacy_project`
- 把 `/api/modes` 改造成全局 runtime role CRUD
- 新建 role 时完全移除 `project_id`
- 停止项目级 role 创建
- 取消 template import / bootstrap 路径

这些内容如果未来还要推进，必须另开一份“locale-aware global role 设计文档”，不能继续混在这份文档里。

## 7.6 本期验收

本期至少满足以下条件才算完成：

1. 项目运行时 role 仍然可正常 bootstrap 与运行
2. 日文项目优先拿到日文模板链路不被破坏
3. `update_conversation()`、`delete_conversation()`、`get_conversation_messages()` 都补齐 project ownership 校验
4. conversation / message 的项目生命周期规则明确且实现一致

---

## 8. 现有测试与守护线

下列测试和守护线已经代表系统真实意图，本文件要求继续保留：

- `backend/tests/test_locale_asset_guard.py`
- `backend/tests/test_tool_safety.py`
- `backend/tests/test_project_mode_bootstrap.py`
- `backend/tests/test_agent_runtime_locale_guard.py`
- `backend/tests/test_agent_project_modes_api.py`
- `backend/tests/test_eval_runtime_locale_guard.py`
- `frontend/e2e/japanese-locale-parity.spec.ts`
- `frontend/e2e/agent-role-panel.spec.ts`

它们共同冻结了以下现实：

1. 日文资产不能混入中文控制文案
2. locale-specific template 与 runtime bootstrap 是正式行为
3. tool safety 和 SuggestionCard 不是可删的临时实现
4. 当前前端 role 管理仍然是项目级运行时角色模型

---

## 9. 非目标与明确不做

为了避免继续发散，本期明确不做：

1. 不把系统表述成“任意语言通用 i18n 平台”
2. 不在本期切换到 global runtime role
3. 不在前端 UI 尚未存在前，把 `constraints` 强行写成“用户正式可编辑字段”
4. 不把 `guidance_input / guidance_output` 误写成“已经彻底删除”
5. 不在 Markdown 导入时自动翻译或改写正文
6. 不在本期强推 `@id:<uuid>` mention 作为唯一必须方案
7. 不在没有真实 token 压力验证前，先把引用协议工具名完全冻结

---

## 10. 分阶段实施顺序

## P0：先把当前事实收口

1. 明确文档与实现都以 `zh-CN / ja-JP` 双 locale 为基线
2. 删除 Agent 引用链路中的硬编码截断
3. 收口“保存成功但 UI 显示旧值”的状态一致性问题
4. 修复 conversation 接口的 project ownership 校验

## P1：补正式能力

1. 落地 Markdown 导入 API 与前端入口
2. 收敛引用时对外暴露的正式字段面
3. 让 Agent 与当前用户编辑面在语义上对齐
4. 收口 conversation / message 的项目生命周期

## P2：只在 P0 / P1 稳定后再讨论

1. 是否默认插入 `@id:<uuid>`
2. 是否让 `group` 进入 mention 列表
3. 是否需要 locale-aware 的 global runtime role 方案

---

## 11. 需要改的文件清单

## 11.1 Locale 基线与守护

- `backend/core/localization.py`
- `backend/core/locale_text.py`
- `backend/core/orchestrator.py`
- `backend/core/digest_service.py`
- `frontend/lib/project-locale.ts`
- `frontend/lib/ui-locale.ts`
- `backend/tests/test_locale_asset_guard.py`
- `frontend/e2e/japanese-locale-parity.spec.ts`

## 11.2 Markdown 导入

- `frontend/components/block-tree.tsx`
- 新增 `frontend/components/project-markdown-import-modal.tsx`
- `frontend/lib/api.ts`
- `backend/api/projects.py`
- 新增 `backend/core/content_markdown_import_service.py`

## 11.3 引用无损

- `backend/api/agent.py`
- `backend/core/content_block_reference.py`
- `backend/core/agent_tools.py`
- `backend/core/tools/architecture_reader.py`
- `frontend/components/agent-panel.tsx`
- `frontend/components/content-block-editor.tsx`
- `frontend/lib/api.ts`

## 11.4 编辑面对齐与状态一致性

- `backend/api/blocks.py`
- `frontend/components/progress-panel.tsx`
- `frontend/app/workspace/page.tsx`
- `frontend/components/content-panel.tsx`
- `frontend/components/content-block-editor.tsx`
- `frontend/components/content-block-card.tsx`
- `frontend/lib/hooks/useBlockGeneration.ts`
- `frontend/lib/block-ui-text.ts`
- `frontend/lib/api.ts`

## 11.5 Role / conversation 安全与生命周期

- `backend/api/modes.py`
- `backend/core/project_mode_bootstrap.py`
- `backend/api/agent.py`
- `backend/api/projects.py`
- `backend/scripts/init_db.py`
- `frontend/components/agent-mode-manager.tsx`
- `frontend/components/agent-panel.tsx`
- `frontend/lib/api.ts`

---

## 12. 最终验收清单

以下全部满足，才允许认为这份校正版需求已经被正确执行。

## 12.1 Locale 基线

- `zh-CN` 与 `ja-JP` 两个项目 locale 的运行时链路都可用
- 日文项目中的系统控制文案不混入中文残留
- 新增功能不允许重新回到“默认中文单语”的隐含前提

## 12.2 Markdown 导入

- 可以批量导入多个 Markdown 文件
- `heading_tree` 与 `raw_file` 都可用
- 文件边界被保留
- 导言节点名称按项目 locale 生成
- 正文内容不被自动翻译或改写

## 12.3 引用无损

- 代码库中不存在对 Agent 引用正文的固定字符截断
- 引用一个大块后，Agent 能回答后半段信息
- 同时引用多个块时，不会在应用层静默丢内容
- 若有预算降级，也必须是显式协议而不是截断

## 12.4 编辑面对齐

- Agent 能读到当前用户正式可见的块运行时字段面
- Agent 修改结果与 UI 观察结果一致
- 保存后 UI 立即显示新值，不出现“数据库已更新但当前面板还显示旧值”的假未保存现象
- 结构化块保护、rewrite guard、SuggestionCard、版本回滚能力仍然存在

## 12.5 Role / conversation

- 项目运行时 role bootstrap 不被破坏
- conversation 与 message 仍然按项目隔离
- conversation 相关接口补齐 project ownership 校验
- 项目生命周期对 conversation / message 的处理规则明确且一致

---

## 13. 三条红线

1. 不允许再把“目标态方案”写成“当前已实现现实”
2. 不允许再做任何静默截断
3. 不允许让 locale、UI、API、Agent 四侧对同一概念出现不同语义

---

## 14. 最终判断

在当前项目状态下，这份需求文档的正确落点已经不是：

1. 继续沿着单语时期的四个目标原封不动推进

而是：

1. 先以双 locale 真实系统形态为前提重写需求
2. 保留 Markdown 导入与无损引用这两个仍然正确的核心目标
3. 把 Agent / 用户对齐收敛到当前真实产品表面，而不是数据库全字段
4. 把 conversation 安全与生命周期从“global role 改造”中拆出来独立完成

只有这样，后续实现才不会一边补功能、一边破坏已经成立的日语运行时与现有安全边界。
