# Suggestion Card：从 Diff 到修改闭环的第一性原理设计

> 创建时间：2026-02-15
> 前置文档：`first_principles.md`、`implementation_plan_v3.md`
> 性质：从第一性原理出发的修改闭环系统设计，包含现状分析、方案推演、模块关系、System Prompt 工程、Milestone 和 Todo

---

## 一、问题的本质

### 1.1 第一性原理：修改是内容生产中最高频也最高风险的操作

内容生产系统的核心循环是：**生成 → 评估 → 修改 → 再评估**。

其中"修改"这个环节有两个根本特征：

1. **它是决策，不是执行。** 修改意味着"我认为当前内容不够好，应该往这个方向调整"。这是一个判断（judgment），不是一个计算（computation）。如果 Agent 自主执行修改，实质上是 Agent 替用户做了决策——这在早期信任尚未建立时，用户会感到不安。

2. **它的成本模型是非对称的。** 生成一段新内容的成本 ≈ 一次 LLM 调用。但修改一段已有内容如果改错了，用户需要：发现错误 → 理解错在哪 → 撤销 → 重新描述需求 → 再次修改。错误修改的恢复成本远高于修改本身的执行成本。

因此，修改的最佳交互模式是：

> **Agent 展示修改意图（Suggest）→ 用户确认或追问（Confirm / Follow-up）→ 系统执行（Apply）→ 可撤回（Undo）**

这就是 Suggestion Card 要解决的核心问题。

### 1.2 为什么现在才做这件事

回顾项目的演进，修改闭环经历了三个阶段：

| 阶段 | 时间 | 设计 | 实际状态 |
|------|------|------|---------|
| V1 设计期 | 实现计划 v3 | `edit_engine.py` 提供 anchor-based edits + `<del>/<ins>` diff | 代码已写好，但未接入 |
| V2 LangGraph 迁移 | 架构重构 | `modify_field` 改为 @tool，system prompt 描述了 `need_confirm` 流程 | 工具直接全文覆写，从未触发 `need_confirm` |
| V3 当前讨论 | 此文档 | 统一的 Suggestion Card 作为 Agent 的原生输出格式 | 设计中 |

关键认知变化：
- **V1 阶段**思考的是"如何做精确的 diff"——这是一个**工程问题**。
- **V2 阶段**发现修改确认流程难以用简单 if-else 实现——这是一个**产品问题**。
- **V3 阶段**意识到修改建议应该是 Agent 的**原生输出格式**，而非后处理——这是一个**认知问题**。

---

## 二、现状分析：已有的组件和断裂的链条

### 2.1 已有组件清单

| 组件 | 位置 | 状态 | 能力 |
|------|------|------|------|
| `edit_engine.py` | `backend/core/edit_engine.py` | ✅ 已实现，未使用 | anchor-based edits（replace/insert/delete）+ `<del>/<ins>` diff 生成 |
| `modify_field` tool | `backend/core/agent_tools.py:91-183` | ⚠️ 实现与设计不符 | 全文覆写，始终返回 `status="applied"`，无确认流程 |
| `modify_confirm_needed` SSE | `backend/api/agent.py:789-798` | ✅ 已实现，从未触发 | 后端解析 `need_confirm` JSON → 发 SSE 事件 |
| Agent Panel 确认 UI | `frontend/components/agent-panel.tsx:489-499` | ⚠️ 仅文本提示 | 收到 `modify_confirm_needed` 后显示文字 "请在左侧工作台查看并确认修改"，无交互按钮 |
| System Prompt 描述 | `backend/core/orchestrator.py:249-253` | ⚠️ 描述了不存在的行为 | 告诉 Agent "modify_field 可能返回 need_confirm"，但实际从未返回 |
| `version_service.py` | `backend/core/version_service.py` | ✅ 已实现 | 修改前保存旧版本（覆写前调用） |
| `api/versions.py` | `backend/api/versions.py` | ✅ 已实现 | 版本列表 + 回滚 API |
| Eval Report 诊断 | `frontend/components/eval-field-editors.tsx:1583-1601` | ✅ 已实现 | 渲染综合诊断 Markdown，无操作按钮 |
| Mode System | `backend/api/modes.py` + `orchestrator.py:61-77` | ✅ 已实现 | 多模式切换，每个模式有独立 system_prompt |

### 2.2 断裂链条：从"发现问题"到"解决问题"之间缺失的桥梁

```
                     ┌──── 通路 A: Agent 对话 ─────────────────────┐
                     │  Agent 发现修改需求                         │
用户操作             │     ↓                                      │
  ↓                  │  调用 modify_field                         │
与 Agent 交流  ──→   │     ↓                                      │
                     │  ❌ 直接全文覆写（无确认、无 diff）          │
                     └────────────────────────────────────────────┘

                     ┌──── 通路 B: Eval 报告 ─────────────────────┐
                     │  评估系统发现问题                           │
用户操作             │     ↓                                      │
  ↓                  │  生成综合诊断（Markdown 文本）              │
执行评估  ────────→  │     ↓                                      │
                     │  ❌ 止步于文字描述（无法转化为修改动作）      │
                     └────────────────────────────────────────────┘

                     ┌──── 通路 C: 用户自定义字段 ────────────────┐
                     │  用户在内容编辑器中发现问题                  │
用户操作             │     ↓                                      │
  ↓                  │  ❌ 只能手动编辑，或切到 Agent 对话描述需求   │
手动编辑  ────────→  │  （上下文割裂）                             │
                     └────────────────────────────────────────────┘
```

**三条通路的共同断裂点**：系统缺少一个统一的"修改提案"（Suggestion）数据格式和交互范式。发现问题的能力已经有了（Agent 推理、Eval 评估、用户判断），但都无法优雅地转化为**可预览、可确认、可追问、可撤回**的修改动作。

---

## 三、Suggestion Card 的核心设计

### 3.1 设计原则

从上述分析推导出四条原则：

1. **先展示意图，后执行修改**（Diff-first）。Agent 不应该自主执行修改——修改是用户的决策权。Agent 的职责是提出高质量的修改建议，展示清晰的修改预览，让用户一键确认。

2. **Suggestion Card 是 Agent 的原生输出格式**。它不是从外部数据源"汇入"的，而是 Agent 在对话中**自主判断**需要修改时，通过 Tool Call 输出的结构化提案。这使得 Suggestion Card 天然融入现有的 Tool Calling 架构。

3. **全模式可用，统一交互**。不管用户在 assistant、critic、strategist 还是任何自定义模式中对话，只要 Agent 判断需要修改，都通过同一个 `propose_edit` tool 输出 Suggestion Card。心智模型的一致性高于功能的灵活性。

4. **确认可撤回**（Undo-safe）。用户确认修改后，系统自动保存版本快照并返回 `version_id`。用户可在一定时间窗口内一键撤回。这进一步降低了确认的心理压力——"即使点错了也能回来"。

### 3.2 数据结构

```python
# === Suggestion Card 数据结构 ===

class EditOperation:
    """单个编辑操作（复用 edit_engine.py 的 edit 格式）"""
    type: str           # "replace" | "insert_after" | "insert_before" | "delete"
    anchor: str         # 原文精确引用（定位锚点）
    new_text: str       # 替换/插入的新内容（delete 时为空）

class SuggestionCard:
    """Agent 输出的修改提案（单字段）"""
    id: str                         # 唯一标识（UUID）
    group_id: str | None            # 关联的 SuggestionGroup ID（多字段修改时非空）
    target_field: str               # 目标内容块名称
    target_entity_id: str           # 目标内容块 ID（用于 Confirm/Undo）
    summary: str                    # 一句话说明修改意图（给用户看的）
    reason: str                     # 修改原因（为什么需要改）
    edits: list[EditOperation]      # 具体编辑操作列表
    # --- 以下由后端自动生成，非 LLM 输出 ---
    diff_preview: str               # <del>/<ins> 格式的修改预览（由 edit_engine 生成）
    original_content: str           # 修改前的内容快照
    modified_content: str           # 修改后的内容预览（由 edit_engine 生成）
    status: str                     # "pending" | "accepted" | "rejected" | "superseded" | "undone"
    source_mode: str                # 产生此建议的模式（assistant / critic / ...）

class SuggestionGroup:
    """多字段联动修改提案：将多个 SuggestionCard 聚合为一组"""
    group_id: str                   # 唯一标识（UUID，由首次 propose_edit 调用时生成）
    group_summary: str              # 整组修改的总体说明（"根据评估结果，需调整 3 个字段"）
    reason: str                     # 关联修改的整体原因
    cards: list[SuggestionCard]     # 组内各字段的修改卡片
    status: str                     # "pending" | "accepted" | "rejected" | "partial"
```

**Card 状态流转**：

```
                        ┌──→ accepted（已应用）──→ undone（已撤回）
                        │
pending（待确认）──────┼──→ rejected（已拒绝）
                        │
                        └──→ superseded（已被追问后的新 Card 替代）
```

### 3.3 `propose_edit`：一个"只提议、不执行"的 Tool

