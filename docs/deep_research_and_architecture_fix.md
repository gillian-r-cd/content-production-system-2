# DeepResearch 可靠性修复 & manage_architecture 组名解析修复

> 创建时间：2026-02-16
> 前置文档：`first_principles.md`、`suggestion_card_design.md`、`deep_research.md`（已过时，待清理）
> 性质：根因分析、修复方案、里程碑与 Todo

---

## 一、问题的本质

### 1.1 DeepResearch 的根本目的

`first_principles.md` 定义了系统的核心假设之一：

> **以终为始**（Backward Design）：先明确目标受众会做什么（期望行动），再倒推内容该怎么写。

DeepResearch 是"以终为始"的第一个数据输入——它把项目意图转化为**真实的消费者洞察**，后续所有内容（内涵设计、场景库、传播策略）都依赖这份调研的质量。

如果 DeepResearch 返回的是 LLM 臆造的内容，整个"以终为始"的链条从第一步就断了。用户看到的不是"基于真实调研的内容方向"，而是"AI 自说自话的猜测"——而且系统没有任何提示告诉用户这份报告是编造的。

### 1.2 manage_architecture 的根本目的

`manage_architecture` 是用户调整项目结构的唯一工具接口。它体现的是 `cursorrule.md` 中的核心设计理念：

> **ContentBlock 统一树**: 所有内容都是树形内容块，phase/field/section 只是 block_type

用户说"在消费者调研里加一个内容块"，本质上是要在 ContentBlock 树的某个 phase 节点下添加一个 field 子节点。如果系统无法正确理解"消费者调研"指的是哪个 phase，这个最基本的结构操作就会失败。

---

## 二、根因分析

### 2.1 DeepResearch：`quick_research` 静默降级陷阱

#### 现状调用链

```
用户点击"做调研"
  → Agent 调用 run_research 工具
    → _run_research_impl()                      [agent_tools.py:734]
      → deep_research(query, intent)            [deep_research.py:233]
        → plan_search_queries(query, intent)    生成 5 个搜索词
        → search_tavily(q) × 5                  Tavily 网络搜索
        → 去重后得到 unique_results
        ┌─ 有结果 → synthesize_report()         基于真实搜索结果综合
        └─ 无结果 → quick_research() ⚠️         纯 LLM 臆造，静默返回
      → report 存入 ContentBlock "消费者调研"
      → 返回 summary 给 Agent
```

#### 根因 #1：`quick_research` 是一个伪装成正常结果的错误

`quick_research()` 的返回类型是 `ResearchReport`——和 `deep_research()` 完全相同的数据结构。下游消费者（存储层、前端渲染、Agent 后续引用）无法区分这份报告来自真实搜索还是 LLM 编造。

它的 prompt 明确说"请勿添加引用标注"、sources 返回空列表。但报告中仍然有 `summary`、`consumer_profile`、`pain_points`、`personas` 等看起来很专业的字段——用户根本看不出这是 AI 瞎编的。

**这不是"降级"，这是"静默欺骗"。** 正确的降级是告诉用户"搜索失败了，请重试"。

#### 根因 #2：`plan_search_queries` 消费者偏向导致搜索空结果

`plan_search_queries` 的 system prompt 是硬编码的消费者调研策略：

```
你是一个搜索策略专家。你的任务是生成有效的搜索查询词，帮助了解特定项目的目标用户群体。
...
请为这个项目生成5个针对性的搜索查询词，用于了解它的目标受众是谁、有什么痛点和需求。
```

当 `research_type="generic"`（通用调研）时，同样的 prompt 仍然围绕"目标用户群体"生成查询词。如果用户要求调研的是"X 市场的竞争格局"或"Y 技术的发展趋势"，生成的搜索词与真实意图偏离，导致 Tavily 返回零相关结果 → 触发 `quick_research` 降级。

**移除 `quick_research` 后，这条路径会变成显式错误。** 但"搜索词不准 → 搜不到东西 → 报错"的体验仍然不好。正确做法是让查询规划能区分消费者调研和通用调研。

