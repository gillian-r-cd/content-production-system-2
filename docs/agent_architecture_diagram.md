# Agent 架构图

> 更新时间: 2026-02-04
> 基于 LangGraph 实现的内容生产 Agent

## 1. 整体架构流程图

```mermaid
flowchart TB
    subgraph Entry["入口"]
        START([用户输入])
    end

    subgraph Router["路由层"]
        ROUTER[["route_intent<br/>LLM 意图识别"]]
    end

    subgraph Tools["工具层"]
        TOOL_ARCH["tool_node<br/>架构操作"]
        TOOL_OUTLINE["tool_node<br/>大纲生成"]
        TOOL_PERSONA["tool_node<br/>人物管理"]
        TOOL_SKILL["tool_node<br/>技能管理"]
    end

    subgraph Phases["阶段节点层"]
        INTENT["intent_analysis_node<br/>意图分析（3轮问答）"]
        RESEARCH["research_node<br/>消费者调研"]
        DESIGN_I["design_inner_node<br/>内涵设计"]
        PRODUCE_I["produce_inner_node<br/>内涵生产"]
        DESIGN_O["design_outer_node<br/>外延设计"]
        PRODUCE_O["produce_outer_node<br/>外延生产"]
        SIMULATE["simulate_node<br/>消费者模拟"]
        EVALUATE["evaluate_node<br/>项目评估"]
    end

    subgraph Reference["引用处理层"]
        MODIFY["modify_node<br/>修改字段内容"]
        QUERY["query_node<br/>查询字段信息"]
    end

    subgraph Dialogue["对话层"]
        CHAT["chat_node<br/>自由对话"]
    end

    subgraph Output["输出"]
        END_NODE([返回结果])
    end

    START --> ROUTER

    ROUTER -->|"tool_architecture"| TOOL_ARCH
    ROUTER -->|"tool_outline"| TOOL_OUTLINE
    ROUTER -->|"tool_persona"| TOOL_PERSONA
    ROUTER -->|"tool_skill"| TOOL_SKILL

    ROUTER -->|"phase_intent"| INTENT
    ROUTER -->|"phase_research"| RESEARCH
    ROUTER -->|"phase_design_inner"| DESIGN_I
    ROUTER -->|"phase_produce_inner"| PRODUCE_I
    ROUTER -->|"phase_design_outer"| DESIGN_O
    ROUTER -->|"phase_produce_outer"| PRODUCE_O
    ROUTER -->|"phase_simulate"| SIMULATE
    ROUTER -->|"phase_evaluate"| EVALUATE

    ROUTER -->|"modify + @引用"| MODIFY
    ROUTER -->|"query + @引用"| QUERY

    ROUTER -->|"chat"| CHAT

    TOOL_ARCH --> END_NODE
    TOOL_OUTLINE --> END_NODE
    TOOL_PERSONA --> END_NODE
    TOOL_SKILL --> END_NODE

    INTENT -->|"is_producing=false"| END_NODE
    INTENT -->|"is_producing=true"| END_NODE
    
    RESEARCH --> END_NODE
    DESIGN_I --> END_NODE
    PRODUCE_I --> END_NODE
    DESIGN_O --> END_NODE
    PRODUCE_O --> END_NODE
    SIMULATE --> END_NODE
    EVALUATE --> END_NODE

    MODIFY --> END_NODE
    QUERY --> END_NODE
    CHAT --> END_NODE

    style ROUTER fill:#f9f,stroke:#333,stroke-width:2px
    style TOOL_ARCH fill:#bbf,stroke:#333
    style TOOL_OUTLINE fill:#bbf,stroke:#333
    style TOOL_PERSONA fill:#bbf,stroke:#333
    style TOOL_SKILL fill:#bbf,stroke:#333
    style INTENT fill:#bfb,stroke:#333
    style RESEARCH fill:#bfb,stroke:#333
```

## 2. 意图路由详细流程

