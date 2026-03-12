# backend/tests/test_database_compat_schema.py
# 功能: 守卫旧 SQLite 数据库在启动时能自动补齐 locale/stable_key 等兼容列
# 主要测试: init_db() 对旧 schema 的兼容迁移与 ORM 查询烟雾验证
# 数据结构: 临时 SQLite 文件、被删列后的 legacy 表、SQLAlchemy Session

import sqlite3
from pathlib import Path

from sqlalchemy import text

from core.config import settings
from core.database import Base, get_engine, get_session_maker, init_db
from core.models import (
    AgentMode,
    Channel,
    CreatorProfile,
    FieldTemplate,
    Grader,
    PhaseTemplate,
    Project,
    Simulator,
    SystemPrompt,
)


LEGACY_DROP_COLUMNS = {
    "projects": ["locale"],
    "creator_profiles": ["stable_key", "locale"],
    "field_templates": ["stable_key", "locale"],
    "phase_templates": ["stable_key", "locale"],
    "system_prompts": ["stable_key", "locale"],
    "channels": ["stable_key", "locale"],
    "simulators": ["stable_key", "locale"],
    "graders": ["stable_key", "locale"],
    "agent_modes": ["stable_key", "locale"],
}


def _table_columns(db_path: Path, table_name: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row[1] for row in rows}
    finally:
        conn.close()


def test_init_db_restores_locale_and_stable_key_columns_for_legacy_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy_content_production.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        for table_name, columns in LEGACY_DROP_COLUMNS.items():
            for column_name in columns:
                conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}"))

    init_db()

    assert "locale" in _table_columns(db_path, "projects")
    for table_name in (
        "creator_profiles",
        "field_templates",
        "phase_templates",
        "system_prompts",
        "channels",
        "simulators",
        "graders",
        "agent_modes",
    ):
        columns = _table_columns(db_path, table_name)
        assert "stable_key" in columns
        assert "locale" in columns

    SessionLocal = get_session_maker()
    db = SessionLocal()
    try:
        assert db.query(Project).count() == 0
        assert db.query(CreatorProfile).count() == 0
        assert db.query(FieldTemplate).count() == 0
        assert db.query(PhaseTemplate).count() == 0
        assert db.query(SystemPrompt).count() == 0
        assert db.query(Channel).count() == 0
        assert db.query(Simulator).count() == 0
        assert db.query(Grader).count() == 0
        assert db.query(AgentMode).count() == 0
    finally:
        db.close()


def test_get_engine_creates_missing_sqlite_parent_directory(tmp_path, monkeypatch):
    db_path = tmp_path / "nested" / "data" / "content_production.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("SELECT 1"))

    assert db_path.parent.exists()
    assert db_path.exists()


def test_init_db_clears_broken_nullable_asset_references(tmp_path, monkeypatch):
    db_path = tmp_path / "broken_ref_content_production.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO projects (id, name, creator_profile_id, locale, version, version_note, current_phase, phase_order, phase_status, agent_autonomy, golden_context, use_deep_research, use_flexible_architecture, created_at, updated_at) "
            "VALUES ('project-1', 'broken project', 'missing-profile', 'ja-JP', 1, '', 'intent', '[]', '{}', '{}', '{}', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
        conn.execute(text(
            "INSERT INTO project_fields (id, project_id, template_id, phase, name, field_type, content, status, ai_prompt, pre_questions, pre_answers, dependencies, constraints, need_review, created_at, updated_at) "
            "VALUES ('field-1', 'project-1', 'missing-template', 'intent', 'field', 'text', '', 'pending', '', '[]', '{}', '{}', '{}', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))

    init_db()

    SessionLocal = get_session_maker()
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == "project-1").first()
        assert project is not None
        assert project.creator_profile_id is None

        field = db.execute(text("SELECT template_id FROM project_fields WHERE id = 'field-1'")).first()
        assert field is not None
        assert field[0] is None
    finally:
        db.close()
