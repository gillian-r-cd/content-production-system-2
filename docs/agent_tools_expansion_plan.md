# Agent 工具能力扩展方案

> 创建时间：2026-02-04
> 更新时间：2026-02-04（已实现 P0/P1 工具）
> 目标：让 Agent 拥有完整的目录和架构级别操作能力

## ✅ 实现状态

| 工具 | 功能 | 状态 | 测试结果 |
|------|------|------|----------|
| `architecture_reader` | 读取项目架构 | ✅ 已实现 | 通过 |
| `architecture_writer` | 修改项目架构（添加/删除阶段和字段） | ✅ 已实现 | 通过 |
| `outline_generator` | 生成内容大纲 | ✅ 已实现 | 通过 |
| `persona_manager` | 管理人物小传 | ✅ 已实现 | 通过 |
| `skill_manager` | 管理可复用技能 | ✅ 已实现 | 通过 |
| `deep_research` | 深度调研 | ✅ 已有 | - |
| `field_generator` | 生成字段内容 | ✅ 已有 | - |
| `simulator` | 消费者模拟 | ✅ 已有 | - |
| `evaluator` | 项目评估 | ✅ 已有 | - |

## 📋 原始工具盘点

| 工具 | 功能 | 调用阶段 | 状态 |
|------|------|---------|------|
| `architecture_reader` | 读取项目架构（阶段、字段、状态） | 任意 | ✅ 新增 |
| `deep_research` | 深度调研（DuckDuckGo + Jina + LLM） | 消费者调研 | ✅ |
| `field_generator` | 生成字段内容（支持流式、并行） | 内涵/外延生产 | ✅ |
| `simulator` | 消费者模拟（5种交互类型） | 消费者模拟 | ✅ |
| `evaluator` | 项目评估（多维度打分+建议） | 评估 | ✅ |

---

## 🎯 扩展目标

根据 PRD 分析，Agent 需要具备以下核心能力：

### 1. 架构操作（Architecture）
- ✅ 读取架构 → `architecture_reader`
- ⏳ 修改架构：添加/删除/重排阶段、添加/删除/移动字段

### 2. 内容规划（Planning）
- ⏳ 生成大纲：根据意图和调研生成内容大纲
- ⏳ 生成字段建议：推荐适合的字段模板

### 3. 实体管理（Entity Management）
- ⏳ 人物小传管理：创建、编辑、选择 Persona
- ⏳ Simulator 设计：根据内容类型设计评估器
- ⏳ Evaluator 设计：根据项目特点设计评估维度

### 4. 技能与工作流（Skills）
- ⏳ Skill 生成与存储：可复用的提示词模板
- ⏳ 工作流生成：多步骤任务编排

---

## 🛠️ 工具扩展设计

### Tool 1: `architecture_writer` - 架构修改工具

**功能**：让 Agent 能够修改项目结构

```python
# 操作类型
class ArchitectureOperation(Enum):
    ADD_PHASE = "add_phase"       # 添加阶段
    REMOVE_PHASE = "remove_phase" # 删除阶段
    REORDER_PHASES = "reorder"    # 重排阶段
    ADD_FIELD = "add_field"       # 添加字段
    REMOVE_FIELD = "remove_field" # 删除字段
    MOVE_FIELD = "move_field"     # 移动字段
    UPDATE_FIELD = "update_field" # 更新字段属性

# 调用示例
await architecture_writer(
    project_id="xxx",
    operation=ArchitectureOperation.ADD_FIELD,
    params={
        "phase": "produce_inner",
        "name": "课程目标",
        "ai_prompt": "根据意图分析，生成明确的课程目标",
        "depends_on": ["意图分析报告"],
    }
)
```

**典型场景**：
- 用户说"在内涵生产阶段加一个'核心论点'字段"
- Agent 调用 `architecture_writer(operation=ADD_FIELD, ...)`

---

### Tool 2: `outline_generator` - 大纲生成工具

**功能**：根据意图和调研结果生成内容大纲

```python
@dataclass
class OutlineNode:
    name: str                    # 节点名称
    description: str             # 描述
    field_type: str              # 字段类型
    ai_prompt: str               # AI 生成提示词
    depends_on: List[str]        # 依赖字段
    children: List["OutlineNode"] # 子节点（支持嵌套）
    
@dataclass  
class ContentOutline:
    title: str                   # 大纲标题
    summary: str                 # 大纲概述
    nodes: List[OutlineNode]     # 大纲节点
    estimated_tokens: int        # 预估 token 消耗
    
async def generate_outline(
    project_id: str,
    content_type: str,          # 内容类型：课程、文章、视频脚本等
    structure_hint: str = None, # 结构提示（可选）
) -> ContentOutline:
    """
    根据项目上下文生成内容大纲
    
    调用时机：内涵设计阶段
    输入：意图分析结果 + 消费者调研结果
    输出：结构化大纲（可直接转换为字段）
    """
```

