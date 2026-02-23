# 工具安全性与 Deep Research 修复（根治版）

创建时间：2026-02-22
最后更新：2026-02-23
状态：完成

---

## 问题诊断

### 问题一：内容修改太容易触发"重写内容块"

用户要求局部修改时，Agent 调用 `rewrite_field`（直接写 DB）而非 `propose_edit`（确认流程）。

### 问题二：Deep Research 返回编造内容

LLM 调用 `generate_field_content("消费者调研报告")` 绕过 `run_research`，用训练数据编造调研报告。

---

## 第一轮修复回顾（治标 → 已被根治替换）

| 编号 | 改动 | 判定 | 根治方案 |
|------|------|------|----------|
| T1 | `_is_structured_handler` 运行时查父块 | 治标 | R1: 数据层传播 special_handler |
| T2 | `_run_research_impl` 保存目标加 `block_type="field"` | 正确 | 保留不变 |
| T3 | `user_message` 塞进 `configurable` + 双重关键词检查 | 偷懒 | R2: 已移除 |
| T4 | `rewrite_field` 走 SuggestionCard | 方向对 | R3: 正式化 card_type |
| T5 | `generate_field_content` 关键词匹配守护 | 硬编码 | R2: 简化为"有内容就拒绝" |
| T7 | Deep Research SSE 日志增强 | 正确 | 保留不变 |

---

## 根治方案（已完成）

### R1. 数据层 `special_handler` 传播 -- DONE

**根因**：`phase_template.py::apply_to_project()` 创建子 field 块时没有传递父 phase 的 `special_handler`。

**修复内容**：
- [x] R1a. `phase_template.py::apply_to_project()` 子 field 继承 `special_handler`
  - `field.get("special_handler", phase_handler)`: field 自身定义优先，否则继承 phase
- [x] R1b. 迁移脚本 `scripts/migrate_special_handler.py` 回填已有数据
  - 找 parent.special_handler 非空但 child.special_handler 为空的记录，回填
- [x] R1c. `_is_structured_handler()` 移除运行时父块查询，恢复为单层检查
  - 从 22 行 → 5 行，无额外 DB 查询
- [x] R1d. 移除 `"(继承自父块)"` fallback（子块自身有 handler 了）

**替换验证**：T1 的 `parent_id` 查询代码已被删除，`_is_structured_handler` 是纯内存操作。

---

### R2. 移除 `user_message` hack，简化 `generate_field_content` 防护 -- DONE

**设计原则**：
> "修改是决策不是执行" — `rewrite_field` 走 SuggestionCard 后，用户有最终确认权。
> 关键词匹配是脆弱的意图分类方式，不该替代 LLM 判断或用户确认。

**修复内容**：
- [x] R2a. `_rewrite_field_impl` 移除 `user_message` 双重检查
  - 保留 `_is_explicit_rewrite_intent(instruction)` 单层检查（T4 之前就有）
  - SuggestionCard 确认流程是真正的兜底防线
- [x] R2b. `_generate_field_impl` 已有内容一律拒绝
  - 移除 10 个关键词的匹配列表
  - 简化为 `if entity.content and entity.content.strip(): return error`
  - 引导到 `propose_edit` 或 `rewrite_field`
- [x] R2c. `generate_field_content` docstring 删除"全部重写"用例
  - 明确为"空块首次生成"专用
- [x] R2d. `api/agent.py` 移除 `user_message` 从 `configurable`
  - 恢复 config 只含 `thread_id` 和 `project_id`

**替换验证**：所有 `user_message` 相关代码已被删除（grep 验证无残留）。

---

### R3. 正式化 SuggestionCard `card_type` -- DONE

**修复内容**：
- [x] R3a. `propose_edit` card 增加 `card_type: "anchor_edit"`
- [x] R3b. `rewrite_field` card 用 `card_type: "full_rewrite"` 替代 ad-hoc `rewrite_mode`
  - `changes` 从 `[{"status":"applied","type":"full_rewrite"}]` → `[]`
  - 移除 `rewrite_mode: "full_replace"` 字段
- [x] R3c. `confirm-suggestion` 用 `card.get("card_type") == "full_rewrite"` 做分支
  - 替代原有的 `card.get("rewrite_mode") == "full_replace"`

**替换验证**：`rewrite_mode` 关键词已从所有源文件中移除。

---

## 测试结果

```
工具安全性测试（根治版）
============================================================
PASS: test_structured_handler_direct
PASS: test_structured_handler_child_has_handler
PASS: test_structured_handler_normal_field
PASS: test_template_propagates_special_handler
PASS: test_rewrite_intent_detection
PASS: test_rewrite_field_rejects_non_rewrite_instruction
PASS: test_rewrite_field_produces_suggestion_card
PASS: test_generate_rejects_existing_content
PASS: test_generate_rejects_existing_even_with_regen_keyword
PASS: test_generate_rejects_research_field
PASS: test_research_saves_to_field_block
PASS: test_confirm_full_rewrite_card
PASS: test_confirm_full_rewrite_card_with_conflict
============================================================
结果: 13 passed, 0 failed, 13 total
```

---

## 修改文件清单

| 文件 | 改动要点 |
|------|----------|
| `backend/core/models/phase_template.py` | 子 field 继承父 phase 的 `special_handler` |
| `backend/scripts/migrate_special_handler.py` | 新增: 回填历史数据迁移脚本 |
| `backend/core/agent_tools.py` | `_is_structured_handler` 简化、`_rewrite_field_impl` 移除 user_message、`_generate_field_impl` 已有内容一律拒绝、SuggestionCard 增加 `card_type` |
| `backend/api/agent.py` | 移除 `user_message` 从 configurable、`confirm-suggestion` 用 `card_type` |
| `backend/tests/test_tool_safety.py` | 全面重写: 13 个测试覆盖根治逻辑 |

---

## 防御体系最终状态

```
用户消息 → LLM 选择工具
                ↓
     ┌──────────┼──────────┐
     ▼          ▼          ▼
propose_edit  rewrite_field  generate_field_content
     │          │               │
     │    instruction 关键词    有内容？
     │    检查（soft guard）    ├─ 是 → 拒绝，引导到
     │          │               │       rewrite/propose_edit
     │          ▼               ├─ 否 → 执行生成（首次）
     │    LLM 生成新内容        │
     │          │               └─ structured_handler? → 拒绝
     │          ▼
     │    SuggestionCard ← card_type="full_rewrite"
     │    （用户确认）
     ▼
SuggestionCard ← card_type="anchor_edit"
（用户确认）
```

核心原则：**所有覆写已有内容的操作都走 SuggestionCard 确认流程**。`generate_field_content` 只允许对空块写 DB，是唯一的直接写入路径。
