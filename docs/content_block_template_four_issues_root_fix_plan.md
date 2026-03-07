# 内容块模板四项问题根因改造方案（待确认后实施）

## 目标与约束

- 目标：一次性、系统性解决以下四个问题，并保持现有“树形 ContentBlock 架构”一致性。
  - 新项目中可直接添加`组`或`内容块`，并可直接从`内容块模板`引用（非“先组后块”）。
  - 项目中的内容块支持手动维护`生成前提问`，生成时`问题+回答`都进入上下文。
  - 在模板编辑中移除`输入指引`、`输出指引`输入框。
  - 全系统删除`阶段（phase）`概念，仅保留`组（group）`与`内容块（field）`。
- 约束：
  - 不做补丁式绕行，必须改数据契约与业务主链路。
  - 与既有模板树/项目树同构方向保持一致。
  - 先出方案，待确认后再实施代码变更。

## 第一性原理与根因判断

## 1) “只能先组后块”问题的根因

- UI 入口限制：项目树顶层主要暴露“新增组”，新增内容块与模板引用入口分布不一致。
- 模板入口分散：新建项目、树内新增、自动拆分导入存在多套入口，能力不对齐。
- 语义历史包袱：`phase/group/field`并存导致“顶层容器”认知混乱，阻碍统一交互。

## 2) “生成前提问可手动添加 + 入上下文”问题的根因

- 数据面已具备：`ContentBlock`与模板节点均已有`pre_questions/pre_answers`字段与复制链路。
- 体验面不足：项目内编辑器以“回答现有问题”为主，缺少“新增/删除问题”的稳定入口与规则。
- 上下文面部分满足：生成链路会拼接`pre_answers`，但需要统一“问题-回答对”注入策略与验证。

## 3) “移除输入/输出指引”问题的根因

- 产品决策与实现不一致：文档已判定该能力冗余，但模板编辑器仍显示；后端与DB仍保留并传播。
- 契约未收敛：API/模型仍公开字段，导致前后端持续携带无效概念。

## 4) “删除阶段 phase”问题的根因

- phase 不是仅 UI 文案，而是系统级主轴：
  - 后端：`Project.current_phase/phase_order/phase_status`、`phase_config/phase_service`。
  - Agent：`orchestrator`系统提示依赖`current_phase`。
  - 前端：workspace、progress、content panel 均有 phase 分支逻辑。
  - 工具链：`architecture_reader/writer`和模板接口仍有 phase 专用语义。
- 因此必须做“架构去 phase 化”，而不是简单改枚举或改文案。

## 目标架构（改造后）

- 统一实体语义：
  - `group`：仅结构容器，可嵌套。
  - `field`：可生成的内容块（含提示词、依赖、前提问答）。
- 模板与实例同构：
  - 模板节点仅允许`group | field`。
  - 项目内容块仅允许`group | field`。
- 生成上下文统一规则：
  - 注入`用户补充信息`时按“问题: 回答”对输出，缺失回答按空值处理或阻断（可配置）。
  - 取消`guidance_input/output`在产品面与生成面的作用，仅保留历史兼容迁移。

## 改造方案（按链路）

## A. 数据模型与契约收敛（后端）

- `ContentBlock.block_type`从`phase|group|field|proposal`收敛到`group|field`（`proposal`按现状评估，若已无业务价值同步收敛）。
- `TemplateNode.type`从`phase|group|field`收敛到`group|field`。
- `Project`去 phase 化：
  - 删除或弃用`current_phase/phase_order/phase_status`读写逻辑。
  - 用“树节点状态 + special_handler（如仍需要）”替代流程位点。
- API 契约调整：
  - blocks/template/settings/phase_templates 等接口移除`guidance_input/output`入参与出参（或先标记 deprecated，下一步彻删）。
  - 移除所有 phase 专属字段与语义返回。

## B. 模板体系统一（FieldTemplate / PhaseTemplate）

- 方向：从“双模板体系”收敛为“单一模板树体系”。
- `PhaseTemplate`迁移策略：
  - 将现有 phase 模板映射为 group 根节点树，保留名称与结构。
  - 新增“模板类型”可选（如需要）但不再以 phase 语义建模。
