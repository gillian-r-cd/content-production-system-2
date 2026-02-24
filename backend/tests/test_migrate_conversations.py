# backend/tests/test_migrate_conversations.py
# 功能: 验证 conversation 迁移脚本行为
# 主要函数: test_migrate_conversations_backfills_messages
# 数据结构: Project/ChatMessage/Conversation 迁移前后状态

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import Project, ChatMessage
from scripts.migrate_conversations import migrate_conversations


def _make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def test_migrate_conversations_backfills_messages():
    db = _make_session()
    try:
        project = Project(name="迁移测试项目")
        db.add(project)
        db.commit()

        m1 = ChatMessage(
            project_id=project.id,
            role="user",
            content="你好",
            message_metadata={"mode": "assistant"},
        )
        m2 = ChatMessage(
            project_id=project.id,
            role="assistant",
            content="你好，我是助手",
            message_metadata={"mode": "assistant"},
        )
        db.add_all([m1, m2])
        db.commit()

        stats = migrate_conversations(db, dry_run=False)
        assert stats["groups_found"] >= 1
        assert stats["messages_backfilled"] == 2
        assert stats["conversations_created"] == 1

        rows = db.query(ChatMessage).all()
        assert all(r.conversation_id for r in rows)
        conv_ids = {r.conversation_id for r in rows}
        assert len(conv_ids) == 1
    finally:
        db.close()

