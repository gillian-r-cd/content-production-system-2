# backend/tests/test_localization.py
# 功能: 测试 locale 规范化、fallback 链和展示名称解析
# 主要函数: test_normalize_locale_aliases, test_locale_fallback_chain_for_japanese, test_resolve_locale_name
# 数据结构: DEFAULT_LOCALE / SUPPORTED_PROJECT_LOCALES 常量与 locale fallback 链

from core.localization import (
    DEFAULT_LOCALE,
    SUPPORTED_PROJECT_LOCALES,
    locale_fallback_chain,
    normalize_locale,
    resolve_locale_name,
)


def test_supported_project_locales_contains_zh_and_ja():
    assert SUPPORTED_PROJECT_LOCALES == ["zh-CN", "ja-JP"]


def test_normalize_locale_aliases():
    assert normalize_locale(None) == DEFAULT_LOCALE
    assert normalize_locale("") == DEFAULT_LOCALE
    assert normalize_locale("zh") == "zh-CN"
    assert normalize_locale("zh-cn") == "zh-CN"
    assert normalize_locale("ja") == "ja-JP"
    assert normalize_locale("jp") == "ja-JP"


def test_locale_fallback_chain_for_japanese():
    assert locale_fallback_chain("ja-JP") == ["ja-JP", "ja", "zh-CN", "zh"]


def test_locale_fallback_chain_defaults_to_zh_cn():
    assert locale_fallback_chain(None) == ["zh-CN", "zh"]


def test_resolve_locale_name():
    assert resolve_locale_name("zh-CN") == "简体中文"
    assert resolve_locale_name("ja-JP") == "日本語"
