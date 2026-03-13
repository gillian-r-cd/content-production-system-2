# backend/tests/test_eval_engine_prompt_integrity.py
# 功能: 验证评分器提示词变量注入完整性（不截断 content/process）
# 主要函数: test_run_individual_grader_keeps_full_content_and_process
# 数据结构:
#   - long_content/long_process: 超长字符串 + 末尾哨兵

import pytest

from core.tools import eval_engine


@pytest.mark.asyncio
async def test_run_individual_grader_keeps_full_content_and_process(monkeypatch):
    captured = {"system_prompt": ""}

    async def fake_call_llm(system_prompt, user_message, step, temperature=0.4):
        captured["system_prompt"] = system_prompt
        return (
            '{"scores":{"综合评价":8},"comments":{"综合评价":"依据充分"},"feedback":"建议补充案例"}',
            type(
                "Call",
                (),
                {"tokens_in": 1, "tokens_out": 1, "cost": 0.0},
            )(),
        )

    monkeypatch.setattr("core.tools.eval_engine._call_llm", fake_call_llm)

    long_content = ("A" * 7000) + "__CONTENT_END__"
    long_process = ("B" * 5000) + "__PROCESS_END__"
    await eval_engine.run_individual_grader(
        grader_name="完整性测试评分器",
        grader_type="content_and_process",
        prompt_template="内容:\n{content}\n\n过程:\n{process}",
        dimensions=["综合评价"],
        content=long_content,
        trial_result_data={},
        process_transcript=long_process,
    )

    assert "__CONTENT_END__" in captured["system_prompt"]
    assert "__PROCESS_END__" in captured["system_prompt"]


@pytest.mark.asyncio
async def test_run_task_trial_exploration_uses_ja_prompt_and_dimensions(monkeypatch):
    captured = []

    class FakeCall:
        def __init__(self, step, system_prompt, user_message):
            self.step = step
            self.input_system = system_prompt
            self.input_user = user_message
            self.output = "ok"
            self.tokens_in = 1
            self.tokens_out = 1
            self.cost = 0.0
            self.duration_ms = 1
            self.timestamp = "2026-01-01T00:00:00"

        def to_dict(self):
            return {
                "step": self.step,
                "input": {"system_prompt": self.input_system, "user_message": self.input_user},
                "output": self.output,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "cost": self.cost,
                "duration_ms": self.duration_ms,
                "timestamp": self.timestamp,
            }

    async def fake_call_llm(system_prompt, user_message, step, temperature=0.6):
        captured.append({"step": step, "system_prompt": system_prompt, "user_message": user_message})
        if step.startswith("explorer_"):
            return (
                '{"exploration_plan":"最初に導入価値を確認する","exploration_steps":[{"step":1,"action":"導入を読む","reason":"全体価値を把握するため","finding":"概要は理解できる","feeling":"追加根拠が欲しい"}],"attention_points":["導入価値"],"found_answer":false,"answer_quality":"やや不足","difficulties":["定量根拠が不足"],"missing_info":["導入成果の数値"],"scores":{"ニーズ適合度":7,"理解しやすさ":8,"価値認知":7,"行動意欲":6},"comments":{"ニーズ適合度":"概ね一致","理解しやすさ":"理解しやすい","価値認知":"価値は伝わる","行動意欲":"追加根拠が必要"},"would_recommend":false,"summary":"追加根拠が必要"}',
                FakeCall(step, system_prompt, user_message),
            )
        return (
            '{"scores":{"総合評価":7},"comments":{"総合評価":"根拠あり"},"feedback":"定量根拠を補ってください。"}',
            FakeCall(step, system_prompt, user_message),
        )

    monkeypatch.setattr("core.tools.eval_engine._call_llm", fake_call_llm)

    result = await eval_engine.run_task_trial(
        simulator_type="consumer",
        interaction_mode="exploration",
        content="導入価値と進め方を説明する本文",
        persona={"name": "佐藤", "background": "導入担当者"},
        simulator_config={"locale": "ja-JP"},
        grader_config={"type": "content", "dimensions": [], "locale": "ja-JP"},
        content_field_names=["導入概要"],
    )

    assert result.success is True
    assert captured[0]["step"] == "explorer_consumer_exploration"
    assert "JSON 形式のみで出力してください" in captured[0]["user_message"]
    assert "ニーズ適合度" in captured[0]["user_message"]
    assert "以下是你要探索的内容" not in captured[0]["user_message"]
    assert "需求匹配度" not in captured[0]["user_message"]
    assert any("探索計画" in str(node.get("content", "")) for node in result.nodes)