# backend/main.py
# 功能: FastAPI应用入口
# 主要函数: create_app(), main()
# 数据结构: 无

"""
Content Production System - Backend Entry Point
启动命令: python main.py
"""

import sys
import os
import logging

# ===== 关键：Windows 下强制 UTF-8 输出，防止中文 print 导致后台任务崩溃 =====
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings


# ===== 日志配置 =====
def _setup_logging():
    """配置应用日志，确保 agent/orchestrator/agent_tools 日志可见"""
    log_level = logging.DEBUG if settings.debug else logging.INFO
    fmt = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"
    datefmt = "%H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    # 为关键模块设置日志级别
    for name in ("agent", "orchestrator", "agent_tools"):
        lg = logging.getLogger(name)
        lg.setLevel(log_level)
        if not lg.handlers:
            lg.addHandler(handler)
        lg.propagate = False  # 避免重复输出

    # root logger 保持 INFO（避免 SQLAlchemy 等噪音）
    logging.basicConfig(level=logging.INFO, format=fmt, datefmt=datefmt)


_setup_logging()


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
    from api import blocks, phase_templates, versions
    from api import eval as eval_api
    from api import graders as graders_api
    
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(fields.router, prefix="/api/fields", tags=["fields"])  # [已废弃] P0-1: 统一使用 blocks.router，保留兼容
    app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
    app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
    app.include_router(simulation.router, prefix="/api/simulations", tags=["simulations"])
    # ⚠️ DEPRECATED: 旧评估系统（EvaluationTemplate/EvaluationReport），前端已改用 /api/eval（EvalRun/EvalTask/EvalTrial）
    app.include_router(evaluation.router, prefix="/api/evaluations", tags=["evaluations"])
    
    # 新架构：内容块和阶段模板
    app.include_router(blocks.router)  # 路由前缀已在 blocks.py 中定义
    app.include_router(phase_templates.router)  # 路由前缀已在 phase_templates.py 中定义
    
    # 新 Eval 体系
    app.include_router(eval_api.router)  # 路由前缀已在 eval.py 中定义
    
    # Grader 评分器管理
    app.include_router(graders_api.router)
    
    # 版本历史
    app.include_router(versions.router)

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.backend_port,
        reload=settings.debug,
    )

