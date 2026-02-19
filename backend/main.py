# backend/main.py
# 功能: FastAPI应用入口，含启动时自动同步评估模板
# 主要函数: create_app(), _sync_eval_template_on_startup(), main()
# 数据结构: 无

"""
Content Production System - Backend Entry Point
启动命令: python main.py
"""

import sys
import os
import logging
import json

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


def _ensure_db_schema_on_startup():
    """
    启动时确保数据库 schema 完整，避免新增表（如 Eval V2）在旧数据库中缺失。
    """
    try:
        from core.database import init_db
        init_db()
        logging.getLogger("startup").info("数据库 schema 校验完成")
    except Exception as e:
        logging.getLogger("startup").warning(
            f"启动时校验数据库 schema 失败（不影响运行）: {e}"
        )


def _sync_eval_template_on_startup():
    """
    启动时同步综合评估模板：若数据库中的版本过期则自动更新为 V2。
    使用 EVAL_TEMPLATE_V2 常量作为单一事实来源。
    """
    from core.database import get_session_maker
    from core.models import FieldTemplate
    from core.models.field_template import (
        EVAL_TEMPLATE_V2_NAME,
        EVAL_TEMPLATE_V2_DESCRIPTION,
        EVAL_TEMPLATE_V2_CATEGORY,
        EVAL_TEMPLATE_V2_FIELDS,
    )

    try:
        SessionLocal = get_session_maker()
        db = SessionLocal()
        existing = db.query(FieldTemplate).filter(
            FieldTemplate.name == EVAL_TEMPLATE_V2_NAME
        ).first()

        # 兼容历史脏数据：某些环境中模板名可能异常，但 special_handler 组合仍可识别
        if not existing:
            expected_handlers = sorted(
                f.get("special_handler", "") for f in EVAL_TEMPLATE_V2_FIELDS
            )
            all_templates = db.query(FieldTemplate).all()
            for t in all_templates:
                handlers = sorted(
                    f.get("special_handler", "") for f in (t.fields or [])
                )
                if handlers == expected_handlers:
                    existing = t
                    break

        expected_fields_json = json.dumps(
            EVAL_TEMPLATE_V2_FIELDS, ensure_ascii=False, sort_keys=True
        )

        if existing:
            existing_fields_json = json.dumps(
                existing.fields or [], ensure_ascii=False, sort_keys=True
            )
            needs_update = (
                existing_fields_json != expected_fields_json
                or existing.description != EVAL_TEMPLATE_V2_DESCRIPTION
                or existing.category != EVAL_TEMPLATE_V2_CATEGORY
                or existing.name != EVAL_TEMPLATE_V2_NAME
            )
            if needs_update:
                existing.fields = EVAL_TEMPLATE_V2_FIELDS
                existing.description = EVAL_TEMPLATE_V2_DESCRIPTION
                existing.category = EVAL_TEMPLATE_V2_CATEGORY
                existing.name = EVAL_TEMPLATE_V2_NAME
                db.commit()
                logging.getLogger("startup").info(
                    "综合评估模板已自动更新为最新 V2 版本"
                )
        else:
            # 启动自愈：不存在时直接创建，避免环境未执行 init_db 导致缺模板
            db.add(
                FieldTemplate(
                    name=EVAL_TEMPLATE_V2_NAME,
                    description=EVAL_TEMPLATE_V2_DESCRIPTION,
                    category=EVAL_TEMPLATE_V2_CATEGORY,
                    fields=EVAL_TEMPLATE_V2_FIELDS,
                )
            )
            db.commit()
            logging.getLogger("startup").info("综合评估模板不存在，已自动创建 V2 版本")

        db.close()
    except Exception as e:
        logging.getLogger("startup").warning(
            f"启动时同步评估模板失败（不影响运行）: {e}"
        )


