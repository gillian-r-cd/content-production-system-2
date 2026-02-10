# 三大功能实现方案（最终版）

> 创建时间: 2026-02-10
> 状态: 方案已确认，待实施

---

## 共识总览

### 话题一：提示词更新
- 用户通过对话框旁的**显式开关**触发"修改提示词"模式
- 开关打开后，用户输入正常修改指令，Agent **依次**完成：内容修改 → 提示词修改确认
- 提示词修改采用**三步制**：WYSIWYG 计划 → 确认 → 修订预览 → 确认 → 写入
- 版本管理复用 `ContentVersion`，`source="prompt_update"`

### 话题二：平台记忆
- 每个字段/内容块新增 `digest` 字段（一句话摘要，≤50字）
- 摘要在字段内容更新时**异步生成**（write-time async，用小模型）
- **全量字段摘要索引**（~600 tokens）无条件注入到每次 LLM 调用的 system prompt
- system prompt 中明确说明索引用途，防止基于摘要过拟合
- `required_fields`：意图路由基于索引判断需要全文的字段（去重 @ 引用，上限 5 个）

### 话题三：字段精细编辑
- LLM 输出**编辑操作指令**（edits），不输出修改后全文
- 每个 edit 用 `anchor`（原文精确引用）定位
- Agent 自主判断是否需要用户确认（`need_confirm`）
- 后端 `apply_edits()` 确定性执行，返回结构化 changes
- 前端 **Word Track Changes** 级别的逐条接受/拒绝
- 所有 ReactMarkdown 渲染点启用 `rehypeRaw`，支持 `<del>/<ins>` 修订标记

---

## 一、提示词更新

### 1.1 前端：对话框开关

**位置**：agent-panel.tsx 的输入框上方（快捷操作栏旁）

```
┌──────────────────────────────────────────┐
│ [消息列表区域...]                         │
├──────────────────────────────────────────┤
│  ☑ 同步修改提示词                         │  ← 新增的 toggle
│  ┌────────────────────────────────┐ [发送] │
│  │ 输入消息... 使用 @ 引用字段     │        │
│  └────────────────────────────────┘        │
│  [继续] [开始调研] [评估] [🔧 调用工具]    │
└──────────────────────────────────────────┘
```

**实现**：

文件：`frontend/components/agent-panel.tsx`

```typescript
// 新增状态
const [updatePrompt, setUpdatePrompt] = useState(false);

// 在发送请求时传递该标记
body: JSON.stringify({
  project_id: projectId,
  message: userMessage,
  references,
  current_phase: currentPhase || undefined,
  update_prompt: updatePrompt,  // 新增
}),

// 渲染 toggle（放在 textarea 上方）
<label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer select-none">
  <input
    type="checkbox"
    checked={updatePrompt}
    onChange={(e) => setUpdatePrompt(e.target.checked)}
    className="w-3.5 h-3.5 rounded border-surface-3 text-brand-600 focus:ring-brand-500"
  />
  同步修改提示词
</label>
```

### 1.2 后端：ChatRequest 扩展

文件：`backend/api/agent.py`

```python
class ChatRequest(BaseModel):
    project_id: str
    message: str
    references: list[str] = []
    current_phase: str = ""
    update_prompt: bool = False  # 新增
```

### 1.3 后端：流程设计

当 `update_prompt=True` 时，Agent 的执行流程变为两阶段：

```
用户发送 "@场景库 把5个模块改成7个模块" (update_prompt=ON)
    │
    ▼
Phase A: 正常的内容修改（走 modify_node / edits 流程）
    │ → 输出 edits，前端展示 Track Changes
    │ → 用户接受/拒绝 → 内容修改完成
    │
    ▼
Phase B: 提示词修改（仅当 Phase A 完成后触发）
    │
    ├── Step 1: WYSIWYG 修改计划
    │   Agent 读取该字段的 ai_prompt，分析用户指令对提示词的影响
    │   输出格式：
    │     修改计划：
    │     - 原句：「基于协访后复盘展开，设计5个模块的训练场景」
    │       改为：「基于协访后复盘展开，设计7个模块的训练场景」
    │     [如果有冲突] 注意：现有规则「场景不超过20个」可能需要同步调整
    │
    ├── 用户确认 → 进入 Step 2
    │
    ├── Step 2: 修订预览
    │   展示带 ~~删除线~~ 和 **高亮** 的完整提示词修订版
    │   用户确认 → 进入 Step 3
    │
    └── Step 3: 写入
        保存新版 ai_prompt → ContentVersion(source="prompt_update")
```

**Phase B 的实现方式**：

