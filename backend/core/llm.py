# backend/core/llm.py
# 功能: 统一的 LLM 实例管理，支持 OpenAI、Anthropic 和 Google Gemini
# 主要导出: llm (主模型), llm_mini (轻量模型), get_chat_model()
# 设计: 通过 LLM_PROVIDER 环境变量切换全局默认 provider；
#        传入具体 model 名时，自动根据前缀判断 provider（claude-* → Anthropic，gemini-* → Google，其余 → OpenAI）
#
# 支持的 provider:
# 1. openai  — ChatOpenAI（支持 OpenAI 直连和 OpenRouter）
# 2. anthropic — ChatAnthropic（Anthropic 原生 API）
# 3. google  — ChatGoogleGenerativeAI（Google AI 直连，Gemini 系列）
#
# 三者都原生支持 tool calling / bind_tools / astream_events

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
    """根据模型名前缀推断 provider。claude-* → anthropic，gemini-* → google，其余 → openai"""
    if model and model.startswith("claude-"):
        return "anthropic"
    if model and model.startswith("gemini-"):
        return "google"
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
      1. 传入了 model 参数 → 根据模型名前缀自动判断（claude-* → Anthropic，gemini-* → Google，其余 → OpenAI）
      2. 未传入 model → 沿用全局 LLM_PROVIDER（.env 配置）

    Args:
        model: 模型名称。传入时自动判断 provider；不传时用全局默认
        temperature: 温度
        streaming: 是否启用流式（默认开启，astream_events 需要）
        **kwargs: 其他参数

    Returns:
        BaseChatModel 实例（ChatOpenAI、ChatAnthropic 或 ChatGoogleGenerativeAI）
    """
    if model:
        provider = _infer_provider(model)
    else:
        provider = (settings.llm_provider or "openai").lower().strip()

    # 统一超时配置（从 .env 读取，默认 300s，思考模型友好）
    timeout = float(settings.llm_timeout or 300)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model or settings.anthropic_model or "claude-opus-4-6",
            api_key=settings.anthropic_api_key,
            temperature=temperature,
            streaming=streaming,
            timeout=timeout,
            max_retries=3,
            max_tokens=16384,
            **kwargs,
        )
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Gemini 3.x thinking 配置：
        #   -1 = 模型默认（推荐，兼容所有 Gemini 模型）
        #    0 = 关闭思考（仅部分模型支持，gemini-3.1-pro 等纯思考模型不支持）
        #   >0 = 指定 thinking token 预算
        # 安全策略: budget=0 时不传参（防止纯思考模型报错），让模型使用默认行为
        thinking_budget = settings.google_thinking_budget
        thinking_kwargs = {}
        if thinking_budget > 0:
            thinking_kwargs["thinking_budget"] = thinking_budget

        return ChatGoogleGenerativeAI(
            model=model or settings.google_model or "gemini-3.1-pro-preview",
            google_api_key=settings.google_api_key,
            temperature=temperature,
            streaming=streaming,
            timeout=timeout,
            max_retries=3,
            max_output_tokens=16384,
            **thinking_kwargs,
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
            timeout=timeout,
            max_retries=3,
            max_tokens=16384,
            **kwargs,
        )


# ============== LLM 调用重试 + 错误解析 ==============

import asyncio
import logging
import re

_llm_logger = logging.getLogger(__name__)

# 可重试的瞬态错误模式（覆盖 Anthropic / OpenAI / Google 常见瞬态错误）
_RETRYABLE_PATTERNS = [
    "overloaded",           # Anthropic 529
    "rate_limit",           # 429 rate limit（下划线格式）
    "rate limit",           # 429 rate limit（空格格式）
    "too many requests",
    "503",                  # Service Unavailable
    "502",                  # Bad Gateway
    "529",                  # Anthropic Overloaded
    "capacity",
    "temporarily unavailable",
    "server_error",         # 下划线格式
    "server error",         # 空格格式（Anthropic 'Internal server error'）
    "internal server error",# Anthropic api_error 500
    "api_error",            # Anthropic error type = api_error（内部错误）
    "UNAVAILABLE",          # Google 503
    "RESOURCE_EXHAUSTED",   # Google quota
    # 注意：timeout / timed out / DeadlineExceeded 已从可重试列表中移除！
    # 原因：思考模型（Gemini 3.1 等）的超时通常不是瞬态问题，
    # 重试只会让用户等 4×timeout ≈ 8 分钟，应该快速失败并提示用户。
]


def _is_retryable(error: Exception) -> bool:
    """判断异常是否属于可重试的瞬态错误。"""
    err_str = str(error).lower()
    for pattern in _RETRYABLE_PATTERNS:
        if pattern.lower() in err_str:
            return True
    # HTTP 状态码检测（500 = Anthropic/OpenAI 内部服务器错误，属于可重试瞬态故障）
    status = getattr(error, "status_code", None) or getattr(error, "status", None)
    if status in (429, 500, 502, 503, 529):
        return True
    return False


def parse_llm_error(error: Exception) -> str:
    """
    将 LLM API 原始异常转为用户友好的中文错误信息。
    返回的字符串可直接发给前端展示。
    """
    err_str = str(error).strip()

    # ===== 补充诊断：当 str(error) 为空时，从异常属性中提取有用信息 =====
    if not err_str:
        # 许多 LLM SDK 的异常有 status_code / body / message 等属性
        parts = []
        err_type = type(error).__name__
        parts.append(err_type)

        status = getattr(error, "status_code", None) or getattr(error, "status", None)
        if status:
            parts.append(f"HTTP {status}")

        body = getattr(error, "body", None)
        if body:
            if isinstance(body, dict):
                parts.append(body.get("message", "") or body.get("error", ""))
            else:
                parts.append(str(body)[:200])

        msg_attr = getattr(error, "message", None)
        if msg_attr:
            parts.append(str(msg_attr))

        err_str = " | ".join(p for p in parts if p)

    # ===== 如果仍然为空，给出最有可能的诊断 =====
    if not err_str:
        err_str = f"(异常类型: {type(error).__name__})"

    err_lower = err_str.lower()

    # ===== 常见错误模式匹配 =====
    if "overloaded" in err_lower or "529" in err_lower:
        return "AI 服务当前过载，请等待 1-2 分钟后重试。"
    if "rate_limit" in err_lower or "rate limit" in err_lower or "429" in err_lower or "too many requests" in err_lower:
        return "API 请求频率超限，请稍后重试。"
    if "unavailable" in err_lower or "503" in err_lower:
        return "AI 服务暂时不可用，请稍后重试。"
    if "timeout" in err_lower or "timed out" in err_lower or "deadline" in err_lower:
        return "AI 服务响应超时，请缩短输入内容后重试。"
    if "invalid_api_key" in err_lower or "authentication" in err_lower or "401" in err_lower or "incorrect api key" in err_lower:
        return "API 密钥无效，请检查 backend/.env 中的 API Key 配置。"
    if "api key" in err_lower and ("not" in err_lower or "miss" in err_lower or "empty" in err_lower or "invalid" in err_lower):
        return "API 密钥无效或未配置，请检查 backend/.env 中的 API Key 配置。"
    if "connection" in err_lower or "connect" in err_lower or "resolve" in err_lower or "refused" in err_lower:
        return f"无法连接到 AI 服务（网络错误），请检查网络连接和 API Base URL 配置。({err_str[:100]})"
    if "insufficient_quota" in err_lower or "billing" in err_lower or "402" in err_lower:
        return "API 额度不足，请检查账户余额。"
    if "context_length" in err_lower or "too long" in err_lower or "max.*token" in err_lower:
        return "输入内容过长，超出模型上下文窗口，请精简内容后重试。"
    if "content_policy" in err_lower or "safety" in err_lower or "blocked" in err_lower:
        return "内容被 AI 安全策略拦截，请调整输入内容。"
    if "not found" in err_lower and ("model" in err_lower or "404" in err_lower):
        return f"模型不存在或不可用，请检查 backend/.env 中的模型名称配置。({err_str[:100]})"

    # 兜底：去除 JSON 格式噪音，保留核心错误信息
    # 尝试提取 'message' 字段
    msg_match = re.search(r"'message':\s*'([^']+)'", err_str)
    if msg_match:
        return f"AI 调用失败: {msg_match.group(1)}"

    # 截断过长的错误信息
    if len(err_str) > 200:
        return f"AI 调用失败: {err_str[:200]}..."
    return f"AI 调用失败: {err_str}"


async def ainvoke_with_retry(
    chat_model,
    messages,
    *,
    max_retries: int = 3,
    base_delay: float = 5.0,
    **kwargs,
):
    """
    带指数退避重试的 ainvoke 调用。

    对瞬态错误（overloaded / rate_limit / 503 等）自动重试，
    对其他错误直接抛出（parse_llm_error 友好化）。

    Args:
        chat_model: BaseChatModel 实例
        messages: 消息列表
        max_retries: 最大重试次数（不含首次调用）
        base_delay: 初始退避延迟（秒），每次翻倍
        **kwargs: 传给 ainvoke 的额外参数（如 config）
    """
    last_error = None
    for attempt in range(1 + max_retries):
        try:
            return await chat_model.ainvoke(messages, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries and _is_retryable(e):
                delay = base_delay * (2 ** attempt)
                _llm_logger.warning(
                    "[llm_retry] 瞬态错误 (attempt %d/%d): %s — 等待 %.1fs 后重试",
                    attempt + 1, 1 + max_retries, type(e).__name__, delay,
                )
                await asyncio.sleep(delay)
            else:
                raise

    # 不会执行到这里，但作为防御
    raise last_error  # type: ignore


async def astream_with_retry(
    chat_model,
    messages,
    *,
    max_retries: int = 3,
    base_delay: float = 5.0,
):
    """
    带指数退避重试的 astream 调用。

    仅在流尚未产出任何 chunk 时重试（出错 → 重新发起整个请求）。
    一旦已产出 chunk 就不再重试（避免内容重复）。

    Yields:
        LLM chunk（与 chat_model.astream 一致）
    """
    last_error = None
    for attempt in range(1 + max_retries):
        try:
            async for chunk in chat_model.astream(messages):
                yield chunk
            return  # 流正常结束
        except Exception as e:
            last_error = e
            if attempt < max_retries and _is_retryable(e):
                delay = base_delay * (2 ** attempt)
                _llm_logger.warning(
                    "[llm_retry] 流式瞬态错误 (attempt %d/%d): %s — 等待 %.1fs 后重试",
                    attempt + 1, 1 + max_retries, type(e).__name__, delay,
                )
                await asyncio.sleep(delay)
            else:
                raise

    raise last_error  # type: ignore


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
elif _provider == "google":
    llm_mini = get_chat_model(
        model=settings.google_mini_model or "gemini-3-flash-preview",
        temperature=0.3,
    )
else:
    llm_mini = get_chat_model(
        model=settings.openai_mini_model or "gpt-4o-mini",
        temperature=0.3,
    )
