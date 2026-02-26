# 内容块「是否自动生成」功能实现计划

## 一、需求本质分析

### 1.1 需求原文

> 项目后台的内容块模板中，需要为除第一个之外的每个内容块补充"是否自动生成"的选项，并在引用内容块模板时能传递到项目页。

### 1.2 需求拆解

| 要素 | 含义 |
|---|---|
| **内容块模板** | 后台设置中的 `PhaseTemplate`（流程模板）和 `FieldTemplate`（内容块模板），定义了项目创建时的内容块结构。 |
| **除第一个之外** | 模板中第一个内容块通常没有上游依赖，无法被"自动触发"——用户必须手动启动它。因此"自动生成"选项仅对有依赖关系的后续内容块有意义。 |
| **是否自动生成** | 当该内容块的所有依赖都已完成时，系统是否自动启动 AI 生成该块的内容（无需用户手动点击"生成"按钮）。 |
| **引用内容块模板时能传递到项目页** | 当用户创建项目并选择模板时，模板中每个内容块的 `auto_generate` 设置必须完整传递到项目中对应的 `ContentBlock` 实例上。 |

### 1.3 根本性架构分析：`auto_generate` vs `need_review`

当前系统中 `need_review` 字段**混淆了两个正交的概念**：

| 概念 | 当前由谁控制 | 真实含义 |
|---|---|---|
| **自动触发** | `need_review=False` 时才会被 `check_auto_triggers` 扫描到 | 当依赖就绪时，系统是否自动开始生成此内容块？ |
| **人工确认** | `need_review=True` 时生成后状态为 `in_progress`（需人工确认），`False` 直接 `completed` | AI 生成内容后，是否需要人工确认才标记为完成？ |

当前代码中（`backend/api/blocks.py:328-330`）：

```python
# check_auto_triggers 中：
if block.need_review:
    continue  # need_review=True 的块永远不会被自动触发
```

这意味着用户**无法**实现「自动触发生成 + 人工确认内容」的组合——只要想看一眼 AI 生成的内容，就必须放弃自动触发。

**根本解法**：引入独立的 `auto_generate` 字段，将"是否自动触发"与"是否需要人工确认"解耦为两个独立控制维度。

### 1.4 四种组合及其业务含义

引入 `auto_generate` 后，两个布尔字段形成 4 种组合：

| `auto_generate` | `need_review` | 行为 | 典型场景 |
|---|---|---|---|
| `False` | `True` | 手动触发 + 需确认 (**当前默认**) | 核心创作内容，用户全程掌控 |
| `False` | `False` | 手动触发 + 自动完成 | 辅助性内容，不需审核但需用户决定何时生成 |
| `True` | `True` | 自动触发 + 需确认 (**新能力**) | 重要但可预生成的内容：依赖就绪即生成，但人工确认后才流向下游 |
| `True` | `False` | 自动触发 + 自动完成（全自动级联） | 标准化内容，依赖就绪即生成即完成，下游块立即解锁 |

---

## 二、当前代码现状与差距分析

### 2.1 现有数据流

```
PhaseTemplate.phases[].default_fields[]
        │
        │ apply_to_project()
        ▼
ContentBlock (DB) ── need_review 字段
        │
        │ API: check_auto_triggers
        ▼
前端 runAutoTriggerChain() → generateStream()
```

### 2.2 差距清单

| 层级 | 现状 | 缺什么 |
|---|---|---|
| **ContentBlock 模型** | 有 `need_review`，无 `auto_generate` | 需新增 `auto_generate` 列 |
| **数据库** | `content_blocks` 表无 `auto_generate` 列 | 需 ALTER TABLE 迁移 |
| **PhaseTemplate 数据** | `phases[].default_fields[]` 无 `auto_generate` | JSON 结构需扩展 |
| **FieldTemplate 数据** | `fields[]` 无 `auto_generate` | JSON 结构需扩展 |
| **apply_to_project()** | 不传递 `auto_generate` | 需透传到 ContentBlock |
| **_field_template_to_blocks()** | 不传递 `auto_generate` | 同上 |
| **BlockCreate/Update/Response** | 无 `auto_generate` 字段 | 需扩展 Pydantic 模型 |
| **check_auto_triggers()** | 用 `need_review` 做门控 | 需改为 `auto_generate` |
| **前端 ContentBlock 类型** | 无 `auto_generate` | 需扩展 TypeScript 接口 |
| **前端 PhaseTemplate 类型** | `default_fields` 无 `auto_generate` | 需扩展 TypeScript 接口 |
| **模板编辑器 UI** | 有"需要人工确认"，无"是否自动生成" | 需新增切换控件 |
| **项目页 UI** | 只展示/切换 `need_review` | 需展示/切换 `auto_generate` |
| **导出/导入** | 不含 `auto_generate` | 需加入 |
| **项目复制/版本** | 不复制 `auto_generate` | 需加入 |

