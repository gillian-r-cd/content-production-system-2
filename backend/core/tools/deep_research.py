# backend/core/tools/deep_research.py
# 功能: DeepResearch工具，基于 Tavily Search API 的深度调研
# 主要函数: deep_research(), quick_research(), search_tavily()
# 数据结构: ResearchReport, ConsumerPersona

"""
DeepResearch 工具
使用 Tavily Search API + OpenAI 实现实时深度调研

流程:
  1. plan_search_queries(): LLM 生成 3-5 个针对性搜索查询词
  2. search_tavily(): Tavily 搜索（返回 URL + 提取后的正文，一步搞定）
  3. synthesize_report(): LLM 综合分析生成调研报告（含引用）

成本:
  - Tavily: 免费 1000 次/月（一个项目约 5-10 次搜索）
  - OpenAI: 项目已有的 LLM API
"""

import os
import asyncio
from typing import Optional, List
from pydantic import BaseModel, Field

from tavily import TavilyClient

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
    sources: List[str] = Field(default_factory=list, description="信息来源URL")
    # 调试信息
    search_queries: List[str] = Field(default_factory=list, description="搜索查询词")
    content_length: int = Field(default=0, description="实际使用的内容长度")


def _get_tavily_client() -> TavilyClient:
    """获取 Tavily 客户端（延迟初始化）
    
    优先级: pydantic-settings > os.environ > load_dotenv fallback
    注意: pydantic-settings 不会将 .env 值注入 os.environ，
    所以不能只依赖 os.getenv("TAVILY_API_KEY")。
    """
    from core.config import settings as app_settings
    api_key = app_settings.tavily_api_key or os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise ValueError(
            "TAVILY_API_KEY 未设置！请在 backend/.env 中添加：TAVILY_API_KEY=tvly-你的key\n"
            "免费注册: https://app.tavily.com/sign-in"
        )
    return TavilyClient(api_key=api_key)


def search_tavily(query: str, max_results: int = 5) -> List[dict]:
    """
    使用 Tavily 搜索（返回 URL + 已提取的正文内容）

    Tavily 的优势：搜索 + 内容提取一步完成，不需要额外的 Jina Reader。
    
    Args:
        query: 搜索查询
        max_results: 最大结果数
    
    Returns:
        搜索结果列表 [{"title": "...", "url": "...", "content": "...", "score": 0.95}]
    """
    try:
        client = _get_tavily_client()
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",  # 深度搜索，提取更多正文
            include_answer=False,     # 不需要 Tavily 的 AI 摘要
        )
        results = response.get("results", [])
        print(f"[Tavily] 搜索 '{query}' → {len(results)} 条结果")
        for r in results[:3]:
            print(f"  [{r.get('score', 0):.2f}] {r.get('title', '')} ({r.get('url', '')})")
        return results
    except Exception as e:
        import traceback
        print(f"[Tavily] 搜索失败 '{query}': {e}")
        traceback.print_exc()
        return []


async def plan_search_queries(query: str, intent: str) -> List[str]:
    """
    使用 LLM 规划搜索查询（中文优先，针对项目意图）
    
    Args:
        query: 调研主题
        intent: 项目意图
    
    Returns:
        搜索查询列表（3-5个）
    """
    messages = [
        ChatMessage(
            role="system",
            content="""你是一个搜索策略专家。你的任务是生成有效的搜索查询词，帮助了解特定项目的目标用户群体。

规则：
1. 搜索词必须针对项目的目标用户、痛点、需求，而不是搜"消费者调研方法"这种方法论
2. 搜索词要具体、有行业针对性
3. 可以使用中文或英文搜索词（选择能获得更好结果的语言）
4. 每个搜索词要从不同角度切入：用户画像、痛点、竞品、行业趋势、真实案例
5. 生成5个搜索词，每行一个，不要编号"""
        ),
        ChatMessage(
            role="user",
            content=f"""项目意图:
{intent}

请为这个项目生成5个针对性的搜索查询词，用于了解它的目标受众是谁、有什么痛点和需求。
注意不要搜"如何做消费者调研"这种方法论，而要搜实际的用户群体信息。"""
        ),
    ]
    
    response = await ai_client.async_chat(messages, temperature=0.7)
    queries = [q.strip().lstrip("0123456789.-、) ") for q in response.content.strip().split("\n") if q.strip()]
    # 过滤掉太短或方法论类的查询词
    queries = [q for q in queries if len(q) >= 4]
    
    print(f"[DeepResearch] 生成搜索查询: {queries}")
    return queries[:5]


