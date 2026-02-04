# 撤回逻辑与依赖引用完善方案

> 创建时间: 2026-02-04
> 状态: ✅ 已完成

## 问题分析

### 问题 1: 删除后无法撤回

**现状**：
- `BlockTree` 组件中 `handleDelete` 直接调用 `blockAPI.delete()`
- 后端 `delete_block` 直接删除记录，级联删除子块
- 没有任何历史记录或撤回机制

**用户痛点**：
- 误删除后数据丢失，无法恢复
- 特别是删除阶段时，会级联删除所有子字段

### 问题 2: 新增字段无法引用特殊字段

**现状**：
```typescript
// content-block-editor.tsx 第 52-56 行
const availableDependencies = allBlocks.filter(b => 
  b.id !== block.id && 
  b.block_type === "field" &&  // ← 只允许 field 类型
  b.parent_id !== block.id
);
```

**问题**：
- 消费者调研报告存储在 `block_type="phase"` + `special_handler="research"` 的块中
- 意图分析结果存储在 `block_type="phase"` + `special_handler="intent"` 的块中
- 当前过滤条件只允许选择 `field` 类型，无法选择这些特殊阶段

---

## 解决方案

### 方案 1: 撤回逻辑

采用**软删除 + 操作历史栈**的混合方案：

#### 1.1 后端改动

**1.1.1 添加 `deleted_at` 字段（软删除）**

```python
# content_block.py
class ContentBlock(BaseModel):
    # ... 现有字段 ...
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

**1.1.2 新增 BlockHistory 模型**

```python
# block_history.py
class BlockHistory(BaseModel):
    """
    内容块操作历史，用于撤回/重做
    """
    __tablename__ = "block_history"
    
    project_id: str           # 所属项目
    action: str               # 操作类型: create/update/delete/move
    block_id: str             # 操作的块 ID
    block_snapshot: dict      # 操作前的完整快照（JSON）
    children_snapshot: list   # 子块快照（删除时保存）
    created_at: datetime      # 操作时间
```

**1.1.3 修改删除 API**

```python
# blocks.py
@router.delete("/{block_id}")
def delete_block(block_id: str, db: Session):
    block = db.query(ContentBlock).filter(ContentBlock.id == block_id).first()
    
    # 1. 保存快照到历史表
    snapshot = block.to_tree_dict()
    history = BlockHistory(
        project_id=block.project_id,
        action="delete",
        block_id=block.id,
        block_snapshot=snapshot,
        children_snapshot=[c.to_tree_dict() for c in block.get_all_descendants()],
    )
    db.add(history)
    
    # 2. 软删除（设置 deleted_at）
    block.deleted_at = datetime.utcnow()
    for child in block.get_all_descendants():
        child.deleted_at = datetime.utcnow()
    
    db.commit()
    return {"message": "删除成功", "history_id": history.id}
```

**1.1.4 新增撤回 API**

```python
@router.post("/undo/{history_id}")
def undo_operation(history_id: str, db: Session):
    history = db.query(BlockHistory).filter(BlockHistory.id == history_id).first()
    
    if history.action == "delete":
        # 恢复主块
        block = db.query(ContentBlock).filter(ContentBlock.id == history.block_id).first()
        block.deleted_at = None
        
        # 恢复子块
        for child_snapshot in history.children_snapshot:
            child = db.query(ContentBlock).filter(ContentBlock.id == child_snapshot["id"]).first()
            if child:
                child.deleted_at = None
    
    # 标记历史已撤回
    history.undone = True
    db.commit()
    
    return {"message": "撤回成功"}
```

**1.1.5 修改查询，排除已删除**

```python
# 所有查询加上 filter
.filter(ContentBlock.deleted_at == None)
```

#### 1.2 前端改动

**1.2.1 添加撤回按钮和操作历史栈**

```typescript
// block-tree.tsx
const [undoStack, setUndoStack] = useState<string[]>([]);  // history_id 列表

const handleDelete = async () => {
    const result = await blockAPI.delete(block.id);
    setUndoStack(prev => [...prev, result.history_id]);
    onBlocksChange?.();
};