后端在 Phase A 完成后，如果 `update_prompt=True`，在 SSE done 事件中追加标记：

```python
# SSE done 事件
yield sse_event({
    "type": "done",
    "message_id": msg_id,
    "is_producing": True,
    "pending_prompt_update": True,  # 新增：告诉前端还有提示词修改流程
    "target_field": target_field,    # 涉及的字段名
})
```

前端收到 `pending_prompt_update=True` 后，自动发送第二条请求（Phase B），带上 `mode: "prompt_plan"`：

```typescript
// 自动触发提示词修改计划
if (data.pending_prompt_update) {
  // 展示 "正在分析提示词修改..." 的过渡消息
  // 然后发送:
  await fetch(`${API_BASE}/api/agent/stream`, {
    method: "POST",
    body: JSON.stringify({
      project_id: projectId,
      message: `[提示词修改计划] 基于刚才的修改指令"${userMessage}"，分析对字段「${data.target_field}」提示词的影响`,
      references: [data.target_field],
      mode: "prompt_plan",  // 专用模式，绕过 route_intent
    }),
  });
}
```

### 1.4 后端：prompt_plan 模式处理

文件：`backend/api/agent.py` 的 stream endpoint

当 `mode="prompt_plan"` 时，直接走提示词修改流程，不经过 `route_intent`：

```python
if request.mode == "prompt_plan":
    # 直接调用提示词修改计划节点
    result = await prompt_plan_node(routed_state)
elif request.mode == "prompt_execute":
    # 用户确认后，执行提示词修改
    result = await prompt_execute_node(routed_state)
else:
    # 正常的意图路由
    ...
```

### 1.5 prompt_plan_node

文件：`backend/core/orchestrator.py`（新增）

```python
async def prompt_plan_node(state: ContentProductionState) -> ContentProductionState:
    """
    提示词修改计划节点
    读取目标字段的 ai_prompt，输出 WYSIWYG 修改计划
    """
    target_field = state.get("parsed_target_field", "")
    project_id = state.get("project_id", "")
    user_input = state.get("user_input", "")
    
    # 获取目标字段的当前 ai_prompt
    current_prompt = get_field_ai_prompt(project_id, target_field)
    
    if not current_prompt:
        return {
            **state,
            "agent_output": f"字段「{target_field}」暂无提示词，无需修改。",
            "is_producing": False,
        }
    
    system_prompt = f"""你要为一个字段的生成提示词做修改计划。

## 当前提示词（字段：{target_field}）
{current_prompt}

## 用户的修改要求
{user_input}

## 输出要求
以"所见即所得"的方式，对于每处改动，直接给出：
- 原句：「引用当前提示词中的原文」
  改为：「修改后的具体文字」

如果新要求和现有规则有冲突，简要指出冲突在哪。
如果没有冲突，不要多说。
不要输出其他内容。"""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content="请输出修改计划"),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.3)
    
    return {
        **state,
        "agent_output": response.content,
        "is_producing": False,  # 计划不保存到字段
        "pending_prompt_plan": {
            "target_field": target_field,
            "current_prompt": current_prompt,
            "plan": response.content,
        },
    }
```

### 1.6 prompt_execute_node

用户确认计划后，前端发送 `mode="prompt_execute"`，后端执行：

```python
async def prompt_execute_node(state: ContentProductionState) -> ContentProductionState:
    """
    提示词修改执行节点
    按确认的计划修改 ai_prompt，输出修订预览
    """
    pending = state.get("pending_prompt_plan", {})
    target_field = pending.get("target_field", "")
    current_prompt = pending.get("current_prompt", "")
    plan = pending.get("plan", "")
    
    system_prompt = f"""你要按照已确认的修改计划，修改一个字段的生成提示词。

## 当前提示词
{current_prompt}

## 已确认的修改计划
{plan}

## 输出要求
输出修改后的完整提示词。只输出提示词本身，不要有任何额外说明。"""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content="请输出修改后的提示词"),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.2)
    new_prompt = response.content
    
    # 生成修订预览（用 diff 标记）
    revision_preview = generate_revision_markdown(current_prompt, new_prompt)
    
    # 保存到字段的 ai_prompt + 版本记录
    save_prompt_update(project_id, target_field, new_prompt, current_prompt)
    
    return {
        **state,
        "agent_output": f"✅ 提示词已更新。修订预览：\n\n{revision_preview}",
        "is_producing": False,
    }
```

### 1.7 辅助函数

文件：`backend/api/agent.py`（新增）