---

## 三、详细实现计划

### 阶段 1：数据层（ContentBlock 模型 + 数据库迁移）

#### 1.1 ContentBlock 模型新增字段

**文件**：`backend/core/models/content_block.py`

在 `need_review` 字段后新增：

```python
# 自动生成：当所有依赖完成时，是否自动触发 AI 生成
# 与 need_review 正交：auto_generate 控制"是否自动开始"，need_review 控制"生成后是否需人工确认"
auto_generate: Mapped[bool] = mapped_column(Boolean, default=False)
```

更新 `to_tree_dict()` 方法，在返回字典中增加 `"auto_generate": self.auto_generate`。

#### 1.2 数据库迁移

**文件**：`backend/scripts/init_db.py` — `_migrate_add_columns()`

新增迁移条目：

```python
("content_blocks", "auto_generate", "BOOLEAN DEFAULT 0"),
```

遵循项目现有的 ALTER TABLE + try/except 模式（无 Alembic）。

> **现有数据兼容**：默认值为 `False`（0），所有现存内容块保持"手动触发"行为，零破坏性。

---

### 阶段 2：模板数据层（PhaseTemplate + FieldTemplate）

#### 2.1 PhaseTemplate — phases JSON 结构扩展

**文件**：`backend/core/models/phase_template.py`

`DEFAULT_PHASE_TEMPLATE` 中的 `default_fields` 条目保持默认（不指定 `auto_generate` 即默认 `False`）。用户自定义模板的 `default_fields` 中可以包含 `"auto_generate": true`。

**文件**：`backend/api/phase_templates.py`

`PhaseDefinition` Pydantic 模型的 `default_fields` 为 `List[Dict]`，JSON 自由结构，无需修改 Pydantic 定义——`auto_generate` 作为 Dict 中的可选 key 自然传递。

#### 2.2 apply_to_project() — 透传 auto_generate

**文件**：`backend/core/models/phase_template.py` — `apply_to_project()`

在创建 `field_block` 字典时，新增一行：

```python
"auto_generate": field.get("auto_generate", False),
```

**位置**：与现有的 `"need_review": field.get("need_review", True)` 相邻。

#### 2.3 _field_template_to_blocks() — 透传 auto_generate

**文件**：`backend/api/blocks.py` — `_field_template_to_blocks()`

在创建 `block_data` 字典时，新增一行：

```python
"auto_generate": field.get("auto_generate", False),
```

#### 2.4 FieldTemplate 字段定义

**文件**：`backend/core/models/field_template.py`

FieldTemplate 的 `fields` 是 JSON 自由结构。文档注释中补充 `auto_generate` 说明：

```python
#   - auto_generate: 是否自动生成（当依赖就绪时自动触发 AI 生成，默认 False）
```

---

### 阶段 3：API 层

#### 3.1 Pydantic 模型扩展

**文件**：`backend/api/blocks.py`

**BlockCreate**：

```python
auto_generate: bool = False  # 是否自动生成
```

**BlockUpdate**：

```python
auto_generate: Optional[bool] = None
```

**BlockResponse**：

```python
auto_generate: bool = False
```

#### 3.2 _block_to_response() 辅助函数

在返回 `BlockResponse` 时增加：

```python
auto_generate=getattr(block, 'auto_generate', False),
```

使用 `getattr` 兼容可能尚未迁移的旧数据库。

#### 3.3 create_block() 路由

创建 `ContentBlock` 时传入 `auto_generate=data.auto_generate`。

#### 3.4 update_block() 路由

处理 `data.auto_generate is not None` 时更新 `block.auto_generate`。

#### 3.5 check_auto_triggers() — 核心逻辑变更

**文件**：`backend/api/blocks.py`

将门控条件从：

```python
if block.need_review:
    continue
```

改为：

```python
if not getattr(block, 'auto_generate', False):
    continue
```

**`need_review` 在此处不再起门控作用**——它回归其本职：控制生成后的状态（`in_progress` vs `completed`）。生成逻辑（`generate_block_content` / `generate_block_content_stream`）中的 `need_review` 行为完全不变：

```python
# 这行逻辑保持不变：
block.status = "completed" if not block.need_review else "in_progress"
```

这意味着：
- `auto_generate=True, need_review=True`：依赖就绪 → 自动生成 → 状态变为 `in_progress`（需人工确认）→ 下游块等待
- `auto_generate=True, need_review=False`：依赖就绪 → 自动生成 → 状态变为 `completed` → 下游块立即解锁

---

### 阶段 4：前端类型定义

#### 4.1 ContentBlock TypeScript 接口

