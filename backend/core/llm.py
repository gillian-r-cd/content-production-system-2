# backend/core/llm.py
# 功能: 统一的 LLM 实例管理，支持 OpenAI 和 Anthropic
# 主要导出: llm (主模型), llm_mini (轻量模型), get_chat_model()
# 设计: 通过 LLM_PROVIDER 环境变量切换全局默认 provider；
#        传入具体 model 名时，自动根据前缀判断 provider（claude-* → Anthropic，其余 → OpenAI）
#
# 支持的 provider:
# 1. openai  — ChatOpenAI（支持 OpenAI 直连和 OpenRouter）
# 2. anthropic — ChatAnthropic（Anthropic 原生 API）
#
# 两者都原生支持 tool calling / bind_tools / astream_events

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

from langchain_core.language_models.chat_models import BaseChatModel
from core.config import settings


def _infer_provider(model: str) -> str:
    """根据模型名前缀推断 provider。claude-* → anthropic，其余 → openai"""
    if model and model.startswith("claude-"):
        return "anthropic"
    return "openai"


def get_chat_model(
    model: str = None,
    temperature: float = 0.7,
    streaming: bool = True,
    **kwargs,
) -> BaseChatModel:
    """
    获取 LLM 实例。

    provider 判断逻辑：
      1. 传入了 model 参数 → 根据模型名前缀自动判断（claude-* → Anthropic，其余 → OpenAI）
      2. 未传入 model → 沿用全局 LLM_PROVIDER（.env 配置）

    Args:
        model: 模型名称。传入时自动判断 provider；不传时用全局默认
        temperature: 温度
        streaming: 是否启用流式（默认开启，astream_events 需要）
        **kwargs: 其他参数

    Returns:
        BaseChatModel 实例（ChatOpenAI 或 ChatAnthropic）
    """
    if model:
        provider = _infer_provider(model)
    else:
        provider = (settings.llm_provider or "openai").lower().strip()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model or settings.anthropic_model or "claude-opus-4-6",
            api_key=settings.anthropic_api_key,
            temperature=temperature,
            streaming=streaming,
            timeout=120.0,
            max_retries=3,
            max_tokens=16384,
            **kwargs,
        )
    else:
        # 默认: OpenAI（也支持 OpenRouter 等 OpenAI 兼容 API）
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model or settings.openai_model or "gpt-4o",
            api_key=settings.openai_api_key,
            base_url=settings.openai_api_base or None,
            organization=settings.openai_org_id or None,
            temperature=temperature,
            streaming=streaming,
            timeout=120.0,
            max_retries=3,
            max_tokens=16384,
            **kwargs,
        )


# ============== 预置实例 ==============

_provider = (settings.llm_provider or "openai").lower().strip()

# 主模型：用于 Agent 决策、内容生成、修改等
llm = get_chat_model()

# 轻量模型：用于摘要、分类等简单任务（成本更低）
if _provider == "anthropic":
    llm_mini = get_chat_model(
        model=settings.anthropic_mini_model or "claude-sonnet-4-6",
        temperature=0.3,
    )
else:
    llm_mini = get_chat_model(
        model=settings.openai_mini_model or "gpt-4o-mini",
        temperature=0.3,
    )