```python
def get_field_ai_prompt(project_id: str, field_name: str) -> str | None:
    """获取字段的 ai_prompt"""
    db = next(get_db())
    # 先查 ContentBlock
    block = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.name == field_name,
        ContentBlock.deleted_at == None,
    ).first()
    if block and block.ai_prompt:
        return block.ai_prompt
    # 再查 ProjectField
    field = db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
        ProjectField.name == field_name,
    ).first()
    if field and field.ai_prompt:
        return field.ai_prompt
    return None

def save_prompt_update(project_id: str, field_name: str, new_prompt: str, old_prompt: str):
    """保存提示词修改 + 版本记录"""
    db = next(get_db())
    # 查找目标
    block = db.query(ContentBlock).filter(...).first()
    if block:
        _save_version_before_overwrite(db, block.id, old_prompt, "prompt_update", field_name)
        block.ai_prompt = new_prompt
    else:
        field = db.query(ProjectField).filter(...).first()
        if field:
            _save_version_before_overwrite(db, field.id, old_prompt, "prompt_update", field_name)
            field.ai_prompt = new_prompt
    db.commit()
```

---

## 二、平台记忆（字段摘要索引）

### 2.1 数据库 Schema 变更

**新增列**：

```python
# ProjectField 新增
digest: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

# ContentBlock 新增
digest: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
```

**迁移脚本**：`backend/scripts/migrate_add_digest.py`

```python
"""
为 ProjectField 和 ContentBlock 添加 digest 列
"""
import sqlite3

DB_PATH = "content_production.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for table in ["project_fields", "content_blocks"]:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN digest TEXT")
            print(f"✅ Added 'digest' column to {table}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"⏭️ Column 'digest' already exists in {table}")
            else:
                raise
    
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
```

### 2.2 异步摘要生成

文件：`backend/core/digest_service.py`（新建）

```python
"""
字段摘要服务
在字段内容更新后异步生成一句话摘要
"""
import asyncio
from core.ai_client import ai_client
from core.models import ProjectField, ContentBlock
from core.database import get_db
from langchain_core.messages import ChatMessage

async def generate_digest(content: str) -> str:
    """用小模型生成一句话摘要（≤50字）"""
    if not content or len(content.strip()) < 10:
        return ""
    
    messages = [
        ChatMessage(
            role="user",
            content=f"用一句话概括以下内容的核心主题和要点（不超过50字，只输出摘要本身）：\n\n{content[:3000]}"
        ),
    ]
    
    response = await ai_client.async_chat(
        messages,
        temperature=0,
        model="gpt-4o-mini",  # 用便宜快速的模型
    )
    return response.content.strip()[:200]


def trigger_digest_update(entity_id: str, entity_type: str, content: str):
    """
    非阻塞地触发摘要更新。
    在字段内容保存后调用。
    
    Args:
        entity_id: ProjectField 或 ContentBlock 的 ID
        entity_type: "field" 或 "block"
        content: 字段内容
    """
    async def _do_update():
        try:
            digest = await generate_digest(content)
            if not digest:
                return
            
            db = next(get_db())
            if entity_type == "field":
                entity = db.query(ProjectField).filter_by(id=entity_id).first()
            else:
                entity = db.query(ContentBlock).filter_by(id=entity_id).first()
            
            if entity:
                entity.digest = digest
                db.commit()
                print(f"[Digest] Updated digest for {entity_type} {entity_id[:8]}: {digest[:50]}")
        except Exception as e:
            print(f"[Digest] Error updating digest: {e}")
    
    # 在后台执行，不阻塞主流程
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_do_update())
        else:
            asyncio.run(_do_update())
    except RuntimeError:
        # 如果没有事件循环（同步上下文），跳过
        pass
```

### 2.3 摘要更新触发点

在以下位置，保存内容后调用 `trigger_digest_update()`：

| 触发点 | 文件 | 说明 |
|--------|------|------|
| `_save_result_to_field()` | `backend/api/agent.py` | Agent 产出/修改字段后 |
| `PUT /api/fields/{id}` | `backend/api/fields.py` | 用户手动编辑字段后 |
| `PUT /api/blocks/{id}` | `backend/api/blocks.py` | 用户手动编辑内容块后 |
| 字段生成完成 | `backend/api/fields.py` | AI 生成字段内容后 |

示例（在 `_save_result_to_field` 中）：

```python
from core.digest_service import trigger_digest_update

# 在保存内容之后
if field_updated and agent_output:
    entity_id = field_updated.get("id", "")
    entity_type = "block" if field_updated.get("phase") == "" else "field"
    trigger_digest_update(entity_id, entity_type, agent_output)
```

### 2.4 构建全量字段索引

文件：`backend/core/digest_service.py`（追加）

