# 四大功能实现方案（最终版）

> 创建时间: 2026-02-10
> 最后更新: 2026-02-11
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

### 话题四：共创模式
- Agent 面板新增 `助手 / 共创` **Tab 切换**
- 共创模式下 AI 扮演指定角色与用户实时对话，用于获取目标受众反馈、共创迭代
- Persona 三层来源：**全局预置**（编辑/Coach/消费者/专家）+ **项目人物库** + **用户自建**
- Persona 配置区在共创 Tab 顶部，支持下拉选择、直接编写、保存复用
- 对话历史**分离显示**（两个 Tab 各自只显示本模式消息），数据存同一张表
- 上下文**单向自动桥接**：助手能看到最近共创对话（只读注入），共创角色看不到助手对话
- 共创模式下跳过 `route_intent`，直接走 `cocreation_node`

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

## 五、共创模式（Co-creation Mode）

### 5.1 概述

内容创作者希望在发布前，能和目标受众实时对话。例如课程设计者让一个"学生"看完课程内容，说"学到了什么""还想学什么"。这是一个**人驱动的角色扮演对话**，区别于：

- **助手模式（现有）**：AI 是生产工具，执行用户指令
- **模拟器（现有）**：AI ↔ AI 自动对话，产出分数
- **共创模式（新增）**：用户 ↔ AI-as-角色，实时对话，产出洞察

共创模式和模拟器**共享 persona 定义和内容注入机制**，但**交互模式完全不同**：共创是人驱动，模拟器是全自动。

### 5.2 前端：Mode 切换 + Persona 配置

**位置**：Agent 面板顶部

```
┌──────────────────────────────────┐
│  [助手]  [共创]      ← tab 切换   │
├──────────────────────────────────┤
│  🎭 角色配置（仅共创 tab 显示）    │
│  ┌───────────────────────────┐   │
│  │ [选择角色 ▾]  [＋ 新建]    │   │
│  ├───────────────────────────┤   │
│  │ 你是一个刚学完急诊护理课程 │   │
│  │ 的一年级护理学生，对临床   │   │
│  │ 流程还不太熟悉...         │   │
│  └───────────────────────────┘   │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  [对话区域 - 只显示共创消息]      │
│  ...                              │
│  ┌──────────────────────┐ [发送] │
│  │ @场景库 你觉得怎么样？ │       │
│  └──────────────────────┘        │
└──────────────────────────────────┘
```

### 5.3 Persona 来源：三层

| 层级 | 示例 | 来源 | 存储 |
|------|------|------|------|
| **全局预置** | 编辑、Coach、典型消费者、行业专家 | 系统内置 | 代码常量 `COCREATION_PRESETS` |
| **项目人物库** | eval 系统创建的人物小传 | persona_manager | research field JSON |
| **用户自建** | "一年级护理学生，对临床不熟悉" | 用户在共创面板配置 | `Project.cocreation_personas` JSON |

**全局预置角色定义**：

```python
COCREATION_PRESETS = [
    {
        "id": "preset_editor",
        "name": "编辑",
        "description": "审稿人视角，关注逻辑、表达和可读性",
        "system_prompt_template": """你是一位资深编辑。你的职责是从读者体验的角度审视内容。
你关注：逻辑是否通顺、表达是否清晰、结构是否合理、有无冗余或遗漏。
你会直接指出问题，给出具体修改建议，不说空话。
说话风格：专业但不刻板，像一个有经验的同事在和你讨论稿件。""",
    },
    {
        "id": "preset_coach",
        "name": "Coach",
        "description": "教练视角，关注成长、引导和启发",
        "system_prompt_template": """你是一位经验丰富的教练。你通过提问来引导创作者思考。
你不直接给答案，而是帮助创作者发现自己的盲点和可能性。
你会问"如果...会怎样？""你有没有考虑过...？"这样的问题。
说话风格：温和、有耐心，但不回避尖锐的问题。""",
    },
    {
        "id": "preset_consumer",
        "name": "典型消费者",
        "description": "大众读者/用户视角，关注理解度和价值感",
        "system_prompt_template": """你是一个普通的目标受众。你没有专业背景，但有真实需求。
你会诚实地说：哪里看不懂、哪里觉得有用、哪里觉得无聊。
你不会客气——如果内容对你没用，你会直说。
说话风格：日常、口语化，像一个真实的用户在给反馈。""",
    },
    {
        "id": "preset_expert",
        "name": "行业专家",
        "description": "领域深度视角，关注专业性和准确性",
        "system_prompt_template": """你是该领域的资深专家。你对行业有深刻理解。
你会评估内容的专业准确性、是否有常见误区、是否遗漏关键概念。
你也会指出内容中的亮点——哪些地方的洞察让你觉得有价值。
说话风格：专业、严谨，但不居高临下。""",
    },
]
```

**Persona 选择器下拉结构**：

```
🔧 全局角色
  ├ 编辑（审稿人视角，关注逻辑和表达）
  ├ Coach（教练视角，关注成长和引导）
  ├ 典型消费者（大众读者视角）
  └ 行业专家（领域深度视角）
📁 项目人物
  ├ 学生A - 李明（来自人物库）
  └ HR总监 - 张琳（来自人物库）
✏️ 自定义角色
  ├ 一年级护理学生（上次保存）
  └ ＋ 新建角色...
```

### 5.4 数据库变更

**Project 模型新增字段**：

```python
# Project 新增
cocreation_personas: Mapped[list] = mapped_column(
    JSON, default=list
)
# 格式: [{"id": "custom_xxx", "name": "角色名", "description": "描述", "prompt": "角色设定文本"}]
```

**ChatMessage metadata 扩展**：

```python
# ChatMessage.message_metadata 增加字段
{
    "phase": "",
    "tool_used": None,
    "skill_used": None,
    "references": [],
    "mode": "assistant",        # 新增: "assistant" | "cocreation"
    "persona_name": None,       # 新增: 共创模式下的角色名
    "persona_id": None,         # 新增: 角色 ID（preset_xxx / custom_xxx / 项目人物 ID）
}
```

