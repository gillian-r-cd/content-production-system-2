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

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.project_structure_draft_service import (
    apply_auto_split_draft as apply_auto_split_draft_service,
    get_or_create_auto_split_draft as get_or_create_auto_split_draft_service,
    serialize_draft,
    split_auto_split_draft as split_auto_split_draft_service,
    update_auto_split_draft as update_auto_split_draft_service,
    validate_auto_split_draft as validate_auto_split_draft_service,
)

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


@router.get("/project/{project_id}/auto-split")
def get_auto_split_draft(
    project_id: str,
    db: Session = Depends(get_db),
):
    try:
        draft = get_or_create_auto_split_draft_service(project_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_draft(draft)


@router.put("/project/{project_id}/auto-split")
def update_auto_split_draft(
    project_id: str,
    request: DraftUpdateRequest,
    db: Session = Depends(get_db),
):
    try:
        draft = get_or_create_auto_split_draft_service(project_id, db)
        updated = update_auto_split_draft_service(
            draft,
            db=db,
            name=request.name,
            source_text=request.source_text,
            split_config=request.split_config,
            draft_payload=request.draft_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_draft(updated)


@router.post("/project/{project_id}/auto-split/split")
async def split_auto_split_draft(
    project_id: str,
    request: DraftSplitRequest,
    db: Session = Depends(get_db),
):
    try:
        draft = get_or_create_auto_split_draft_service(project_id, db)
        return await split_auto_split_draft_service(
            draft,
            db=db,
            source_text=request.source_text,
            split_config=request.split_config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 保留给 LLM / 外部错误
        raise HTTPException(status_code=500, detail=f"拆分失败: {exc}") from exc


@router.post("/project/{project_id}/auto-split/validate")
def validate_auto_split_draft(
    project_id: str,
    db: Session = Depends(get_db),
):
    try:
        draft = get_or_create_auto_split_draft_service(project_id, db)
        return validate_auto_split_draft_service(draft, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/project/{project_id}/auto-split/apply")
def apply_auto_split_draft_route(
    project_id: str,
    request: DraftApplyRequest,
    db: Session = Depends(get_db),
):
    try:
        draft = get_or_create_auto_split_draft_service(project_id, db)
        if draft.project_id != project_id:
            raise HTTPException(status_code=400, detail="草稿与项目不匹配")
        return apply_auto_split_draft_service(
            draft,
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

