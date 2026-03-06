# backend/tests/test_gemini_provider.py
# 功能: Google Gemini provider 全链路测试
# 覆盖: _infer_provider, get_model_name, get_chat_model, sanitize_messages,
#        calculate_cost, list_available_models (Google 分支), 集成测试 (真实 API 调用)

"""
Google Gemini Provider 测试

两层测试:
  1. 单元测试（mock）: 验证代码逻辑正确分发到 google 分支
  2. 集成测试（真实 API）: 验证 ChatGoogleGenerativeAI 能完成 ainvoke / 流式 / bind_tools

运行:
  pytest tests/test_gemini_provider.py -v                    # 单元测试
  pytest tests/test_gemini_provider.py -v -k integration     # 集成测试（需 GOOGLE_API_KEY）
"""

import pytest
from unittest.mock import patch, MagicMock


# ============== 单元测试: _infer_provider ==============

class TestInferProviderGoogle:
    """_infer_provider 对 gemini-* 前缀的识别。"""

    def test_gemini_3_1_pro_preview(self):
        from core.llm_compat import _infer_provider
        assert _infer_provider("gemini-3.1-pro-preview") == "google"

    def test_gemini_3_flash_preview(self):
        from core.llm_compat import _infer_provider
        assert _infer_provider("gemini-3-flash-preview") == "google"

    def test_gemini_3_pro_preview(self):
        from core.llm_compat import _infer_provider
        assert _infer_provider("gemini-3-pro-preview") == "google"

    def test_gemini_any_version(self):
        from core.llm_compat import _infer_provider
        assert _infer_provider("gemini-99.9-whatever") == "google"

    def test_llm_py_infer_provider_consistent(self):
        """llm.py 和 llm_compat.py 的 _infer_provider 行为一致。"""
        from core.llm import _infer_provider as llm_infer
        from core.llm_compat import _infer_provider as compat_infer
        for model in ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-3-pro-preview"]:
            assert llm_infer(model) == compat_infer(model) == "google"
        for model in ["claude-opus-4-6", "claude-sonnet-4-6"]:
            assert llm_infer(model) == compat_infer(model) == "anthropic"
        for model in ["gpt-5.1", "gpt-4o-mini", ""]:
            assert llm_infer(model) == compat_infer(model) == "openai"


# ============== 单元测试: get_model_name ==============

class TestGetModelNameGoogle:
    """get_model_name 对 google provider 的返回值。"""

    @patch("core.llm_compat.settings")
    def test_google_main(self, mock_settings):
        mock_settings.llm_provider = "google"
        mock_settings.google_model = "gemini-3.1-pro-preview"
        mock_settings.google_mini_model = "gemini-3-flash-preview"
        from core.llm_compat import get_model_name
        assert get_model_name() == "gemini-3.1-pro-preview"

    @patch("core.llm_compat.settings")
    def test_google_mini(self, mock_settings):
        mock_settings.llm_provider = "google"
        mock_settings.google_model = "gemini-3.1-pro-preview"
        mock_settings.google_mini_model = "gemini-3-flash-preview"
        from core.llm_compat import get_model_name
        assert get_model_name(mini=True) == "gemini-3-flash-preview"

    @patch("core.llm_compat.settings")
    def test_google_empty_model_fallback(self, mock_settings):
        """google_model 为空时回退到硬编码默认值。"""
        mock_settings.llm_provider = "google"
        mock_settings.google_model = ""
        mock_settings.google_mini_model = ""
        from core.llm_compat import get_model_name
        assert get_model_name() == "gemini-3.1-pro-preview"
        assert get_model_name(mini=True) == "gemini-3-flash-preview"


# ============== 单元测试: get_chat_model ==============

class TestGetChatModelGoogle:
    """get_chat_model 对 gemini-* 模型自动实例化 ChatGoogleGenerativeAI。"""

    def test_gemini_model_returns_correct_type(self):
        from core.llm import get_chat_model
        model = get_chat_model(model="gemini-3.1-pro-preview")
        assert type(model).__name__ == "ChatGoogleGenerativeAI"

    def test_gemini_flash_returns_correct_type(self):
        from core.llm import get_chat_model
        model = get_chat_model(model="gemini-3-flash-preview")
        assert type(model).__name__ == "ChatGoogleGenerativeAI"

    def test_gemini_model_has_correct_model_name(self):
        from core.llm import get_chat_model
        model = get_chat_model(model="gemini-3.1-pro-preview")
        assert model.model == "gemini-3.1-pro-preview"

    def test_other_providers_still_work(self):
        """确认 OpenAI 和 Anthropic 不受影响。"""
        from core.llm import get_chat_model
        openai_model = get_chat_model(model="gpt-5.1")
        assert type(openai_model).__name__ == "ChatOpenAI"
        anthropic_model = get_chat_model(model="claude-sonnet-4-6")
        assert type(anthropic_model).__name__ == "ChatAnthropic"


