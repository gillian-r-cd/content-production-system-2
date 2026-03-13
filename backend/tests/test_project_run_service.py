import asyncio
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import ContentBlock, Project, ProjectStructureDraft
from core.project_structure_apply_service import apply_project_structure_draft
from core.project_run_service import list_ready_blocks, run_project_blocks


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


def create_project(session):
    project = Project(
        id="project-1",
        name="Run Service Project",
        current_phase="intent",
        phase_order=["intent"],
        phase_status={"intent": "pending"},
    )
    session.add(project)
    session.commit()
    return project


def test_list_ready_blocks_respects_mode(db_session):
    project = create_project(db_session)
    completed_dep = ContentBlock(
        id="dep-1",
        project_id=project.id,
        parent_id=None,
        name="依赖",
        block_type="field",
        depth=0,
        order_index=0,
        content="已有内容",
        status="completed",
    )
    auto_block = ContentBlock(
        id="auto-1",
        project_id=project.id,
        parent_id=None,
        name="自动块",
        block_type="field",
        depth=0,
        order_index=1,
        status="pending",
        auto_generate=True,
        depends_on=["dep-1"],
    )
    manual_block = ContentBlock(
        id="manual-1",
        project_id=project.id,
        parent_id=None,
        name="手动块",
        block_type="field",
        depth=0,
        order_index=2,
        status="pending",
        auto_generate=False,
        depends_on=["dep-1"],
    )
    root_ready = ContentBlock(
        id="root-ready",
        project_id=project.id,
        parent_id=None,
        name="无依赖块",
        block_type="field",
        depth=0,
        order_index=3,
        status="pending",
        auto_generate=False,
        depends_on=[],
    )
    db_session.add_all([completed_dep, auto_block, manual_block, root_ready])
    db_session.commit()

    auto_ids = list_ready_blocks(project_id=project.id, mode="auto_trigger", db=db_session)
    all_ids = list_ready_blocks(project_id=project.id, mode="start_all_ready", db=db_session)

    assert auto_ids == ["auto-1"]
    assert set(all_ids) == {"auto-1", "manual-1", "root-ready"}


def test_list_ready_blocks_only_blocks_unanswered_required_questions(db_session):
    project = create_project(db_session)
    optional_only = ContentBlock(
        id="optional-only",
        project_id=project.id,
        parent_id=None,
        name="选答块",
        block_type="field",
        depth=0,
        order_index=0,
        status="pending",
        pre_questions=[
            {"id": "q-1", "question": "补充背景", "required": False},
        ],
        pre_answers={},
    )
    required_missing = ContentBlock(
        id="required-missing",
        project_id=project.id,
        parent_id=None,
        name="必答未填块",
        block_type="field",
        depth=0,
        order_index=1,
        status="pending",
        pre_questions=[
            {"id": "q-2", "question": "核心目标", "required": True},
        ],
        pre_answers={},
    )
    required_answered = ContentBlock(
        id="required-answered",
        project_id=project.id,
        parent_id=None,
        name="必答已填块",
        block_type="field",
        depth=0,
        order_index=2,
        status="pending",
        pre_questions=[
            {"id": "q-3", "question": "受众是谁", "required": True},
        ],
        pre_answers={"q-3": "创业者"},
    )
    db_session.add_all([optional_only, required_missing, required_answered])
    db_session.commit()

    ready_ids = list_ready_blocks(project_id=project.id, mode="start_all_ready", db=db_session)

    assert set(ready_ids) == {"optional-only", "required-answered"}


def test_list_ready_blocks_includes_stale_blocks_and_blocks_on_stale_dependencies(db_session):
    project = create_project(db_session)
    fresh_dep = ContentBlock(
        id="fresh-dep",
        project_id=project.id,
        parent_id=None,
        name="最新依赖",
        block_type="field",
        depth=0,
        order_index=0,
        content="最新内容",
        status="completed",
    )
    stale_auto = ContentBlock(
        id="stale-auto",
        project_id=project.id,
        parent_id=None,
        name="待自动重生成块",
        block_type="field",
        depth=0,
        order_index=1,
        content="旧内容",
        status="completed",
        auto_generate=True,
        need_review=False,
        needs_regeneration=True,
        depends_on=["fresh-dep"],
    )
    stale_manual = ContentBlock(
        id="stale-manual",
        project_id=project.id,
        parent_id=None,
        name="待手动重生成块",
        block_type="field",
        depth=0,
        order_index=2,
        content="旧内容",
        status="completed",
        auto_generate=False,
        need_review=False,
        needs_regeneration=True,
        depends_on=["fresh-dep"],
    )
    blocked_downstream = ContentBlock(
        id="blocked-downstream",
        project_id=project.id,
        parent_id=None,
        name="被 stale 依赖阻塞的下游块",
        block_type="field",
        depth=0,
        order_index=3,
        content="旧内容",
        status="completed",
        auto_generate=True,
        need_review=False,
        needs_regeneration=True,
        depends_on=["stale-auto"],
    )
    db_session.add_all([fresh_dep, stale_auto, stale_manual, blocked_downstream])
    db_session.commit()

    auto_ids = list_ready_blocks(project_id=project.id, mode="auto_trigger", db=db_session)
    all_ids = list_ready_blocks(project_id=project.id, mode="start_all_ready", db=db_session)

    assert auto_ids == ["stale-auto"]
    assert set(all_ids) == {"stale-auto", "stale-manual"}


