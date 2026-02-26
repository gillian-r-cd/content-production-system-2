# backend/api/models.py
# 功能: 可用 LLM 模型列表 API
# 主要路由: GET /api/models/ — 返回当前可用模型及用户默认配置
# 设计: 模型列表硬编码已验证模型，根据 API Key 是否配置动态过滤

"""
可用 LLM 模型列表 API

返回当前配置下可用的 LLM 模型清单及用户全局默认设置。
前端设置页和内容块编辑器的模型选择下拉依赖此端点。
"""

from fastapi import APIRouter

from core.config import settings
from core.llm_compat import resolve_model

router = APIRouter(prefix="/api/models", tags=["models"])


# 已验证可用的模型列表（2026-02-26 API 测试确认）
AVAILABLE_MODELS = [
    # OpenAI
    {"id": "gpt-5.1", "provider": "openai", "name": "GPT-5.1", "tier": "main"},
    {"id": "gpt-5.2", "provider": "openai", "name": "GPT-5.2", "tier": "main"},
    {"id": "gpt-4o-mini", "provider": "openai", "name": "GPT-4o Mini", "tier": "mini"},
    # Anthropic
    {"id": "claude-opus-4-6", "provider": "anthropic", "name": "Claude Opus 4.6", "tier": "main"},
    {"id": "claude-sonnet-4-6", "provider": "anthropic", "name": "Claude Sonnet 4.6", "tier": "main"},
    {"id": "claude-sonnet-4-5", "provider": "anthropic", "name": "Claude Sonnet 4.5", "tier": "mini"},
]


@router.get("/")
def list_available_models():
    """
    返回当前可用的 LLM 模型列表及用户默认配置。

    只返回已配置 API Key 的 provider 的模型。
    """
    models = []

    has_openai = bool(settings.openai_api_key)
    has_anthropic = bool(settings.anthropic_api_key)

    for m in AVAILABLE_MODELS:
        if m["provider"] == "openai" and has_openai:
            models.append(m)
        elif m["provider"] == "anthropic" and has_anthropic:
            models.append(m)

    return {
        "models": models,
        "current_default": {
            "main": resolve_model(),
            "mini": resolve_model(use_mini=True),
        },
        "env_provider": (settings.llm_provider or "openai").lower().strip(),
    }