```mermaid
flowchart TB
    INPUT[用户输入]
    
    subgraph Rule1["规则 1: @ 引用检测"]
        CHECK_REF{有 @ 引用?}
        CHECK_MODIFY{包含修改关键词?}
        CHECK_QUERY{包含查询关键词?}
        ROUTE_MODIFY[route_target = modify]
        ROUTE_QUERY[route_target = query]
    end

    subgraph Rule2["规则 2: 阶段推进"]
        CHECK_ADVANCE{触发词 + 阶段已完成?}
        ROUTE_ADVANCE[route_target = advance_phase]
    end

    subgraph Rule3["规则 3: 阶段开始"]
        CHECK_START{开始触发词 + 阶段未完成?}
        ROUTE_PHASE[route_target = phase_current]
    end

    subgraph Rule4["规则 4: intent 阶段"]
        CHECK_INTENT{当前是 intent 且未完成?}
        ROUTE_INTENT[route_target = phase_current]
    end

    subgraph Rule5["规则 5: LLM 意图分类"]
        LLM_CLASSIFY["LLM 分析意图<br/>返回 JSON"]
        NORMALIZE["意图标准化映射<br/>architecture → tool_architecture"]
        
        subgraph IntentTypes["意图类型"]
            T_ARCH[tool_architecture]
            T_OUT[tool_outline]
            T_PER[tool_persona]
            T_SKI[tool_skill]
            T_MOD[modify]
            T_QUE[query]
            T_GEN[generate]
            T_RES[research]
            T_SIM[simulate]
            T_EVA[evaluate]
            T_ADV[advance_phase]
            T_PHA[phase_action]
            T_CHA[chat]
        end
    end

    INPUT --> CHECK_REF
    CHECK_REF -->|Yes| CHECK_MODIFY
    CHECK_REF -->|No| CHECK_ADVANCE
    
    CHECK_MODIFY -->|Yes| ROUTE_MODIFY
    CHECK_MODIFY -->|No| CHECK_QUERY
    CHECK_QUERY -->|Yes| ROUTE_QUERY
    CHECK_QUERY -->|No| LLM_CLASSIFY
    
    CHECK_ADVANCE -->|Yes| ROUTE_ADVANCE
    CHECK_ADVANCE -->|No| CHECK_START
    
    CHECK_START -->|Yes| ROUTE_PHASE
    CHECK_START -->|No| CHECK_INTENT
    
    CHECK_INTENT -->|Yes| ROUTE_INTENT
    CHECK_INTENT -->|No| LLM_CLASSIFY
    
    LLM_CLASSIFY --> NORMALIZE
    NORMALIZE --> IntentTypes
```

## 3. 工具节点详细流程

