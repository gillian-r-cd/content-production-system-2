# backend/tests/test_eval_v2_executor.py
# 功能: 验证 Experience 三步分块执行器的核心行为（规划/逐块/总结与分块均分）
# 主要函数: test_run_experience_trial_three_steps
# 数据结构:
#   - blocks: 多内容块输入
#   - llm mocked outputs: plan + per_block*N + summary

import pytest

from core.tools.eval_v2_executor import run_experience_trial


@pytest.mark.asyncio
async def test_run_experience_trial_three_steps(monkeypatch):
    outputs = [
        # step 1: plan
        '{"plan":[{"block_id":"b2","block_title":"第二章","reason":"先看案例","expectation":"验证价值"},{"block_id":"b1","block_title":"第一章","reason":"再看原理","expectation":"补理论"}],"overall_goal":"判断是否值得购买"}',
        # step 2 block b2
        '{"concern_match":"部分回应","discovery":"有案例","doubt":"缺成本说明","missing":"ROI细节","feeling":"我仍在犹豫","score":6}',
        # step 2 block b1
        '{"concern_match":"回应较好","discovery":"框架清晰","doubt":"术语略多","missing":"实操步骤","feeling":"有帮助","score":8}',
        # step 3 summary
        '{"overall_impression":"整体中上","concerns_addressed":["价值说明"],"concerns_unaddressed":["ROI细节"],"would_recommend":false,"summary":"还需要补充价格与回报细节"}',
    ]

    class FakeResp:
        def __init__(self, text):
            self.content = text
            self.usage_metadata = {"input_tokens": 10, "output_tokens": 5}

    class FakeModel:
        async def ainvoke(self, messages):
            return FakeResp(outputs.pop(0))

    def fake_get_chat_model(**kwargs):
        return FakeModel()

    monkeypatch.setattr("core.tools.eval_v2_executor.get_chat_model", fake_get_chat_model)

    result = await run_experience_trial(
        persona_name="张晨",
        persona_prompt="你是张晨，关注定价价值。",
        probe="关注定价合理性",
        blocks=[
            {"id": "b1", "title": "第一章", "content": "原理内容"},
            {"id": "b2", "title": "第二章", "content": "案例内容"},
        ],
    )

    assert result.error == ""
    assert len(result.llm_calls) == 4
    assert any(p.get("type") == "plan" for p in result.process)
    assert len([p for p in result.process if p.get("type") == "per_block"]) == 2
    assert any(p.get("type") == "summary" for p in result.process)
    assert result.exploration_score == 7.0

