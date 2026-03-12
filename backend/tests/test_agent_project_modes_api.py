# backend/tests/test_agent_project_modes_api.py
# 功能: 验证项目级 Agent 角色 API 与 mode_id 运行时链路
# 主要测试: 模板导入、项目角色 CRUD、会话按 mode_id 隔离、chat 接口按 mode_id 运行
# 数据结构: FastAPI TestClient + 内存数据库中的 Project / AgentMode / Conversation / ChatMessage

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from langchain_core.messages import AIMessage

from core.database import Base, get_db
from core.models import Project, AgentMode, Conversation, ChatMessage, generate_uuid
import core.memory_service as memory_service
import api.agent as agent_api
from main import app


@pytest.fixture
def client_and_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    session = TestingSessionLocal()
    try:
        yield client, session
    finally:
        session.close()
        app.dependency_overrides.clear()


def _seed_project_and_templates(session, *, locale: str = "zh-CN"):
    project = Project(id=generate_uuid(), name="Mode Test Project", locale=locale)
    session.add(project)
    session.flush()

    templates = [
        AgentMode(
            id=generate_uuid(),
            project_id=None,
            name="assistant",
            display_name="助手",
            description="默认助手模板",
            system_prompt="你是助手",
            icon="A",
            is_system=True,
            is_template=True,
            sort_order=0,
        ),
        AgentMode(
            id=generate_uuid(),
            project_id=None,
            name="critic",
            display_name="审稿人",
            description="默认审稿人模板",
            system_prompt="你是审稿人",
            icon="C",
            is_system=True,
            is_template=True,
            sort_order=1,
        ),
    ]
    session.add_all(templates)
    session.commit()
    return project, templates


def test_modes_list_templates_and_import_to_project(client_and_session):
    client, session = client_and_session
    project, templates = _seed_project_and_templates(session)

    listed_templates = client.get("/api/modes/")
    assert listed_templates.status_code == 200
    rows = listed_templates.json()
    assert [row["name"] for row in rows] == ["assistant", "critic"]
    assert all(row["is_template"] is True for row in rows)

    listed_project_modes = client.get("/api/modes/", params={"project_id": project.id})
    assert listed_project_modes.status_code == 200
    assert listed_project_modes.json() == []

    imported = client.post("/api/modes/import-templates", json={"project_id": project.id})
    assert imported.status_code == 200
    imported_json = imported.json()
    assert len(imported_json["imported"]) == 2
    assert imported_json["skipped_count"] == 0

    listed_project_modes = client.get("/api/modes/", params={"project_id": project.id})
    assert listed_project_modes.status_code == 200
    project_rows = listed_project_modes.json()
    assert [row["display_name"] for row in project_rows] == ["助手", "审稿人"]
    assert all(row["project_id"] == project.id for row in project_rows)
    assert all(row["is_template"] is False for row in project_rows)
    assert {row["name"] for row in project_rows}.isdisjoint({tpl.name for tpl in templates})


def test_legacy_system_modes_are_backfilled_and_importable(client_and_session):
    client, session = client_and_session
    project = Project(id=generate_uuid(), name="Legacy Mode Project")
    session.add(project)
    session.add_all([
        AgentMode(
            id=generate_uuid(),
            project_id=None,
            name="assistant",
            display_name="助手",
            description="legacy assistant",
            system_prompt="你是助手",
            icon="A",
            is_system=True,
            is_template=False,
            sort_order=0,
        ),
        AgentMode(
            id=generate_uuid(),
            project_id=None,
            name="critic",
            display_name="审稿人",
            description="legacy critic",
            system_prompt="你是审稿人",
            icon="C",
            is_system=True,
            is_template=False,
            sort_order=1,
        ),
    ])
    session.commit()

    listed_templates = client.get("/api/modes/templates")
    assert listed_templates.status_code == 200
    rows = listed_templates.json()
    assert [row["name"] for row in rows] == ["assistant", "critic"]
    assert all(row["is_template"] is True for row in rows)

    session.expire_all()
    db_rows = session.query(AgentMode).filter(AgentMode.project_id.is_(None)).order_by(AgentMode.sort_order).all()
    assert len(db_rows) == 2
    assert all(row.is_template is True for row in db_rows)

    imported = client.post("/api/modes/import-templates", json={"project_id": project.id})
    assert imported.status_code == 200
    imported_json = imported.json()
    assert [row["display_name"] for row in imported_json["imported"]] == ["助手", "审稿人"]


