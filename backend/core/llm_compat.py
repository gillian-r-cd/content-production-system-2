# backend/core/llm_compat.py
# 功能: LLM Provider 兼容性工具函数
# 主要导出: normalize_content, get_stop_reason, get_model_name, sanitize_messages
# 设计: 屏蔽 OpenAI / Anthropic 返回值差异，让下游代码无需感知 Provider

"""
LLM Provider 兼容层。

所有直接读取 LLM 返回值的下游代码应通过本模块提供的工具函数，
而非直接访问 response.content / response.response_metadata 等字段。

用法:
    from core.llm_compat import normalize_content, get_stop_reason, get_model_name

    text = normalize_content(response.content)
    reason, truncated = get_stop_reason(response)
    model = get_model_name()
"""

from __future__ import annotations

from typing import Any, List, Tuple

from langchain_core.messages import BaseMessage, SystemMessage

from core.config import settings


def normalize_content(content: Any) -> str:
    """
    将 LLM 返回的 content 归一化为 str。

    ChatOpenAI:     content 始终是 str
    ChatAnthropic:  content 可能是 str 或 list[dict]（内容块列表）

    对 str 输入是恒等操作（零开销）。
    对 list 输入提取所有 text 块并拼接。
    对 None / 其他类型做安全回退。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content) if content else ""


def get_stop_reason(response: Any) -> Tuple[str, bool]:
    """
    从 LLM 响应中提取停止原因。

    Returns:
        (reason, is_truncated) — reason 是统一后的停止原因字符串，
        is_truncated 为 True 表示输出被截断（达到 max_tokens）。

    OpenAI:     response_metadata["finish_reason"] = "stop" | "length" | "tool_calls"
    Anthropic:  response_metadata["stop_reason"]   = "end_turn" | "max_tokens" | "tool_use"
    """
    meta = getattr(response, "response_metadata", None) or {}
    reason = meta.get("finish_reason", meta.get("stop_reason", "stop"))
    is_truncated = reason in ("length", "max_tokens")
    return reason, is_truncated


def get_model_name(mini: bool = False) -> str:
    """
    获取当前活跃的模型名称（用于日志和计费）。

    Args:
        mini: 为 True 时返回轻量模型名。

    根据 settings.llm_provider 返回对应 provider 的模型名。
    """
    provider = (settings.llm_provider or "openai").lower().strip()
    if provider == "anthropic":
        if mini:
            return settings.anthropic_mini_model or "claude-sonnet-4-6"
        return settings.anthropic_model or "claude-opus-4-6"
    else:
        if mini:
            return settings.openai_mini_model or "gpt-4o-mini"
        return settings.openai_model or "gpt-5.1"


def sanitize_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    清理消息列表，确保符合当前 Provider 的约束。

    对 Anthropic:
      - 将所有 SystemMessage 的内容合并为一条
      - 确保合并后的 SystemMessage 在列表首位
      - 移除其他位置的 SystemMessage
    对 OpenAI: 不做处理（无约束）。

    这是防御性措施，防止 Checkpointer 恢复的历史消息中混入多条 SystemMessage。
    """
    provider = (settings.llm_provider or "openai").lower().strip()
    if provider != "anthropic":
        return messages

    system_parts: list[str] = []
    non_system: list[BaseMessage] = []

    for msg in messages:
        if isinstance(msg, SystemMessage):
            content = normalize_content(msg.content)
            if content.strip():
                system_parts.append(content)
        else:
            non_system.append(msg)

    if system_parts:
        merged = SystemMessage(content="\n\n".join(system_parts))
        return [merged] + non_system
    return non_system
