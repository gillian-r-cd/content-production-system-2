# backend/tests/test_model_selection.py
# 功能: M5 模型选择功能的单元测试
# 覆盖: resolve_model, get_chat_model 自动 provider, sanitize_messages(model=...), _infer_provider

"""
M5 模型选择功能 — 单元测试

覆盖:
  - resolve_model 覆盖链 3 级回退
  - get_chat_model 按模型名自动选择 provider
  - sanitize_messages 按 model 参数判断 provider
  - _infer_provider 推断逻辑
  - calculate_cost 新模型定价
"""

import pytest
from unittest.mock import patch, MagicMock


# ============== _infer_provider ==============

class TestInferProvider:
    def test_claude_models(self):
        from core.llm_compat import _infer_provider
        assert _infer_provider("claude-opus-4-6") == "anthropic"
        assert _infer_provider("claude-sonnet-4-6") == "anthropic"
        assert _infer_provider("claude-sonnet-4-5") == "anthropic"
        assert _infer_provider("claude-haiku-3-5") == "anthropic"

    def test_openai_models(self):
        from core.llm_compat import _infer_provider
        assert _infer_provider("gpt-5.1") == "openai"
        assert _infer_provider("gpt-5.2") == "openai"
        assert _infer_provider("gpt-4o-mini") == "openai"
        assert _infer_provider("gpt-4o") == "openai"

    def test_empty_or_none(self):
        from core.llm_compat import _infer_provider
        assert _infer_provider("") == "openai"
        assert _infer_provider(None) == "openai"


# ============== resolve_model ==============

class TestResolveModel:
    def test_block_override_takes_priority(self):
        """model_override 非空时直接返回，不查 DB"""
        from core.llm_compat import resolve_model
        assert resolve_model(model_override="gpt-5.2") == "gpt-5.2"
        assert resolve_model(model_override="claude-sonnet-4-6") == "claude-sonnet-4-6"

    def test_global_default_from_db(self):
        """model_override 为空时回退到 AgentSettings"""
        from core.llm_compat import resolve_model, invalidate_model_cache

        # Mock _get_agent_settings_model：主模型返回 gpt-5.2，mini 返回 gpt-4o-mini
        def fake_get_model(use_mini=False):
            return "gpt-4o-mini" if use_mini else "gpt-5.2"

        invalidate_model_cache()
        with patch("core.llm_compat._get_agent_settings_model", side_effect=fake_get_model):
            result = resolve_model()
            assert result == "gpt-5.2"

            result_mini = resolve_model(use_mini=True)
            assert result_mini == "gpt-4o-mini"

        invalidate_model_cache()

    def test_env_fallback(self):
        """AgentSettings 也为空时回退到 .env"""
        from core.llm_compat import resolve_model, invalidate_model_cache, get_model_name

        # Mock _get_agent_settings_model 返回 None（DB 无默认模型）
        invalidate_model_cache()
        with patch("core.llm_compat._get_agent_settings_model", return_value=None):
            result = resolve_model()
            assert result == get_model_name(mini=False)

            result_mini = resolve_model(use_mini=True)
            assert result_mini == get_model_name(mini=True)

        invalidate_model_cache()


# ============== get_chat_model auto provider ==============

class TestGetChatModelAutoProvider:
    def test_openai_model_returns_chatopenai(self):
        from core.llm import get_chat_model
        model = get_chat_model(model="gpt-5.2")
        assert type(model).__name__ == "ChatOpenAI"

    def test_anthropic_model_returns_chatanthropic(self):
        from core.llm import get_chat_model
        model = get_chat_model(model="claude-sonnet-4-6")
        assert type(model).__name__ == "ChatAnthropic"

    def test_no_model_uses_global_provider(self):
        """不传 model 时使用全局 provider（向后兼容）"""
        from core.llm import get_chat_model
        from core.config import settings
        model = get_chat_model()
        provider = (settings.llm_provider or "openai").lower().strip()
        if provider == "anthropic":
            assert type(model).__name__ == "ChatAnthropic"
        else:
            assert type(model).__name__ == "ChatOpenAI"


# ============== sanitize_messages with model param ==============

class TestSanitizeMessagesWithModel:
    def test_anthropic_model_merges_system(self):
        """传 model='claude-...' 时执行 SystemMessage 合并"""
        from core.llm_compat import sanitize_messages
        from langchain_core.messages import SystemMessage, HumanMessage

        msgs = [
            SystemMessage(content="First"),
            SystemMessage(content="Second"),
            HumanMessage(content="Hello"),
        ]
        result = sanitize_messages(msgs, model="claude-opus-4-6")
        # 应该合并为 1 条 SystemMessage
        sys_msgs = [m for m in result if isinstance(m, SystemMessage)]
        assert len(sys_msgs) == 1
        assert "First" in sys_msgs[0].content
        assert "Second" in sys_msgs[0].content

    def test_openai_model_no_merge(self):
        """传 model='gpt-...' 时不做处理"""
        from core.llm_compat import sanitize_messages
        from langchain_core.messages import SystemMessage, HumanMessage

        msgs = [
            SystemMessage(content="First"),
            SystemMessage(content="Second"),
            HumanMessage(content="Hello"),
        ]
        result = sanitize_messages(msgs, model="gpt-5.2")
        # 不应该合并
        sys_msgs = [m for m in result if isinstance(m, SystemMessage)]
        assert len(sys_msgs) == 2

    def test_no_model_uses_global(self):
        """不传 model 时使用全局 provider"""
        from core.llm_compat import sanitize_messages
        from langchain_core.messages import SystemMessage, HumanMessage

        msgs = [
            SystemMessage(content="Single"),
            HumanMessage(content="Hello"),
        ]
        result = sanitize_messages(msgs)
        # 无论全局 provider 是什么，单条 SystemMessage 都不会出问题
        assert len(result) >= 1


# ============== calculate_cost new models ==============

class TestCalculateCostNewModels:
    def test_gpt_5_2_pricing(self):
        from core.models.generation_log import GenerationLog
        cost = GenerationLog.calculate_cost("gpt-5.2", 1_000_000, 1_000_000)
        assert cost == round(5.00 + 15.00, 6)

    def test_claude_sonnet_4_5_pricing(self):
        from core.models.generation_log import GenerationLog
        cost = GenerationLog.calculate_cost("claude-sonnet-4-5", 1_000_000, 1_000_000)
        assert cost == round(3.00 + 15.00, 6)
