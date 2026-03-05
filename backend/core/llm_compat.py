# backend/core/llm_compat.py
# 功能: LLM Provider 兼容性工具函数 + 模型选择覆盖链
# 主要导出: normalize_content, get_stop_reason, get_model_name, sanitize_messages, resolve_model
# 设计: 屏蔽 OpenAI / Anthropic / Google 返回值差异，让下游代码无需感知 Provider；
#        resolve_model() 实现 "内容块覆盖 → 用户全局默认 → .env" 三级回退链

"""
LLM Provider 兼容层。

所有直接读取 LLM 返回值的下游代码应通过本模块提供的工具函数，
而非直接访问 response.content / response.response_metadata 等字段。

用法:
    from core.llm_compat import normalize_content, get_stop_reason, get_model_name, resolve_model

    text = normalize_content(response.content)
    reason, truncated = get_stop_reason(response)
    model = get_model_name()

    # 模型选择覆盖链
    model_name = resolve_model(model_override=block.model_override)
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional, Tuple

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage

from core.config import settings

logger = logging.getLogger(__name__)


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
    elif provider == "google":
        if mini:
            return settings.google_mini_model or "gemini-3-flash-preview"
        return settings.google_model or "gemini-3.1-pro-preview"
    else:
        if mini:
            return settings.openai_mini_model or "gpt-4o-mini"
        return settings.openai_model or "gpt-5.1"


def sanitize_messages(
    messages: List[BaseMessage],
    model: Optional[str] = None,
) -> List[BaseMessage]:
    """
    清理消息列表，确保符合 Provider 的约束。

    对 Anthropic:
      - 将所有 SystemMessage 的内容合并为一条，确保在列表首位
      - 移除其他位置的 SystemMessage
      - 修复孤立的 tool_use/tool_result：
          * 没有紧跟 ToolMessage 的 AIMessage(tool_calls) → 丢弃（防止 400 错误）
          * 没有对应 AIMessage 的孤立 ToolMessage → 丢弃
    对 OpenAI: 不做任何处理。

    Args:
        messages: 消息列表
        model: 实际使用的模型名。传入时按模型名判断 provider；
               不传时回退到全局 settings.llm_provider

    这是防御性措施，防止 Checkpointer 恢复的历史消息中出现格式违规。
    """
    if model:
        provider = _infer_provider(model)
    else:
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
        return [merged] + _repair_tool_pairs(non_system)
    return _repair_tool_pairs(non_system)


def _repair_tool_pairs(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    修复 Anthropic 要求的 tool_use → tool_result 配对约束。

    Anthropic API 要求：每个含 tool_calls 的 AIMessage（tool_use）必须
    紧跟对应的 ToolMessage（tool_result）。如果 Checkpointer 恢复的状态
    中存在孤立的 tool_use（例如服务重启导致工具未执行），直接发给 Anthropic
    会触发 400 错误。

    本函数扫描消息列表，移除任何没有紧跟完整 ToolMessage 的 AIMessage(tool_calls)，
    以及任何前面没有对应 AIMessage(tool_calls) 的孤立 ToolMessage。
    对 OpenAI/其他 provider 调用时本函数是恒等操作（不做任何修改）。
    """
    if not messages:
        return messages

    repaired: List[BaseMessage] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        # 检查是否是含 tool_calls 的 AIMessage
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            tool_call_ids = {tc["id"] for tc in msg.tool_calls if "id" in tc}
            # 收集紧随其后的所有 ToolMessage
            j = i + 1
            tool_results: List[ToolMessage] = []
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                tool_results.append(messages[j])
                j += 1
            result_ids = {tm.tool_call_id for tm in tool_results if hasattr(tm, "tool_call_id")}
            # 只有当所有 tool_call_id 都有对应的 tool_result 时才保留这组消息
            if tool_call_ids and tool_call_ids.issubset(result_ids):
                repaired.append(msg)
                repaired.extend(tool_results)
            else:
                # 孤立的 tool_use：丢弃（同时丢弃其后不完整的 ToolMessage）
                logger.warning(
                    "[sanitize_messages] 丢弃孤立 tool_use: tool_call_ids=%s, "
                    "found_result_ids=%s",
                    tool_call_ids,
                    result_ids,
                )
            i = j  # 跳过已处理的 ToolMessage
        elif isinstance(msg, ToolMessage):
            # 到达这里说明 ToolMessage 前面没有对应的 AIMessage(tool_calls)，属于孤立消息
            logger.warning(
                "[sanitize_messages] 丢弃孤立 tool_result: tool_call_id=%s",
                getattr(msg, "tool_call_id", "unknown"),
            )
            i += 1
        else:
            repaired.append(msg)
            i += 1

    return repaired


