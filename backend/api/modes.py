# backend/api/modes.py
# 功能: Agent 模式管理 API — CRUD 操作 + 列表
# 主要路由: GET /api/modes, POST /api/modes, PUT /api/modes/{id}, DELETE /api/modes/{id}
# 关联: core/models/agent_mode.py, frontend agent-panel.tsx

"""
Agent 模式管理 API

提供模式的增删改查。系统内置模式（is_system=True）不可删除。
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import AgentMode, generate_uuid

router = APIRouter(prefix="/api/modes", tags=["modes"])
logger = logging.getLogger("modes")


# ============== Schemas ==============

class ModeResponse(PydanticBaseModel):
    """模式响应"""
    id: str
    name: str
    display_name: str
    description: str
    system_prompt: str
    icon: str
    is_system: bool
    sort_order: int

    model_config = {"from_attributes": True}


class ModeCreate(PydanticBaseModel):
    """创建模式请求"""
    name: str
    display_name: str
    description: str = ""
    system_prompt: str = ""
    icon: str = "🤖"
    sort_order: int = 99


class ModeUpdate(PydanticBaseModel):
    """更新模式请求"""
    display_name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


# ============== Routes ==============

@router.get("/", response_model=List[ModeResponse])
def list_modes(db: Session = Depends(get_db)):
    """获取所有 Agent 模式，按 sort_order 排序"""
    modes = db.query(AgentMode).order_by(AgentMode.sort_order, AgentMode.created_at).all()
    return modes


@router.get("/{mode_id}", response_model=ModeResponse)
def get_mode(mode_id: str, db: Session = Depends(get_db)):
    """获取单个模式详情"""
    mode = db.query(AgentMode).filter(AgentMode.id == mode_id).first()
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")
    return mode


@router.post("/", response_model=ModeResponse)
def create_mode(data: ModeCreate, db: Session = Depends(get_db)):
    """创建自定义模式"""
    # 检查 name 唯一性
    existing = db.query(AgentMode).filter(AgentMode.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Mode name '{data.name}' already exists")

    mode = AgentMode(
        id=generate_uuid(),
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        system_prompt=data.system_prompt,
        icon=data.icon,
        is_system=False,
        sort_order=data.sort_order,
    )
    db.add(mode)
    db.commit()
    db.refresh(mode)
    logger.info("Created mode: %s (%s)", mode.name, mode.display_name)
    return mode


@router.put("/{mode_id}", response_model=ModeResponse)
def update_mode(mode_id: str, data: ModeUpdate, db: Session = Depends(get_db)):
    """更新模式（系统模式也允许更新 system_prompt 等）"""
    mode = db.query(AgentMode).filter(AgentMode.id == mode_id).first()
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")

    if data.display_name is not None:
        mode.display_name = data.display_name
    if data.description is not None:
        mode.description = data.description
    if data.system_prompt is not None:
        mode.system_prompt = data.system_prompt
    if data.icon is not None:
        mode.icon = data.icon
    if data.sort_order is not None:
        mode.sort_order = data.sort_order

    db.commit()
    db.refresh(mode)
    logger.info("Updated mode: %s", mode.name)
    return mode


@router.delete("/{mode_id}")
def delete_mode(mode_id: str, db: Session = Depends(get_db)):
    """删除自定义模式（系统内置模式不可删除）"""
    mode = db.query(AgentMode).filter(AgentMode.id == mode_id).first()
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")

    if mode.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system mode")

    db.delete(mode)
    db.commit()
    logger.info("Deleted mode: %s", mode.name)
    return {"message": f"Mode '{mode.name}' deleted"}
