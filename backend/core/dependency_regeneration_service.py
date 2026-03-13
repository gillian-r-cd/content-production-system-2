# backend/core/dependency_regeneration_service.py
# 功能: 统一处理内容块依赖失效传播与项目级自动重生成调度
# 主要函数: finalize_block_content_change, invalidate_downstream_blocks,
#   schedule_project_auto_trigger, enqueue_project_auto_trigger
# 数据结构: DependencyUpdateSummary（受影响下游块摘要）、ContentBlock 依赖反向图

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from core.models import ContentBlock

logger = logging.getLogger("dependency_regeneration")

_PROJECT_AUTORUN_STATE_LOCK = threading.Lock()
_PROJECT_AUTORUN_RUNNING: set[str] = set()
_PROJECT_AUTORUN_PENDING: set[str] = set()


def _launch_auto_trigger_thread(project_id: str) -> None:
    thread = threading.Thread(
        target=enqueue_project_auto_trigger,
        args=(project_id,),
        daemon=True,
        name=f"auto-trigger-{project_id[:8]}",
    )
    thread.start()


@dataclass
class DependencyUpdateSummary:
    """描述一次上游内容变化对下游内容块造成的影响。"""

    affected_block_ids: list[str] = field(default_factory=list)
    affected_block_names: list[str] = field(default_factory=list)
    auto_regenerate_block_ids: list[str] = field(default_factory=list)
    auto_regenerate_block_names: list[str] = field(default_factory=list)
    manual_attention_block_ids: list[str] = field(default_factory=list)
    manual_attention_block_names: list[str] = field(default_factory=list)


def _list_active_project_field_blocks(*, project_id: str, db: Session) -> list[ContentBlock]:
    return db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,  # noqa: E711
        ContentBlock.block_type == "field",
    ).all()


def _has_content(block: ContentBlock) -> bool:
    return bool((getattr(block, "content", "") or "").strip())


def invalidate_downstream_blocks(*, source_block: ContentBlock, db: Session) -> DependencyUpdateSummary:
    """
    将 source_block 的所有下游内容块标记为依赖失效。

    规则：
    - 只处理同项目、未删除的 field 类型块
    - 仅当下游块当前已有内容时，才标记为 `needs_regeneration=True`
    - 递归传播到所有传递下游，确保 A -> B -> C 的链路能完整失效
    """

    summary = DependencyUpdateSummary()
    if getattr(source_block, "block_type", None) != "field":
        return summary

    all_fields = _list_active_project_field_blocks(project_id=source_block.project_id, db=db)
    dependents_by_dep_id: dict[str, list[ContentBlock]] = {}
    for block in all_fields:
        for dep_id in block.depends_on or []:
            dependents_by_dep_id.setdefault(dep_id, []).append(block)

    queue = list(dependents_by_dep_id.get(source_block.id, []))
    visited: set[str] = set()

    while queue:
        current = queue.pop(0)
        if current.id in visited:
            continue
        visited.add(current.id)
        queue.extend(dependents_by_dep_id.get(current.id, []))

        if not _has_content(current):
            continue

        current.needs_regeneration = True
        summary.affected_block_ids.append(current.id)
        summary.affected_block_names.append(current.name)

        if bool(getattr(current, "auto_generate", False)):
            summary.auto_regenerate_block_ids.append(current.id)
            summary.auto_regenerate_block_names.append(current.name)

        # 自动生成但仍需人工确认的块，也属于“仍需要人工处理”的范畴。
        if not (bool(getattr(current, "auto_generate", False)) and not bool(getattr(current, "need_review", False))):
            summary.manual_attention_block_ids.append(current.id)
            summary.manual_attention_block_names.append(current.name)

    return summary


def finalize_block_content_change(*, block: ContentBlock, db: Session) -> DependencyUpdateSummary:
    """
    在某个内容块完成一次有效内容变更后，清除自身失效标记并传播下游失效。

    适用于：
    - 手动保存内容
    - AI 生成/重生成
    - 回滚到历史版本
    - 其他正式内容覆写入口
    """

    block.needs_regeneration = False
    return invalidate_downstream_blocks(source_block=block, db=db)


def enqueue_project_auto_trigger(project_id: str) -> None:
    """
    串行执行指定项目的 auto_trigger 运行，并合并并发重复请求。

    同一项目在一次运行期间如果再次收到调度请求，只会被折叠为
    “当前轮跑完后再补跑一轮”，避免重复并发生成同一批块。
    """

    if not project_id:
        return

    with _PROJECT_AUTORUN_STATE_LOCK:
        if project_id in _PROJECT_AUTORUN_RUNNING:
            _PROJECT_AUTORUN_PENDING.add(project_id)
            return
        _PROJECT_AUTORUN_RUNNING.add(project_id)

    while True:
        try:
            from core.project_run_service import run_project_blocks

            asyncio.run(run_project_blocks(
                project_id=project_id,
                mode="auto_trigger",
            ))
        except Exception:  # pragma: no cover - 调度异常记录即可，不应打崩请求线程
            logger.exception("[dependency-regeneration] auto trigger run failed for project %s", project_id)

        with _PROJECT_AUTORUN_STATE_LOCK:
            if project_id in _PROJECT_AUTORUN_PENDING:
                _PROJECT_AUTORUN_PENDING.discard(project_id)
                continue
            _PROJECT_AUTORUN_RUNNING.discard(project_id)
            break


def schedule_project_auto_trigger(
    project_id: str,
    *,
    background_tasks: BackgroundTasks | None = None,
) -> None:
    """为当前项目安排一次 auto_trigger 运行。"""

    if not project_id:
        return
    if background_tasks is not None:
        background_tasks.add_task(_launch_auto_trigger_thread, project_id)
        return
    _launch_auto_trigger_thread(project_id)