**迁移脚本**：`backend/scripts/migrate_add_cocreation.py`

```python
"""为 Project 添加 cocreation_personas 列"""
import sqlite3

DB_PATH = "content_production.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN cocreation_personas TEXT DEFAULT '[]'")
        print("✅ Added 'cocreation_personas' column to projects")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("⏭️ Column already exists")
        else:
            raise
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
```

### 5.5 后端：ChatRequest 扩展

文件：`backend/api/agent.py`

```python
class ChatRequest(BaseModel):
    project_id: str
    message: str
    references: list[str] = []
    current_phase: str = ""
    update_prompt: bool = False
    mode: str = "assistant"                  # 新增: "assistant" | "cocreation"
    persona_config: dict | None = None       # 新增: 共创角色配置
    # persona_config 格式:
    # {"id": "preset_editor", "name": "编辑", "prompt": "你是一位资深编辑..."}
    # 或 {"id": "custom_xxx", "name": "自定义角色", "prompt": "用户自定义的角色描述"}
```

### 5.6 后端：路由分流

文件：`backend/api/agent.py` 的 stream endpoint

```python
async def stream_chat(request: ChatRequest):
    # ...
    
    if request.mode == "cocreation":
        # 共创模式：跳过 route_intent，直接走 cocreation_node
        result = await cocreation_node({
            "project_id": request.project_id,
            "user_input": request.message,
            "references": request.references,
            "referenced_contents": referenced_contents,
            "persona_config": request.persona_config,
            "messages": cocreation_history,  # 只加载共创消息
        })
        # SSE 输出（复用现有流式机制）
        # ...
    
    elif request.mode == "prompt_plan":
        # 提示词修改流程（话题一）
        # ...
    
    else:
        # 助手模式：正常 route_intent
        # ...
```

### 5.7 后端：cocreation_node

文件：`backend/core/orchestrator.py`（新增）

```python
async def cocreation_node(state: dict) -> dict:
    """
    共创对话节点
    AI 扮演指定角色与用户实时对话
    """
    persona_config = state.get("persona_config", {})
    referenced_contents = state.get("referenced_contents", {})
    history = state.get("messages", [])
    user_input = state.get("user_input", "")
    
    # 构建角色 system prompt
    persona_prompt = persona_config.get("prompt", "")
    persona_name = persona_config.get("name", "角色")
    
    # 如果是全局预置角色，使用其模板
    if not persona_prompt:
        preset_id = persona_config.get("id", "")
        for preset in COCREATION_PRESETS:
            if preset["id"] == preset_id:
                persona_prompt = preset["system_prompt_template"]
                break
    
    # 构建引用内容上下文
    content_context = ""
    if referenced_contents:
        content_parts = []
        for name, content in referenced_contents.items():
            content_parts.append(f"### {name}\n{content}")
        content_context = f"""

【创作者分享给你的内容】
{chr(10).join(content_parts)}

你需要基于以上内容进行对话。如果用户 @ 了新的内容，也会在这里出现。"""
    
    system_prompt = f"""你正在扮演一个角色，与内容创作者进行一对一的共创对话。

【你的角色设定】
{persona_prompt}

【你的名字】
{persona_name}
{content_context}

【核心规则】
1. 始终以 {persona_name} 的身份和视角说话
2. 对内容给出真实反应——看不懂就说看不懂，觉得好就说好在哪
3. 主动表达你的困惑、期待、建议
4. 你不是 AI 助手，你就是 {persona_name}。不要说"作为AI"之类的话
5. 回答要自然、口语化，像真人在聊天
6. 如果创作者问你角色设定之外的事（比如帮我写代码），礼貌拒绝并把话题拉回内容"""
    
    messages = [ChatMessage(role="system", content=system_prompt)]
    
    # 添加共创历史消息
    for msg in history[-20:]:  # 最近 20 条
        messages.append(ChatMessage(
            role="user" if msg.get("role") == "user" else "assistant",
            content=msg.get("content", ""),
        ))
    
    # 当前用户输入
    messages.append(ChatMessage(role="user", content=user_input))
    
    response = await ai_client.async_chat(messages, temperature=0.8)
    
    return {
        "agent_output": response.content,
        "is_producing": False,  # 共创不产出字段内容
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "duration_ms": response.duration_ms,
    }
```

### 5.8 对话历史：分离显示 + 上下文自动桥接

#### 前端：两个 Tab

```tsx
// agent-panel.tsx
const [agentMode, setAgentMode] = useState<"assistant" | "cocreation">("assistant");

// 消息过滤
const displayMessages = messages.filter(
  msg => (msg.metadata?.mode || "assistant") === agentMode
);

// Tab 切换时，在消息流中插入分隔符（可选）
```

#### 后端：消息加载 + 上下文桥接

消息加载（按 mode 过滤）：

```python
def load_messages(project_id: str, mode: str, limit: int = 50):
    """加载指定 mode 的消息"""
    return db.query(ChatMessage).filter(
        ChatMessage.project_id == project_id,
        # JSON 字段查询：sqlite 的 json_extract
        func.json_extract(ChatMessage.message_metadata, "$.mode") == mode,
    ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
```

**上下文桥接（共创→助手方向，单向）**：

