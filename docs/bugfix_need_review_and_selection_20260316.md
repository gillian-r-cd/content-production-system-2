# Bug Fix 方案：need_review 状态同步 & 文本选中交互修复

**日期**: 2026-03-16
**优先级**: P1（影响核心交互体验）

---

## Bug 1：设为"无需确认"后内容块状态不自动变为已确认

### 第一性原理分析

内容块的语义模型：
- `need_review = true`：内容生成后需要人工过眼确认，才算"完成"
- `need_review = false`：内容生成即完成，不需要人工介入
- `status = "completed"`：内容块已完成（无论是人工确认还是自动完成）
- `status = "in_progress"`：内容已生成，等待人工确认

推论：当 `need_review` 从 `true` → `false` 时，"需要确认"这个条件消失了。如果此时内容已存在，那该内容块在逻辑上应立即处于"已完成"状态，不需要任何额外操作。

**当前行为**：切换 `need_review` 只更新该字段，不触发状态联动，导致块停留在 `in_progress`，确认按钮消失（因为 `need_review=false`），但状态又不是 `completed`，形成死局。

### 根本原因

`backend/api/blocks.py` 的 `update_block()` 函数中，状态自动计算逻辑**只在 content 变更时触发**（第 591-595 行），`need_review` 字段更新（第 617-618 行）没有相应的状态联动：

```python
# 现有代码：need_review 更新时没有状态联动
if data.need_review is not None:
    block.need_review = data.need_review
    # ← 缺少：状态同步逻辑
```

### 修复方案

在 `need_review` 更新后，立即根据新值和内容是否存在同步 `status`：

```python
if data.need_review is not None:
    block.need_review = data.need_review
    # 状态联动：仅在没有显式传 status 且内容存在时生效
    if data.status is None and (block.content or "").strip():
        if not data.need_review:
            # need_review → false：有内容即已确认
            block.status = "completed"
        elif data.need_review and block.status == "completed":
            # need_review → true：已完成的块重新需要确认
            block.status = "in_progress"
```

**修改文件**：`backend/api/blocks.py`，第 617-618 行附近

**影响范围**：仅 `PUT /api/blocks/{block_id}` 中 `need_review` 字段的处理，不触碰内容写入、确认 API、数据库结构。

---

## Bug 2：内容块内选中文字后，点击同块其他位置无法清除选中

### 第一性原理分析

文本选中的本质是浏览器维护的一个 `Selection` 对象，清除它需要调用 `window.getSelection().removeAllRanges()`（或等价的 CSS Highlights API 清理）。

用户期望的交互模型：
- 点击 = 清除选中（如果此时已有选中）
- 拖动 = 新建选中

**当前行为死区分析**：
- `mousedown` 在内容区内 → `handleMouseDown` 判断 `contentDisplayRef.contains(target)` → return（不清除）
- `mouseup` 在内容区内 → `handleContentMouseUp` → `selection.isCollapsed` 为 true（仅点击无拖动）→ return（不清除）

两层都放行，导致"内容区内的点击"对选中状态完全无效。

### 根本原因

`handleContentMouseUp`（`content-block-editor.tsx` 第 676 行）在检测到无新选中时直接 `return`，注释写的是"避免干扰已有的 inline edit 状态"。但这恰恰造成了 bug：用户在内容区点击时，既不会产生新选中，也不会清除旧选中。

```typescript
// 现有代码：isCollapsed 时直接返回，不清除旧状态
if (!selection || selection.isCollapsed || !selection.toString().trim()) {
  // 没有选中文本时不清空（避免干扰已有的 inline edit 状态）
  return;  // ← 这里是 bug 的根源
}
```

注释中的"干扰"场景（用户点击 toolbar 按钮时 mouseup 触发）**实际上不会发生**：toolbar 是绝对定位浮层，不在 `contentDisplayRef` 内，点击 toolbar 时 `mouseup` 不会冒泡到内容区的 `onMouseUp`。所以移除这个保护是安全的。

### 修复方案

在 `handleContentMouseUp` 中，当检测到无新选中（isCollapsed）时，主动清除旧的选中状态：

```typescript
const handleContentMouseUp = useCallback(() => {
  setTimeout(() => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.toString().trim()) {
      // 用户只是点击（没有拖拽产生新选中）→ 清除旧的选中状态
      if (selectedText || inlineEditResult) {
        setSelectedText("");
        setToolbarPosition(null);
        setInlineEditResult(null);
        setShowCustomInput(false);
        setCustomInstruction("");
        clearSelectionHighlight();
        window.getSelection()?.removeAllRanges();
      }
      return;
    }
    // ... 下面是新选中的处理逻辑（不变）
  }, 10);
}, [selectedText, inlineEditResult, applySelectionHighlight, clearSelectionHighlight]);
```

**修改文件**：`frontend/components/content-block-editor.tsx`，`handleContentMouseUp` 函数

**影响范围**：只影响内容展示区域的点击行为。toolbar 点击、agent 区点击均不受影响（路径不变）。

---

## 修改清单

| 文件 | 位置 | 修改类型 |
|------|------|----------|
| `backend/api/blocks.py` | `update_block()`，need_review 赋值后 | 新增 4 行状态联动逻辑 |
| `frontend/components/content-block-editor.tsx` | `handleContentMouseUp`，isCollapsed 分支 | 将 return 改为先清除再 return |

无数据库变更，无 API 签名变更，无新增依赖。
