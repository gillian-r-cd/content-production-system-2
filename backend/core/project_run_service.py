# backend/core/project_run_service.py
# 功能: 项目级调度服务，统一计算 ready 块并按模式执行（auto_trigger / start_all_ready）
# 主要函数: list_ready_blocks, run_project_blocks
# 数据结构: 以 project_id 为粒度，返回扫描/执行摘要

"""
项目级调度服务

第一版目标：
- 让 check-auto-triggers 和“全部开始”共用同一套 ready 判定
- 由后端统一循环扫描并执行，不再由前端递归 orchestrate
- 支持并发上限，但保持数据库写入与单块生成边界清晰
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException

from core.block_generation_service import generate_block_content_sync, list_ready_block_ids
from core.database import get_session_maker


VALID_PROJECT_RUN_MODES = {"auto_trigger", "start_all_ready"}


def list_ready_blocks(*, project_id: str, mode: str, db) -> list[str]:
    if mode not in VALID_PROJECT_RUN_MODES:
        raise HTTPException(status_code=400, detail=f"不支持的运行模式: {mode}")
    return list_ready_block_ids(project_id=project_id, db=db, mode=mode)


async def run_project_blocks(
    *,
    project_id: str,
    mode: str,
    max_concurrency: int = 4,
) -> dict[str, Any]:
    if mode not in VALID_PROJECT_RUN_MODES:
        raise HTTPException(status_code=400, detail=f"不支持的运行模式: {mode}")

    session_factory = get_session_maker()
    attempted_ids: set[str] = set()
    succeeded_ids: list[str] = []
    failed_items: list[dict[str, str]] = []
    rounds: list[dict[str, Any]] = []
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def _run_single(block_id: str) -> dict[str, Any]:
        async with semaphore:
            db = session_factory()
            try:
                result = await generate_block_content_sync(block_id=block_id, db=db)
                return {"ok": True, "block_id": block_id, "result": result}
            except HTTPException as exc:
                return {
                    "ok": False,
                    "block_id": block_id,
                    "error": str(exc.detail),
                }
            except Exception as exc:  # pragma: no cover
                return {
                    "ok": False,
                    "block_id": block_id,
                    "error": str(exc),
                }
            finally:
                db.close()

    while True:
        scan_db = session_factory()
        try:
            ready_ids = list_ready_block_ids(
                project_id=project_id,
                db=scan_db,
                mode=mode,
                exclude_ids=attempted_ids,
            )
        finally:
            scan_db.close()

        if not ready_ids:
            break

        attempted_ids.update(ready_ids)
        round_results = await asyncio.gather(*[_run_single(block_id) for block_id in ready_ids])
        round_summary = {
            "started_ids": ready_ids,
            "succeeded_ids": [item["block_id"] for item in round_results if item["ok"]],
            "failed_ids": [item["block_id"] for item in round_results if not item["ok"]],
        }
        rounds.append(round_summary)

        for item in round_results:
            if item["ok"]:
                succeeded_ids.append(item["block_id"])
            else:
                failed_items.append({
                    "block_id": item["block_id"],
                    "error": item["error"],
                })

    return {
        "project_id": project_id,
        "mode": mode,
        "rounds": rounds,
        "started_count": len(attempted_ids),
        "completed_count": len(succeeded_ids),
        "failed_count": len(failed_items),
        "failed_items": failed_items,
    }
