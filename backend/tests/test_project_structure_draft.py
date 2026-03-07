import asyncio
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import ContentBlock, Project, ProjectStructureDraft
from core.project_split_service import split_source_text
from core.project_structure_apply_service import apply_project_structure_draft
from core.project_structure_compiler import compile_project_structure_draft


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


def create_project_with_existing_block(session):
    project = Project(
        id="project-1",
        name="Test Project",
        current_phase="intent",
        phase_order=["intent"],
        phase_status={"intent": "pending"},
    )
    existing_block = ContentBlock(
        id="existing-field",
        project_id=project.id,
        parent_id=None,
        name="已有内容块",
        block_type="field",
        depth=0,
        order_index=0,
        status="completed",
        content="已有上下文",
    )
    session.add(project)
    session.add(existing_block)
    session.commit()
    return project, existing_block


def test_compile_project_structure_draft_builds_batch_tree_and_dependencies(db_session):
    project, existing_block = create_project_with_existing_block(db_session)
    draft = ProjectStructureDraft(
        id="draft-1",
        project_id=project.id,
        draft_type="auto_split",
        name="自动拆分内容",
        draft_payload={
            "chunks": [
                {"chunk_id": "chunk-1", "title": "片段一", "content": "第一段内容", "order_index": 0},
                {"chunk_id": "chunk-2", "title": "片段二", "content": "第二段内容", "order_index": 1},
            ],
            "plans": [
                {
                    "plan_id": "plan-1",
                    "name": "摘要方案",
                    "target_chunk_ids": ["chunk-1", "chunk-2"],
                    "root_nodes": [
                        {
                            "template_node_id": "summary-node",
                            "name": "摘要",
                            "block_type": "field",
                            "draft_dependency_refs": [
                                {"ref_type": "chunk_source", "chunk_id": "current"},
                                {"ref_type": "shared_node", "node_id": "shared-context"},
                                {"ref_type": "project_block", "block_id": existing_block.id},
                            ],
                        }
                    ],
                }
            ],
            "shared_root_nodes": [
                {
                    "template_node_id": "shared-context",
                    "name": "共享背景",
                    "block_type": "field",
                    "content": "公共信息",
                }
            ],
            "aggregate_root_nodes": [
                {
                    "template_node_id": "aggregate-node",
                    "name": "总汇",
                    "block_type": "field",
                    "draft_dependency_refs": [
                        {"ref_type": "chunk_plan_node", "chunk_id": "chunk-1", "node_id": "summary-node"},
                        {"ref_type": "chunk_plan_node", "chunk_id": "chunk-2", "node_id": "summary-node"},
                    ],
                }
            ],
        },
    )

    result = compile_project_structure_draft(
        draft,
        existing_project_blocks=[existing_block],
    )

    assert result.validation_errors == []
    assert result.summary["chunk_count"] == 2
    assert result.summary["plan_count"] == 1

    batch_group = result.root_nodes[0]
    assert batch_group["block_type"] == "group"
    assert [child["name"] for child in batch_group["children"]] == ["共享结构", "片段一", "片段二", "聚合结构"]

    chunk_one_group = batch_group["children"][1]
    chunk_one_source = chunk_one_group["children"][0]
    chunk_one_summary = chunk_one_group["children"][1]
    assert chunk_one_source["name"] == "片段一"
    assert len(chunk_one_summary["depends_on_template_node_ids"]) == 2
    assert chunk_one_summary["external_depends_on_block_ids"] == [existing_block.id]

    aggregate_group = batch_group["children"][-1]
    aggregate_node = aggregate_group["children"][0]
    assert len(aggregate_node["depends_on_template_node_ids"]) == 2


def test_apply_project_structure_draft_creates_blocks_and_updates_metadata(db_session):
    project, _ = create_project_with_existing_block(db_session)
    draft = ProjectStructureDraft(
        id="draft-2",
        project_id=project.id,
        draft_type="auto_split",
        name="自动拆分内容",
        status="validated",
        last_validated_at=datetime.now(),
        validation_errors=[],
        draft_payload={
            "chunks": [
                {"chunk_id": "chunk-1", "title": "片段一", "content": "第一段内容", "order_index": 0},
            ],
            "plans": [],
            "shared_root_nodes": [],
            "aggregate_root_nodes": [],
        },
    )
    db_session.add(draft)
    db_session.commit()

    result = apply_project_structure_draft(draft=draft, db=db_session)

    db_session.refresh(draft)
    created_blocks = db_session.query(ContentBlock).filter(
        ContentBlock.project_id == project.id,
        ContentBlock.name.in_(["自动拆分内容批次", "片段一"]),
    ).all()

    assert result["blocks_created"] == 3
    assert draft.apply_count == 1
    assert draft.status == "applied"
    assert draft.last_applied_at is not None
    assert len(created_blocks) >= 2