**典型场景**：
- 用户说"帮我设计一下这个课程的大纲"
- Agent 调用 `outline_generator`，生成包含章节、小节的嵌套大纲
- 用户确认后，Agent 调用 `architecture_writer` 将大纲转为字段

---

### Tool 3: `persona_manager` - 人物小传管理工具

**功能**：创建、编辑、存储消费者人物小传

```python
class PersonaOperation(Enum):
    CREATE = "create"          # 创建新人物
    UPDATE = "update"          # 更新人物
    SELECT = "select"          # 选中用于模拟
    DESELECT = "deselect"      # 取消选中
    GENERATE = "generate"      # 根据画像生成

@dataclass
class Persona:
    id: str
    name: str
    basic_info: Dict[str, Any]  # 年龄、职业、收入等
    background: str              # 背景故事
    pain_points: List[str]       # 核心痛点
    behaviors: List[str]         # 行为特征
    selected: bool               # 是否用于模拟
    
async def manage_persona(
    project_id: str,
    operation: PersonaOperation,
    persona_data: Dict[str, Any],
) -> Persona:
    """
    管理消费者人物小传
    
    调用时机：消费者调研阶段、模拟前
    """
```

**典型场景**：
- 用户说"再生成一个技术背景的用户画像"
- Agent 调用 `persona_manager(operation=GENERATE, persona_data={...})`
- 用户说"把李明选上作为测试用户"
- Agent 调用 `persona_manager(operation=SELECT, persona_data={"name": "李明"})`

---

### Tool 4: `simulator_designer` - 模拟器设计工具

**功能**：根据内容类型设计合适的模拟器

```python
class SimulationType(Enum):
    READING = "reading"           # 阅读式（文章、文档）
    DIALOGUE = "dialogue"         # 对话式（Chatbot、客服）
    DECISION = "decision"         # 决策式（选择题、场景判断）
    EXPLORATION = "exploration"   # 探索式（课程、学习）
    EXPERIENCE = "experience"     # 体验式（产品、服务）

@dataclass
class SimulatorConfig:
    name: str
    simulation_type: SimulationType
    prompt_template: str          # 模拟提示词
    evaluation_dimensions: List[str]  # 评估维度
    interaction_count: int        # 交互轮数
    success_criteria: Dict        # 成功标准
    
async def design_simulator(
    project_id: str,
    content_type: str,           # 被模拟的内容类型
    target_behavior: str,        # 目标用户行为
) -> SimulatorConfig:
    """
    根据内容和目标设计模拟器
    
    调用时机：消费者模拟阶段前
    输入：内容类型 + 期望用户行为
    输出：模拟器配置（可保存为模板）
    """
```

**典型场景**：
- 用户说"我需要一个可以测试学习效果的模拟器"
- Agent 分析内容类型，调用 `simulator_designer` 生成配置
- 用户确认后，Agent 将配置保存并在模拟阶段使用

---

### Tool 5: `evaluator_designer` - 评估器设计工具

**功能**：根据项目特点设计评估维度和标准

```python
@dataclass
class EvaluationDimension:
    name: str                    # 维度名称
    description: str             # 维度描述
    weight: float                # 权重（0-1）
    metrics: List[Dict]          # 具体指标
    grader_prompt: str           # 评分提示词

@dataclass
class EvaluatorConfig:
    name: str
    dimensions: List[EvaluationDimension]
    overall_prompt: str          # 总体评价提示词
    suggestion_prompt: str       # 建议生成提示词
    
async def design_evaluator(
    project_id: str,
    evaluation_focus: str,       # 评估重点
) -> EvaluatorConfig:
    """
    根据项目设计评估器
    
    调用时机：评估阶段前
    """
```

---

### Tool 6: `skill_manager` - 技能管理工具

**功能**：创建、存储、复用提示词模板

```python
@dataclass
class Skill:
    id: str
    name: str                    # 技能名称
    description: str             # 描述
    category: str                # 类别：生成/分析/评估/其他
    prompt_template: str         # 提示词模板（支持变量）
    input_schema: Dict           # 输入参数定义
    output_format: str           # 输出格式要求
    examples: List[Dict]         # 使用示例
    
async def manage_skill(
    operation: str,              # create/update/delete/list/apply
    skill_data: Dict = None,
    apply_params: Dict = None,   # 应用技能时的参数
) -> Union[Skill, List[Skill], str]:
    """
    管理和应用技能
    
    调用时机：任意（用户请求或 Agent 自主调用）
    """
```

**典型场景**：
- Agent 发现某个生成模式很有效，调用 `skill_manager(operation="create", ...)` 保存为技能
- 用户说"用我之前保存的'专业文案'技能来写这段"
- Agent 调用 `skill_manager(operation="apply", apply_params={...})`

---

## 🔄 工具调用流程

### 场景 1：用户说"帮我设计课程大纲"

```
用户输入: "帮我设计课程大纲"
    ↓
route_intent: 识别为 "generate" + 架构相关
    ↓
架构感知: 读取项目当前阶段和已有字段
    ↓
outline_generator: 生成大纲建议
    ↓
返回用户确认
    ↓
用户确认后 → architecture_writer: 将大纲转为字段
```