async def synthesize_report(
    contents: List[dict],
    query: str,
    intent: str,
) -> ResearchReport:
    """
    综合分析生成调研报告
    
    Args:
        contents: Tavily 搜索结果列表 [{title, url, content, score}]
        query: 调研主题
        intent: 项目意图
    
    Returns:
        ResearchReport
    """
    # 将搜索结果格式化为带编号的来源
    numbered_sections = []
    source_urls = []
    for idx, item in enumerate(contents[:10]):
        url = item.get("url", f"来源{idx+1}")
        title = item.get("title", "")
        content = item.get("content", "")
        score = item.get("score", 0)
        
        source_urls.append(url)
        # 限制每个源的长度
        truncated = content[:3000] if len(content) > 3000 else content
        numbered_sections.append(
            f"[来源{idx+1}] ({url})\n标题: {title}\n相关度: {score:.2f}\n{truncated}"
        )
    
    combined = "\n\n---\n\n".join(numbered_sections)
    if len(combined) > 15000:
        combined = combined[:15000] + "\n...(内容已截断)"
    
    source_list = "\n".join(
        f"[{idx+1}] {url}" for idx, url in enumerate(source_urls)
    )
    
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
- personas: 3个典型用户小传，每个包含 {name, basic_info: {age, gender, city, occupation, income_level}, background, pain_points}
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

# 搜索结果（已标注来源编号，含实际网页内容）
{combined}

请基于以上真实搜索结果生成调研报告（记得在文中添加引用标注 [1] [2] 等）："""
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
    执行深度调研（Tavily Search API）
    
    流程:
    1. LLM 生成搜索词 (plan_search_queries)
    2. Tavily 搜索 (search_tavily) — 搜索 + 内容提取一步完成
    3. LLM 综合分析生成报告 (synthesize_report)
    
    Args:
        query: 调研主题
        intent: 项目意图
        max_sources: 最大信息源数量
    
    Returns:
        ResearchReport
    """
    # 1. 规划搜索查询
    search_queries = await plan_search_queries(query, intent)
    if not search_queries:
        # 降级：如果 LLM 未能生成查询词，使用意图中的关键信息
        search_queries = [intent[:100]]
    
    # 2. 执行搜索（Tavily 返回 URL + 已提取的正文）
    all_results = []
    for q in search_queries:
        results = search_tavily(q, max_results=5)
        all_results.extend(results)
    
    # 3. 去重（按 URL）
    seen_urls = set()
    unique_results = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(r)
            if len(unique_results) >= max_sources:
                break
    
    print(f"[DeepResearch] 总搜索: {len(all_results)} 条, 去重后: {len(unique_results)} 条")
    
    # 4. 综合分析
    combined_content = "\n".join(r.get("content", "") for r in unique_results)

    print(f"[DeepResearch] unique_results数量: {len(unique_results)}, URLs: {[r.get('url','')[:50] for r in unique_results[:3]]}")

    if not unique_results:
        print("[DeepResearch] 警告：搜索未返回任何结果，降级到 quick_research")
        return await quick_research(query, intent)
    
    report = await synthesize_report(unique_results, query, intent)

    # 始终使用 Tavily 返回的真实 URL（不依赖 LLM 输出的 sources）
    # LLM 有时会返回占位文本（如 "[1] 当前报告阶段无外部可用URL..."）而非实际 URL
    actual_urls = [r.get("url", "") for r in unique_results if r.get("url")]
    report.sources = actual_urls
    report.search_queries = search_queries
    report.content_length = len(combined_content)
    
    print(f"[DeepResearch] 搜索查询: {search_queries}")
    print(f"[DeepResearch] 来源URLs: {[r.get('url','') for r in unique_results[:5]]}")
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
- personas: 3个典型用户小传，每个包含 {name, basic_info: {age, gender, city, occupation, income_level}, background, pain_points}
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
