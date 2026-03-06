# 内容块模板与项目树结构对齐方案

## 背景
当前系统里有两套相近但能力不对齐的结构编辑能力：

- 项目工作台中的 `ContentBlock` 树已经支持无限层级、`phase/group/field` 混合嵌套、节点折叠、拖拽移动、复制、软删除、模板导入到组下。
- 后台设置中的“内容块模板”仍然是旧的扁平 `FieldTemplate.fields[]` 模型，只能顺序添加内容块，不能表达组结构，也没有模板侧折叠状态。

这直接带来三个问题：

1. 模板编辑体验弱于项目结构编辑体验，后台定义出来的模板无法完整表达项目真实结构。
2. 项目中的“新建 / 引用模板 / 新建组”入口与模板本身的数据结构不一致，导致引用能力天然受限。
3. 依赖、引用、AI 生成、Agent 架构修改等逻辑仍大量依赖“名称”而非稳定节点标识，扩展到树形模板后风险会放大。

本方案目标是在**不立即动代码的前提下**，给出一份完整的产品与技术改造方案，覆盖需求理解、现状调研、数据模型、前后端改造、兼容迁移、测试矩阵与实施 TODO。

## 一、第一性原理理解需求

### 1.1 用户真正要解决的问题
从第一性原理看，用户不是单纯想“让模板多几个字段”，而是在追求三件事：

- `结构复用`：把已经验证过的项目结构，作为模板在未来项目中重复使用。
- `认知对齐`：后台设置里定义的模板，必须和项目中实际操作的树结构是同一种对象模型，而不是“后台是字段列表，项目是树”。
- `渐进搭建`：项目结构不是一次性整体创建，而是随时可以在任意节点新增组、新增内容块、从模板引用、继续嵌套。

因此，模板的本质不应再是“字段数组”，而应是“可复用的树形结构片段”。

### 1.2 需求拆解
原始需求可以拆成以下能力：

1. 模板节点文案增强
- 每个内容块字段后都要补一句引导。
- 本质上是给模板节点增加“用户输入说明 / 期待输出说明”类元数据。

2. 模板结构与项目树完全同构
- 模板里可以创建组。
- 组下可以放组或内容块。
- 层级无限。

3. 模板节点也支持折叠
- 组可折叠。
- 内容块也可折叠。
- 折叠状态至少要支持编辑态 UI；是否持久化到模板数据，需要产品明确，但建议持久化。

4. 项目侧入口统一
- 项目里不应只有“新建组”这一个顶层入口。
- 任意可容器节点下，都应统一支持：
  - 新建内容块
  - 新建组
  - 从内容块模板引用
  - 长期看也可以支持“从流程模板/结构模板引用片段”

5. 引用与依赖逻辑升级
- 现状里很多地方按“名称”找块。
- 树结构复杂后，重名、移动、局部引用、模板片段应用都会让“按名称定位”越来越脆弱。
- 必须定义稳定节点标识与兼容策略。

## 二、现状调研结论

## 2.1 后台设置页面结构
后台设置页 `frontend/app/settings/page.tsx` 目前有两个与本需求直接相关的 Tab：

- `内容块模板`：对应 `TemplatesSection`
- `流程模板`：对应 `PhaseTemplatesSection`

这两个 Tab 现在能力严重不对称：

- `TemplatesSection` 管的是扁平 `FieldTemplate`
- `PhaseTemplatesSection` 管的是“顶层组 + 组内 default_fields”

这说明系统已经有两种模板模型并存，但都还没有真正和项目树完全同构。

## 2.2 内容块模板现状
相关代码：

- `frontend/components/settings/templates-section.tsx`
- `backend/api/settings.py`
- `backend/core/models/field_template.py`

现状特征：

- 数据结构是 `FieldTemplate.fields[]`
- 只支持顺序增删改内容块
- 依赖关系用 `depends_on: string[]`，值是“其他节点名称”
- 不支持组
- 不支持无限层级
- 不支持模板节点折叠
- 导入导出也是基于旧的扁平 `fields`

这套模型本质是“字段清单模板”，不是“树模板”。

## 2.3 流程模板现状
相关代码：

- `frontend/components/settings/phase-templates-section.tsx`
- `backend/core/models/phase_template.py`

现状特征：

- 支持顶层 `phases[]`
- 每个 `phase` 下有 `default_fields[]`
- `default_fields` 可以把 `block_type` 填成 `field` 或 `phase`
- 但后端 `apply_to_project()` 只按“phase -> 一层子块”展开
- 没有递归应用任意深度树
- 没有通用模板片段复用能力
- 也没有模板节点级折叠持久化

它比 `FieldTemplate` 更接近树，但仍是“最多两层”的弱结构。