```python
def build_field_index(project_id: str) -> str:
    """
    构建项目的全量字段摘要索引。
    返回格式化的字符串，注入到 system prompt。
    """
    db = next(get_db())
    
    entries = []
    
    # ProjectField
    fields = db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
    ).all()
    for f in fields:
        status_label = {"pending": "待生成", "generating": "生成中", "completed": "已完成", "failed": "失败"}.get(f.status, f.status)
        digest = f.digest or ("（有内容，摘要生成中）" if f.content else "（空）")
        entries.append(f"- {f.name} [{status_label}]: {digest}")
    
    # ContentBlock（仅 field 类型，排除 phase/group）
    blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.block_type == "field",
        ContentBlock.deleted_at == None,
    ).all()
    for b in blocks:
        status_label = {"pending": "待处理", "in_progress": "进行中", "completed": "已完成"}.get(b.status, b.status)
        digest = b.digest or ("（有内容，摘要生成中）" if b.content else "（空）")
        entries.append(f"- {b.name} [{status_label}]: {digest}")
    
    if not entries:
        return ""
    
    return "\n".join(entries)
```

### 2.5 注入到 System Prompt

在**所有 LLM 调用节点**（modify_node, query_node, chat_node, phase nodes, tool_node）的 system prompt 中追加：

```python
field_index = build_field_index(project_id)

# 注入到 system prompt 末尾（所有节点通用）
field_index_block = ""
if field_index:
    field_index_block = f"""

## 项目字段索引
以下是本项目所有字段及其摘要。
用途：帮你定位与用户指令相关的字段。
注意：摘要只是索引，不是完整内容。如果你需要某个字段的完整内容来回答问题或执行操作，请通过 required_fields 获取，不要基于摘要猜测或编造内容。

{field_index}
"""
```

**关键语句**："不要基于摘要猜测或编造内容"——这是防止过拟合的核心约束。

### 2.6 route_intent 输出 required_fields

在意图路由的 LLM prompt 中，追加 required_fields 输出要求：

```python
# 在 route_intent 的 system prompt 最后追加：
f"""
## 上下文需求判断
根据用户指令，判断执行此操作需要哪些字段的**完整内容**。
参考上面的项目字段索引，列出所有可能相关的字段名（上限 5 个）。
宁可多列，不要遗漏。不确定是否需要就列上。
{f"排除已通过 @ 引用的字段：{references}" if references else ""}

在 JSON 输出中追加：
"required_fields": ["字段名1", "字段名2"]
如果不需要额外字段，输出空数组。
"""
```

**处理逻辑**（在 route_intent 后、节点执行前）：

```python
# 获取 required_fields 的全文
required_fields = routed_state.get("required_fields", [])
# 去重：排除已通过 @ 引用获取的
already_referenced = set(references)
required_fields = [f for f in required_fields if f not in already_referenced]

extra_context = {}
for field_name in required_fields[:5]:  # 硬上限
    data = get_field_content(project_id, field_name)
    if data and data.get("content"):
        extra_context[field_name] = data["content"]

routed_state["extra_referenced_contents"] = extra_context
```

节点中使用 `extra_referenced_contents` 作为额外上下文。

---

## 三、字段精细编辑

### 3.1 核心数据结构：Edit 操作

```python
# 单个编辑操作
Edit = {
    "type": "replace" | "insert_after" | "insert_before" | "delete",
    "anchor": str,      # 原文中的精确引用（用于定位）
    "new_text": str,     # 替换/插入的新内容（delete 时为空）
}

# LLM 输出格式
ModifyResult = {
    "edits": list[Edit],
    "need_confirm": bool,          # Agent 判断是否需要用户确认
    "summary": str,                # 变更摘要（改了什么，没改什么）
    "ambiguity": str | None,       # 如果 need_confirm=True，说明歧义在哪
}
```

### 3.2 modify_node 提示词重写

文件：`backend/core/orchestrator.py`（替换现有 modify_node 中的 system_prompt）

