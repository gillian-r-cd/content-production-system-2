# backend/core/llm.py
# 功能: 统一的 LLM 实例管理，基于 LangChain ChatOpenAI
# 主要导出: llm (主模型), llm_mini (轻量模型), get_chat_model()
# 设计: 取代 ai_client.py，所有 LLM 调用统一走 LangChain ChatModel 接口
#
# 为什么用 ChatOpenAI 而不是自定义 ai_client:
# 1. 原生支持 tool calling (bind_tools) — LangGraph Agent 的基础
# 2. 原生支持 LangChain 消息类型 (HumanMessage, AIMessage, ToolMessage)
# 3. 切换 API 只需改一行 import (ChatGoogleGenerativeAI, ChatTongyi 等)
# 4. astream_events 原生支持 token 级流式

"""
统一 LLM 实例管理

用法:
    from core.llm import llm, llm_mini

    # 异步调用
    response = await llm.ainvoke([SystemMessage(content="..."), HumanMessage(content="...")])
    print(response.content)

    # 流式
    async for chunk in llm.astream([HumanMessage(content="...")]):
        print(chunk.content, end="")

    # 带工具
    llm_with_tools = llm.bind_tools(tools)
    response = await llm_with_tools.ainvoke(messages)
"""

from langchain_openai import ChatOpenAI
from core.config import settings


def get_chat_model(
    model: str = None,
    temperature: float = 0.7,
    streaming: bool = True,
    **kwargs,
) -> ChatOpenAI:
    """
    获取 ChatOpenAI 实例。

    Args:
        model: 模型名称，默认用配置中的 openai_model
        temperature: 温度
        streaming: 是否启用流式（默认开启，astream_events 需要）
        **kwargs: 其他 ChatOpenAI 参数

    Returns:
        ChatOpenAI 实例
    """
    return ChatOpenAI(
        model=model or settings.openai_model or "gpt-4o",
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base or None,
        organization=settings.openai_org_id or None,
        temperature=temperature,
        streaming=streaming,
        timeout=120.0,
        max_retries=3,  # 网络瞬时故障自动重试
        max_tokens=16384,  # 显式设置最大输出 token，防止长内容截断
        **kwargs,
    )


# ============== 预置实例 ==============

# 主模型：用于 Agent 决策、内容生成、修改等
llm = get_chat_model()

# 轻量模型：用于摘要、分类等简单任务（成本更低）
llm_mini = get_chat_model(model=settings.openai_mini_model or "gpt-4o-mini", temperature=0.3)