**文件**：`frontend/lib/api.ts`

在 `ContentBlock` 接口中增加：

```typescript
auto_generate?: boolean;  // 是否自动生成（当依赖就绪时自动触发）
```

#### 4.2 PhaseTemplate TypeScript 接口

**文件**：`frontend/lib/api.ts`

在 `PhaseTemplate.phases[].default_fields[]` 中增加：

```typescript
auto_generate?: boolean;
```

#### 4.3 FieldTemplateFieldItem TypeScript 接口

**文件**：`frontend/lib/api.ts`

在 `FieldTemplateFieldItem` 中增加：

```typescript
auto_generate?: boolean;
```

---

### 阶段 5：前端 — 模板编辑器 UI

#### 5.1 PhaseTemplate 编辑器（流程模板）

**文件**：`frontend/components/settings/phase-templates-section.tsx`

在每个内容块编辑区域的 `need_review` checkbox 旁边，**为非首个内容块**新增"是否自动生成"toggle：

**判定"非首个"的逻辑**：遍历所有 phases 的所有 default_fields，第一个 field 不显示此 toggle。具体实现：用一个全局计数器追踪，或计算当前 field 在全模板中的全局索引是否 > 0。

```tsx
{/* 是否自动生成（仅非首个内容块显示） */}
{globalFieldIndex > 0 && (
  <label className="flex items-center gap-2 text-xs text-zinc-400">
    <input
      type="checkbox"
      checked={field.auto_generate === true}
      onChange={(e) => updateField(pIdx, fIdx, "auto_generate", e.target.checked)}
    />
    自动生成（依赖就绪时自动触发）
  </label>
)}
```

同时更新 `addField` 函数，新建字段时携带 `auto_generate: false`。

#### 5.2 FieldTemplate 编辑器（内容块模板）

**文件**：`frontend/components/settings/templates-section.tsx`

同理，在每个字段编辑区域增加"自动生成"toggle（跳过第一个字段）。

#### 5.3 模板预览

在模板预览区域（`phase-templates-section.tsx` 底部的预览列表），为开启了 `auto_generate` 的内容块增加可视化标记（如 ⚡ 图标）。

---

### 阶段 6：前端 — 项目页 UI

#### 6.1 ContentBlockCard

**文件**：`frontend/components/content-block-card.tsx`

当前已有 `need_review` 的切换按钮（`ShieldCheck` / `Zap` 图标）。需要：

1. **新增 `auto_generate` 切换按钮**：独立于 `need_review`，使用不同图标（如 `Workflow` 或 `Play`），显示为"自动生成"/"手动生成"。

2. **新增 `handleToggleAutoGenerate` 函数**：

```typescript
const handleToggleAutoGenerate = async () => {
  try {
    await blockAPI.update(block.id, { auto_generate: !block.auto_generate });
    onUpdate?.();
  } catch (err) {
    console.error("切换自动生成失败:", err);
  }
};
```

3. **按钮仅对有依赖的 field 类型块显示**：没有依赖的块不可能被自动触发，隐藏此按钮避免用户困惑。

#### 6.2 ContentBlockEditor

**文件**：`frontend/components/content-block-editor.tsx`

在工具栏区域（`need_review` 状态标签旁），增加 `auto_generate` 的状态展示标签：

```tsx
{/* auto_generate 状态 */}
<span className={`flex items-center gap-1 px-2 py-1 text-xs rounded ${
  block.auto_generate 
    ? "bg-blue-600/10 text-blue-400"
    : "bg-zinc-600/10 text-zinc-400"
}`}>
  {block.auto_generate ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
  {block.auto_generate ? "自动生成" : "手动生成"}
</span>
```

---

### 阶段 7：数据完整性 — 导出/导入/复制

#### 7.1 项目导出

**文件**：`backend/api/projects.py` — `export_project()`

无需修改。导出使用 `_ser()` 遍历所有列，`auto_generate` 作为新列会自动被包含。

#### 7.2 项目导入

**文件**：`backend/api/projects.py` — `import_project()`

在 ContentBlock 导入部分增加：

```python
auto_generate=b.get("auto_generate", False),
```

#### 7.3 项目复制

**文件**：`backend/api/projects.py` — `duplicate_project()`

在复制 ContentBlock 时增加：

```python
auto_generate=old_block.auto_generate if hasattr(old_block, 'auto_generate') else False,
```

#### 7.4 项目版本

**文件**：`backend/api/projects.py` — `create_new_version()`

同上，复制 ContentBlock 时传入 `auto_generate`。

#### 7.5 内容块复制

**文件**：`backend/api/blocks.py` — `duplicate_block()`

在复制块时增加：

```python
auto_generate=getattr(node, 'auto_generate', False),
```

---

