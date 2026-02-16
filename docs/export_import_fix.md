# 项目导入/导出/复制 完整性修复

## 问题概述

项目级导入/导出（`export_project` / `import_project`）及复制（`duplicate_project`）存在多处数据缺失和 Bug，导致还原后的项目状态不完整。

## 缺陷清单（全部已修复）

### M1: 关键 Bug 修复（Export/Import）-- DONE

| ID | 问题 | 严重性 | 修复 |
|----|------|--------|------|
| T1.1 | CreatorProfile import 使用不存在的字段（`style_tags`, `tone`, `values` 等），实际模型只有 `name`, `description`, `traits` | CRITICAL | 改为使用 `traits` JSON 字段 |
| T1.2 | 导入时所有实体的 `created_at` / `updated_at` 丢失，被替换为当前时间 | HIGH | 添加 `_set_timestamps()` 辅助函数，从导出数据中恢复原始时间戳 |

### M2: 导出/导入缺失数据 -- DONE

| ID | 问题 | 修复 |
|----|------|------|
| T2.1 | MemoryItem 未导出 | 添加项目记忆 + 全局记忆导出 |
| T2.2 | MemoryItem 未导入 | 添加导入逻辑，全局记忆保持 project_id=None |
| T2.3 | Grader（project_id 关联）未导出 | 添加项目专用评分器导出 |
| T2.4 | Grader（project_id 关联）未导入 | 添加导入逻辑 |
| T2.5 | export_version 需升级为 "2.0" | 已升级 |

### M3: delete_project 数据完整性 -- DONE

| ID | 问题 | 修复 |
|----|------|------|
| T3.1 | delete_project 未清理 MemoryItem | 添加 `MemoryItem.project_id == project_id` 删除 |
| T3.2 | delete_project 未清理 Grader | 添加 `Grader.project_id == project_id` 删除 |

### M4: duplicate_project 数据完整性 -- DONE

| ID | 缺失数据 | 修复 |
|----|----------|------|
| T4.1 | MemoryItem 未复制 | 添加项目记忆复制 |
| T4.2 | ContentVersion 未复制 | 添加版本历史复制（block_id 重映射） |
| T4.3 | BlockHistory 未复制 | 添加操作历史复制（快照内 ID 重映射） |
| T4.4 | SimulationRecord 未复制 | 添加模拟记录复制（target_field_ids 重映射） |
| T4.5 | EvalRun/EvalTask/EvalTrial 未复制 | 添加评估全链路复制（run/task/trial ID 互相重映射） |
| T4.6 | Grader（project_id 关联）未复制 | 添加项目专用评分器复制 |

### 已知限制（不修复，已评估为可接受）

| 项目 | 原因 | 影响 |
|------|------|------|
| LangGraph Checkpoints | 存储在独立 SQLite DB (`agent_checkpoints.db`) 中，为序列化 BLOB 格式。解析和重映射 checkpoint 内部状态涉及 LangGraph 私有序列化格式，风险高、收益低。 | 导入后 Agent 对话状态从零开始，但 ChatMessage 历史完整保留，用户仍可在 UI 中看到所有历史对话。Agent 的 context window 有 trim_messages 100K 限制，旧消息本就会被裁剪。 |
| PENDING_SUGGESTIONS 内存缓存 | 运行时内存状态，重启即丢失。Suggestion Card 状态已通过 ChatMessage.message_metadata.suggestion_cards 持久化，导入后历史卡片可正常显示。 | 无实质影响 |

## 修改文件

- `backend/api/projects.py` -- export_project, import_project, delete_project, duplicate_project

## 数据模型对照（修复后）

| 模型 | export | import | delete | duplicate |
|------|--------|--------|--------|-----------|
| Project | OK | OK | OK | OK |
| CreatorProfile | OK | OK | N/A | OK |
| ContentBlock | OK | OK | OK | OK |
| ProjectField | OK | OK | OK | OK |
| ChatMessage | OK | OK | OK | OK |
| ContentVersion | OK | OK | OK | OK |
| BlockHistory | OK | OK | OK | OK |
| SimulationRecord | OK | OK | OK | OK |
| EvalRun | OK | OK | OK | OK |
| EvalTask | OK | OK | OK | OK |
| EvalTrial | OK | OK | OK | OK |
| GenerationLog | OK(可选) | OK | OK | 不需要(日志) |
| MemoryItem | OK | OK | OK | OK |
| Grader | OK | OK | OK | OK |

## 向后兼容

- v1.0 导出文件（不含 `memory_items` / `graders`）可正常导入，这些字段默认为空数组
- v2.0 导出文件包含完整数据
