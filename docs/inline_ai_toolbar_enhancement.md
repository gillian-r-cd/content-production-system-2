# Inline AI 工具栏增强 + 编辑交互优化

> 创建时间：20260308
>
> 涉及组件：`content-block-editor.tsx`, `content-block-card.tsx`, `agent-panel.tsx`, `workspace/page.tsx`, `backend/api/agent.py`

## 一、背景

当前 `content-block-editor.tsx` 已实现 M4 Inline AI 编辑：选中文字 → 浮动工具栏（改写/扩展/精简）→ diff 卡片 → 接受/拒绝。本次在此基础上做 5 项改动，无新增模式或技术栈。

---

## 二、改动清单

| # | 改动 | 涉及文件 | 复杂度 |
|---|------|----------|--------|
| A | 对话改内容：工具栏新增自由文本输入，用户描述修改方向后出 diff 卡片 | `content-block-editor.tsx`, `backend/api/agent.py` | 中 |
| B | 添加到 Agent Panel：工具栏新增「问问 Agent」，选中内容作为引用上下文叠加到对话 | `content-block-editor.tsx`, `agent-panel.tsx`, `workspace/page.tsx` | 中 |
| C | 复制/编辑按钮 sticky：内容超一屏滚动时按钮钉在右上角 | `content-block-editor.tsx` | 小 |
| D | 移除内容区域单击进入编辑：仅保留「编辑」按钮和空内容区域的点击入口 | `content-block-editor.tsx`, `content-block-card.tsx` | 小 |
| E | 生成前提问默认收起 | `content-block-card.tsx` | 小 |

---

## 三、各改动详细方案

### A. 对话改内容

**用户流程：** 选中文字 → 工具栏出现 → 点击「对话改」按钮 → 工具栏下方展开一个小输入框 → 用户输入修改方向（如"改成更口语化"）→ 回车/点击提交 → loading → 出现与改写/扩展/精简完全相同的 diff 卡片 → 接受/拒绝。

**前端改动（`content-block-editor.tsx`）：**

1. 新增状态：
   - `showCustomInput: boolean` — 控制自由输入框的显示
   - `customInstruction: string` — 用户输入的修改方向

2. 工具栏（状态 3 区域）中，在「精简」按钮后增加分隔符 + 「对话改」按钮：
   - 点击后 `setShowCustomInput(true)`，工具栏下方展开输入框
   - 输入框内回车或点击提交 → 调用 `handleInlineEdit("custom")`，传入 `customInstruction`
   - 提交后清空输入框，收起输入态

3. `handleInlineEdit` 函数扩展：当 `operation === "custom"` 时，请求体增加 `custom_instruction` 字段。

**后端改动（`backend/api/agent.py`）：**

1. `InlineEditRequest` 新增可选字段：`custom_instruction: str = ""`
2. `/inline-edit` 端点：当 `operation === "custom"` 时，使用 `custom_instruction` 作为指令（替代预设的 `operation_prompts`），其余流程（LLM 调用、diff 生成、返回结构）完全复用。

**不做的事：** 不新建 API 端点，不引入新的数据结构，复用现有 `InlineEditResponse`。

---

### B. 添加到 Agent Panel

**核心原则：选中内容的引用是叠加在原有对话上下文之上的附加信息，不替换对话历史、不替换 @ 引用、不替换追问上下文。**

**用户流程：** 选中文字 → 工具栏出现 → 点击「问问 Agent」 → 右侧 Agent Panel 输入框上方出现引用标签卡片（显示内容块名称 + 选中片段摘要 + ×关闭按钮）→ 用户在输入框中输入问题 → 发送 → 请求体中额外携带 `{ block_id, block_name, selected_text }` → 后端在构建 prompt 时将完整内容块内容 + 选中片段作为附加上下文注入 → AI 回答时知道整体语境和局部焦点 → 发送后引用卡片消耗掉、自动消失。

**数据通道（自下而上）：**

```
ContentBlockEditor                       → onSendSelectionToAgent({ blockId, blockName, selectedText })
  ↓ prop callback
ContentPanel                             → 透传
  ↓ prop callback
WorkspacePage                            → setState: pendingAgentSelection
  ↓ prop
AgentPanel (externalSelection prop)      → 显示引用卡片 + 发送时注入 metadata
```

**前端改动：**

1. **新增类型**（`lib/api.ts` 或行内定义）：
   ```ts
   interface AgentSelectionRef {
     blockId: string;
     blockName: string;
     selectedText: string;
   }
   ```

2. **`content-block-editor.tsx`**：
   - `ContentBlockEditorProps` 新增 `onSendSelectionToAgent?: (ref: AgentSelectionRef) => void`
   - 工具栏（状态 3）增加「问问 Agent」按钮，点击后调用 `onSendSelectionToAgent({ blockId: block.id, blockName: block.name, selectedText })`，然后清除选中态

3. **`content-panel.tsx`**：透传 `onSendSelectionToAgent` prop

4. **`workspace/page.tsx`**：
   - 新增状态 `pendingAgentSelection: AgentSelectionRef | null`
   - 传给 `ContentPanel` 的回调：`onSendSelectionToAgent={setPendingAgentSelection}`
   - 传给 `AgentPanel` 的 prop：`externalSelection={pendingAgentSelection}`, `onExternalSelectionConsumed={() => setPendingAgentSelection(null)}`