### 场景 2：用户说"删掉意图分析阶段"

```
用户输入: "删掉意图分析阶段"
    ↓
route_intent: 识别为 "modify" + 架构操作
    ↓
architecture_writer(operation=REMOVE_PHASE, params={"phase": "intent"})
    ↓
更新 project.phase_order
    ↓
返回确认信息
```

### 场景 3：用户说"设计一个测试学习效果的模拟器"

```
用户输入: "设计一个测试学习效果的模拟器"
    ↓
route_intent: 识别为 "generate" + 模拟器相关
    ↓
simulator_designer: 根据项目内容类型设计
    ↓
返回配置供用户确认
    ↓
用户确认后 → 保存到 Simulator 表
```

---

## 📐 实现优先级

| 优先级 | 工具 | 工作量 | 价值 |
|--------|------|--------|------|
| P0 | `architecture_writer` | 中 | 高（核心能力） |
| P0 | `outline_generator` | 中 | 高（设计阶段关键） |
| P1 | `persona_manager` | 低 | 中（调研阶段增强） |
| P1 | `skill_manager` | 中 | 中（可复用性） |
| P2 | `simulator_designer` | 中 | 中（模拟阶段增强） |
| P2 | `evaluator_designer` | 中 | 中（评估阶段增强） |

---

## 🎛️ 意图路由扩展

需要在 `route_intent` 中增加对工具调用的识别：

```python
# 新增的工具调用意图关键词
TOOL_KEYWORDS = {
    "architecture_write": ["添加阶段", "删除阶段", "添加字段", "删除字段", "移动"],
    "outline_generate": ["大纲", "结构", "框架", "规划内容"],
    "persona_manage": ["人物", "画像", "用户角色", "消费者"],
    "simulator_design": ["模拟器", "测试方式", "模拟方案"],
    "evaluator_design": ["评估", "打分标准", "评价维度"],
    "skill_manage": ["技能", "保存模板", "复用"],
}
```

---

## 💾 数据模型扩展

### 新增表：`skills`

```python
class Skill(BaseModel):
    __tablename__ = "skills"
    
    name: str                    # 技能名称
    description: str             # 描述
    category: str                # 类别
    prompt_template: str         # 提示词模板
    input_schema: dict           # 输入定义（JSON）
    output_format: str           # 输出格式
    examples: list               # 示例（JSON）
    is_system: bool = False      # 是否系统预置
    usage_count: int = 0         # 使用次数
```

### 新增表：`content_outlines`

```python
class ContentOutline(BaseModel):
    __tablename__ = "content_outlines"
    
    project_id: str              # 所属项目
    title: str                   # 大纲标题
    summary: str                 # 大纲概述
    nodes: list                  # 节点结构（JSON）
    status: str                  # pending/confirmed/applied
    applied_at: datetime         # 应用时间
```

---

## 🧪 测试计划

### 测试用例 1：大纲生成
| 输入 | 预期输出 |
|------|---------|
| "帮我设计这个培训课程的大纲" | 返回包含章节、小节的结构化大纲 |
| "大纲太长了，简化一下" | 返回精简版大纲 |
| "确认这个大纲" | 将大纲转为字段并保存 |

### 测试用例 2：架构修改
| 输入 | 预期输出 |
|------|---------|
| "在内涵生产里加个'核心论点'字段" | 创建字段并返回确认 |
| "删掉消费者模拟阶段" | 删除阶段并更新 phase_order |
| "把外延设计移到内涵生产前面" | 重排阶段顺序 |

### 测试用例 3：人物管理
| 输入 | 预期输出 |
|------|---------|
| "再生成一个程序员背景的用户" | 创建新 Persona |
| "把王磊作为测试用户" | 设置 selected=True |
| "修改李明的痛点" | 更新 Persona 数据 |

---

## ⏰ 实现计划

| 阶段 | 任务 | 时间 |
|------|------|------|
| Phase 1 | `architecture_writer` + 路由扩展 | 2h |
| Phase 2 | `outline_generator` + 前端展示 | 2h |
| Phase 3 | `persona_manager` + 前端交互 | 1.5h |
| Phase 4 | `skill_manager` + 技能存储 | 2h |
| Phase 5 | `simulator_designer` + `evaluator_designer` | 2h |
| Phase 6 | 集成测试 + 优化 | 1.5h |

**总计：约 11 小时**

---

## 📝 结论

本方案的核心思路是：

1. **工具化**：将各种操作抽象为独立工具，Agent 根据意图调用
2. **结构化**：所有操作的输入输出都是结构化数据，便于存储和复用
3. **可组合**：工具之间可以组合使用，形成复杂工作流
4. **可扩展**：新工具可以随时添加，不影响现有逻辑

这样设计的好处：
- Agent 能力边界清晰
- 每个工具职责单一
- 用户可以通过自然语言触发任意操作
- 操作结果可追溯、可回滚
