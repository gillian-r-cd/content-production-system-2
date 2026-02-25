# backend/tests/test_llm_compat.py
# 功能: llm_compat 工具模块的单元测试
# 覆盖: normalize_content, get_stop_reason, get_model_name, sanitize_messages

"""
测试 LLM Provider 兼容层的所有工具函数。
"""

import pytest
from unittest.mock import MagicMock, patch

from core.llm_compat import (
    normalize_content,
    get_stop_reason,
    get_model_name,
    sanitize_messages,
)
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


# ============== normalize_content ==============

class TestNormalizeContent:
    """测试 content 归一化。"""

    def test_str_passthrough(self):
        """str 输入原样返回。"""
        assert normalize_content("hello world") == "hello world"

    def test_str_empty(self):
        """空字符串原样返回。"""
        assert normalize_content("") == ""

    def test_list_text_blocks(self):
        """Anthropic 风格的 text 块列表正确拼接。"""
        blocks = [
            {"type": "text", "text": "hello "},
            {"type": "text", "text": "world"},
        ]
        assert normalize_content(blocks) == "hello world"

    def test_list_mixed_blocks(self):
        """混合块（text + tool_use）只提取 text。"""
        blocks = [
            {"type": "text", "text": "let me check"},
            {"type": "tool_use", "id": "abc", "name": "read_field", "input": {}},
        ]
        assert normalize_content(blocks) == "let me check"

    def test_list_str_elements(self):
        """list 内是 str 元素（非 dict）。"""
        assert normalize_content(["a", "b", "c"]) == "abc"

    def test_list_empty(self):
        """空 list 返回空字符串。"""
        assert normalize_content([]) == ""

    def test_none_returns_empty(self):
        """None 返回空字符串。"""
        assert normalize_content(None) == ""

    def test_int_converts_to_str(self):
        """非 str/list 类型安全转换。"""
        assert normalize_content(42) == "42"

    def test_list_tool_use_only(self):
        """纯 tool_use 块（无 text 键）返回空字符串。"""
        blocks = [
            {"type": "tool_use", "id": "abc", "name": "read_field", "input": {}},
        ]
        assert normalize_content(blocks) == ""


# ============== get_stop_reason ==============

class TestGetStopReason:
    """测试停止原因提取。"""

    def test_openai_stop(self):
        """OpenAI 正常停止。"""
        resp = MagicMock()
        resp.response_metadata = {"finish_reason": "stop"}
        reason, truncated = get_stop_reason(resp)
        assert reason == "stop"
        assert truncated is False

    def test_openai_length(self):
        """OpenAI 输出被截断。"""
        resp = MagicMock()
        resp.response_metadata = {"finish_reason": "length"}
        reason, truncated = get_stop_reason(resp)
        assert reason == "length"
        assert truncated is True

    def test_openai_tool_calls(self):
        """OpenAI 工具调用。"""
        resp = MagicMock()
        resp.response_metadata = {"finish_reason": "tool_calls"}
        reason, truncated = get_stop_reason(resp)
        assert reason == "tool_calls"
        assert truncated is False

    def test_anthropic_end_turn(self):
        """Anthropic 正常停止。"""
        resp = MagicMock()
        resp.response_metadata = {"stop_reason": "end_turn"}
        reason, truncated = get_stop_reason(resp)
        assert reason == "end_turn"
        assert truncated is False

    def test_anthropic_max_tokens(self):
        """Anthropic 输出被截断。"""
        resp = MagicMock()
        resp.response_metadata = {"stop_reason": "max_tokens"}
        reason, truncated = get_stop_reason(resp)
        assert reason == "max_tokens"
        assert truncated is True

    def test_anthropic_tool_use(self):
        """Anthropic 工具调用。"""
        resp = MagicMock()
        resp.response_metadata = {"stop_reason": "tool_use"}
        reason, truncated = get_stop_reason(resp)
        assert reason == "tool_use"
        assert truncated is False

    def test_no_metadata(self):
        """无 response_metadata 时回退到 "stop"。"""
        resp = MagicMock()
        resp.response_metadata = None
        reason, truncated = get_stop_reason(resp)
        assert reason == "stop"
        assert truncated is False

    def test_empty_metadata(self):
        """空 metadata 回退到 "stop"。"""
        resp = MagicMock()
        resp.response_metadata = {}
        reason, truncated = get_stop_reason(resp)
        assert reason == "stop"
        assert truncated is False


