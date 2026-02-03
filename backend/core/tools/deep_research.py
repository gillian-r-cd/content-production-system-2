# backend/core/tools/deep_research.py
# 功能: DeepResearch工具，零额外成本的深度调研
# 主要函数: deep_research(), search_ddg(), read_with_jina()
# 数据结构: ResearchReport

"""
DeepResearch 工具
使用 DuckDuckGo + Jina Reader + OpenAI 实现零额外成本的深度调研
"""

import asyncio
from typing import Optional
from pydantic import BaseModel, Field

import httpx
from duckduckgo_search import DDGS

from core.ai_client import ai_client, ChatMessage


class ConsumerPersona(BaseModel):
    """用户小传"""
    name: str = Field(description="人物名称")
    background: str = Field(description="背景描述")
    story: str = Field(description="完整的故事小传")
    pain_points: list[str] = Field(description="该人物的痛点")


class ResearchReport(BaseModel):
    """调研报告"""
    summary: str = Field(description="总体概述")
    consumer_profile: dict = Field(description="消费者画像")
    pain_points: list[str] = Field(description="核心痛点列表")
    value_propositions: list[str] = Field(description="价值主张列表")
    personas: list[ConsumerPersona] = Field(description="典型用户小传")
    sources: list[str] = Field(default_factory=list, description="信息来源")


def search_ddg(query: str, max_results: int = 10) -> list[dict]:
    """
    使用DuckDuckGo搜索
    
    Args:
        query: 搜索查询
        max_results: 最大结果数
    
    Returns:
        搜索结果列表 [{"title": "...", "href": "...", "body": "..."}]
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception as e:
        print(f"DuckDuckGo search failed: {e}")
        return []


async def read_with_jina(url: str, timeout: float = 30.0) -> Optional[str]:
    """
    使用Jina Reader读取网页内容
    
    Args:
        url: 网页URL
        timeout: 超时时间
    
    Returns:
        网页内容（Markdown格式）
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://r.jina.ai/{url}",
                timeout=timeout,
                headers={"Accept": "text/markdown"}
            )
            if response.status_code == 200:
                return response.text
    except Exception as e:
        print(f"Jina Reader failed for {url}: {e}")
    return None


async def plan_search_queries(query: str, intent: str) -> list[str]:
    """
    使用LLM规划搜索查询
    
    Args:
        query: 调研主题
        intent: 项目意图
    
    Returns:
        搜索查询列表
    """
    messages = [
        ChatMessage(
            role="system",
            content="你是一个搜索策略专家。请根据调研主题和项目意图，生成3-5个有效的搜索查询词。"
        ),
        ChatMessage(
            role="user",
            content=f"""调研主题: {query}
项目意图: {intent}

请生成搜索查询词，每行一个，不要编号："""
        ),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    queries = [q.strip() for q in response.content.strip().split("\n") if q.strip()]
    return queries[:5]  # 最多5个


async def synthesize_report(
    contents: list[str],
    query: str,
    intent: str,
) -> ResearchReport:
    """
    综合分析生成调研报告
    
    Args:
        contents: 网页内容列表
        query: 调研主题
        intent: 项目意图
    
    Returns:
        ResearchReport
    """
    # 限制内容长度
    combined = "\n\n---\n\n".join(contents[:5])
    if len(combined) > 15000:
        combined = combined[:15000] + "\n...(内容已截断)"
    
    messages = [
        ChatMessage(
            role="system",
            content="""你是一个资深的用户研究专家。请基于搜索结果，生成一份详细的消费者调研报告。

输出JSON格式，包含以下字段：
- summary: 总体概述（200字以内）
- consumer_profile: 消费者画像对象 {age_range, occupation, characteristics, behaviors}
- pain_points: 核心痛点列表（3-5个）
- value_propositions: 价值主张列表（3-5个）
- personas: 3个典型用户小传，每个包含 {name, background, story, pain_points}"""
        ),
        ChatMessage(
            role="user",
            content=f"""# 调研主题
{query}

# 项目意图
{intent}

# 搜索结果
{combined}

请生成调研报告："""
        ),
    ]
    
    report, _ = await ai_client.generate_structured(
        messages=messages,
        response_model=ResearchReport,
        temperature=0.7,
    )
    
    return report


async def deep_research(
    query: str,
    intent: str,
    max_sources: int = 10,
) -> ResearchReport:
    """
    执行深度调研
    
    Args:
        query: 调研主题
        intent: 项目意图
        max_sources: 最大信息源数量
    
    Returns:
        ResearchReport
    """
    # 1. 规划搜索查询
    search_queries = await plan_search_queries(query, intent)
    
    # 2. 执行搜索
    all_results = []
    for q in search_queries:
        results = search_ddg(q, max_results=5)
        all_results.extend(results)
    
    # 3. 去重URLs
    seen_urls = set()
    unique_urls = []
    for r in all_results:
        url = r.get("href", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_urls.append(url)
            if len(unique_urls) >= max_sources:
                break
    
    # 4. 并行读取网页内容
    contents = await asyncio.gather(*[
        read_with_jina(url) for url in unique_urls
    ], return_exceptions=True)
    
    # 过滤有效内容
    valid_contents = [c for c in contents if isinstance(c, str) and c]
    
    # 5. 综合分析
    report = await synthesize_report(valid_contents, query, intent)
    report.sources = unique_urls
    
    return report


async def quick_research(
    query: str,
    intent: str,
) -> ResearchReport:
    """
    快速调研（不使用搜索，直接由LLM生成）
    
    Args:
        query: 调研主题
        intent: 项目意图
    
    Returns:
        ResearchReport
    """
    messages = [
        ChatMessage(
            role="system",
            content="""你是一个资深的用户研究专家。请基于你的知识，为以下项目生成消费者调研报告。

注意：这是基于通用知识的推测，建议后续补充真实调研数据。

输出JSON格式，包含以下字段：
- summary: 总体概述（200字以内）
- consumer_profile: 消费者画像对象 {age_range, occupation, characteristics, behaviors}
- pain_points: 核心痛点列表（3-5个）
- value_propositions: 价值主张列表（3-5个）
- personas: 3个典型用户小传，每个包含 {name, background, story, pain_points}"""
        ),
        ChatMessage(
            role="user",
            content=f"""# 调研主题
{query}

# 项目意图
{intent}

请生成调研报告："""
        ),
    ]
    
    report, _ = await ai_client.generate_structured(
        messages=messages,
        response_model=ResearchReport,
        temperature=0.7,
    )
    
    return report

