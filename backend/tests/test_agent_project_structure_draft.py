# backend/tests/test_agent_project_structure_draft.py
# 功能: 验证 Agent 草稿 tool 与结构阅读链正确理解自动拆分产物
# 主要测试: manage_project_structure_draft / architecture_reader / 重名引用消歧

import json
import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.content_block_reference import DuplicateBlockReferenceError, find_block_by_identifier
from core.database import Base
from core.models import ContentBlock, Project, ProjectStructureDraft, generate_uuid
from core.tools.architecture_reader import get_project_architecture, get_content_block_tree


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def seed_project_with_auto_split_artifacts(session):
    project = Project(
        id=generate_uuid(),
        name="Auto Split Agent Project",
        current_phase="intent",
        phase_order=["intent"],
        phase_status={"intent": "pending"},
    )
    root_group = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="自动拆分内容批次",
        block_type="group",
        depth=0,
        order_index=0,
        status="completed",
    )
    chunk_group = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=root_group.id,
        name="内容片段 01",
        block_type="group",
        depth=1,
        order_index=0,
        status="completed",
    )
    field_block = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=chunk_group.id,
        name="摘要",
        block_type="field",
        depth=2,
        order_index=0,
        status="pending",
        content="",
        auto_generate=True,
    )
    draft = ProjectStructureDraft(
        id=generate_uuid(),
        project_id=project.id,
        draft_type="auto_split",
        name="自动拆分内容",
        status="draft",
        source_text="alpha\n\nbeta",
        split_config={"mode": "count", "target_count": 2, "overlap_chars": 0},
        draft_payload={
            "chunks": [{"chunk_id": "chunk-1", "title": "内容片段 01", "content": "alpha"}],
            "plans": [],
            "shared_root_nodes": [],
            "aggregate_root_nodes": [],
            "ui_state": {},
        },
    )
    session.add_all([project, root_group, chunk_group, field_block, draft])
    session.commit()
    return project, draft, root_group, chunk_group, field_block


def test_manage_project_structure_draft_tool_reads_and_splits(db_session, monkeypatch):
    from core import agent_tools

    project, _, _, _, _ = seed_project_with_auto_split_artifacts(db_session)
    monkeypatch.setattr(agent_tools, "_get_db", lambda: db_session)

    read_result = asyncio.run(agent_tools.manage_project_structure_draft.ainvoke(
        {"operation": "read"},
        config={"configurable": {"project_id": project.id}},
    ))
    read_payload = json.loads(read_result)
    assert read_payload["status"] == "draft_read"
    assert read_payload["draft_summary"]["chunk_count"] == 1

    split_result = asyncio.run(agent_tools.manage_project_structure_draft.ainvoke(
        {
            "operation": "split",
            "source_text": "part one\n\npart two",
            "split_config_json": json.dumps({
                "mode": "count",
                "target_count": 2,
                "overlap_chars": 0,
            }),
        },
        config={"configurable": {"project_id": project.id}},
    ))
    split_payload = json.loads(split_result)
    assert split_payload["status"] == "draft_split"
    assert len(split_payload["chunks"]) == 2
    assert split_payload["draft_summary"]["chunk_count"] == 2


def test_find_block_by_identifier_rejects_ambiguous_names(db_session):
    project = Project(
        id=generate_uuid(),
        name="Duplicate Names",
        current_phase="intent",
        phase_order=["intent"],
        phase_status={"intent": "pending"},
    )
    db_session.add(project)
    db_session.flush()
    db_session.add_all([
        ContentBlock(
            id=generate_uuid(),
            project_id=project.id,
            name="重复块",
            block_type="field",
            depth=0,
            order_index=0,
            status="pending",
        ),
        ContentBlock(
            id=generate_uuid(),
            project_id=project.id,
            name="重复块",
            block_type="field",
            depth=0,
            order_index=1,
            status="pending",
        ),
    ])
    db_session.commit()

    with pytest.raises(DuplicateBlockReferenceError):
        find_block_by_identifier(db_session, project.id, "重复块")


def test_architecture_reader_exposes_auto_split_paths_and_draft_overview(db_session):
    project, _, _, _, field_block = seed_project_with_auto_split_artifacts(db_session)

    architecture = get_project_architecture(project.id, db_session)
    tree = get_content_block_tree(project.id, db_session)

    assert architecture is not None
    assert architecture.auto_split_draft is not None
    assert architecture.auto_split_draft["chunk_count"] == 1
    assert any("id:" in block.reference_key for block in architecture.content_blocks or [])

    flattened = []

    def collect(nodes):
        for node in nodes:
            flattened.append(node)
            collect(node.get("children", []))

    collect(tree)
    target = next(node for node in flattened if node["id"] == field_block.id)
    assert target["path"].endswith("自动拆分内容批次 / 内容片段 01 / 摘要")
    assert target["reference_key"].endswith(f"id:{field_block.id}")
