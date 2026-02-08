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

    # OpenAI
    openai_api_key: str = ""
    openai_org_id: str = ""
    openai_model: str = "gpt-5.1"
    openai_api_base: str = ""

    # Tavily Search API (DeepResearch)
    tavily_api_key: str = ""

    # Database
    database_url: str = "sqlite:///./data/content_production.db"

    # Server
    backend_port: int = 8000
    debug: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()