def _cleanup_legacy_eval_templates_on_startup():
    """
    清理历史 Eval 模板，仅保留唯一的 Eval V2 综合评估模板。
    用户已确认无需迁移旧 Eval 模板数据。
    """
    from core.database import get_session_maker
    from core.models import FieldTemplate
    from core.models.field_template import EVAL_TEMPLATE_V2_NAME

    try:
        SessionLocal = get_session_maker()
        db = SessionLocal()
        templates = db.query(FieldTemplate).all()
        removed = 0
        for t in templates:
            handlers = [f.get("special_handler", "") for f in (t.fields or [])]
            has_eval_handler = any(
                h in {"eval_persona_setup", "eval_task_config", "eval_report", "evaluate", "eval"}
                for h in handlers
            )
            name_hit = "评估" in (t.name or "")
            if (has_eval_handler or name_hit) and t.name != EVAL_TEMPLATE_V2_NAME:
                db.delete(t)
                removed += 1

        if removed > 0:
            db.commit()
            logging.getLogger("startup").info(
                f"已清理 {removed} 个历史 Eval 模板，仅保留综合评估模板"
            )
        db.close()
    except Exception as e:
        logging.getLogger("startup").warning(
            f"启动时清理历史 Eval 模板失败（不影响运行）: {e}"
        )


def _dedupe_eval_anchor_blocks_on_startup():
    """
    按 project_id + special_handler 去重 Eval 三个锚点块，
    避免历史重复块导致前端随机命中旧块/乱码块。
    """
    from core.database import get_session_maker
    from core.models import ContentBlock

    target_handlers = ["eval_persona_setup", "eval_task_config", "eval_report"]
    canonical_names = {
        "eval_persona_setup": "人物画像设置",
        "eval_task_config": "评估任务配置",
        "eval_report": "评估报告",
    }

    try:
        SessionLocal = get_session_maker()
        db = SessionLocal()
        blocks = db.query(ContentBlock).filter(
            ContentBlock.special_handler.in_(target_handlers)
        ).all()

        grouped: dict[tuple[str, str], list[ContentBlock]] = {}
        for b in blocks:
            key = (b.project_id, b.special_handler)
            grouped.setdefault(key, []).append(b)

        removed = 0
        renamed = 0
        for (_pid, handler), items in grouped.items():
            if len(items) == 0:
                continue

            # 优先保留有内容且更新更晚的块，减少数据丢失风险
            items_sorted = sorted(
                items,
                key=lambda x: (
                    1 if (x.content and x.content.strip()) else 0,
                    x.updated_at or x.created_at,
                ),
                reverse=True,
            )
            keep = items_sorted[0]
            expected_name = canonical_names.get(handler, keep.name)
            if keep.name != expected_name:
                keep.name = expected_name
                renamed += 1

            for extra in items_sorted[1:]:
                db.delete(extra)
                removed += 1

        if removed > 0 or renamed > 0:
            db.commit()
            logging.getLogger("startup").info(
                f"已完成 Eval 锚点块去重：删除 {removed} 个重复块，规范命名 {renamed} 个"
            )
        db.close()
    except Exception as e:
        logging.getLogger("startup").warning(
            f"启动时去重 Eval 锚点块失败（不影响运行）: {e}"
        )


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
    from api import projects, fields, agent, settings as settings_api, simulation
    from api import blocks, phase_templates, versions
    from api import eval as eval_api
    from api import graders as graders_api
    from api import modes as modes_api
    from api import memories as memories_api
    
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(fields.router, prefix="/api/fields", tags=["fields"])  # [已废弃] P0-1: 统一使用 blocks.router，保留兼容
    app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
    app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
    app.include_router(simulation.router, prefix="/api/simulations", tags=["simulations"])
    
    # 新架构：内容块和阶段模板
    app.include_router(blocks.router)  # 路由前缀已在 blocks.py 中定义
    app.include_router(phase_templates.router)  # 路由前缀已在 phase_templates.py 中定义
    
    # 新 Eval 体系
    app.include_router(eval_api.router)  # 路由前缀已在 eval.py 中定义
    
    # Grader 评分器管理
    app.include_router(graders_api.router)
    
    # 版本历史
    app.include_router(versions.router)
    
    # Agent 模式管理
    app.include_router(modes_api.router)
    
    # 项目记忆管理
    app.include_router(memories_api.router)

    # 启动时同步评估模板
    @app.on_event("startup")
    def on_startup():
        _ensure_db_schema_on_startup()
        _sync_eval_template_on_startup()
        _cleanup_legacy_eval_templates_on_startup()
        _dedupe_eval_anchor_blocks_on_startup()

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.backend_port,
        reload=settings.debug,
    )

