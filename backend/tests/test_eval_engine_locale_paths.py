# backend/tests/test_eval_engine_locale_paths.py
# 功能: 验证 eval_engine 中日文 locale 关键运行路径（探索模式）不会回落到中文 prompt 或中文默认维度
# 主要函数: test_run_task_trial_exploration_uses_ja_prompt_and_dimensions
# 数据结构:
#   - fake_call_llm: 拦截 exploration / grader 调用
#   - FakeCall: 最小 LLMCall 替身，支持 to_dict

import pytest

from core.tools import eval_engine


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

    exploration_output = (
        '{"exploration_plan":"最初に導入価値を確認する",'
        '"exploration_steps":[{"step":1,"action":"導入を読む","reason":"全体価値を把握するため",'
        '"finding":"概要は理解できる","feeling":"追加根拠が欲しい"}],'
        '"attention_points":["導入価値"],'
        '"found_answer":false,'
        '"answer_quality":"やや不足",'
        '"difficulties":["定量根拠が不足"],'
        '"missing_info":["導入成果の数値"],'
        '"scores":{"ニーズ適合度":7,"理解しやすさ":8,"価値認知":7,"行動意欲":6},'
        '"comments":{"ニーズ適合度":"概ね一致","理解しやすさ":"理解しやすい","価値認知":"価値は伝わる","行動意欲":"追加根拠が必要"},'
        '"would_recommend":false,'
        '"summary":"追加根拠が必要"}'
    )

    async def fake_call_llm(system_prompt, user_message, step, temperature=0.6):
        captured.append({"step": step, "system_prompt": system_prompt, "user_message": user_message})
        if step.startswith("explorer_"):
            return exploration_output, FakeCall(step, system_prompt, user_message)
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