- `template_schema`统一：
  - normalize/instantiate 只处理`group|field`。
  - 兼容读取历史`phase`节点并在归一化时自动转`group`，迁移完成后移除兼容分支。

## C. 生成前提问答（项目编辑与生成链路）

- 前端编辑器（完整编辑器 + 卡片编辑器）：
  - 支持增删改`pre_questions`。
  - 回答以`pre_answers[question]`绑定，问题重命名需同步迁移旧 key。
- 后端更新接口：
  - `BlockUpdate`允许原子更新`pre_questions`与`pre_answers`，并做一致性校验（孤儿 answer 清理/保留策略明确）。
- 生成服务：
  - 上下文拼接改为稳定格式：
    - `用户补充信息`
    - `- 问题A: 回答A`
    - `- 问题B: 回答B`
  - 自动生成就绪检查继续校验“有问题则需有答案”，并给出明确错误信息。

## D. 前端交互重构

- 项目树（`block-tree`）：
  - 顶层直接提供：新增`组`、新增`内容块`、从模板添加。
  - 子级同样提供三种入口，能力对齐。
- 新建项目（`create-project-modal`）：
  - 支持“空项目后立即选模板注入”与“直接空树创建”。
  - 模板来源统一（不再分 phase/field 的认知层）。
- 内容面板（`content-panel`）：
  - 删除 phase 分支渲染逻辑，仅按`group/field + special_handler`分发。
- 模板设置页（`template-tree-editor`等）：
  - 删除`输入指引/输出指引`表单项。
  - 节点类型仅`组/内容块`。

## E. Agent 与工具链去 phase 化

- `orchestrator`：
  - 移除`current_phase`注入与 phase 专属系统提示分支。
  - 将流程引导改为“基于当前选中节点 + special_handler + 依赖状态”的动态策略。
- `agent_tools`、`architecture_reader/writer`：
  - 删除`add_phase/remove_phase/advance_to_phase`等 phase 语义工具。
  - 保留并强化通用`add_node/remove_node/move_node/update_node_meta`。

## F. 迁移与兼容策略（一次性根改，不停服）

- 数据迁移：
  - 将所有`content_blocks.block_type='phase'`批量转`group`，校正父子层级与排序。
  - 模板树中`type='phase'`批量转`group`。
  - 项目表 phase 字段冻结为只读历史字段（短期），最终删除列（长期）。
- 兼容窗口（建议两阶段）：
  - 阶段1：读兼容、写新值（禁止再写 phase/guidance）。
  - 阶段2：删除兼容代码与废弃列。
- 导入导出与复制：
  - 全链路使用新契约；导入历史数据时做映射转换并输出迁移告警日志。

## G. 自动拆分内容专项改造（必须与主链路同步）

- 范围界定：
  - 覆盖`project-structure-draft-editor`、`project-auto-split-modal`、`project-template-import-bar`、`project-structure-draft-utils`。
  - 覆盖`project_structure_compiler`、`project_structure_apply_service`、`project_structure_drafts` API。
  - 覆盖`ProjectStructureDraft.draft_payload`历史数据迁移。
- 前端草稿编辑器改造：
  - 草稿节点创建类型仅允许`group|field`，移除`phase`入口与文案。
  - 草稿内模板树编辑同样移除`guidance_input/output`表单项。
  - 模板导入与节点克隆时统一做`phase -> group`归一化与依赖重映射校验。
- 后端编译/校验/应用改造：
  - `validate`阶段：拒绝新提交`phase`；历史草稿自动归一化后再参与循环依赖与完整性校验。
  - `apply`阶段：应用前再次归一化（防御式），保证落库只有`group|field`。
  - 错误信息统一：明确标注“草稿中存在已废弃 phase 节点”与自动修复结果。
- 草稿数据迁移策略：
  - 为历史`draft_payload`提供迁移脚本：节点`type='phase'`批量转`group`，清理`guidance_input/output`业务字段。
  - 迁移后自动执行`validate`，确保依赖映射、层级顺序、可应用性均通过。