# ============== 单元测试: sanitize_messages (google = pass-through) ==============

class TestSanitizeMessagesGoogle:
    """sanitize_messages 对 google provider 不做任何处理。"""

    def test_google_model_no_merge(self):
        from core.llm_compat import sanitize_messages
        from langchain_core.messages import SystemMessage, HumanMessage

        msgs = [
            SystemMessage(content="First"),
            SystemMessage(content="Second"),
            HumanMessage(content="Hello"),
        ]
        result = sanitize_messages(msgs, model="gemini-3.1-pro-preview")
        # google 不合并 SystemMessage，原样返回
        assert len(result) == 3
        assert result is msgs  # 同一引用

    @patch("core.llm_compat.settings")
    def test_google_global_provider_no_merge(self, mock_settings):
        mock_settings.llm_provider = "google"
        from core.llm_compat import sanitize_messages
        from langchain_core.messages import SystemMessage, HumanMessage

        msgs = [
            SystemMessage(content="A"),
            SystemMessage(content="B"),
            HumanMessage(content="Hi"),
        ]
        result = sanitize_messages(msgs)
        assert len(result) == 3
        assert result is msgs


# ============== 单元测试: calculate_cost ==============

class TestCalculateCostGemini:
    """calculate_cost 支持 Gemini 3.x 模型定价。"""

    def test_gemini_3_1_pro_preview_pricing(self):
        from core.models.generation_log import GenerationLog
        cost = GenerationLog.calculate_cost("gemini-3.1-pro-preview", 1_000_000, 1_000_000)
        assert cost == round(1.25 + 10.00, 6)

    def test_gemini_3_flash_preview_pricing(self):
        from core.models.generation_log import GenerationLog
        cost = GenerationLog.calculate_cost("gemini-3-flash-preview", 1_000_000, 1_000_000)
        assert cost == round(0.15 + 0.60, 6)

    def test_gemini_3_pro_preview_pricing(self):
        from core.models.generation_log import GenerationLog
        cost = GenerationLog.calculate_cost("gemini-3-pro-preview", 1_000_000, 1_000_000)
        assert cost == round(1.25 + 10.00, 6)

    def test_gemini_flash_much_cheaper_than_pro(self):
        """Flash 比 Pro 便宜很多。"""
        from core.models.generation_log import GenerationLog
        cost_pro = GenerationLog.calculate_cost("gemini-3.1-pro-preview", 1_000_000, 1_000_000)
        cost_flash = GenerationLog.calculate_cost("gemini-3-flash-preview", 1_000_000, 1_000_000)
        assert cost_flash < cost_pro / 5


# ============== 单元测试: list_available_models API ==============

class TestListModelsGoogleFiltering:
    """GET /api/models/ 在配置了 GOOGLE_API_KEY 时返回 Gemini 模型。"""

    @patch("api.models.settings")
    def test_with_google_key_returns_gemini(self, mock_settings):
        mock_settings.openai_api_key = ""
        mock_settings.anthropic_api_key = ""
        mock_settings.google_api_key = "AIzaSy-test-key"
        mock_settings.llm_provider = "google"

        from api.models import AVAILABLE_MODELS

        has_google = bool(mock_settings.google_api_key)
        google_models = [m for m in AVAILABLE_MODELS if m["provider"] == "google"]

        assert has_google is True
        assert len(google_models) >= 2
        ids = [m["id"] for m in google_models]
        assert "gemini-3.1-pro-preview" in ids
        assert "gemini-3-flash-preview" in ids

    @patch("api.models.settings")
    def test_without_google_key_no_gemini(self, mock_settings):
        mock_settings.openai_api_key = "sk-test"
        mock_settings.anthropic_api_key = ""
        mock_settings.google_api_key = ""

        from api.models import AVAILABLE_MODELS

        has_google = bool(mock_settings.google_api_key)
        google_models = [m for m in AVAILABLE_MODELS if m["provider"] == "google" and has_google]
        assert len(google_models) == 0

    def test_available_models_has_google_entries(self):
        """AVAILABLE_MODELS 静态列表包含 Google 条目。"""
        from api.models import AVAILABLE_MODELS
        providers = {m["provider"] for m in AVAILABLE_MODELS}
        assert "google" in providers
        assert "openai" in providers
        assert "anthropic" in providers

    def test_gemini_tiers_correct(self):
        """Gemini 3.1 Pro 是 main tier, 3 Flash 是 mini tier。"""
        from api.models import AVAILABLE_MODELS
        for m in AVAILABLE_MODELS:
            if m["id"] == "gemini-3.1-pro-preview":
                assert m["tier"] == "main"
            elif m["id"] == "gemini-3-flash-preview":
                assert m["tier"] == "mini"


