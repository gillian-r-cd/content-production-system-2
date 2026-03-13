# 功能: 统一构建内容块当前运行时表面的可读文本，供 Agent 引用与查询复用
# 主要函数: build_block_runtime_surface
# 数据结构: ContentBlock + blocks_by_id 映射

from __future__ import annotations

from core.content_block_reference import build_block_reference_label
from core.localization import DEFAULT_LOCALE, normalize_locale
from core.locale_text import rt
from core.models.content_block import ContentBlock
from core.pre_question_utils import normalize_pre_answers, normalize_pre_questions


def _bool_text(value: bool, locale: str) -> str:
    return rt(locale, "agent.reference_context.bool_yes") if value else rt(locale, "agent.reference_context.bool_no")


def _dependency_lines(
    block: ContentBlock,
    *,
    blocks_by_id: dict[str, ContentBlock] | None,
    locale: str,
) -> str:
    depends_on = getattr(block, "depends_on", None) or []
    if not depends_on:
        return rt(locale, "agent.reference_context.none")

    lines: list[str] = []
    for dep_id in depends_on:
        dep_block = blocks_by_id.get(dep_id) if blocks_by_id else None
        if dep_block:
            label = build_block_reference_label(dep_block, blocks_by_id=blocks_by_id)
        else:
            label = f"id:{dep_id}"
        lines.append(f"- {label}")
    return "\n".join(lines)


def _pre_question_lines(block: ContentBlock, *, locale: str) -> str:
    questions = normalize_pre_questions(getattr(block, "pre_questions", None) or [])
    if not questions:
        return rt(locale, "agent.reference_context.none")

    lines: list[str] = []
    for item in questions:
        badge = rt(
            locale,
            "agent.reference_context.pre_question_required" if item.get("required") else "agent.reference_context.pre_question_optional",
        )
        lines.append(f"- [{badge}] {item['question']}")
    return "\n".join(lines)


def _pre_answer_lines(block: ContentBlock, *, locale: str) -> str:
    questions = normalize_pre_questions(getattr(block, "pre_questions", None) or [])
    answers = normalize_pre_answers(getattr(block, "pre_answers", None) or {}, questions)
    if not answers:
        return rt(locale, "agent.reference_context.none")

    question_map = {str(item["id"]): str(item["question"]) for item in questions}
    lines: list[str] = []
    for question_id, answer in answers.items():
        question_label = question_map.get(str(question_id), str(question_id))
        lines.append(f"- {question_label}: {answer}")
    return "\n".join(lines)


def build_block_runtime_surface(
    block: ContentBlock,
    *,
    blocks_by_id: dict[str, ContentBlock] | None = None,
    locale: str = DEFAULT_LOCALE,
) -> str:
    """返回当前内容块对 Agent 暴露的正式运行时表面文本。"""

    normalized_locale = normalize_locale(locale)
    none_text = rt(normalized_locale, "agent.reference_context.none")
    content = getattr(block, "content", "") or ""
    ai_prompt = getattr(block, "ai_prompt", "") or ""
    status = getattr(block, "status", "") or none_text
    block_type = getattr(block, "block_type", "") or none_text
    special_handler = getattr(block, "special_handler", None) or none_text
    model_override = getattr(block, "model_override", None) or rt(normalized_locale, "agent.reference_context.default_model")
    reference_label = build_block_reference_label(block, blocks_by_id=blocks_by_id)

    parts = [
        rt(normalized_locale, "agent.reference_context.target", label=reference_label),
        content if content.strip() else rt(normalized_locale, "agent.reference_context.empty_content"),
        f"\n{rt(normalized_locale, 'agent.reference_context.ai_prompt')}\n{ai_prompt if ai_prompt.strip() else none_text}",
        f"\n{rt(normalized_locale, 'agent.reference_context.depends_on')}\n{_dependency_lines(block, blocks_by_id=blocks_by_id, locale=normalized_locale)}",
        f"\n{rt(normalized_locale, 'agent.reference_context.pre_questions')}\n{_pre_question_lines(block, locale=normalized_locale)}",
        f"\n{rt(normalized_locale, 'agent.reference_context.pre_answers')}\n{_pre_answer_lines(block, locale=normalized_locale)}",
        rt(
            normalized_locale,
            "agent.reference_context.need_review",
            value=_bool_text(bool(getattr(block, "need_review", False)), normalized_locale),
        ),
        rt(
            normalized_locale,
            "agent.reference_context.auto_generate",
            value=_bool_text(bool(getattr(block, "auto_generate", False)), normalized_locale),
        ),
        rt(
            normalized_locale,
            "agent.reference_context.needs_regeneration",
            value=_bool_text(bool(getattr(block, "needs_regeneration", False)), normalized_locale),
        ),
        rt(normalized_locale, "agent.reference_context.model_override", value=model_override),
        rt(normalized_locale, "agent.reference_context.status", status=status),
        rt(normalized_locale, "agent.reference_context.block_type", block_type=block_type),
        rt(normalized_locale, "agent.reference_context.special_handler", special_handler=special_handler),
    ]
    return "\n".join(parts)