# ============== Provider 推断 ==============

def _infer_provider(model: str) -> str:
    """根据模型名前缀推断 provider。claude-* → anthropic，gemini-* → google，其余 → openai"""
    if model and model.startswith("claude-"):
        return "anthropic"
    if model and model.startswith("gemini-"):
        return "google"
    return "openai"


# ============== 模型选择覆盖链 ==============

# 进程内缓存：存储从 DB 读取的 AgentSettings 默认模型
# 格式: {"default_model": str|None, "default_mini_model": str|None, "_ts": float}
_agent_settings_cache: dict = {}
_CACHE_TTL_SECONDS = 60  # 缓存有效期（秒）


def _get_agent_settings_model(use_mini: bool = False) -> Optional[str]:
    """
    从 AgentSettings 单例读取用户全局默认模型。
    带进程内缓存（TTL 60s），写入时通过 invalidate_model_cache() 立即失效。
    """
    global _agent_settings_cache

    now = time.time()
    if _agent_settings_cache and (now - _agent_settings_cache.get("_ts", 0)) < _CACHE_TTL_SECONDS:
        key = "default_mini_model" if use_mini else "default_model"
        return _agent_settings_cache.get(key)

    # 缓存过期或不存在，查 DB
    try:
        from core.database import get_session_maker
        from core.models.agent_settings import AgentSettings

        SessionLocal = get_session_maker()
        db = SessionLocal()
        try:
            row = db.query(AgentSettings).filter(AgentSettings.name == "default").first()
            if row:
                _agent_settings_cache = {
                    "default_model": row.default_model,
                    "default_mini_model": row.default_mini_model,
                    "_ts": now,
                }
            else:
                _agent_settings_cache = {
                    "default_model": None,
                    "default_mini_model": None,
                    "_ts": now,
                }
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"读取 AgentSettings 默认模型失败: {e}")
        _agent_settings_cache = {
            "default_model": None,
            "default_mini_model": None,
            "_ts": now,
        }

    key = "default_mini_model" if use_mini else "default_model"
    return _agent_settings_cache.get(key)


def invalidate_model_cache() -> None:
    """
    使模型缓存立即失效。
    在 AgentSettings 更新 default_model / default_mini_model 时调用。
    """
    global _agent_settings_cache
    _agent_settings_cache = {}


def resolve_model(
    model_override: Optional[str] = None,
    use_mini: bool = False,
) -> str:
    """
    解析最终模型名。覆盖链优先级：
      1. model_override（内容块级）
      2. AgentSettings.default_model（用户全局级）
      3. settings.xxx_model（.env 级）

    Args:
        model_override: 内容块的 model_override 值（可能为 None）
        use_mini: 是否使用轻量模型

    Returns:
        最终模型名（如 "gpt-5.2" 或 "claude-opus-4-6"）
    """
    # 级别 1: 内容块覆盖
    if model_override:
        return model_override

    # 级别 2: 用户全局默认（从 DB 读取，带缓存）
    db_default = _get_agent_settings_model(use_mini)
    if db_default:
        return db_default

    # 级别 3: .env 默认
    return get_model_name(mini=use_mini)
