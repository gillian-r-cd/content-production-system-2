"""
从本地数据库抽取 DeepResearch 真实样本，补齐为 20 条评测样本。

运行:
  cd backend && python -m scripts.build_deepresearch_samples
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.database import get_session_maker, init_db
from core.models import ChatMessage


TARGET_COUNT = 20


def _find_previous_user(rows: list[ChatMessage], idx: int) -> ChatMessage | None:
    for i in range(idx - 1, -1, -1):
        if rows[i].role == "user":
            return rows[i]
    return None


def _extract_real_samples() -> list[dict[str, Any]]:
    SessionLocal = get_session_maker()
    db = SessionLocal()
    try:
        rows = db.query(ChatMessage).order_by(ChatMessage.created_at.asc()).all()
        samples: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            if row.role != "assistant":
                continue
            meta = row.message_metadata or {}
            tools = meta.get("tools_used") or []
            if "run_research" not in tools:
                continue
            user_msg = _find_previous_user(rows, i)
            research_meta = meta.get("run_research_metrics") or {}
            sample = {
                "request": (user_msg.content if user_msg else "").strip(),
                "expected_aspects": [],
                "tools_used": tools,
                "search_queries": research_meta.get("search_queries", []),
                "sources": research_meta.get("sources", []),
                "report_text": row.content or "",
                "from_db": True,
                "assistant_message_id": row.id,
            }
            samples.append(sample)
        return samples
    finally:
        db.close()


def _build_pending_samples(start_idx: int, count: int) -> list[dict[str, Any]]:
    out = []
    for i in range(count):
        n = start_idx + i + 1
        out.append({
            "request": f"[待执行样本 {n}] 请补充真实 DeepResearch 请求",
            "expected_aspects": [],
            "tools_used": ["run_research"],
            "search_queries": [],
            "sources": [],
            "report_text": "",
            "from_db": False,
            "status": "pending_execution",
        })
    return out


def main() -> None:
    init_db()
    real = _extract_real_samples()
    real = real[:TARGET_COUNT]
    if len(real) < TARGET_COUNT:
        real.extend(_build_pending_samples(len(real), TARGET_COUNT - len(real)))

    out_path = Path("scripts/data/deepresearch_samples_20.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(real, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"DeepResearch 样本已生成: {out_path}")
    print(f"  - real_from_db: {sum(1 for s in real if s.get('from_db'))}")
    print(f"  - pending_execution: {sum(1 for s in real if not s.get('from_db'))}")


if __name__ == "__main__":
    main()

