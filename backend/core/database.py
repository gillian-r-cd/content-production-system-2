# backend/core/database.py
# 功能: 数据库连接管理与轻量兼容迁移
# 主要函数: get_engine(), get_session_maker(), init_db(), ensure_compat_schema()
# 数据结构: Base (SQLAlchemy declarative base)

"""
数据库连接管理模块
使用 SQLAlchemy 2.0 异步模式
"""

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool

from core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    """为文件型 SQLite URL 预先创建父目录，避免隔离工作目录下首次启动直接失败。"""
    try:
        url = make_url(database_url)
    except Exception:
        return

    if not url.drivername.startswith("sqlite"):
        return

    database = url.database or ""
    if not database or database == ":memory:" or database.startswith("file:"):
        return

    Path(database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def get_engine():
    """
    获取数据库引擎
    SQLite使用StaticPool确保单连接（适合本地单用户）
    """
    # SQLite特殊配置
    connect_args = {"check_same_thread": False}
    _ensure_sqlite_parent_dir(settings.database_url)

    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        poolclass=StaticPool,
        echo=settings.debug,  # 调试模式打印SQL
    )
    return engine


def get_session_maker():
    """获取Session工厂"""
    engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """初始化数据库（创建所有表）"""
    engine = get_engine()
    # 导入所有模型以确保它们被注册
    from core.models import base  # noqa
    Base.metadata.create_all(bind=engine)
    ensure_compat_schema(engine)


def ensure_compat_schema(engine) -> None:
    """统一执行启动期/初始化脚本共用的轻量兼容迁移。"""
    _ensure_conversation_schema(engine)
    _ensure_agent_mode_schema(engine)
    _ensure_memory_schema(engine)
    _ensure_project_columns(engine)
    _ensure_content_block_columns(engine)
    _ensure_agent_settings_columns(engine)
    _ensure_field_template_columns(engine)
    _ensure_phase_template_columns(engine)
    _ensure_localized_asset_columns(engine)
    _backfill_compat_defaults(engine)


def _ensure_conversation_schema(engine) -> None:
    """
    兼容旧库补齐会话化字段。

    当前项目未引入 Alembic，启动时通过轻量 SQL 兼容迁移：
    1) 为 chat_messages 增加 conversation_id（若不存在）
    2) 为 conversations 增加 mode_id（若不存在）
    3) 创建 conversations 索引（若不存在）
    """
    with engine.begin() as conn:
        columns = conn.execute(text("PRAGMA table_info(chat_messages)")).fetchall()
        column_names = {row[1] for row in columns}
        if "conversation_id" not in column_names:
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN conversation_id VARCHAR(36)"))

        conv_columns = conn.execute(text("PRAGMA table_info(conversations)")).fetchall()
        conv_column_names = {row[1] for row in conv_columns}
        if "mode_id" not in conv_column_names:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN mode_id VARCHAR(36)"))

        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_created "
                "ON chat_messages(conversation_id, created_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_conversations_project_mode_lastmsg "
                "ON conversations(project_id, mode, last_message_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_conversations_project_mode_status "
                "ON conversations(project_id, mode, status)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_conversations_project_modeid_lastmsg "
                "ON conversations(project_id, mode_id, last_message_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_conversations_project_modeid_status "
                "ON conversations(project_id, mode_id, status)"
            )
        )


def _ensure_agent_mode_schema(engine) -> None:
    """兼容旧库：为 agent_modes 补齐项目角色与模板字段。"""
    new_columns = {
        "project_id": "VARCHAR(36)",
        "is_template": "BOOLEAN DEFAULT 0",
    }
    _add_missing_columns(engine, "agent_modes", new_columns)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_agent_modes_project_sort "
                "ON agent_modes(project_id, sort_order, created_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_agent_modes_templates "
                "ON agent_modes(is_template, sort_order, created_at)"
            )
        )
        conn.execute(
            text(
                "UPDATE agent_modes "
                "SET is_template = 1 "
                "WHERE project_id IS NULL AND is_system = 1 AND (is_template IS NULL OR is_template = 0)"
            )
        )