def test_run_project_blocks_scans_multiple_rounds(db_session, monkeypatch):
    from core import project_run_service as run_service

    project = create_project(db_session)
    first = ContentBlock(
        id="field-1",
        project_id=project.id,
        parent_id=None,
        name="第一块",
        block_type="field",
        depth=0,
        order_index=0,
        status="pending",
        depends_on=[],
    )
    second = ContentBlock(
        id="field-2",
        project_id=project.id,
        parent_id=None,
        name="第二块",
        block_type="field",
        depth=0,
        order_index=1,
        status="pending",
        depends_on=["field-1"],
    )
    db_session.add_all([first, second])
    db_session.commit()

    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_session.get_bind(),
    )

    async def fake_generate_block_content_sync(*, block_id: str, db):
        block = db.query(ContentBlock).filter(ContentBlock.id == block_id).first()
        block.content = f"{block.name} 内容"
        block.status = "completed"
        db.commit()
        return {"block_id": block_id, "status": "completed", "content": block.content}

    monkeypatch.setattr(run_service, "get_session_maker", lambda: session_factory)
    monkeypatch.setattr(run_service, "generate_block_content_sync", fake_generate_block_content_sync)

    result = asyncio.run(run_project_blocks(
        project_id=project.id,
        mode="start_all_ready",
        max_concurrency=2,
    ))

    assert result["started_count"] == 2
    assert result["completed_count"] == 2
    assert result["failed_count"] == 0
    assert len(result["rounds"]) == 2
    assert result["rounds"][0]["started_ids"] == ["field-1"]
    assert result["rounds"][1]["started_ids"] == ["field-2"]


def test_run_project_blocks_reprocesses_stale_chain_in_dependency_order(db_session, monkeypatch):
    from core import project_run_service as run_service

    project = create_project(db_session)
    source = ContentBlock(
        id="source",
        project_id=project.id,
        parent_id=None,
        name="上游块",
        block_type="field",
        depth=0,
        order_index=0,
        status="completed",
        content="最新上游内容",
    )
    middle = ContentBlock(
        id="middle",
        project_id=project.id,
        parent_id=None,
        name="中间块",
        block_type="field",
        depth=0,
        order_index=1,
        status="completed",
        content="旧中间内容",
        auto_generate=True,
        need_review=False,
        needs_regeneration=True,
        depends_on=["source"],
    )
    downstream = ContentBlock(
        id="downstream",
        project_id=project.id,
        parent_id=None,
        name="下游块",
        block_type="field",
        depth=0,
        order_index=2,
        status="completed",
        content="旧下游内容",
        auto_generate=True,
        need_review=False,
        needs_regeneration=True,
        depends_on=["middle"],
    )
    db_session.add_all([source, middle, downstream])
    db_session.commit()

    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_session.get_bind(),
    )

    async def fake_generate_block_content_sync(*, block_id: str, db):
        block = db.query(ContentBlock).filter(ContentBlock.id == block_id).first()
        block.content = f"{block.name} 新内容"
        block.status = "completed"
        block.needs_regeneration = False
        db.commit()
        return {"block_id": block_id, "status": "completed", "content": block.content}

    monkeypatch.setattr(run_service, "get_session_maker", lambda: session_factory)
    monkeypatch.setattr(run_service, "generate_block_content_sync", fake_generate_block_content_sync)

    result = asyncio.run(run_project_blocks(
        project_id=project.id,
        mode="auto_trigger",
        max_concurrency=2,
    ))

    db_session.refresh(middle)
    db_session.refresh(downstream)

    assert result["started_count"] == 2
    assert result["completed_count"] == 2
    assert result["failed_count"] == 0
    assert len(result["rounds"]) == 2
    assert result["rounds"][0]["started_ids"] == ["middle"]
    assert result["rounds"][1]["started_ids"] == ["downstream"]
    assert middle.needs_regeneration is False
    assert downstream.needs_regeneration is False


def test_run_project_blocks_handles_auto_split_applied_blocks(db_session, monkeypatch):
    from core import project_run_service as run_service

    project = create_project(db_session)
    draft = ProjectStructureDraft(
        id="draft-run-1",
        project_id=project.id,
        draft_type="auto_split",
        name="自动拆分内容",
        status="validated",
        validation_errors=[],
        last_validated_at=datetime.now(),
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
                            "ai_prompt": "请基于源内容生成摘要",
                            "auto_generate": True,
                            "draft_dependency_refs": [
                                {"ref_type": "chunk_source", "chunk_id": "current"},
                            ],
                            "children": [],
                        }
                    ],
                }
            ],
            "shared_root_nodes": [],
            "aggregate_root_nodes": [],
        },
    )
    db_session.add(draft)
    db_session.commit()

    apply_project_structure_draft(draft=draft, db=db_session)

    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_session.get_bind(),
    )

    async def fake_generate_block_content_sync(*, block_id: str, db):
        block = db.query(ContentBlock).filter(ContentBlock.id == block_id).first()
        block.content = "自动生成的摘要内容"
        block.status = "completed"
        db.commit()
        return {"block_id": block_id, "status": "completed", "content": block.content}

    monkeypatch.setattr(run_service, "get_session_maker", lambda: session_factory)
    monkeypatch.setattr(run_service, "generate_block_content_sync", fake_generate_block_content_sync)

    result = asyncio.run(run_project_blocks(
        project_id=project.id,
        mode="start_all_ready",
        max_concurrency=2,
    ))

    summary_block = db_session.query(ContentBlock).filter(
        ContentBlock.project_id == project.id,
        ContentBlock.name == "摘要",
    ).first()

    assert result["started_count"] == 1
    assert result["completed_count"] == 1
    assert result["failed_count"] == 0
    assert result["rounds"][0]["started_ids"] == [summary_block.id]
    assert summary_block is not None
    assert summary_block.status == "completed"
    assert summary_block.content == "自动生成的摘要内容"