5. **`agent-panel.tsx`**：
   - `AgentPanelProps` 新增 `externalSelection?: AgentSelectionRef | null`, `onExternalSelectionConsumed?: () => void`
   - 新增内部状态 `selectionRef: AgentSelectionRef | null`
   - 当 `externalSelection` 变化时，`setSelectionRef(externalSelection)`, 然后调用 `onExternalSelectionConsumed()`
   - 输入框上方渲染引用标签卡片（与追问标签条 `followUpTarget` 同级并列，视觉风格一致）：
     ```
     📎 引用「{blockName}」: "{selectedText 截断至50字}..."  [×]
     ```
   - `handleSend` 中：如果 `selectionRef` 存在，将其序列化到请求体的 `metadata.selection_context` 中，发送后 `setSelectionRef(null)`
   - **与已有上下文的关系：** `selectionRef` 与 `followUpTarget`、`references`（@ 引用）、`conversation_id`（对话历史）互不干扰，全部叠加。请求体中同时存在多种上下文是正常的。

**后端改动（`backend/api/agent.py` 或 `core/orchestrator.py`）：**

1. 消息处理时检测 `metadata.selection_context`，如果存在：
   - 根据 `block_id` 从数据库读取完整内容块内容
   - 在 system prompt 或 user message 中注入附加上下文段落：
     ```
     [引用上下文]
     用户在内容块「{block_name}」中选中了以下内容：
     ---
     {selected_text}
     ---
     该内容块完整内容：
     {block_full_content}
     ```
2. 其余对话流程（历史消息加载、工具调用、流式输出）完全不变

**不做的事：** 不新建会话，不改变消息格式，不影响已有的 @ 引用和追问机制。

---

### C. 复制/编辑按钮 sticky 定位

**问题：** `content-block-editor.tsx` 中内容展示区域的「复制」「编辑」按钮使用 `absolute top-2 right-2`，当内容超过一屏、用户向下滚动时，按钮随内容滚走、不可见。

**方案：** 将按钮容器从 `absolute` 改为 `sticky`，使其在滚动时钉在内容区域视口的右上角。

**具体改法（`content-block-editor.tsx`）：**

当前结构（约 1167-1184 行）：
```
<div className="relative" ref={contentDisplayRef}>
  <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 ...">
    复制 / 编辑 按钮
  </div>
  <div className="prose ...">
    <ReactMarkdown>
  </div>
</div>
```

改为：
```
<div ref={contentDisplayRef}>
  <div className="sticky top-0 z-10 flex justify-end gap-1 opacity-0 group-hover:opacity-100 ...">
    复制 / 编辑 按钮
  </div>
  <div className="prose ...">
    <ReactMarkdown>
  </div>
</div>
```

关键点：
- 去掉父级 `relative`（`sticky` 相对于最近的滚动祖先 `overflow-y-auto` 定位，不需要 `relative` 父级）
- 按钮容器改为 `sticky top-0`，在自然文档流中位于内容顶部，滚动时钉住
- 按钮使用 `flex justify-end` 靠右，替代 `absolute right-2`
- 保留 `group-hover:opacity-100` 行为不变
- `content-block-card.tsx` 的按钮不需要改（卡片视图内容较短，不会超一屏）

---

### D. 移除内容区域单击进入编辑

**方案：有内容时移除内容区域的 onClick 进入编辑，仅通过 hover「编辑」按钮进入；无内容时保留单击空白占位区进入编辑。**

**`content-block-editor.tsx`（约 1145-1153 行）：**

当前：
```tsx
<div className="min-h-[200px] cursor-pointer group"
  onClick={() => {
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;
    if (inlineEditResult) return;
    setIsEditing(true);
  }}
  onMouseUp={handleContentMouseUp}
>
```

改为：
```tsx
<div className="min-h-[200px] group"
  onMouseUp={handleContentMouseUp}
>
```

- 删除整个 `onClick` handler
- 删除 `cursor-pointer`（改为默认光标，方便文字选中）
- `onMouseUp` 保留（用于 inline AI 文字选中检测）
- hover 出现的「编辑」按钮已有独立的 `onClick`（`e.stopPropagation()` + `setIsEditing(true)`），不受影响
- 无内容时的空白占位区（"点击此处编辑内容"）保留单击入口，单独在那个 `<div>` 上加 `onClick={() => setIsEditing(true)}` + `cursor-pointer`

**`content-block-card.tsx`（约 964-966 行）：**

当前：
```tsx
<div className="min-h-[80px] cursor-pointer group"
  onClick={() => setIsEditing(true)}
>
```

改为：
```tsx
<div className="min-h-[80px] group">
```

- 删除 `onClick` 和 `cursor-pointer`
- hover 出现的「编辑」按钮同样不受影响
- 无内容时的空白占位区同样保留单击入口

---

### E. 生成前提问默认收起

**问题：** `content-block-card.tsx` 第 227-231 行有一个 `useEffect`，当内容块类型为 field 且没有生成前提问时，会自动 `setIsExpanded(true)` 展开整个卡片（包括生成前提问区域）。导致新建内容块时卡片乱七八糟地展开。

**方案：** 删除这个自动展开的 `useEffect`。

当前代码：
```tsx
useEffect(() => {
  if (showPreQuestionsSection && preQuestions.length === 0) {
    setIsExpanded(true);
  }
}, [showPreQuestionsSection, preQuestions.length]);
```

直接删除。`isExpanded` 已默认 `useState(false)`，组和内容块都会默认收起。

`content-block-editor.tsx` 中 `preQuestionsExpanded` 已经默认 `useState(false)`（第 214 行），无需修改。

---

## 四、实施顺序

按依赖关系和风险从低到高排列：

1. **E — 生成前提问默认收起**（删一个 useEffect，零风险）
2. **D — 移除单击进入编辑**（删 onClick + cursor-pointer，零风险）
3. **C — 复制/编辑按钮 sticky**（CSS 改动，低风险）
4. **A — 对话改内容**（前后端联动，中风险）
5. **B — 添加到 Agent Panel**（跨组件数据通道，中风险）

每步完成后验证，再进入下一步。
