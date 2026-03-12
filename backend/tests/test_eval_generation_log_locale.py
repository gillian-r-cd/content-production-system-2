# backend/tests/test_eval_generation_log_locale.py
# 功能: 验证日文项目在评估报告生成时写入 GenerationLog 的 prompt_input 不混入中文历史标签或控制文案
# 主要函数: test_eval_report_generation_logs_use_ja_locale_prompts
# 数据结构:
#   - 内存数据库中的 Project / ContentBlock / GenerationLog
#   - eval_report + eval_task_config 内容块

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.eval as eval_api
from core.database import Base, get_db
from core.models import ContentBlock, GenerationLog, Project, generate_uuid
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


@pytest.mark.asyncio
async def test_eval_report_generation_logs_use_ja_locale_prompts(client_and_session, monkeypatch):
    client, session = client_and_session

    project = Project(id=generate_uuid(), name="JA Eval Log Project", locale="ja-JP")
    session.add(project)
    session.flush()

    content_block = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=None,
        name="導入概要",
        block_type="field",
        content="このコンテンツは導入価値と進め方を説明します。",
        status="completed",
        order_index=1,
    )
    task_block = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=None,
        name="評価タスク設定",
        block_type="field",
        content=json.dumps(
            {
                "trials": [
                    {
                        "name": "顧客対話-佐藤",
                        "simulator_type": "consumer",
                        "interaction_mode": "dialogue",
                        "persona_config": {"name": "佐藤", "background": "導入担当者"},
                        "simulator_config": {"max_turns": 1, "locale": "ja-JP"},
                        "grader_config": {"type": "combined", "dimensions": [], "locale": "ja-JP"},
                        "order_index": 0,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        status="completed",
        special_handler="eval_task_config",
        order_index=2,
    )
    report_block = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=None,
        name="評価レポート",
        block_type="field",
        content="",
        status="pending",
        special_handler="eval_report",
        order_index=3,
    )
    session.add_all([content_block, task_block, report_block])
    session.commit()

    outputs = [
        "費用対効果はどの程度ですか？",
        "本文では導入価値を説明しています。",
        '{"scores":{"総合評価":7},"comments":{"総合評価":"価値は理解できる"},"problems_solved":["導入価値"],"problems_unsolved":["費用対効果"],"content_gaps":["定量根拠"],"would_recommend":false,"summary":"定量根拠が欲しい"}',
        '{"scores":{"対話の流暢さ":7,"課題解決効率":6,"情報伝達の有効性":7,"ユーザー体験":6},"comments":{"対話の流暢さ":"自然","課題解決効率":"やや不足","情報伝達の有効性":"概ね十分","ユーザー体験":"追加根拠が必要"},"feedback":"費用対効果の根拠を追加してください。"}',
    ]

    class FakeResp:
        def __init__(self, text):
            self.content = text
            self.usage_metadata = {"input_tokens": 11, "output_tokens": 6}

    async def fake_ainvoke_with_retry(_model, _messages):
        return FakeResp(outputs.pop(0))

    async def fake_run_diagnoser(*args, **kwargs):
        return (
            {
                "overview": "1件の対話を確認しました。",
                "strengths": ["課題意識は共有できている"],
                "improvements": ["定量根拠を補う"],
                "action_items": ["導入成果の数値例を追加する"],
                "summary": "根拠補強が必要です。",
            },
            None,
        )

    monkeypatch.setattr("core.tools.eval_engine.get_chat_model", lambda **kwargs: object())
    monkeypatch.setattr("core.llm.ainvoke_with_retry", fake_ainvoke_with_retry)
    monkeypatch.setattr(eval_api, "run_diagnoser", fake_run_diagnoser)

    response = client.post(f"/api/eval/generate-for-block/{report_block.id}")
    assert response.status_code == 200

    session.expire_all()
    logs = (
        session.query(GenerationLog)
        .filter(GenerationLog.project_id == project.id, GenerationLog.field_id == report_block.id)
        .all()
    )
    assert len(logs) >= 4

    prompt_inputs = "\n".join(str(log.prompt_input or "") for log in logs)
    assert "【あなたの役割】" in prompt_inputs
    assert "[相手(user)]" in prompt_inputs
    assert "ニーズ適合度" in prompt_inputs
    assert "你的角色" not in prompt_inputs
    assert "需求匹配度" not in prompt_inputs
    assert "对方(user)" not in prompt_inputs
    assert "我方(assistant)" not in prompt_inputs
