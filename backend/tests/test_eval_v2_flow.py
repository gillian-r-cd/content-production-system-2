# backend/tests/test_eval_v2_flow.py
# 功能: 验证 Eval V2 新链路的核心闭环（Task 容器、TrialConfig 执行、Task 级分析）
# 主要函数: test_eval_v2_task_execute_and_aggregate, test_eval_v2_task_diagnosis
# 数据结构:
#   - 内存数据库中的 Project/ContentBlock/Grader
#   - /api/eval/tasks/{project_id} 与 /api/eval/task/{task_id}/execute 新接口响应

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from core.models import Project, ContentBlock, Grader, generate_uuid
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


def _seed_minimal_eval_context(session):
    project = Project(id=generate_uuid(), name="Eval V2 Test Project")
    session.add(project)
    session.flush()

    content_block = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=None,
        name="第一章",
        block_type="field",
        content="这是用于评估的正文内容，包含结构和价值描述。",
        status="completed",
        special_handler=None,
        order_index=1,
    )
    session.add(content_block)

    grader = Grader(
        id=generate_uuid(),
        name="测试评分器",
        grader_type="content_only",
        prompt_template="请评分 {content}",
        dimensions=["结构", "价值"],
        scoring_criteria={},
        is_preset=False,
        project_id=project.id,
    )
    session.add(grader)
    session.commit()
    return project, content_block, grader