```python
system_prompt = f"""你是一个精确的内容编辑器。你的任务是将用户的修改指令转化为具体的编辑操作。

## 当前项目
{creator_profile}

## 目标字段：{target_field}
{original_content}

{f"## 参考内容" + chr(10) + chr(10).join(f"### {k}{chr(10)}{v}" for k, v in extra_context.items()) if extra_context else ""}

## 用户指令
{operation}

## 你的工作
1. 理解用户想要做什么修改
2. 将修改转化为具体的 edits（编辑操作列表）
3. 判断是否需要用户确认：
   - 指令清晰、无歧义 → need_confirm: false
   - 指令有多种理解方式，或影响范围不确定 → need_confirm: true

## edit 类型
- replace: 替换。anchor 是要被替换的原文，new_text 是替换后的内容
- insert_after: 在 anchor 之后插入 new_text
- insert_before: 在 anchor 之前插入 new_text
- delete: 删除 anchor 指定的内容

## 关键规则
- anchor 必须是原文中**逐字逐句精确存在**的片段，不要改动或概括
- anchor 必须在原文中**唯一**。如果目标片段出现多次，加长引用（包含前后文）直到唯一
- 只输出需要变更的部分。用户没提到的内容，不要动，不要出现在 edits 里
- 如果用户要修改表格中的内容，anchor 应该包含整行（从 | 到 |）

## 输出格式（严格 JSON）
{{
  "edits": [
    {{"type": "replace", "anchor": "原文精确引用", "new_text": "替换后的内容"}},
    {{"type": "insert_after", "anchor": "原文精确引用", "new_text": "要插入的内容"}},
    {{"type": "delete", "anchor": "原文精确引用", "new_text": ""}}
  ],
  "need_confirm": false,
  "summary": "简述改了什么、没改什么",
  "ambiguity": null
}}

只输出 JSON，不要有其他内容。"""
```

### 3.3 后端：apply_edits()

文件：`backend/core/edit_engine.py`（新建）

```python
"""
编辑引擎
将 LLM 输出的 edits 确定性地应用到原始内容上
"""
from typing import Optional


def apply_edits(
    original: str,
    edits: list[dict],
    accepted_ids: set[str] | None = None,
) -> tuple[str, list[dict]]:
    """
    将编辑操作应用到原始内容。
    
    Args:
        original: 原始内容
        edits: 编辑操作列表，每个包含 type, anchor, new_text
        accepted_ids: 如果提供，只应用这些 ID 的 edits（用于部分接受）
                      如果为 None，应用所有 edits
    
    Returns:
        (修改后的内容, 带状态和位置信息的 changes 列表)
    """
    result = original
    changes = []
    
    # 为每个 edit 分配 ID（如果没有）
    for i, edit in enumerate(edits):
        if "id" not in edit:
            edit["id"] = f"e{i}"
    
    # 按原文中出现位置从后往前排序（避免位置偏移）
    positioned_edits = []
    for edit in edits:
        anchor = edit.get("anchor", "")
        pos = original.find(anchor)
        positioned_edits.append((pos, edit))
    
    # 从后往前处理，避免前面的修改影响后面的位置
    positioned_edits.sort(key=lambda x: x[0], reverse=True)
    
    for pos, edit in positioned_edits:
        edit_id = edit["id"]
        anchor = edit.get("anchor", "")
        new_text = edit.get("new_text", "")
        edit_type = edit.get("type", "replace")
        
        # 如果指定了 accepted_ids，检查是否被接受
        if accepted_ids is not None and edit_id not in accepted_ids:
            changes.append({
                **edit,
                "status": "rejected",
                "position": {"start": pos, "end": pos + len(anchor) if pos >= 0 else -1},
            })
            continue
        
        if pos == -1:
            changes.append({
                **edit,
                "status": "failed",
                "reason": "anchor_not_found",
                "position": {"start": -1, "end": -1},
            })
            continue
        
        # 检查 anchor 唯一性
        if result.count(anchor) > 1:
            changes.append({
                **edit,
                "status": "failed",
                "reason": "anchor_not_unique",
                "position": {"start": pos, "end": pos + len(anchor)},
            })
            continue
        
        # 应用编辑
        if edit_type == "replace":
            result = result[:pos] + new_text + result[pos + len(anchor):]
            changes.append({
                **edit,
                "old_text": anchor,
                "status": "applied",
                "position": {"start": pos, "end": pos + len(new_text)},
            })
        elif edit_type == "insert_after":
            insert_pos = pos + len(anchor)
            result = result[:insert_pos] + "\n" + new_text + result[insert_pos:]
            changes.append({
                **edit,
                "old_text": None,
                "status": "applied",
                "position": {"start": insert_pos + 1, "end": insert_pos + 1 + len(new_text)},
            })
        elif edit_type == "insert_before":
            result = result[:pos] + new_text + "\n" + result[pos:]
            changes.append({
                **edit,
                "old_text": None,
                "status": "applied",
                "position": {"start": pos, "end": pos + len(new_text)},
            })
        elif edit_type == "delete":
            result = result[:pos] + result[pos + len(anchor):]
            changes.append({
                **edit,
                "old_text": anchor,
                "status": "applied",
                "position": {"start": pos, "end": pos},
            })
    
    return result, changes


def generate_revision_markdown(old: str, new: str) -> str:
    """
    生成带修订标记的 markdown（用于提示词修改预览等场景）。
    删除的内容用 <del> 包裹，新增的内容用 <ins> 包裹。
    """
    import difflib
    
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    result = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result.extend(old_lines[i1:i2])
        elif tag == "replace":
            for line in old_lines[i1:i2]:
                result.append(f"<del>{line.rstrip()}</del>\n")
            for line in new_lines[j1:j2]:
                result.append(f"<ins>{line.rstrip()}</ins>\n")
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                result.append(f"<del>{line.rstrip()}</del>\n")
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                result.append(f"<ins>{line.rstrip()}</ins>\n")
    
    return "".join(result)
```

