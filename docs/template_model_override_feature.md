# 模板模型选择功能方案
# 创建时间: 2026-02-27
# 功能: 内容块模板中为每个内容块预设模型，引用模板时透传到项目
# 关联: phase_template.py, field_template.py, blocks.py, projects.py, api.ts,
#       templates-section.tsx, phase-templates-section.tsx

---

## 一、需求本质

用户希望在 **内容块模板**（FieldTemplate + PhaseTemplate）中为每个内容块预设一个 LLM 模型，
应用模板创建项目时把这个模型设置带到项目里的 `ContentBlock.model_override`，
用户在项目中还可以按需修改。

## 二、当前架构状况

### 2.1 已有基础设施（无需改动）

| 组件 | 状态 | 说明 |
|------|------|------|
| `ContentBlock.model_override` | 已存在 | `VARCHAR(100)`, nullable, 数据库列已迁移 |
| `resolve_model()` 覆盖链 | 已完整 | `block.model_override → AgentSettings → .env` |
| 前端项目页模型选择器 | 已有 | `content-block-card.tsx`, `content-block-editor.tsx` |
| `modelsAPI.list()` | 已有 | 返回可用模型列表 |
| `blockAPI.update({ model_override })` | 已有 | 更新接口 |
| `ModelInfo` 类型 | 已有 | `{ id, provider, name, tier }` |
| `export_project()` | 自动包含 | `_ser()` 遍历所有列 |

### 2.2 缺失部分

#### 后端 — 模板透传缺失

| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| 1 | `phase_template.py` `apply_to_project()` | 不透传 `model_override` | 加 `"model_override": field.get("model_override")` |
| 2 | `blocks.py` `_field_template_to_blocks()` | 不透传 `model_override` | 同上 |

#### 后端 — BlockCreate / create_block 缺失

| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| 3 | `blocks.py` `BlockCreate` | 缺少 `model_override` 字段 | 加 `model_override: Optional[str] = None` |
| 4 | `blocks.py` `create_block()` | 创建时不传 `model_override` | 加 `model_override=data.model_override` |

#### 后端 — 已有 bug（复制/导入遗漏 model_override）

| # | 位置 | 问题 |
|---|------|------|
| 5 | `projects.py` `duplicate_project()` | 不复制 `model_override` |
| 6 | `projects.py` `create_new_version()` | 不复制 `model_override` |
| 7 | `projects.py` `import_project()` | 不导入 `model_override` |
| 8 | `blocks.py` `duplicate_block()` | 不复制 `model_override` |

#### 后端 — 文档注释

| # | 位置 | 问题 |
|---|------|------|
| 9 | `field_template.py` 文档注释 | 缺少 `model_override` 描述 |

#### 前端 — 类型 + UI

| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| 10 | `api.ts` `PhaseTemplate` 类型 | `default_fields` 无显式 `model_override` | 加可选字段 |
| 11 | `templates-section.tsx` | 模板编辑器无模型选择 UI | 加模型选择下拉 |
| 12 | `phase-templates-section.tsx` | 模板编辑器无模型选择 UI | 加模型选择下拉 |

## 三、实施顺序

```
阶段 1: 后端模板透传
  1.1 phase_template.py — apply_to_project() 加 model_override
  1.2 blocks.py — _field_template_to_blocks() 加 model_override

阶段 2: 后端 BlockCreate + create_block
  2.1 blocks.py — BlockCreate 加 model_override
  2.2 blocks.py — create_block() 传 model_override

阶段 3: 后端 bug 修复（复制/导入遗漏）
  3.1 projects.py — duplicate_project() 加 model_override
  3.2 projects.py — create_new_version() 加 model_override
  3.3 projects.py — import_project() 加 model_override
  3.4 blocks.py — duplicate_block() 加 model_override

阶段 4: 后端文档注释
  4.1 field_template.py — 文档注释补充 model_override

阶段 5: 前端类型
  5.1 api.ts — PhaseTemplate.default_fields 加 model_override
  5.2 templates-section.tsx — TemplateField 接口加 model_override

阶段 6: 前端 UI
  6.1 templates-section.tsx — 加载 modelsAPI + 模型选择下拉
  6.2 phase-templates-section.tsx — 加载 modelsAPI + 模型选择下拉

阶段 7: 验证
  7.1 后端启动检查
  7.2 前端编译检查
```

## 四、不需要改动的部分

- `ContentBlock` SQLAlchemy 模型 — 字段已存在
- 数据库迁移 — 列已存在
- `resolve_model()` — 覆盖链已完整
- 前端项目页模型选择器 — 已有
- `blockAPI.create / blockAPI.update` 前端类型 — `model_override` 已有
- `architecture_reader.py` — 不需要模型信息

## 五、设计原则

1. **零新增依赖，零新增数据表，零新增 API 端点** — 全部在已有基础设施上补齐管道
2. **模板只是"建议"** — 模板中的 model_override 在应用时写入 ContentBlock，用户随后可自由修改
3. **向后兼容** — 模板中无 model_override 时，ContentBlock 默认 None，走 resolve_model 覆盖链
4. **之前的设计文档（model_selection_feature.md）说"模板不设模型字段"** — 该约束被本需求推翻，但不影响覆盖链架构