def _ensure_memory_schema(engine) -> None:
    """兼容旧库：为 memory_items 补齐稳定角色来源字段。"""
    new_columns = {
        "source_mode_id": "VARCHAR(36)",
    }
    _add_missing_columns(engine, "memory_items", new_columns)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_memory_items_project_modeid_created "
                "ON memory_items(project_id, source_mode_id, created_at)"
            )
        )


def _ensure_content_block_columns(engine) -> None:
    """兼容旧库：为 content_blocks 补齐 0225-compatible 新增列。"""
    new_columns = {
        "auto_generate": "BOOLEAN DEFAULT 0",
        "needs_regeneration": "BOOLEAN DEFAULT 0",
        "model_override": "VARCHAR(100)",
        "digest": "TEXT",
        "guidance_input": "TEXT DEFAULT ''",
        "guidance_output": "TEXT DEFAULT ''",
    }
    _add_missing_columns(engine, "content_blocks", new_columns)


def _ensure_project_columns(engine) -> None:
    """兼容旧库：为 projects 补齐 locale/版本族谱/废弃兼容字段。"""
    from core.localization import DEFAULT_LOCALE

    new_columns = {
        "locale": f"VARCHAR(20) DEFAULT '{DEFAULT_LOCALE}'",
        "version": "INTEGER DEFAULT 1",
        "version_note": "TEXT DEFAULT ''",
        "parent_version_id": "VARCHAR(36)",
        "agent_autonomy": "JSON",
        "golden_context": "JSON",
        "use_deep_research": "BOOLEAN DEFAULT 1",
        "use_flexible_architecture": "BOOLEAN DEFAULT 1",
    }
    _add_missing_columns(engine, "projects", new_columns)


def _ensure_agent_settings_columns(engine) -> None:
    """兼容旧库：为 agent_settings 补齐模型选择列。"""
    new_columns = {
        "default_model": "VARCHAR(100)",
        "default_mini_model": "VARCHAR(100)",
    }
    _add_missing_columns(engine, "agent_settings", new_columns)


def _ensure_field_template_columns(engine) -> None:
    """兼容旧库：为 field_templates 补齐树模板列。"""
    from core.localization import DEFAULT_LOCALE

    new_columns = {
        "schema_version": "INTEGER DEFAULT 1",
        "root_nodes": "JSON",
        "stable_key": "VARCHAR(100) DEFAULT ''",
        "locale": f"VARCHAR(20) DEFAULT '{DEFAULT_LOCALE}'",
    }
    _add_missing_columns(engine, "field_templates", new_columns)


def _ensure_phase_template_columns(engine) -> None:
    """兼容旧库：为 phase_templates 补齐 locale 资产列。"""
    from core.localization import DEFAULT_LOCALE

    new_columns = {
        "stable_key": "VARCHAR(100) DEFAULT ''",
        "locale": f"VARCHAR(20) DEFAULT '{DEFAULT_LOCALE}'",
    }
    _add_missing_columns(engine, "phase_templates", new_columns)


def _ensure_localized_asset_columns(engine) -> None:
    """兼容旧库：为 locale 资产表补齐 stable_key / locale 列。"""
    from core.localization import DEFAULT_LOCALE

    locale_columns = {
        "stable_key": "VARCHAR(100) DEFAULT ''",
        "locale": f"VARCHAR(20) DEFAULT '{DEFAULT_LOCALE}'",
    }
    for table in (
        "creator_profiles",
        "system_prompts",
        "channels",
        "simulators",
        "graders",
        "agent_modes",
    ):
        _add_missing_columns(engine, table, locale_columns)


