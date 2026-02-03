# Agent 架构设计
# 创建时间: 20260202
# 更新时间: 20260203
# 功能: 定义LangGraph Agent的状态机、节点、边、工具

## Agent 核心架构

使用 LangGraph 构建状态图，实现真正的Agent架构（非if/else）。

### 实现状态 ✅

- [x] 意图路由器
- [x] 阶段节点 (8个)
- [x] 工具节点 (generate_field, read_field, update_field)
- [x] 自主权检查点
- [x] Golden Context 注入
- [x] 意图分析阶段两种模式 (questioning/producing)

## 状态定义

```python
class ContentProductionState(TypedDict):
    # 项目标识
    project_id: str
    
    # 当前阶段: intent | research | design_inner | produce_inner | 
    #          design_outer | produce_outer | simulate | evaluate
    current_phase: str
    
    # Golden Context (自动注入每次LLM调用)
    golden_context: dict  # {creator_profile, intent, consumer_personas}
    
    # 已生成的字段
    fields: dict[str, FieldValue]
    
    # 对话历史
    messages: list[BaseMessage]
    
    # Agent自主权设置
    autonomy_settings: dict[str, bool]  # {phase: need_human_confirm}
    
    # 是否等待人工确认
    waiting_for_human: bool
```

## 流程图 (Mermaid)

```mermaid
graph TB
    subgraph "用户交互层"
        UI[右栏对话框]
        EDIT[中栏编辑器]
    end
    
    subgraph "LangGraph Agent"
        ROUTER{意图路由器}
        
        subgraph "流程节点"
            INTENT[意图分析节点]
            RESEARCH[消费者调研节点]
            DESIGN_I[内涵设计节点]
            PRODUCE_I[内涵生产节点]
            DESIGN_E[外延设计节点]
            PRODUCE_E[外延生产节点]
            SIMULATE[消费者模拟节点]
            EVALUATE[评估节点]
        end
        
        subgraph "工具节点"
            DEEP[DeepResearch Tool]
            SEARCH[WebSearch Tool]
            GEN[生成字段 Tool]
            READ[读取字段 Tool]
            UPDATE[更新字段 Tool]
        end
        
        CHECKPOINT{自主权检查点}
    end
    
    subgraph "状态管理"
        STATE[(ContentProductionState)]
        GOLDEN[Golden Context注入]
    end
    
    UI -->|用户消息| ROUTER
    EDIT -->|@引用/编辑| READ
    
    ROUTER -->|推进流程| INTENT
    ROUTER -->|调研请求| RESEARCH
    ROUTER -->|生成内容| GEN
    ROUTER -->|自由对话| CHAT[普通对话]
    
    INTENT --> CHECKPOINT
    RESEARCH --> DEEP
    RESEARCH --> CHECKPOINT
    
    DESIGN_I --> CHECKPOINT
    PRODUCE_I --> GEN
    PRODUCE_I --> CHECKPOINT
    
    DESIGN_E --> CHECKPOINT
    PRODUCE_E --> GEN
    PRODUCE_E --> CHECKPOINT
    
    SIMULATE --> CHECKPOINT
    EVALUATE --> CHECKPOINT
    
    CHECKPOINT -->|需要人工确认| UI
    CHECKPOINT -->|自主模式| NEXT[下一节点]
    
    GOLDEN --> INTENT
    GOLDEN --> RESEARCH
    GOLDEN --> DESIGN_I
    GOLDEN --> PRODUCE_I
    GOLDEN --> DESIGN_E
    GOLDEN --> PRODUCE_E
    
    STATE --> ROUTER
    GEN --> STATE
    UPDATE --> STATE
```

## 意图分析阶段（特殊处理）

意图分析阶段有两种交互模式：

### 1. 引导提问模式 (questioning)
- **触发条件**: 用户输入不包含生成触发词
- **AI行为**: 根据对话历史，继续提问澄清意图
- **输出位置**: 只在右侧对话区显示
- **是否保存**: 不保存为字段

### 2. 产出生成模式 (producing)
- **触发条件**: 用户输入包含 "生成"、"可以了"、"就这些"、"继续" 等触发词
- **AI行为**: 根据用户的所有回答，生成结构化的意图分析报告
- **输出位置**: 保存为字段，显示在中间内容栏
- **是否保存**: 保存为 ProjectField

**其他阶段**: 直接生成，自动保存为字段（根据字段依赖关系）

---

## 意图路由器

每次用户消息先经过路由器，使用LLM判断意图类型：

| 意图类型 | 触发条件 | 路由目标 |
|----------|----------|----------|
| `advance_phase` | "继续"、"下一步"、确认当前阶段 | **下一阶段节点** |
| `research` | 调研相关请求 | DeepResearch Tool |
| `generate` | 生成内容请求 | generate_field Tool |
| `modify` | 修改已有内容 | update_field Tool |
| `query` | 查询已有内容 | read_field Tool |
| `chat` | 自由对话、提问 | 普通对话节点 |

## 自主权检查点

每个阶段节点执行完后检查：

```python
def should_wait_for_human(state: ContentProductionState) -> str:
    current_phase = state["current_phase"]
    autonomy = state["autonomy_settings"]
    
    if autonomy.get(current_phase, True):  # 默认需要确认
        return "wait_human"
    else:
        return "continue"
```

## 预置工具 (Tools)

| Tool名称 | 功能 | 参数 |
|----------|------|------|
| `deep_research` | 深度调研 | query, max_sources |
| `web_search` | 快速搜索 | query |
| `generate_field` | 生成字段 | field_name, field_schema, context |
| `evaluate_content` | 评估内容 | content, criteria |
| `simulate_consumer` | 模拟消费者 | persona, content, interaction_type |
| `read_field` | 读取字段 | field_path |
| `update_field` | 更新字段 | field_path, new_content |
| `export_content` | 导出内容 | format, fields |

## DeepResearch 实现

零额外成本方案：DuckDuckGo + Jina Reader + OpenAI

```python
async def deep_research(query: str, max_sources: int = 10) -> ResearchReport:
    # 1. 规划搜索查询 (OpenAI)
    search_queries = await plan_queries(query)
    
    # 2. 并行搜索 (DuckDuckGo, 免费)
    search_results = await asyncio.gather(*[
        search_ddg(q) for q in search_queries
    ])
    
    # 3. 读取网页内容 (Jina Reader, 免费)
    contents = await asyncio.gather(*[
        read_with_jina(url) for url in top_urls
    ])
    
    # 4. 综合分析 (OpenAI)
    report = await synthesize(contents, query)
    
    return report
```

## Golden Context 注入

每次LLM调用前自动拼接：

```python
def build_golden_context(state: ContentProductionState) -> str:
    gc = state["golden_context"]
    return f"""
## 创作者特质
{gc.get("creator_profile", "")}

## 项目意图
{gc.get("intent", "")}

## 目标用户画像
{gc.get("consumer_personas", "")}
"""
```