### 2.2 manage_architecture(add_field)：组名解析断裂

#### 现状失败链路

```
1. 用户输入: "帮我在「前期调研」里加一个内容块叫XXX"
   ↓
2. @ 引用系统: 只支持 field（内容块），不支持 phase（组）
   → "前期调研" 无法被解析为精确引用
   → Agent 只收到自由文本
   ↓
3. Agent 系统上下文:
   → 看到 "当前组: research"
   → 看到 "项目组顺序: intent → research → design_inner → ..."
   → 全部是内部代码，没有 "前期调研" ↔ "research" 的映射说明
   ↓
4. Agent (LLM) 构造工具调用:
   → manage_architecture("add_field", "XXX", '{"phase":"前期调研"}')
   → phase 参数使用了用户原文，不是内部代码
   ↓
5. manage_architecture 收到 phase="前期调研"
   → 原封不动传给 add_field()，无任何别名解析
   ↓
6. add_field() 校验: "前期调研" not in project.phase_order
   → project.phase_order = ["intent", "research", "design_inner", ...]
   → 失败: OperationResult(success=False, message="阶段 '前期调研' 不存在")
```

#### 根因 #1（Layer 2 — 工具层）：无别名解析

`manage_architecture` → `add_field()` 接收到的 `phase` 参数，直接与 `project.phase_order`（内部代码列表）比较。系统已经有 `PHASE_ALIAS`（中文名 → 内部代码）和 `PHASE_DISPLAY_NAMES`（内部代码 → 显示名），但 `add_field` 从未使用它们。

即使 Agent 完美传递了显示名 `"消费者调研"`，也会被 `add_field` 拒绝。

这是**必修的**。工具层应该对输入做归一化，不应假设 LLM 总能给出完美的内部代码。

#### 根因 #2（Layer 1 — 上下文层）：Agent 缺乏组名映射信息

系统给 Agent 看的组上下文是：

```
当前组: research
项目组顺序: intent → research → design_inner → produce_inner → ...
```

全部是内部代码。Agent 需要自行推断 "前期调研" = "research"，但系统没有提供任何映射信息。

这是**锦上添花的**。即使 Agent 传了中文名，Layer 2 的别名解析也能兜底。但提供映射信息可以让 Agent 更频繁地直接传出正确的内部代码，减少 fallback 依赖。

#### 根因 #3（结构层）：`@` 引用系统不支持组

前端 `mentionItems` 构建逻辑（`agent-panel.tsx:161-198`）只包含 `block_type === "field"` 的内容块。组（phase）不在可引用范围内。

这意味着用户想精确引用一个组时，只能用自然语言描述。对于"在 XX 组加一个内容块"这种高精度操作，缺乏精确引用是根本性的交互缺陷。

但这是一个更大的改动（前端 + 后端），**不在本次修复范围内**。本次通过 Layer 2 别名解析 + Layer 1 上下文增强来解决。

---

## 三、修复方案

### M8a：移除 `quick_research`，修复搜索查询策略

**目标**：消灭静默降级，让 DeepResearch 要么返回真实结果，要么明确告诉用户失败原因。同步修复搜索查询策略的消费者偏向。

### M8b：`manage_architecture` 组名别名解析

**目标**：让 `add_field` / `move_field` 等需要 phase 参数的操作能正确解析中文组名、显示名、别名，不再要求 Agent 必须传出精确的内部代码。

---

## 四、涉及文件与改动范围

### M8a 文件清单

