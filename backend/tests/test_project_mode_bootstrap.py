# 功能: 覆盖项目 Agent 角色 bootstrap 的 locale 选择与模板命名约束，防止 ja-JP 角色再次回退到中文
# 主要测试: _template_mode_name / ensure_project_agent_modes
# 数据结构: AgentMode / Project / in-memory SQLite

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import AgentMode, Project
from core.project_mode_bootstrap import ensure_project_agent_modes
from scripts.init_db import _template_mode_name


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_template_mode_name_is_unique_per_locale():
    assert _template_mode_name("assistant", "zh-CN") == "assistant__zh_cn"
    assert _template_mode_name("assistant", "ja-JP") == "assistant__ja_jp"
    assert _template_mode_name("assistant", "zh-CN") != _template_mode_name("assistant", "ja-JP")


def test_ensure_project_agent_modes_prefers_japanese_templates(db_session):
    project = Project(
        id="project-ja",
        name="Japanese Project",
        locale="ja-JP",
        current_phase="intent",
        phase_order=["intent"],
        phase_status={"intent": "pending"},
    )
    zh_template = AgentMode(
        id="tmpl-zh-assistant",
        project_id=None,
        name=_template_mode_name("assistant", "zh-CN"),
        stable_key="assistant",
        locale="zh-CN",
        display_name="助手",
        description="中文模板",
        system_prompt="中文 assistant",
        icon="🛠️",
        is_system=True,
        is_template=True,
        sort_order=0,
    )
    ja_template = AgentMode(
        id="tmpl-ja-assistant",
        project_id=None,
        name=_template_mode_name("assistant", "ja-JP"),
        stable_key="assistant",
        locale="ja-JP",
        display_name="アシスタント",
        description="日本語テンプレート",
        system_prompt="日本語 assistant",
        icon="🛠️",
        is_system=True,
        is_template=True,
        sort_order=0,
    )
    db_session.add_all([project, zh_template, ja_template])
    db_session.commit()

    created = ensure_project_agent_modes(db_session, project.id, locale=project.locale)
    db_session.commit()

    assert len(created) == 1
    assert created[0].display_name == "アシスタント"
    assert created[0].locale == "ja-JP"
