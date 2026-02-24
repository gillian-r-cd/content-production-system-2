"""
按 project + mode 回填 Conversation，并为历史 ChatMessage 补写 conversation_id。

运行:
  cd backend && python -m scripts.migrate_conversations --dry-run
  cd backend && python -m scripts.migrate_conversations --execute
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from core.database import get_session_maker, init_db
from core.models import ChatMessage, Conversation, generate_uuid


def _resolve_mode(message: ChatMessage) -> str:
    meta = message.message_metadata or {}
    return (meta.get("mode") or "assistant").strip() or "assistant"


def migrate_conversations(db: Session, dry_run: bool = True) -> dict:
    stats = {
        "groups_found": 0,
        "conversations_created": 0,
        "messages_backfilled": 0,
        "existing_conversations_reused": 0,
    }

    messages = db.query(ChatMessage).order_by(ChatMessage.created_at.asc()).all()
    grouped: Dict[Tuple[str, str], List[ChatMessage]] = defaultdict(list)
    for m in messages:
        if m.conversation_id:
            continue
        grouped[(m.project_id, _resolve_mode(m))].append(m)

    stats["groups_found"] = len(grouped)

    for (project_id, mode), rows in grouped.items():
        existing = db.query(Conversation).filter(
            Conversation.project_id == project_id,
            Conversation.mode == mode,
            Conversation.status == "active",
        ).order_by(Conversation.created_at.asc()).first()

        if existing:
            conv = existing
            stats["existing_conversations_reused"] += 1
        else:
            first_user = next((r for r in rows if r.role == "user"), rows[0] if rows else None)
            title_seed = (first_user.content if first_user else "历史会话") if first_user else "历史会话"
            conv = Conversation(
                id=generate_uuid(),
                project_id=project_id,
                mode=mode,
                title=(title_seed or "历史会话")[:40],
                status="active",
                bootstrap_policy="memory_only",
                last_message_at=max((r.created_at for r in rows if r.created_at), default=datetime.now()),
                message_count=len(rows),
            )
            if not dry_run:
                db.add(conv)
                db.flush()
            stats["conversations_created"] += 1

        for row in rows:
            row.conversation_id = conv.id
            stats["messages_backfilled"] += 1

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
    # 先确保 schema 补齐（兼容旧库缺 conversation_id 字段）
    init_db()
    SessionLocal = get_session_maker()
    db = SessionLocal()
    try:
        stats = migrate_conversations(db, dry_run=dry_run)
        mode = "DRY_RUN" if dry_run else "EXECUTE"
        print(f"[{mode}] migrate_conversations stats:")
        for k, v in stats.items():
            print(f"  - {k}: {v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