### 3.4 后端：modify_node 改造

文件：`backend/core/orchestrator.py`

modify_node 的返回值变更：

```python
async def modify_node(state: ContentProductionState) -> ContentProductionState:
    # ... 构建 system_prompt（使用 3.2 的新提示词）
    # ... 调用 LLM
    
    # 解析 JSON 输出
    import json
    try:
        modify_result = json.loads(response.content)
    except json.JSONDecodeError:
        # 降级：把整个输出当成纯文本（兼容老行为）
        return {**state, "agent_output": response.content, "is_producing": True, "modify_target_field": target_field}
    
    edits = modify_result.get("edits", [])
    need_confirm = modify_result.get("need_confirm", False)
    summary = modify_result.get("summary", "")
    ambiguity = modify_result.get("ambiguity")
    
    if need_confirm:
        # 需要确认：不保存，把计划返回给用户
        plan_text = f"📝 **修改计划**（字段：{target_field}）\n\n"
        plan_text += f"{summary}\n\n"
        if ambiguity:
            plan_text += f"⚠️ 需要确认：{ambiguity}\n\n"
        plan_text += "**具体修改：**\n"
        for i, edit in enumerate(edits):
            if edit["type"] == "replace":
                plan_text += f"{i+1}. 替换：「{edit['anchor'][:80]}」→「{edit['new_text'][:80]}」\n"
            elif edit["type"] == "insert_after" or edit["type"] == "insert_before":
                plan_text += f"{i+1}. 新增：在「{edit['anchor'][:60]}」{'之后' if edit['type'] == 'insert_after' else '之前'}插入内容\n"
            elif edit["type"] == "delete":
                plan_text += f"{i+1}. 删除：「{edit['anchor'][:80]}」\n"
        plan_text += "\n请确认，或告诉我需要调整。"
        
        return {
            **state,
            "agent_output": plan_text,
            "is_producing": False,  # 不保存到字段
            "pending_edits": {
                "target_field": target_field,
                "original_content": original_content,
                "edits": edits,
                "summary": summary,
            },
        }
    else:
        # 直接执行
        new_content, changes = apply_edits(original_content, edits)
        
        # 检查是否有失败的 edit
        failed = [c for c in changes if c["status"] == "failed"]
        if failed:
            error_msg = "\n".join([f"- {c['anchor'][:50]}... ({c['reason']})" for c in failed])
            # 有失败的 edit，回退到确认模式
            return {
                **state,
                "agent_output": f"部分修改无法定位：\n{error_msg}\n\n请确认或调整指令。",
                "is_producing": False,
            }
        
        return {
            **state,
            "agent_output": "",  # 实际内容通过 changes 传递
            "is_producing": True,
            "modify_target_field": target_field,
            "modify_result": {
                "original_content": original_content,
                "new_content": new_content,
                "changes": changes,
                "summary": summary,
            },
        }
```

### 3.5 后端：SSE 事件传递 changes

文件：`backend/api/agent.py` 的 stream endpoint

在 `done` 事件中传递 Track Changes 数据：

```python
modify_result = result.get("modify_result")
if modify_result:
    # 有 Track Changes 数据
    yield sse_event({
        "type": "modify_preview",
        "target_field": result.get("modify_target_field"),
        "original_content": modify_result["original_content"],
        "new_content": modify_result["new_content"],
        "changes": modify_result["changes"],
        "summary": modify_result["summary"],
    })

pending_edits = result.get("pending_edits")
if pending_edits:
    # Agent 需要确认
    yield sse_event({
        "type": "modify_confirm_needed",
        "target_field": pending_edits["target_field"],
        "edits": pending_edits["edits"],
        "summary": pending_edits["summary"],
    })
```

### 3.6 后端：部分接受 API

文件：`backend/api/fields.py`（新增 endpoint）