### 阶段 8：Agent 工具层兼容

#### 8.1 _set_content_status()

**文件**：`backend/core/agent_tools.py`

此函数根据 `need_review` 设置内容块状态。**无需修改**——`auto_generate` 不影响生成后的状态逻辑。

#### 8.2 Agent 生成工具

Agent 通过 `generate_field_content` / `rewrite_field` 等工具直接生成内容，不经过 `check_auto_triggers`，因此 `auto_generate` 对 Agent 行为无影响。无需修改。

---

## 四、修改文件清单

| 文件 | 修改类型 | 涉及内容 |
|---|---|---|
| `backend/core/models/content_block.py` | 模型字段 | 新增 `auto_generate` 列 + `to_tree_dict()` |
| `backend/core/models/phase_template.py` | 透传字段 | `apply_to_project()` 增加 `auto_generate` |
| `backend/core/models/field_template.py` | 文档注释 | 字段定义说明补充 `auto_generate` |
| `backend/scripts/init_db.py` | 迁移 | `_migrate_add_columns()` 新增迁移条目 |
| `backend/api/blocks.py` | API 全链路 | Pydantic 模型 + 创建/更新/响应 + `check_auto_triggers` 核心逻辑 + `_field_template_to_blocks` + `duplicate_block` |
| `backend/api/projects.py` | 导出/导入/复制/版本 | ContentBlock 的 `auto_generate` 透传 |
| `frontend/lib/api.ts` | TypeScript 类型 | `ContentBlock` + `PhaseTemplate` + `FieldTemplateFieldItem` |
| `frontend/components/settings/phase-templates-section.tsx` | 模板编辑器 UI | "是否自动生成" toggle + 模板预览标记 |
| `frontend/components/settings/templates-section.tsx` | 模板编辑器 UI | "是否自动生成" toggle |
| `frontend/components/content-block-card.tsx` | 项目页 UI | `auto_generate` 切换按钮 |
| `frontend/components/content-block-editor.tsx` | 项目页 UI | `auto_generate` 状态展示 |

---

## 五、实施顺序

严格按依赖关系排列，避免编译/运行错误：

1. **数据层**：`content_block.py` 模型 → `init_db.py` 迁移
2. **模板透传**：`phase_template.py` → `blocks.py`（`_field_template_to_blocks`）→ `field_template.py` 文档
3. **API 层**：`blocks.py`（Pydantic + CRUD + `check_auto_triggers`）
4. **数据完整性**：`projects.py`（导出/导入/复制/版本）+ `blocks.py`（`duplicate_block`）
5. **前端类型**：`api.ts`
6. **前端 UI**：`phase-templates-section.tsx` → `templates-section.tsx` → `content-block-card.tsx` → `content-block-editor.tsx`

---

## 六、测试验证点

| # | 验证场景 | 预期结果 |
|---|---|---|
| 1 | 创建模板，第一个内容块不显示"自动生成"选项 | 只有后续内容块显示 toggle |
| 2 | 模板中将第二个内容块设为 `auto_generate=True`，创建项目 | 对应 ContentBlock 的 `auto_generate=True` |
| 3 | `auto_generate=True, need_review=False`：确认第一个块后 | 第二个块自动开始生成 → 生成完成后状态直接 `completed` → 下游块继续触发 |
| 4 | `auto_generate=True, need_review=True`：确认第一个块后 | 第二个块自动开始生成 → 生成完成后状态为 `in_progress`（需人工确认）→ 下游块等待确认 |
| 5 | `auto_generate=False, need_review=False`：确认第一个块后 | 第二个块不自动生成，用户手动点击生成 → 生成后直接 `completed` |
| 6 | 在项目页手动切换 `auto_generate` | 切换成功，下次依赖变更时按新设置触发/不触发 |
| 7 | 导出含 `auto_generate` 块的项目 → 导入 | 导入后 `auto_generate` 值保持一致 |
| 8 | 复制项目 | 所有块的 `auto_generate` 值被复制 |
| 9 | 模板中不设 `auto_generate`（旧模板）→ 应用到项目 | 所有块默认 `auto_generate=False`，行为与以前完全一致 |

---

## 七、向后兼容性保证

1. **默认值 `False`**：所有现存内容块、模板中未指定 `auto_generate` 的字段均默认为 `False`，行为与当前完全一致。
2. **`need_review` 保持不变**：`need_review` 继续控制生成后状态（`in_progress` vs `completed`），不受 `auto_generate` 影响。
3. **`getattr` 兼容**：API 层使用 `getattr(block, 'auto_generate', False)`，在数据库迁移尚未执行时也不会报错。
4. **旧模板自动兼容**：`field.get("auto_generate", False)` 确保旧模板 JSON 中无此字段时使用默认值。