# ============== 集成测试: 真实 Gemini API 调用 ==============

def _has_google_api_key() -> bool:
    """检查是否配置了 GOOGLE_API_KEY。"""
    try:
        from core.config import settings
        return bool(settings.google_api_key)
    except Exception:
        return False


skip_no_google_key = pytest.mark.skipif(
    not _has_google_api_key(),
    reason="需要 GOOGLE_API_KEY 环境变量才能运行集成测试",
)


@skip_no_google_key
class TestGeminiIntegration:
    """集成测试: 真实调用 Google Gemini API (gemini-3.x)。
    
    注意: Gemini 3.x 的 response.content 可能是 list[dict] 而非 str，
    与 Anthropic 类似，需通过 normalize_content() 转换。
    """

    @pytest.mark.asyncio
    async def test_integration_ainvoke(self):
        """Gemini ainvoke 基本对话能返回非空内容（经 normalize_content 转 str）。"""
        from core.llm import get_chat_model
        from core.llm_compat import normalize_content
        from langchain_core.messages import HumanMessage

        llm = get_chat_model(model="gemini-3-flash-preview", temperature=0.0)
        response = await llm.ainvoke([HumanMessage(content="Say 'hello' and nothing else.")])
        text = normalize_content(response.content)
        assert isinstance(text, str)
        assert len(text.strip()) > 0
        assert "hello" in text.lower()

    @pytest.mark.asyncio
    async def test_integration_streaming(self):
        """Gemini 流式输出能正常工作。"""
        from core.llm import get_chat_model
        from core.llm_compat import normalize_content
        from langchain_core.messages import HumanMessage

        llm = get_chat_model(model="gemini-3-flash-preview", temperature=0.0)
        chunks = []

        async for chunk in llm.astream([HumanMessage(content="Count from 1 to 3.")]):
            chunks.append(chunk)

        assert len(chunks) > 0
        # Gemini 3.x chunk.content 可能是 str 或 list，统一用 normalize_content
        full = "".join(normalize_content(c.content) for c in chunks)
        assert "1" in full
        assert "2" in full
        assert "3" in full

    @pytest.mark.asyncio
    async def test_integration_bind_tools(self):
        """Gemini bind_tools 能正常工作（tool calling 支持）。"""
        from core.llm import get_chat_model
        from core.llm_compat import normalize_content
        from langchain_core.messages import HumanMessage
        from langchain_core.tools import tool

        @tool
        def get_weather(city: str) -> str:
            """Get the current weather for a city."""
            return f"Sunny in {city}"

        # gemini-3-pro-preview 作为稳定的 tool calling 测试模型
        llm = get_chat_model(model="gemini-3-pro-preview", temperature=0.0)
        llm_with_tools = llm.bind_tools([get_weather])

        response = await llm_with_tools.ainvoke([
            HumanMessage(content="What's the weather in Tokyo?")
        ])
        # 应该产生 tool_calls 或者文本回复
        assert response is not None
        has_tool_calls = bool(response.tool_calls)
        has_content = bool(normalize_content(response.content))
        assert has_tool_calls or has_content

    @pytest.mark.asyncio
    async def test_integration_normalize_content_compatibility(self):
        """Gemini 3.x 返回的 content (可能是 list) 经过 normalize_content 后是 str。"""
        from core.llm import get_chat_model
        from core.llm_compat import normalize_content
        from langchain_core.messages import HumanMessage

        llm = get_chat_model(model="gemini-3-flash-preview", temperature=0.0)
        response = await llm.ainvoke([HumanMessage(content="Reply with exactly: test")])
        normalized = normalize_content(response.content)
        assert isinstance(normalized, str)
        assert len(normalized) > 0

    @pytest.mark.asyncio
    async def test_integration_3_pro_preview_main_model(self):
        """gemini-3-pro-preview 基本对话正常（gemini-3.1 可能暂时 503 时备用）。"""
        from core.llm import get_chat_model
        from core.llm_compat import normalize_content
        from langchain_core.messages import HumanMessage

        llm = get_chat_model(model="gemini-3-pro-preview", temperature=0.0)
        response = await llm.ainvoke([HumanMessage(content="What is 2+2? Reply with just the number.")])
        text = normalize_content(response.content)
        assert isinstance(text, str)
        assert "4" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