def _backfill_compat_defaults(engine) -> None:
    """为新增兼容列回填安全默认值，并清理已知可空坏引用。"""
    from core.localization import DEFAULT_LOCALE

    statements = [
        (
            "UPDATE projects SET locale = :default_locale "
            "WHERE locale IS NULL OR locale = ''",
            {"default_locale": DEFAULT_LOCALE},
        ),
        (
            "UPDATE creator_profiles SET locale = :default_locale "
            "WHERE locale IS NULL OR locale = ''",
            {"default_locale": DEFAULT_LOCALE},
        ),
        (
            "UPDATE field_templates SET locale = :default_locale "
            "WHERE locale IS NULL OR locale = ''",
            {"default_locale": DEFAULT_LOCALE},
        ),
        (
            "UPDATE phase_templates SET locale = :default_locale "
            "WHERE locale IS NULL OR locale = ''",
            {"default_locale": DEFAULT_LOCALE},
        ),
        (
            "UPDATE content_blocks SET auto_generate = 0 "
            "WHERE auto_generate IS NULL",
            {},
        ),
        (
            "UPDATE content_blocks SET needs_regeneration = 0 "
            "WHERE needs_regeneration IS NULL",
            {},
        ),
        (
            "UPDATE channels SET locale = :default_locale "
            "WHERE locale IS NULL OR locale = ''",
            {"default_locale": DEFAULT_LOCALE},
        ),
        (
            "UPDATE simulators SET locale = :default_locale "
            "WHERE locale IS NULL OR locale = ''",
            {"default_locale": DEFAULT_LOCALE},
        ),
        (
            "UPDATE graders SET locale = :default_locale "
            "WHERE locale IS NULL OR locale = ''",
            {"default_locale": DEFAULT_LOCALE},
        ),
        (
            "UPDATE system_prompts SET locale = :default_locale "
            "WHERE locale IS NULL OR locale = ''",
            {"default_locale": DEFAULT_LOCALE},
        ),
        (
            "UPDATE agent_modes SET locale = :default_locale "
            "WHERE locale IS NULL OR locale = ''",
            {"default_locale": DEFAULT_LOCALE},
        ),
        (
            "UPDATE creator_profiles SET stable_key = name "
            "WHERE stable_key IS NULL OR stable_key = ''",
            {},
        ),
        (
            "UPDATE field_templates SET stable_key = name "
            "WHERE stable_key IS NULL OR stable_key = ''",
            {},
        ),
        (
            "UPDATE phase_templates SET stable_key = name "
            "WHERE stable_key IS NULL OR stable_key = ''",
            {},
        ),
        (
            "UPDATE channels SET stable_key = name "
            "WHERE stable_key IS NULL OR stable_key = ''",
            {},
        ),
        (
            "UPDATE simulators SET stable_key = name "
            "WHERE stable_key IS NULL OR stable_key = ''",
            {},
        ),
        (
            "UPDATE graders SET stable_key = name "
            "WHERE stable_key IS NULL OR stable_key = ''",
            {},
        ),
        (
            "UPDATE system_prompts SET stable_key = phase "
            "WHERE stable_key IS NULL OR stable_key = ''",
            {},
        ),
        (
            "UPDATE agent_modes SET stable_key = name "
            "WHERE stable_key IS NULL OR stable_key = ''",
            {},
        ),
        (
            "UPDATE projects SET creator_profile_id = NULL "
            "WHERE creator_profile_id IS NOT NULL "
            "AND creator_profile_id NOT IN (SELECT id FROM creator_profiles)",
            {},
        ),
        (
            "UPDATE project_fields SET template_id = NULL "
            "WHERE template_id IS NOT NULL "
            "AND template_id NOT IN (SELECT id FROM field_templates)",
            {},
        ),
    ]
    with engine.begin() as conn:
        for sql, params in statements:
            conn.execute(text(sql), params)


def _add_missing_columns(engine, table: str, columns: dict[str, str]) -> None:
    """通用：检查并补齐缺失列。columns = {col_name: col_definition}"""
    with engine.begin() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        existing = {row[1] for row in rows}
        for col_name, col_def in columns.items():
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))


# 依赖注入用的Session生成器
def get_db():
    """FastAPI依赖: 获取数据库Session"""
    SessionLocal = get_session_maker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


