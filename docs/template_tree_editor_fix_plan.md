# 模板树编辑器 UI 修正方案

> 创建时间: 2026-03-06
> 背景: `template-tree-editor.tsx` 上一轮实现存在 5 个根本性理解偏差，本文档记录问题根因和修正方案。

---

## 问题清单

### 问题 1: `guidance_input` / `guidance_output` 理解错误

**根因**: 设计文档 3.4 节建议"每个字段后补充一句引导"，被错误理解为"在 TemplateNode 和 ContentBlock 上新增两个可编辑的元数据字段"。
实际需求是：模板编辑表单里的每个字段标题下方加一行静态帮助文案（小字），告诉用户这个表单字段是干什么的。这是纯 UI 层的表单体验改善，不需要任何数据模型变更。

**影响面**:
- `frontend/components/settings/template-tree-editor.tsx` — 有两个 textarea（输入指引 / 输出指引）
- `frontend/components/content-block-editor.tsx` — 提示词弹窗里有两个 textarea + 对应 state + 保存调用
- `frontend/components/content-block-card.tsx` — 同上
- `frontend/lib/api.ts` — `TemplateNode` 和 `ContentBlock` 接口里有 `guidance_input` / `guidance_output`
- `backend/core/prompt_engine.py` — `get_field_generation_prompt` 注入了这两个字段到 LLM 提示词
- `backend/core/models/content_block.py` — ORM 模型有两列
- `backend/core/database.py` — 自愈补列逻辑
- `backend/scripts/init_db.py` — 初始化补列
- `backend/api/blocks.py` — BlockCreate / BlockUpdate / _block_to_response 里有
- `backend/api/projects.py` — 项目复制 / 导入时带上了这两个字段
- `backend/core/template_schema.py` — 模板归一化 / 实例化时带上了
- `backend/core/agent_tools.py` — add_node 时带上了
- `backend/tests/test_prompt_engine.py` — 测试里有

**修正方案**:

| 层 | 动作 | 说明 |
|---|---|---|
| 模板编辑器 UI | 删除两个 textarea | 不需要用户填写 |
| 模板编辑器 UI | 给每个 FormField 加 `hint` 属性 | 利用现有 `FormField` 组件的 `hint` 参数，加一行小字说明 |
| content-block-editor | 删除 guidance state、textarea、保存调用 | 这两个字段从一开始就不该存在 |
| content-block-card | 同上 | 同上 |
| prompt_engine | 删除 guidance 注入逻辑 | 没有用户填写来源，注入空字符串无意义 |
| 前端 api.ts | 从 `TemplateNode` / `ContentBlock` 接口中移除 | 前端不需要读写这两个字段 |
| 后端 ORM / DB / API | **保留不动** | 列已存在于数据库中，默认空字符串，无害；强行删列反而会破坏迁移链路 |
| template_schema | **保留** | 字段在归一化和实例化时传空字符串，无害 |

### 问题 2: 缺少折叠功能

**根因**: `TemplateNode` 已有 `is_collapsed` 字段，但模板树编辑器没有实现折叠/展开 UI。当模板节点较多时，编辑体验很差。

**修正方案**:
- 在 `NodeEditor` 的标题栏加一个折叠/展开切换按钮（ChevronRight / ChevronDown 图标）
- 折叠时隐藏所有表单字段和子节点列表，只保留标题栏（名称 + 类型 + 操作按钮）
- 折叠状态写回 `is_collapsed`，保存到模板数据中

### 问题 3: "方案"类型不应暴露

**根因**: 后端 `BLOCK_TYPES` 定义了 `proposal`（方案）用于内涵设计的多方案场景，属于内部使用的语义。模板编辑器不应向用户暴露这个类型。

**修正方案**:
- 从 block_type 下拉菜单移除 `<option value="proposal">方案</option>`
- 删除 `+ 子方案` 按钮
- `isContentNode` 判断只保留 `field`，不再包含 `proposal`

### 问题 4: "特殊处理器"不应暴露

**根因**: `special_handler` 是后端用来识别特殊阶段行为的内部字段（如 `intent` → 意图分析三问、`research` → 调研流程）。普通用户在编辑模板时不需要也不应该看到这个字段。

**修正方案**:
- 从 `NodeEditor` 中移除"特殊处理器"输入框
- `createTemplateNode()` 仍保留 `special_handler: null` 默认值（后端兼容）

### 问题 5: "模型覆盖" → "模型"

**根因**: 内部字段名 `model_override` 被直译为"模型覆盖"显示在 UI 上。用户只需要知道"这个节点用什么模型"，标签应该叫"模型"。

**修正方案**:
- 将 FormField label 从 `"模型覆盖"` 改为 `"模型"`

---

## 修改文件清单

| 文件 | 改动类型 |
|---|---|
| `frontend/components/settings/template-tree-editor.tsx` | 主要修改：折叠、移除方案/特殊处理器/guidance、改标签、加 hint |
| `frontend/components/content-block-editor.tsx` | 移除 guidance state/textarea/保存调用 |
| `frontend/components/content-block-card.tsx` | 移除 guidance state/textarea/保存调用 |
| `frontend/lib/api.ts` | 从 TemplateNode / ContentBlock 接口移除 guidance 字段 |
| `backend/core/prompt_engine.py` | 移除 guidance 注入 |

**不修改**（保留后端兼容）:
- `backend/core/models/content_block.py` — ORM 列保留
- `backend/core/database.py` — 自愈列保留
- `backend/scripts/init_db.py` — 初始化列保留
- `backend/api/blocks.py` — API 字段保留（前端不传就是空字符串）
- `backend/api/projects.py` — 复制时带空字符串，无害
- `backend/core/template_schema.py` — 归一化时带空字符串，无害
- `backend/core/agent_tools.py` — add_node 时带空字符串，无害

---

## 每个表单字段的帮助文案

| 字段 | 帮助文案 (hint) |
|---|---|
| 节点名称 | （集成在 placeholder 里，不用 hint） |
| AI 提示词 | 生成此内容块时给 AI 的指令，会与项目上下文一起发送 |
| 预置内容 | 应用模板后预填到内容块的初始内容 |
| 生成前提问 | 生成前需要用户回答的问题，答案会注入 AI 提示词 |
| 依赖节点 | 生成此节点前需要先完成的其他节点 |
| 模型 | 此节点使用的 AI 模型，留空则使用项目默认模型 |
| 需要人工确认 | 勾选后 AI 生成完毕仍需用户确认才算完成 |
| 自动生成 | 勾选后当依赖就绪时自动触发 AI 生成 |