const handleUndo = async () => {
    if (undoStack.length === 0) return;
    const historyId = undoStack[undoStack.length - 1];
    await blockAPI.undo(historyId);
    setUndoStack(prev => prev.slice(0, -1));
    onBlocksChange?.();
};
```

**1.2.2 显示撤回按钮**

```tsx
{undoStack.length > 0 && (
    <button onClick={handleUndo} className="...">
        <Undo className="w-4 h-4" />
        撤回
    </button>
)}
```

---

### 方案 2: 依赖引用特殊字段

#### 2.1 修改过滤逻辑

```typescript
// content-block-editor.tsx
const availableDependencies = allBlocks.filter(b => {
  // 排除自己
  if (b.id === block.id) return false;
  // 排除自己的子节点
  if (b.parent_id === block.id) return false;
  
  // 允许选择的类型：
  // 1. 所有 field 类型
  // 2. 有 special_handler 的 phase 类型（意图分析、消费者调研等）
  if (b.block_type === "field") return true;
  if (b.block_type === "phase" && b.special_handler) return true;
  
  return false;
});
```

#### 2.2 改进依赖选择 UI

将依赖按阶段分组显示，更清晰：

```tsx
// 依赖选择弹窗改进
<div className="space-y-4">
    {/* 特殊阶段区域 */}
    <div>
        <h4 className="text-sm font-medium text-zinc-400 mb-2">📌 特殊阶段</h4>
        {specialDependencies.map(dep => (
            <DependencyItem key={dep.id} dep={dep} ... />
        ))}
    </div>
    
    {/* 按阶段分组的字段 */}
    {groupedByPhase.map(group => (
        <div key={group.phase}>
            <h4 className="text-sm font-medium text-zinc-400 mb-2">
                📁 {group.phaseName}
            </h4>
            {group.fields.map(dep => (
                <DependencyItem key={dep.id} dep={dep} ... />
            ))}
        </div>
    ))}
</div>
```

---

## 实施 TODO

### Phase 1: 撤回逻辑

- [x] **1.1** 后端：添加 `deleted_at` 字段到 `ContentBlock` 模型
- [x] **1.2** 后端：创建 `BlockHistory` 模型
- [x] **1.3** 后端：创建数据库迁移脚本 (`scripts/migrate_add_undo.py`)
- [x] **1.4** 后端：修改 `delete_block` API，实现软删除 + 保存历史
- [x] **1.5** 后端：新增 `/undo/{history_id}` API
- [x] **1.6** 后端：修改所有查询，过滤已删除记录
- [x] **1.7** 前端：`BlockTree` 添加 `undoStack` 状态
- [x] **1.8** 前端：添加撤回按钮（删除后显示黄色提示条）
- [x] **1.9** 前端：`lib/api.ts` 添加 `blockAPI.undo()` 和 `blockAPI.getUndoHistory()`
- [x] **1.10** 测试：删除 → 撤回 → 验证恢复

### Phase 2: 依赖引用改进

- [x] **2.1** 前端：修改 `availableDependencies` 过滤逻辑（允许 phase + special_handler）
- [x] **2.2** 前端：依赖选择 UI 分组显示（特殊阶段 / 普通字段）
- [x] **2.3** 后端：验证依赖生成时正确获取特殊阶段内容
- [x] **2.4** 测试：新建字段 → 添加消费者调研依赖 → 生成验证

---

## 验收标准

### 撤回功能

1. ✅ 删除字段后，显示「撤回」按钮
2. ✅ 点击撤回，字段及其子块完整恢复
3. ✅ 撤回后按钮消失，可继续删除
4. ✅ 刷新页面后，删除的内容不显示（真的删了）
5. ✅ 软删除记录在 30 天后物理清理（可选）

### 依赖引用

1. ✅ 依赖选择弹窗显示「消费者调研报告」「意图分析」等特殊阶段
2. ✅ 选择后正确保存到 `depends_on`
3. ✅ 生成时正确注入依赖内容
4. ✅ 依赖状态正确显示（已完成/未完成）

---

## 风险与注意事项

1. **软删除查询性能**：需要确保所有查询都加上 `deleted_at == None` 过滤
2. **历史记录膨胀**：可能需要定期清理过期历史
3. **级联恢复复杂度**：恢复时需要正确重建父子关系
4. **依赖循环检测**：添加依赖时需检测是否形成循环