## 2.4 项目树现状
相关代码：

- `frontend/components/block-tree.tsx`
- `frontend/components/progress-panel.tsx`
- `frontend/components/content-panel.tsx`
- `backend/api/blocks.py`
- `backend/core/models/content_block.py`

项目树已经具备的能力：

- `ContentBlock` 原生支持 `parent_id`、`depth`、`block_type`、`children`
- 支持 `phase/group/field/proposal`
- 支持任意深度嵌套
- 支持折叠状态 `is_collapsed`
- 支持拖拽移动
- 支持复制、删除、撤回
- 非 `field` 节点下可新增：
  - 空白内容块
  - 子组
  - 从模板添加

当前不足：

- 顶层空状态和底部入口只支持“添加组”，不支持“添加内容块”“从模板添加”
- “从模板添加”只能把 `FieldTemplate.fields[]` 批量挂到某个组下
- 模板弹窗文案也明确写的是“从模板添加内容块”

因此，项目树能力比模板强，但“入口统一性”仍不完整。

## 2.5 项目创建时模板应用现状
相关代码：

- `frontend/components/create-project-modal.tsx`
- `backend/api/blocks.py::apply_template_to_project`

现状：

- 创建项目时统一展示 `PhaseTemplate + FieldTemplate`
- 若选中 `PhaseTemplate`，后端调用 `PhaseTemplate.apply_to_project()`
- 若选中 `FieldTemplate`，后端调用 `_field_template_to_blocks()`
- `FieldTemplate` 会被降级为“一个默认组 + 若干内容块”

这说明：

- 系统已经承认“扁平内容块模板其实不够表达完整结构”
- 但当前的补救方式仍是临时转换，不是真正的数据模型统一

## 2.6 引用 / 依赖 / Agent 架构修改现状
这部分是本次最关键的隐藏约束。

相关代码：

- `backend/core/prompt_engine.py`
- `backend/core/tools/architecture_reader.py`
- `backend/core/agent_tools.py`
- `backend/core/tools/architecture_writer.py`
- `backend/api/blocks.py`

现状问题：

1. 大量逻辑按名称找块
- `_find_block()` 按 `ContentBlock.name`
- `FieldTemplate.depends_on` 按名称
- `architecture_reader` 多处按名称读取块
- prompt `@引用` 也是按名称解析

2. 模板内部依赖应用时靠名称映射
- `block-tree.tsx` 中模板添加逻辑通过字段名映射已创建块 ID
- `apply_template_to_project()` 也是先 name -> id，再回填 `depends_on`

3. Agent 架构修改能力仍是旧“phase / field”思维
- `manage_architecture` 只支持 `add_phase/remove_phase/add_field/remove_field/move_field`
- `architecture_writer` 也主要围绕顶层 phase 和 field
- 不支持真正的任意层 group/tree 操作

4. 重名风险被低估
- 一旦模板允许无限层级，出现同名组、同名内容块会很常见
- 单靠 `name` 已不足以表达模板节点身份

结论：
如果只改模板编辑器 UI 而不升级“节点身份与引用解析”，后续一定会在引用、依赖、模板应用、Agent 改结构、重命名、迁移中反复出问题。

## 三、核心设计判断

### 3.1 不能继续新增第三套模板模型
当前已有：

- `FieldTemplate`
- `PhaseTemplate`
- 项目运行时 `ContentBlock`

如果为了这次需求再加一套“TemplateTree”，但不整合旧模型，只会让系统更复杂。

正确方向应是：

- 让模板结构尽量向 `ContentBlock` 的树模型靠拢
- 把模板看成“未绑定 project_id 的结构化节点树”
- 逐步弱化 `FieldTemplate` 与“半结构化 `PhaseTemplate`”的历史差异

### 3.2 模板和项目要“同构，不同实例”
建议的原则：

- 项目中的节点是 `ContentBlock`
- 模板中的节点是 `TemplateNode`
- 两者字段尽量同构，但语义不同：
  - 项目节点有运行态字段，如 `status`
  - 模板节点有设计态字段，如 `guidance_input`、`guidance_output`

也可以更激进地直接把模板节点存成 `ContentBlock` 兼容 JSON 结构，但当前从演进与兼容性角度看，定义清晰的模板节点 JSON 更稳。

### 3.3 模板应用本质上是“子树实例化”
不应再把“应用模板”理解成“把字段数组循环 create 一遍”。

正确语义应是：

- 输入：一个模板节点子树
- 输出：在目标项目、目标父节点下实例化一棵 `ContentBlock` 子树
- 实例化时需要完成：
  - 新 ID 分配
  - 父子关系重建
  - 节点排序
  - 模板内依赖重写
  - 可选的外部依赖保留/映射
  - 初始折叠态写入

