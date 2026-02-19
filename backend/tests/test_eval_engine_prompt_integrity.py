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


