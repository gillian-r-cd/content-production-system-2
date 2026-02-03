# 数据模型设计
# 创建时间: 20260202
# 功能: 定义SQLAlchemy数据模型、字段关系、版本管理

## ER图

```
┌─────────────────┐       ┌─────────────────────┐
│ CreatorProfile  │       │      Project        │
├─────────────────┤       ├─────────────────────┤
│ id (PK)         │       │ id (PK)             │
│ name            │◄──────│ creator_profile_id  │
│ traits (JSON)   │       │ name                │
│ created_at      │       │ version             │
└─────────────────┘       │ version_note        │
                          │ current_phase       │
┌─────────────────┐       │ phase_order (JSON)  │
│  FieldTemplate  │       │ agent_autonomy (JSON)│
├─────────────────┤       │ created_at          │
│ id (PK)         │       │ updated_at          │
│ name            │       └─────────┬───────────┘
│ fields (JSON)   │                 │
│ created_at      │       ┌─────────▼─────────┐
└─────────────────┘       │   ProjectField    │
                          ├───────────────────┤
┌─────────────────┐       │ id (PK)           │
│    Channel      │       │ project_id (FK)   │
├─────────────────┤       │ template_id (FK)  │
│ id (PK)         │       │ phase             │
│ name            │       │ name              │
│ description     │       │ content (TEXT)    │
│ prompt_template │       │ status            │
│ created_at      │       │ ai_prompt         │
└─────────────────┘       │ pre_questions(JSON)│
                          │ dependencies (JSON)│
┌─────────────────┐       │ created_at        │
│   Simulator     │       └───────────────────┘
├─────────────────┤
│ id (PK)         │       ┌───────────────────┐
│ name            │       │ SimulationRecord  │
│ interaction_type│       ├───────────────────┤
│ prompt_template │       │ id (PK)           │
│ created_at      │       │ project_id (FK)   │
└─────────────────┘       │ simulator_id (FK) │
                          │ persona (JSON)    │
┌─────────────────┐       │ interaction_log   │
│ GenerationLog   │       │ feedback (JSON)   │
├─────────────────┤       │ created_at        │
│ id (PK)         │       └───────────────────┘
│ project_id (FK) │
│ field_id (FK)   │       ┌───────────────────┐
│ phase           │       │ EvaluationReport  │
│ prompt_input    │       ├───────────────────┤
│ prompt_output   │       │ id (PK)           │
│ model           │       │ project_id (FK)   │
│ tokens_in       │       │ template (JSON)   │
│ tokens_out      │       │ scores (JSON)     │
│ duration_ms     │       │ suggestions (JSON)│
│ cost            │       │ created_at        │
│ status          │       └───────────────────┘
│ error_message   │
│ created_at      │       ┌───────────────────┐
└─────────────────┘       │EvaluationTemplate │
                          ├───────────────────┤
                          │ id (PK)           │
                          │ name              │
                          │ sections (JSON)   │
                          │ created_at        │
                          └───────────────────┘
```

## 模型定义

### CreatorProfile (创作者特质)

```python
class CreatorProfile(Base):
    __tablename__ = "creator_profiles"
    
    id: str  # UUID
    name: str  # 名称
    traits: dict  # JSON: 特质描述，自由格式
    created_at: datetime
    updated_at: datetime
```

### Project (项目)

```python
class Project(Base):
    __tablename__ = "projects"
    
    id: str  # UUID
    creator_profile_id: str  # FK
    name: str
    version: int  # 版本号，从1开始
    version_note: str  # 版本说明
    current_phase: str  # 当前阶段
    phase_order: list[str]  # JSON: 阶段顺序（可拖拽调整）
    agent_autonomy: dict[str, bool]  # JSON: 每阶段是否需人工确认
    golden_context: dict  # JSON: 缓存的Golden Context
    created_at: datetime
    updated_at: datetime
```

### FieldTemplate (字段模板 - 全局共享)

```python
class FieldTemplate(Base):
    __tablename__ = "field_templates"
    
    id: str
    name: str  # 模板名称
    description: str
    fields: list[FieldSchema]  # JSON: 字段定义列表
    created_at: datetime
    
# FieldSchema 结构
FieldSchema = {
    "name": str,           # 字段名
    "type": str,           # text | richtext | list | structured
    "ai_prompt": str,      # AI生成提示词
    "pre_questions": list, # 生成前提问
    "depends_on": list,    # 依赖的字段名
}
```