def test_apply_project_structure_draft_resolves_draft_dependencies_to_block_ids(db_session):
    project, existing_block = create_project_with_existing_block(db_session)
    draft = ProjectStructureDraft(
        id="draft-3",
        project_id=project.id,
        draft_type="auto_split",
        name="自动拆分内容",
        status="validated",
        last_validated_at=datetime.now(),
        validation_errors=[],
        draft_payload={
            "chunks": [
                {"chunk_id": "chunk-1", "title": "片段一", "content": "第一段内容", "order_index": 0},
            ],
            "plans": [
                {
                    "plan_id": "plan-1",
                    "name": "摘要方案",
                    "target_chunk_ids": ["chunk-1"],
                    "root_nodes": [
                        {
                            "template_node_id": "summary-node",
                            "name": "摘要",
                            "block_type": "field",
                            "draft_dependency_refs": [
                                {"ref_type": "chunk_source", "chunk_id": "current"},
                                {"ref_type": "shared_node", "node_id": "shared-context"},
                                {"ref_type": "project_block", "block_id": existing_block.id},
                            ],
                        }
                    ],
                }
            ],
            "shared_root_nodes": [
                {
                    "template_node_id": "shared-context",
                    "name": "共享背景",
                    "block_type": "field",
                    "content": "公共信息",
                }
            ],
            "aggregate_root_nodes": [],
        },
    )
    db_session.add(draft)
    db_session.commit()

    apply_project_structure_draft(draft=draft, db=db_session)

    shared_block = db_session.query(ContentBlock).filter(
        ContentBlock.project_id == project.id,
        ContentBlock.name == "共享背景",
    ).first()
    source_block = db_session.query(ContentBlock).filter(
        ContentBlock.project_id == project.id,
        ContentBlock.name == "片段一",
        ContentBlock.block_type == "field",
        ContentBlock.parent_id.isnot(None),
    ).first()
    summary_block = db_session.query(ContentBlock).filter(
        ContentBlock.project_id == project.id,
        ContentBlock.name == "摘要",
    ).first()

    assert shared_block is not None
    assert source_block is not None
    assert summary_block is not None
    assert set(summary_block.depends_on or []) == {existing_block.id, shared_block.id, source_block.id}


def test_apply_project_structure_draft_rejects_unvalidated_draft(db_session):
    project, _ = create_project_with_existing_block(db_session)
    draft = ProjectStructureDraft(
        id="draft-unvalidated",
        project_id=project.id,
        draft_type="auto_split",
        name="自动拆分内容",
        status="draft",
        validation_errors=[],
        last_validated_at=None,
        draft_payload={
            "chunks": [
                {"chunk_id": "chunk-1", "title": "片段一", "content": "第一段内容", "order_index": 0},
            ],
            "plans": [],
            "shared_root_nodes": [],
            "aggregate_root_nodes": [],
        },
    )
    db_session.add(draft)
    db_session.commit()

    with pytest.raises(ValueError, match="先执行校验"):
        apply_project_structure_draft(draft=draft, db=db_session)


def test_compile_project_structure_draft_detects_cycle_dependencies(db_session):
    project, _ = create_project_with_existing_block(db_session)
    draft = ProjectStructureDraft(
        id="draft-cycle",
        project_id=project.id,
        draft_type="auto_split",
        name="自动拆分内容",
        draft_payload={
            "chunks": [
                {"chunk_id": "chunk-1", "title": "片段一", "content": "第一段内容", "order_index": 0},
            ],
            "plans": [
                {
                    "plan_id": "plan-cycle",
                    "name": "循环方案",
                    "target_chunk_ids": ["chunk-1"],
                    "root_nodes": [
                        {
                            "template_node_id": "node-a",
                            "name": "节点A",
                            "block_type": "field",
                            "depends_on_template_node_ids": ["node-b"],
                        },
                        {
                            "template_node_id": "node-b",
                            "name": "节点B",
                            "block_type": "field",
                            "depends_on_template_node_ids": ["node-a"],
                        },
                    ],
                }
            ],
            "shared_root_nodes": [],
            "aggregate_root_nodes": [],
        },
    )

    result = compile_project_structure_draft(draft, existing_project_blocks=[])

    assert any("循环依赖" in error for error in result.validation_errors)
    assert any("节点A" in error and "节点B" in error for error in result.validation_errors)


def test_split_source_text_supports_count_and_chars_modes():
    source_text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"

    count_chunks = asyncio.run(split_source_text(source_text, {"mode": "count", "target_count": 2}))
    chars_chunks = asyncio.run(split_source_text(source_text, {"mode": "chars", "max_chars_per_chunk": 8}))

    assert len(count_chunks) == 2
    assert len(chars_chunks) >= 2
    assert all(chunk["title"] for chunk in count_chunks)
    assert all(chunk["content"] for chunk in chars_chunks)


def test_split_source_text_count_mode_without_overlap_keeps_adjacent_chunks_disjoint():
    source_text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"

    count_chunks = asyncio.run(split_source_text(source_text, {
        "mode": "count",
        "target_count": 3,
        "overlap_chars": 0,
    }))

    assert [chunk["content"] for chunk in count_chunks] == [
        "第一段内容。",
        "第二段内容。",
        "第三段内容。",
    ]


def test_split_source_text_count_mode_with_overlap_still_allows_explicit_repetition():
    source_text = "Alpha part one. Beta part two. Gamma part three."

    count_chunks = asyncio.run(split_source_text(source_text, {
        "mode": "count",
        "target_count": 2,
        "overlap_chars": 8,
    }))

    assert len(count_chunks) == 2
    assert sum(len(chunk["content"]) for chunk in count_chunks) > len(source_text)


def test_split_source_text_count_mode_without_overlap_keeps_plain_text_contiguous():
    source_text = "ABCDEFGHIJKL"

    count_chunks = asyncio.run(split_source_text(source_text, {
        "mode": "count",
        "target_count": 3,
        "overlap_chars": 0,
    }))

    assert "".join(chunk["content"] for chunk in count_chunks) == source_text
