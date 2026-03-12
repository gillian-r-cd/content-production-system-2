# backend/api/modes.py
# 功能: Agent 角色管理 API — 项目级角色 CRUD + 系统模板导入
# 主要路由: GET /api/modes, GET /api/modes/templates, POST /api/modes/import-templates, POST/PUT/DELETE /api/modes
# 关联: core/models/agent_mode.py, frontend agent-panel.tsx

"""
Agent 角色管理 API

右侧 Agent 运行时只消费项目级角色实例。
系统内置的 5 个角色仅作为模板存在，不直接出现在项目运行区。
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from core.database import get_db
from core.localization import DEFAULT_LOCALE, normalize_locale
from core.models import AgentMode, generate_uuid

router = APIRouter(prefix="/api/modes", tags=["modes"])
logger = logging.getLogger("modes")


def _stable_key(value: Optional[str], fallback: str) -> str:
    resolved = (value or "").strip()
    return resolved or fallback.strip()


# ============== Schemas ==============

class ModeResponse(PydanticBaseModel):
    """角色响应"""
    id: str
    name: str
    stable_key: str
    locale: str
    project_id: Optional[str] = None
    display_name: str
    description: str
    system_prompt: str
    icon: str
    is_system: bool
    is_template: bool
    sort_order: int

    model_config = {"from_attributes": True}


class ModeCreate(PydanticBaseModel):
    """创建项目角色请求"""
    project_id: str
    display_name: str
    stable_key: str = ""
    locale: str = DEFAULT_LOCALE
    description: str = ""
    system_prompt: str
    icon: str = "🤖"
    sort_order: Optional[int] = None


class ModeUpdate(PydanticBaseModel):
    """更新项目角色请求"""
    display_name: Optional[str] = None
    stable_key: Optional[str] = None
    locale: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class ImportTemplatesRequest(PydanticBaseModel):
    """导入模板到项目角色列表"""
    project_id: str
    template_ids: List[str] = []


class ImportTemplatesResponse(PydanticBaseModel):
    """模板导入结果"""
    imported: List[ModeResponse]
    skipped_count: int = 0


def _sanitize_text(value: str) -> str:
    return (value or "").strip()


def _next_sort_order(db: Session, project_id: str) -> int:
    current_max = db.query(func.max(AgentMode.sort_order)).filter(
        AgentMode.project_id == project_id,
        AgentMode.is_template.is_(False),
    ).scalar()
    return int(current_max or -1) + 1


def _generate_internal_name() -> str:
    return f"mode_{generate_uuid().replace('-', '')[:12]}"


def _normalize_legacy_system_templates(db: Session) -> None:
    """将旧库里的系统角色回填为模板，收敛到单一模板语义。"""
    legacy_rows = db.query(AgentMode).filter(
        AgentMode.project_id.is_(None),
        AgentMode.is_system.is_(True),
        AgentMode.is_template.is_(False),
    ).all()
    if not legacy_rows:
        return

    for row in legacy_rows:
        row.is_template = True
        row.locale = normalize_locale(getattr(row, "locale", DEFAULT_LOCALE))
        row.stable_key = getattr(row, "stable_key", "") or row.name
    db.commit()
    logger.warning("Backfilled %s legacy system roles as templates", len(legacy_rows))


def _system_templates_query(db: Session):
    _normalize_legacy_system_templates(db)
    return db.query(AgentMode).filter(
        AgentMode.project_id.is_(None),
        AgentMode.is_template.is_(True),
    )


def _get_project_mode_or_404(db: Session, mode_id: str) -> AgentMode:
    mode = db.query(AgentMode).filter(
        AgentMode.id == mode_id,
        AgentMode.project_id.is_not(None),
        AgentMode.is_template.is_(False),
    ).first()
    if not mode:
        raise HTTPException(status_code=404, detail="Project mode not found")
    return mode


# ============== Routes ==============

@router.get("/", response_model=List[ModeResponse])
def list_modes(project_id: Optional[str] = None, db: Session = Depends(get_db)):
    """获取角色列表。传 project_id 时返回项目角色；否则返回系统模板。"""
    if project_id:
        query = db.query(AgentMode).filter(
            AgentMode.project_id == project_id,
            AgentMode.is_template.is_(False),
        )
    else:
        query = _system_templates_query(db)
    return query.order_by(AgentMode.sort_order, AgentMode.created_at).all()


@router.get("/templates", response_model=List[ModeResponse])
def list_mode_templates(db: Session = Depends(get_db)):
    """获取系统角色模板。"""
    templates = _system_templates_query(db).order_by(AgentMode.sort_order, AgentMode.created_at).all()
    return templates


@router.get("/{mode_id}", response_model=ModeResponse)
def get_mode(mode_id: str, db: Session = Depends(get_db)):
    """获取单个角色详情。"""
    mode = db.query(AgentMode).filter(AgentMode.id == mode_id).first()
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")
    return mode


@router.post("/", response_model=ModeResponse)
def create_mode(data: ModeCreate, db: Session = Depends(get_db)):
    """创建项目角色。"""
    display_name = _sanitize_text(data.display_name)
    system_prompt = _sanitize_text(data.system_prompt)
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name 不能为空")
    if not system_prompt:
        raise HTTPException(status_code=400, detail="system_prompt 不能为空")

    mode = AgentMode(
        id=generate_uuid(),
        project_id=data.project_id,
        name=_generate_internal_name(),
        stable_key=_stable_key(data.stable_key, display_name),
        locale=normalize_locale(data.locale),
        display_name=display_name,
        description=_sanitize_text(data.description),
        system_prompt=system_prompt,
        icon=_sanitize_text(data.icon) or "🤖",
        is_system=False,
        is_template=False,
        sort_order=data.sort_order if data.sort_order is not None else _next_sort_order(db, data.project_id),
    )
    db.add(mode)
    db.commit()
    db.refresh(mode)
    logger.info("Created project mode: %s (%s)", mode.id, mode.display_name)
    return mode


@router.post("/import-templates", response_model=ImportTemplatesResponse)
def import_templates(data: ImportTemplatesRequest, db: Session = Depends(get_db)):
    """将系统模板复制为当前项目的角色实例。"""
    templates_query = _system_templates_query(db)
    if data.template_ids:
        templates_query = templates_query.filter(AgentMode.id.in_(data.template_ids))
    templates = templates_query.order_by(AgentMode.sort_order, AgentMode.created_at).all()
    if not templates:
        raise HTTPException(status_code=404, detail="No templates found")

    existing_keys = {
        (
            getattr(row, "stable_key", "") or row.display_name,
            normalize_locale(getattr(row, "locale", DEFAULT_LOCALE)),
        )
        for row in db.query(AgentMode).filter(
            AgentMode.project_id == data.project_id,
            AgentMode.is_template.is_(False),
        ).all()
    }
    next_sort = _next_sort_order(db, data.project_id)
    imported: list[AgentMode] = []
    skipped = 0
    for template in templates:
        template_key = (
            getattr(template, "stable_key", "") or template.display_name,
            normalize_locale(getattr(template, "locale", DEFAULT_LOCALE)),
        )
        if template_key in existing_keys:
            skipped += 1
            continue
        cloned = AgentMode(
            id=generate_uuid(),
            project_id=data.project_id,
            name=_generate_internal_name(),
            stable_key=getattr(template, "stable_key", "") or template.name,
            locale=normalize_locale(getattr(template, "locale", DEFAULT_LOCALE)),
            display_name=template.display_name,
            description=template.description,
            system_prompt=template.system_prompt,
            icon=template.icon,
            is_system=False,
            is_template=False,
            sort_order=next_sort,
        )
        next_sort += 1
        imported.append(cloned)
        existing_keys.add(template_key)
        db.add(cloned)

    db.commit()
    for row in imported:
        db.refresh(row)

    return ImportTemplatesResponse(imported=imported, skipped_count=skipped)


@router.put("/{mode_id}", response_model=ModeResponse)
def update_mode(mode_id: str, data: ModeUpdate, db: Session = Depends(get_db)):
    """更新项目角色。"""
    mode = _get_project_mode_or_404(db, mode_id)

    if data.display_name is not None:
        display_name = _sanitize_text(data.display_name)
        if not display_name:
            raise HTTPException(status_code=400, detail="display_name 不能为空")
        mode.display_name = display_name
    if data.stable_key is not None:
        mode.stable_key = _stable_key(data.stable_key, data.display_name or mode.display_name)
    if data.locale is not None:
        mode.locale = normalize_locale(data.locale)
    if data.description is not None:
        mode.description = _sanitize_text(data.description)
    if data.system_prompt is not None:
        system_prompt = _sanitize_text(data.system_prompt)
        if not system_prompt:
            raise HTTPException(status_code=400, detail="system_prompt 不能为空")
        mode.system_prompt = system_prompt
    if data.icon is not None:
        mode.icon = _sanitize_text(data.icon) or "🤖"
    if data.sort_order is not None:
        mode.sort_order = data.sort_order

    db.commit()
    db.refresh(mode)
    logger.info("Updated project mode: %s", mode.id)
    return mode


@router.delete("/{mode_id}")
def delete_mode(mode_id: str, db: Session = Depends(get_db)):
    """删除项目角色。模板不可通过此接口删除。"""
    mode = _get_project_mode_or_404(db, mode_id)
    db.delete(mode)
    db.commit()
    logger.info("Deleted project mode: %s", mode.id)
    return {"message": f"Mode '{mode.display_name}' deleted"}