```mermaid
flowchart TB
    TOOL_NODE[tool_node]
    
    subgraph Dispatch["工具分发"]
        CHECK_TYPE{parsed_intent_type?}
    end

    subgraph ArchTool["架构工具"]
        ARCH_LLM["_llm_handle_architecture<br/>LLM 解析操作"]
        ARCH_PARSE["解析 JSON 结果"]
        ARCH_ADD_P["add_phase()"]
        ARCH_DEL_P["remove_phase()"]
        ARCH_ADD_F["add_field()"]
        ARCH_DEL_F["remove_field()"]
        ARCH_MOV_F["move_field()"]
    end

    subgraph OutlineTool["大纲工具"]
        OUT_LLM["_llm_handle_outline"]
        OUT_GEN["generate_outline()"]
        OUT_APPLY["apply_outline_to_project()"]
    end

    subgraph PersonaTool["人物工具"]
        PER_LLM["_llm_handle_persona<br/>LLM 解析操作"]
        PER_LIST["list_personas()"]
        PER_GEN["generate_persona()"]
        PER_SEL["select_persona()"]
        PER_DEL["delete_persona()"]
    end

    subgraph SkillTool["技能工具"]
        SKI_LLM["_llm_handle_skill<br/>LLM 解析操作"]
        SKI_LIST["list_skills()"]
        SKI_APPLY["apply_skill()"]
        SKI_GET["get_skill()"]
    end

    TOOL_NODE --> CHECK_TYPE
    
    CHECK_TYPE -->|"tool_architecture"| ARCH_LLM
    ARCH_LLM --> ARCH_PARSE
    ARCH_PARSE -->|"add_phase"| ARCH_ADD_P
    ARCH_PARSE -->|"remove_phase"| ARCH_DEL_P
    ARCH_PARSE -->|"add_field"| ARCH_ADD_F
    ARCH_PARSE -->|"remove_field"| ARCH_DEL_F
    ARCH_PARSE -->|"move_field"| ARCH_MOV_F

    CHECK_TYPE -->|"tool_outline"| OUT_LLM
    OUT_LLM --> OUT_GEN
    OUT_GEN -.->|"用户确认后"| OUT_APPLY

    CHECK_TYPE -->|"tool_persona"| PER_LLM
    PER_LLM -->|"list"| PER_LIST
    PER_LLM -->|"generate"| PER_GEN
    PER_LLM -->|"select"| PER_SEL
    PER_LLM -->|"delete"| PER_DEL

    CHECK_TYPE -->|"tool_skill"| SKI_LLM
    SKI_LLM -->|"list"| SKI_LIST
    SKI_LLM -->|"apply"| SKI_APPLY
    SKI_LLM -->|"get"| SKI_GET
```

## 4. 意图分析节点详细流程

```mermaid
flowchart TB
    INTENT_NODE[intent_analysis_node]
    
    subgraph CountQuestions["统计当前轮次问题数"]
        COUNT["遍历历史消息"]
        STOP1{"遇到确认消息?"}
        STOP2{"遇到意图分析结果?"}
        FOUND_Q{"发现【问题 X/3】?"}
        INCREMENT["question_count++"]
    end

    subgraph Decide["决定模式"]
        CHECK_COUNT{question_count >= 3?}
        PRODUCE_MODE["产出模式"]
        QUESTION_MODE["提问模式"]
    end

    subgraph ProduceMode["产出模式"]
        GEN_INTENT["生成意图分析 JSON"]
        UPDATE_GC["更新 golden_context.intent"]
        RETURN_CONFIRM["返回确认消息"]
    end

    subgraph QuestionMode["提问模式"]
        Q1{"问题 1?"}
        Q2{"问题 2?"}
        Q3{"问题 3?"}
        
        FIXED_Q1["固定问题：<br/>你想做什么内容？"]
        AI_Q2["AI 生成问题：<br/>给谁看？痛点？"]
        AI_Q3["AI 生成问题：<br/>期望读者行动？"]
    end

    INTENT_NODE --> COUNT
    COUNT --> STOP1
    STOP1 -->|Yes| CHECK_COUNT
    STOP1 -->|No| STOP2
    STOP2 -->|Yes| CHECK_COUNT
    STOP2 -->|No| FOUND_Q
    FOUND_Q -->|Yes| INCREMENT
    FOUND_Q -->|No| COUNT
    INCREMENT --> COUNT

    CHECK_COUNT -->|Yes| PRODUCE_MODE
    CHECK_COUNT -->|No| QUESTION_MODE

    PRODUCE_MODE --> GEN_INTENT
    GEN_INTENT --> UPDATE_GC
    UPDATE_GC --> RETURN_CONFIRM

    QUESTION_MODE --> Q1
    Q1 -->|Yes| FIXED_Q1
    Q1 -->|No| Q2
    Q2 -->|Yes| AI_Q2
    Q2 -->|No| Q3
    Q3 -->|Yes| AI_Q3
```

## 5. 状态数据流