```python
@router.post("/{field_id}/accept-changes")
def accept_changes(
    field_id: str,
    body: dict,  # {"original_content": str, "edits": list, "accepted_ids": list[str]}
    db: Session = Depends(get_db),
):
    """
    接受部分修改。
    用户在 Track Changes UI 中逐条接受/拒绝后，
    前端发送 accepted_ids 列表，后端只应用被接受的 edits。
    """
    original = body["original_content"]
    edits = body["edits"]
    accepted_ids = set(body.get("accepted_ids", []))
    
    new_content, changes = apply_edits(original, edits, accepted_ids=accepted_ids)
    
    # 保存
    field = db.query(ProjectField).filter_by(id=field_id).first()
    if not field:
        block = db.query(ContentBlock).filter_by(id=field_id).first()
        if block:
            _save_version_before_overwrite(db, block.id, block.content, "agent_modify", block.name)
            block.content = new_content
            trigger_digest_update(block.id, "block", new_content)
    else:
        _save_version_before_overwrite(db, field.id, field.content, "agent_modify", field.name)
        field.content = new_content
        trigger_digest_update(field.id, "field", new_content)
    
    db.commit()
    
    return {
        "status": "ok",
        "applied_count": len([c for c in changes if c["status"] == "applied"]),
        "rejected_count": len([c for c in changes if c["status"] == "rejected"]),
    }
```

### 3.7 前端：RevisionView 组件

文件：`frontend/components/revision-view.tsx`（新建）

```tsx
/**
 * RevisionView - Word Track Changes 级别的修订视图
 * 
 * 在渲染后的 markdown 界面上展示修订标记：
 * - 删除的内容：红色删除线
 * - 新增的内容：绿色高亮
 * - 每个 change 旁有 ✓/✗ 按钮
 */

interface Change {
  id: string;
  type: "replace" | "insert_after" | "insert_before" | "delete";
  anchor: string;
  old_text?: string;
  new_text: string;
  status: "applied" | "failed";
  position: { start: number; end: number };
}

interface RevisionViewProps {
  originalContent: string;
  changes: Change[];
  summary: string;
  onAcceptAll: () => void;
  onRejectAll: () => void;
  onAcceptChange: (id: string) => void;
  onRejectChange: (id: string) => void;
  onFinalize: (acceptedIds: string[]) => void;
}
```

**渲染逻辑**：

基于 `originalContent` 和 `changes` 列表，生成带 `<del>/<ins>` 标签的 markdown 字符串，然后交给 ReactMarkdown（启用 rehypeRaw）渲染。每个 change 区域包裹在一个带 `data-change-id` 的容器中，通过 CSS hover 显示 ✓/✗ 按钮。

```tsx
// 生成带修订标记的内容
function buildRevisionContent(original: string, changes: Change[], acceptedIds: Set<string>): string {
  let content = original;
  
  // 按位置从后往前处理（避免偏移）
  const sortedChanges = [...changes]
    .filter(c => c.status === "applied")
    .sort((a, b) => b.position.start - a.position.start);
  
  for (const change of sortedChanges) {
    const isAccepted = acceptedIds.has(change.id);
    const isPending = !acceptedIds.has(change.id) && !rejectedIds.has(change.id);
    
    if (change.type === "replace" && change.old_text) {
      const marker = isPending
        ? `<del class="revision-del" data-cid="${change.id}">${change.old_text}</del><ins class="revision-ins" data-cid="${change.id}">${change.new_text}</ins>`
        : isAccepted
          ? change.new_text
          : change.old_text;
      content = content.replace(change.old_text, marker);
    }
    // ... insert_after, insert_before, delete 类似处理
  }
  
  return content;
}
```

### 3.8 前端：RevisionView 工具栏

```tsx
<div className="revision-toolbar flex items-center gap-3 px-4 py-2 bg-surface-2 border-b border-surface-3">
  <span className="text-sm text-zinc-400">
    ✏️ {pendingCount} 处修改待确认
  </span>
  <div className="flex-1" />
  <button onClick={onAcceptAll} className="px-3 py-1 text-xs bg-green-600/20 text-green-400 hover:bg-green-600/30 rounded">
    ✓ 接受全部
  </button>
  <button onClick={onRejectAll} className="px-3 py-1 text-xs bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded">
    ✗ 拒绝全部
  </button>
  <button onClick={() => onFinalize(Array.from(acceptedIds))} className="px-3 py-1 text-xs bg-brand-600 text-white rounded">
    完成
  </button>
</div>
```

### 3.9 前端：ReactMarkdown 启用 rehypeRaw

所有展示修订标记的 ReactMarkdown 实例需要：

```bash
npm install rehype-raw
```