| 文件 | 改动类型 | 具体内容 |
|------|---------|---------|
| `backend/core/tools/deep_research.py` | **修改** | 1) 删除 `quick_research()` 函数（L304-342）<br>2) `deep_research()` 中移除降级分支（L284-286），改为 `raise ValueError` 明确报错<br>3) `plan_search_queries()` 增加 `research_type` 参数，区分消费者/通用调研的 prompt<br>4) 更新文件头注释 |
| `backend/core/agent_tools.py` | **修改** | 1) `_run_research_impl` 移除 `import quick_research`（L735）<br>2) 将 `research_type` 传递给 `deep_research()`，让查询规划知道调研类型 |
| `backend/core/tools/__init__.py` | **修改** | 移除 `quick_research` 的导入和 `__all__` 导出（L12, L107） |
| `docs/agent_architecture_analysis.md` | **修改** | 移除 `quick_research` 引用（L37, L191） |
| `docs/deep_research.md` | **重写** | 当前文档内容已完全过时（仍引用 DuckDuckGo + Jina），更新为 Tavily 架构 |

**不改的文件**（已确认安全）：

| 文件 | 不改原因 |
|------|---------|
| `_run_research_impl()` 的调用逻辑 | 它只调 `deep_research()`，降级逻辑在 `deep_research` 内部处理 |
| `api/projects.py` | `use_deep_research` 只是项目配置字段，工具执行时未检查，属于历史遗留死标志 |
| `tests/test_langgraph_migration.py` | 只测 `deep_research` 导入，不涉及 `quick_research` |
| 前端代码 | 前端只消费 `ResearchReport` 的 JSON 结构，不区分来源 |

### M8b 文件清单

| 文件 | 改动类型 | 具体内容 |
|------|---------|---------|
| `backend/core/tools/architecture_writer.py` | **修改** | `add_field()` 开头增加 phase 别名解析：用 `PHASE_ALIAS` + `PHASE_DISPLAY_NAMES` 反查，将中文名/显示名/别名统一解析为内部代码。同样修复 `move_field()` |
| `backend/core/orchestrator.py` | **修改** | `build_system_prompt` 的组状态段落，将 `intent → research → ...` 改为 `intent(意图分析) → research(消费者调研) → ...`，让 Agent 看到 code ↔ display_name 的映射 |

**不改的文件**（已确认安全）：

| 文件 | 不改原因 |
|------|---------|
| `manage_architecture()` in `agent_tools.py` | 不在此层做解析；解析下沉到 `add_field()` / `move_field()`，因为它们是真正校验 phase 的地方，也可能被其他调用方复用 |
| `phase_config.py` | 纯数据定义，不需要改动。`PHASE_ALIAS` 已有足够映射 |
| `phase_service.py` | `advance_to_phase` 已经用了 `PHASE_ALIAS` 做解析，是正确的参考实现 |
| 前端 `@` 引用系统 | 扩展 `@` 支持组引用是更大的功能变更，不在本次范围 |

---

## 五、里程碑与 Todo

### M8a：移除 quick_research + 修复搜索策略

#### 后端

- [x] **T8a.1** `deep_research.py`：删除 `quick_research()` 函数
  - 删除整个函数体
  - 更新文件头注释，移除 `quick_research()` 引用

- [x] **T8a.2** `deep_research.py`：`deep_research()` 移除静默降级
  - 原代码：`if not unique_results: return await quick_research(query, intent)`
  - 替换为：`raise ValueError("Tavily 搜索未返回任何结果...")`，附带可能原因提示
  - 这个异常会被 `_run_research_impl` 的 `except` 捕获，返回 `"❌ 调研执行失败"` 给 Agent
  - Agent 会如实告知用户搜索失败，用户可以调整主题后重试

- [x] **T8a.3** `deep_research.py`：`plan_search_queries()` 区分调研类型
  - 增加 `research_type: str = "consumer"` 参数
  - `research_type="consumer"` 时使用消费者调研 prompt（目标用户、痛点、需求）
  - `research_type="generic"` 时使用通用调研 prompt（市场现状、竞争格局、趋势、关键玩家、技术发展）

- [x] **T8a.4** `deep_research.py`：`deep_research()` 接收并传递 `research_type`
  - 签名增加 `research_type: str = "consumer"`
  - 传给 `plan_search_queries(query, intent, research_type)`

- [x] **T8a.5** `agent_tools.py`：`_run_research_impl` 传递 `research_type`
  - 移除 `import quick_research`
  - 将 `research_type` 参数传给 `deep_research()` 调用

