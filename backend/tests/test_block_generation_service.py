# 功能: 覆盖内容块生成服务的 locale 链路，防止项目级运行再次因未定义的 locale 崩溃
# 主要测试: generate_block_content_sync
# 数据结构: Project / ContentBlock / mocked LLM response

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core import block_generation_service as generation_service
from core import config as config_module
from core import version_service
from core.database import Base
from core.locale_text import rt
from core.models import ContentBlock, CreatorProfile, Project


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


@pytest.mark.asyncio
async def test_generate_block_content_sync_uses_project_locale_in_human_prompt(db_session, monkeypatch):
    project = Project(
        id="project-ja",
        name="Japanese Project",
        locale="ja-JP",
        current_phase="intent",
        phase_order=["intent"],
        phase_status={"intent": "pending"},
    )
    block = ContentBlock(
        id="block-ja",
        project_id=project.id,
        parent_id=None,
        name="要約",
        block_type="field",
        depth=0,
        order_index=0,
        status="pending",
        need_review=False,
        ai_prompt="内容を要約してください",
    )
    db_session.add_all([project, block])
    db_session.commit()

    captured = {}

    monkeypatch.setattr(config_module, "validate_llm_config", lambda: None)
    monkeypatch.setattr(version_service, "save_content_version", lambda *args, **kwargs: None)
    monkeypatch.setattr(generation_service, "resolve_model", lambda model_override=None: "gpt-4o-mini")
    monkeypatch.setattr(generation_service, "get_chat_model", lambda model=None: object())

    async def fake_ainvoke_with_retry(_model, messages):
        captured["human"] = messages[1].content
        return SimpleNamespace(
            content="生成された内容",
            usage_metadata={"input_tokens": 12, "output_tokens": 18},
        )

    monkeypatch.setattr(generation_service, "ainvoke_with_retry", fake_ainvoke_with_retry)

    result = await generation_service.generate_block_content_sync(block_id=block.id, db=db_session)
    db_session.refresh(block)

    assert captured["human"] == rt("ja-JP", "block.generate.human", name="要約")
    assert result["status"] == "completed"
    assert block.status == "completed"
    assert block.content == "生成された内容"


def test_build_generation_system_prompt_injects_creator_profile_and_japanese_runtime_text():
    profile = CreatorProfile(
        id="creator-ja",
        name="知的で簡潔",
        locale="ja-JP",
        description="構造化して要点を伝える",
        traits={"tone": "落ち着いたビジネス文体"},
    )
    project = Project(
        id="project-ja",
        name="Japanese Project",
        locale="ja-JP",
        creator_profile=profile,
        creator_profile_id=profile.id,
        current_phase="produce_inner",
        phase_order=["produce_inner"],
        phase_status={"produce_inner": "pending"},
    )
    block = ContentBlock(
        id="block-ja",
        project_id=project.id,
        name="要約",
        block_type="field",
        depth=0,
        order_index=0,
        status="pending",
        ai_prompt="依存情報を踏まえて内容をまとめてください。",
    )

    prompt = generation_service.build_generation_system_prompt(
        block=block,
        project=project,
        dependency_content="参考本文",
    )

    assert "知的で簡潔" in prompt
    assert "落ち着いたビジネス文体" in prompt
    assert "## クリエイタープロファイル" in prompt
    assert "名前: 知的で簡潔" in prompt
    assert "トーン: 落ち着いたビジネス文体" in prompt
    assert "# 出力形式（必須）" in prompt
    assert "输出格式（必须遵守）" not in prompt
    assert "创作者特质" not in prompt


def test_resolve_dependencies_uses_japanese_runtime_error_copy():
    block = ContentBlock(
        id="target",
        project_id="project-ja",
        name="本文",
        block_type="field",
        depends_on=["dep-1"],
    )
    dependency = ContentBlock(
        id="dep-1",
        project_id="project-ja",
        name="前提",
        block_type="field",
        content="",
    )

    class DummyQuery:
        def __init__(self, dataset):
            self._dataset = dataset

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return self._dataset

        def first(self):
            return next((item for item in self._dataset if item.id == "dep-1"), None)

    class DummySession:
        def query(self, model):
            return DummyQuery([block, dependency])

        def flush(self):
            return None

    _, _, error = generation_service.resolve_dependencies(block, DummySession(), locale="ja-JP")

    assert error == "以下の依存コンテンツが未完了です: 前提"