```python
def build_assistant_context_with_bridge(project_id: str) -> str:
    """
    为助手模式构建上下文时，自动注入最近的共创对话摘要。
    规则：
    - 只注入共创→助手方向（助手能看到共创内容）
    - 反方向不注入（共创角色不需要知道助手做了什么）
    - 只注入最近 1 次共创会话（最近 5 轮 = 10 条消息）
    """
    recent_cocreation = db.query(ChatMessage).filter(
        ChatMessage.project_id == project_id,
        func.json_extract(ChatMessage.message_metadata, "$.mode") == "cocreation",
    ).order_by(ChatMessage.created_at.desc()).limit(10).all()
    
    if not recent_cocreation:
        return ""
    
    recent_cocreation.reverse()  # 时间正序
    
    persona_name = recent_cocreation[0].message_metadata.get("persona_name", "角色")
    
    bridge = f"\n\n【参考：最近与「{persona_name}」的共创对话】\n"
    for msg in recent_cocreation:
        speaker = persona_name if msg.role == "assistant" else "用户"
        bridge += f"  {speaker}: {msg.content[:300]}\n"
    bridge += "【共创对话结束】\n"
    bridge += "如果用户提到"刚才的对话""角色说的"等，请参考上面的共创记录。\n"
    bridge += "如果用户没有提及，不需要主动引用这些内容。\n"
    
    return bridge
```

**注入位置**：在助手模式所有节点（chat_node, modify_node, query_node 等）的 system prompt 末尾追加。

#### 上下文桥接流程图

```
┌──────────────────────────────────────────────────┐
│                 chat_messages 表                  │
│  ┌─────────────────┐  ┌────────────────────────┐ │
│  │ mode=assistant   │  │  mode=cocreation       │ │
│  │ 用户: 生成场景库  │  │  用户: @场景库 怎么样？ │ │
│  │ 助手: ✅已生成    │  │  🎭学生A: 不错但...    │ │
│  │ ...              │  │  ...                   │ │
│  └────────┬────────┘  └──────────┬─────────────┘ │
│           │                      │                │
└───────────┼──────────────────────┼────────────────┘
            │                      │
            ▼                      │
  ┌─────────────────────┐          │
  │ 助手 mode context   │ ◄────────┘  ✅ 自动桥接（只读注入最近共创对话）
  │ = 助手历史           │
  │ + 共创桥接摘要       │
  │ + 字段索引           │
  └─────────────────────┘

            ▲
            │ ✘ 不注入（共创角色不知道助手的存在）
            │
  ┌─────────────────────┐
  │ 共创 mode context   │
  │ = 共创历史（仅当前角色）│
  │ + 角色设定           │
  │ + @ 引用的字段内容    │
  └─────────────────────┘
```

### 5.9 前端实现细节

文件：`frontend/components/agent-panel.tsx`

**新增状态**：

```typescript
// Mode 切换
const [agentMode, setAgentMode] = useState<"assistant" | "cocreation">("assistant");

// 共创角色
const [currentPersona, setCurrentPersona] = useState<{
  id: string;
  name: string;
  prompt: string;
} | null>(null);

// 共创角色配置面板是否展开
const [showPersonaConfig, setShowPersonaConfig] = useState(true);
```

**Tab 切换 UI**：

```tsx
<div className="flex border-b border-surface-3">
  <button
    onClick={() => setAgentMode("assistant")}
    className={cn(
      "flex-1 py-2 text-sm font-medium transition-colors",
      agentMode === "assistant"
        ? "text-brand-400 border-b-2 border-brand-400"
        : "text-zinc-500 hover:text-zinc-300"
    )}
  >
    🤖 助手
  </button>
  <button
    onClick={() => setAgentMode("cocreation")}
    className={cn(
      "flex-1 py-2 text-sm font-medium transition-colors",
      agentMode === "cocreation"
        ? "text-purple-400 border-b-2 border-purple-400"
        : "text-zinc-500 hover:text-zinc-300"
    )}
  >
    🎭 共创
  </button>
</div>
```

**发送消息时传递 mode**：

```typescript
body: JSON.stringify({
  project_id: projectId,
  message: userMessage,
  references,
  current_phase: currentPhase || undefined,
  update_prompt: agentMode === "assistant" ? updatePrompt : false,
  mode: agentMode,
  persona_config: agentMode === "cocreation" ? currentPersona : undefined,
}),
```

**消息气泡区分**（共创模式下 AI 消息的样式）：

```tsx
// 共创模式下的 AI 消息：紫色调，显示角色名
const isCocreation = message.metadata?.mode === "cocreation";
const personaName = message.metadata?.persona_name;

<div className={cn(
  "px-4 py-2 rounded-2xl",
  isUser
    ? "bg-brand-600 text-white rounded-br-md"
    : isCocreation
      ? "bg-purple-900/40 text-zinc-200 rounded-bl-md border border-purple-500/20"
      : "bg-surface-3 text-zinc-200 rounded-bl-md"
)}>
  {!isUser && isCocreation && personaName && (
    <div className="text-xs text-purple-400 font-medium mb-1">🎭 {personaName}</div>
  )}
  {/* ... message content ... */}
</div>
```

### 5.10 Persona CRUD API

文件：`backend/api/projects.py`（追加）

```python
@router.get("/{project_id}/cocreation-personas")
def list_cocreation_personas(project_id: str, db: Session = Depends(get_db)):
    """
    获取共创角色列表（全局预置 + 项目人物 + 自建角色）
    """
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    
    result = {
        "presets": COCREATION_PRESETS,
        "project_personas": _get_project_personas(project_id, db),
        "custom": project.cocreation_personas or [],
    }
    return result


@router.post("/{project_id}/cocreation-personas")
def save_cocreation_persona(
    project_id: str,
    body: dict,  # {"name": str, "prompt": str}
    db: Session = Depends(get_db),
):
    """保存自建共创角色"""
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    
    personas = project.cocreation_personas or []
    new_persona = {
        "id": f"custom_{uuid.uuid4().hex[:8]}",
        "name": body.get("name", "自定义角色"),
        "prompt": body.get("prompt", ""),
    }
    personas.append(new_persona)
    project.cocreation_personas = personas
    db.commit()
    
    return new_persona


@router.delete("/{project_id}/cocreation-personas/{persona_id}")
def delete_cocreation_persona(
    project_id: str,
    persona_id: str,
    db: Session = Depends(get_db),
):
    """删除自建共创角色"""
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    
    personas = project.cocreation_personas or []
    personas = [p for p in personas if p.get("id") != persona_id]
    project.cocreation_personas = personas
    db.commit()
    
    return {"status": "ok"}


def _get_project_personas(project_id: str, db: Session) -> list:
    """从 eval 系统的人物库读取 persona"""
    field = db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
        ProjectField.phase == "research",
    ).first()
    if not field or not field.content:
        return []
    try:
        import json
        data = json.loads(field.content)
        raw_personas = data.get("personas", [])
        return [
            {
                "id": p.get("id", f"proj_{i}"),
                "name": p.get("name", "未命名"),
                "prompt": f"你是{p.get('name', '一个用户')}。\n背景：{p.get('background', '')}\n痛点：{'、'.join(p.get('pain_points', []))}\n行为特征：{'、'.join(p.get('behaviors', []))}",
            }
            for i, p in enumerate(raw_personas)
        ]
    except Exception:
        return []
```

