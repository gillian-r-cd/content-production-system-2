# backend/main.py
# 功能: FastAPI应用入口
# 主要函数: create_app(), main()
# 数据结构: 无

"""
Content Production System - Backend Entry Point
启动命令: python main.py
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings


def create_app() -> FastAPI:
    """创建FastAPI应用实例"""
    app = FastAPI(
        title="Content Production System",
        description="AI Agent 驱动的商业内容生产平台",
        version="0.1.0",
    )

    # CORS配置 - 允许前端访问
    # 注意：allow_origins 必须在 allow_credentials=True 时明确指定，不能用 ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",  # 备用端口
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],  # 允许前端访问所有响应头
    )

    # 健康检查
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "message": "Content Production System is running"}

    # 注册路由
    from api import projects, fields, agent, settings as settings_api, simulation, evaluation
    from api import blocks, phase_templates
    
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(fields.router, prefix="/api/fields", tags=["fields"])
    app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
    app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
    app.include_router(simulation.router, prefix="/api/simulations", tags=["simulations"])
    app.include_router(evaluation.router, prefix="/api/evaluations", tags=["evaluations"])
    
    # 新架构：内容块和阶段模板
    app.include_router(blocks.router)  # 路由前缀已在 blocks.py 中定义
    app.include_router(phase_templates.router)  # 路由前缀已在 phase_templates.py 中定义

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.backend_port,
        reload=settings.debug,
    )