- 与主方案的对齐约束：
  - 自动拆分链路不得再引入任何 phase 语义分支。
  - 自动拆分链路不得再向下游写入 guidance 字段。

## H. 测试与验收

- 后端单测：
  - `template_schema`：phase->group 归一化、依赖映射正确。
  - `blocks`生成：`pre_questions/pre_answers`注入文本与就绪校验。
  - `projects`复制/导入导出：无 phase/guidance 回流。
  - `project_structure_draft`：历史 phase 草稿输入可自动归一化，`validate/apply`成功且依赖不丢失。
- 前端单测：
  - 项目树三入口可见且可用（顶层/子层）。
  - 模板编辑器无 guidance 字段。
  - 内容块可手动新增前提问，回答保存后触发生成能带入上下文。
  - 自动拆分弹窗/编辑器中不可创建 phase，导入模板后节点类型始终为`group|field`。
- 集成验收场景：
  - 新项目空树 -> 直接加内容块 -> 生成成功。
  - 新项目 -> 直接从内容块模板注入 -> 依赖与问答正常。
  - 历史项目（含 phase）升级后可正常编辑与生成。
  - 自动拆分：拆分 -> 编辑草稿 -> 校验 -> 应用 -> 生成，全链路无 phase/guidance 回流。

## 实施 To-Do List（执行清单）

- [x] T1. 冻结目标契约：定义唯一节点类型`group|field`与 API 字段白名单（移除 guidance/phase 写入）。
- [x] T2. 设计并落地数据迁移脚本：`phase -> group`（内容块 + 模板树 + 历史导入映射）。
- [x] T3. 重构`template_schema`与实例化链路：仅保留`group|field`主路径，保留短期读兼容。
- [x] T4. 重构 blocks API 模型：统一`pre_questions/pre_answers`原子更新与校验逻辑。
- [x] T5. 重构生成服务上下文拼接：稳定注入“问题-回答对”，补齐错误提示。
- [x] T6. 前端项目树改造：顶层/子层统一支持“加组/加内容块/从模板添加”。
- [x] T7. 前端内容块编辑器改造：支持手动增删改前提问题并保持答案映射一致。
- [x] T8. 前端模板编辑器改造：移除`输入指引/输出指引`，节点类型仅`组/内容块`。
- [x] T9. 新建项目与模板选择流程收敛：统一模板来源与注入路径。
- [x] T10. Agent 去 phase 化：下线`current_phase`驱动，改为节点/handler驱动。
- [x] T11. 清理 phase 专属代码与配置：`phase_config/phase_service`及前端 phase 常量链路。
- [x] T12. 全量测试补齐：单测、集成测试、回归清单与历史数据升级验证。
- [x] T13. 兼容窗口收口：删除读兼容分支与废弃字段/列，完成最终收敛。
- [x] T14. 自动拆分前端专项：草稿编辑/模板导入链路彻底去 phase 与 guidance。
- [x] T15. 自动拆分后端专项：`compiler/validate/apply`全链路去 phase 与 guidance，并补防御式归一化。
- [x] T16. 自动拆分历史草稿迁移：批量迁移`draft_payload`并执行迁移后 validate。
- [x] T17. 自动拆分专项测试：单测 + 集成用例覆盖拆分到生成全链路。

## 关键决策点（需你确认）

- 是否接受“两阶段兼容窗口”：
  - 若接受：先保证平滑升级，再彻删历史字段。
  - 若不接受：可做一次性强迁移，但上线风险和回滚成本更高。
- `special_handler`是否保留：
  - 建议保留（这是能力类型，不等于 phase）。
  - 若要进一步简化，可在后续第二轮再评估。
- `proposal`类型是否一并收敛：
  - 建议本轮先聚焦四项问题；若当前仍被业务使用，暂不动。

## 交付标准（本方案通过后）

- 用户认知层只剩两类节点：`组`与`内容块`。
- 新项目和项目树中，任意层级均可直接创建内容块或从模板引入。
- 内容块可手动维护前提问题，生成时问题与回答稳定进入上下文。
- 模板编辑界面不再出现`输入指引/输出指引`，后端不再依赖其业务语义。
- 代码中不再存在“phase 作为主流程控制轴”的运行时依赖。

