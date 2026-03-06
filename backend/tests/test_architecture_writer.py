# backend/tests/test_architecture_writer.py
# 功能: 测试 architecture_writer 的通用树节点操作
# 主要函数: test_add_node_under_group(), test_move_node_updates_depth_and_parent(), test_instantiate_template_under_parent()

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import Project, FieldTemplate
from core.models.content_block import ContentBlock
from core.tools.architecture_writer import add_node, remove_node, move_node, instantiate_template


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
        name="Test Project",
        current_phase="intent",
        phase_order=["intent", "research"],
        phase_status={"intent": "pending", "research": "pending"},
    )
    session.add(project)
    session.add(ContentBlock(
        id="phase-intent",
        project_id=project.id,
        parent_id=None,
        name="意图分析",
        block_type="phase",
        depth=0,
        order_index=0,
        status="pending",
    ))
    session.commit()
    return project


def test_add_node_under_group(db_session):
    project = create_project(db_session)
    parent = ContentBlock(
        id="group-1",
        project_id=project.id,
        parent_id="phase-intent",
        name="子分组",
        block_type="group",
        depth=1,
        order_index=0,
        status="pending",
    )
    db_session.add(parent)
    db_session.commit()

    result = add_node(
        project_id=project.id,
        name="新内容块",
        block_type="field",
        parent_id=parent.id,
        ai_prompt="生成提示词",
        db=db_session,
    )

    assert result.success is True
    block = db_session.query(ContentBlock).filter(ContentBlock.name == "新内容块").first()
    assert block is not None
    assert block.parent_id == parent.id
    assert block.depth == 2


def test_move_node_updates_depth_and_parent(db_session):
    project = create_project(db_session)
    source_parent = ContentBlock(
        id="group-a",
        project_id=project.id,
        parent_id="phase-intent",
        name="分组A",
        block_type="group",
        depth=1,
        order_index=0,
        status="pending",
    )
    target_parent = ContentBlock(
        id="group-b",
        project_id=project.id,
        parent_id="phase-intent",
        name="分组B",
        block_type="group",
        depth=1,
        order_index=1,
        status="pending",
    )
    child = ContentBlock(
        id="field-1",
        project_id=project.id,
        parent_id=source_parent.id,
        name="字段1",
        block_type="field",
        depth=2,
        order_index=0,
        status="pending",
    )
    db_session.add_all([source_parent, target_parent, child])
    db_session.commit()

    result = move_node(
        project_id=project.id,
        node_id=child.id,
        new_parent_id=target_parent.id,
        db=db_session,
    )

    assert result.success is True
    db_session.refresh(child)
    assert child.parent_id == target_parent.id
    assert child.depth == 2


def test_instantiate_template_under_parent(db_session):
    project = create_project(db_session)
    parent = ContentBlock(
        id="group-root",
        project_id=project.id,
        parent_id="phase-intent",
        name="模板挂载点",
        block_type="group",
        depth=1,
        order_index=0,
        status="pending",
    )
    template = FieldTemplate(
        id="template-1",
        name="测试模板",
        fields=[],
        root_nodes=[
            {
                "template_node_id": "node-1",
                "name": "模板字段",
                "block_type": "field",
                "ai_prompt": "提示词",
                "children": [],
            }
        ],
    )
    db_session.add_all([parent, template])
    db_session.commit()

    result = instantiate_template(
        project_id=project.id,
        template_id=template.id,
        parent_id=parent.id,
        db=db_session,
    )

    assert result.success is True
    created = db_session.query(ContentBlock).filter(ContentBlock.name == "模板字段").first()
    assert created is not None
    assert created.parent_id == parent.id


def test_add_node_top_level_phase_delegates_to_add_phase(db_session):
    """add_node with block_type=phase and parent_id=None should delegate to add_phase
    and update Project.phase_order accordingly."""
    project = create_project(db_session)
    original_order = list(project.phase_order)

    result = add_node(
        project_id=project.id,
        name="自定义阶段",
        block_type="phase",
        parent_id=None,
        db=db_session,
    )

    assert result.success is True
    db_session.refresh(project)
    # phase_order should now contain the new phase
    assert len(project.phase_order) == len(original_order) + 1
    # A new ContentBlock with block_type=phase should exist
    new_block = db_session.query(ContentBlock).filter(
        ContentBlock.project_id == project.id,
        ContentBlock.name == "自定义阶段",
        ContentBlock.block_type == "phase",
        ContentBlock.parent_id == None,  # noqa: E711
    ).first()
    assert new_block is not None


def test_remove_node_top_level_phase_delegates_to_remove_phase(db_session):
    """remove_node on a top-level phase block should delegate to remove_phase
    and clean up Project.phase_order."""
    project = create_project(db_session)
    assert "intent" in project.phase_order

    result = remove_node(
        project_id=project.id,
        node_id="phase-intent",
        db=db_session,
    )

    assert result.success is True
    db_session.refresh(project)
    assert "intent" not in project.phase_order


def test_move_node_top_level_phase_rejected(db_session):
    """move_node on a top-level phase should be rejected with guidance to use reorder_phases."""
    project = create_project(db_session)

    result = move_node(
        project_id=project.id,
        node_id="phase-intent",
        new_parent_id=None,
        new_order_index=1,
        db=db_session,
    )

    assert result.success is False
    assert "reorder_phases" in result.message