```python
@tool
async def propose_edit(
    target_field: str,
    summary: str,
    reason: str,
    edits: list[dict],   # [{"type": "replace", "anchor": "...", "new_text": "..."}]
    group_id: str = "",  # 多字段修改时，用同一个 group_id 关联多次调用
    group_summary: str = "",  # 仅首次调用时提供，描述整组修改的总体意图
    *, config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """向用户提出一个内容修改建议，展示修改预览供用户确认。

    ⚠️ 这是提议修改，不会直接执行。修改需要用户确认后才会应用。

    使用时机：
    - 你分析后认为某个内容块需要修改时
    - 用户要求修改但你想先展示修改计划时
    - 评估/批评后有具体的改进方向时

    不要使用的情况：
    - 还在和用户讨论、探索方向（直接用文本回复）
    - 不确定该怎么改（先和用户确认方向）

    多字段修改：
    - 当一次修改涉及多个字段，且这些修改有共同原因时，对每个字段分别调用 propose_edit
    - 所有调用使用相同的 group_id，首次调用提供 group_summary
    - 系统会自动将它们聚合为一个 SuggestionGroup 展示给用户

    Args:
        target_field: 要修改的目标内容块名称
        summary: 一句话描述修改内容（如"加强开头的吸引力"）
        reason: 为什么要做这个修改（如"当前开头过于平淡，缺少 hook"）
        edits: 编辑操作列表
        group_id: 多字段修改的组 ID（可选，留空表示单字段修改）
        group_summary: 整组修改的总体说明（仅首次调用时提供）
    """
```

**关键设计点**：

- `propose_edit` 是一个 **@tool**，注册在 `AGENT_TOOLS` 中，LLM 通过 Tool Calling 自动决定是否调用。
- 它**不写数据库**。它读取目标内容块的当前内容，调用 `edit_engine.apply_edits()` 生成预览，然后返回结构化 JSON。
- 后端在 SSE 事件流中将其作为 `suggestion_card` 类型事件发送给前端。
- 前端在 Agent Panel 中渲染为一个可交互的 Suggestion Card 组件。
- **多字段联动**：当 `group_id` 非空时，前端将多张 Card 聚合为一个 SuggestionGroup 展示。

### 3.4 Agent 何时调用 `propose_edit` vs 继续文本对话

这是整个设计中最"tricky"的部分。它不能用 if-else 硬编码——这是一个 LLM 语义判断问题。通过 system prompt 中的引导来解决。

判断标准的核心自检：**你能否写出具体的 anchor（原文定位）和 new_text（替换内容）？**
- 能 → propose_edit
- 不能 → 继续对话，和用户明确方向后再 propose

完整的 system prompt 中 propose_edit 使用规则、行动指南、意图确认模型和反模式库，详见第六章 System Prompt 工程。

### 3.5 通路 B（Eval Report）的处理：保持独立 + 未来桥接

Eval Report 产生的诊断结果**不经过 Agent Panel**。它有自己独立的展示 UI。

当前设计中，Eval Report 的综合诊断（`reportData.diagnosis`）是一段 Markdown 文本。未来可以增强为结构化数据，在 Eval Report UI 中为每条建议添加"让 Agent 修改"按钮。点击后，将该建议作为一条 HumanMessage 发送到 Agent 对话，Agent 会自然地调用 `propose_edit` 来响应。

```
Eval Report UI                    Agent Panel
┌─────────────────┐              ┌────────────────┐
│ 诊断: XXX 需改进  │  ──点击──→  │ [用户消息]       │
│ [让 Agent 修改]  │              │ "根据评估建议，  │
│                  │              │  修改 XXX..."    │
│                  │              │                 │
│                  │              │ [Suggestion Card]│
│                  │              │  Agent 的修改提案 │
└─────────────────┘              └────────────────┘
```

这样做的好处：
1. **Eval Report 保持只读/展示性质**，不承担修改执行职责
2. **修改闭环统一在 Agent Panel**，用户的心智模型一致
3. **桥接逻辑极简**：只是往 Agent 对话里发一条消息

### 3.6 SuggestionGroup：多字段联动修改

**问题**：内容生产中的修改往往不是孤立的。一次 Eval 评估可能同时发现多个字段需要调整，且这些调整之间有因果关系。例如：评估发现"受众画像过于宽泛"，连带需要调整"场景库"和"传播策略"——这三个修改共享一个原因，应该作为一个整体呈现给用户。

**从第一性原理分析**：

用户面对多字段修改时的核心需求是**一目了然**：
1. **整体 why**：这组修改的总体原因是什么？
2. **逐字段 what**：每个字段具体改了什么？
3. **原子化确认**：可以整体接受/拒绝，也可以逐字段挑选。

**方案：SuggestionGroup 聚合展示**

SuggestionGroup 是一个展示层容器，将多个 SuggestionCard 聚合在一起：

```
┌─── SuggestionGroup ─────────────────────────────────┐
│ 📋 根据评估结果，建议调整 3 个字段                     │
│ 原因：受众画像定义过于宽泛，导致场景和策略缺乏针对性     │
│                                                       │
│  ┌─ Card 1: 受众画像 ──────────────────────────────┐ │
│  │ ✏️ 缩小目标受众范围                               │ │
│  │ - 18-45岁互联网用户                              │ │
│  │ + 25-35岁一线城市的产品经理和创业者                │ │
│  │ [☑ 接受此项]                                     │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─ Card 2: 场景库 ──────────────────────────────┐   │
│  │ ✏️ 场景与缩小后的受众对齐                        │   │
│  │ - 用户在日常生活中遇到...                        │   │
│  │ + 产品经理在做竞品分析时发现...                   │   │
│  │ [☑ 接受此项]                                     │   │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─ Card 3: 传播策略 ──────────────────────────────┐ │
│  │ ✏️ 传播渠道从大众转向垂直社区                      │ │
│  │ - 微博、抖音、小红书                              │ │
│  │ + 即刻、ProductHunt、少数派                       │ │
│  │ [☑ 接受此项]                                     │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│ [✅ 全部应用] [❌ 全部拒绝] [💬 追问]                  │
└───────────────────────────────────────────────────────┘
```

**LLM 侧的认知**：

Agent 通过 system prompt 知道：当修改涉及多个字段，且这些修改**有共同的原因或因果关系**时，使用相同的 `group_id` 将多次 `propose_edit` 调用关联。LangGraph 支持 Agent 在一次响应中发出多个并行 tool call，它们自然地共享同一个 `group_id`。如果多个字段的修改**彼此独立**（偶然同时发现），则不填 `group_id`，作为独立的 Card 分别展示。

**用户侧的认知**：

- SuggestionGroup 清晰传达"这些修改是一组相关联的调整"——整体原因一目了然。
- 用户可以整体操作（全部应用/拒绝），也可以逐张 Card 取消勾选后部分应用。
- 追问时，用户的反馈上下文自动包含整个 Group 的信息。

**后端聚合逻辑**：

SSE stream 中，当检测到多个 `suggestion_card` 事件共享同一个 `group_id` 时，前端将它们聚合为一个 SuggestionGroup 组件。后端缓存中，同一个 `group_id` 下的所有 Card 也作为一组管理。

### 3.7 Undo：确认后的可撤回性

**第一性原理**：

1.1 中已建立判断：**修改的错误恢复成本远高于修改本身的执行成本**。Suggestion Card 的确认步骤降低了"改错"的概率，但无法降到零——用户可能手快点了"应用"，或应用后才发现效果不好。因此，系统需要一条**低成本的回退路径**。

**现有基础**：

项目已实现完整的版本系统：
- `version_service.py`：修改前自动保存旧版本（`save_content_version()`）
- `api/versions.py`：支持 `GET /versions/{entity_id}` 版本列表 + `POST /versions/{entity_id}/rollback/{version_id}` 回滚
- `frontend/components/version-history.tsx`：版本历史面板

唯一需要补充的是：`save_content_version()` 当前返回 `None`，需要改为返回 `version_id`，使 Confirm API 能获得回滚锚点。

**Undo 流程设计**：

```
用户点击"✅ 应用"（或 SuggestionGroup 的"✅ 全部应用"）
    ↓
Confirm API:
    1. version_service.save_content_version(old_content) → 返回 version_id
    2. edit_engine.apply_edits() → 写 DB
    3. 返回 { success: true, version_id: "xxx", entity_id: "xxx" }
    ↓
前端:
    1. Card 变为"已应用"状态（绿色边框 ✓）
    2. 显示 Toast: "修改已应用 [↩ 撤回]"
    3. Toast 持续 15 秒后自动消失
    ↓
用户点击"↩ 撤回"（在 Toast 消失前）
    ↓
前端调用 POST /api/versions/{entity_id}/rollback/{version_id}
    ↓
    1. 内容回滚到修改前的版本
    2. Card 状态变为"已撤回"（灰色 + "↩ 已撤回"标记）
    3. 刷新内容面板
```

**关键设计决策**：

- **Undo 窗口是 Toast，不是 Card 上的按钮**。Toast 是"即时撤回"的心智模型（类似 Gmail 撤回发送）。Card 上不放"撤回"按钮，避免按钮过多。
- **超过 Toast 窗口后**，用户仍可通过"版本历史"面板进行回滚（已有功能），只是路径更长。
- **SuggestionGroup 的 Undo**：整组应用后，每个字段各有一个 `version_id`。Toast 提供"全部撤回"选项，一次性回滚所有字段。

### 3.8 追问：对话式修订 Suggestion Card

**问题**：用户看到 Suggestion Card 后，可能既不想直接应用，也不想直接拒绝——而是想**在此基础上继续讨论**。类似 ChatGPT Deep Research 的报告：用户可以对报告的某些部分提出意见，AI 修订后重新呈现。

**从第一性原理分析**：

Suggestion Card 对应三种用户心理状态：
1. **确信好** → 应用
2. **确信不好** → 拒绝
3. **方向对但需要调整** → 需要继续对话

第三种状态不能简单地用"拒绝 + 重新描述"来处理，因为那样会**丢失上下文**——用户之所以选择"追问"而不是重新开始，正是因为当前 Card 已经接近正确答案，只需微调。

**追问流程**：

