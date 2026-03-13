# 功能: 覆盖依赖更新后 stale 标记、自动调度和 locale 化提示的 API 主链
# 主要测试: update_block / confirm_block / rollback_version
# 数据结构: FastAPI TestClient + 内存数据库中的 Project / ContentBlock / ContentVersion

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from core.models import ContentBlock, ContentVersion, Project, generate_uuid
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


def _make_project(*, locale: str) -> Project:
    return Project(
        id=generate_uuid(),
        name=f"Project-{locale}",
        locale=locale,
        current_phase="produce_inner",
        phase_order=["produce_inner"],
        phase_status={"produce_inner": "pending"},
    )


def test_update_block_marks_downstream_stale_and_warns_only_manual_attention_in_japanese(client_and_session, monkeypatch):
    import api.blocks as blocks_api

    scheduled_projects: list[str] = []
    monkeypatch.setattr(
        blocks_api,
        "schedule_project_auto_trigger",
        lambda project_id, background_tasks=None: scheduled_projects.append(project_id),
    )

    client, session = client_and_session
    project = _make_project(locale="ja-JP")
    source = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="元ブロック",
        block_type="field",
        depth=0,
        order_index=0,
        content="古い上流内容",
        status="completed",
    )
    auto_downstream = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="自動下流",
        block_type="field",
        depth=0,
        order_index=1,
        content="古い自動内容",
        status="completed",
        auto_generate=True,
        need_review=False,
        depends_on=[source.id],
    )
    manual_downstream = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="手動下流",
        block_type="field",
        depth=0,
        order_index=2,
        content="古い手動内容",
        status="completed",
        auto_generate=False,
        need_review=True,
        depends_on=[source.id],
    )
    session.add_all([project, source, auto_downstream, manual_downstream])
    session.commit()

    response = client.put(
        f"/api/blocks/{source.id}",
        json={"content": "新しい上流内容"},
    )

    assert response.status_code == 200
    body = response.json()
    session.refresh(auto_downstream)
    session.refresh(manual_downstream)

    assert auto_downstream.needs_regeneration is True
    assert manual_downstream.needs_regeneration is True
    assert body["affected_blocks"] == ["手動下流"]
    assert body["version_warning"] == (
        "「元ブロック」の内容を更新しました。"
        "以下の下流内容ブロックは更新待ちとしてマークされており、引き続き手動対応が必要です: 手動下流"
    )
    assert scheduled_projects == [project.id]


def test_confirm_block_rejects_stale_content_in_japanese(client_and_session):
    client, session = client_and_session
    project = _make_project(locale="ja-JP")
    block = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="確認対象",
        block_type="field",
        depth=0,
        order_index=0,
        content="古い内容",
        status="in_progress",
        need_review=True,
        needs_regeneration=True,
    )
    session.add_all([project, block])
    session.commit()

    response = client.post(f"/api/blocks/{block.id}/confirm")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "内容ブロック「確認対象」の依存関係が更新されました。"
        "現在の内容は古くなっているため、再生成または手動更新の後に確認してください。"
    )


def test_rollback_marks_downstream_stale_and_schedules_auto_trigger(client_and_session, monkeypatch):
    import api.versions as versions_api

    scheduled_projects: list[str] = []
    monkeypatch.setattr(
        versions_api,
        "schedule_project_auto_trigger",
        lambda project_id, background_tasks=None: scheduled_projects.append(project_id),
    )

    client, session = client_and_session
    project = _make_project(locale="zh-CN")
    source = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="上游块",
        block_type="field",
        depth=0,
        order_index=0,
        content="当前内容",
        status="completed",
    )
    downstream = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="下游块",
        block_type="field",
        depth=0,
        order_index=1,
        content="旧下游内容",
        status="completed",
        auto_generate=True,
        need_review=False,
        depends_on=[source.id],
    )
    version = ContentVersion(
        id=generate_uuid(),
        block_id=source.id,
        version_number=1,
        content="历史版本内容",
        source="manual",
    )
    session.add_all([project, source, downstream, version])
    session.commit()

    response = client.post(f"/api/versions/{source.id}/rollback/{version.id}")

    assert response.status_code == 200
    body = response.json()
    session.refresh(source)
    session.refresh(downstream)

    assert source.content == "历史版本内容"
    assert source.needs_regeneration is False
    assert downstream.needs_regeneration is True
    assert body["message"] == "已回滚到版本 v1"
    assert scheduled_projects == [project.id]
