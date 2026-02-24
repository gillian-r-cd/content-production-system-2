# backend/core/database.py
# 功能: 数据库连接管理
# 主要函数: get_engine(), get_session(), init_db()
# 数据结构: Base (SQLAlchemy declarative base)

"""
数据库连接管理模块
使用 SQLAlchemy 2.0 异步模式
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool

from core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


def get_engine():
    """
    获取数据库引擎
    SQLite使用StaticPool确保单连接（适合本地单用户）
    """
    # SQLite特殊配置
    connect_args = {"check_same_thread": False}

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
    _ensure_conversation_schema(engine)


def _ensure_conversation_schema(engine) -> None:
    """
    兼容旧库补齐会话化字段。

    当前项目未引入 Alembic，启动时通过轻量 SQL 兼容迁移：
    1) 为 chat_messages 增加 conversation_id（若不存在）
    2) 创建 conversations 索引（若不存在）
    """
    with engine.begin() as conn:
        columns = conn.execute(text("PRAGMA table_info(chat_messages)")).fetchall()
        column_names = {row[1] for row in columns}
        if "conversation_id" not in column_names:
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN conversation_id VARCHAR(36)"))

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


# 依赖注入用的Session生成器
def get_db():
    """FastAPI依赖: 获取数据库Session"""
    SessionLocal = get_session_maker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


