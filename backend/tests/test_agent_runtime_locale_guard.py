# backend/tests/test_agent_runtime_locale_guard.py
# 功能: 守卫 Agent 运行时注入的 locale 文案，防止日语链路混入中文引用上下文
# 主要测试: _build_ref_context

from api import agent as agent_api
from core.models import ContentBlock


def test_build_ref_context_uses_japanese_runtime_labels():
    block = ContentBlock(
        id="block-ja",
        project_id="project-ja",
        name="概要",
        block_type="field",
        content="既存の本文",
        ai_prompt="日本語の要約を作成してください",
        status="completed",
    )

    text = agent_api._build_ref_context(block, locale="ja-JP")

    assert "[参照対象]" in text
    assert "[この内容ブロックの AI プロンプト設定]" in text
    assert "[ステータス: completed]" in text
    assert "[引用目标]" not in text
    assert "该内容块的 AI 提示词配置" not in text