---

## 六、实施顺序

### Phase 1: 基建（无 UI 变化）
1. 迁移脚本：ProjectField / ContentBlock 加 `digest` 列
2. 迁移脚本：Project 加 `cocreation_personas` 列
3. `backend/core/edit_engine.py`：`apply_edits()` + `generate_revision_markdown()`
4. `backend/core/digest_service.py`：摘要生成 + 字段索引构建
5. `npm install rehype-raw`

### Phase 2: 话题二 — 平台记忆
6. 所有内容保存触发点加 `trigger_digest_update()`
7. 所有 LLM 节点的 system prompt 注入 `field_index_block`
8. route_intent 输出 `required_fields`，节点执行前获取全文

### Phase 3: 话题三 — 精细编辑
9. modify_node 重写（新提示词 + edits JSON 输出 + need_confirm 判断）
10. SSE 新增 `modify_preview` / `modify_confirm_needed` 事件
11. `POST /api/fields/{id}/accept-changes` endpoint
12. 前端 `RevisionView` 组件
13. ReactMarkdown 启用 rehypeRaw + del/ins 样式
14. 字段面板集成 RevisionView（收到 modify_preview 事件时切换到修订模式）

### Phase 4: 话题一 — 提示词更新
15. ChatRequest 新增 `update_prompt` + `mode` 字段
16. 前端 toggle "同步修改提示词"
17. `prompt_plan_node` + `prompt_execute_node`
18. SSE `pending_prompt_update` 事件 → 前端自动触发 Phase B
19. 提示词修订预览（复用 `generate_revision_markdown`）

### Phase 5: 话题四 — 共创模式
20. `COCREATION_PRESETS` 全局角色常量定义
21. `cocreation_node` 实现（orchestrator.py）
22. 后端路由分流（mode="cocreation" 时跳过 route_intent）
23. 上下文桥接函数 `build_assistant_context_with_bridge()`
24. Persona CRUD API（list / save / delete）
25. 前端 Agent 面板 tab 切换 + persona 配置区
26. 前端 PersonaSelector 组件（三层来源）
27. 消息加载按 mode 过滤 + 共创消息视觉区分
28. 前端发送消息传递 mode + persona_config

---

## 七、风险与 Fallback

| 风险 | 应对 |
|------|------|
| LLM 输出的 edits JSON 格式不对 | `json.JSONDecoder().raw_decode()` + fallback 到纯文本（兼容现有行为） |
| anchor 在原文中找不到 | edit 标记为 failed，告知用户；如果所有 edits 都失败，回退到确认模式 |
| anchor 不唯一 | edit 标记为 failed，提示 LLM 需要更长的引用 |
| 摘要生成延迟（字段刚更新后立刻请求） | 索引中显示"有内容，摘要生成中"，不影响功能 |
| rehypeRaw 导致用户内容中的 HTML 被意外渲染 | 只在修订模式下启用 rehypeRaw；正常渲染模式不启用 |
| 大段内容的 diff 过于碎片化 | 如果 changes 超过 15 个，提示用户"修改较多，建议逐段确认" |
| 共创角色跳出角色 | system prompt 强约束 + temperature=0.8 保持创造性但守住角色边界 |
| 共创→助手上下文桥接不够精确 | 桥接最近 10 条消息 + 标签说明；用户也可以在助手模式显式 @ 引用 |
| 共创对话过长导致 context window 溢出 | 共创历史限制最近 20 条；超过后提示用户"建议开始新会话" |

---

# 八、逐步执行手册（Execution Spec）

> 以下是每一步修改的**精确执行指令**。每一步都标注了：
> - 目标文件的绝对路径
> - 修改类型（新建文件 / 在指定位置插入 / 替换指定代码段）
> - 完整的代码（含所有 import）
> - 输入输出契约
> - 验证方法
>
> **约定**：所有路径相对于项目根 `content-production-system-2/`

---

## Phase 1: 基建（无 UI 变化）

### Step 1.1 — 新建 `backend/core/edit_engine.py`

**类型**: 新建文件
**依赖**: 无