- [x] **T8a.6** `__init__.py`：清理导出
  - 移除 `quick_research` 的 import 和 `__all__` 导出

#### 文档

- [x] **T8a.7** `docs/agent_architecture_analysis.md`：移除 `quick_research` 引用
  - 工具表格中移除"快速调研"行，更新"深度调研"为 Tavily 签名
  - 阶段节点图中移除 `quick_research` 引用

- [x] **T8a.8** `docs/deep_research.md`：重写文档
  - 完全重写为 Tavily 架构（原内容引用 DuckDuckGo + Jina，已完全过时）
  - 包含：架构流程图、调用链、核心函数表、数据结构、错误处理策略、成本分析

### M8b：manage_architecture 组名别名解析

#### 后端

- [x] **T8b.1** `architecture_writer.py`：`add_field()` 增加 phase 别名解析
  - 新增 `_resolve_phase_code(phase, phase_order)` 函数，解析优先级：
    1. 完全匹配 `phase_order` 中的 code
    2. `PHASE_ALIAS` 匹配（display_name→code 和自定义别名→code）
    3. `PHASE_DISPLAY_NAMES` 反查
  - `add_field()` 在校验前调用 `_resolve_phase_code()` 解析 phase 参数

- [x] **T8b.2** `architecture_writer.py`：`move_field()` 同步增加别名解析
  - 复用 `_resolve_phase_code()` 解析 `target_phase` 参数

- [x] **T8b.3** `orchestrator.py`：组状态上下文增加 code ↔ 显示名映射
  - 格式改为 `"intent(意图分析) → research(消费者调研) → ..."`
  - 追加提示：`manage_architecture` 的 phase 参数支持内部 code 或中文显示名

---

## 六、安全性验证清单

每个 Todo 完成后，需验证以下项目：

### M8a 验证

| 验证项 | 方法 | 预期结果 |
|--------|------|---------|
| Tavily API 正常时，调研流程正常完成 | 启动后端，Agent 执行 `run_research` | 返回含真实 URL 和引用标注的 `ResearchReport` |
| Tavily 无结果时，返回明确错误 | mock `search_tavily` 返回空列表 | Agent 回复包含"调研执行失败"字样，不返回虚假报告 |
| generic 调研生成正确的搜索词 | 检查 `plan_search_queries` 日志 | 搜索词与调研主题相关，不全是"目标用户群体"类查询 |
| `quick_research` 无残留引用 | 全项目 grep `quick_research` | 零结果 |

### M8b 验证

| 验证项 | 方法 | 预期结果 |
|--------|------|---------|
| 内部代码正常工作 | `add_field(phase="research", ...)` | 成功 |
| 显示名正常工作 | `add_field(phase="消费者调研", ...)` | 解析为 "research"，成功 |
| 别名正常工作 | `add_field(phase="调研", ...)` | 解析为 "research"，成功 |
| 无效组名报错清晰 | `add_field(phase="不存在的组", ...)` | 返回"阶段不存在"，附带可用组列表 |
| Agent 看到映射信息 | 检查 system prompt 日志 | 组顺序含 `research(消费者调研)` 格式 |
| `move_field` 同样支持别名 | `move_field(target_phase="内涵设计", ...)` | 解析为 "design_inner"，成功 |

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 移除 `quick_research` 后 Tavily API 故障 = 调研彻底不可用 | 用户无法完成调研步骤 | `search_tavily` 的 `except` 块已返回空列表，`deep_research` 会触发明确错误信息。Agent 告知用户"搜索服务暂时不可用，请稍后重试" — 这比返回虚假报告更诚实、更安全 |
| Tavily API 配额耗尽（免费 1000 次/月） | 同上 | Tavily 配额耗尽时 API 会返回错误码，`search_tavily` 捕获异常并记录，用户看到明确失败信息 |
| 通用调研的新 prompt 生成的搜索词质量待验证 | 搜索结果可能不理想 | T8a.3 是 prompt 修改，可通过实际测试几个 generic 主题验证搜索词质量，迭代调优 |
| 别名解析的优先级冲突（如果两个别名指向不同 phase） | 理论上可能，实践中 `PHASE_ALIAS` 是手工维护的，冲突概率极低 | `_resolve_phase_code` 按固定优先级链解析：原值 → PHASE_ALIAS → PHASE_DISPLAY_NAMES 反查 |
| Agent 仍可能传出系统不认识的组名 | `_resolve_phase_code` 返回原值，最终被 phase_order 校验拒绝 | 改进错误信息：从 `"阶段 'XX' 不存在"` 改为 `"阶段 'XX' 不存在，可用的组: intent(意图分析), research(消费者调研), ..."`，帮助 Agent 自我修正 |
| `docs/deep_research.md` 重写可能遗漏信息 | 历史设计决策丢失 | 旧文档已完全过时（DuckDuckGo + Jina），不存在需要保留的有效信息 |
| `use_deep_research` 项目配置标志是死代码 | 用户在项目设置中关闭了 DeepResearch 但工具仍会执行 | **不在本次修复范围**。标记为已知技术债务，后续决定是否移除或接入 |