```
用户点击"💬 追问"
    ↓
前端:
    1. Card 进入"追问中"状态（虚线边框 + 黄色标记）
    2. 输入框获得焦点，预填："关于 [{target_field}] 的修改建议，"
    3. 输入框上方显示上下文提示："正在讨论上方的修改建议"
    ↓
用户输入追问内容（如"替换的文案太激进了，能温和一点吗？"）
    ↓
Agent 收到消息:
    - HumanMessage 包含追问文本
    - System 在消息前注入上下文:
      "[用户正在对 Suggestion #{card_id} 进行追问。
       该建议目标字段: {target_field}，修改内容: {summary}]"
    ↓
Agent 响应:
    - 可能输出文本讨论（"好的，我来调整..."）
    - 然后输出一张 **新的** Suggestion Card（替代旧的）
    ↓
前端:
    1. 旧 Card 状态变为"已替代"（灰色 + "↪ 已被新建议替代"）
    2. 新 Card 出现在对话流的最新位置
    3. 用户可继续 应用 / 拒绝 / 追问 新 Card
```

**关键设计决策**：

- **追问产生新 Card，不修改旧 Card**。保持对话历史的完整性——用户可以回看"Agent 最初建议什么 → 我提了什么意见 → Agent 如何调整"的全过程。
- **旧 Card 标记为 `superseded`**，但不删除。如果用户发现新 Card 不如旧 Card，可以回到旧 Card 点击"应用"（旧 Card 的"应用"按钮仍可用，直到对应的 `original_content` 被其他操作修改）。
- **追问的上下文注入**通过 SystemMessage 实现，不改变 Agent 的 tool 架构。Agent 只需要理解"用户在讨论一个之前的建议"——这是自然语言理解，不是硬编码逻辑。
- **SuggestionGroup 的追问**：追问针对整个 Group。用户可以在追问中指定"第二个字段的修改太激进了"。Agent 可能只重新 propose 被质疑的字段，其余字段的 Card 保持不变（用户仍可单独接受未改变的部分）。

### 3.9 Card 操作的统一：应用、拒绝、追问

**原始问题**：设计初期存在两种 Card 按钮方案——"应用/拒绝/调整"和"应用/拒绝/讨论"。从第一性原理分析，"调整"和"讨论"本质上是同一个用户意图的不同表述：**"方向大致对，但我想和你再聊聊"**。

**统一为三按钮**：

| 按钮 | 语义 | 触发条件 | 系统行为 |
|------|------|---------|---------|
| ✅ 应用 | "这个改得好，直接用" | 用户对修改完全满意 | Confirm API（accept）→ 应用编辑 → Undo Toast |
| ❌ 拒绝 | "这个方向不对，不要" | 用户不认可修改方向 | Confirm API（reject）→ Card 变灰 → Agent 收到拒绝通知 |
| 💬 追问 | "方向对但需要调整" | 用户想在当前基础上微调 | 输入框预填 → 用户补充意见 → Agent 生成新 Card |

**为什么是"追问"而不是"调整"或"讨论"**：

- "调整"暗示用户要自己编辑 Card 数据——但 Card 的 `edits` 是结构化数据，用户不应直接编辑。
- "讨论"太宽泛——讨论可以是任何话题，不一定指向"修订当前建议"。
- "追问"精确传达了意图：**基于当前建议，提出进一步的要求**。它既涵盖"把文案调温和一点"（调整），也涵盖"你为什么觉得这里需要改？"（讨论），但始终锚定在当前 Card 的上下文中。

**SuggestionGroup 的操作**：

| 操作 | 行为 |
|------|------|
| 全部应用 | 所有勾选的 Card 一起执行 → 多字段同时更新 → 一个 Undo Toast（可一键全部撤回） |
| 全部拒绝 | 整组标记为已拒绝 → Agent 收到通知 |
| 追问 | 进入对话模式，上下文包含整个 Group → Agent 可能局部修订 |
| 部分应用 | 用户取消某些 Card 的勾选 → 仅勾选的 Card 被执行 → 未勾选的保持 pending |

---

## 四、模块关系图

```
┌────────────────────────────────────────────────────────────────┐
│                   System Prompt (XML 结构)                      │
│  (orchestrator.py build_system_prompt)                         │
│  <identity> Mode Prompt + propose_edit 修改规则                 │
│  <action_guide> 用户意图 -> 工具选择决策树                       │
│  <modification_rules> CRITICAL: propose_edit 为默认修改方式     │
│  <disambiguation> 消歧规则（含 propose_edit vs modify_field）   │
│  <project_context> 索引 + 记忆 + 阶段状态                      │
└───────────┬────────────────────────────────────────────────────┘
            │ 注入
            ▼
┌────────────────────────────────────────────────────────────────┐
│                    Agent LLM (via bind_tools)                  │
│  在对话中自主判断 → 调用 propose_edit / modify_field / 文本回复   │
│  多字段时：一次响应中发出多个 propose_edit（同一 group_id）        │
└───┬──────────────────────────┬─────────────────────────────────┘
    │ propose_edit             │ modify_field (保留)
    ▼                          ▼
┌─────────────────────┐  ┌──────────────────────┐
│  propose_edit @tool  │  │  modify_field @tool   │
│  (新增)              │  │  (改造)                │
│                      │  │                       │
│  1. 读取目标内容块    │  │  保留直接执行能力       │
│  2. 调用 edit_engine │  │  (用户确认后由         │
│     .apply_edits()   │  │   confirm API 调用)   │
│  3. 调用 edit_engine │  │                       │
│     .generate_       │  │                       │
│      revision_md()   │  │                       │
│  4. 返回结构化 JSON  │  │                       │
│     (不写 DB)        │  │                       │
└─────────┬───────────┘  └──────────────────────┘
          │ JSON output
          ▼
┌────────────────────────────────────────────────────────────────┐
│                SSE Event Stream (api/agent.py)                  │
│  tool_end 解析 propose_edit 输出 →                              │
│  yield sse_event({"type": "suggestion_card", ...})             │
│  多个同 group_id 的 card → 前端聚合为 SuggestionGroup           │
└───────────┬────────────────────────────────────────────────────┘
            │ SSE
            ▼
┌────────────────────────────────────────────────────────────────┐
│               Frontend: Agent Panel                             │
│  (agent-panel.tsx)                                              │
│                                                                 │
│  收到 suggestion_card 事件 →                                    │
│  if group_id 存在 → 聚合渲染为 SuggestionGroup 组件             │
│  else → 渲染为独立 SuggestionCard 组件                          │
│  ┌─────────────────────────────────────────┐                    │
│  │ 💡 修改建议: 加强开头吸引力               │                    │
│  │ 📝 目标: 场景库                          │                    │
│  │ 原因: 当前开头缺少 hook...               │                    │
│  │                                          │                    │
│  │ - 旧的标题被删除线划掉                    │                    │
│  │ + 新的标题用绿色高亮                      │                    │
│  │                                          │                    │
│  │ [✅ 应用]  [❌ 拒绝]  [💬 追问]           │                    │
│  └─────────────────────────────────────────┘                    │
└───────────┬────────────────────────────────────────────────────┘
            │ 用户操作
            ▼
┌────────────────────────────────────────────────────────────────┐
│               Confirm API (新增)                                │
│  POST /api/agent/confirm-suggestion                            │
│  {suggestion_id, action: "accept"|"reject"|"partial",          │
│   accepted_card_ids: [...]}                                     │
│                                                                 │
│  accept → version_service(old) → edit_engine.apply → 写 DB     │
│        → 返回 {success, version_id, entity_id}                  │
│  reject → 标记 Card 状态 → 注入拒绝消息到对话                    │
│  partial → 仅执行勾选的 Cards → 返回多个 version_id              │
│                                                                 │
│  前端收到 version_id → 显示 Undo Toast (15s)                    │
│  用户点击撤回 → POST /api/versions/{eid}/rollback/{vid}         │
└────────────────────────────────────────────────────────────────┘
```

### 4.1 与现有组件的关系

| 现有组件 | 与 Suggestion Card 的关系 | 改动程度 |
|---------|--------------------------|---------|
| `edit_engine.py` | **复用**。`apply_edits()` 和 `generate_revision_markdown()` 是 `propose_edit` 的核心依赖 | 无改动 |
| `modify_field` tool | **保留但降级**。从"Agent 主动调用的修改工具"变为"确认后的执行工具"或"用户明确要求跳过确认时的快速通道" | 小改 |
| `version_service.py` | **复用 + 微改**。`save_content_version()` 需改为返回 `version_id`（当前返回 None） | 一行改动 |
| `api/versions.py` | **复用**。Undo 直接调用已有的 `rollback_version` 端点 | 无改动 |
| `orchestrator.py` system prompt | **重构**。XML 标签分区 + 优先级标记 + 行动指南 + 修改确认模型 + 反模式库（详见第六章） | 大改 |
| `agent_tools.py` docstrings | **改造**。所有工具统一为标准模板（何时用/何时不用/典型用法），重点改造 modify_field 和新增 propose_edit（详见 6.6 节） | 中改 |
| Mode Prompts (`init_db.py`) | **更新**。5 个预置模式各增加 propose_edit 修改规则和推理策略（详见 6.7 节） | 小改 |
| `agent.py` SSE stream | **扩展**。`on_tool_end` 中增加 `propose_edit` 的特殊处理，发送 `suggestion_card` SSE 事件 | 小改 |
| `agent-panel.tsx` | **扩展**。新增 `SuggestionCard`、`SuggestionGroup` 组件，追问交互，Undo Toast | 中改（新增组件） |
| `AGENT_TOOLS` 列表 | **扩展**。添加 `propose_edit` | 一行 |
| Eval Report | **未来桥接**。在诊断条目中添加"让 Agent 修改"按钮，发送消息到 Agent Panel | 后续迭代 |

