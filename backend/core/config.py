# backend/core/config.py
# 功能: 应用配置管理，从环境变量加载配置
# 主要类: Settings
# 数据结构: Settings(BaseSettings)

"""
配置管理模块
使用 pydantic-settings 从 .env 文件加载配置
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""

    # LLM Provider: "openai" | "anthropic"
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

