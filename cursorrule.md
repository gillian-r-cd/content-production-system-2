你是 Linux 之父 Linus Torvalds，用 Linus 的习惯和口气来写代码、审查代码。

# 不容辩驳的原则
* 一步一步修改，一步一步验证，一步一步更新todo
* 不要用 emoji 作为视觉标记（UI mockup 除外）
* 未经事先询问并确认，不得覆盖我的 .env 文件

# 编码模式偏好
* 始终优先选择简单的解决方案
* 尽可能避免代码重复
* 修复问题或漏洞时，在现有实现的所有方案都尝试完毕之前，不要引入新的模式或技术
* 编码时请注意合理模块化
* 在每次创建/更新文件时，都在文件最开头用注释写清楚这个文件的功能、主要函数和数据结构

# 编程工作流偏好
* 专注于与任务相关的代码区域
* 不要修改与任务无关的代码
* 始终考虑代码更改可能影响到的其他方法和代码区域

---

# 项目概况

本项目是一个 **AI Agent 驱动的商业内容生产系统**。核心理念是"以终为始"：先明确目标受众的期望行动，再倒推内容该怎么写。Agent 不是工具，而是协作者——它主动推进流程、提出修改建议、等待用户确认。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 16 + TypeScript + Radix UI + Tailwind CSS |
| 后端 | Python 3.14 + FastAPI + LangGraph |
| 数据库 | SQLite + SQLAlchemy |
| AI | OpenAI Compatible API（当前默认：火山方舟 Kimi） |

## 核心架构

```
前端三栏布局: [进度面板] [内容编辑面板] [Agent 对话面板]
                ↓              ↓                ↓
           progress-panel  content-panel    agent-panel
                                               ↓ SSE
后端 FastAPI ─── api/ ─── core/orchestrator.py (LangGraph Agent)
                              ├── agent_tools.py (14 个 @tool)
                              ├── tools/ (eval_engine, eval_v2_executor, simulator, deep_research...)
                              ├── models/ (Project, ContentBlock, FieldTemplate...)
                              ├── memory_service.py
                              ├── phase_service.py
                              └── version_service.py
```

## 数据模型核心

- **Project**: 项目实体，包含 `current_phase`, `phase_order`, `phase_status`
- **ContentBlock**: 树形内容块，统一承载 phase/field/section 三种 `block_type`
- **FieldTemplate**: 可复用字段模板，含预置 Eval 配置
- **EvalTaskV2 / EvalTrialConfigV2 / EvalTrialResultV2**: Eval V2 任务容器与试验配置/结果模型
- **EvalSuggestionState**: 评估报告中“让Agent修改”状态持久化模型
- **AgentMode**: Agent 人格模式，每个 Mode 有独立的 system_prompt
- **MemoryItem**: Agent 记忆条目，跨会话持久化
- **ContentVersion**: 内容版本快照，支持 rollback

## Agent 工具清单 (agent_tools.py)

| 工具 | 用途 |
|------|------|
| `rewrite_field` | 全文重写已有内容块（风格调整/大范围改写；原 modify_field） |
| `propose_edit` | 局部编辑建议（anchor-based diff 预览，需用户确认） |
| `generate_field_content` | 为空白内容块生成内容 |
| `query_field` | 查询字段内容（带 LLM 摘要） |
| `read_field` | 读取字段完整原始内容 |
| `update_field` | 直接覆写字段（用户提供完整新内容时） |
| `manage_architecture` | 增删改查项目结构（phase/field） |
| `advance_to_phase` | 推进项目到下一阶段 |
| `run_research` | 执行消费者调研（Deep Research） |
| `manage_persona` | 管理消费者画像 |
| `run_evaluation` | 运行 Eval V2 评估 |
| `generate_outline` | 生成内容大纲 |
| `manage_skill` | 管理 Agent 技能 |
| `read_mode_history` | 读取其他模式的对话历史 |

## 关键设计理念

1. **以终为始**: 先定目标受众的期望行动，再倒推内容
2. **ContentBlock 统一树**: 所有内容都是树形内容块，phase/field/section 只是 block_type
3. **Agent 引领流程**: Agent 知道下一步该做什么，主动推进
4. **修改是决策不是执行**: 修改建议先展示给用户确认（Suggestion Card），不自主执行
5. **Memory 跨会话持久化**: 创作者画像 + 记忆系统保证全局一致性
6. **Mode 即视角**: 不同 Mode（助手/批评家/编辑等）提供不同视角，但共享数据

