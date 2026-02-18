# 内容评估体系 (Eval System) 设计文档

> 2026-02-19 更新说明：本文保留历史设计语境；当前线上实现以 `eval_v2_redesign.md` 为准。
> 关键差异：`EvalRun` 旧链路已降级为兼容层，主链路为 `Project -> EvalTaskV2 -> EvalTrialConfigV2 -> EvalTrialResultV2`。

## 一、设计理念

### 核心问题
内容的价值 = **在特定场景下，对特定人群，实现特定目标的能力**

评估必须是**情境化的**：
1. **谁在看？** → Simulator 角色（不是交互方式）
2. **什么时候看？** → 内容生产的哪个阶段
3. **看什么？** → 评估的内容范围（哪些字段/内容块）
4. **怎么判断好不好？** → Grader（评分标准）
5. **发现了什么模式？** → Diagnoser（跨 Trial 诊断）

### 与旧系统的区别
| 旧系统 | 新系统 |
|-------|-------|
| 5种交互类型（对话/阅读/决策/探索/体验） | 5种评估角色（教练/编辑/专家/消费者/销售） |
| 交互方式决定了评估方式 | 角色视角决定评估维度，交互方式是可选的 |
| Simulator 和 Evaluator 分离 | 统一为角色驱动的 Eval 体系 |
| 评估结果存在独立模型里 | 评估结果就是 ContentBlock，可被其他字段引用 |

---

## 二、Simulator 角色定义

### 5种核心角色

| 角色 | 英文 | 核心视角 | 核心问题 | 知识边界 |
|------|------|---------|---------|---------|
| **教练** | Coach | 策略 | "方向对不对？" | creator_profile + intent + 市场认知 |
| **编辑** | Editor | 手艺 | "做得好不好？" | 写作标准 + 品牌语气 + 行业规范 |
| **领域专家** | Expert | 专业 | "准不准？" | 行业知识 + 竞品信息 + 数据 |
| **消费者** | Consumer | 用户体验 | "对我有用吗？" | persona背景 + 需求 + 痛点 |
| **内容销售** | Seller | 转化 | "能卖出去吗？" | 内容本身 + 目标人群画像 |

### 交互模式（每个角色可选）
- **审查模式 (review)**: 一次性阅读全部内容，给出结构化反馈
- **对话模式 (dialogue)**: 多轮交互
- **场景模式 (scenario)**: 模拟特定场景流程

---

## 三、Grader 评分体系

### 三级评分
| 级别 | 评分时机 | 适用场景 | 价值 |
|------|---------|---------|------|
| **Node-level** | 对话的每一轮后 | 对话式评估 | 发现内容薄弱环节在哪一轮暴露 |
| **Outcome-level** | Trial 结束后 | 所有类型 | 衡量内容的最终效果 |
| **Log-level** | 分析完整日志 | 所有类型 | 发现交互中的系统性问题 |

### 预置评分维度
- **策略对齐度**: 内容是否与原始意图一致
- **受众匹配度**: 内容是否解决目标用户痛点
- **内容质量**: 结构、表达、专业性
- **转化潜力**: 内容是否有说服力
- **传播价值**: 内容是否容易被分享推荐

---

## 四、Diagnoser 诊断器

跨 Trial 分析，发现系统性问题：
- **跨角色诊断**: 不同角色的评价是否一致？矛盾在哪？
- **内容缺陷诊断**: 多个消费者/角色都指出的问题是什么？
- **改进优先级**: 哪些问题最值得先修复？

---

## 五、数据模型（已更新为 V2 主链路）

```python
EvalTaskV2:
  project_id
  name
  description
  status
  latest_batch_id
  latest_scores
  latest_overall

EvalTrialConfigV2:
  task_id
  form_type           # assessment/review/experience/scenario
  target_block_ids[]
  grader_ids[]
  repeat_count
  probe
  form_config

EvalTrialResultV2:
  task_id
  trial_config_id
  batch_id
  repeat_index
  process
  grader_results
  dimension_scores
  overall_score
  llm_calls
```

---

## 六、集成为 ContentBlock

评估结果是 ContentBlock，完全融入树形结构：

```
项目
├── [其他阶段...]
└── 综合评估 (phase, special_handler=eval_container)
    ├── 教练评审 (field, special_handler=eval_coach)
    ├── 编辑评审 (field, special_handler=eval_editor)
    ├── 领域专家评审 (field, special_handler=eval_expert)
    ├── 消费者体验 (field, special_handler=eval_consumer)
    ├── 内容销售测试 (field, special_handler=eval_seller)
    └── 综合诊断 (field, special_handler=eval_diagnoser)
```

### 作为字段模板可被引用
`FieldTemplate` "综合评估模板" 包含以上6个字段，带有：
- 各角色的 `ai_prompt`
- 内部依赖关系（综合诊断依赖前5项）
- `special_handler` 标识

---

## 七、内容销售模拟详细设计

### 角色设定
- **Sales Rep**: 深入了解内容的销售顾问，主动推介
- **Consumer**: 来自消费者调研的 Persona，真实反应

### 对话流程
1. **销售开场** (1轮): 分析 persona 背景，选择切入点
2. **需求挖掘** (2-3轮): 提问了解具体需求
3. **价值匹配** (2-3轮): 匹配内容价值点到需求
4. **异议处理** (1-2轮): 回应质疑
5. **关单** (1轮): 消费者做出最终决策

### 评估维度
- 价值传达清晰度
- 需求匹配度
- 异议处理能力
- 最终转化结果

---

## 八、Phase × Role 矩阵

| 阶段 | Coach | Editor | Expert | Consumer | Seller |
|------|-------|--------|--------|----------|--------|
| 设计前 | ✅ 审查意图 | - | ✅ 验证假设 | ✅ 需求验证 | - |
| 设计中 | ✅ 架构审查 | ✅ 结构审查 | - | - | - |
| 设计后 | ✅ 终检 | ✅ 全面审查 | ✅ 专业审查 | ✅ 完整体验 | ✅ 销售测试 |
| 销售时 | - | - | - | ✅ 转化行为 | ✅ 主力测试 |

---

## 九、实施计划

### Phase 1: 核心模型 + 角色引擎
- 新增 `EvalRun`, `EvalTrial` 模型
- 更新 `Simulator` 模型支持 role_type
- 实现 5 个角色的评估逻辑

### Phase 2: 模板 + API
- 创建 "综合评估模板" (FieldTemplate)
- 新增 Eval API 端点
- 数据库迁移

### Phase 3: 前端 + 集成
- Eval 结果面板组件
- special_handler 支持
- 与 ContentBlock 系统整合

### Phase 4: 诊断器
- 跨 Trial 分析
- 改进建议生成
