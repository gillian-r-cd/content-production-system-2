# backend/tests/test_eval_runtime_locale_guard.py
# 功能: 守卫 Eval API/runtime 的日文 locale 文案与控制层提示不回流中文
# 主要测试: 创作者特质上下文标签、提示词生成 helper、Task 诊断摘要
# 数据结构:
#   - 内存数据库中的 Project / CreatorProfile
#   - `_generate_prompt_with_llm()` 捕获的 LLM 输入消息
#   - `_build_task_analysis_from_trials()` 的规则化输出

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.eval as eval_api
from core.database import Base
from core.models import CreatorProfile, EvalTaskV2, EvalTrialResultV2, Project, generate_uuid


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_get_creator_profile_uses_ja_labels(db_session):
    profile = CreatorProfile(
        id=generate_uuid(),
        name="日文创作者画像",
        stable_key="ja_profile_guard",
        locale="ja-JP",
        description="",
        traits={
            "tone": "端正で信頼感がある",
            "vocabulary": "業務用語を正確に使う",
            "personality": "落ち着いて論理的",
        },
    )
    project = Project(
        id=generate_uuid(),
        name="日本語評価プロジェクト",
        locale="ja-JP",
        creator_profile_id=profile.id,
    )
    db_session.add_all([profile, project])
    db_session.commit()

    text = eval_api._get_creator_profile(project, db_session)

    assert "トーン:" in text
    assert "語彙:" in text
    assert "人物像:" in text
    assert "语调:" not in text
    assert "词汇:" not in text
    assert "性格:" not in text


@pytest.mark.asyncio
async def test_generate_prompt_with_llm_uses_ja_prompt_labels(monkeypatch):
    captured = {}

    class DummyModel:
        async def ainvoke(self, messages):
            captured["system"] = messages[0].content
            captured["user"] = messages[1].content
            return SimpleNamespace(content='{"generated_prompt":"ok"}')

    monkeypatch.setattr("api.eval.get_chat_model", lambda temperature=0.7: DummyModel())

    prompt = await eval_api._generate_prompt_with_llm(
        "reviewer_prompt",
        {
            "locale": "ja-JP",
            "form_type": "review",
            "description": "",
            "project_context": "",
        },
    )

    assert captured["system"]
    assert captured["user"]
    assert "レビュー役プロンプト" in captured["user"]
    assert "視点レビュー" in captured["user"]
    for token in ["审查角色提示词", "视角审查", "未提供", "无"]:
        assert token not in captured["user"]


def test_build_task_analysis_from_trials_uses_ja_copy():
    task = EvalTaskV2(
        id=generate_uuid(),
        project_id=generate_uuid(),
        name="体験評価タスク",
    )
    row = EvalTrialResultV2(
        id=generate_uuid(),
        task_id=task.id,
        trial_config_id=generate_uuid(),
        project_id=task.project_id,
        batch_id="batch-ja",
        repeat_index=0,
        form_type="assessment",
        status="completed",
        dimension_scores={"構成": 6},
        grader_results=[
            {
                "comments": {"構成": "明確ではなく、改善余地があります。"},
                "feedback": "根拠を追加してください。",
            }
        ],
    )

    analysis = eval_api._build_task_analysis_from_trials(task, [row], "batch-ja", locale="ja-JP")

    assert "タスク「体験評価タスク」" in analysis.summary
    assert "共通パターン" in analysis.summary
    assert analysis.patterns[0]["title"] == "構成 は複数の Trial で低スコアです"
    assert analysis.suggestions[0]["title"] == "「構成」を優先改善"
    assert "構造化した表現" in analysis.suggestions[0]["detail"]
    assert "优先提升" not in analysis.suggestions[0]["title"]
    assert "任务「" not in analysis.summary
