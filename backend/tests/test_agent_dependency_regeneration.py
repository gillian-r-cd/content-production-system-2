# 功能: 覆盖 Agent 落库改写后的下游失效传播与自动调度
# 主要测试: /api/agent/confirm-suggestion
# 数据结构: FastAPI TestClient + 内存数据库中的 Project / ContentBlock / PENDING_SUGGESTIONS

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from core.models import ContentBlock, Project, generate_uuid
from core.agent_tools import PENDING_SUGGESTIONS
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
        PENDING_SUGGESTIONS.clear()
        session.close()
        app.dependency_overrides.clear()


def test_confirm_suggestion_marks_downstream_stale_and_resets_need_review_status(client_and_session, monkeypatch):
    import api.agent as agent_api

    scheduled_projects: list[str] = []
    monkeypatch.setattr(
        agent_api,
        "schedule_project_auto_trigger",
        lambda project_id, background_tasks=None: scheduled_projects.append(project_id),
    )

    client, session = client_and_session
    project = Project(
        id=generate_uuid(),
        name="Agent Test",
        locale="ja-JP",
        current_phase="produce_inner",
        phase_order=["produce_inner"],
        phase_status={"produce_inner": "pending"},
    )
    source = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="原文",
        block_type="field",
        depth=0,
        order_index=0,
        content="旧内容",
        status="completed",
        need_review=True,
    )
    downstream = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="ローカライズ内容",
        block_type="field",
        depth=0,
        order_index=1,
        content="旧下游内容",
        status="completed",
        need_review=False,
        auto_generate=True,
        depends_on=[source.id],
    )
    session.add_all([project, source, downstream])
    session.commit()

    suggestion_id = generate_uuid()
    PENDING_SUGGESTIONS[suggestion_id] = {
        "id": suggestion_id,
        "target_entity_id": source.id,
        "target_field": source.name,
        "summary": "改写原文",
        "original_content": "旧内容",
        "modified_content": "新内容",
        "edits": [],
        "card_type": "full_rewrite",
        "status": "pending",
    }

    response = client.post(
        "/api/agent/confirm-suggestion",
        json={
            "project_id": project.id,
            "suggestion_id": suggestion_id,
            "action": "accept",
            "accepted_card_ids": [],
        },
    )

    assert response.status_code == 200
    session.refresh(source)
    session.refresh(downstream)

    assert source.content == "新内容"
    assert source.status == "in_progress"
    assert source.needs_regeneration is False
    assert downstream.needs_regeneration is True
    assert scheduled_projects == [project.id]
