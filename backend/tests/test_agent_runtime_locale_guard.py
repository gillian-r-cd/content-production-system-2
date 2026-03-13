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
        depends_on=[],
        pre_questions=[],
        pre_answers={},
        need_review=True,
        auto_generate=False,
        model_override=None,
        special_handler=None,
    )

    text = agent_api._build_ref_context(block, locale="ja-JP")

    assert "[参照対象]" in text
    assert "[この内容ブロックの AI プロンプト設定]" in text
    assert "[依存コンテンツ]" in text
    assert "[事前質問]" in text
    assert "[現在の回答]" in text
    assert "[手動確認が必要: はい]" in text
    assert "[自動生成: いいえ]" in text
    assert "[再生成待ち: いいえ]" in text
    assert "[モデル上書き: 既定モデル]" in text
    assert "[ステータス: completed]" in text
    assert "[ブロック種別: field]" in text
    assert "[特殊ハンドラ: （なし）]" in text
    assert "[引用目标]" not in text
    assert "该内容块的 AI 提示词配置" not in text


def test_build_ref_context_keeps_full_ai_prompt_without_truncation():
    suffix = "PROMPT-END-UNTRUNCATED"
    ai_prompt = ("日本語の要約を作成してください。" * 120) + suffix
    block = ContentBlock(
        id="block-full",
        project_id="project-ja",
        name="概要",
        block_type="field",
        content="既存の本文",
        ai_prompt=ai_prompt,
        status="completed",
    )

    text = agent_api._build_ref_context(block, locale="ja-JP")

    assert suffix in text
    assert ai_prompt in text


def test_build_ref_context_includes_visible_runtime_fields_and_excludes_hidden_legacy_fields():
    block = ContentBlock(
        id="block-surface",
        project_id="project-zh",
        name="正文块",
        block_type="field",
        content="这是正文",
        ai_prompt="请根据依赖写成总结",
        status="in_progress",
        depends_on=["dep-1"],
        pre_questions=[{"id": "pq-1", "question": "目标受众是谁？", "required": True}],
        pre_answers={"pq-1": "初学者"},
        need_review=False,
        auto_generate=True,
        model_override="gpt-4.1-mini",
        special_handler="evaluate",
        constraints={"max_length": 50},
        guidance_input="legacy in",
        guidance_output="legacy out",
    )
    dependency = ContentBlock(
        id="dep-1",
        project_id="project-zh",
        name="依赖块",
        block_type="field",
        content="依赖正文",
    )

    text = agent_api._build_ref_context(
        block,
        blocks_by_id={
            block.id: block,
            dependency.id: dependency,
        },
        locale="zh-CN",
    )

    assert "[依赖内容块]" in text
    assert "依赖块 | id:dep-1" in text
    assert "[生成前提问]" in text
    assert "[必答] 目标受众是谁？" in text
    assert "[当前回答]" in text
    assert "目标受众是谁？: 初学者" in text
    assert "[需要人工确认: 否]" in text
    assert "[自动生成: 是]" in text
    assert "[待重新生成: 否]" in text
    assert "[模型覆盖: gpt-4.1-mini]" in text
    assert "[特殊处理器: evaluate]" in text
    assert "constraints" not in text
    assert "legacy in" not in text
    assert "legacy out" not in text