```python
# backend/core/edit_engine.py
"""
编辑引擎 - 将 LLM 输出的 edits 确定性地应用到原始内容上
主要函数: apply_edits(), generate_revision_markdown()
"""
import difflib
from typing import Optional


def apply_edits(
    original: str,
    edits: list[dict],
    accepted_ids: set[str] | None = None,
) -> tuple[str, list[dict]]:
    """
    将编辑操作应用到原始内容。

    输入:
        original  - 原始内容字符串
        edits     - 编辑操作列表，每个元素:
                     {"type": "replace"|"insert_after"|"insert_before"|"delete",
                      "anchor": str,   # 原文精确引用
                      "new_text": str}  # 替换/插入内容（delete 时为 ""）
        accepted_ids - 如果提供，只应用这些 ID 的 edits（部分接受）
                       None 表示应用所有

    输出:
        (modified_content, changes)
        changes 列表每个元素:
            {**edit, "id": str, "old_text": str|None,
             "status": "applied"|"failed"|"rejected",
             "reason": str|None,
             "position": {"start": int, "end": int}}
    """
    result = original
    changes = []

    # 1. 分配 ID
    for i, edit in enumerate(edits):
        if "id" not in edit:
            edit["id"] = f"e{i}"

    # 2. 定位并排序（从后往前，避免偏移）
    positioned_edits = []
    for edit in edits:
        anchor = edit.get("anchor", "")
        pos = original.find(anchor)
        positioned_edits.append((pos, edit))
    positioned_edits.sort(key=lambda x: x[0], reverse=True)

    # 3. 逐个处理
    for pos, edit in positioned_edits:
        edit_id = edit["id"]
        anchor = edit.get("anchor", "")
        new_text = edit.get("new_text", "")
        edit_type = edit.get("type", "replace")

        # 3a. 部分接受检查
        if accepted_ids is not None and edit_id not in accepted_ids:
            changes.append({
                **edit,
                "status": "rejected",
                "reason": None,
                "position": {"start": pos, "end": pos + len(anchor) if pos >= 0 else -1},
            })
            continue

        # 3b. anchor 找不到
        if pos == -1:
            changes.append({
                **edit,
                "status": "failed",
                "reason": "anchor_not_found",
                "position": {"start": -1, "end": -1},
            })
            continue

        # 3c. anchor 不唯一
        if result.count(anchor) > 1:
            changes.append({
                **edit,
                "status": "failed",
                "reason": "anchor_not_unique",
                "position": {"start": pos, "end": pos + len(anchor)},
            })
            continue

        # 3d. 执行编辑
        if edit_type == "replace":
            result = result[:pos] + new_text + result[pos + len(anchor):]
            changes.append({
                **edit, "old_text": anchor,
                "status": "applied", "reason": None,
                "position": {"start": pos, "end": pos + len(new_text)},
            })
        elif edit_type == "insert_after":
            insert_pos = pos + len(anchor)
            result = result[:insert_pos] + "\n" + new_text + result[insert_pos:]
            changes.append({
                **edit, "old_text": None,
                "status": "applied", "reason": None,
                "position": {"start": insert_pos + 1, "end": insert_pos + 1 + len(new_text)},
            })
        elif edit_type == "insert_before":
            result = result[:pos] + new_text + "\n" + result[pos:]
            changes.append({
                **edit, "old_text": None,
                "status": "applied", "reason": None,
                "position": {"start": pos, "end": pos + len(new_text)},
            })
        elif edit_type == "delete":
            result = result[:pos] + result[pos + len(anchor):]
            changes.append({
                **edit, "old_text": anchor,
                "status": "applied", "reason": None,
                "position": {"start": pos, "end": pos},
            })

    return result, changes


def generate_revision_markdown(old: str, new: str) -> str:
    """
    生成带修订标记的 markdown。删除用 <del>，新增用 <ins>。

    输入: old - 修改前文本, new - 修改后文本
    输出: 带 <del>/<ins> 标签的字符串
    """
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

**验证**: `cd backend && python -c "from core.edit_engine import apply_edits, generate_revision_markdown; print('OK')"`

---

### Step 1.2 — 新建 `backend/core/digest_service.py`

**类型**: 新建文件
**依赖**: `core.ai_client`, `core.database`, `core.models`

```python
# backend/core/digest_service.py
"""
字段摘要服务
在字段内容更新后异步生成一句话摘要
构建全量字段索引注入 system prompt
"""
import asyncio
import logging

from core.ai_client import ai_client, ChatMessage
from core.models.project_field import ProjectField
from core.models.content_block import ContentBlock
from core.database import get_db

logger = logging.getLogger("digest")


async def generate_digest(content: str) -> str:
    """
    用小模型生成一句话摘要

    输入: content - 字段内容（取前 3000 字）
    输出: 摘要字符串（<=200 字符），内容过短返回 ""
    """
    if not content or len(content.strip()) < 10:
        return ""
    messages = [
        ChatMessage(
            role="user",
            content=f"用一句话概括以下内容的核心主题和要点（不超过50字，只输出摘要本身）：\n\n{content[:3000]}"
        ),
    ]
    try:
        response = await ai_client.async_chat(messages, temperature=0, model="gpt-4o-mini")
        return response.content.strip()[:200]
    except Exception as e:
        logger.warning(f"[Digest] 生成摘要失败: {e}")
        return ""


def trigger_digest_update(entity_id: str, entity_type: str, content: str):
    """
    非阻塞地触发摘要更新。在字段内容保存后调用。

    输入:
        entity_id   - ProjectField.id 或 ContentBlock.id
        entity_type - "field" | "block"
        content     - 字段内容
    输出: 无（后台执行）
    """
    async def _do_update():
        try:
            digest = await generate_digest(content)
            if not digest:
                return
            db = next(get_db())
            try:
                if entity_type == "field":
                    entity = db.query(ProjectField).filter_by(id=entity_id).first()
                else:
                    entity = db.query(ContentBlock).filter_by(id=entity_id).first()
                if entity:
                    entity.digest = digest
                    db.commit()
                    logger.info(f"[Digest] {entity_type} {entity_id[:8]}: {digest[:50]}")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[Digest] 更新失败: {e}")

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_do_update())
        else:
            asyncio.run(_do_update())
    except RuntimeError:
        pass