### 3.4 引导文案不是 UI 提示，而是节点元数据
需求（1）里“每个字段后补充一句引导，用户需要输入什么、期待输出什么”，不应只做成前端 placeholder。

建议抽象成模板节点元数据：

- `guidance_input`: 用户应提供什么输入
- `guidance_output`: 期待这个节点产出什么

后续这些数据可复用到：

- 后台模板编辑表单
- 项目内容块详情页提示
- 新建节点后的空态引导
- Agent 解释某节点用途
- 模板预览与选择器卡片

## 四、目标方案

## 4.1 统一的模板节点数据结构
建议新增一个统一模板结构，命名可选：

- `BlockStructureTemplate`
- 或 `ContentTreeTemplate`
- 或在现有 `FieldTemplate` 上升级到 `schema_version = 2`

为了降低迁移成本，建议优先采用：

- 保留 `FieldTemplate` 这张表
- 增加版本字段与新结构字段
- 逐步把旧 `fields` 迁移为 `nodes`

建议目标结构：

```json
{
  "schema_version": 2,
  "name": "示例模板",
  "description": "说明",
  "category": "通用",
  "root_nodes": [
    {
      "template_node_id": "node_root_1",
      "parent_template_node_id": null,
      "name": "一级组",
      "block_type": "group",
      "order_index": 0,
      "is_collapsed": false,
      "special_handler": null,
      "content": "",
      "ai_prompt": "",
      "pre_questions": [],
      "depends_on_template_node_ids": [],
      "depends_on_legacy_names": [],
      "need_review": true,
      "auto_generate": false,
      "model_override": null,
      "constraints": {},
      "guidance_input": "用户需要补充什么",
      "guidance_output": "期待得到什么",
      "children": []
    }
  ]
}
```

关键点：

- `template_node_id` 是模板内稳定节点 ID，不再只靠名称
- `children` 支持无限层级
- `block_type` 允许 `group/field`，是否允许模板内出现顶层 `phase` 需产品决定
- `is_collapsed` 持久化
- `guidance_input/guidance_output` 显式落库
- `depends_on_template_node_ids` 作为新主依赖表达
- `depends_on_legacy_names` 作为过渡兼容字段

## 4.2 模板类型收敛策略
建议未来按职责收敛成两类：

1. `结构模板`
- 用于项目创建
- 可以是完整树
- 可以包含顶层多个组

2. `片段模板`
- 用于项目编辑时，在任意节点下引用
- 也是树
- 只是规模较小

从存储上不一定需要两张表，可以是一张模板表加 `template_scope`：

- `project_bootstrap`
- `subtree_snippet`
- `both`

这样可以避免 `FieldTemplate` 和 `PhaseTemplate` 长期双轨。

## 4.3 项目侧入口统一
目标交互：

1. 顶层空状态
- `新建组`
- `新建内容块`
- `从模板引用`

2. 顶层底部操作条
- `添加组`
- `添加内容块`
- `从模板引用`

3. 任意可容器节点（group/phase）
- `添加子组`
- `添加内容块`
- `从模板引用`

4. 是否允许 `field` 下继续挂子节点
- 当前系统不允许，建议继续保持不允许
- 即“容器节点 = phase/group”

## 4.4 折叠能力设计
需求说“每个组和每个内容块都可以折叠”。

建议拆成两层：

1. 模板编辑器折叠
- 纯编辑体验，避免长模板难以操作
- 持久化到模板数据中，方便下次编辑保持状态

2. 项目实例折叠
- 继续沿用 `ContentBlock.is_collapsed`
- 模板应用时可选择是否继承模板默认折叠态

建议默认：

- 模板节点折叠态在实例化时复制到项目节点

## 4.5 引导文案呈现方式
建议每个 `field` 节点在模板编辑和项目编辑中都显示：

- `用户输入引导`
- `期待输出引导`

项目侧使用方式建议：

- 内容块为空时，在编辑器顶部以提示条显示
- 内容块已有内容时折叠展示或弱化展示
- 模板预览卡片中只展示摘要，不显示全文

## 4.6 生成前提问的端到端设计
这一点必须单独定义，因为它不是“多一个表单字段”这么简单，而是一条必须贯通的链路：

- 模板中定义 `pre_questions`
- 模板实例化到项目后保留到 `ContentBlock.pre_questions`
- 用户在项目里填写答案，保存到 `ContentBlock.pre_answers`
- 生成时将问答显式拼进最终发给大模型的 prompt

这四步缺任意一步，都会出现“UI 看起来支持了生成前提问，但模型实际没拿到补充信息”的伪完成问题。

### 4.6.1 设计原则