```mermaid
flowchart LR
    subgraph State["ContentProductionState"]
        direction TB
        S1["project_id"]
        S2["user_input"]
        S3["current_phase"]
        S4["phase_status"]
        S5["phase_order"]
        S6["golden_context"]
        S7["messages (chat_history)"]
        S8["references (@ 引用)"]
        S9["referenced_contents"]
        S10["parsed_intent_type"]
        S11["parsed_target_field"]
        S12["route_target"]
        S13["agent_output"]
        S14["is_producing"]
        S15["waiting_for_human"]
    end

    subgraph GC["golden_context"]
        GC1["creator_profile"]
        GC2["intent"]
        GC3["consumer_personas"]
    end

    S6 --> GC
```

## 6. 关键路由逻辑说明

### 6.1 route_intent（意图路由器）

```python
async def route_intent(state) -> state:
    """
    5 层规则，按优先级执行：
    
    1. @ 引用检测
       - 有引用 + 修改词 → modify
       - 有引用 + 查询词 → query
    
    2. 阶段推进
       - 触发词 + 当前阶段已完成 → advance_phase
    
    3. 阶段开始
       - 开始词 + 当前阶段未完成 → phase_current
    
    4. intent 阶段特殊处理
       - 当前是 intent 且未完成 → phase_current
    
    5. LLM 意图分类
       - 调用 LLM 返回 JSON
       - 标准化映射（architecture → tool_architecture）
       - 返回最终 route_target
    """
```

### 6.2 route_by_intent（节点路由器）

```python
def route_by_intent(state) -> str:
    """
    根据 route_target 返回下一个节点名：
    
    - phase_current → phase_{current_phase}
    - advance_phase → phase_{next_phase}
    - tool_* → tool
    - modify/query → modify/query
    - chat → chat
    """
```

### 6.3 tool_node（工具执行器）

```python
async def tool_node(state) -> state:
    """
    根据 parsed_intent_type 分发到具体工具处理器：
    
    - tool_architecture → _llm_handle_architecture()
    - tool_outline → _llm_handle_outline()
    - tool_persona → _llm_handle_persona()
    - tool_skill → _llm_handle_skill()
    
    每个处理器内部再用 LLM 解析具体操作参数
    """
```

## 7. 可用工具清单

| 工具 | 函数 | 功能 |
|------|------|------|
| **架构读取** | `get_project_architecture()` | 读取项目结构 |
| **架构修改** | `add_phase()`, `remove_phase()`, `add_field()`, `remove_field()`, `move_field()` | 修改项目结构 |
| **大纲生成** | `generate_outline()`, `apply_outline_to_project()` | 生成内容大纲 |
| **人物管理** | `list_personas()`, `generate_persona()`, `select_persona()`, `delete_persona()` | 管理用户画像 |
| **技能管理** | `list_skills()`, `apply_skill()`, `get_skill()`, `create_skill()` | 管理提示词技能 |
| **深度调研** | `deep_research()` | DuckDuckGo + Jina 调研 |
| **消费者模拟** | `simulate()` | 5 种模拟类型 |
| **评估** | `evaluate()` | 多维度评估 |

## 8. LangGraph 节点注册

```python
# 节点注册
graph.add_node("router", route_intent)
graph.add_node("chat", chat_node)
graph.add_node("research", research_node)
graph.add_node("modify", modify_node)
graph.add_node("query", query_node)
graph.add_node("tool", tool_node)

# 阶段节点
for phase in ["intent", "research", "design_inner", "produce_inner", 
              "design_outer", "produce_outer", "simulate", "evaluate"]:
    graph.add_node(f"phase_{phase}", phase_node)

# 条件边：从 router 分发
graph.add_conditional_edges("router", route_by_intent, {
    "phase_intent": "phase_intent",
    "phase_research": "phase_research",
    # ... 其他阶段
    "modify": "modify",
    "query": "query",
    "tool": "tool",
    "chat": "chat",
})

# 所有节点 → END
graph.add_edge("tool", END)
graph.add_edge("chat", END)
graph.add_edge("modify", END)
graph.add_edge("query", END)
```