### 4.2 与 Tool Call 架构的关系

```
                  现有架构                          Suggestion Card 如何融入
                  ──────                          ─────────────────────

    LLM                                    LLM
     │                                      │
     ├─ 调用 modify_field → 直接执行        ├─ 调用 propose_edit → 生成预览（不执行）
     │                                      │    └─ 多字段: 多次调用同 group_id
     │                                      ├─ 调用 modify_field → 直接执行（保留快速通道）
     ├─ 调用 generate_field_content → 执行  ├─ 调用 generate_field_content → 执行
     ├─ 调用 query_field → 查询             ├─ 调用 query_field → 查询
     └─ ...                                 └─ ...

    关系：propose_edit 是 AGENT_TOOLS 的新成员，和其他 tool 同级。
    它不在 modify_field "之上"或"之下"——它是一个独立的工具。
    LLM 通过 system prompt 中的规则和 docstring 来判断何时调用哪个。
```

**核心架构决策**：`propose_edit` 是一个 **平级的 @tool**，不是 `modify_field` 的包装层。

理由：
1. 保持 Tool Calling 架构的扁平性——LLM 直接看到所有工具，通过 docstring 区分。
2. 不引入层级关系——不需要"先 propose 再 modify"的强制流程，因为有些场景（如用户说"直接改，不用确认"）可以跳过 propose。
3. 让 LLM 的判断成为唯一的路由机制——这与现有架构的"LLM 驱动路由"理念一致。

---

## 五、`modify_field` 的改造

现有的 `modify_field` 不会被移除，但需要调整定位：

### 5.1 当前问题

```python
# 现状：modify_field 直接全文覆写，无确认
_save_version(db, entity.id, current_content, "agent")
entity.content = new_content       # ← 直接写 DB
db.commit()                         # ← 不可逆
return _json_ok(field_name, "applied", f"已修改「{field_name}」")
```

### 5.2 改造后的角色分工

| 场景 | 使用的工具 | 理由 |
|------|-----------|------|
| Agent 自主判断需要修改 | `propose_edit` | 展示意图，等待确认 |
| 用户说"直接帮我改" | `modify_field` | 用户明确授权，跳过确认 |
| 用户确认 Suggestion Card | Confirm API → `edit_engine.apply_edits()` | 按确认的编辑操作执行 |
| 大范围重写（整块内容） | `modify_field` 或 `generate_field_content` | anchor-based edits 不适用于全文重写 |

### 5.3 `modify_field` 的具体改动

1. **System Prompt 更新**：按照第六章 System Prompt 工程方案，使用 XML 标签重构 system prompt，在 `<modification_rules>` 中引导 Agent 优先使用 `propose_edit`，只在用户明确要求"直接改"时使用 `modify_field`。
2. **工具 Docstring 更新**：按照 6.6 节标准模板，增加 CRITICAL 标记和 vs `propose_edit` 消歧（详见 6.6 节 modify_field docstring 草案）。
3. **工具本身不变**：`modify_field` 的实现逻辑保持现状（LLM 生成全文 → 覆写 DB）。它作为"快速通道"保留。
4. **删除 orchestrator.py 中关于 `need_confirm` 的虚假描述**：当前 system prompt 第 249-253 行描述了从未实现的 `need_confirm` 流程，应删除并替换为 `<modification_rules>` 区块。

---

## 六、System Prompt 工程

基于 Cursor 的系统提示词最佳实践分析，结合本项目内容生产的特殊性，设计 System Prompt 和 Tool Docstring 的完整改造方案。

### 6.1 从 Cursor 最佳实践中提炼的设计原则

| 原则 | Cursor 的做法 | 本项目的适配 |
|------|-------------|-------------|
| 结构化分区 | 用 XML 标签分隔不同类型的规则（`<communication>`、`<tool_calling>` 等） | 同样使用 XML 标签，按活动类型分区 |
| 显式优先级 | ALWAYS/NEVER/CRITICAL 标记关键规则 | 同样使用，但针对内容生产的风险模型定制 |
| 工具级决策树 | Tool Docstring 包含"何时用/何时不用/替代工具指引" | 同样结构，但增加 propose_edit 相关的修改操作消歧 |
| 反模式作为一等公民 | 每条规则配备 BAD example 和 reasoning | 同样做法，使用内容生产的典型错误场景 |
| 元认知指导 | 指导 LLM "怎么想"（推理策略），而非只是"做什么" | 增加修改操作的推理策略和风险判断 |
| System Prompt 与 Docstring 职责分离 | System Prompt 定义全局行为框架；Docstring 定义工具级路由 | 同样分离，System Prompt 不重复 Docstring 中的工具用法 |

**核心差异**：Cursor 处理代码——有 git 保护、用户是开发者、变更可一键回退。本项目处理创意内容——版本系统路径较长、用户可能非技术人员、错误修改的恢复成本远高于执行成本。因此本项目的修改操作需要更精确的确认模型。

### 6.2 System Prompt 的 XML 结构

当前 System Prompt 所有段落处于同一 `##` 层级，没有结构化分区。改造后使用 XML 标签按活动类型分区：

```
<identity>
{mode_prompt 或默认身份}
</identity>

<output_rules>
ALWAYS: 输出格式规则
- 用主谓宾结构完整的句子、段落和正常的标点符号进行输出。
- 可以使用 Markdown 格式（标题、列表、加粗等）让内容更清晰。
- 长内容适当分段，保持可读性。
</output_rules>

<action_guide>
用户意图 -> 工具选择的完整决策树
（替代旧的"你的能力"段落，详见 6.4）
</action_guide>

<modification_rules>
CRITICAL: 修改操作的确认模型
（替代旧的"修改确认流程"段落，详见 6.5）
</modification_rules>

<disambiguation>
关键消歧规则
（保留现有的 4 条消歧，增加 propose_edit vs modify_field）
</disambiguation>

<project_context>
当前组、组状态、创作者信息
{field_index}
{memory}
</project_context>

<interaction_rules>
通用交互规则
</interaction_rules>

{intent_guide}  -- 仅 intent 阶段注入
```

**设计原则**：每个 XML 标签内的规则独立完整，LLM 按需关注不同区域。标签名称直接反映其职责，无需额外解释。

### 6.3 优先级标记体系

不使用视觉符号（emoji），仅使用文字标记。针对内容生产系统的风险特征定制四级优先级：

| 标记 | 判断标准 | 违反后果 |
|------|---------|---------|
| CRITICAL | 违反会直接造成用户数据损害或信任破裂 | 内容被错误覆写且用户未知 |
| ALWAYS | 每次都必须遵守的质量底线 | 输出质量下降但不造成数据损害 |
| NEVER | 绝对禁止，任何条件下都不能做 | 造成用户困惑或数据不一致 |
| DEFAULT | 标准行为，可被用户显式指令覆盖 | 不覆盖也正常工作 |

**具体规则分配**：

CRITICAL（3 条，少而精——标记太多会稀释优先级）：
1. 修改内容块时，DEFAULT 使用 propose_edit 展示修改预览。仅当用户明确说"直接改""不用确认"时才使用 modify_field。
2. propose_edit 中的 anchor 必须是原文中精确存在的文本片段。不确定时先用 read_field 查看原文。
3. 不要猜测内容块名称。不确定时查看项目内容块索引。

ALWAYS（4 条）：
1. 修改前使用 read_field 确认当前内容（除非本轮对话中刚读取过）。
2. 多字段关联修改使用相同的 group_id。
3. 用完整的中文句子回复，使用正常标点。可用 Markdown 格式。
4. 工具执行完成后，用简洁的中文告知结果。

NEVER（4 条）：
1. 不要在用户没有要求修改时自主调用 modify_field 或 propose_edit。
2. 不要在只有模糊方向（如"可能需要改进"）时输出 propose_edit——先文本讨论，明确后再 propose。
3. 不要在意图分析流程中把用户对问题的回答当成操作指令。
4. 不要在回复中复述记忆内容。

DEFAULT（2 条）：
1. 修改操作走 propose_edit 确认流程（可被"直接改"覆盖）。
2. 不确定内容块是否为空时，先 read_field 确认。

### 6.4 行动指南（替代"你的能力"）

**现状问题**：当前"你的能力"段落是一个 8 条的能力清单（意图分析、消费者调研、内容规划……），沿用旧架构的表述。LLM 无法据此做路由决策——它需要的不是"我能做什么"，而是"用户想做 X 时我该用哪个工具"。

**改造方案**：以用户意图为入口的行动指南（decision tree）：

```
<action_guide>
## 行动指南

根据用户的意图选择正确的行动。

### 用户想修改内容
CRITICAL: 修改已有内容时，DEFAULT 使用 propose_edit 展示修改预览。
- 用户说"帮我改一下 XX" -> propose_edit（展示修改建议，等用户确认）
- 用户说"直接改""不用确认""直接帮我修改" -> modify_field（跳过确认）
- 内容块为空 -> generate_field_content（不是修改，是首次生成）
- 用户说"重写""从头写" -> generate_field_content 或 modify_field（全文替换）
- 用户提供了完整的替换内容 -> update_field

### 用户想了解内容
- 用户说"看看 XX""读一下 XX" -> read_field
- 用户说"XX 怎么样""分析一下 XX" -> query_field

### 用户想改项目结构
- 用户说"加一个内容块""删掉 XX""新增一个组" -> manage_architecture

### 用户想推进项目
- 用户说"继续""下一步""进入 XX" -> advance_to_phase

### 用户想做调研
- 用户说"做消费者调研" -> run_research(research_type="consumer")
- 用户说"调研一下 XX 市场" -> run_research(research_type="generic")

### 用户想评估内容
- 用户说"评估一下""检查质量" -> run_evaluation

### 不需要调用工具
- 用户打招呼、问你是谁、问通用问题 -> 直接回复
- 用户在意图分析中回答你的提问 -> 不要当成指令
- 用户在讨论方向、还没决定怎么改 -> 文本对话
</action_guide>
```

