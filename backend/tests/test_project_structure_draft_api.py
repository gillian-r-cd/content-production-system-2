# backend/tests/test_project_structure_draft_api.py
# 功能: 覆盖项目级自动拆分草稿 API 的主链语义，验证校验、应用、重复应用与编辑失效约束
# 主要测试: test_auto_split_draft_api_requires_validation_before_apply_and_allows_reapply
# 数据结构: FastAPI TestClient + 内存数据库中的 Project / ProjectStructureDraft / ContentBlock

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from core.models import Project, generate_uuid
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


def test_auto_split_draft_api_requires_validation_before_apply_and_allows_reapply(client_and_session):
    client, session = client_and_session
    project = Project(id=generate_uuid(), name="自动拆分 API 测试项目")
    session.add(project)
    session.commit()

    split_resp = client.post(
        f"/api/project-structure-drafts/project/{project.id}/auto-split/split",
        json={
            "source_text": "第一段内容。",
            "split_config": {"mode": "count", "target_count": 1},
        },
    )
    assert split_resp.status_code == 200
    assert len(split_resp.json()["chunks"]) == 1

    validate_resp = client.post(
        f"/api/project-structure-drafts/project/{project.id}/auto-split/validate",
    )
    assert validate_resp.status_code == 200
    assert validate_resp.json()["draft"]["status"] == "validated"

    first_apply_resp = client.post(
        f"/api/project-structure-drafts/project/{project.id}/auto-split/apply",
        json={},
    )
    assert first_apply_resp.status_code == 200
    assert first_apply_resp.json()["draft"]["status"] == "applied"
    assert first_apply_resp.json()["draft"]["apply_count"] == 1

    second_apply_resp = client.post(
        f"/api/project-structure-drafts/project/{project.id}/auto-split/apply",
        json={},
    )
    assert second_apply_resp.status_code == 200
    assert second_apply_resp.json()["draft"]["status"] == "applied"
    assert second_apply_resp.json()["draft"]["apply_count"] == 2

    update_resp = client.put(
        f"/api/project-structure-drafts/project/{project.id}/auto-split",
        json={"name": "重新命名后的草稿"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "draft"

    rejected_apply_resp = client.post(
        f"/api/project-structure-drafts/project/{project.id}/auto-split/apply",
        json={},
    )
    assert rejected_apply_resp.status_code == 400
    assert "先执行校验" in rejected_apply_resp.json()["detail"]
