# DeepResearch 实现方案
# 创建时间: 20260202
# 功能: 零额外成本的深度调研方案

## 方案概述

使用免费API组合实现深度调研：
- **DuckDuckGo**: 免费搜索，无需API Key
- **Jina Reader**: 免费网页内容提取
- **OpenAI**: 用户已有的API

## 架构流程

```
┌─────────────────────────────────────────────────────────────┐
│                DeepResearch Agent                            │
│                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐     │
│  │ 1. 规划查询   │ → │ 2. DuckDuckGo │ → │ 3. Jina Reader│    │
│  │ (OpenAI)     │   │ (免费搜索)    │   │ (读取网页)    │    │
│  └──────────────┘   └──────────────┘   └──────────────┘     │
│         │                                     │              │
│         │         ┌───────────────────────────┘              │
│         │         ▼                                          │
│         │  ┌─────────────┐                                   │
│         │  │ 4. 内容筛选  │  (去重、相关性过滤)                 │
│         │  └──────┬──────┘                                   │
│         │         │                                          │
│         └────────►│                                          │
│                   ▼                                          │
│           ┌─────────────────┐                                │
│           │ 5. 综合分析报告  │                                │
│           │ (OpenAI结构化)  │                                │
│           └─────────────────┘                                │
└─────────────────────────────────────────────────────────────┘
```

## 实现代码

```python
import asyncio
from duckduckgo_search import DDGS
import httpx
from pydantic import BaseModel

class ResearchReport(BaseModel):
    """调研报告结构"""
    summary: str  # 总体概述
    consumer_profile: dict  # 消费者画像
    pain_points: list[str]  # 痛点列表
    value_propositions: list[str]  # 价值点
    personas: list[dict]  # 典型人物小传
    sources: list[str]  # 信息来源

async def deep_research(
    query: str, 
    intent: str,
    max_sources: int = 10
) -> ResearchReport:
    """
    执行深度调研
    
    Args:
        query: 调研主题
        intent: 项目意图（用于上下文）
        max_sources: 最大信息源数量
    """
    
    # 1. 规划搜索查询
    search_queries = await plan_search_queries(query, intent)
    
    # 2. 并行执行DuckDuckGo搜索
    all_results = []
    for q in search_queries:
        results = search_ddg(q)
        all_results.extend(results)
    
    # 3. 去重、筛选Top URLs
    unique_urls = deduplicate_urls(all_results, max_sources)
    
    # 4. 并行读取网页内容
    contents = await asyncio.gather(*[
        read_with_jina(url) for url in unique_urls
    ], return_exceptions=True)
    
    # 过滤失败的请求
    valid_contents = [c for c in contents if isinstance(c, str)]
    
    # 5. 综合分析生成报告
    report = await synthesize_report(valid_contents, query, intent)
    
    return report


def search_ddg(query: str, max_results: int = 10) -> list[dict]:
    """DuckDuckGo搜索"""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return results  # [{"title": "...", "href": "...", "body": "..."}]


async def read_with_jina(url: str, timeout: float = 30.0) -> str:
    """使用Jina Reader读取网页内容"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://r.jina.ai/{url}",
            timeout=timeout,
            headers={"Accept": "text/markdown"}
        )
        if response.status_code == 200:
            return response.text
        raise Exception(f"Jina Reader failed: {response.status_code}")


async def plan_search_queries(query: str, intent: str) -> list[str]:
    """使用LLM规划搜索查询"""
    prompt = f"""
基于以下调研主题和项目意图，生成3-5个有效的搜索查询词。

调研主题: {query}
项目意图: {intent}

要求:
1. 查询词要多角度覆盖（用户痛点、市场现状、竞品分析等）
2. 使用中文搜索词
3. 每个查询词独立成行

输出搜索查询词:
"""
    # 调用OpenAI生成
    response = await call_openai(prompt)
    queries = response.strip().split("\n")
    return [q.strip() for q in queries if q.strip()]


async def synthesize_report(
    contents: list[str], 
    query: str, 
    intent: str
) -> ResearchReport:
    """综合分析生成报告"""
    combined = "\n\n---\n\n".join(contents[:5])  # 限制长度
    
    prompt = f"""
基于以下搜索结果，生成一份消费者调研报告。

# 调研主题
{query}

# 项目意图
{intent}

# 搜索结果
{combined}

# 输出要求
请以JSON格式输出，包含以下字段:
- summary: 总体概述（200字以内）
- consumer_profile: 消费者画像（年龄、职业、特征等）
- pain_points: 主要痛点列表（3-5个）
- value_propositions: 价值主张列表（3-5个）
- personas: 3个典型用户小传（每个包含name, background, story）
"""
    
    response = await call_openai_json(prompt, ResearchReport)
    return response
```

## 降级策略

如果用户选择不使用DeepResearch：

```python
async def generate_research_from_llm(
    query: str, 
    intent: str
) -> ResearchReport:
    """
    不使用搜索，直接由LLM生成
    警告: 基于训练数据，可能不够准确
    """
    prompt = f"""
基于你的知识，为以下项目生成消费者调研报告。

注意: 这是基于通用知识的推测，建议后续补充真实调研数据。

# 项目意图
{intent}

# 调研主题
{query}

请生成报告...
"""
    return await call_openai_json(prompt, ResearchReport)
```

## 用户上传资料模式

```python
async def research_from_uploaded_files(
    files: list[UploadFile],
    query: str,
    intent: str
) -> ResearchReport:
    """基于用户上传的资料进行分析"""
    
    # 1. 解析上传文件
    contents = []
    for file in files:
        if file.content_type == "application/pdf":
            text = extract_pdf_text(file)
        else:
            text = file.read().decode("utf-8")
        contents.append(text)
    
    # 2. 综合分析
    return await synthesize_report(contents, query, intent)
```

## 成本分析

| 操作 | 成本 |
|------|------|
| DuckDuckGo搜索 | 免费 |
| Jina Reader | 免费 |
| OpenAI (规划查询) | ~$0.01 |
| OpenAI (综合分析) | ~$0.05 |
| **总计** | **~$0.06/次调研** |

仅消耗用户已有的OpenAI额度。