def test_create_update_delete_project_mode(client_and_session):
    client, session = client_and_session
    project, _ = _seed_project_and_templates(session)

    created = client.post(
        "/api/modes/",
        json={
            "project_id": project.id,
            "display_name": "增长教练",
            "description": "",
            "icon": "G",
            "system_prompt": "你是增长教练",
        },
    )
    assert created.status_code == 200
    created_json = created.json()
    assert created_json["project_id"] == project.id
    assert created_json["display_name"] == "增长教练"
    assert created_json["description"] == ""
    assert created_json["is_template"] is False
    assert created_json["name"].startswith("mode_")

    updated = client.put(
        f"/api/modes/{created_json['id']}",
        json={"display_name": "转化教练", "description": "可选简介", "icon": "T"},
    )
    assert updated.status_code == 200
    updated_json = updated.json()
    assert updated_json["display_name"] == "转化教练"
    assert updated_json["description"] == "可选简介"
    assert updated_json["icon"] == "T"

    deleted = client.delete(f"/api/modes/{created_json['id']}")
    assert deleted.status_code == 200

    listed = client.get("/api/modes/", params={"project_id": project.id})
    assert listed.status_code == 200
    assert listed.json() == []


def test_project_modes_respect_sort_order_updates(client_and_session):
    client, session = client_and_session
    project, _ = _seed_project_and_templates(session)

    first = client.post(
        "/api/modes/",
        json={
            "project_id": project.id,
            "display_name": "角色A",
            "description": "",
            "icon": "A",
            "system_prompt": "你是角色A",
        },
    )
    second = client.post(
        "/api/modes/",
        json={
            "project_id": project.id,
            "display_name": "角色B",
            "description": "",
            "icon": "B",
            "system_prompt": "你是角色B",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200

    first_json = first.json()
    second_json = second.json()
    swapped_a = client.put(f"/api/modes/{first_json['id']}", json={"sort_order": 1})
    swapped_b = client.put(f"/api/modes/{second_json['id']}", json={"sort_order": 0})
    assert swapped_a.status_code == 200
    assert swapped_b.status_code == 200

    listed = client.get("/api/modes/", params={"project_id": project.id})
    assert listed.status_code == 200
    rows = listed.json()
    assert [row["display_name"] for row in rows] == ["角色B", "角色A"]


def test_create_conversation_and_history_filter_by_mode_id(client_and_session):
    client, session = client_and_session
    project, _ = _seed_project_and_templates(session)

    imported = client.post("/api/modes/import-templates", json={"project_id": project.id}).json()
    assistant_mode = imported["imported"][0]
    critic_mode = imported["imported"][1]

    conv_a = client.post("/api/agent/conversations", json={"project_id": project.id, "mode_id": assistant_mode["id"]})
    conv_b = client.post("/api/agent/conversations", json={"project_id": project.id, "mode_id": critic_mode["id"]})
    assert conv_a.status_code == 200
    assert conv_b.status_code == 200

    listed_a = client.get("/api/agent/conversations", params={"project_id": project.id, "mode_id": assistant_mode["id"]})
    listed_b = client.get("/api/agent/conversations", params={"project_id": project.id, "mode_id": critic_mode["id"]})
    assert listed_a.status_code == 200
    assert listed_b.status_code == 200
    assert len(listed_a.json()) == 1
    assert len(listed_b.json()) == 1
    assert listed_a.json()[0]["mode_id"] == assistant_mode["id"]
    assert listed_b.json()[0]["mode_id"] == critic_mode["id"]

    session.add_all([
        ChatMessage(
            id=generate_uuid(),
            project_id=project.id,
            conversation_id=conv_a.json()["id"],
            role="user",
            content="assistant history",
            message_metadata={"mode": assistant_mode["id"], "mode_id": assistant_mode["id"], "mode_label": assistant_mode["display_name"]},
        ),
        ChatMessage(
            id=generate_uuid(),
            project_id=project.id,
            conversation_id=conv_b.json()["id"],
            role="user",
            content="critic history",
            message_metadata={"mode": critic_mode["id"], "mode_id": critic_mode["id"], "mode_label": critic_mode["display_name"]},
        ),
    ])
    session.commit()

    history = client.get(f"/api/agent/history/{project.id}", params={"mode_id": critic_mode["id"]})
    assert history.status_code == 200
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["content"] == "critic history"

    renamed = client.put(
        f"/api/modes/{critic_mode['id']}",
        json={"display_name": "严格审稿人"},
    )
    assert renamed.status_code == 200

    history_after_rename = client.get(f"/api/agent/history/{project.id}", params={"mode_id": critic_mode["id"]})
    assert history_after_rename.status_code == 200
    renamed_rows = history_after_rename.json()
    assert len(renamed_rows) == 1
    assert renamed_rows[0]["content"] == "critic history"


def test_create_conversation_defaults_to_project_locale_copy(client_and_session):
    client, session = client_and_session
    project, _ = _seed_project_and_templates(session, locale="ja-JP")

    imported = client.post("/api/modes/import-templates", json={"project_id": project.id}).json()
    assistant_mode = imported["imported"][0]

    conv = client.post("/api/agent/conversations", json={"project_id": project.id, "mode_id": assistant_mode["id"]})
    assert conv.status_code == 200
    assert conv.json()["title"] == "新しい会話"


def test_chat_requires_project_mode_and_uses_mode_id(client_and_session, monkeypatch):
    client, session = client_and_session
    project, _ = _seed_project_and_templates(session)

    no_mode_resp = client.post(
        "/api/agent/chat",
        json={"project_id": project.id, "message": "hello"},
    )
    assert no_mode_resp.status_code == 400
    assert "尚未配置 Agent 角色" in no_mode_resp.json()["detail"]

    imported = client.post("/api/modes/import-templates", json={"project_id": project.id}).json()
    mode = imported["imported"][0]

    async def fake_load_memory_context_async(*args, **kwargs):
        return ""

    class FakeGraph:
        async def ainvoke(self, state, config=None):
            assert state["mode"] == mode["id"]
            assert state["mode_prompt"] == "你是助手"
            assert config["configurable"]["mode_id"] == mode["id"]
            return {"messages": [AIMessage(content="mode ok")]}

    async def fake_get_agent_graph():
        return FakeGraph()

    monkeypatch.setattr(memory_service, "load_memory_context_async", fake_load_memory_context_async)
    monkeypatch.setattr(agent_api, "get_agent_graph", fake_get_agent_graph)

    resp = client.post(
        "/api/agent/chat",
        json={"project_id": project.id, "message": "hello", "mode_id": mode["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "mode ok"

    conv = session.query(Conversation).filter(Conversation.project_id == project.id).first()
    assert conv is not None
    assert conv.mode_id == mode["id"]
    assert conv.mode == mode["display_name"]

    msgs = session.query(ChatMessage).filter(ChatMessage.project_id == project.id).order_by(ChatMessage.created_at.asc()).all()
    assert len(msgs) == 2
    assert msgs[0].message_metadata["mode_id"] == mode["id"]
    assert msgs[1].message_metadata["mode_label"] == mode["display_name"]


def test_duplicate_and_export_import_preserve_project_modes(client_and_session):
    client, session = client_and_session
    project, _ = _seed_project_and_templates(session)

    created = client.post(
        "/api/modes/",
        json={
            "project_id": project.id,
            "display_name": "品牌总编",
            "description": "统一品牌口径",
            "icon": "B",
            "system_prompt": "你是品牌总编",
        },
    )
    assert created.status_code == 200

    duplicated = client.post(f"/api/projects/{project.id}/duplicate", json={"name": "Mode Copy"})
    assert duplicated.status_code == 200
    duplicated_project_id = duplicated.json()["id"]

    duplicated_modes = client.get("/api/modes/", params={"project_id": duplicated_project_id})
    assert duplicated_modes.status_code == 200
    duplicated_rows = duplicated_modes.json()
    assert len(duplicated_rows) == 1
    assert duplicated_rows[0]["display_name"] == "品牌总编"
    assert duplicated_rows[0]["name"].startswith("mode_")

    exported = client.get(f"/api/projects/{project.id}/export")
    assert exported.status_code == 200
    exported_json = exported.json()
    assert len(exported_json["agent_modes"]) == 1
    assert exported_json["agent_modes"][0]["display_name"] == "品牌总编"

    imported = client.post("/api/projects/import", json={"data": exported_json})
    assert imported.status_code == 200
    imported_project_id = imported.json()["project"]["id"]

    imported_modes = client.get("/api/modes/", params={"project_id": imported_project_id})
    assert imported_modes.status_code == 200
    imported_rows = imported_modes.json()
    assert len(imported_rows) == 1
    assert imported_rows[0]["display_name"] == "品牌总编"