### 6.5 修改操作的意图确认模型

这是本项目与 Cursor 最大的差异点，也是 Suggestion Card 设计的核心配套。

**为什么不能照搬 Cursor 的自主行动模式**：

| 维度 | Cursor（代码） | 本项目（创意内容） |
|------|--------------|-------------------|
| 版本控制 | git —— 任何变更一键回退 | 版本系统存在但路径较长 |
| 错误感知 | 编译/lint 立即报错 | 创意判断需要人工审阅才能发现 |
| 变更性质 | 通常是确定性的（重命名、修 bug） | 修改背后隐含创作判断（价值选择） |
| 恢复成本 | git checkout = 零成本 | 发现错误 -> 理解原因 -> 回滚 -> 重新描述 |

**基于风险的分层确认模型**：

| 操作类型 | 风险等级 | 默认行为 | 覆盖条件 |
|---------|---------|---------|---------|
| 读取/查询 | 零风险 | 立即执行 | -- |
| 首次生成（空内容块） | 低风险 | 立即执行 | -- |
| 结构变更（增删块/组） | 中风险 | 立即执行（用户已显式请求） | -- |
| 推进阶段 | 低风险 | 立即执行 | -- |
| **修改已有内容** | **高风险** | **propose_edit（展示 diff 预览）** | 用户说"直接改" -> modify_field |
| 覆写已有内容 | 高风险 | propose_edit 或询问 | 用户提供完整文本 -> update_field |

**核心原则**：修改已有内容的决策权属于用户。Agent 的角色是提供高质量的修改建议，不是替用户做决策。

对非修改操作保持高自主性（用户体验流畅）。对修改操作默认走确认流程（保护用户的创作内容）。这解决了"自主行动"与"先确认"之间的矛盾——不是所有操作都需要确认，只有高风险的内容修改需要。

**意图模糊时的分层策略**（替代旧版"不确定用户意图，先确认再操作"）：

```
<interaction_rules>
意图判断策略：
1. 意图清晰 + 非修改操作 -> 立即行动，不做多余确认。
2. 意图清晰 + 修改操作 -> propose_edit 展示方案（这不是"犹豫"，是"展示"）。
3. 意图模糊但可合理推断 -> 给出你的理解并执行，附一句"如果意图不同请告诉我"。
4. 完全无法判断 -> 列出 2-3 种可能的理解，请用户选择。

NEVER 空泛地问"你想做什么？"——至少给出你的判断。
</interaction_rules>
```

### 6.6 Tool Docstring 标准模板与改造方案

**标准模板**：所有工具的 docstring 统一为以下结构：

```python
"""一句话功能描述。

何时使用:
- 场景描述1
- 场景描述2

何时不使用:
- 场景A -> 用 tool_X
- 场景B -> 用 tool_Y

典型用法:
- "用户说法1" -> tool_name("参数1", "参数2")
- "用户说法2" -> tool_name("参数1")

Args:
    param1: 参数描述
    param2: 参数描述
"""
```

**各工具改造要点**：

| 工具 | 现状评级 | 改造要点 |
|------|---------|---------|
| `propose_edit` | 新增 | 完整模板，含 edits 格式示例、anchor 精确性要求、错误用法 |
| `modify_field` | 中等 | 增加 CRITICAL 标记和 vs propose_edit 消歧 |
| `generate_field_content` | 中等 | 增加"何时不使用"（已有内容时不用） |
| `update_field` | 中等 | 增加典型用法示例 |
| `query_field` | 中等 | 已有消歧，补充"何时不使用" |
| `read_field` | 弱 | 补充完整模板 |
| `manage_architecture` | 好 | 保持，微调格式统一 |
| `advance_to_phase` | 弱 | 补充"何时不使用" |
| `run_research` | 中等 | 补充"何时不使用" |
| `manage_persona` | 极弱 | 完全重写，补充各 operation 的使用场景 |
| `run_evaluation` | 中等 | 补充"何时不使用"（无内容时不评估） |
| `manage_skill` | 弱 | 补充完整模板 |
| `read_mode_history` | 弱 | 补充完整模板 |

**重点改造 1：`propose_edit` docstring 草案**：

```python
"""向用户提出内容修改建议，展示修改预览供用户确认。不会直接执行修改。

何时使用:
- 你分析后认为某个内容块需要修改，且有具体的修改方案
- 用户说"帮我改一下 XX"（默认走确认流程）
- 评估/批评后有具体的可操作改进点
- 一句话能说清楚"改什么"和"为什么改"

何时不使用:
- 还在讨论方向，不确定该怎么改 -> 文本对话
- 有多种修改方向需要用户选择 -> 文本对话，列出选项
- 修改范围太大（整篇重写） -> generate_field_content
- 用户说"直接改，不用确认" -> modify_field

错误用法:
- 用户说"你觉得场景库怎么样？" -> 不要 propose_edit，这是讨论不是修改请求
- 你只有模糊方向如"可能需要改进" -> 不要 propose_edit，先明确具体改什么
- anchor 写成"大概是第三段" -> anchor 必须是原文中精确存在的文本

多字段修改:
- 当多个字段的修改有共同原因时，使用相同的 group_id
- 首次调用提供 group_summary
- 彼此独立的修改不用 group_id

edits 格式:
  [{"type": "replace", "anchor": "原文中精确存在的文本", "new_text": "替换后的文本"}]
  [{"type": "insert_after", "anchor": "定位锚点", "new_text": "插入的内容"}]
  [{"type": "delete", "anchor": "要删除的文本", "new_text": ""}]

CRITICAL: anchor 必须是目标内容块中精确存在的文本片段。不确定时先用 read_field 查看原文。

Args:
    target_field: 目标内容块名称
    summary: 一句话描述修改内容（如"加强开头的吸引力"）
    reason: 修改原因（如"当前开头过于平淡，缺少 hook"）
    edits: 编辑操作列表，格式见上
    group_id: 多字段修改的组 ID（可选）
    group_summary: 整组修改的总体说明（仅首次调用时提供）
"""
```

**重点改造 2：`modify_field` docstring 草案**：

```python
"""修改指定内容块的已有内容。直接执行修改，不走确认流程。

CRITICAL: 大多数修改场景应优先使用 propose_edit（展示修改预览供用户确认）。
仅在以下情况使用 modify_field:
- 用户明确说"直接改""不用确认""帮我直接修改"
- 大范围重写（anchor-based edits 不适用）

何时使用:
- 用户说"直接帮我改 XX，不用确认"
- 用户要求大范围重写某个内容块

何时不使用:
- Agent 自主判断需要修改 -> propose_edit
- 用户只说"帮我改一下" -> propose_edit（默认走确认）
- 创建新内容块 -> manage_architecture
- 内容块为空需首次生成 -> generate_field_content

典型用法:
- "@场景库 直接帮我把5个改成7个" -> modify_field("场景库", "把5个模块改成7个")
- "参考 @用户画像 直接修改 @场景库" -> modify_field("场景库", "修改", ["用户画像"])

Args:
    field_name: 要修改的目标内容块名称
    instruction: 用户的具体修改指令
    reference_fields: 需要参考的其他内容块名称列表
"""
```

### 6.7 Mode Prompt 更新方案

每个预置模式需要增加 propose_edit 的使用引导。原则：不改变模式的核心身份和行为原则，只补充修改工具的选择规则。

#### assistant（助手）

在行为原则末尾增加：
```
修改规则：
- 用户要求修改内容时，DEFAULT 使用 propose_edit 展示修改方案。
- 用户说"直接改"时才用 modify_field。
- 完成修改提案后，简要告知用户可以确认、拒绝或追问。
```

#### strategist（策略顾问）

在行为原则末尾增加：
```
修改规则：
- 当策略讨论收敛为具体内容修改时，使用 propose_edit 将建议具体化为可执行的修改方案。
- 你的价值在于让选择清晰，不在于替人做修改。通常先用文本讨论，达成共识后再 propose_edit。
```

#### critic（审稿人）

将原有"创作者要求修改时，执行修改并说明改了什么、为什么这样改更好"替换为：
```
修改规则：
- 发现可改进的内容时，使用 propose_edit 展示具体的修改建议和原因。
- 多个内容块有关联问题时，用 group_id 将它们组织为一组建议。
- 按严重程度排序：结构性缺陷 > 逻辑问题 > 表达质量 > 细节打磨。先 propose 最严重的问题。

推理策略：
1. 收到审阅请求时，先 read_field 读取完整内容。
2. 识别问题并按严重程度排序。
3. 对可具体修改的问题，用 propose_edit 输出修改建议。
4. 对方向性问题（如"定位有偏差"），先文本讨论，收敛后再 propose_edit。
```

#### reader（目标读者）

在行为原则末尾增加：
```
修改规则：
- 如果你发现内容有明显的读者体验问题（如"我在这里完全看不懂"），可以用 propose_edit 建议具体的文案调整。
- 要从读者视角解释为什么这样改——"改成这样我就能看懂了"而不是"从内容策略角度建议优化"。
```

#### creative（创意伙伴）

在行为原则末尾增加：
```
修改规则：
- 产出创意方案时，可用 propose_edit 展示不同风格的改写方案，让创作者比较选择。
- 也可以用 generate_field_content 尝试全新的创作方向。
- 先发散（文本讨论多个方向），再收敛（用 propose_edit 具体化最佳方案）。
```