---

## 八、与项目架构的融贯性

### 与 `first_principles.md` 的关系

| 第一性原理 | 本次修复的对应 |
|-----------|--------------|
| **以终为始**：先调研，再倒推内容 | M8a 确保调研结果是真实的网络搜索，而非 LLM 臆造。虚假调研 = 以终为始的链条从源头断裂 |
| **结构化拆解**：内容拆成可评估的原子单元 | M8b 确保用户能正确地在结构树中添加内容块。组名解析失败 = 无法修改结构 |
| **Agent 引领流程**：Agent 主动推进 | 两个修复都让 Agent 的工具调用更可靠。工具失败 = Agent 无法推进流程 |

### 与 `cursorrule.md` 的关系

| cursorrule 原则 | 本次修复的遵循 |
|----------------|--------------|
| **简单优先** | `_resolve_phase_code` 是一个 5 行的纯函数，不引入新依赖 |
| **避免代码重复** | `_resolve_phase_code` 提取为公共函数，`add_field` 和 `move_field` 复用 |
| **修复前穷尽现有方案** | 别名解析复用已有的 `PHASE_ALIAS` + `PHASE_DISPLAY_NAMES`，不新增映射表 |
| **不修改无关代码** | 只改 6 个文件，每个文件改动范围清晰，不涉及前端或其他工具 |

### 与 `suggestion_card_design.md` 的关系

M8a/M8b 与 Suggestion Card 系统无交叉。它们分别修复的是调研工具和结构管理工具，不涉及 propose_edit / confirm-suggestion / SSE 流等 Suggestion Card 链路。

### 与 `phase_service.py` 的一致性

`phase_service.py:59` 中 `advance_to_phase` 已经使用了 `PHASE_ALIAS` 做别名解析：

```python
resolved = PHASE_ALIAS.get(target_phase.strip(), target_phase.strip())
```

M8b 的 `_resolve_phase_code` 采用相同的模式，保持整个 phase 相关操作的一致性。

---

## 九、不在本次范围内的已知问题

以下问题在排查过程中发现，记录但**不在本次修复**：

| 问题 | 原因 | 建议 |
|------|------|------|
| `@` 引用系统不支持组（phase） | `mentionItems` 只包含 `block_type === "field"` | 后续考虑扩展 `@` 支持组引用，需前端 + 后端联动 |
| `use_deep_research` 项目标志是死代码 | `_run_research_impl` 未检查此标志 | 后续决定：移除标志 or 在工具层检查并跳过 |
| `docs/deep_research.md` 内容完全过时 | 仍引用 DuckDuckGo + Jina，实际已切换到 Tavily | T8a.8 会重写此文档 |

---

> 下一步：按 M8a → M8b 顺序执行。M8a 的 T8a.1-T8a.2 是最高优先级（消灭静默降级），T8a.3-T8a.4 紧随其后（修复搜索策略），M8b 独立并行。