1. `pre_questions` 是生成配置的一部分，不是纯前端提示
- 必须持久化
- 必须随模板实例化传递
- 必须进入后端生成上下文

2. `pre_answers` 是项目运行态数据，不属于模板本体
- 模板里只定义问题
- 项目里才存答案

3. 大模型看到的是“问题 + 用户回答”，不是只有回答
- 避免回答脱离上下文，模型不知道这段补充信息是在回答什么

4. prompt 注入要稳定、显式、可测试
- 不能依赖某个前端临时拼接逻辑
- 应在后端统一的 prompt 构建链路中注入

### 4.6.2 模板侧要求

无论是在“内容块模板”还是未来统一后的“结构模板”里，只要节点类型是 `field`，都必须支持配置：

- `pre_questions: string[]`

模板编辑器要求：

- 可新增、删除、排序 `pre_questions`
- 空字符串不允许保存
- 自动去除首尾空白
- 保留问题顺序，因为顺序会影响用户理解与填写体验

模板预览要求：

- 预览卡片中展示“包含 N 个生成前提问”
- 不必默认展开全文，但要让使用者知道该块在生成前需要补充信息

### 4.6.3 项目实例化要求

模板实例化时必须满足：

1. `pre_questions` 从模板节点原样复制到对应的 `ContentBlock.pre_questions`
2. 新创建的项目块 `pre_answers` 初始为空对象
3. 多次从同一模板重复实例化时，各实例的 `pre_answers` 相互独立
4. 局部从模板引用到某个组下时，`pre_questions` 同样必须完整保留

这是创建项目和项目内“从模板引用结构”两个入口的共同要求，不能只保证其中一个入口。

### 4.6.4 项目编辑态要求

项目中的 `field` 节点若存在 `pre_questions`，则编辑器必须：

1. 明确展示“生成前提问”区域
2. 支持逐题填写答案
3. 显式保存到 `pre_answers`
4. 保存后再次进入仍能回显
5. 即使内容块为空，也能先填写回答再触发生成

建议 UI 行为：

- 未回答时显示未完成计数，如 `0/3 已回答`
- 部分回答允许保存，但生成时的是否放行需要单独定义

建议的生成放行策略：

- 默认允许部分回答后生成，因为有些问题可能非必填
- 但若后续产品确认“生成前提问必须全部回答”，则应在节点级增加 `require_all_pre_questions_answered`
- 本次先不扩张字段，默认采用“允许部分回答，但在 UI 上提醒未回答项”的策略

### 4.6.5 Prompt 注入要求

这是最重要的硬性要求。

当前后端已有 `PromptEngine.get_field_generation_prompt()` 将 `field.pre_answers` 拼入 prompt 的实现，未来改造必须保留并强化这条链路，而不是被模板重构意外绕过。

目标要求：

1. 所有内容块生成入口都必须走统一的 prompt 构建函数
2. `pre_answers` 必须在后端注入，不允许仅靠前端拼 prompt
3. 注入格式必须包含“问题 + 回答”，建议继续使用如下语义块：

```text
# 用户补充信息
- 问题A: 回答A
- 问题B: 回答B
```

4. 注入顺序建议固定为：
- 系统上下文 / 创作者特质
- 依赖内容
- 当前字段信息
- 具体生成要求 `ai_prompt`
- 用户补充信息 `pre_answers`
- 输出格式要求

或保持现有顺序，但必须确保：
- `pre_answers` 不丢
- 注入位置稳定
- 可被测试断言

5. 若 `pre_questions` 存在但 `pre_answers` 为空：
- prompt 中不应伪造默认答案
- 后端只传真实已有回答
- 前端负责提醒用户当前回答不完整

### 4.6.6 与引导文案的边界

要明确区分：

- `guidance_input/guidance_output`：给人看的说明，帮助理解这个块该填什么、产出什么
- `pre_questions/pre_answers`：会进入生成链路、参与 prompt 的结构化补充信息

两者不能混用，也不能因为有了引导文案就省略生成前提问。

### 4.6.7 兼容迁移要求

历史模板和历史项目里已经有 `pre_questions/pre_answers` 的地方，迁移时必须保持：

- 旧 `FieldTemplate.fields[].pre_questions` 不丢失
- 旧 `PhaseTemplate.default_fields[].pre_questions` 不丢失
- 旧项目块上的 `pre_questions/pre_answers` 不被清空
- 新模板树 schema 在升级保存后仍能回显这些问题

### 4.6.8 实现红线

下面这些都算“没改对”：

1. 模板设置里能编辑 `pre_questions`，但实例化到项目后消失
2. 项目里能填写回答，但重新打开块后不回显
3. 回答保存成功，但生成 prompt 没带上
4. 创建项目时应用模板能保留，项目内“从模板引用”却丢失
5. 只有内容块模板支持，流程模板/统一结构模板不支持
6. 只有前端显示，Agent 或后端生成链路没读到