# ============== get_model_name ==============

class TestGetModelName:
    """测试模型名获取。"""

    @patch("core.llm_compat.settings")
    def test_openai_default(self, mock_settings):
        mock_settings.llm_provider = "openai"
        mock_settings.openai_model = "gpt-5.1"
        mock_settings.openai_mini_model = "gpt-4o-mini"
        assert get_model_name() == "gpt-5.1"

    @patch("core.llm_compat.settings")
    def test_openai_mini(self, mock_settings):
        mock_settings.llm_provider = "openai"
        mock_settings.openai_model = "gpt-5.1"
        mock_settings.openai_mini_model = "gpt-4o-mini"
        assert get_model_name(mini=True) == "gpt-4o-mini"

    @patch("core.llm_compat.settings")
    def test_anthropic_default(self, mock_settings):
        mock_settings.llm_provider = "anthropic"
        mock_settings.anthropic_model = "claude-opus-4-6"
        mock_settings.anthropic_mini_model = "claude-sonnet-4-6"
        assert get_model_name() == "claude-opus-4-6"

    @patch("core.llm_compat.settings")
    def test_anthropic_mini(self, mock_settings):
        mock_settings.llm_provider = "anthropic"
        mock_settings.anthropic_model = "claude-opus-4-6"
        mock_settings.anthropic_mini_model = "claude-sonnet-4-6"
        assert get_model_name(mini=True) == "claude-sonnet-4-6"

    @patch("core.llm_compat.settings")
    def test_empty_provider_defaults_to_openai(self, mock_settings):
        mock_settings.llm_provider = ""
        mock_settings.openai_model = "gpt-5.1"
        mock_settings.openai_mini_model = "gpt-4o-mini"
        assert get_model_name() == "gpt-5.1"


# ============== sanitize_messages ==============

class TestSanitizeMessages:
    """测试消息列表清理。"""

    @patch("core.llm_compat.settings")
    def test_openai_no_change(self, mock_settings):
        """OpenAI provider 不做任何处理。"""
        mock_settings.llm_provider = "openai"
        msgs = [
            SystemMessage(content="sys1"),
            HumanMessage(content="hi"),
            SystemMessage(content="sys2"),
        ]
        result = sanitize_messages(msgs)
        assert len(result) == 3
        assert result is msgs  # 同一引用，未处理

    @patch("core.llm_compat.settings")
    def test_anthropic_merge_system(self, mock_settings):
        """Anthropic provider 合并多条 SystemMessage。"""
        mock_settings.llm_provider = "anthropic"
        msgs = [
            SystemMessage(content="sys1"),
            HumanMessage(content="hi"),
            SystemMessage(content="sys2"),
            AIMessage(content="hello"),
        ]
        result = sanitize_messages(msgs)
        assert len(result) == 3  # 1 merged system + human + AI
        assert isinstance(result[0], SystemMessage)
        assert "sys1" in result[0].content
        assert "sys2" in result[0].content
        assert isinstance(result[1], HumanMessage)
        assert isinstance(result[2], AIMessage)

    @patch("core.llm_compat.settings")
    def test_anthropic_single_system_unchanged(self, mock_settings):
        """Anthropic 单条 SystemMessage 保持不变。"""
        mock_settings.llm_provider = "anthropic"
        msgs = [
            SystemMessage(content="only one"),
            HumanMessage(content="hi"),
        ]
        result = sanitize_messages(msgs)
        assert len(result) == 2
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "only one"

    @patch("core.llm_compat.settings")
    def test_anthropic_no_system(self, mock_settings):
        """Anthropic 无 SystemMessage 也正常。"""
        mock_settings.llm_provider = "anthropic"
        msgs = [
            HumanMessage(content="hi"),
            AIMessage(content="hello"),
        ]
        result = sanitize_messages(msgs)
        assert len(result) == 2

    @patch("core.llm_compat.settings")
    def test_anthropic_empty_system_skipped(self, mock_settings):
        """Anthropic 空内容的 SystemMessage 被跳过。"""
        mock_settings.llm_provider = "anthropic"
        msgs = [
            SystemMessage(content=""),
            SystemMessage(content="real content"),
            HumanMessage(content="hi"),
        ]
        result = sanitize_messages(msgs)
        assert len(result) == 2
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "real content"
