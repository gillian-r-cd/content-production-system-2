from __future__ import annotations

from copy import deepcopy
from typing import Any
import uuid


def _generate_uuid() -> str:
    return str(uuid.uuid4())


def normalize_pre_questions(
    value: Any,
    *,
    default_required: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in value:
        if isinstance(item, dict):
            question = str(
                item.get("question")
                or item.get("text")
                or item.get("label")
                or item.get("name")
                or ""
            ).strip()
            if not question:
                continue
            question_id = str(
                item.get("id")
                or item.get("question_id")
                or ""
            ).strip() or _generate_uuid()
            required = bool(item.get("required", default_required))
            extra = {
                key: deepcopy(raw_value)
                for key, raw_value in item.items()
                if key not in {"id", "question_id", "question", "text", "label", "name", "required"}
            }
        else:
            question = str(item or "").strip()
            if not question:
                continue
            question_id = _generate_uuid()
            required = default_required
            extra = {}

        if question_id in seen_ids:
            question_id = _generate_uuid()
        seen_ids.add(question_id)

        normalized.append({
            "id": question_id,
            "question": question,
            "required": required,
            **extra,
        })

    return normalized


def normalize_pre_answers(
    value: Any,
    questions: Any,
) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    normalized_questions = normalize_pre_questions(questions)
    question_id_map = {str(item["id"]): item for item in normalized_questions}
    question_text_map = {
        str(item["question"]): str(item["id"])
        for item in normalized_questions
    }

    normalized: dict[str, str] = {}
    for raw_key, raw_answer in value.items():
        key = str(raw_key or "").strip()
        answer = str(raw_answer or "").strip()
        if not key or not answer:
            continue

        if key in question_id_map:
            normalized[key] = answer
            continue

        mapped_id = question_text_map.get(key)
        if mapped_id:
            normalized[mapped_id] = answer

    return normalized


def iter_answered_pre_question_items(
    questions: Any,
    answers: Any,
) -> list[tuple[dict[str, Any], str]]:
    normalized_questions = normalize_pre_questions(questions)
    normalized_answers = normalize_pre_answers(answers, normalized_questions)

    if normalized_questions:
        result: list[tuple[dict[str, Any], str]] = []
        for item in normalized_questions:
            answer = str(normalized_answers.get(str(item["id"]), "")).strip()
            if answer:
                result.append((item, answer))
        return result

    if not isinstance(answers, dict):
        return []

    fallback: list[tuple[dict[str, Any], str]] = []
    for raw_key, raw_answer in answers.items():
        key = str(raw_key or "").strip()
        answer = str(raw_answer or "").strip()
        if not key or not answer:
            continue
        fallback.append(({
            "id": key,
            "question": key,
            "required": False,
        }, answer))
    return fallback


def list_missing_required_pre_questions(
    questions: Any,
    answers: Any,
) -> list[dict[str, Any]]:
    normalized_questions = normalize_pre_questions(questions)
    normalized_answers = normalize_pre_answers(answers, normalized_questions)

    missing: list[dict[str, Any]] = []
    for item in normalized_questions:
        if not bool(item.get("required", False)):
            continue
        answer = str(normalized_answers.get(str(item["id"]), "")).strip()
        if not answer:
            missing.append(item)
    return missing