## 五、前端改造方案

## 5.1 后台设置页
主要改造对象：

- `frontend/components/settings/templates-section.tsx`

建议把它从“扁平字段表单”改成“模板树编辑器”，而不是继续追加 patch。

建议拆分组件：

- `template-tree-editor.tsx`
- `template-node-row.tsx`
- `template-node-form.tsx`
- `template-node-actions.tsx`
- `template-template-picker.tsx`（如后续支持模板内嵌引用）

关键交互：

- 新建模板时默认空树
- 顶层可添加组或内容块
- 节点支持：
  - 新增同级
  - 新增子组
  - 新增子内容块
  - 删除
  - 复制
  - 重命名
  - 折叠
  - 上下移动

字段编辑项：

- 名称
- AI 提示词
- 预置内容
- 生成前提问
- 依赖
- 需要人工确认
- 自动生成
- 模型覆盖
- 约束
- 用户输入引导
- 期待输出引导
- 折叠状态

## 5.2 流程模板页
主要改造对象：

- `frontend/components/settings/phase-templates-section.tsx`

建议不要继续维护一套完全独立的“phase + default_fields”编辑器。

推荐方向：

- 第一阶段先保留该页，但底层改为复用同一个树编辑器
- 通过约束保证“项目启动模板必须有至少一个顶层组”
- 顶层组如需表达历史 phase，可通过 `block_type=phase` 或 `group + special_handler`

长期目标：

- 与内容块模板合并为统一模板中心
- 仅通过“用途/范围”区分模板，而不再通过两套 UI 区分

## 5.3 项目树入口
主要改造对象：

- `frontend/components/block-tree.tsx`
- `frontend/components/progress-panel.tsx`

建议：

- 空态从单按钮改为三按钮入口
- 底部从单按钮“添加组”改为操作条
- 模板弹窗文案改为“从模板引用结构”
- 引用目标说明改为“添加到当前组/当前顶层”

## 5.4 项目详情页
主要改造对象：

- `frontend/components/content-block-editor.tsx`
- `frontend/components/content-block-card.tsx`

需要新增：

- 读取并展示 `guidance_input/guidance_output`
- 读取并展示 `pre_questions`
- 支持编辑并保存 `pre_answers`
- 在空内容时给用户明确提示：
  - 你需要输入什么
  - 这个块应产出什么

生成链路硬性要求：

- 不能因为模板树改造而破坏当前项目侧 `pre_questions -> pre_answers -> prompt` 的链路
- 项目块只要存在 `pre_questions`，就必须能在生成前填写并保存回答
- 所有生成入口都必须读取最新的 `pre_answers`，不能读到旧缓存

注意：

- 当前 `ContentBlock` 类型还没有这两个字段
- 需要在 API 和前端类型里同步补充

## 5.5 项目创建弹窗
主要改造对象：

- `frontend/components/create-project-modal.tsx`

建议：

- 不再把 `FieldTemplate` 强行转成单 phase 预览
- 统一预览真实树结构
- 标注模板来源：
  - 完整项目模板
  - 结构片段模板

如果仍保留“从零开始”，则应在文案里明确：

- 从零开始后，用户可以：
  - 新建组
  - 新建内容块
  - 从模板引用结构片段

## 六、后端改造方案

## 6.1 模板存储
主要改造对象：

- `backend/core/models/field_template.py`
- `backend/api/settings.py`

建议增加：

- `schema_version`
- `nodes` 或 `root_nodes`
- 保留旧 `fields` 作为兼容读字段

不建议直接删除 `fields`，因为：

- 现有导入导出依赖它
- 旧模板数据需要可读
- 创建项目弹窗当前也依赖它

建议兼容策略：

- 读取模板时：
  - 若 `schema_version >= 2 && nodes` 存在，走新逻辑
  - 否则将旧 `fields` 临时升格成一层树

## 6.2 模板 CRUD API
主要改造对象：

- `backend/api/settings.py`

需要：

- 新的 `TemplateNode` Pydantic schema
- 新的模板 create/update 校验
- 递归校验：
  - 节点 ID 唯一
  - 父子无环
  - 容器节点合法
  - 依赖目标存在
  - 依赖不能指向后代
  - 可选：依赖图无环

建议把校验逻辑放到独立模块：

- `backend/core/template_validation.py`

## 6.3 模板实例化 API
主要改造对象：

- `backend/api/blocks.py::apply_template_to_project`

需要把现有逻辑升级为：