def build_field_index(project_id: str) -> str:
    """
    构建项目的全量字段摘要索引。

    输入: project_id
    输出: 格式化字符串（每行一个字段: "- 字段名 [状态]: 摘要"），空项目返回 ""
    """
    db = next(get_db())
    try:
        entries = []
        fields = db.query(ProjectField).filter(
            ProjectField.project_id == project_id,
        ).all()
        for f in fields:
            status_label = {
                "pending": "待生成", "generating": "生成中",
                "completed": "已完成", "failed": "失败",
            }.get(f.status, f.status)
            digest = getattr(f, 'digest', None) or (
                "（有内容，摘要生成中）" if f.content else "（空）"
            )
            entries.append(f"- {f.name} [{status_label}]: {digest}")

        blocks = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.block_type == "field",
            ContentBlock.deleted_at == None,
        ).all()
        for b in blocks:
            status_label = {
                "pending": "待处理", "in_progress": "进行中",
                "completed": "已完成",
            }.get(b.status, b.status)
            digest = getattr(b, 'digest', None) or (
                "（有内容，摘要生成中）" if b.content else "（空）"
            )
            entries.append(f"- {b.name} [{status_label}]: {digest}")

        return "\n".join(entries) if entries else ""
    finally:
        db.close()
```

**验证**: `cd backend && python -c "from core.digest_service import build_field_index; print('OK')"`

---

### Step 1.3 — 迁移脚本 `backend/scripts/migrate_add_digest.py`

**类型**: 新建文件

```python
# backend/scripts/migrate_add_digest.py
"""迁移脚本: 为 ProjectField 和 ContentBlock 添加 digest 列"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "content_production.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for table in ["project_fields", "content_blocks"]:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN digest TEXT")
            print(f"Added 'digest' column to {table}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"Column 'digest' already exists in {table}")
            else:
                raise
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
```

**执行**: `cd backend && python scripts/migrate_add_digest.py`

---

### Step 1.4 — Model 层: ProjectField 添加 digest 属性

**文件**: `backend/core/models/project_field.py`

在 `generation_log_id` 定义（约第89-91行）之后、`# 关联` 注释（约第93行）之前插入:

```python
    # 一句话摘要（<=50字，异步生成）
    digest: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
```

---

### Step 1.5 — Model 层: ContentBlock 添加 digest 属性

**文件**: `backend/core/models/content_block.py`

在 `is_collapsed` 属性（约第135行）之后、`# 软删除` 注释（约第137行）之前插入:

```python
    # 一句话摘要（<=50字，异步生成）
    digest: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
```

---

### Step 1.6 — 前端安装 rehype-raw

**执行**: `cd frontend && npm install rehype-raw`

---

## Phase 2: 平台记忆

### Step 2.1 — 摘要触发: `_save_result_to_field()`

**文件**: `backend/api/agent.py`

**2.1a** — 文件顶部 import 区追加:

```python
from core.digest_service import trigger_digest_update
```

**2.1b** — `_save_result_to_field` 函数末尾（约第293行），将 `return field_updated` 替换为:

```python
    # 触发摘要更新
    if field_updated and agent_output:
        fid = field_updated.get("id", "")
        if fid:
            etype = "field" if field_updated.get("phase") else "block"
            trigger_digest_update(fid, etype, agent_output)

    return field_updated
```

---

### Step 2.2 — 摘要触发: `PUT /api/fields/{id}`

**文件**: `backend/api/fields.py`

**2.2a** — 顶部追加:

```python
from core.digest_service import trigger_digest_update
```

**2.2b** — `update_field` 函数的 `db.commit()` 之后、`return` 之前追加:

```python
    if body.content is not None and field.content:
        trigger_digest_update(field.id, "field", field.content)
```

---

### Step 2.3 — 摘要触发: `PUT /api/blocks/{id}`

**文件**: `backend/api/blocks.py`

**2.3a** — 顶部追加:

```python
from core.digest_service import trigger_digest_update
```

**2.3b** — block 更新 endpoint 的 `db.commit()` 之后追加:

```python
    if hasattr(body, 'content') and body.content is not None and block.content:
        trigger_digest_update(block.id, "block", block.content)
```

---

### Step 2.4 — orchestrator.py: 字段索引构建辅助函数

**文件**: `backend/core/orchestrator.py`

**2.4a** — 顶部追加:

```python
from core.digest_service import build_field_index
```

**2.4b** — `normalize_consumer_personas` 之后、`ContentProductionState` 之前插入:

```python
def build_field_index_block(project_id: str) -> str:
    """
    构建字段索引注入块。
    输入: project_id
    输出: 可直接拼接到 system prompt 的字符串。无字段时返回 ""。
    """
    fi = build_field_index(project_id)
    if not fi:
        return ""
    return f"""

## 项目字段索引
以下是本项目所有字段及其摘要。
用途：帮你定位与用户指令相关的字段。
注意：摘要只是索引，不是完整内容。不要基于摘要猜测或编造内容。