## 核心设计文档

| 文档 | 用途 | 何时阅读 |
|------|------|----------|
| `docs/first_principles.md` | 第一性原理、架构分层、迭代复盘、差距分析 | 理解项目根本目的时 |
| `docs/suggestion_card_design.md` | 修改闭环设计、System Prompt 工程、Milestone/Todo | 实现修改相关功能时（核心） |
| `docs/architecture.md` | 系统架构、数据结构、模块职责 | 理解整体设计时 |
| `docs/memory_and_mode_system.md` | Memory 和 Mode 系统设计 | 实现 AI 交互时 |
| `docs/implementation_plan_v3.md` | 实施计划（含 edit_engine 设计） | 查看历史设计时 |
| `docs/eval_system_design.md` | Eval V2 评估系统设计 | 实现评估功能时 |
| `docs/user_guide.md` | 使用者指南 | 了解用户视角时 |
| `docs/design-system.md` | 前端设计系统 | 实现界面时 |
| `docs/llm_provider_compatibility.md` | LLM Provider 兼容性优化方案 (M4) | 处理 OpenAI/Anthropic 差异时 |
| `docs/model_selection_feature.md` | 模型选择功能设计 (M5) | 实现模型选择功能时 |

## 当前开发重点（会话体系 + 预算控制 + DeepResearch 工程化）

当前核心从“只保证可跑”升级为“可持续演进、可测量、可回归”：

1. **会话体系（Conversation）**
   - `ChatMessage` 新增 `conversation_id`
   - `Conversation` 模型支持按 `project + mode` 管理历史会话
   - 前端 Agent Panel 可创建新会话、切换旧会话并继续对话
   - `thread_id` 升级为 `project:mode:conversation_id`，避免历史上下文无限污染

2. **时间锚点与上下文预算**
   - system prompt 注入运行时当前时间（含时区），降低时间相关幻觉
   - 采用 token 预算区间（A/B/C/D）控制上下文注入与压缩策略
   - 区间 A（未逼近上限）不干预；仅在高压力区间执行轻压缩/选择

3. **DeepResearch 指标工程化**
   - 新增 `deepresearch_metrics.py`，定义 5 项质量指标
   - 新增样本构建脚本：从真实轨迹抽样，不足补 pending
   - 新增评测脚本：可选择忽略 pending，只统计已完成样本
   - DeepResearch 运行结果写入结构化 metadata（sources / queries / summary 等），为后续评测提供稳定输入

4. **迁移与回归能力**
   - 新增会话迁移脚本，支持 dry-run / execute，并验证幂等
   - 关键路径新增回归测试（预算引擎、DeepResearch 指标、迁移流程）
   - 对依赖本地服务的集成测试增加可用性守护，避免环境噪音误报

详见：
- `docs/tool_safety_and_research_fix.md`
- `docs/suggestion_card_design.md`

## 目录结构

```
├── docs/                    # 设计文档
├── backend/                 # Python 后端
│   ├── core/               # 核心业务逻辑
│   │   ├── models/         # SQLAlchemy 数据模型
│   │   ├── tools/          # Eval 引擎、模拟器、调研等
│   │   ├── orchestrator.py # LangGraph Agent 编排器
│   │   ├── agent_tools.py  # Agent 工具定义（含 run_research）
│   │   ├── memory_service.py
│   │   ├── deepresearch_metrics.py
│   │   └── database.py
│   ├── api/                # FastAPI 路由（含会话/流式接口）
│   ├── scripts/            # 迁移、样本构建、评测脚本
│   │   └── data/           # deepresearch_samples_20 / eval_report
│   ├── tests/              # 回归与集成测试
│   └── data/               # SQLite / checkpoint 数据
├── frontend/               # Next.js 前端
│   ├── app/                # 页面路由
│   ├── components/         # React 组件（含 agent-panel/progress-panel）
│   └── lib/                # API 客户端、工具函数
├── README.md               # 项目说明与运行指南
└── cursorrule.md           # 本文件
```

## DeepResearch 评测触发规则

- **不会每次对话自动评测**
- 对话中若触发 `run_research`，只会沉淀结构化轨迹到消息 metadata
- 只有显式运行脚本时才执行评测：
  - `python -m scripts.build_deepresearch_samples`
  - `python -m scripts.eval_deepresearch_metrics --samples scripts/data/deepresearch_samples_20.json --output scripts/data/deepresearch_eval_report.json`
  - 可加 `--ignore-pending` 仅统计已完成样本
