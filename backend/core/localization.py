# backend/core/localization.py
# 功能: locale 规范化、默认值、fallback 链与少量共享 locale 命名工具
# 主要函数: normalize_locale, locale_fallback_chain, resolve_locale_name, resolve_eval_anchor_name
# 数据结构: DEFAULT_LOCALE / SUPPORTED_PROJECT_LOCALES 常量

from __future__ import annotations

DEFAULT_LOCALE = "zh-CN"
SUPPORTED_PROJECT_LOCALES = ["zh-CN", "ja-JP"]


def normalize_locale(locale: str | None) -> str:
    """将空值和别名归一化为系统支持的 locale。"""
    value = (locale or "").strip()
    if not value:
        return DEFAULT_LOCALE
    lowered = value.lower()
    if lowered in {"zh", "zh-cn", "zh_hans"}:
        return "zh-CN"
    if lowered in {"ja", "ja-jp", "jp"}:
        return "ja-JP"
    return value


def locale_fallback_chain(locale: str | None) -> list[str]:
    """返回 locale 的逐级 fallback 链，最后兜底到默认中文。"""
    normalized = normalize_locale(locale)
    chain: list[str] = []
    if normalized:
        chain.append(normalized)
    language = normalized.split("-", 1)[0] if normalized else ""
    if language and language not in chain:
        chain.append(language)
    if DEFAULT_LOCALE not in chain:
        chain.append(DEFAULT_LOCALE)
    base_language = DEFAULT_LOCALE.split("-", 1)[0]
    if base_language not in chain:
        chain.append(base_language)
    return chain


def resolve_locale_name(locale: str | None) -> str:
    """返回前端展示友好的语言名称。"""
    normalized = normalize_locale(locale)
    mapping = {
        "zh-CN": "简体中文",
        "ja-JP": "日本語",
    }
    return mapping.get(normalized, normalized)


def resolve_eval_anchor_name(handler: str, locale: str | None) -> str:
    """返回 Eval V2 锚点块在指定 locale 下的规范名称。"""
    normalized = normalize_locale(locale)
    mapping = {
        "eval_persona_setup": {
            "zh-CN": "人物画像设置",
            "ja-JP": "ペルソナ設定",
        },
        "eval_task_config": {
            "zh-CN": "评估任务配置",
            "ja-JP": "評価タスク設定",
        },
        "eval_report": {
            "zh-CN": "评估报告",
            "ja-JP": "評価レポート",
        },
    }
    localized = mapping.get(handler, {})
    return localized.get(normalized) or localized.get(DEFAULT_LOCALE) or handler
