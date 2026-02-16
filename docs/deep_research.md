# DeepResearch 实现方案
# 更新时间: 20260216
# 功能: 基于 Tavily Search API 的深度调研工具

## 方案概述

使用 Tavily Search API + LLM 实现深度调研：
- **Tavily Search**: 搜索 + 网页内容提取一步完成（免费 1000 次/月）
- **LLM (OpenAI)**: 搜索词规划 + 结果综合分析

## 架构流程

```
┌──────────────────────────────────────────────────────────────────┐
│                      DeepResearch 工具                            │
│                                                                   │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────┐  │
│  │ 1. plan_search_  │ → │ 2. search_tavily │ → │ 3. synthesize│  │
│  │    queries()     │   │    () × N        │   │    _report() │  │
│  │ LLM 生成搜索词   │   │ Tavily 搜索+提取  │   │ LLM 综合分析 │  │
│  └──────────────────┘   └──────────────────┘   └──────────────┘  │
│                                                                   │
│  research_type 参数控制搜索词策略:                                   │
│    "consumer" → 面向目标用户/痛点/需求                               │
│    "generic"  → 面向市场/竞争/趋势/技术                              │
└──────────────────────────────────────────────────────────────────┘
```

## 调用链

```
用户触发调研（Agent Chat / 按钮）
  → agent 调用 run_research 工具      [agent_tools.py]
    → _run_research_impl()
      → deep_research(query, intent, research_type)  [deep_research.py]
        → plan_search_queries(query, intent, research_type)   生成 5 个搜索词
        → search_tavily(query) × 5                            Tavily 搜索
        → 去重（按 URL）
        → 如果 unique_results == 0 → raise ValueError（明确报错）
        → synthesize_report(results, query, intent)           LLM 综合
      → report 存入 ContentBlock "消费者调研"
      → 返回摘要给 Agent
```

## 核心函数

| 函数 | 位置 | 职责 |
|------|------|------|
| `deep_research()` | `core/tools/deep_research.py` | 主入口：编排搜索词规划、搜索执行、结果综合 |
| `plan_search_queries()` | 同上 | LLM 生成 3-5 个搜索词，按 `research_type` 区分 prompt |
| `search_tavily()` | 同上 | 调用 Tavily API 执行单次搜索，返回 URL + 正文 |
| `synthesize_report()` | 同上 | LLM 综合搜索结果，输出 `ResearchReport` 结构化报告 |
| `_run_research_impl()` | `core/agent_tools.py` | 工具层：获取项目意图，调用 `deep_research`，保存结果 |

## 数据结构

```python
class ResearchReport(BaseModel):
    summary: str                          # 总体概述
    consumer_profile: ConsumerProfileInfo  # 消费者画像
    pain_points: List[str]                # 核心痛点列表
    value_propositions: List[str]         # 价值主张列表
    personas: List[ConsumerPersona]       # 典型用户小传
    sources: List[str]                    # 信息来源 URL（Tavily 返回的真实 URL）
    search_queries: List[str]             # 搜索查询词（调试用）
    content_length: int                   # 实际使用的内容长度（调试用）
```

## 错误处理

- Tavily API Key 未配置 → `_get_tavily_client()` 抛出 `ValueError`，附注册链接
- 单次搜索失败 → `search_tavily()` 捕获异常，返回空列表，不中断整体流程
- 所有搜索均无结果 → `deep_research()` 抛出 `ValueError`，包含可能原因提示
- LLM 生成搜索词失败 → 降级使用 `intent[:100]` 作为搜索词

设计原则：**搜不到就明确告知用户，绝不用 LLM 编造内容冒充调研结果。**

## 成本分析

| 操作 | 成本 |
|------|------|
| Tavily 搜索 | 免费 1000 次/月（一个项目约 5-10 次搜索） |
| LLM (规划查询) | ~$0.01 |
| LLM (综合分析) | ~$0.05 |
| **总计** | **~$0.06/次调研** |
