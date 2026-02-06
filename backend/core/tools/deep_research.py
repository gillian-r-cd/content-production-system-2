# backend/core/tools/deep_research.py
# 功能: DeepResearch工具，零额外成本的深度调研
# 主要函数: deep_research(), search_ddg(), read_with_jina()
# 数据结构: ResearchReport

"""
DeepResearch 工具
使用 DuckDuckGo + Jina Reader + OpenAI 实现零额外成本的深度调研
"""

import asyncio
from typing import Optional, List
from pydantic import BaseModel, Field

import httpx
from duckduckgo_search import DDGS

from core.ai_client import ai_client, ChatMessage


class ConsumerPersona(BaseModel):
    """用户小传"""
    id: str = Field(default="", description="唯一标识")
    name: str = Field(description="人物名称")
    basic_info: dict = Field(default_factory=dict, description="基本信息（年龄、职位、行业等）")
    background: str = Field(description="背景简介")
    pain_points: List[str] = Field(description="核心痛点")
    selected: bool = Field(default=True, description="是否选中用于Simulator")


class ResearchReport(BaseModel):
    """调研报告"""
    summary: str = Field(description="总体概述")
    consumer_profile: dict = Field(description="消费者画像")
    pain_points: List[str] = Field(description="核心痛点列表")
    value_propositions: List[str] = Field(description="价值主张列表")
    personas: List[ConsumerPersona] = Field(description="典型用户小传")
    sources: List[str] = Field(default_factory=list, description="信息来源")
    # 调试信息
    search_queries: List[str] = Field(default_factory=list, description="搜索查询词")
    content_length: int = Field(default=0, description="实际使用的内容长度")


def search_ddg(query: str, max_results: int = 10) -> List[dict]:
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


async def plan_search_queries(query: str, intent: str) -> List[str]:
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
    contents: List[str],
    query: str,
    intent: str,
    source_urls: List[str] = None,
) -> ResearchReport:
    """
    综合分析生成调研报告
    
    Args:
        contents: 网页内容列表
        query: 调研主题
        intent: 项目意图
        source_urls: 与 contents 对应的源URL列表
    
    Returns:
        ResearchReport
    """
    # 将内容与编号来源配对，以便 LLM 可以添加引用
    source_urls = source_urls or []
    numbered_sections = []
    for idx, content in enumerate(contents[:5]):
        url_label = source_urls[idx] if idx < len(source_urls) else f"来源{idx+1}"
        # 限制每个源的长度
        truncated = content[:3000] if len(content) > 3000 else content
        numbered_sections.append(f"[来源{idx+1}] ({url_label})\n{truncated}")
    
    combined = "\n\n---\n\n".join(numbered_sections)
    if len(combined) > 15000:
        combined = combined[:15000] + "\n...(内容已截断)"
    
    # 构建引用列表供 LLM 参考
    source_list = "\n".join(
        f"[{idx+1}] {url}" for idx, url in enumerate(source_urls[:5])
    ) if source_urls else "无来源URL"
    
    messages = [
        ChatMessage(
            role="system",
            content="""你是一个资深的用户研究专家。请基于搜索结果，生成一份详细的消费者调研报告。

**重要：你必须在报告中添加内联引用。** 
- 在 summary、pain_points、value_propositions 等文字中，凡是引用了某个来源的信息，都要标注 [来源N] 或 [N]。
- 例如："消费者普遍关注产品安全性 [1][3]" 或 "根据调研 [来源2]，用户主要痛点是..."
- 这样读者可以追溯每条信息的出处。

输出JSON格式，包含以下字段：
- summary: 总体概述（200字以内，包含引用标注）
- consumer_profile: 消费者画像对象 {age_range, occupation, characteristics, behaviors}
- pain_points: 核心痛点列表（3-5个，每个痛点描述中包含引用标注）
- value_propositions: 价值主张列表（3-5个，每个主张描述中包含引用标注）
- personas: 3个典型用户小传，每个包含 {name, background, story, pain_points}
- sources: 引用来源URL列表（直接使用提供的来源URL）"""
        ),
        ChatMessage(
            role="user",
            content=f"""# 调研主题
{query}

# 项目意图
{intent}

# 来源列表
{source_list}

# 搜索结果（已标注来源编号）
{combined}

请生成调研报告（记得在文中添加引用标注 [1] [2] 等）："""
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
    
    # 过滤有效内容，保持URL与内容的对应关系
    valid_contents = []
    valid_urls = []
    for url, content in zip(unique_urls, contents):
        if isinstance(content, str) and content:
            valid_contents.append(content)
            valid_urls.append(url)
    
    # 5. 综合分析（传入配对的URL以生成内联引用）
    combined_content = "\n\n---\n\n".join(valid_contents[:5])
    report = await synthesize_report(
        valid_contents, query, intent, source_urls=valid_urls
    )
    # 确保 sources 包含所有成功读取的 URL
    if not report.sources:
        report.sources = valid_urls
    report.search_queries = search_queries
    report.content_length = len(combined_content)
    
    print(f"[DeepResearch] 搜索查询: {search_queries}")
    print(f"[DeepResearch] 找到 {len(unique_urls)} 个URL，成功读取 {len(valid_contents)} 个")
    print(f"[DeepResearch] 内容总长度: {len(combined_content)} 字符")
    
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

注意：这是基于通用知识的推测（非实时搜索），建议后续补充真实调研数据。
由于没有网络搜索来源，请勿添加引用标注。

输出JSON格式，包含以下字段：
- summary: 总体概述（200字以内）
- consumer_profile: 消费者画像对象 {age_range, occupation, characteristics, behaviors}
- pain_points: 核心痛点列表（3-5个）
- value_propositions: 价值主张列表（3-5个）
- personas: 3个典型用户小传，每个包含 {name, background, story, pain_points}
- sources: 空列表（因为未使用网络搜索）"""
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

