# backend/api/phase_templates.py
# 功能: 阶段模板 API，管理流程模板
# 主要路由: /api/phase-templates
# 数据结构: PhaseTemplate 的 CRUD

"""
阶段模板 API
管理预设的流程模板，支持用户选择或创建自定义模板
"""

import json
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
from core.localization import DEFAULT_LOCALE, normalize_locale
from core.locale_text import rt
from core.models import PhaseTemplate, generate_uuid
from core.template_schema import (
    TEMPLATE_SCHEMA_VERSION,
    phase_template_to_root_nodes,
    root_nodes_to_phase_template_phases,
)


router = APIRouter(prefix="/api/phase-templates", tags=["phase-templates"])


def _stable_key(value: Optional[str], fallback: str) -> str:
    resolved = (value or "").strip()
    return resolved or fallback.strip()


def _to_template_response(template: PhaseTemplate) -> "TemplateResponse":
    return TemplateResponse(
        id=template.id,
        name=template.name,
        stable_key=getattr(template, "stable_key", "") or template.name,
        locale=normalize_locale(getattr(template, "locale", DEFAULT_LOCALE)),
        description=template.description or "",
        schema_version=TEMPLATE_SCHEMA_VERSION,
        phases=template.phases or [],
        root_nodes=phase_template_to_root_nodes(template.phases or [])[0],
        is_default=template.is_default,
        is_system=template.is_system,
        created_at=template.created_at.isoformat() if template.created_at else None,
        updated_at=template.updated_at.isoformat() if template.updated_at else None,
    )


# ========== Pydantic 模型 ==========

class PhaseDefinition(BaseModel):
    """阶段定义"""
    name: str
    block_type: str = "phase"
    special_handler: Optional[str] = None
    order_index: int
    default_fields: List[Dict] = Field(default_factory=list)


class TemplateCreate(BaseModel):
    """创建模板请求"""
    name: str
    stable_key: str = ""
    locale: str = DEFAULT_LOCALE
    description: str = ""
    phases: List[PhaseDefinition] = Field(default_factory=list)
    root_nodes: List[Dict] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    """更新模板请求"""
    name: Optional[str] = None
    stable_key: Optional[str] = None
    locale: Optional[str] = None
    description: Optional[str] = None
    phases: Optional[List[PhaseDefinition]] = None
    root_nodes: Optional[List[Dict]] = None


class TemplateResponse(BaseModel):
    """模板响应"""
    id: str
    name: str
    stable_key: str
    locale: str
    description: str
    schema_version: int
    phases: List[Dict]
    root_nodes: List[Dict]
    is_default: bool
    is_system: bool
    created_at: Optional[str]
    updated_at: Optional[str]

    model_config = {"from_attributes": True}


# ========== API 路由 ==========

@router.get("/", response_model=List[TemplateResponse])
def list_templates(
    db: Session = Depends(get_db),
):
    """获取所有模板"""
    templates = db.query(PhaseTemplate).order_by(
        PhaseTemplate.is_default.desc(),
        PhaseTemplate.created_at,
    ).all()
    
    return [_to_template_response(t) for t in templates]


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: str,
    db: Session = Depends(get_db),
):
    """获取单个模板"""
    template = db.query(PhaseTemplate).filter(PhaseTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    return _to_template_response(template)


@router.post("/", response_model=TemplateResponse)
def create_template(
    data: TemplateCreate,
    db: Session = Depends(get_db),
):
    """创建模板"""
    template = PhaseTemplate(
        id=generate_uuid(),
        name=data.name,
        stable_key=_stable_key(data.stable_key, data.name),
        locale=normalize_locale(data.locale),
        description=data.description,
        phases=(
            root_nodes_to_phase_template_phases(data.root_nodes)
            if data.root_nodes
            else [p.model_dump() for p in data.phases]
        ),
        is_default=False,
        is_system=False,
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)

    return _to_template_response(template)


@router.put("/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: str,
    data: TemplateUpdate,
    db: Session = Depends(get_db),
):
    """更新模板"""
    template = db.query(PhaseTemplate).filter(PhaseTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    if template.is_system:
        raise HTTPException(status_code=400, detail="系统模板不可修改")
    
    if data.name is not None:
        template.name = data.name
    if data.locale is not None:
        template.locale = normalize_locale(data.locale)
    if data.stable_key is not None:
        template.stable_key = _stable_key(data.stable_key, data.name or template.name)
    if data.description is not None:
        template.description = data.description
    if data.root_nodes is not None:
        template.phases = root_nodes_to_phase_template_phases(data.root_nodes)
    elif data.phases is not None:
        template.phases = [p.model_dump() for p in data.phases]
    
    db.commit()
    db.refresh(template)

    return _to_template_response(template)


@router.delete("/{template_id}")
def delete_template(
    template_id: str,
    db: Session = Depends(get_db),
):
    """删除模板"""
    template = db.query(PhaseTemplate).filter(PhaseTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    if template.is_system:
        raise HTTPException(status_code=400, detail="系统模板不可删除")
    
    db.delete(template)
    db.commit()
    
    return {"message": "删除成功"}


@router.post("/{template_id}/duplicate", response_model=TemplateResponse)
def duplicate_template(
    template_id: str,
    new_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """复制模板"""
    template = db.query(PhaseTemplate).filter(PhaseTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    duplicate_locale = normalize_locale(getattr(template, "locale", DEFAULT_LOCALE))
    duplicate_name = (new_name or "").strip() or rt(duplicate_locale, "phase_template.duplicate.name", name=template.name)
    new_template = PhaseTemplate(
        id=generate_uuid(),
        name=duplicate_name,
        stable_key=_stable_key("", duplicate_name),
        locale=duplicate_locale,
        description=template.description,
        phases=json.loads(json.dumps(template.phases or [])),
        is_default=False,
        is_system=False,
    )
    
    db.add(new_template)
    db.commit()
    db.refresh(new_template)

    return _to_template_response(new_template)