1. 支持把模板应用到空项目根节点
2. 支持把模板应用到任意目标父节点
3. 支持实例化整棵子树
4. 模板内依赖由 `template_node_id -> new block.id` 重映射
5. 外部依赖策略可配置
6. 模板节点的 `pre_questions` 必须完整复制到实例化后的 `ContentBlock`
7. 新实例的 `pre_answers` 必须初始化为空对象，不能继承其他项目或其他实例的数据

建议新增 API，而不是继续复用老接口语义：

- `POST /api/blocks/project/{project_id}/instantiate-template`

请求体示例：

```json
{
  "template_id": "xxx",
  "target_parent_id": "block_xxx_or_null",
  "insert_mode": "append",
  "inherit_collapsed_state": true
}
```

旧的 `apply-template` 可以内部转发到新逻辑，保持兼容。

## 6.4 ContentBlock 模型扩展
主要改造对象：

- `backend/core/models/content_block.py`
- `backend/api/blocks.py`
- `frontend/lib/api.ts`

建议新增字段：

- `guidance_input`
- `guidance_output`

原因：

- 模板实例化后，项目节点仍需保留这些说明
- 不然模板的引导信息会在应用后丢失

同时必须确认并保持以下运行态字段行为：

- `pre_questions`：模板定义的问题列表，实例化后写入项目块
- `pre_answers`：项目中用户填写的回答，生成时参与 prompt 构建

这里的要求不是“字段继续存在”就算完成，而是：

- API 响应中可读写
- 前端类型中可访问
- 生成链路中可稳定注入给大模型

## 6.4.1 Prompt 构建链路的硬性要求
主要改造对象：

- `backend/core/prompt_engine.py`
- `backend/core/tools/field_generator.py`
- `backend/api/blocks.py`

必须保证以下约束：

1. `PromptEngine.get_field_generation_prompt()` 继续作为统一注入点，负责把 `pre_answers` 拼入最终 prompt
2. 模板树重构后，任何新的生成入口都不能绕过这条链路
3. 注入内容必须保留“问题 + 回答”的对应关系，不能只拼接回答文本
4. 若未来对 prompt 拼装顺序做重构，必须新增回归测试，确保 `pre_answers` 仍然出现在最终 prompt 中
5. 流式生成与非流式生成都必须走同一套包含 `pre_answers` 的 prompt 逻辑

## 6.5 引用与依赖解析升级
这是最高风险点，建议单独立项处理。

### 短期兼容方案
- 项目运行时 `depends_on` 仍继续存 `block.id`
- 模板侧新结构用 `depends_on_template_node_ids`
- 历史模板仍可读 `depends_on` 名称

### 中期升级方案
将所有“按名称找块”的逻辑逐步升级为优先按 ID，再回退名称：

- `backend/core/agent_tools.py::_find_block`
- `backend/core/tools/architecture_reader.py`
- `backend/core/prompt_engine.py::parse_references`
- `backend/core/tools/architecture_writer.py`

建议新增统一定位协议：

- 显式 ID：`block:uuid`
- 路径引用：`groupA/groupB/内容块`
- 名称引用：仅作兼容回退

### 对用户侧 @引用 的建议
用户输入时继续允许 `@块名`，但系统内部解析最好支持：

- 精确块 ID
- 唯一路径
- 重名歧义提示

## 6.6 Agent 架构修改工具升级
主要改造对象：

- `backend/core/agent_tools.py::manage_architecture`
- `backend/core/tools/architecture_writer.py`

当前问题：

- 操作语义还停留在 `phase/field`
- 不支持任意层 `group`
- 不支持“从模板引用结构片段”

建议演进成更通用的树操作：

- `add_node`
- `remove_node`
- `move_node`
- `duplicate_node`
- `instantiate_template`
- `update_node_meta`

输入参数也应改成：

- `target_parent_id`
- `target_node_id`
- `node_type`
- `position`

而不是继续依赖 phase 名称。

## 七、迁移与兼容策略

## 7.1 数据迁移原则
目标是“平滑升级，不阻塞已有项目和模板使用”。

### 模板迁移
1. 历史 `FieldTemplate.fields[]`
- 自动迁移为：
  - 一个虚拟根下的若干 `field` 节点
  - 或一个顶层默认 `group`

2. 历史 `PhaseTemplate.phases[].default_fields[]`
- 自动迁移为：
  - 多个顶层 `phase/group` 节点
  - 每个节点下挂其子节点

### 项目数据
- `ContentBlock` 现有树结构无需结构性重建
- 只需新增字段支持与实例化逻辑升级

## 7.2 兼容阶段划分

### 阶段 A：读兼容
- 新后端能读旧模板
- 新前端仍可显示旧模板

### 阶段 B：写新不写旧
- 新编辑器保存新 `schema_version=2`
- 旧模板首次编辑后升级

