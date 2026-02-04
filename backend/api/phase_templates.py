# backend/api/phase_templates.py
# 功能: 阶段模板 API，管理流程模板
# 主要路由: /api/phase-templates
# 数据结构: PhaseTemplate 的 CRUD

"""
阶段模板 API
管理预设的流程模板，支持用户选择或创建自定义模板
"""

from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import PhaseTemplate, generate_uuid


router = APIRouter(prefix="/api/phase-templates", tags=["phase-templates"])


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
    description: str = ""
    phases: List[PhaseDefinition]


class TemplateUpdate(BaseModel):
    """更新模板请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    phases: Optional[List[PhaseDefinition]] = None


class TemplateResponse(BaseModel):
    """模板响应"""
    id: str
    name: str
    description: str
    phases: List[Dict]
    is_default: bool
    is_system: bool
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


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
    
    return [
        TemplateResponse(
            id=t.id,
            name=t.name,
            description=t.description or "",
            phases=t.phases or [],
            is_default=t.is_default,
            is_system=t.is_system,
            created_at=t.created_at.isoformat() if t.created_at else None,
            updated_at=t.updated_at.isoformat() if t.updated_at else None,
        )
        for t in templates
    ]


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: str,
    db: Session = Depends(get_db),
):
    """获取单个模板"""
    template = db.query(PhaseTemplate).filter(PhaseTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description or "",
        phases=template.phases or [],
        is_default=template.is_default,
        is_system=template.is_system,
        created_at=template.created_at.isoformat() if template.created_at else None,
        updated_at=template.updated_at.isoformat() if template.updated_at else None,
    )


@router.post("/", response_model=TemplateResponse)
def create_template(
    data: TemplateCreate,
    db: Session = Depends(get_db),
):
    """创建模板"""
    template = PhaseTemplate(
        id=generate_uuid(),
        name=data.name,
        description=data.description,
        phases=[p.dict() for p in data.phases],
        is_default=False,
        is_system=False,
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description or "",
        phases=template.phases or [],
        is_default=template.is_default,
        is_system=template.is_system,
        created_at=template.created_at.isoformat() if template.created_at else None,
        updated_at=template.updated_at.isoformat() if template.updated_at else None,
    )


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
    if data.description is not None:
        template.description = data.description
    if data.phases is not None:
        template.phases = [p.dict() for p in data.phases]
    
    db.commit()
    db.refresh(template)
    
    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description or "",
        phases=template.phases or [],
        is_default=template.is_default,
        is_system=template.is_system,
        created_at=template.created_at.isoformat() if template.created_at else None,
        updated_at=template.updated_at.isoformat() if template.updated_at else None,
    )


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
    
    new_template = PhaseTemplate(
        id=generate_uuid(),
        name=new_name or f"{template.name} (副本)",
        description=template.description,
        phases=template.phases.copy() if template.phases else [],
        is_default=False,
        is_system=False,
    )
    
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    
    return TemplateResponse(
        id=new_template.id,
        name=new_template.name,
        description=new_template.description or "",
        phases=new_template.phases or [],
        is_default=new_template.is_default,
        is_system=new_template.is_system,
        created_at=new_template.created_at.isoformat() if new_template.created_at else None,
        updated_at=new_template.updated_at.isoformat() if new_template.updated_at else None,
    )
