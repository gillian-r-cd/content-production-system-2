# 功能: 覆盖内容树导出、保存模板、JSON 追加导入 API 的主链语义
# 主要测试: 项目级 Markdown/模板、节点级 bundle/模板、项目级 JSON 追加导入
# 数据结构: FastAPI TestClient + 内存数据库中的 Project / ContentBlock / FieldTemplate

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from core.models import ContentBlock, FieldTemplate, Project, generate_uuid
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


def test_project_markdown_export_and_project_template_save(client_and_session):
    client, session = client_and_session
    project = Project(id=generate_uuid(), name="导出项目")
    session.add(project)
    session.flush()

    group = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="章节组",
        block_type="group",
        depth=0,
        order_index=0,
    )
    field = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=group.id,
        name="正文块",
        block_type="field",
        depth=1,
        order_index=0,
        content="这里是正文内容。",
    )
    loose = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="结尾块",
        block_type="field",
        depth=0,
        order_index=1,
        content="收尾内容。",
    )
    session.add_all([group, field, loose])
    session.commit()

    markdown_resp = client.get(f"/api/projects/{project.id}/export-markdown")
    assert markdown_resp.status_code == 200
    markdown = markdown_resp.json()["markdown"]
    assert "# 导出项目" in markdown
    assert "## 章节组" in markdown
    assert "### 正文块" in markdown
    assert "这里是正文内容。" in markdown

    save_resp = client.post(
        f"/api/projects/{project.id}/save-as-field-template",
        json={
            "name": "项目模板",
            "description": "来自项目整树",
            "category": "测试",
        },
    )
    assert save_resp.status_code == 200
    body = save_resp.json()
    assert body["template"]["name"] == "项目模板"
    assert len(body["template"]["root_nodes"]) == 2

    template = session.query(FieldTemplate).filter(FieldTemplate.name == "项目模板").first()
    assert template is not None
    assert len(template.root_nodes or []) == 2


def test_block_bundle_export_and_block_template_save_warns_on_external_deps(client_and_session):
    client, session = client_and_session
    project = Project(id=generate_uuid(), name="节点导出项目")
    session.add(project)
    session.flush()

    external = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="外部依赖块",
        block_type="field",
        depth=0,
        order_index=0,
        content="外部内容",
    )
    group = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="专题组",
        block_type="group",
        depth=0,
        order_index=1,
    )
    child = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=group.id,
        name="专题正文",
        block_type="field",
        depth=1,
        order_index=0,
        content="专题内容",
        depends_on=[external.id],
    )
    session.add_all([external, group, child])
    session.commit()

    export_resp = client.get(f"/api/blocks/{group.id}/export-json")
    assert export_resp.status_code == 200
    bundle = export_resp.json()
    assert bundle["type"] == "content_block_bundle"
    assert bundle["meta"]["has_external_dependencies"] is True
    assert len(bundle["content_blocks"]) == 2

    save_resp = client.post(
        f"/api/blocks/{group.id}/save-as-field-template",
        json={
            "name": "专题模板",
            "description": "来自专题组",
            "category": "测试",
        },
    )
    assert save_resp.status_code == 200
    data = save_resp.json()
    assert data["warnings"]

    template = session.query(FieldTemplate).filter(FieldTemplate.name == "专题模板").first()
    assert template is not None
    root = template.root_nodes[0]
    child_node = root["children"][0]
    assert child_node["depends_on_template_node_ids"] == []


def test_import_content_tree_json_appends_roots_and_remaps_internal_dependencies(client_and_session):
    client, session = client_and_session
    project = Project(id=generate_uuid(), name="导入目标项目")
    session.add(project)
    session.flush()

    existing = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        name="现有根节点",
        block_type="group",
        depth=0,
        order_index=0,
    )
    session.add(existing)
    session.commit()

    imported_root_a = "import-root-a"
    imported_root_b = "import-root-b"
    imported_child = "import-child"

    import_resp = client.post(
        f"/api/projects/{project.id}/import-content-tree-json",
        json={
            "data": {
                "export_version": "2.0",
                "project": {"id": "source-project", "name": "源项目"},
                "content_blocks": [
                    {
                        "id": imported_root_a,
                        "project_id": "source-project",
                        "parent_id": None,
                        "name": "导入根A",
                        "block_type": "field",
                        "depth": 0,
                        "order_index": 0,
                        "content": "A",
                        "status": "completed",
                        "ai_prompt": "",
                        "constraints": {},
                        "pre_questions": [],
                        "pre_answers": {},
                        "depends_on": [],
                        "special_handler": None,
                        "need_review": True,
                        "auto_generate": False,
                        "is_collapsed": False,
                    },
                    {
                        "id": imported_root_b,
                        "project_id": "source-project",
                        "parent_id": None,
                        "name": "导入根B",
                        "block_type": "group",
                        "depth": 0,
                        "order_index": 1,
                        "content": "",
                        "status": "pending",
                        "ai_prompt": "",
                        "constraints": {},
                        "pre_questions": [],
                        "pre_answers": {},
                        "depends_on": [],
                        "special_handler": None,
                        "need_review": True,
                        "auto_generate": False,
                        "is_collapsed": False,
                    },
                    {
                        "id": imported_child,
                        "project_id": "source-project",
                        "parent_id": imported_root_b,
                        "name": "导入子节点",
                        "block_type": "field",
                        "depth": 1,
                        "order_index": 0,
                        "content": "child",
                        "status": "pending",
                        "ai_prompt": "",
                        "constraints": {},
                        "pre_questions": [],
                        "pre_answers": {},
                        "depends_on": [imported_root_a, "missing-dependency"],
                        "special_handler": None,
                        "need_review": True,
                        "auto_generate": False,
                        "is_collapsed": False,
                    },
                ],
            }
        },
    )
    assert import_resp.status_code == 200
    result = import_resp.json()
    assert result["blocks_created"] == 3
    assert result["warning_count"] == 1

    top_level_blocks = (
        session.query(ContentBlock)
        .filter(
            ContentBlock.project_id == project.id,
            ContentBlock.parent_id == None,  # noqa: E711
            ContentBlock.deleted_at == None,  # noqa: E711
        )
        .order_by(ContentBlock.order_index.asc())
        .all()
    )
    assert [block.name for block in top_level_blocks] == ["现有根节点", "导入根A", "导入根B"]

    imported_root_a_block = next(block for block in top_level_blocks if block.name == "导入根A")
    imported_root_b_block = next(block for block in top_level_blocks if block.name == "导入根B")
    imported_child_block = (
        session.query(ContentBlock)
        .filter(ContentBlock.parent_id == imported_root_b_block.id, ContentBlock.name == "导入子节点")
        .first()
    )
    assert imported_child_block is not None
    assert imported_child_block.depends_on == [imported_root_a_block.id]
