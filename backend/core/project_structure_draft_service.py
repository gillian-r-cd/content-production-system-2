# backend/core/project_structure_draft_service.py
# 功能: 项目级结构草稿的公共 service，供 API 与 Agent 共用
# 主要函数: get_or_create_auto_split_draft(), split_auto_split_draft(), validate_auto_split_draft(), apply_auto_split_draft()
# 数据结构: ProjectStructureDraft + split_config + draft_payload

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.models import Project, ProjectStructureDraft
from core.pre_question_utils import normalize_pre_questions
from core.project_split_service import split_source_text
from core.project_structure_apply_service import apply_project_structure_draft
from core.project_structure_compiler import compile_project_structure_draft


def normalize_node_types(nodes: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in nodes or []:
        if not isinstance(raw, dict):
            continue
        node = dict(raw)
        block_type = str(node.get("block_type") or "").strip().lower()
        if block_type in {"phase", "group"}:
            node["block_type"] = "group"
        elif block_type in {"field", "proposal"}:
            node["block_type"] = "field"
        else:
            node["block_type"] = "field"
        node.pop("guidance_input", None)
        node.pop("guidance_output", None)
        node["pre_questions"] = normalize_pre_questions(node.get("pre_questions"))
        node["children"] = normalize_node_types(
            node.get("children") if isinstance(node.get("children"), list) else []
        )
        normalized.append(node)
    return normalized


def normalize_draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "chunks": data.get("chunks") if isinstance(data.get("chunks"), list) else [],
        "plans": [
            {
                **(plan if isinstance(plan, dict) else {}),
                "root_nodes": normalize_node_types(
                    (plan or {}).get("root_nodes")
                    if isinstance((plan or {}).get("root_nodes"), list) else []
                ),
            }
            for plan in (data.get("plans") if isinstance(data.get("plans"), list) else [])
            if isinstance(plan, dict)
        ],
        "shared_root_nodes": normalize_node_types(
            data.get("shared_root_nodes") if isinstance(data.get("shared_root_nodes"), list) else []
        ),
        "aggregate_root_nodes": normalize_node_types(
            data.get("aggregate_root_nodes") if isinstance(data.get("aggregate_root_nodes"), list) else []
        ),
        "ui_state": data.get("ui_state") if isinstance(data.get("ui_state"), dict) else {},
    }


def serialize_draft(draft: ProjectStructureDraft) -> dict[str, Any]:
    return {
        "id": draft.id,
        "project_id": draft.project_id,
        "draft_type": draft.draft_type,
        "name": draft.name,
        "status": draft.status,
        "source_text": draft.source_text or "",
        "split_config": draft.split_config or {},
        "draft_payload": normalize_draft_payload(draft.draft_payload or {}),
        "validation_errors": draft.validation_errors or [],
        "last_validated_at": draft.last_validated_at.isoformat() if draft.last_validated_at else None,
        "apply_count": draft.apply_count or 0,
        "last_applied_at": draft.last_applied_at.isoformat() if draft.last_applied_at else None,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }


def summarize_draft(draft: ProjectStructureDraft) -> dict[str, Any]:
    payload = normalize_draft_payload(draft.draft_payload or {})
    return {
        "draft_type": draft.draft_type,
        "status": draft.status,
        "chunk_count": len(payload.get("chunks") or []),
        "plan_count": len(payload.get("plans") or []),
        "shared_root_node_count": len(payload.get("shared_root_nodes") or []),
        "aggregate_root_node_count": len(payload.get("aggregate_root_nodes") or []),
        "validation_error_count": len(draft.validation_errors or []),
        "apply_count": draft.apply_count or 0,
    }


def get_or_create_auto_split_draft(project_id: str, db: Session) -> ProjectStructureDraft:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("项目不存在")

    draft = db.query(ProjectStructureDraft).filter(
        ProjectStructureDraft.project_id == project_id,
        ProjectStructureDraft.draft_type == "auto_split",
    ).first()
    if draft:
        return draft

    draft = ProjectStructureDraft(
        project_id=project_id,
        draft_type="auto_split",
        name="自动拆分内容",
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def reset_draft_runtime_state(draft: ProjectStructureDraft) -> None:
    draft.status = "draft"
    draft.validation_errors = []
    draft.last_validated_at = None
    flag_modified(draft, "validation_errors")


def update_auto_split_draft(
    draft: ProjectStructureDraft,
    *,
    db: Session,
    name: str | None = None,
    source_text: str | None = None,
    split_config: dict[str, Any] | None = None,
    draft_payload: dict[str, Any] | None = None,
) -> ProjectStructureDraft:
    if name is not None:
        draft.name = name.strip() or "自动拆分内容"
    if source_text is not None:
        draft.source_text = source_text
    if split_config is not None:
        draft.split_config = split_config
        flag_modified(draft, "split_config")
    if draft_payload is not None:
        draft.draft_payload = normalize_draft_payload(draft_payload)
        flag_modified(draft, "draft_payload")

    reset_draft_runtime_state(draft)
    db.commit()
    db.refresh(draft)
    return draft


async def split_auto_split_draft(
    draft: ProjectStructureDraft,
    *,
    db: Session,
    source_text: str | None = None,
    split_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actual_source_text = source_text if source_text is not None else draft.source_text
    actual_split_config = split_config if split_config is not None else draft.split_config
    chunks = await split_source_text(actual_source_text or "", actual_split_config or {})

    draft.source_text = actual_source_text or ""
    draft.split_config = actual_split_config or {}
    payload = normalize_draft_payload(draft.draft_payload or {})
    payload["chunks"] = chunks
    payload.setdefault("plans", [])
    payload.setdefault("shared_root_nodes", [])
    payload.setdefault("aggregate_root_nodes", [])
    payload.setdefault("ui_state", {})
    draft.draft_payload = payload
    reset_draft_runtime_state(draft)
    flag_modified(draft, "split_config")
    flag_modified(draft, "draft_payload")
    db.commit()
    db.refresh(draft)
    return {
        "draft": serialize_draft(draft),
        "draft_summary": summarize_draft(draft),
        "chunks": chunks,
    }


def validate_auto_split_draft(
    draft: ProjectStructureDraft,
    *,
    db: Session,
) -> dict[str, Any]:
    project = db.query(Project).filter(Project.id == draft.project_id).first()
    if not project:
        raise ValueError("项目不存在")

    compilation = compile_project_structure_draft(
        draft,
        existing_project_blocks=[block for block in (project.content_blocks or []) if block.deleted_at is None],
    )
    draft.validation_errors = compilation.validation_errors
    draft.last_validated_at = datetime.now()
    draft.status = "validated" if not compilation.validation_errors else "draft"
    flag_modified(draft, "validation_errors")
    db.commit()
    db.refresh(draft)
    return {
        "draft": serialize_draft(draft),
        "summary": compilation.summary,
        "draft_summary": summarize_draft(draft),
        "validation_errors": compilation.validation_errors,
        "preview_root_nodes": compilation.root_nodes,
    }


def apply_auto_split_draft(
    draft: ProjectStructureDraft,
    *,
    db: Session,
    parent_id: str | None = None,
    batch_name: str | None = None,
) -> dict[str, Any]:
    result = apply_project_structure_draft(
        draft=draft,
        db=db,
        parent_id=parent_id,
        batch_name=batch_name,
    )
    db.refresh(draft)
    return {
        **result,
        "draft": serialize_draft(draft),
        "draft_summary": summarize_draft(draft),
    }
