"""
迁移生成前提问到结构化 schema。

运行:
  cd backend && python -m scripts.migrate_pre_question_schema --dry-run
  cd backend && python -m scripts.migrate_pre_question_schema --execute
"""

from __future__ import annotations

import argparse
from datetime import datetime, UTC
from typing import Any

from sqlalchemy.orm import Session

from core.database import get_session_maker, init_db
from core.models import ContentBlock, FieldTemplate, PhaseTemplate, ProjectField, ProjectStructureDraft
from core.pre_question_utils import normalize_pre_answers, normalize_pre_questions
from core.project_structure_compiler import compile_project_structure_draft


def _normalize_pre_question_container(payload: Any) -> tuple[Any, bool]:
    changed = False

    if isinstance(payload, list):
        normalized_items = []
        for item in payload:
            normalized_item, item_changed = _normalize_pre_question_container(item)
            normalized_items.append(normalized_item)
            changed = changed or item_changed
        return normalized_items, changed

    if isinstance(payload, dict):
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            normalized_value, value_changed = _normalize_pre_question_container(value)
            normalized[key] = normalized_value
            changed = changed or value_changed

        if "pre_questions" in normalized or "pre_answers" in normalized:
            normalized_questions = normalize_pre_questions(normalized.get("pre_questions", []))
            normalized_answers = normalize_pre_answers(
                normalized.get("pre_answers", {}),
                normalized_questions,
            )
            if normalized.get("pre_questions") != normalized_questions:
                normalized["pre_questions"] = normalized_questions
                changed = True
            if normalized.get("pre_answers") != normalized_answers:
                normalized["pre_answers"] = normalized_answers
                changed = True

        return normalized, changed

    return payload, False


def migrate_pre_question_schema(db: Session, dry_run: bool = True) -> dict[str, int]:
    stats = {
        "content_blocks_scanned": 0,
        "content_blocks_changed": 0,
        "project_fields_scanned": 0,
        "project_fields_changed": 0,
        "field_templates_scanned": 0,
        "field_templates_changed": 0,
        "phase_templates_scanned": 0,
        "phase_templates_changed": 0,
        "drafts_scanned": 0,
        "drafts_changed": 0,
        "drafts_revalidated": 0,
    }

    blocks = db.query(ContentBlock).all()
    stats["content_blocks_scanned"] = len(blocks)
    for block in blocks:
        normalized_questions = normalize_pre_questions(block.pre_questions or [])
        normalized_answers = normalize_pre_answers(block.pre_answers or {}, normalized_questions)
        if block.pre_questions != normalized_questions or block.pre_answers != normalized_answers:
            block.pre_questions = normalized_questions
            block.pre_answers = normalized_answers
            stats["content_blocks_changed"] += 1

    fields = db.query(ProjectField).all()
    stats["project_fields_scanned"] = len(fields)
    for field in fields:
        normalized_questions = normalize_pre_questions(field.pre_questions or [])
        normalized_answers = normalize_pre_answers(field.pre_answers or {}, normalized_questions)
        if field.pre_questions != normalized_questions or field.pre_answers != normalized_answers:
            field.pre_questions = normalized_questions
            field.pre_answers = normalized_answers
            stats["project_fields_changed"] += 1

    field_templates = db.query(FieldTemplate).all()
    stats["field_templates_scanned"] = len(field_templates)
    for template in field_templates:
        template_changed = False
        normalized_fields, fields_changed = _normalize_pre_question_container(template.fields or [])
        normalized_root_nodes, root_nodes_changed = _normalize_pre_question_container(template.root_nodes or [])
        if fields_changed:
            template.fields = normalized_fields
            template_changed = True
        if root_nodes_changed:
            template.root_nodes = normalized_root_nodes
            template_changed = True
        if template_changed:
            stats["field_templates_changed"] += 1

    phase_templates = db.query(PhaseTemplate).all()
    stats["phase_templates_scanned"] = len(phase_templates)
    for template in phase_templates:
        normalized_phases, phases_changed = _normalize_pre_question_container(template.phases or [])
        if phases_changed:
            template.phases = normalized_phases
            stats["phase_templates_changed"] += 1

    drafts = db.query(ProjectStructureDraft).all()
    stats["drafts_scanned"] = len(drafts)
    for draft in drafts:
        normalized_payload, payload_changed = _normalize_pre_question_container(draft.draft_payload or {})
        if payload_changed:
            draft.draft_payload = normalized_payload
            stats["drafts_changed"] += 1

        if draft.draft_type == "auto_split":
            existing_blocks = db.query(ContentBlock).filter(
                ContentBlock.project_id == draft.project_id,
                ContentBlock.deleted_at == None,  # noqa: E711
            ).all()
            result = compile_project_structure_draft(
                draft,
                existing_project_blocks=existing_blocks,
                batch_name=draft.name,
            )
            draft.validation_errors = result.validation_errors
            draft.last_validated_at = datetime.now(UTC).replace(tzinfo=None)
            draft.status = "validated" if not result.validation_errors else "draft"
            stats["drafts_revalidated"] += 1

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="实际执行迁移")
    parser.add_argument("--dry-run", action="store_true", help="仅预演（默认）")
    args = parser.parse_args()

    dry_run = not args.execute or args.dry_run
    init_db()
    SessionLocal = get_session_maker()
    db = SessionLocal()
    try:
        stats = migrate_pre_question_schema(db, dry_run=dry_run)
        mode = "DRY_RUN" if dry_run else "EXECUTE"
        print(f"[{mode}] migrate_pre_question_schema stats:")
        for key, value in stats.items():
            print(f"  - {key}: {value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
