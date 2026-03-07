# backend/tests/test_projects_draft_lifecycle.py
# 功能: 覆盖项目 API 中结构草稿的生命周期语义，验证删除/复制/版本/导入导出都能正确处理草稿
# 主要测试: duplicate/version/import/delete 对 ProjectStructureDraft 的处理
# 数据结构: FastAPI TestClient + 内存数据库中的 Project / ContentBlock / ProjectStructureDraft

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from core.models import ContentBlock, Project, ProjectStructureDraft, generate_uuid
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


def seed_project_with_draft(session):
    project = Project(
        id=generate_uuid(),
        name="Draft Lifecycle Project",
        current_phase="intent",
        phase_order=["intent"],
        phase_status={"intent": "pending"},
    )
    block = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=None,
        name="Existing Dependency Block",
        block_type="field",
        depth=0,
        order_index=0,
        status="completed",
        content="Existing content",
    )
    draft = ProjectStructureDraft(
        id=generate_uuid(),
        project_id=project.id,
        draft_type="auto_split",
        name="自动拆分内容",
        status="validated",
        source_text="alpha\n\nbeta",
        split_config={"mode": "count", "target_count": 2, "overlap_chars": 0},
        draft_payload={
            "chunks": [
                {"chunk_id": "chunk-1", "title": "内容片段 01", "content": "alpha", "order_index": 0},
            ],
            "plans": [
                {
                    "plan_id": "plan-1",
                    "name": "摘要方案",
                    "target_chunk_ids": ["chunk-1"],
                    "root_nodes": [
                        {
                            "template_node_id": "node-1",
                            "name": "摘要",
                            "block_type": "field",
                            "draft_dependency_refs": [
                                {"ref_type": "project_block", "block_id": block.id},
                            ],
                            "children": [],
                        }
                    ],
                }
            ],
            "shared_root_nodes": [],
            "aggregate_root_nodes": [],
            "ui_state": {},
        },
        validation_errors=["old error"],
        last_validated_at=datetime.now(),
        apply_count=3,
        last_applied_at=datetime.now(),
    )
    session.add_all([project, block, draft])
    session.commit()
    return project, block, draft


def extract_project_block_ref(draft: ProjectStructureDraft) -> str:
    refs = draft.draft_payload["plans"][0]["root_nodes"][0]["draft_dependency_refs"]
    return refs[0]["block_id"]


def test_duplicate_project_remaps_draft_block_refs_and_resets_runtime_fields(client_and_session):
    client, session = client_and_session
    project, _, _ = seed_project_with_draft(session)

    response = client.post(f"/api/projects/{project.id}/duplicate")
    assert response.status_code == 200
    duplicated = response.json()

    duplicated_project = session.query(Project).filter(Project.id == duplicated["id"]).first()
    duplicated_block = session.query(ContentBlock).filter(
        ContentBlock.project_id == duplicated_project.id,
        ContentBlock.name == "Existing Dependency Block",
    ).first()
    duplicated_draft = session.query(ProjectStructureDraft).filter(
        ProjectStructureDraft.project_id == duplicated_project.id,
        ProjectStructureDraft.draft_type == "auto_split",
    ).first()

    assert duplicated_draft is not None
    assert extract_project_block_ref(duplicated_draft) == duplicated_block.id
    assert duplicated_draft.status == "draft"
    assert duplicated_draft.validation_errors == []
    assert duplicated_draft.last_validated_at is None
    assert duplicated_draft.apply_count == 0
    assert duplicated_draft.last_applied_at is None


def test_create_new_version_remaps_draft_block_refs_and_resets_runtime_fields(client_and_session):
    client, session = client_and_session
    project, _, _ = seed_project_with_draft(session)

    response = client.post(f"/api/projects/{project.id}/versions", json={"version_note": "new version"})
    assert response.status_code == 200
    versioned = response.json()

    versioned_project = session.query(Project).filter(Project.id == versioned["id"]).first()
    versioned_block = session.query(ContentBlock).filter(
        ContentBlock.project_id == versioned_project.id,
        ContentBlock.name == "Existing Dependency Block",
    ).first()
    versioned_draft = session.query(ProjectStructureDraft).filter(
        ProjectStructureDraft.project_id == versioned_project.id,
        ProjectStructureDraft.draft_type == "auto_split",
    ).first()

    assert versioned_draft is not None
    assert extract_project_block_ref(versioned_draft) == versioned_block.id
    assert versioned_draft.status == "draft"
    assert versioned_draft.validation_errors == []
    assert versioned_draft.last_validated_at is None
    assert versioned_draft.apply_count == 0
    assert versioned_draft.last_applied_at is None


def test_export_and_import_project_preserve_draft_content_but_remap_project_block_refs(client_and_session):
    client, session = client_and_session
    project, block, draft = seed_project_with_draft(session)

    export_response = client.get(f"/api/projects/{project.id}/export")
    assert export_response.status_code == 200
    exported = export_response.json()
    assert exported["project_structure_drafts"][0]["id"] == draft.id
    assert exported["project_structure_drafts"][0]["draft_payload"]["plans"][0]["root_nodes"][0]["draft_dependency_refs"][0]["block_id"] == block.id

    import_response = client.post("/api/projects/import", json={"data": exported, "match_creator_profile": True})
    assert import_response.status_code == 200
    imported_project_id = import_response.json()["project"]["id"]

    imported_block = session.query(ContentBlock).filter(
        ContentBlock.project_id == imported_project_id,
        ContentBlock.name == "Existing Dependency Block",
    ).first()
    imported_draft = session.query(ProjectStructureDraft).filter(
        ProjectStructureDraft.project_id == imported_project_id,
        ProjectStructureDraft.draft_type == "auto_split",
    ).first()

    assert imported_draft is not None
    assert extract_project_block_ref(imported_draft) == imported_block.id
    assert imported_draft.status == "draft"
    assert imported_draft.validation_errors == []
    assert imported_draft.last_validated_at is None
    assert imported_draft.apply_count == 0
    assert imported_draft.last_applied_at is None


def test_delete_project_removes_project_structure_drafts(client_and_session):
    client, session = client_and_session
    project, _, draft = seed_project_with_draft(session)
    draft_id = draft.id
    project_id = project.id

    response = client.delete(f"/api/projects/{project_id}")
    assert response.status_code == 200

    deleted_draft = session.query(ProjectStructureDraft).filter(ProjectStructureDraft.id == draft_id).first()
    deleted_project = session.query(Project).filter(Project.id == project_id).first()

    assert deleted_draft is None
    assert deleted_project is None