### 阶段 C：统一入口
- 创建项目与工作台引用都走新模板实例化接口

### 阶段 D：收敛旧模型
- 弱化 `PhaseTemplate` 与旧 `fields[]`
- 仅保留兼容读

## 八、测试方案

## 8.1 后端单元测试

1. 模板校验
- 空模板可创建
- 无限层级树可创建
- 非容器节点不能有子节点
- 依赖节点不存在时报错
- 依赖环报错
- 节点 ID 重复时报错

2. 旧模板兼容读取
- 旧 `FieldTemplate.fields[]` 能升格成树
- 旧 `PhaseTemplate` 能升格成树

3. 模板实例化
- 顶层实例化成功
- 向某个组下实例化成功
- 多层父子关系正确
- `order_index` 正确
- `is_collapsed` 继承正确
- `guidance_*` 正确复制
- `pre_questions` 正确复制
- `pre_answers` 初始化为空对象
- 模板内依赖正确映射到新 block ID

4. 边界情况
- 模板内重名节点
- 目标父节点不存在
- 往 `field` 下实例化时报错
- 目标项目已有内容时仍可局部实例化

5. 依赖 / 引用兼容
- 旧名称依赖仍能解析
- 新 ID 依赖优先解析
- 重名节点歧义时返回明确错误

6. Prompt 注入回归
- `pre_answers` 存在时，`PromptEngine.get_field_generation_prompt()` 的结果必须包含“问题 + 回答”
- 流式生成与非流式生成得到的最终 prompt 语义一致
- 模板实例化后的块在填写 `pre_answers` 后，生成接口确实读取到最新值

## 8.2 前端组件测试

1. 模板树编辑器
- 新增顶层组
- 新增顶层内容块
- 新增子组
- 新增子内容块
- 折叠 / 展开
- 删除 / 移动 / 重命名
- 引导文案编辑保存
- `pre_questions` 编辑、排序、删除、保存

2. 项目树入口
- 顶层可新建组
- 顶层可新建内容块
- 顶层可从模板引用
- 组下三种入口都可用

3. 项目详情页
- 空内容块展示引导文案
- 已有内容时不干扰编辑
- `pre_questions` 正确展示
- `pre_answers` 保存后回显
- 回答更新后再次生成使用的是最新回答

4. 创建项目弹窗
- 真实树预览
- 旧模板显示兼容

## 8.3 集成测试

1. 后台创建树模板 -> 项目中引用 -> 树结构一致
2. 创建项目时应用树模板 -> 项目初始结构一致
3. 模板含多层依赖 -> 实例化后生成链仍可执行
4. 模板含折叠态 -> 项目默认折叠状态正确
5. 模板含引导文案 -> 项目编辑器正确展示
6. 模板含 `pre_questions` -> 项目中可填写回答 -> 最终 prompt 包含对应问答

## 8.4 人工验收清单

1. 在后台设置新建一个三层模板：
- 一级组
- 二级组
- 内容块

2. 给每个内容块填写：
- AI 提示词
- 生成前提问
- 引导输入
- 引导输出

3. 在项目里：
- 顶层引用该模板
- 在某个组下再次引用该模板
- 单独新增内容块
- 单独新增组
- 折叠各级节点

4. 验证：
- 结构一致
- 文案一致
- 折叠生效
- 依赖仍可生成
- 生成前提问在项目里可回答并回显
- 回答后触发生成时，模型实际收到这些补充信息

## 九、推荐实施顺序

### P0：模型与接口打底
- 设计并落地统一模板树 schema
- 新增模板校验器
- 新增模板实例化接口
- 为 `ContentBlock` 增加引导字段
- 明确 `pre_questions/pre_answers` 在模板实例化与 prompt 构建链路中的保留策略

### P1：后台设置模板编辑器
- 将 `TemplatesSection` 升级为树编辑器
- 支持无限层级
- 支持折叠
- 支持引导文案

### P2：项目侧入口统一
- 顶层与组内统一三类入口
- 模板引用走新接口

### P3：项目详情与创建弹窗
- 展示引导文案
- 创建项目弹窗预览真实树

### P4：Agent / 引用 / 依赖收敛
- 升级 `manage_architecture`
- 升级名称解析逻辑
- 推进 ID / 路径优先策略

## 十、风险与注意事项

1. `名称依赖` 是最大技术债
- 如果不先设计模板节点稳定 ID，这次改造只会把问题做大

2. `PhaseTemplate` 不宜继续野蛮扩展
- 它现在只是“弱树”
- 继续 patch 只会让未来统一更难

3. `重名节点` 必须提前定义行为
- 模板允许重名吗
- 项目允许同级重名吗
- 引用遇到重名是报错、选第一个，还是要求用户 disambiguate