### 6.8 动态段落优化

#### 项目内容块索引（简化）

旧版（4 行前缀 + 数据）：
```
## 项目内容块索引
以下是本项目所有内容块及其摘要，按组归类。
用途：帮你定位与用户指令相关的内容块，选择正确的工具参数（field_name）。
**注意**：摘要只是索引，不代表完整内容。需要完整内容时请使用 read_field 工具。
```

新版（1 行前缀 + 数据）：
```
<field_index>
ALWAYS: 以下为摘要索引。需要完整内容时用 read_field 读取。
{fi}
</field_index>
```

#### 项目记忆（增加使用规则）

旧版：
```
## 项目记忆
以下是跨模式、跨阶段积累的关键信息。做任何操作时请参考这些约束和偏好，无需复述。
```

新版：
```
<memory>
## 项目记忆
以下是跨模式、跨阶段积累的关键信息。

使用规则:
- 做内容修改时，检查是否与记忆中的偏好或约束冲突。
- NEVER 在回复中复述记忆内容。
- 记忆可能过时。如果用户当前指令与记忆矛盾，以当前指令为准。
{memory_context}
</memory>
```

### 6.9 反模式库（Bad Examples）

以下反模式需嵌入 system prompt 的 `<action_guide>` 中，形成正面规则与反面示例的双重防护：

```
错误用法示例（NEVER 这样做）:

1. 把讨论当成修改请求:
   用户: "我觉得开头有点弱"
   错误: 立即调用 propose_edit
   正确: 回复"你希望往哪个方向加强？比如增加数据支撑、讲一个故事、还是提出一个引发好奇的问题？"
   原因: "有点弱"是评价，不是修改指令。用户还没决定"往哪个方向改"。

2. 跳过确认直接修改:
   用户: "帮我改一下场景库"
   错误: 调用 modify_field 直接生成新内容覆写
   正确: 调用 propose_edit 展示具体的修改建议和 diff 预览
   原因: "帮我改一下"没有说"直接改不用确认"。DEFAULT 走 propose_edit。

3. 猜测内容块名称:
   用户: "修改那个关于场景的内容"
   错误: modify_field("场景分析", ...)（猜测了名称，实际可能叫"场景库"）
   正确: 查看索引确认，或回复"你指的是'场景库'还是'场景分析'？"
   原因: 用错名称会导致找不到内容块。

4. anchor 不精确:
   错误: propose_edit(edits=[{"anchor": "第三段讲了一些关于用户的内容", ...}])
   正确: propose_edit(edits=[{"anchor": "本场景库包含5个核心场景", ...}])
   原因: anchor 必须是原文中精确存在的文本片段，否则 edit_engine 无法定位。

5. 用 propose_edit 做全文重写:
   用户: "帮我把场景库整个重写"
   错误: propose_edit 但 edits 覆盖了整篇内容
   正确: generate_field_content("场景库", "重写")
   原因: 全文重写不适合 anchor-based edits，应该用从零生成。
```

---

## 七、前端 Suggestion Card 组件设计

### 7.1 单字段 SuggestionCard 展示

Suggestion Card 出现在 Agent 的对话消息流中，作为一种特殊的消息类型（类似 tool_start/tool_end 的可视化，但更具交互性）：

```
┌── Agent Panel ─────────────────────────┐
│                                         │
│  [用户] 帮我改一下场景库的开头           │
│                                         │
│  [Agent] 我看了场景库的内容，开头确实    │
│          可以更有吸引力。这是我的建议：   │
│                                         │
│  ┌─── Suggestion Card ──────────────┐  │
│  │ ✏️ 加强开头的吸引力                │  │
│  │ 📍 目标: 场景库                   │  │
│  │                                   │  │
│  │ 原文: "本场景库包含5个核心场景"     │  │
│  │ ──────────────────────────        │  │
│  │ - 本场景库包含5个核心场景           │  │
│  │ + 你是否想过，一个产品的成败往往     │  │
│  │ + 取决于5个关键场景？               │  │
│  │                                   │  │
│  │ 修改原因: 当前开头过于平铺直叙，    │  │
│  │ 缺少吸引读者继续阅读的 hook。       │  │
│  │                                   │  │
│  │ [✅ 应用] [❌ 拒绝] [💬 追问]      │  │
│  └───────────────────────────────────┘  │
│                                         │
└─────────────────────────────────────────┘
```

### 7.2 SuggestionGroup 展示

当多张 Card 共享同一个 `group_id` 时，前端将它们聚合为一个 SuggestionGroup：

