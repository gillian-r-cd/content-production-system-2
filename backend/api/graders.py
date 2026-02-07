# backend/api/graders.py
# 功能: Grader（评分器）CRUD API
# 主要端点:
#   GET  /api/graders               - 列出所有评分器（预置 + 项目专用）
#   GET  /api/graders/{id}          - 获取单个评分器
#   POST /api/graders               - 创建评分器
#   PUT  /api/graders/{id}          - 更新评分器
#   DELETE /api/graders/{id}        - 删除评分器（不可删预置）
#   GET  /api/graders/project/{pid} - 获取某项目可用的评分器（预置 + 该项目专用）
#   GET  /api/graders/types         - 获取评分器类型定义

"""
Grader API - 评分器管理
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel as PydanticBase
from sqlalchemy.orm import Session

from core.database import get_db
from core.models.grader import Grader, GRADER_TYPE_CHOICES, PRESET_GRADERS
from core.models.base import generate_uuid


router = APIRouter(prefix="/api/graders", tags=["graders"])


# ============== Schemas ==============

class GraderCreate(PydanticBase):
    name: str
    grader_type: str = "content_only"
    prompt_template: str = ""
    dimensions: list = []
    scoring_criteria: dict = {}
    project_id: Optional[str] = None


class GraderUpdate(PydanticBase):
    name: Optional[str] = None
    grader_type: Optional[str] = None
    prompt_template: Optional[str] = None
    dimensions: Optional[list] = None
    scoring_criteria: Optional[dict] = None


class GraderResponse(PydanticBase):
    id: str
    name: str
    grader_type: str
    prompt_template: str
    dimensions: list
    scoring_criteria: dict
    is_preset: bool
    project_id: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


def _grader_to_response(g: Grader) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "grader_type": g.grader_type,
        "prompt_template": g.prompt_template or "",
        "dimensions": g.dimensions or [],
        "scoring_criteria": g.scoring_criteria or {},
        "is_preset": g.is_preset,
        "project_id": g.project_id,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }


# ============== Endpoints ==============

@router.get("/types")
def get_grader_types():
    """获取评分器类型定义"""
    return GRADER_TYPE_CHOICES


@router.get("", response_model=List[GraderResponse])
def list_graders(db: Session = Depends(get_db)):
    """列出所有评分器（预置 + 全部项目自定义）"""
    graders = db.query(Grader).order_by(Grader.is_preset.desc(), Grader.created_at).all()
    return [_grader_to_response(g) for g in graders]


@router.get("/project/{project_id}", response_model=List[GraderResponse])
def list_project_graders(project_id: str, db: Session = Depends(get_db)):
    """获取某项目可用的评分器（预置 + 该项目专用）"""
    graders = db.query(Grader).filter(
        (Grader.is_preset == True) | (Grader.project_id == project_id)
    ).order_by(Grader.is_preset.desc(), Grader.created_at).all()
    return [_grader_to_response(g) for g in graders]


@router.get("/{grader_id}", response_model=GraderResponse)
def get_grader(grader_id: str, db: Session = Depends(get_db)):
    """获取单个评分器"""
    g = db.query(Grader).filter(Grader.id == grader_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Grader not found")
    return _grader_to_response(g)


@router.post("", response_model=GraderResponse)
def create_grader(data: GraderCreate, db: Session = Depends(get_db)):
    """创建评分器"""
    g = Grader(
        id=generate_uuid(),
        name=data.name,
        grader_type=data.grader_type,
        prompt_template=data.prompt_template,
        dimensions=data.dimensions,
        scoring_criteria=data.scoring_criteria,
        is_preset=False,
        project_id=data.project_id,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return _grader_to_response(g)


@router.put("/{grader_id}", response_model=GraderResponse)
def update_grader(grader_id: str, data: GraderUpdate, db: Session = Depends(get_db)):
    """更新评分器"""
    g = db.query(Grader).filter(Grader.id == grader_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Grader not found")
    
    if data.name is not None:
        g.name = data.name
    if data.grader_type is not None:
        g.grader_type = data.grader_type
    if data.prompt_template is not None:
        g.prompt_template = data.prompt_template
    if data.dimensions is not None:
        g.dimensions = data.dimensions
    if data.scoring_criteria is not None:
        g.scoring_criteria = data.scoring_criteria
    
    g.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(g)
    return _grader_to_response(g)


@router.delete("/{grader_id}")
def delete_grader(grader_id: str, db: Session = Depends(get_db)):
    """删除评分器（预置评分器不可删除）"""
    g = db.query(Grader).filter(Grader.id == grader_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Grader not found")
    if g.is_preset:
        raise HTTPException(status_code=403, detail="不可删除预置评分器")
    
    db.delete(g)
    db.commit()
    return {"ok": True, "deleted": grader_id}