4. `折叠` 要区分模板态与实例态
- 模板里折叠只是编辑视图还是默认实例态，需要统一口径

5. `Agent 架构工具` 不能继续只认 phase
- 否则用户会在 UI 能做、Agent 不能做，产生能力断裂

## 十一、建议的最终形态
长期建议把“内容块模板”和“流程模板”收敛成一个统一的“结构模板中心”：

- 同一套树编辑器
- 同一套模板节点 schema
- 通过模板用途区分：
  - 项目初始化模板
  - 结构片段模板
  - 评估专用模板

这样整个系统最终只保留两种核心结构模型：

- 设计态：模板树
- 运行态：项目块树

而不是现在的三套半结构。

## 十二、完整 TODO

## 12.1 产品与交互
- 明确模板节点允许的 `block_type` 集合，建议 `group/field`
- 明确项目根节点是否允许直接创建 `field`
- 明确模板折叠态是否默认继承到项目实例
- 明确引导文案最终字段名与展示方式
- 明确“内容块模板”和“流程模板”是否在 UI 上合并
- 明确同名节点策略与歧义处理规则

## 12.2 数据模型
- 为模板定义 `schema_version`
- 定义 `TemplateNode` 结构
- 为模板节点增加稳定 `template_node_id`
- 为模板节点增加 `guidance_input`
- 为模板节点增加 `guidance_output`
- 确认模板节点继续支持 `pre_questions`
- 为模板节点增加 `is_collapsed`
- 定义模板依赖字段从“名称”向“节点 ID”过渡的兼容结构
- 为 `ContentBlock` 增加 `guidance_input`
- 为 `ContentBlock` 增加 `guidance_output`
- 保持 `ContentBlock.pre_questions/pre_answers` 的运行态语义不变

## 12.3 后端 API
- 重构 `FieldTemplate` 的 create/update/list/export/import
- 新增模板树校验模块
- 新增模板树实例化 API
- 支持实例化到项目根节点
- 支持实例化到任意组节点
- 支持模板内依赖 ID 重映射
- 支持模板节点 `pre_questions` 到项目块的完整复制
- 为旧 `apply-template` 保留兼容入口
- 为旧模板增加读兼容升级逻辑
- 为 prompt 构建链路补充回归测试，确保 `pre_answers` 继续进入最终大模型输入

## 12.4 前端后台设置
- 重写 `TemplatesSection` 为树编辑器
- 支持顶层添加组
- 支持顶层添加内容块
- 支持节点添加子组
- 支持节点添加子内容块
- 支持节点折叠
- 支持节点排序
- 支持引导文案编辑
- 支持 `pre_questions` 编辑、排序、删除
- 支持模板树预览
- 导入导出升级到新 schema

## 12.5 前端项目工作台
- 顶层空态新增“添加内容块”“从模板引用”
- 顶层底部入口改为三按钮操作条
- 模板引用弹窗改成结构模板弹窗
- 引用时允许选择目标父节点
- 项目编辑器展示引导文案
- 项目编辑器展示 `pre_questions` 并支持保存 `pre_answers`
- 内容块卡片展示引导摘要
- 创建项目弹窗预览真实树结构

## 12.6 Agent 与引用逻辑
- 升级 `manage_architecture` 为树操作模型
- 升级 `architecture_writer` 支持 group/tree
- 升级 `_find_block` 支持 ID / 路径 / 名称
- 升级 `PromptEngine.parse_references()` 的歧义处理
- 升级 `architecture_reader` 避免仅按名称读取

## 12.7 测试
- 为模板校验新增单元测试
- 为模板实例化新增单元测试
- 为兼容旧模板读取新增测试
- 为前端模板树编辑器新增组件测试
- 为项目树入口统一新增交互测试
- 为创建项目模板预览新增测试
- 为 `pre_questions -> pre_answers -> final prompt` 新增端到端测试
- 为依赖映射与重名歧义新增集成测试

## 12.8 迁移与发布
- 编写旧模板到新 schema 的迁移脚本
- 在 staging 用真实模板数据回放验证
- 做一次项目创建与模板引用的回归测试
- 发布时保留回退开关
- 发布后观察模板导入、创建项目、Agent 改结构的错误日志

## 结论
这次需求表面上是三个 UI 问题，实际上是在推动系统从“模板是字段清单”升级为“模板是树结构片段”。

如果只局部修补：

- 可以很快加出一个能用的界面
- 但会继续放大名称依赖、模型分裂、入口不一致的问题

如果按本方案推进：

- 可以把后台模板、项目树、创建项目、模板引用、Agent 改结构逐步收敛到同一套结构语义
- 后续无论是评估模板、行业模板、片段复用，还是更复杂的结构引用，都能站在统一基础上继续演进
