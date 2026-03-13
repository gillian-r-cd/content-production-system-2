# backend/tests/test_agent_reference_integrity.py
# 功能: 回归测试 Agent 引用链路不再对内容块正文做静默截断
# 主要测试: stream 引用拼接、rewrite_field 参考块、generate_field_content 依赖块、query_field 查询块
# 数据结构: FastAPI TestClient + SQLite 内存库中的 Project / AgentMode / ContentBlock

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.agent as agent_api
import core.agent_tools as agent_tools
import core.memory_service as memory_service
from core.database import Base, get_db
from core.models import AgentMode, Project, generate_uuid
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
        yield client, session, TestingSessionLocal
    finally:
        session.close()
        app.dependency_overrides.clear()


def _seed_project_mode_and_blocks(session):
    project = Project(id=generate_uuid(), name="Reference Integrity Project", locale="zh-CN")
    mode = AgentMode(
        id=generate_uuid(),
        project_id=project.id,
        name="assistant_runtime",
        display_name="助手",
        description="项目运行时助手",
        system_prompt="你是助手",
        icon="A",
        is_system=True,
        is_template=False,
        sort_order=0,
    )
    session.add_all([project, mode])
    session.commit()
    return project, mode


def _make_block(
    project_id: str,
    name: str,
    *,
    content: str,
    ai_prompt: str = "",
    depends_on=None,
    **overrides,
) -> ContentBlock:
    return ContentBlock(
        id=generate_uuid(),
        project_id=project_id,
        name=name,
        block_type="field",
        depth=0,
        order_index=0,
        content=content,
        status="completed",
        ai_prompt=ai_prompt,
        depends_on=depends_on or [],
        pre_questions=overrides.pop("pre_questions", []),
        pre_answers=overrides.pop("pre_answers", {}),
        need_review=overrides.pop("need_review", True),
        auto_generate=overrides.pop("auto_generate", False),
        model_override=overrides.pop("model_override", None),
        special_handler=overrides.pop("special_handler", None),
        constraints=overrides.pop("constraints", {}),
        guidance_input=overrides.pop("guidance_input", ""),
        guidance_output=overrides.pop("guidance_output", ""),
        **overrides,
    )


def _tool_config(project_id: str, mode_id: str = "assistant") -> dict:
    return {
        "configurable": {
            "project_id": project_id,
            "mode_id": mode_id,
            "thread_id": f"{project_id}:{mode_id}:conversation-1",
        }
    }


def test_stream_chat_keeps_full_reference_and_selection_content(client_and_session, monkeypatch):
    client, session, _ = client_and_session
    project, mode = _seed_project_mode_and_blocks(session)

    first_tail = "REF-ONE-TAIL-UNTRUNCATED"
    second_tail = "REF-TWO-TAIL-UNTRUNCATED"
    selection_tail = "SELECTION-BLOCK-TAIL-UNTRUNCATED"
    first_ref = _make_block(project.id, "引用一", content=("甲" * 2500) + first_tail)
    second_ref = _make_block(project.id, "引用二", content=("乙" * 2600) + second_tail)
    selection_block = _make_block(project.id, "正文块", content=("丙" * 3400) + selection_tail)
    session.add_all([first_ref, second_ref, selection_block])
    session.commit()

    async def fake_load_memory_context_async(*args, **kwargs):
        return ""

    class FakeGraph:
        async def astream_events(self, input_state, config=None, version=None):
            human_message = input_state["messages"][-1].content
            assert first_tail in human_message
            assert second_tail in human_message
            assert selection_tail in human_message
            assert "用户选中的文字片段" in human_message
            yield {
                "event": "on_chat_model_stream",
                "metadata": {"langgraph_node": "agent"},
                "data": {"chunk": AIMessageChunk(content="引用完整")},
            }

    async def fake_get_agent_graph():
        return FakeGraph()

    monkeypatch.setattr(memory_service, "load_memory_context_async", fake_load_memory_context_async)
    monkeypatch.setattr(agent_api, "get_agent_graph", fake_get_agent_graph)

    with client.stream(
        "POST",
        "/api/agent/stream",
        json={
            "project_id": project.id,
            "message": "请综合参考这些内容",
            "mode_id": mode.id,
            "references": [first_ref.id, second_ref.id],
            "selection_context": {
                "block_id": selection_block.id,
                "block_name": selection_block.name,
                "selected_text": "用户选中的文字片段",
            },
        },
    ) as response:
        payload = "".join(response.iter_text())

    assert response.status_code == 200
    assert "引用完整" in payload


