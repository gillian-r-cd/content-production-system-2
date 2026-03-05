# backend/core/config.py
# 功能: 应用配置管理，从环境变量加载配置
# 主要类: Settings
# 数据结构: Settings(BaseSettings)

"""
配置管理模块
使用 pydantic-settings 从 .env 文件加载配置
"""

from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""

    # LLM Provider: "openai" | "anthropic" | "google"
    llm_provider: str = "openai"

    # OpenAI
    openai_api_key: str = ""
    openai_org_id: str = ""
    openai_model: str = "gpt-5.1"
    openai_mini_model: str = "gpt-4o-mini"
    openai_api_base: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-6"
    anthropic_mini_model: str = "claude-sonnet-4-6"

    # Google (Gemini)
    google_api_key: str = ""
    google_model: str = "gemini-3.1-pro-preview"
    google_mini_model: str = "gemini-3-flash-preview"
    google_thinking_budget: int = -1  # Gemini 3.x thinking token 预算。-1=模型默认，0=关闭思考（更快首token）

    # LLM 超时（秒）— 思考模型（Gemini 3.1 等）建议 300+
    llm_timeout: int = 300

    # Tavily Search API (DeepResearch)
    tavily_api_key: str = ""

    # Database
    database_url: str = "sqlite:///./data/content_production.db"

    # Server
    backend_port: int = 8000
    debug: bool = True

    # Eval V2
    eval_max_parallel_trials: int = 8

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()


# ============== API Key 校验工具 ==============

_PLACEHOLDER_KEYS = {"sk-xxxx", "sk-ant-xxxx", "AIzaSy-xxxx", "", "xxxx"}


def validate_llm_config() -> Optional[str]:
    """
    校验当前 LLM 配置是否可用。

    Returns:
        None  — 配置正常
        str   — 人类可读的错误说明（可直接发给前端）
    """
    provider = (settings.llm_provider or "openai").lower().strip()

    if provider == "anthropic":
        key = (settings.anthropic_api_key or "").strip()
        if not key or key in _PLACEHOLDER_KEYS:
            return (
                f"Anthropic API Key 未配置。"
                f"请编辑 backend/.env，将 ANTHROPIC_API_KEY 设为真实密钥"
                f"（当前值: '{key or '(空)'}' ）。"
            )
    elif provider == "google":
        key = (settings.google_api_key or "").strip()
        if not key or key in _PLACEHOLDER_KEYS:
            return (
                f"Google API Key 未配置。"
                f"请编辑 backend/.env，将 GOOGLE_API_KEY 设为真实密钥"
                f"（当前值: '{key or '(空)'}' ）。"
            )
    else:
        key = (settings.openai_api_key or "").strip()
        if not key or key in _PLACEHOLDER_KEYS:
            return (
                f"OpenAI API Key 未配置。"
                f"请编辑 backend/.env，将 OPENAI_API_KEY 设为真实密钥"
                f"（当前值: '{key or '(空)'}' ）。"
            )

    return None

