import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from main import app


@pytest.fixture
def client():
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
    c = TestClient(app)
    try:
        yield c
    finally:
        app.dependency_overrides.clear()


def test_eval_prompt_presets_seed_and_update(client):
    listed = client.get("/api/settings/eval-prompts")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) >= 12
    phases = {r["phase"] for r in rows}
    assert "eval_experience_plan" in phases
    assert "eval_scenario_role_a" in phases
    locales = {r["locale"] for r in rows}
    assert locales == {"zh-CN", "ja-JP"}
    assert all(r["stable_key"] for r in rows)
    by_phase_locale = {(r["phase"], r["locale"]): r for r in rows}
    assert "plan 至少 3 步" in by_phase_locale[("eval_experience_plan", "zh-CN")]["content"]
    assert "score 必须是 1-10 的整数" in by_phase_locale[("eval_experience_per_block", "zh-CN")]["content"]
    assert "是否推荐 + 条件/原因" in by_phase_locale[("eval_experience_summary", "zh-CN")]["content"]
    assert "内容未覆盖" in by_phase_locale[("eval_scenario_role_a", "zh-CN")]["content"]
    assert "3ステップ以上" in by_phase_locale[("eval_experience_plan", "ja-JP")]["content"]
    assert "1-10 の整数" in by_phase_locale[("eval_experience_per_block", "ja-JP")]["content"]
    assert "推薦するか" in by_phase_locale[("eval_experience_summary", "ja-JP")]["content"]
    assert "コンテンツには含まれていません" in by_phase_locale[("eval_scenario_role_a", "ja-JP")]["content"]

    target = rows[0]
    updated = client.put(
        f"/api/settings/eval-prompts/{target['id']}",
        json={"content": "你是测试模板。{persona}", "description": "测试更新"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "测试更新"

    listed2 = client.get("/api/settings/eval-prompts")
    assert listed2.status_code == 200
    hit = next(r for r in listed2.json() if r["id"] == target["id"])
    assert hit["content"] == "你是测试模板。{persona}"


def test_eval_presets_sync_is_idempotent(client):
    first = client.post("/api/settings/eval-presets/sync")
    assert first.status_code == 200
    first_json = first.json()
    assert first_json["imported_graders"] >= 1
    assert first_json["imported_simulators"] >= 1

    graders1 = client.get("/api/graders")
    sims1 = client.get("/api/settings/simulators")
    assert graders1.status_code == 200
    assert sims1.status_code == 200
    preset_graders_count_1 = len([g for g in graders1.json() if g.get("is_preset")])
    preset_sims_count_1 = len([s for s in sims1.json() if s.get("is_preset")])
    assert {g.get("locale") for g in graders1.json() if g.get("is_preset")} == {"zh-CN", "ja-JP"}
    assert all(g.get("stable_key") for g in graders1.json() if g.get("is_preset"))
    assert {s.get("locale") for s in sims1.json() if s.get("is_preset")} == {"zh-CN", "ja-JP"}
    assert all(s.get("stable_key") for s in sims1.json() if s.get("is_preset"))
    assert preset_graders_count_1 >= 8
    assert preset_sims_count_1 >= 8

    second = client.post("/api/settings/eval-presets/sync")
    assert second.status_code == 200
    second_json = second.json()
    assert second_json["imported_graders"] == 0
    assert second_json["imported_simulators"] == 0

    graders2 = client.get("/api/graders")
    sims2 = client.get("/api/settings/simulators")
    preset_graders_count_2 = len([g for g in graders2.json() if g.get("is_preset")])
    preset_sims_count_2 = len([s for s in sims2.json() if s.get("is_preset")])
    assert preset_graders_count_2 == preset_graders_count_1
    assert preset_sims_count_2 == preset_sims_count_1