```tsx
import rehypeRaw from "rehype-raw";

<ReactMarkdown
  remarkPlugins={[remarkGfm]}
  rehypePlugins={[rehypeRaw]}  // 新增
  components={{
    // 自定义 del/ins 渲染
    del: ({ children }) => (
      <del className="revision-del bg-red-500/20 text-red-300 line-through">{children}</del>
    ),
    ins: ({ children }) => (
      <ins className="revision-ins bg-green-500/20 text-green-300 no-underline">{children}</ins>
    ),
    // ... 其他 components
  }}
>
  {content}
</ReactMarkdown>
```

### 3.10 前端：CSS 样式

文件：`frontend/app/globals.css`（追加）

```css
/* ===== Revision Mode (Track Changes) ===== */
.revision-del {
  background-color: rgba(239, 68, 68, 0.15);
  color: #fca5a5;
  text-decoration: line-through;
  padding: 0 2px;
  border-radius: 2px;
}

.revision-ins {
  background-color: rgba(34, 197, 94, 0.15);
  color: #86efac;
  text-decoration: none;
  padding: 0 2px;
  border-radius: 2px;
  border-bottom: 1px solid rgba(34, 197, 94, 0.4);
}

/* 修订标记的悬停交互 */
[data-cid]:hover {
  outline: 2px solid rgba(139, 92, 246, 0.5);
  outline-offset: 1px;
  cursor: pointer;
}
```

---

## 四、版本管理

### 4.1 ContentVersion 新增 source 类型

在 `VERSION_SOURCES` 中追加：

```python
VERSION_SOURCES = {
    "manual": "手动编辑",
    "ai_generate": "AI 生成",
    "ai_regenerate": "重新生成",
    "agent": "Agent 修改",
    "rollback": "版本回滚",
    "prompt_update": "提示词修改",  # 新增
}
```

### 4.2 提示词版本记录

提示词修改时，在 `save_prompt_update()` 中，将旧的 ai_prompt 保存为 ContentVersion：

```python
_save_version_before_overwrite(
    db, 
    field_id,           # 字段ID
    old_ai_prompt,      # 旧提示词内容（不是字段内容）
    "prompt_update",    # source
    f"prompt:{field_name}",  # source_detail，用 "prompt:" 前缀区分
)
```

---

## 五、实施顺序

### Phase 1: 基建（无 UI 变化）
1. ✅ 迁移脚本：ProjectField / ContentBlock 加 `digest` 列
2. ✅ `backend/core/edit_engine.py`：`apply_edits()` + `generate_revision_markdown()`
3. ✅ `backend/core/digest_service.py`：摘要生成 + 字段索引构建
4. ✅ `npm install rehype-raw`

### Phase 2: 话题二 — 平台记忆
5. 所有内容保存触发点加 `trigger_digest_update()`
6. 所有 LLM 节点的 system prompt 注入 `field_index_block`
7. route_intent 输出 `required_fields`，节点执行前获取全文

### Phase 3: 话题三 — 精细编辑
8. modify_node 重写（新提示词 + edits JSON 输出 + need_confirm 判断）
9. SSE 新增 `modify_preview` / `modify_confirm_needed` 事件
10. `POST /api/fields/{id}/accept-changes` endpoint
11. 前端 `RevisionView` 组件
12. ReactMarkdown 启用 rehypeRaw + del/ins 样式
13. 字段面板集成 RevisionView（收到 modify_preview 事件时切换到修订模式）

### Phase 4: 话题一 — 提示词更新
14. ChatRequest 新增 `update_prompt` + `mode` 字段
15. 前端 toggle "同步修改提示词"
16. `prompt_plan_node` + `prompt_execute_node`
17. SSE `pending_prompt_update` 事件 → 前端自动触发 Phase B
18. 提示词修订预览（复用 `generate_revision_markdown`）

---

## 六、风险与 Fallback

| 风险 | 应对 |
|------|------|
| LLM 输出的 edits JSON 格式不对 | `json.JSONDecoder().raw_decode()` + fallback 到纯文本（兼容现有行为） |
| anchor 在原文中找不到 | edit 标记为 failed，告知用户；如果所有 edits 都失败，回退到确认模式 |
| anchor 不唯一 | edit 标记为 failed，提示 LLM 需要更长的引用 |
| 摘要生成延迟（字段刚更新后立刻请求） | 索引中显示"有内容，摘要生成中"，不影响功能 |
| rehypeRaw 导致用户内容中的 HTML 被意外渲染 | 只在修订模式下启用 rehypeRaw；正常渲染模式不启用 |
| 大段内容的 diff 过于碎片化 | 如果 changes 超过 15 个，提示用户"修改较多，建议逐段确认" |
