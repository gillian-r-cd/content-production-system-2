# backend/main.py
# 功能: FastAPI应用入口，含启动时自动同步评估模板和种子数据
# 主要函数: create_app(), _seed_default_data_on_startup(), _sync_eval_template_on_startup(), main()
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

import traceback

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel as _PydanticBase

from core.config import settings
from core.localization import DEFAULT_LOCALE, normalize_locale, resolve_eval_anchor_name


# ===== 统一错误响应模型 =====
class ErrorResponse(_PydanticBase):
    """统一 API 错误响应格式。"""
    error: str           # 机器可读的简短错误码或消息
    detail: str = ""     # 人类可读的详细描述（可选）
    status_code: int = 500


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


def _seed_default_data_on_startup():
    """
    启动时检查并填充预置数据（创作者特质、系统提示词、Agent 设置等）。
    复用 scripts/init_db.py 的 seed_default_data()，该函数是幂等的：
    每个表都先 count() == 0 再插入，已有数据不受影响。
    """
    try:
        from scripts.init_db import seed_default_data
        seed_default_data()
        logging.getLogger("startup").info("预置数据校验完成")
    except Exception as e:
        logging.getLogger("startup").warning(
            f"启动时填充预置数据失败（不影响运行）: {e}"
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
            FieldTemplate.stable_key == "eval_template_v2",
            FieldTemplate.locale == DEFAULT_LOCALE,
        ).first()

        # 兼容历史脏数据：某些环境中模板名可能异常，但 special_handler 组合仍可识别
        if not existing:
            expected_handlers = sorted(
                f.get("special_handler", "") for f in EVAL_TEMPLATE_V2_FIELDS
            )
            all_templates = db.query(FieldTemplate).all()
            for t in all_templates:
                if normalize_locale(getattr(t, "locale", DEFAULT_LOCALE)) == "ja-JP":
                    continue
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
                or getattr(existing, "stable_key", "") != "eval_template_v2"
                or normalize_locale(getattr(existing, "locale", DEFAULT_LOCALE)) != DEFAULT_LOCALE
            )
            if needs_update:
                existing.fields = EVAL_TEMPLATE_V2_FIELDS
                existing.description = EVAL_TEMPLATE_V2_DESCRIPTION
                existing.category = EVAL_TEMPLATE_V2_CATEGORY
                existing.name = EVAL_TEMPLATE_V2_NAME
                existing.stable_key = "eval_template_v2"
                existing.locale = DEFAULT_LOCALE
                db.commit()
                logging.getLogger("startup").info(
                    "综合评估模板已自动更新为最新 V2 版本"
                )
        else:
            # 启动自愈：不存在时直接创建，避免环境未执行 init_db 导致缺模板
            db.add(
                FieldTemplate(
                    name=EVAL_TEMPLATE_V2_NAME,
                    stable_key="eval_template_v2",
                    locale=DEFAULT_LOCALE,
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


def _sync_eval_presets_on_startup():
    """启动时同步 Eval 预置评分器与模拟器，避免 live 服务缺失 locale 资产。"""
    from core.database import get_session_maker
    from api.settings import _sync_preset_graders, _sync_preset_simulators

    db = None
    try:
        SessionLocal = get_session_maker()
        db = SessionLocal()
        imported_graders, updated_graders = _sync_preset_graders(db)
        imported_simulators, updated_simulators = _sync_preset_simulators(db)
        db.commit()
        logging.getLogger("startup").info(
            "已同步 Eval 预置: "
            f"graders imported={imported_graders} updated={updated_graders}, "
            f"simulators imported={imported_simulators} updated={updated_simulators}"
        )
        db.close()
    except Exception as e:
        logging.getLogger("startup").warning(
            f"启动时同步 Eval 预置失败（不影响运行）: {e}"
        )
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


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
            is_localized_eval_template = getattr(t, "stable_key", "") == "eval_template_v2"
            if (has_eval_handler or name_hit) and not is_localized_eval_template:
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
    from core.models import ContentBlock, Project

    target_handlers = ["eval_persona_setup", "eval_task_config", "eval_report"]

    try:
        SessionLocal = get_session_maker()
        db = SessionLocal()
        blocks = db.query(ContentBlock).filter(
            ContentBlock.special_handler.in_(target_handlers)
        ).all()
        project_locale_map = {
            project.id: normalize_locale(getattr(project, "locale", DEFAULT_LOCALE))
            for project in db.query(Project).all()
        }

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
            expected_name = resolve_eval_anchor_name(handler, project_locale_map.get(_pid, DEFAULT_LOCALE))
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


def _heal_stale_running_tasks_on_startup():
    """
    启动时将所有卡在 running 状态的 EvalTask 重置为 failed。
    进程内存态（_TASK_RUNTIME_STATE）在重启后丢失，
    若 DB 仍显示 running 会导致 pause/stop/resume 接口报"任务未运行"。
    """
    try:
        from core.database import get_session_maker
        from core.models import EvalTaskV2
        Session = get_session_maker()
        db = Session()
        stale = db.query(EvalTaskV2).filter(EvalTaskV2.status == "running").all()
        for t in stale:
            t.status = "failed"
            if not (t.last_error or "").strip():
                t.last_error = "执行状态丢失（服务重启或任务中断），请重新执行。"
        if stale:
            db.commit()
            logging.getLogger("startup").info(
                "启动时重置 %d 个 stale running EvalTask 为 failed", len(stale)
            )
        db.close()
    except Exception as e:
        logging.getLogger("startup").warning(
            "启动时清理 stale running tasks 失败（不影响运行）: %s", e
        )


def _check_llm_config_on_startup():
    """
    启动时检查 LLM 配置，在日志中给出明确警告。
    不阻止启动（允许先启动再配置），但让用户立刻看到问题。
    """
    import os
    startup_logger = logging.getLogger("startup")

    # 检查 .env 文件是否存在
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        startup_logger.warning(
            "⚠️  未找到 .env 文件（当前目录: %s）。"
            "请确保在 backend/ 目录下启动，或将 .env 放到 %s",
            os.getcwd(), env_path,
        )

    from core.config import validate_llm_config
    config_error = validate_llm_config()
    if config_error:
        startup_logger.warning("⚠️  LLM 配置问题: %s", config_error)
        startup_logger.warning(
            "⚠️  AI 生成功能将不可用，请先正确配置 backend/.env 中的 API Key。"
        )
    else:
        provider = (settings.llm_provider or "openai").lower().strip()
        startup_logger.info("✅ LLM 配置检查通过 (provider: %s)", provider)


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
            "http://127.0.0.1:3001",  # 备用端口（127.0.0.1）
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],  # 允许前端访问所有响应头
    )

    # ===== 统一异常处理 =====
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """将 HTTPException 转为统一格式的 JSON 响应。"""
        detail = exc.detail or ""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": str(detail)[:500] if isinstance(detail, str) else str(detail)[:500],
                "detail": str(detail),
                "status_code": exc.status_code,
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """捕获未处理的通用异常，返回统一格式，避免泄露内部堆栈。"""
        _generic_logger = logging.getLogger("error_handler")
        _generic_logger.error(
            "未处理异常 [%s %s]: %s\n%s",
            request.method, request.url.path,
            exc, traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                "detail": "服务器内部错误，请稍后重试。",
                "status_code": 500,
            },
        )

    # 健康检查
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "message": "Content Production System is running"}

    # 注册路由
    from api import projects, fields, agent, settings as settings_api, simulation
    from api import blocks, phase_templates, project_structure_drafts, versions
    from api import eval as eval_api
    from api import graders as graders_api
    from api import modes as modes_api
    from api import memories as memories_api
    from api import models as models_api
    
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])          # → /api/projects
    app.include_router(fields.router, prefix="/api/fields", tags=["fields"])                # → /api/fields  [已废弃] P0-1: 统一使用 blocks.router，保留兼容
    app.include_router(agent.router, prefix="/api/agent", tags=["agent"])                   # → /api/agent
    app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])      # → /api/settings
    app.include_router(simulation.router, prefix="/api/simulations", tags=["simulations"])  # → /api/simulations

    # 新架构：内容块和阶段模板
    app.include_router(blocks.router)                   # → /api/blocks          (prefix 在 blocks.py 中定义)
    app.include_router(phase_templates.router)          # → /api/phase-templates (prefix 在 phase_templates.py 中定义)
    app.include_router(project_structure_drafts.router) # → /api/project-structure-drafts (prefix 在 project_structure_drafts.py 中定义)

    # 新 Eval 体系
    app.include_router(eval_api.router)     # → /api/eval     (prefix 在 eval.py 中定义)

    # Grader 评分器管理
    app.include_router(graders_api.router)  # → /api/graders  (prefix 在 graders.py 中定义)

    # 版本历史
    app.include_router(versions.router)     # → /api/versions (prefix 在 versions.py 中定义)

    # Agent 模式管理
    app.include_router(modes_api.router)    # → /api/modes    (prefix 在 modes.py 中定义)

    # 项目记忆管理
    app.include_router(memories_api.router) # → /api/memories (prefix 在 memories.py 中定义)

    # 可用模型列表
    app.include_router(models_api.router)   # → /api/models   (prefix 在 models.py 中定义)

    # 启动时确保数据库就绪：schema -> 种子数据 -> 评估模板同步 -> 清理
    @app.on_event("startup")
    def on_startup():
        _ensure_db_schema_on_startup()
        _seed_default_data_on_startup()
        _sync_eval_template_on_startup()
        _sync_eval_presets_on_startup()
        _cleanup_legacy_eval_templates_on_startup()
        _dedupe_eval_anchor_blocks_on_startup()
        _heal_stale_running_tasks_on_startup()
        # ===== 启动时校验 LLM 配置，提前暴露 .env 问题 =====
        _check_llm_config_on_startup()

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.backend_port,
        reload=settings.debug,
    )

