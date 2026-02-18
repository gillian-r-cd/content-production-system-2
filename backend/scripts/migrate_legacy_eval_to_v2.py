"""
旧 Eval（EvalRun/EvalTask/EvalTrial）迁移到 Eval V2。

运行:
  cd backend && python -m scripts.migrate_legacy_eval_to_v2 --execute
  cd backend && python -m scripts.migrate_legacy_eval_to_v2 --dry-run
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from core.database import get_session_maker
from core.models import (
    EvalRun,
    EvalTask,
    EvalTrial,
    EvalTaskV2,
    EvalTrialConfigV2,
    EvalTrialResultV2,
    generate_uuid,
)
from core.tools.eval_v2_service import aggregate_task_scores


def _map_form_type(old_task: EvalTask) -> str:
    mode = (old_task.interaction_mode or "").strip().lower()
    role = (old_task.simulator_type or "").strip().lower()
    if mode == "scenario":
        return "scenario"
    if role == "consumer":
        return "experience"
    if mode in {"review", "dialogue"}:
        return "review"
    return "assessment"


def _build_form_config(old_task: EvalTask, form_type: str) -> dict:
    sim_cfg = old_task.simulator_config or {}
    persona = old_task.persona_config or {}
    if form_type == "review":
        return {
            "system_prompt": sim_cfg.get("system_prompt", ""),
            "persona_prompt": persona.get("prompt", persona.get("background", "")),
        }
    if form_type == "experience":
        return {
            "persona_prompt": persona.get("prompt", persona.get("background", "")),
        }
    if form_type == "scenario":
        return {
            "role_a_prompt": sim_cfg.get("system_prompt", ""),
            "role_b_prompt": sim_cfg.get("secondary_prompt", ""),
            "max_turns": int(sim_cfg.get("max_turns", 5) or 5),
        }
    return {}


def migrate_legacy_eval_to_v2(db: Session, dry_run: bool = True) -> dict:
    stats = {
        "tasks_created": 0,
        "configs_created": 0,
        "results_created": 0,
        "results_skipped_existing": 0,
        "tasks_skipped_existing": 0,
        "orphan_trials_skipped": 0,
    }

    legacy_tasks: List[EvalTask] = db.query(EvalTask).order_by(EvalTask.created_at.asc()).all()
    v2_task_map: Dict[str, Tuple[EvalTaskV2, EvalTrialConfigV2]] = {}

    for old_task in legacy_tasks:
        marker = f"legacy_eval_task_id={old_task.id}"
        existing_task = (
            db.query(EvalTaskV2)
            .filter(EvalTaskV2.project_id == old_task.eval_run.project_id)
            .filter(EvalTaskV2.description.like(f"%{marker}%"))
            .first()
        )
        if existing_task:
            cfg = (
                db.query(EvalTrialConfigV2)
                .filter(EvalTrialConfigV2.task_id == existing_task.id)
                .order_by(EvalTrialConfigV2.order_index.asc())
                .first()
            )
            if cfg:
                v2_task_map[old_task.id] = (existing_task, cfg)
            stats["tasks_skipped_existing"] += 1
            continue

        form_type = _map_form_type(old_task)
        task_v2 = EvalTaskV2(
            id=generate_uuid(),
            project_id=old_task.eval_run.project_id,
            name=old_task.name,
            description=f"[migrated] {marker}; legacy_eval_run_id={old_task.eval_run_id}",
            order_index=old_task.order_index or 0,
            status="pending",
        )
        cfg_v2 = EvalTrialConfigV2(
            id=generate_uuid(),
            task_id=task_v2.id,
            name=f"{old_task.name}-legacy",
            form_type=form_type,
            target_block_ids=old_task.target_block_ids or [],
            grader_ids=[],
            grader_weights={},
            repeat_count=1,
            probe="",
            form_config=_build_form_config(old_task, form_type),
            order_index=0,
        )
        if not dry_run:
            db.add(task_v2)
            db.add(cfg_v2)
        v2_task_map[old_task.id] = (task_v2, cfg_v2)
        stats["tasks_created"] += 1
        stats["configs_created"] += 1

    # 按（旧 task_id, 旧 run_id）划分 batch，稳定且可幂等
    trials = db.query(EvalTrial).order_by(EvalTrial.created_at.asc()).all()
    grouped: Dict[Tuple[str, str], List[EvalTrial]] = defaultdict(list)
    for tr in trials:
        if not tr.eval_task_id or tr.eval_task_id not in v2_task_map:
            stats["orphan_trials_skipped"] += 1
            continue
        grouped[(tr.eval_task_id, tr.eval_run_id)].append(tr)

    for (legacy_task_id, legacy_run_id), rows in grouped.items():
        task_v2, cfg_v2 = v2_task_map[legacy_task_id]
        batch_id = f"legacy-{legacy_run_id[:8]}-{legacy_task_id[:8]}"
        sorted_rows = sorted(rows, key=lambda x: (x.created_at or 0, x.id))

        for repeat_index, row in enumerate(sorted_rows):
            exists = (
                db.query(EvalTrialResultV2)
                .filter(
                    EvalTrialResultV2.task_id == task_v2.id,
                    EvalTrialResultV2.trial_config_id == cfg_v2.id,
                    EvalTrialResultV2.batch_id == batch_id,
                    EvalTrialResultV2.repeat_index == repeat_index,
                )
                .first()
            )
            if exists:
                stats["results_skipped_existing"] += 1
                continue

            result = EvalTrialResultV2(
                id=generate_uuid(),
                task_id=task_v2.id,
                trial_config_id=cfg_v2.id,
                project_id=task_v2.project_id,
                batch_id=batch_id,
                repeat_index=repeat_index,
                form_type=cfg_v2.form_type,
                process=row.nodes or [],
                grader_results=row.grader_outputs or [],
                dimension_scores=(row.result or {}).get("scores", {}) if isinstance(row.result, dict) else {},
                overall_score=row.overall_score,
                llm_calls=row.llm_calls or [],
                tokens_in=row.tokens_in or 0,
                tokens_out=row.tokens_out or 0,
                cost=row.cost or 0.0,
                status=row.status or "completed",
                error=row.error or "",
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            if not dry_run:
                db.add(result)
            stats["results_created"] += 1

        # 刷新 task 最新聚合
        if not dry_run:
            db.flush()
            latest_rows = (
                db.query(EvalTrialResultV2)
                .filter(
                    EvalTrialResultV2.task_id == task_v2.id,
                    EvalTrialResultV2.batch_id == batch_id,
                )
                .all()
            )
            agg_input = [
                {"overall_score": r.overall_score, "dimension_scores": r.dimension_scores or {}}
                for r in latest_rows
                if r.status == "completed"
            ]
            agg = aggregate_task_scores(agg_input)
            task_v2.latest_batch_id = batch_id
            task_v2.latest_scores = agg
            task_v2.latest_overall = (agg.get("overall") or {}).get("mean") if agg.get("overall") else None
            task_v2.status = "completed" if latest_rows else task_v2.status
            task_v2.last_executed_at = max((r.created_at for r in latest_rows if r.created_at), default=task_v2.last_executed_at)

    if not dry_run:
        db.commit()
    else:
        db.rollback()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="实际执行迁移")
    parser.add_argument("--dry-run", action="store_true", help="仅预演（默认）")
    args = parser.parse_args()

    dry_run = not args.execute or args.dry_run
    SessionLocal = get_session_maker()
    db = SessionLocal()
    try:
        stats = migrate_legacy_eval_to_v2(db, dry_run=dry_run)
        mode = "DRY_RUN" if dry_run else "EXECUTE"
        print(f"[{mode}] {stats}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