@pytest.mark.asyncio
async def test_eval_v2_task_execute_and_aggregate(client_and_session, monkeypatch):
    client, session = client_and_session
    project, _, grader = _seed_minimal_eval_context(session)

    async def fake_run_individual_grader(**kwargs):
        return (
            {
                "grader_name": kwargs.get("grader_name", "测试评分器"),
                "scores": {"结构": 6, "价值": 8},
                "comments": {"结构": "结构一般", "价值": "价值尚可"},
                "feedback": "建议提升结构衔接。",
            },
            {
                "step": "grader_fake",
                "input": {"system_prompt": "s", "user_message": "u"},
                "output": "ok",
                "tokens_in": 10,
                "tokens_out": 5,
                "cost": 0.0,
                "duration_ms": 1,
                "timestamp": "2026-01-01T00:00:00",
            },
        )

    monkeypatch.setattr("api.eval.run_individual_grader", fake_run_individual_grader)

    create_resp = client.post(
        f"/api/eval/tasks/{project.id}",
        json={
            "name": "内容质量任务",
            "description": "测试任务",
            "trial_configs": [
                {
                    "name": "直接判定A",
                    "form_type": "assessment",
                    "target_block_ids": [],
                    "grader_ids": [grader.id],
                    "repeat_count": 2,
                    "order_index": 0,
                    "form_config": {},
                }
            ],
        },
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["id"]

    exec_resp = client.post(f"/api/eval/task/{task_id}/execute")
    assert exec_resp.status_code == 200
    payload = exec_resp.json()
    assert payload["task"]["latest_batch_id"] != ""
    assert payload["task"]["latest_overall"] == 7.0
    assert len(payload["trials"]) == 2
    assert all(t["status"] == "completed" for t in payload["trials"])

    latest_resp = client.get(f"/api/eval/task/{task_id}/latest")
    assert latest_resp.status_code == 200
    latest = latest_resp.json()
    assert len(latest["trials"]) == 2
    assert latest["task"]["latest_scores"]["overall"]["mean"] == 7.0


@pytest.mark.asyncio
async def test_eval_v2_task_diagnosis(client_and_session, monkeypatch):
    client, session = client_and_session
    project, _, grader = _seed_minimal_eval_context(session)

    async def fake_run_individual_grader(**kwargs):
        return (
            {
                "grader_name": kwargs.get("grader_name", "测试评分器"),
                "scores": {"结构": 5, "价值": 8},
                "comments": {"结构": "结构偏弱", "价值": "价值尚可"},
                "feedback": "重点增强结构连贯性。",
            },
            None,
        )

    monkeypatch.setattr("api.eval.run_individual_grader", fake_run_individual_grader)

    create_resp = client.post(
        f"/api/eval/tasks/{project.id}",
        json={
            "name": "结构优化任务",
            "trial_configs": [
                {
                    "name": "直接判定B",
                    "form_type": "assessment",
                    "grader_ids": [grader.id],
                    "repeat_count": 3,
                    "form_config": {},
                }
            ],
        },
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["id"]

    run_resp = client.post(f"/api/eval/task/{task_id}/execute")
    assert run_resp.status_code == 200

    diag_resp = client.post(f"/api/eval/task/{task_id}/diagnose")
    assert diag_resp.status_code == 200
    analysis = diag_resp.json()["analysis"]
    assert analysis["task_id"] == task_id
    assert len(analysis["patterns"]) >= 1
    assert len(analysis["suggestions"]) >= 1


@pytest.mark.asyncio
async def test_eval_v2_execution_records_are_flat_by_batch(client_and_session, monkeypatch):
    client, session = client_and_session
    project, _, grader = _seed_minimal_eval_context(session)

    async def fake_run_individual_grader(**kwargs):
        return (
            {
                "grader_name": kwargs.get("grader_name", "测试评分器"),
                "scores": {"结构": 7, "价值": 7},
                "comments": {"结构": "稳定", "价值": "稳定"},
                "feedback": "继续优化案例细节。",
            },
            None,
        )

    monkeypatch.setattr("api.eval.run_individual_grader", fake_run_individual_grader)

    create_resp = client.post(
        f"/api/eval/tasks/{project.id}",
        json={
            "name": "批次列表任务",
            "trial_configs": [
                {
                    "name": "直接判定C",
                    "form_type": "assessment",
                    "grader_ids": [grader.id],
                    "repeat_count": 1,
                    "form_config": {},
                }
            ],
        },
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["id"]

    first = client.post(f"/api/eval/task/{task_id}/execute")
    second = client.post(f"/api/eval/task/{task_id}/execute")
    assert first.status_code == 200
    assert second.status_code == 200
    first_batch = first.json()["batch_id"]
    second_batch = second.json()["batch_id"]
    assert first_batch != second_batch

    executions = client.get(f"/api/eval/tasks/{project.id}/executions")
    assert executions.status_code == 200
    rows = executions.json()["executions"]
    hit = [r for r in rows if r["task_id"] == task_id]
    assert len(hit) == 2

    batch_detail = client.get(f"/api/eval/task/{task_id}/batch/{first_batch}")
    assert batch_detail.status_code == 200
    assert batch_detail.json()["batch_id"] == first_batch
    assert len(batch_detail.json()["trials"]) == 1


@pytest.mark.asyncio
async def test_eval_v2_experience_uses_three_step_executor(client_and_session, monkeypatch):
    client, session = client_and_session
    project, content_block, grader = _seed_minimal_eval_context(session)

    # 写入 persona block，供 experience 引用
    persona_block = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=None,
        name="人物画像设置",
        block_type="field",
        content='{"personas":[{"id":"p1","name":"张晨","prompt":"你是张晨，关注定价与价值。"}]}',
        status="completed",
        special_handler="eval_persona_setup",
        order_index=2,
    )
    session.add(persona_block)
    session.commit()

    async def fake_experience_trial(**kwargs):
        return type(
            "R",
            (),
            {
                "process": [
                    {"type": "plan", "data": {"plan": [{"block_id": content_block.id}]}},
                    {"type": "per_block", "block_id": content_block.id, "data": {"score": 6, "missing": "缺案例"}},
                    {"type": "summary", "data": {"summary": "总体一般"}},
                ],
                "llm_calls": [
                    {"step": "experience_plan", "tokens_in": 1, "tokens_out": 1, "cost": 0.0},
                    {"step": "experience_per_block_1", "tokens_in": 1, "tokens_out": 1, "cost": 0.0},
                    {"step": "experience_summary", "tokens_in": 1, "tokens_out": 1, "cost": 0.0},
                ],
                "exploration_score": 6.0,
                "summary": {"summary": "总体一般"},
                "error": "",
            },
        )()

    async def fake_run_individual_grader(**kwargs):
        return (
            {
                "grader_name": kwargs.get("grader_name", "测试评分器"),
                "scores": {"结构": 6, "价值": 7},
                "comments": {"结构": "一般", "价值": "尚可"},
                "feedback": "补充示例可提升体验。",
            },
            None,
        )

    monkeypatch.setattr("api.eval.run_experience_trial", fake_experience_trial)
    monkeypatch.setattr("api.eval.run_individual_grader", fake_run_individual_grader)

    create_resp = client.post(
        f"/api/eval/tasks/{project.id}",
        json={
            "name": "消费者体验任务",
            "trial_configs": [
                {
                    "name": "张晨-体验",
                    "form_type": "experience",
                    "grader_ids": [grader.id],
                    "repeat_count": 1,
                    "probe": "关注价值是否说服我",
                    "target_block_ids": [content_block.id],
                    "form_config": {"persona_id": "p1"},
                }
            ],
        },
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["id"]

    run_resp = client.post(f"/api/eval/task/{task_id}/execute")
    assert run_resp.status_code == 200
    trials = run_resp.json()["trials"]
    assert len(trials) == 1
    assert trials[0]["form_type"] == "experience"
    assert any((x or {}).get("type") == "plan" for x in (trials[0].get("process") or []))
    assert any((x or {}).get("type") == "summary" for x in (trials[0].get("process") or []))


@pytest.mark.asyncio
async def test_eval_v2_generate_persona_endpoint(client_and_session, monkeypatch):
    client, session = client_and_session
    project, _, _ = _seed_minimal_eval_context(session)

    # 已有 persona（用于测试 avoid_names）
    persona_block = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=None,
        name="人物画像设置",
        block_type="field",
        content='{"personas":[{"id":"p1","name":"已有画像","prompt":"你是已有画像"}]}',
        status="completed",
        special_handler="eval_persona_setup",
        order_index=2,
    )
    session.add(persona_block)
    session.commit()

    captured = {"existing_names": []}

    async def fake_generate_persona_with_llm(project_name, project_intent, existing_names):
        captured["existing_names"] = existing_names
        return {"name": "AI画像A", "prompt": "你是AI画像A，关注ROI和实操。"}

    monkeypatch.setattr("api.eval._generate_persona_with_llm", fake_generate_persona_with_llm)

    resp = client.post(
        "/api/eval/personas/generate",
        json={"project_id": project.id, "avoid_names": ["手动避让名"]},
    )
    assert resp.status_code == 200
    persona = resp.json()["persona"]
    assert persona["name"] == "AI画像A"
    assert "ROI" in persona["prompt"]
    # 断言接口层合并了 avoid_names + 项目已有画像名
    assert "已有画像" in captured["existing_names"]
    assert "手动避让名" in captured["existing_names"]


@pytest.mark.asyncio
async def test_eval_v2_mixed_form_multi_batch_trend(client_and_session, monkeypatch):
    client, session = client_and_session
    project, content_block, grader = _seed_minimal_eval_context(session)

    persona_block = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=None,
        name="人物画像设置",
        block_type="field",
        content='{"personas":[{"id":"p1","name":"张晨","prompt":"你是张晨，关注价值。"}]}',
        status="completed",
        special_handler="eval_persona_setup",
        order_index=2,
    )
    session.add(persona_block)
    session.commit()

    async def fake_experience_trial(**kwargs):
        return type(
            "R",
            (),
            {
                "process": [
                    {"type": "plan", "data": {"plan": [{"block_id": content_block.id}]}},
                    {"type": "per_block", "block_id": content_block.id, "data": {"score": 7}},
                    {"type": "summary", "data": {"summary": "ok"}},
                ],
                "llm_calls": [
                    {"step": "experience_plan", "input": {"system_prompt": "s1", "user_message": "u1"}, "output": "o1"},
                    {"step": "experience_per_block_1", "input": {"system_prompt": "s2", "user_message": "u2"}, "output": "o2"},
                    {"step": "experience_summary", "input": {"system_prompt": "s3", "user_message": "u3"}, "output": "o3"},
                ],
                "exploration_score": 7.0,
                "summary": {"summary": "ok"},
                "error": "",
            },
        )()

    async def fake_run_individual_grader(**kwargs):
        return (
            {
                "grader_name": kwargs.get("grader_name", "测试评分器"),
                "scores": {"结构": 7, "价值": 8},
                "comments": {"结构": "稳定", "价值": "稳定"},
                "feedback": "继续补充案例。",
            },
            None,
        )

    monkeypatch.setattr("api.eval.run_experience_trial", fake_experience_trial)
    monkeypatch.setattr("api.eval.run_individual_grader", fake_run_individual_grader)

    create_resp = client.post(
        f"/api/eval/tasks/{project.id}",
        json={
            "name": "混合形态任务",
            "trial_configs": [
                {
                    "name": "直接判定",
                    "form_type": "assessment",
                    "grader_ids": [grader.id],
                    "repeat_count": 1,
                    "target_block_ids": [content_block.id],
                    "form_config": {},
                },
                {
                    "name": "张晨体验",
                    "form_type": "experience",
                    "grader_ids": [grader.id],
                    "repeat_count": 2,
                    "target_block_ids": [content_block.id],
                    "form_config": {"persona_id": "p1"},
                },
            ],
        },
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["id"]

    run1 = client.post(f"/api/eval/task/{task_id}/execute")
    run2 = client.post(f"/api/eval/task/{task_id}/execute")
    assert run1.status_code == 200
    assert run2.status_code == 200
    batch1 = run1.json()["batch_id"]
    batch2 = run2.json()["batch_id"]
    assert batch1 != batch2
    assert len(run1.json()["trials"]) == 3
    assert len(run2.json()["trials"]) == 3

    exec_rows = client.get(f"/api/eval/tasks/{project.id}/executions")
    assert exec_rows.status_code == 200
    rows = [r for r in exec_rows.json()["executions"] if r["task_id"] == task_id]
    assert len(rows) == 2
    assert all(r["trial_count"] == 3 for r in rows)

    detail1 = client.get(f"/api/eval/task/{task_id}/batch/{batch1}")
    assert detail1.status_code == 200
    trials1 = detail1.json()["trials"]
    assert len(trials1) == 3
    forms = sorted([t["form_type"] for t in trials1])
    assert forms == ["assessment", "experience", "experience"]


@pytest.mark.asyncio
async def test_eval_v2_persona_crud_api(client_and_session):
    client, session = client_and_session
    project, _, _ = _seed_minimal_eval_context(session)

    create = client.post(
        f"/api/eval/personas/{project.id}",
        json={"name": "王芳", "prompt": "你是王芳，关注预算和落地性。", "source": "manual"},
    )
    assert create.status_code == 200
    persona = create.json()["persona"]
    assert persona["name"] == "王芳"
    persona_id = persona["id"]
    assert persona_id

    listed = client.get(f"/api/eval/personas/{project.id}")
    assert listed.status_code == 200
    assert any(p.get("id") == persona_id for p in listed.json()["personas"])

    update = client.put(
        f"/api/eval/persona/{persona_id}",
        json={"name": "王芳-更新", "prompt": "你是王芳，重点看ROI证明。"},
    )
    assert update.status_code == 200
    assert update.json()["persona"]["name"] == "王芳-更新"

    listed2 = client.get(f"/api/eval/personas/{project.id}")
    assert any(p.get("name") == "王芳-更新" for p in listed2.json()["personas"])

    delete = client.delete(f"/api/eval/persona/{persona_id}")
    assert delete.status_code == 200

    listed3 = client.get(f"/api/eval/personas/{project.id}")
    assert all(p.get("id") != persona_id for p in listed3.json()["personas"])


@pytest.mark.asyncio
async def test_eval_v2_generate_prompt_endpoint(client_and_session, monkeypatch):
    client, session = client_and_session
    _seed_minimal_eval_context(session)

    captured = {"prompt_type": "", "context": {}}

    async def fake_generate_prompt_with_llm(prompt_type, context):
        captured["prompt_type"] = prompt_type
        captured["context"] = context
        return "你是评估专家，请按 JSON 输出。{content}"

    monkeypatch.setattr("api.eval._generate_prompt_with_llm", fake_generate_prompt_with_llm)

    resp = client.post(
        "/api/eval/prompts/generate",
        json={"prompt_type": "grader_prompt", "context": {"form_type": "assessment", "description": "检查结构"}},
    )
    assert resp.status_code == 200
    assert "{content}" in resp.json()["generated_prompt"]
    assert captured["prompt_type"] == "grader_prompt"
    assert captured["context"]["form_type"] == "assessment"


@pytest.mark.asyncio
async def test_eval_v2_e2e_all_forms_single_task(client_and_session, monkeypatch):
    client, session = client_and_session
    project, content_block, grader = _seed_minimal_eval_context(session)

    persona_block = ContentBlock(
        id=generate_uuid(),
        project_id=project.id,
        parent_id=None,
        name="人物画像设置",
        block_type="field",
        content=(
            '{"personas":['
            '{"id":"p_review","name":"资深编辑","prompt":"你是资深编辑。"},'
            '{"id":"p_exp","name":"张晨","prompt":"你是张晨。"},'
            '{"id":"p_a","name":"课程顾问","prompt":"你是课程顾问。"},'
            '{"id":"p_b","name":"王芳","prompt":"你是王芳。"}'
            ']}'
        ),
        status="completed",
        special_handler="eval_persona_setup",
        order_index=2,
    )
    session.add(persona_block)
    session.commit()

    async def fake_run_individual_grader(**kwargs):
        return (
            {
                "grader_name": kwargs.get("grader_name", "测试评分器"),
                "scores": {"结构": 7, "价值": 8},
                "comments": {"结构": "稳定", "价值": "稳定"},
                "feedback": "建议补充案例。",
            },
            None,
        )

    async def fake_experience_trial(**kwargs):
        return type(
            "R",
            (),
            {
                "process": [
                    {"type": "plan", "data": {"plan": [{"block_id": content_block.id}]}},
                    {"type": "per_block", "block_id": content_block.id, "data": {"score": 7}},
                    {"type": "summary", "data": {"summary": "ok"}},
                ],
                "llm_calls": [{"step": "experience_plan", "input": {"system_prompt": "s", "user_message": "u"}, "output": "o"}],
                "exploration_score": 7.0,
                "summary": {"summary": "ok"},
                "error": "",
            },
        )()

    async def fake_run_task_trial(**kwargs):
        return type(
            "TR",
            (),
            {
                "nodes": [{"role": "assistant", "content": "ok"}],
                "llm_calls": [{"step": "sim_call", "input": {"system_prompt": "s", "user_message": "u"}, "output": "o"}],
                "tokens_in": 1,
                "tokens_out": 1,
                "cost": 0.0,
                "success": True,
                "error": "",
                "grader_outputs": [],
            },
        )()

    monkeypatch.setattr("api.eval.run_individual_grader", fake_run_individual_grader)
    monkeypatch.setattr("api.eval.run_experience_trial", fake_experience_trial)
    monkeypatch.setattr("api.eval.run_task_trial", fake_run_task_trial)

    create_resp = client.post(
        f"/api/eval/tasks/{project.id}",
        json={
            "name": "四形态E2E任务",
            "trial_configs": [
                {"name": "直接判定", "form_type": "assessment", "grader_ids": [grader.id], "repeat_count": 1, "target_block_ids": [content_block.id], "form_config": {}},
                {"name": "视角审查", "form_type": "review", "grader_ids": [grader.id], "repeat_count": 1, "target_block_ids": [content_block.id], "form_config": {"persona_id": "p_review"}},
                {"name": "消费体验", "form_type": "experience", "grader_ids": [grader.id], "repeat_count": 1, "target_block_ids": [content_block.id], "form_config": {"persona_id": "p_exp"}},
                {"name": "场景模拟", "form_type": "scenario", "grader_ids": [grader.id], "repeat_count": 1, "target_block_ids": [content_block.id], "form_config": {"role_a_persona_id": "p_a", "role_b_persona_id": "p_b", "max_turns": 3}},
            ],
        },
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["id"]

    run_resp = client.post(f"/api/eval/task/{task_id}/execute")
    assert run_resp.status_code == 200
    trials = run_resp.json()["trials"]
    assert len(trials) == 4
    forms = sorted([t["form_type"] for t in trials])
    assert forms == ["assessment", "experience", "review", "scenario"]
    assert all(t["status"] == "completed" for t in trials)
    assert all(isinstance(t.get("overall_score"), (int, float)) for t in trials)

