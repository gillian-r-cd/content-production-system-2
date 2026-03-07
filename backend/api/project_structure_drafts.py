# backend/api/project_structure_drafts.py
# 功能: 项目级结构草稿 API，提供自动拆分草稿的读取、保存、拆分、校验和应用入口
# 主要路由: /api/project-structure-drafts/project/{project_id}/auto-split/*
# 数据结构: ProjectStructureDraft + split_config + draft_payload

"""
项目级结构草稿 API

第一阶段先固定一类草稿：`draft_type=auto_split`
这样前端、后端、后续 Agent 都围绕同一份正式草稿工作。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.database import get_db
from core.models import Project, ProjectStructureDraft
from core.project_split_service import split_source_text
from core.project_structure_apply_service import apply_project_structure_draft
from core.project_structure_compiler import compile_project_structure_draft
from core.pre_question_utils import normalize_pre_questions

router = APIRouter(
    prefix="/api/project-structure-drafts",
    tags=["project-structure-drafts"],
)


class DraftUpdateRequest(BaseModel):
    name: Optional[str] = None
    source_text: Optional[str] = None
    split_config: Optional[dict[str, Any]] = None
    draft_payload: Optional[dict[str, Any]] = None


class DraftSplitRequest(BaseModel):
    source_text: Optional[str] = None
    split_config: Optional[dict[str, Any]] = None


class DraftApplyRequest(BaseModel):
    parent_id: Optional[str] = None
    batch_name: Optional[str] = None


def _normalize_node_types(nodes: list[Any]) -> list[dict[str, Any]]:
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
        node["children"] = _normalize_node_types(node.get("children") if isinstance(node.get("children"), list) else [])
        normalized.append(node)
    return normalized


def _normalize_draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "chunks": data.get("chunks") if isinstance(data.get("chunks"), list) else [],
        "plans": [
            {
                **(plan if isinstance(plan, dict) else {}),
                "root_nodes": _normalize_node_types(
                    (plan or {}).get("root_nodes") if isinstance((plan or {}).get("root_nodes"), list) else []
                ),
            }
            for plan in (data.get("plans") if isinstance(data.get("plans"), list) else [])
            if isinstance(plan, dict)
        ],
        "shared_root_nodes": _normalize_node_types(
            data.get("shared_root_nodes") if isinstance(data.get("shared_root_nodes"), list) else []
        ),
        "aggregate_root_nodes": _normalize_node_types(
            data.get("aggregate_root_nodes") if isinstance(data.get("aggregate_root_nodes"), list) else []
        ),
        "ui_state": data.get("ui_state") if isinstance(data.get("ui_state"), dict) else {},
    }


def _serialize_draft(draft: ProjectStructureDraft) -> dict[str, Any]:
    return {
        "id": draft.id,
        "project_id": draft.project_id,
        "draft_type": draft.draft_type,
        "name": draft.name,
        "status": draft.status,
        "source_text": draft.source_text or "",
        "split_config": draft.split_config or {},
        "draft_payload": _normalize_draft_payload(draft.draft_payload or {}),
        "validation_errors": draft.validation_errors or [],
        "last_validated_at": draft.last_validated_at.isoformat() if draft.last_validated_at else None,
        "apply_count": draft.apply_count or 0,
        "last_applied_at": draft.last_applied_at.isoformat() if draft.last_applied_at else None,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }


def _get_or_create_auto_split_draft(project_id: str, db: Session) -> ProjectStructureDraft:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

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


@router.get("/project/{project_id}/auto-split")
def get_auto_split_draft(
    project_id: str,
    db: Session = Depends(get_db),
):
    draft = _get_or_create_auto_split_draft(project_id, db)
    return _serialize_draft(draft)


@router.put("/project/{project_id}/auto-split")
def update_auto_split_draft(
    project_id: str,
    request: DraftUpdateRequest,
    db: Session = Depends(get_db),
):
    draft = _get_or_create_auto_split_draft(project_id, db)

    if request.name is not None:
        draft.name = request.name.strip() or "自动拆分内容"
    if request.source_text is not None:
        draft.source_text = request.source_text
    if request.split_config is not None:
        draft.split_config = request.split_config
        flag_modified(draft, "split_config")
    if request.draft_payload is not None:
        draft.draft_payload = _normalize_draft_payload(request.draft_payload)
        flag_modified(draft, "draft_payload")

    draft.status = "draft"
    draft.validation_errors = []
    draft.last_validated_at = None
    flag_modified(draft, "validation_errors")
    db.commit()
    db.refresh(draft)
    return _serialize_draft(draft)


@router.post("/project/{project_id}/auto-split/split")
async def split_auto_split_draft(
    project_id: str,
    request: DraftSplitRequest,
    db: Session = Depends(get_db),
):
    draft = _get_or_create_auto_split_draft(project_id, db)
    source_text = request.source_text if request.source_text is not None else draft.source_text
    split_config = request.split_config if request.split_config is not None else draft.split_config

    try:
        chunks = await split_source_text(source_text or "", split_config or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 保留给 LLM / 外部错误
        raise HTTPException(status_code=500, detail=f"拆分失败: {exc}") from exc

    draft.source_text = source_text or ""
    draft.split_config = split_config or {}
    payload = _normalize_draft_payload(draft.draft_payload or {})
    payload["chunks"] = chunks
    payload.setdefault("plans", [])
    payload.setdefault("shared_root_nodes", [])
    payload.setdefault("aggregate_root_nodes", [])
    payload.setdefault("ui_state", {})
    draft.draft_payload = payload
    draft.validation_errors = []
    draft.last_validated_at = None
    draft.status = "draft"
    flag_modified(draft, "split_config")
    flag_modified(draft, "draft_payload")
    flag_modified(draft, "validation_errors")
    db.commit()
    db.refresh(draft)
    return {
        "draft": _serialize_draft(draft),
        "chunks": chunks,
    }


@router.post("/project/{project_id}/auto-split/validate")
def validate_auto_split_draft(
    project_id: str,
    db: Session = Depends(get_db),
):
    draft = _get_or_create_auto_split_draft(project_id, db)
    existing_blocks = db.query(Project).filter(Project.id == project_id).first()
    if not existing_blocks:
        raise HTTPException(status_code=404, detail="项目不存在")

    content_blocks = existing_blocks.content_blocks or []
    compilation = compile_project_structure_draft(
        draft,
        existing_project_blocks=[block for block in content_blocks if block.deleted_at is None],
    )
    draft.validation_errors = compilation.validation_errors
    draft.last_validated_at = datetime.now()
    draft.status = "validated" if not compilation.validation_errors else "draft"
    flag_modified(draft, "validation_errors")
    db.commit()
    db.refresh(draft)
    return {
        "draft": _serialize_draft(draft),
        "validation_errors": compilation.validation_errors,
        "summary": compilation.summary,
        "preview_root_nodes": compilation.root_nodes,
    }


@router.post("/project/{project_id}/auto-split/apply")
def apply_auto_split_draft_route(
    project_id: str,
    request: DraftApplyRequest,
    db: Session = Depends(get_db),
):
    draft = _get_or_create_auto_split_draft(project_id, db)
    if draft.project_id != project_id:
        raise HTTPException(status_code=400, detail="草稿与项目不匹配")
    try:
        result = apply_project_structure_draft(
            draft=draft,
            db=db,
            parent_id=request.parent_id,
            batch_name=request.batch_name,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"应用草稿失败: {exc}") from exc

    db.refresh(draft)
    return {
        **result,
        "draft": _serialize_draft(draft),
    }