### ProjectField (项目字段 - 实际内容)

```python
class ProjectField(Base):
    __tablename__ = "project_fields"
    
    id: str
    project_id: str  # FK
    template_id: str | None  # FK, 可选
    phase: str  # intent | research | inner | outer
    name: str
    content: str  # 实际内容
    status: str  # pending | generating | completed | failed
    ai_prompt: str  # 可覆盖模板的提示词
    pre_questions: dict  # JSON: 用户回答的提问
    dependencies: dict  # JSON: {"depends_on": [...], "dependency_type": "all"|"any"}
    generation_log_id: str | None  # 最近一次生成日志
    created_at: datetime
    updated_at: datetime
```

### 字段依赖解析

```python
def resolve_field_dependencies(fields: list[ProjectField]) -> list[list[str]]:
    """
    拓扑排序 + 并行分组
    返回: [["A"], ["B", "C"], ["D"]] 表示A先执行，BC并行，最后D
    """
    # 构建依赖图
    graph = {f.id: set(f.dependencies.get("depends_on", [])) for f in fields}
    
    # Kahn算法拓扑排序
    result = []
    while graph:
        # 找出没有依赖的节点（可并行执行）
        ready = [node for node, deps in graph.items() if not deps]
        if not ready:
            raise ValueError("检测到循环依赖")
        result.append(ready)
        # 移除已处理节点
        for node in ready:
            del graph[node]
        for deps in graph.values():
            deps -= set(ready)
    
    return result
```

### Simulator (模拟器)

```python
class Simulator(Base):
    __tablename__ = "simulators"
    
    id: str
    name: str
    interaction_type: str  # dialogue | reading | decision | exploration | experience
    prompt_template: str  # 模拟器提示词模板
    evaluation_dimensions: list  # JSON: 评估维度
    created_at: datetime
```

### 预置交互类型

| 类型 | 适用场景 | 交互方式 | 评估维度 |
|------|----------|----------|----------|
| dialogue | 对话式Chatbot | 多轮对话 | 响应相关性、解决率、体验感 |
| reading | 文章、课程 | 阅读后反馈 | 理解难度、价值感知、行动意愿 |
| decision | 销售页 | 决策模拟 | 转化意愿、顾虑点、信任度 |
| exploration | 产品文档 | 带目的探索 | 找到答案效率、满意度 |
| experience | 交互产品 | 任务完成 | 易用性、效率、愉悦度 |

### EvaluationTemplate (评估模板)

```python
class EvaluationTemplate(Base):
    __tablename__ = "evaluation_templates"
    
    id: str
    name: str
    sections: list[EvaluationSection]  # JSON
    created_at: datetime

# EvaluationSection 结构
EvaluationSection = {
    "id": str,
    "name": str,           # 如 "意图对齐度"
    "grader_prompt": str,  # 评分提示词
    "weight": float,       # 权重
    "metrics": [           # 评估指标
        {"name": str, "type": "score_1_10" | "text_list" | "boolean"}
    ],
    "sub_sections": list,  # 可嵌套
}
```

### GenerationLog (生成日志)

```python
class GenerationLog(Base):
    __tablename__ = "generation_logs"
    
    id: str
    project_id: str
    field_id: str | None
    phase: str
    prompt_input: str  # 完整输入
    prompt_output: str  # 完整输出
    model: str  # gpt-4o 等
    tokens_in: int
    tokens_out: int
    duration_ms: int
    cost: float  # 美元
    status: str  # success | failed
    error_message: str | None
    created_at: datetime
```

## 版本管理

项目级快照策略：

```python
def create_new_version(project_id: str, version_note: str) -> Project:
    """
    创建项目新版本：复制项目和所有字段
    """
    old_project = get_project(project_id)
    old_fields = get_project_fields(project_id)
    
    # 创建新项目记录
    new_project = Project(
        id=generate_uuid(),
        creator_profile_id=old_project.creator_profile_id,
        name=old_project.name,
        version=old_project.version + 1,
        version_note=version_note,
        # 复制其他字段...
    )
    
    # 复制所有字段
    for field in old_fields:
        new_field = ProjectField(
            id=generate_uuid(),
            project_id=new_project.id,
            # 复制其他字段...
        )
    
    return new_project
```

