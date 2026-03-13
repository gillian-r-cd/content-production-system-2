# backend/tests/test_project_markdown_import_api.py
# 功能: 验证项目级 Markdown 导入 API 的解析规则、locale 文案与事务回滚
# 主要测试: heading_tree 批量导入、raw_file 回退、任一文件失败时整体回滚
# 数据结构: FastAPI TestClient + SQLite 内存数据库中的 Project / ContentBlock

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from core.models import Project, generate_uuid
from core.models.content_block import ContentBlock
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


def _seed_project(session, *, locale: str) -> Project:
    project = Project(id=generate_uuid(), name=f"Markdown {locale}", locale=locale)
    session.add(project)
    session.commit()
    return project


def test_import_markdown_files_builds_heading_tree_for_multiple_files(client_and_session):
    client, session = client_and_session
    project = _seed_project(session, locale="zh-CN")

    response = client.post(
        f"/api/projects/{project.id}/import-markdown-files",
        json={
            "import_mode": "heading_tree",
            "files": [
                {
                    "name": "overview.md",
                    "content": "开场说明\n\n# 第一章\n正文段落\n\n## 子节\n- 列表项\n\n```md\n# 代码块里的标题不应被解析\n```",
                },
                {
                    "name": "appendix.markdown",
                    "content": "# 附录\n附录正文",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_count"] == 2
    assert payload["root_count"] == 2
    assert payload["warning_count"] == 0

    session.expire_all()
    blocks = session.query(ContentBlock).filter(ContentBlock.project_id == project.id).order_by(
        ContentBlock.depth.asc(),
        ContentBlock.order_index.asc(),
        ContentBlock.created_at.asc(),
    ).all()
    names = [block.name for block in blocks]
    assert "overview" in names
    assert "appendix" in names
    assert "导言" in names
    assert "第一章" in names
    assert "子节" in names
    assert "附录" in names

    overview_root = next(block for block in blocks if block.name == "overview")
    appendix_root = next(block for block in blocks if block.name == "appendix")
    intro_block = next(block for block in blocks if block.name == "导言")
    chapter_block = next(block for block in blocks if block.name == "第一章")
    subsection_block = next(block for block in blocks if block.name == "子节")
    appendix_block = next(block for block in blocks if block.name == "附录")

    assert overview_root.block_type == "group"
    assert appendix_root.block_type == "group"
    assert intro_block.parent_id == overview_root.id
    assert intro_block.content == "开场说明"
    assert chapter_block.block_type == "group"
    assert chapter_block.content == "正文段落"
    assert chapter_block.parent_id == overview_root.id
    assert subsection_block.parent_id == chapter_block.id
    assert "# 代码块里的标题不应被解析" in subsection_block.content
    assert appendix_block.parent_id == appendix_root.id
    assert appendix_block.content == "附录正文"


def test_import_markdown_files_falls_back_to_raw_file_and_uses_project_locale(client_and_session):
    client, session = client_and_session
    project = _seed_project(session, locale="ja-JP")

    response = client.post(
        f"/api/projects/{project.id}/import-markdown-files",
        json={
            "import_mode": "heading_tree",
            "files": [
                {
                    "name": "notes.md",
                    "content": "見出しがない本文\n\n- 箇条書き",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["warning_count"] == 1
    assert "notes.md" in payload["warnings"][0]
    assert payload["files"][0]["mode_used"] == "raw_file"
    assert "Markdown ファイル" in payload["message"]

    session.expire_all()
    imported_blocks = session.query(ContentBlock).filter(ContentBlock.project_id == project.id).all()
    assert len(imported_blocks) == 1
    assert imported_blocks[0].name == "notes"
    assert imported_blocks[0].block_type == "field"
    assert imported_blocks[0].content == "見出しがない本文\n\n- 箇条書き"


def test_import_markdown_files_rolls_back_when_any_file_is_invalid(client_and_session):
    client, session = client_and_session
    project = _seed_project(session, locale="zh-CN")

    response = client.post(
        f"/api/projects/{project.id}/import-markdown-files",
        json={
            "import_mode": "heading_tree",
            "files": [
                {
                    "name": "valid.md",
                    "content": "# 标题\n正常内容",
                },
                {
                    "name": "",
                    "content": "# 标题\n这个文件应该触发失败",
                },
            ],
        },
    )

    assert response.status_code == 400
    assert "缺少有效文件名" in response.json()["detail"]

    session.expire_all()
    assert session.query(ContentBlock).filter(ContentBlock.project_id == project.id).count() == 0
