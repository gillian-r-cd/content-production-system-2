"""
迁移 T16：历史 auto_split 草稿 payload 归一化并重跑 validate。

运行:
  cd backend && python -m scripts.migrate_t16_auto_split_draft_payload --dry-run
  cd backend && python -m scripts.migrate_t16_auto_split_draft_payload --execute
"""

from __future__ import annotations

import argparse
from datetime import datetime, UTC
from typing import Any

from sqlalchemy.orm import Session

from core.database import get_session_maker, init_db
from core.models import ContentBlock, ProjectStructureDraft
from core.project_structure_compiler import compile_project_structure_draft


TYPE_MAP = {
    "phase": "group",
    "proposal": "field",
}


def _normalize_json(value: Any) -> tuple[Any, bool]:
    changed = False

    if isinstance(value, list):
        normalized_items = []
        for item in value:
            normalized_item, item_changed = _normalize_json(item)
            normalized_items.append(normalized_item)
            changed = changed or item_changed
        return normalized_items, changed

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, raw in value.items():
            if key in {"guidance_input", "guidance_output"}:
                changed = True
                continue
            normalized_raw, raw_changed = _normalize_json(raw)
            changed = changed or raw_changed
            if key == "block_type" and isinstance(normalized_raw, str):
                mapped = TYPE_MAP.get(normalized_raw, normalized_raw)
                if mapped != normalized_raw:
                    changed = True
                normalized[key] = mapped
            else:
                normalized[key] = normalized_raw
        return normalized, changed

    return value, False


def migrate_t16_auto_split_draft_payload(db: Session, dry_run: bool = True) -> dict[str, int]:
    stats = {
        "drafts_total": 0,
        "drafts_changed": 0,
        "validate_passed": 0,
        "validate_failed": 0,
    }

    drafts = db.query(ProjectStructureDraft).filter(
        ProjectStructureDraft.draft_type == "auto_split"
    ).all()
    stats["drafts_total"] = len(drafts)

    for draft in drafts:
        payload = draft.draft_payload or {}
        normalized_payload, payload_changed = _normalize_json(payload)
        if payload_changed:
            draft.draft_payload = normalized_payload
            stats["drafts_changed"] += 1

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
        if result.validation_errors:
            draft.status = "draft"
            stats["validate_failed"] += 1
        else:
            draft.status = "validated"
            stats["validate_passed"] += 1

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
        stats = migrate_t16_auto_split_draft_payload(db, dry_run=dry_run)
        mode = "DRY_RUN" if dry_run else "EXECUTE"
        print(f"[{mode}] migrate_t16_auto_split_draft_payload stats:")
        for key, value in stats.items():
            print(f"  - {key}: {value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