{fi}
"""
```

---

### Step 2.5 — 所有 LLM 节点注入字段索引

在以下节点函数中，system_prompt 构建完毕后（调用 ai_client 之前），追加:

```python
    # 注入字段索引
    field_index_block = build_field_index_block(project_id)
    system_prompt += field_index_block
```

需要修改的节点:

| # | 函数名 | 文件 |
|---|--------|------|
| 1 | modify_node | orchestrator.py（Step 3.1 已包含） |
| 2 | query_node | orchestrator.py |
| 3 | chat_node | orchestrator.py |
| 4 | intent_analysis_node | orchestrator.py |
| 5 | design_inner_node | orchestrator.py |
| 6 | produce_inner_node | orchestrator.py |
| 7 | design_outer_node | orchestrator.py |
| 8 | produce_outer_node | orchestrator.py |
| 9 | evaluate_node | orchestrator.py |
| 10 | tool_node | orchestrator.py |
| 11 | generate_field_node | orchestrator.py |

同时修改 agent.py 的 `_build_chat_system_prompt`:

**2.5a** — 函数签名新增 `project_id: str = ""` 参数

**2.5b** — return 前追加:

```python
    field_index_section = ""
    if project_id:
        from core.digest_service import build_field_index
        fi = build_field_index(project_id)
        if fi:
            field_index_section = f"\n\n## 项目字段索引\n{fi}\n\n注意：以上是摘要索引，不要基于摘要猜测或编造内容。"
```

**2.5c** — 调用处传入 `project_id=request.project_id`

---

### Step 2.6 — route_intent 输出 required_fields

**文件**: `backend/core/orchestrator.py`

**2.6a** — `ContentProductionState` 新增字段:

```python
    extra_referenced_contents: Dict[str, str]
```

**2.6b** — LLM 意图分类 JSON 输出格式追加:

```
"required_fields": ["字段名1", "字段名2"]
```

**2.6c** — route_intent 返回值构建前（约第497行）追加:

```python
    required_fields_raw = current_intent.get("required_fields", [])
    already_referenced = set(references)
    required_fields = [f for f in required_fields_raw if f not in already_referenced][:5]
    extra_referenced_contents = {}
    if required_fields:
        for fn in required_fields:
            fd = get_field_content(state.get("project_id", ""), fn)
            if fd and fd.get("content"):
                extra_referenced_contents[fn] = fd["content"]
```

**2.6d** — 返回 dict 追加 `"extra_referenced_contents": extra_referenced_contents`

---

## Phase 3: 精细编辑

### Step 3.1 — modify_node 重写

**文件**: `backend/core/orchestrator.py`
**类型**: 替换整个 `modify_node` 函数体（约第1300-1433行）

核心变化点:
1. JSON 内容（方案等）仍走旧逻辑（全量替换）
2. Markdown/文本走新的 edits JSON 逻辑
3. 新增 `need_confirm` 分支 -> 返回 `pending_edits`
4. 直接执行分支 -> 调用 `apply_edits()` -> 返回 `modify_result`
5. JSON 解析失败 -> 降级为全量替换（向后兼容）

新 system prompt（Markdown/文本分支）:

```
你是一个精确的内容编辑器。你的任务是将用户的修改指令转化为具体的编辑操作。

## 当前项目
{creator_profile}

## 目标字段：{target_field}
{original_content}

{ref_section}

## 用户指令
{operation}

## 你的工作
1. 理解用户想要做什么修改
2. 将修改转化为具体的 edits（编辑操作列表）
3. 判断是否需要用户确认：
   - 指令清晰、无歧义 -> need_confirm: false
   - 指令有多种理解方式，或影响范围不确定 -> need_confirm: true

## edit 类型
- replace: 替换。anchor 是要被替换的原文，new_text 是替换后的内容
- insert_after: 在 anchor 之后插入 new_text
- insert_before: 在 anchor 之前插入 new_text
- delete: 删除 anchor 指定的内容

## 关键规则
- anchor 必须是原文中**逐字逐句精确存在**的片段，不要改动或概括
- anchor 必须在原文中**唯一**。如果目标片段出现多次，加长引用直到唯一
- 只输出需要变更的部分。用户没提到的内容不要动
- 表格中的 anchor 应该包含整行（从 | 到 |）

## Markdown 格式硬性要求
- 表格每一行的列数必须与表头完全一致
- 单元格内多条内容用 <br> 换行
- 表格必须有表头分隔行
- 表格每行必须以 | 开头以 | 结尾

## 输出格式（严格 JSON）
{
  "edits": [
    {"type": "replace", "anchor": "原文精确引用", "new_text": "替换后的内容"},
    {"type": "insert_after", "anchor": "原文精确引用", "new_text": "要插入的内容"},
    {"type": "delete", "anchor": "原文精确引用", "new_text": ""}
  ],
  "need_confirm": false,
  "summary": "简述改了什么",
  "ambiguity": null
}

只输出 JSON，不要有其他内容。
```

---

### Step 3.2 — ContentProductionState 新增字段

**文件**: `backend/core/orchestrator.py`

在 `pending_intents` 之后追加:

```python
    modify_result: Optional[dict]
    pending_edits: Optional[dict]
    pending_prompt_plan: Optional[dict]
```

同时在 agent.py 的 `initial_state` 构建处补充默认值:

```python
    "modify_result": None,
    "pending_edits": None,
    "pending_prompt_plan": None,
    "extra_referenced_contents": {},
```

---

### Step 3.3 — SSE 事件传递 modify_result / pending_edits

**文件**: `backend/api/agent.py`

在 `display_content = _build_chat_display(...)` 之后、`yield ... type: content` 之前插入:

```python
            modify_result = result.get("modify_result")
            if modify_result:
                yield f"data: {json.dumps({'type': 'modify_preview', 'target_field': result.get('modify_target_field'), 'original_content': modify_result['original_content'], 'new_content': modify_result['new_content'], 'changes': modify_result['changes'], 'summary': modify_result['summary']}, ensure_ascii=False)}\n\n"

            pending_edits = result.get("pending_edits")
            if pending_edits:
                yield f"data: {json.dumps({'type': 'modify_confirm_needed', 'target_field': pending_edits['target_field'], 'edits': pending_edits['edits'], 'summary': pending_edits['summary']}, ensure_ascii=False)}\n\n"
```

---

### Step 3.4 — 部分接受 API

**文件**: `backend/api/fields.py`
**类型**: 文件末尾追加新 endpoint

```python
class AcceptChangesBody(BaseModel):
    """接受部分修改请求"""
    original_content: str
    edits: list
    accepted_ids: List[str] = []


@router.post("/{field_id}/accept-changes")
def accept_changes(
    field_id: str,
    body: AcceptChangesBody,
    db: Session = Depends(get_db),
):
    """
    接受部分修改。用户逐条接受/拒绝后，后端只应用被接受的 edits。

    输入:
        field_id              - ProjectField.id 或 ContentBlock.id
        body.original_content - 原始内容
        body.edits            - 完整 edits 列表
        body.accepted_ids     - 用户接受的 edit ID 列表
    输出:
        {"status": "ok", "applied_count": N, "rejected_count": M}
    """
    from core.edit_engine import apply_edits
    from core.models.content_block import ContentBlock

    new_content, changes = apply_edits(
        body.original_content, body.edits,
        accepted_ids=set(body.accepted_ids),
    )

    field = db.query(ProjectField).filter_by(id=field_id).first()
    if field:
        _save_field_version(field, "agent_modify", db)
        field.content = new_content
        trigger_digest_update(field.id, "field", new_content)
    else:
        block = db.query(ContentBlock).filter_by(id=field_id).first()
        if not block:
            raise HTTPException(status_code=404, detail="Field/Block not found")
        block.content = new_content
        trigger_digest_update(block.id, "block", new_content)

    db.commit()
    return {
        "status": "ok",
        "applied_count": len([c for c in changes if c["status"] == "applied"]),
        "rejected_count": len([c for c in changes if c["status"] == "rejected"]),
    }
```

---

### Step 3.5 — 前端 RevisionView 组件

**文件**: `frontend/components/revision-view.tsx`（新建）

> 包含: Change 接口定义、RevisionView 组件、工具栏（接受全部/拒绝全部/完成/取消）、逐条 toggle、ReactMarkdown+rehypeRaw 渲染。
> 详细代码见上方「三、字段精细编辑」章节完整描述。

核心 props:

```typescript
interface RevisionViewProps {
  originalContent: string;
  changes: Change[];
  summary: string;
  onFinalize: (acceptedIds: string[]) => void;
  onCancel: () => void;
}
```

---

### Step 3.6 — 前端 CSS

**文件**: `frontend/app/globals.css`（末尾追加）

```css
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
```

---

### Step 3.7 — 前端 agent-panel 处理新 SSE 事件

**文件**: `frontend/components/agent-panel.tsx`

在 SSE 事件处理中追加 `modify_preview` 和 `modify_confirm_needed` 分支。

---

## Phase 4: 提示词更新

### Step 4.1 — ChatRequest 新增字段

**文件**: `backend/api/agent.py`

ChatRequest 追加:

```python
    update_prompt: bool = False
    mode: Optional[str] = None  # "prompt_plan" | "prompt_execute" | None
```

---

### Step 4.2 — 辅助函数

**文件**: `backend/api/agent.py`

追加 `get_field_ai_prompt(project_id, field_name) -> str|None` 和 `save_prompt_update(project_id, field_name, new_prompt, old_prompt)` 两个函数。

---

### Step 4.3 — prompt_plan_node / prompt_execute_node

**文件**: `backend/core/orchestrator.py`

在 `modify_node` 之后追加。

`prompt_plan_node` 的 system prompt:

```
你要为一个字段的生成提示词做修改计划。

## 当前提示词（字段：{target_field}）
{current_prompt}

## 用户的修改要求
{user_input}

## 输出要求
以"所见即所得"的方式，对于每处改动，直接给出：
- 原句：「引用当前提示词中的原文」
  改为：「修改后的具体文字」

如果新要求和现有规则有冲突，简要指出冲突在哪。
不要输出其他内容。
```

`prompt_execute_node` 的 system prompt:

```
你要按照已确认的修改计划，修改一个字段的生成提示词。

## 当前提示词
{current_prompt}

## 已确认的修改计划
{plan}

## 输出要求
输出修改后的完整提示词。只输出提示词本身。
```

---

### Step 4.4 — stream_chat: mode 快捷分发

**文件**: `backend/api/agent.py`

在 `# ===== 唯一路由决策 =====` 之前插入 mode 分支:
- `mode == "prompt_plan"` -> 调用 prompt_plan_node
- `mode == "prompt_execute"` -> 调用 prompt_execute_node

---

### Step 4.5 — SSE done 事件追加字段

在 done JSON 追加:

```python
'pending_prompt_update': bool,
'prompt_target_field': str,
```

---

### Step 4.6 — ContentVersion 新增 source 类型

**文件**: `backend/core/models/content_version.py`

VERSION_SOURCES 追加:

```python
    "agent_modify": "Agent 精细编辑",
    "prompt_update": "提示词修改",
```

---

### Step 4.7 — 前端 toggle "同步修改提示词"

**文件**: `frontend/components/agent-panel.tsx`

- 新增 `updatePrompt` state
- fetch body 追加 `update_prompt: updatePrompt`
- textarea 上方追加 checkbox UI
- SSE done 处理 `pending_prompt_update` 事件

---

## 九、执行前检查清单

| 检查项 | 说明 |
|--------|------|
| import 完整 | 新函数引用的模块是否在文件顶部导入 |
| 参数传递链 | 新参数是否从调用方一路传到被调用方 |
| 类型定义 | 新增的 state 字段是否在 ContentProductionState 中声明 |
| 数据库列 | 新增的列是否同时出现在 Model 和迁移脚本中 |
| SSE 事件 | 新增的事件类型是否在前端有对应的处理分支 |
| 向后兼容 | 新增字段是否有默认值，不影响已有数据 |

---

## 十、执行后验证清单

| 阶段 | 验证方法 |
|------|----------|
| Phase 1 | 1. 迁移脚本无报错 2. `from core.edit_engine import apply_edits` 成功 3. `from core.digest_service import build_field_index` 成功 |
| Phase 2 | 1. 修改字段后 digest 有值 2. system prompt 末尾出现字段索引 3. route_intent 输出含 required_fields |
| Phase 3 | 1. `@字段 把X改成Y` → edits JSON → apply_edits 成功 2. SSE 含 modify_preview 3. accept-changes 返回 200 |
| Phase 4 | 1. toggle → done 含 pending_prompt_update 2. prompt_plan 返回计划 3. prompt_execute 更新并返回预览 |
| Phase 5 | 1. 共创 tab 切换正常 2. 选择角色后对话返回角色扮演内容 3. 切回助手后，助手能引用共创对话 4. Persona CRUD 正常 |