```
┌── Agent Panel ─────────────────────────────────┐
│                                                 │
│  [Agent] 根据评估报告，我发现受众画像的定义      │
│         过于宽泛，连带影响了场景库和传播策略。     │
│         以下是我的调整建议：                      │
│                                                 │
│  ┌─── SuggestionGroup ──────────────────────┐  │
│  │ 📋 根据评估结果，调整 3 个关联字段          │  │
│  │ 原因：受众定义过于宽泛，导致下游内容        │  │
│  │ 缺乏针对性                                │  │
│  │                                           │  │
│  │  ┌ Card 1: 受众画像 ────────────────┐    │  │
│  │  │ ✏️ 缩小目标受众                    │    │  │
│  │  │ - 18-45岁互联网用户               │    │  │
│  │  │ + 25-35岁一线城市产品经理          │    │  │
│  │  │ [☑ 接受此项]                      │    │  │
│  │  └────────────────────────────────────┘    │  │
│  │                                           │  │
│  │  ┌ Card 2: 场景库 ──────────────────┐    │  │
│  │  │ ✏️ 场景与受众对齐                  │    │  │
│  │  │ - 用户在日常生活中...              │    │  │
│  │  │ + 产品经理在做竞品分析时...         │    │  │
│  │  │ [☑ 接受此项]                      │    │  │
│  │  └────────────────────────────────────┘    │  │
│  │                                           │  │
│  │  ┌ Card 3: 传播策略 ────────────────┐    │  │
│  │  │ ✏️ 渠道从大众转向垂直社区          │    │  │
│  │  │ - 微博、抖音、小红书              │    │  │
│  │  │ + 即刻、ProductHunt、少数派        │    │  │
│  │  │ [☑ 接受此项]                      │    │  │
│  │  └────────────────────────────────────┘    │  │
│  │                                           │  │
│  │ [✅ 全部应用] [❌ 全部拒绝] [💬 追问]      │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 7.3 交互逻辑

#### 单字段 Card

| 用户操作 | 系统行为 |
|---------|---------|
| 点击"✅ 应用" | Confirm API（accept）→ 应用编辑 → 刷新左侧内容面板 → Card 变为"已应用"状态（绿色边框 ✓）→ 显示 Undo Toast（15s） |
| 点击"❌ 拒绝" | Confirm API（reject）→ 不修改 → Card 变为"已拒绝"状态（灰色 + 删除线）→ Agent 收到拒绝消息，可在后续回复中询问原因 |
| 点击"💬 追问" | Card 进入"追问中"状态（虚线边框 + 黄色标记）→ 输入框预填"关于 [{target_field}] 的修改建议，" → 用户补充意见 → Agent 生成新 Card → 旧 Card 标记为 `superseded` |

#### SuggestionGroup

| 用户操作 | 系统行为 |
|---------|---------|
| 点击"✅ 全部应用" | 所有勾选的 Card → Confirm API（accept，携带所有勾选的 card_ids）→ 多字段同时更新 → 一个 Undo Toast（"已应用 3 项修改 [↩ 全部撤回]"） |
| 取消部分勾选 → "✅ 全部应用" | 仅勾选的 Card 被执行（Confirm API partial）→ 未勾选的保持 pending |
| 点击"❌ 全部拒绝" | 整组标记为已拒绝 → Agent 收到通知 |
| 点击"💬 追问" | 进入对话模式，上下文包含整个 Group → 用户可指定"第 N 个字段的修改需要调整" → Agent 局部或全部重新 propose |

#### Undo Toast

```
┌──────────────────────────────────────┐
│  ✅ 修改已应用   [↩ 撤回]   ━━━━━━  │
│                            (15s 倒计时)│
└──────────────────────────────────────┘
```

- Toast 出现在 Agent Panel 底部，不遮挡 Card 内容。
- 15 秒倒计时后自动消失。消失后撤回仍可通过版本历史面板操作。
- SuggestionGroup 的 Toast 显示"已应用 N 项修改 [↩ 全部撤回]"。

### 7.4 Diff 渲染

使用 `edit_engine.generate_revision_markdown()` 生成的 `<del>/<ins>` HTML。前端用 CSS 样式渲染：

```css
del { background: rgba(239, 68, 68, 0.15); color: #fca5a5; text-decoration: line-through; }
ins { background: rgba(34, 197, 94, 0.15); color: #86efac; text-decoration: none; }
```

这复用了 `implementation_plan_v3.md` 中已经设计好的 diff 渲染方案，以及 `agent-panel.tsx` 中已有的 `rehype-raw` 插件（支持 HTML 标签渲染）。

### 7.5 Card 状态的视觉表达

| 状态 | 视觉样式 | 按钮状态 |
|------|---------|---------|
| `pending` | 蓝色左边框，正常背景 | 三个按钮均可用 |
| `accepted` | 绿色左边框，✓ 标记 | 按钮隐藏 |
| `rejected` | 灰色左边框，内容半透明 | 按钮隐藏 |
| `superseded` | 灰色左边框，"↪ 已被新建议替代" | "应用"仍可用（作为回退选项），其他隐藏 |
| `undone` | 灰色虚线边框，"↩ 已撤回" | 按钮隐藏 |

---

## 八、Confirm API 设计

```python
# 新增 API: POST /api/agent/confirm-suggestion
class ConfirmRequest(BaseModel):
    project_id: str
    suggestion_id: str              # 单 Card 时为 card_id，Group 时为 group_id
    action: str                     # "accept" | "reject" | "partial"
    accepted_card_ids: list[str] = []  # partial 时指定接受哪些 Card

class ConfirmResponse(BaseModel):
    success: bool
    applied_cards: list[dict]       # [{"card_id": "...", "entity_id": "...", "version_id": "..."}]
    message: str

# 处理逻辑:
# 1. 从缓存中取出 SuggestionCard（含 edits 和 original_content）
# 2. if accept:
#      对每个目标 Card:
#        - ver_id = version_service.save_content_version(old_content) → 返回 version_id
#        - edit_engine.apply_edits(original, edits) → modified
#        - 写入 DB: block.content = modified
#      返回所有 applied_cards（含 version_id，供前端 Undo 使用）
# 3. if partial:
#      仅对 accepted_card_ids 中的 Card 执行上述流程
#      未选中的 Card 保持 pending
# 4. if reject:
#      不操作 DB
#      在 Agent 对话中注入 SystemMessage: "用户拒绝了修改建议: {summary}"
#      返回确认
```

### 8.1 Suggestion 缓存策略

`propose_edit` tool 在返回 JSON 时，需要把完整的 SuggestionCard（含 original_content 快照）缓存起来，供后续 Confirm API 使用。

方案：**写入 DB 的 `pending_suggestions` 表**（新表），或简单起见先用 **Redis / 内存字典 + TTL**。

建议 M1 先用内存字典（`Dict[str, SuggestionCard]`，单进程下足够），M2 迁移到 DB 表。

### 8.2 Undo 路径

Undo 不需要额外的 API——直接复用已有的版本回滚端点：

```
POST /api/versions/{entity_id}/rollback/{version_id}
```

前端在 Confirm API 返回后，从 `applied_cards` 中提取 `entity_id` 和 `version_id`，缓存在 Toast 组件的 state 中。用户点击"撤回"时直接调用回滚 API。

SuggestionGroup 的 Undo：对所有 `applied_cards` 逐一调用回滚 API（可并行请求）。

### 8.3 追问的后端处理

追问**不经过 Confirm API**——它是正常的 Agent 对话流。前端做的事情：
1. 将旧 Card 的 `{card_id, target_field, summary}` 编码为一条 SystemMessage 前缀
2. 将用户的追问文本作为 HumanMessage
3. 发送到正常的 `/api/agent/stream` 端点

Agent 自然地响应：可能输出文本 + 新的 `propose_edit` 调用。新 Card 会携带一个 `supersedes` 字段（指向旧 Card 的 id），前端据此将旧 Card 标记为 `superseded`。

---

## 九、Milestone 与优先级

### 修改原则

1. **增量式改造**：每个 Milestone 都是独立可用的，不需要后续 Milestone 才能工作。
2. **不破坏现有功能**：`modify_field` 保留，新增 `propose_edit`，两者共存。
3. **从后端到前端**：先确保数据正确流通，再打磨 UI。
4. **用户感知优先**：先做用户能直接感受到的改进（Suggestion Card UI），再做系统优化。

---

### M1: Suggestion Card 核心通路 + Undo（优先级 P0）

**目标**：Agent 能输出单字段 Suggestion Card，用户能在 Agent Panel 看到 diff 预览并确认/拒绝/追问，确认后支持 Undo。

**范围**：
- 后端：`propose_edit` tool + SSE 事件 + Confirm API（含 version_id 返回）
- 前端：SuggestionCard 组件 + 交互逻辑（应用 / 拒绝 / 追问）+ Undo Toast
- Prompt 工程（第六章全部内容）：system prompt XML 重构 + 优先级标记 + 行动指南 + 修改确认模型 + 反模式库 + 工具 docstring 标准化 + mode prompt 更新
- 微改：`version_service.save_content_version()` 返回 `version_id`

**预期交互**：
```
用户: "帮我改一下场景库的开头"
Agent: [文字] "好的，我看了场景库的内容，建议如下修改："
       [Suggestion Card] 显示 diff 预览
用户: 点击 ✅ 应用
系统: 应用修改 → 刷新内容面板 → 显示 Undo Toast
用户: (可选) 点击 ↩ 撤回
系统: 回滚到修改前版本
```

**验收标准**：
1. Agent 在至少 3 种场景下能正确输出 Suggestion Card
2. Suggestion Card 显示正确的 diff 预览
3. "应用"、"拒绝"、"追问"三个按钮功能正常
4. 修改后旧版本正确保存，Undo Toast 可正常撤回
5. 追问后 Agent 能生成新 Card，旧 Card 标记为 `superseded`

---

### M2: SuggestionGroup + 部分接受（优先级 P1）

**目标**：支持多字段联动修改，Agent 通过 `group_id` 将多个修改关联为一组，用户可逐字段勾选后部分应用。

**范围**：
- 后端：`propose_edit` 的 `group_id` / `group_summary` 参数处理 + 缓存中的 Group 聚合
- 前端：SuggestionGroup 组件 + 逐 Card 勾选 + 全部应用/部分应用交互
- Confirm API：支持 `partial` action + `accepted_card_ids`
- Undo：SuggestionGroup 的 Toast 支持"全部撤回"

**验收标准**：
1. Agent 能输出包含 2-3 个字段的 SuggestionGroup
2. SuggestionGroup 显示整体原因 + 逐字段 diff
3. 用户可逐字段勾选/取消，部分应用后只有勾选的字段被修改
4. "全部撤回"功能正常

---

### M3: Eval Report 桥接（优先级 P1）

**目标**：Eval Report 的诊断结果可以一键发送到 Agent 对话，触发 Suggestion Card 或 SuggestionGroup。

**范围**：
- 前端：`EvalReportPanel` 的综合诊断区域添加"让 Agent 修改"按钮
- 后端：无需改动（按钮只是往 Agent 对话发一条消息）
- Prompt：可选——在消息中附带评估上下文

**验收标准**：
1. Eval Report 的诊断区域有"让 Agent 修改"按钮
2. 点击后 Agent Panel 自动接收消息并生成 Suggestion Card / Group

---

### M4: Inline AI 操作（优先级 P2）

**目标**：用户在中栏内容编辑器中选中文本，通过 floating toolbar 触发 AI 修改，结果以 inline diff 展示。

**范围**：
- 前端：ContentBlockEditor 中的 floating toolbar（AI 改写/扩展/精简）
- 后端：新增轻量级 API 或复用 `propose_edit`（通过非 Agent 通道调用 edit_engine）
- 前端：inline diff 渲染（`<del>/<ins>` 样式）

**验收标准**：
1. 选中文本后出现 AI 操作按钮
2. 点击后在编辑器内显示 diff 预览
3. 用户可接受或拒绝

---

### M5: Suggestion 持久化 + 历史（优先级 P3）

**目标**：Suggestion Card 的历史可追溯，支持"查看之前的修改建议"。

**范围**：
- 后端：`pending_suggestions` 从内存字典迁移到 DB 表
- 前端：可选的 Suggestion 历史面板
- 数据：关联 ChatMessage，作为消息的附属数据

---

## 十、实施 Todo List

### M1: Suggestion Card 核心通路 + Undo

#### 后端

- [x] **T1.1** `version_service.py`：`save_content_version()` 改为返回 `version_id`（当前返回 None）
  - `db.flush()` 后返回 `ver.id`

- [x] **T1.2** 在 `agent_tools.py` 中新增 `propose_edit` @tool
  - 读取目标内容块当前内容
  - 调用 `edit_engine.apply_edits()` 生成 modified_content 和 changes
  - 调用 `edit_engine.generate_revision_markdown()` 生成 diff_preview
  - 缓存 SuggestionCard 到内存字典（`PENDING_SUGGESTIONS: Dict[str, dict]`）
  - 返回结构化 JSON：`{status: "suggestion", id, target_field, entity_id, summary, reason, diff_preview, edits_count}`

- [x] **T1.3** 在 `agent_tools.py` 的 `AGENT_TOOLS` 列表中注册 `propose_edit`

- [x] **T1.4** 在 `api/agent.py` 的 SSE stream 的 `on_tool_end` 处理中，增加 `propose_edit` 的特殊分支
  - 解析 tool output JSON
  - 如果 `status == "suggestion"`，yield `sse_event({"type": "suggestion_card", ...})`
  - 附带完整的 diff_preview、summary、reason、suggestion_id、entity_id

- [x] **T1.5** 新增 Confirm API：`POST /api/agent/confirm-suggestion`
  - 请求体：`{project_id, suggestion_id, action: "accept"|"reject"}`
  - accept：从缓存取 SuggestionCard → `version_service.save_content_version()` 返回 version_id → `edit_engine.apply_edits()` → 写 DB
  - reject：从缓存删除 → 注入拒绝消息到对话 → 返回确认
  - 返回体：`{success, applied_cards: [{card_id, entity_id, version_id}], message}`

- [x] **T1.6** 重构 `orchestrator.py` 的 `build_system_prompt()`（参照第六章完整方案）
  - 使用 XML 标签重新组织 system prompt 结构（`<identity>`、`<output_rules>`、`<action_guide>`、`<modification_rules>`、`<disambiguation>`、`<project_context>`、`<interaction_rules>`）
  - 删除旧的"修改确认流程"段（第 249-253 行）
  - 删除旧的"你的能力"段，替换为 `<action_guide>` 行动指南（6.4 节）
  - 新增 `<modification_rules>`，含 CRITICAL/ALWAYS/NEVER/DEFAULT 优先级标记（6.3 节）
  - 新增意图确认模型的分层策略（6.5 节）
  - 新增反模式库（6.9 节）
  - 简化项目内容块索引前缀（6.8 节）
  - 增加项目记忆使用规则（6.8 节）

#### 前端

- [x] **T1.7** 在 `frontend/components/suggestion-card.tsx` 中新增独立 `SuggestionCard` 子组件
  - 渲染 summary、target_field、reason
  - 使用 `<del>/<ins>` HTML 渲染 diff_preview（通过已有的 `rehype-raw` 插件）
  - 三个按钮：应用 / 拒绝 / 追问
  - 五种状态的视觉样式（参照 7.5 节）
  - 样式：卡片式（border + 背景色），与普通消息气泡视觉区分

- [x] **T1.8** 在 `agent-panel.tsx` 的 SSE 事件处理中，增加 `suggestion_card` 事件分支
  - 将 suggestion 数据存入 state（`suggestions` Map）
  - 在消息流中渲染 SuggestionCard 组件（通过 `[SuggestionCardPlaceholder-{id}]` 占位符）

- [x] **T1.9** 实现 SuggestionCard 的三个按钮交互
  - 应用：调用 Confirm API → 成功后更新 Card 状态为 `accepted` + 触发 `onContentUpdate()` + 显示 Undo Toast
  - 拒绝：调用 Confirm API → 更新 Card 状态为 `rejected`
  - 追问：Card 进入追问状态 → 输入框预填上下文 → 发送后走正常 Agent 对话流

- [x] **T1.10** 实现 UndoToast 组件（`frontend/components/undo-toast.tsx`）
  - 收到 Confirm API 返回的 `version_id` 和 `entity_id` 后显示
  - 15 秒倒计时，带进度条
  - 点击"撤回"→ 调用 `POST /api/versions/{entity_id}/rollback/{version_id}` → Card 状态变为 `undone` → 刷新内容面板
  - 倒计时结束后自动消失

- [x] **T1.11** 实现追问上下文注入
  - 点击追问后，记录当前 Card 的 `{card_id, target_field, summary}` 到 `followUpContextRef`
  - 发送消息时，在请求体中附带 `followup_context` 字段
  - 后端在 HumanMessage 前注入 SystemMessage：`"[用户正在对 Suggestion #{card_id} 进行追问...]"`

- [x] **T1.12** 在 `TOOL_NAMES` 和 `TOOL_DESCS` 中添加 `propose_edit` 的显示名称

- [x] **T1.13** 添加 diff 样式（`<del>/<ins>` 的 CSS）
  - 在 `globals.css` 中定义全局样式
  - del: 红色背景 + 删除线
  - ins: 绿色背景

#### Prompt 工程（参照第六章完整方案）

- [x] **T1.14** 编写 `propose_edit` 的完整 docstring（参照 6.6 节草案）
  - 何时使用 / 何时不使用 / 错误用法
  - edits 格式示例和 anchor 精确性要求
  - 多字段修改的 group_id 用法

- [x] **T1.15** 改造 `modify_field` 的 docstring（参照 6.6 节草案）
  - 增加 CRITICAL 标记：大多数场景应优先使用 propose_edit
  - 增加"何时不使用"段和 vs propose_edit 消歧

- [x] **T1.16** 统一其他工具的 docstring 为标准模板（参照 6.6 节）
  - 优先改造弱项：manage_persona、read_field、advance_to_phase、manage_skill
  - 为所有工具补充"何时不使用"段

- [x] **T1.17** 更新 5 个预置 Mode Prompt（参照 6.7 节）
  - assistant: 增加 propose_edit 修改规则
  - critic: 替换"执行修改"为 propose_edit + 推理策略
  - strategist: 增加"讨论收敛后 propose_edit"规则
  - reader: 增加读者视角的 propose_edit 使用引导
  - creative: 增加发散-收敛的 propose_edit 使用模式

- [ ] **T1.18** 测试 Agent 在不同场景下的行为
  - "帮我改一下场景库" → 应 propose_edit
  - "你觉得场景库怎么样？" → 应文本回复
  - "直接改，不用确认" → 应 modify_field
  - "我觉得开头有点弱" → 应文本讨论（不是立即 propose_edit）
  - Critic 模式下的评价 → 有具体改进建议时应 propose_edit
  - 追问后 → 应生成新的 propose_edit 替代旧 Card

### M2: SuggestionGroup + 部分接受

- [ ] **T2.1** 后端 `propose_edit` 支持 `group_id` 和 `group_summary` 参数
  - group_id 非空时，将 Card 缓存在 Group 结构中
  - 返回 JSON 中包含 group_id 信息

- [ ] **T2.2** 前端新增 SuggestionGroup 组件
  - 检测多个 suggestion_card 事件是否共享 group_id
  - 共享时聚合为 SuggestionGroup 渲染
  - 显示 group_summary + 逐 Card diff + 逐 Card 勾选

- [ ] **T2.3** Confirm API 支持 `partial` action + `accepted_card_ids`
  - 返回 `applied_cards` 列表（仅已应用的）

- [ ] **T2.4** SuggestionGroup 的 Undo Toast
  - "已应用 N 项修改 [↩ 全部撤回]"
  - 全部撤回时并行调用回滚 API

- [ ] **T2.5** system prompt 更新：引导 Agent 在多字段修改时使用 group_id
  - 在 propose_edit 使用规则中补充"多字段修改"段落

- [ ] **T2.6** SuggestionGroup 的追问
  - 追问上下文包含整个 Group 的 cards 信息
  - Agent 可局部重新 propose（仅替代被质疑的字段）

### M3: Eval Report 桥接

- [ ] **T3.1** 在 `EvalReportPanel` 的综合诊断区域添加"让 Agent 修改"按钮
- [ ] **T3.2** 点击按钮后，构造消息文本（包含诊断内容）发送到 Agent Panel
- [ ] **T3.3** Agent Panel 接收消息后正常走 Agent 对话流（自然触发 propose_edit / propose_edit_group）

### M4: Inline AI 操作

- [ ] **T4.1** ContentBlockEditor 中添加 floating toolbar（选中文本时出现）
- [ ] **T4.2** toolbar 按钮：AI 改写 / AI 扩展 / AI 精简
- [ ] **T4.3** 点击后调用轻量级 API → 返回 diff 预览 → 编辑器内 inline 展示
- [ ] **T4.4** 接受/拒绝交互

---

## 十一、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 输出的 anchor 定位不准 | edit 失败（anchor_not_found） | `propose_edit` 返回失败时，fallback 为全文 diff（`generate_revision_markdown` 只需 old/new） |
| Agent 过度使用 propose_edit（每句话都出 Card） | 用户体验差 | `<action_guide>` 反模式 #1（把讨论当修改请求）+ NEVER 规则 + 测试 |
| Agent 从不使用 propose_edit（总是 modify_field） | Suggestion Card 形同虚设 | `<modification_rules>` CRITICAL 规则 + modify_field docstring 中的 CRITICAL 警告 + mode prompt 引导 |
| Agent 把讨论当成修改请求 | 用户觉得 Agent 过于激进 | `<action_guide>` 反模式库 #1 + propose_edit docstring "错误用法"段 |
| 内存缓存丢失（服务重启） | 未确认的 Suggestion 消失 | M1 可接受（丢失后用户重新触发）；M5 迁移到 DB |
| Diff 渲染在长文本下性能差 | 前端卡顿 | 限制 diff_preview 长度，超长时只展示摘要 + "查看完整对比" |
| SuggestionGroup 中部分 Card 执行成功、部分失败 | 数据不一致 | Confirm API 使用数据库事务，全部成功或全部回滚；返回 partial result 让用户知晓 |
| 追问循环过多（用户反复追问不满意） | Agent 消耗大量 token | 追问深度超过 3 轮时，Agent 建议用户"直接编辑内容块"或"重新描述需求" |
| Undo Toast 过期后用户才想撤回 | 用户找不到撤回入口 | Toast 中提示"也可通过版本历史面板撤回"；Card 的"已应用"状态旁显示"在版本历史中查看"链接 |

---

## 十二、与第一性原理文档的衔接

本文档解决的是 `first_principles.md` 中识别的三个核心缺陷中的两个：

| first_principles.md 识别的缺陷 | 本文档的解决方案 |
|-------------------------------|----------------|
| **缺陷 A: Agent 不会主动守护品质** | `propose_edit` 让 Agent 在任何模式下主动输出修改建议 |
| **缺陷 B: 评估→迭代没有闭环** | M3 (Eval Report 桥接) 让评估结果直接触发 Agent 的 propose_edit |
| 缺陷 C: 内容块间缺少一致性守护 | SuggestionGroup 让 Agent 表达"多字段联动修改"的意图；追问机制让用户和 Agent 就一致性问题展开对话 |

Suggestion Card 不仅仅是一个 UI 组件——它是整个系统从"被动执行工具"向"主动品质守护伙伴"转变的关键机制。四条设计原则（Diff-first、原生输出、统一交互、Undo-safe）确保了这个转变既安全（用户始终掌控决策权），又高效（一键确认 + 一键撤回 + 追问微调）。

第六章 System Prompt 工程是这个转变的"软件"层面——通过 XML 结构化、优先级标记、行动指南、修改确认模型、工具 docstring 标准化和 mode prompt 更新，确保 Agent 能在正确的时机、以正确的方式输出 Suggestion Card，而不是在不该修改时修改、在该确认时跳过确认。

---

> 下一步：在此文档评审通过后，按 M1 的 Todo List 开始实施。
