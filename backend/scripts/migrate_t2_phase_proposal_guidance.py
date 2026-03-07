"""
迁移 T2：phase/proposal/guidance 历史数据收敛到 group/field。

运行:
  cd backend && python -m scripts.migrate_t2_phase_proposal_guidance --dry-run
  cd backend && python -m scripts.migrate_t2_phase_proposal_guidance --execute
"""

from __future__ import annotations

import argparse
from typing import Any

from sqlalchemy.orm import Session

from core.database import get_session_maker, init_db
from core.models import ContentBlock, FieldTemplate, PhaseTemplate


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

            if key in {"block_type", "type"} and isinstance(normalized_raw, str):
                mapped = TYPE_MAP.get(normalized_raw, normalized_raw)
                if mapped != normalized_raw:
                    changed = True
                normalized[key] = mapped
            else:
                normalized[key] = normalized_raw
        return normalized, changed

    return value, False


def migrate_t2_phase_proposal_guidance(db: Session, dry_run: bool = True) -> dict[str, int]:
    stats = {
        "content_blocks_scanned": 0,
        "content_blocks_changed": 0,
        "content_blocks_type_changed": 0,
        "content_blocks_guidance_cleared": 0,
        "field_templates_scanned": 0,
        "field_templates_changed": 0,
        "phase_templates_scanned": 0,
        "phase_templates_changed": 0,
    }

    blocks = db.query(ContentBlock).all()
    stats["content_blocks_scanned"] = len(blocks)
    for block in blocks:
        block_changed = False

        mapped_type = TYPE_MAP.get(block.block_type, block.block_type)
        if mapped_type != block.block_type:
            block.block_type = mapped_type
            stats["content_blocks_type_changed"] += 1
            block_changed = True

        if getattr(block, "guidance_input", None):
            block.guidance_input = ""
            stats["content_blocks_guidance_cleared"] += 1
            block_changed = True
        if getattr(block, "guidance_output", None):
            block.guidance_output = ""
            stats["content_blocks_guidance_cleared"] += 1
            block_changed = True

        if block_changed:
            stats["content_blocks_changed"] += 1

    field_templates = db.query(FieldTemplate).all()
    stats["field_templates_scanned"] = len(field_templates)
    for template in field_templates:
        template_changed = False

        normalized_root_nodes, root_changed = _normalize_json(template.root_nodes or [])
        if root_changed:
            template.root_nodes = normalized_root_nodes
            template_changed = True

        normalized_fields, fields_changed = _normalize_json(template.fields or [])
        if fields_changed:
            template.fields = normalized_fields
            template_changed = True

        if template_changed:
            stats["field_templates_changed"] += 1

    phase_templates = db.query(PhaseTemplate).all()
    stats["phase_templates_scanned"] = len(phase_templates)
    for template in phase_templates:
        normalized_phases, phases_changed = _normalize_json(template.phases or [])
        if phases_changed:
            template.phases = normalized_phases
            stats["phase_templates_changed"] += 1

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
        stats = migrate_t2_phase_proposal_guidance(db, dry_run=dry_run)
        mode = "DRY_RUN" if dry_run else "EXECUTE"
        print(f"[{mode}] migrate_t2_phase_proposal_guidance stats:")
        for key, value in stats.items():
            print(f"  - {key}: {value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