@pytest.mark.asyncio
async def test_rewrite_field_uses_full_reference_content(client_and_session, monkeypatch):
    _, session, testing_session_local = client_and_session
    project, _ = _seed_project_mode_and_blocks(session)
    target = _make_block(project.id, "主文案", content="这是原始内容。")
    reference_tail = "REWRITE-REFERENCE-TAIL-UNTRUNCATED"
    reference = _make_block(project.id, "参考块", content=("参" * 2600) + reference_tail)
    session.add_all([target, reference])
    session.commit()

    async def fake_ainvoke_with_retry(chat_model, messages, config=None):
        assert reference_tail in messages[0].content
        return AIMessage(content="这是重写后的完整内容。")

    monkeypatch.setattr(agent_tools, "_get_db", testing_session_local)
    monkeypatch.setattr("core.llm.get_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr("core.llm.ainvoke_with_retry", fake_ainvoke_with_retry)

    result = await agent_tools._rewrite_field_impl(
        target.name,
        "请全文重写为更口语化的版本",
        [reference.id],
        _tool_config(project.id),
    )

    payload = json.loads(result)
    assert payload["status"] == "suggestion"


@pytest.mark.asyncio
async def test_generate_field_content_uses_full_dependency_content(client_and_session, monkeypatch):
    _, session, testing_session_local = client_and_session
    project, _ = _seed_project_mode_and_blocks(session)
    dependency_tail = "DEPENDENCY-TAIL-UNTRUNCATED"
    dependency = _make_block(project.id, "依赖块", content=("依" * 2600) + dependency_tail)
    target = _make_block(project.id, "待生成块", content="", depends_on=[dependency.id])
    session.add_all([dependency, target])
    session.commit()

    async def fake_ainvoke_with_retry(chat_model, messages, config=None):
        assert dependency_tail in messages[0].content
        return AIMessage(content="生成后的内容。")

    monkeypatch.setattr(agent_tools, "_get_db", testing_session_local)
    monkeypatch.setattr("core.llm.get_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr("core.llm.ainvoke_with_retry", fake_ainvoke_with_retry)

    result = await agent_tools._generate_field_impl(
        target.name,
        "请生成完整文案",
        _tool_config(project.id),
    )

    payload = json.loads(result)
    assert payload["status"] == "generated"

    session.expire_all()
    refreshed = session.query(ContentBlock).filter(ContentBlock.id == target.id).first()
    assert refreshed is not None
    assert refreshed.content == "生成后的内容。"


@pytest.mark.asyncio
async def test_query_field_uses_full_block_content(client_and_session, monkeypatch):
    _, session, testing_session_local = client_and_session
    project, _ = _seed_project_mode_and_blocks(session)
    content_tail = "QUERY-CONTENT-TAIL-UNTRUNCATED"
    block = _make_block(project.id, "问答块", content=("问" * 4200) + content_tail)
    session.add(block)
    session.commit()

    async def fake_ainvoke_with_retry(chat_model, messages, config=None):
        assert content_tail in messages[0].content
        return AIMessage(content="我已经读取了完整内容。")

    monkeypatch.setattr(agent_tools, "_get_db", testing_session_local)
    monkeypatch.setattr("core.llm.get_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr("core.llm.ainvoke_with_retry", fake_ainvoke_with_retry)

    result = await agent_tools._query_field_impl(
        block.name,
        "后半段写了什么？",
        _tool_config(project.id),
    )

    assert result == "我已经读取了完整内容。"


@pytest.mark.asyncio
async def test_query_field_reads_runtime_surface_config(client_and_session, monkeypatch):
    _, session, testing_session_local = client_and_session
    project, _ = _seed_project_mode_and_blocks(session)
    dependency = _make_block(project.id, "依赖块", content="依赖内容")
    block = _make_block(
        project.id,
        "配置块",
        content="",
        ai_prompt="请写成 FAQ",
        depends_on=[dependency.id],
        pre_questions=[{"id": "pq-1", "question": "受众是谁？", "required": True}],
        pre_answers={"pq-1": "开发者"},
        need_review=False,
        auto_generate=True,
        model_override="gpt-4.1-mini",
    )
    session.add_all([dependency, block])
    session.commit()

    async def fake_ainvoke_with_retry(chat_model, messages, config=None):
        system_prompt = messages[0].content
        assert "[依赖内容块]" in system_prompt
        assert "依赖块" in system_prompt
        assert "[生成前提问]" in system_prompt
        assert "受众是谁？" in system_prompt
        assert "[当前回答]" in system_prompt
        assert "开发者" in system_prompt
        assert "[需要人工确认: 否]" in system_prompt
        assert "[自动生成: 是]" in system_prompt
        assert "[模型覆盖: gpt-4.1-mini]" in system_prompt
        return AIMessage(content="我已经读取了运行时配置。")

    monkeypatch.setattr(agent_tools, "_get_db", testing_session_local)
    monkeypatch.setattr("core.llm.get_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr("core.llm.ainvoke_with_retry", fake_ainvoke_with_retry)

    result = await agent_tools._query_field_impl(
        block.name,
        "这个块现在的配置是什么？",
        _tool_config(project.id),
    )

    assert result == "我已经读取了运行时配置。"


@pytest.mark.asyncio
async def test_generate_field_content_respects_required_pre_questions(client_and_session, monkeypatch):
    _, session, testing_session_local = client_and_session
    project, _ = _seed_project_mode_and_blocks(session)
    block = _make_block(
        project.id,
        "待生成块",
        content="",
        ai_prompt="请生成完整文案",
        pre_questions=[{"id": "pq-1", "question": "目标受众是谁？", "required": True}],
        pre_answers={},
    )
    session.add(block)
    session.commit()

    monkeypatch.setattr(agent_tools, "_get_db", testing_session_local)

    result = await agent_tools._generate_field_impl(
        block.name,
        "请生成完整文案",
        _tool_config(project.id),
    )

    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "目标受众是谁？" in payload["message"]


@pytest.mark.asyncio
async def test_generate_field_content_respects_dependency_readiness(client_and_session, monkeypatch):
    _, session, testing_session_local = client_and_session
    project, _ = _seed_project_mode_and_blocks(session)
    dependency = _make_block(project.id, "未完成依赖", content="")
    block = _make_block(
        project.id,
        "待生成块",
        content="",
        ai_prompt="请生成完整文案",
        depends_on=[dependency.id],
    )
    session.add_all([dependency, block])
    session.commit()

    monkeypatch.setattr(agent_tools, "_get_db", testing_session_local)

    result = await agent_tools._generate_field_impl(
        block.name,
        "请生成完整文案",
        _tool_config(project.id),
    )

    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "未完成依赖" in payload["message"]
