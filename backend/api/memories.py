# backend/api/memories.py
# 功能: 项目记忆 CRUD API — 查看、编辑、删除、手动添加记忆
# 主要路由: GET/POST/PUT/DELETE /api/memories/{project_id}
# 关联: core/models/memory_item.py, core/memory_service.py, frontend memory-panel.tsx

"""
项目记忆管理 API

提供记忆的增删改查。每条记忆属于一个项目，是从 Agent 对话中提炼的可复用知识。
用户可以查看 Agent 记住了什么、手动修正错误记忆、添加额外记忆。
"""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import MemoryItem, generate_uuid

router = APIRouter(prefix="/api/memories", tags=["memories"])
logger = logging.getLogger("memories")


# ============== Schemas ==============

class MemoryResponse(PydanticBaseModel):
    """记忆响应"""
    id: str
    project_id: Optional[str]
    content: str
    source_mode: str
    source_phase: str
    related_blocks: list
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemoryCreate(PydanticBaseModel):
    """手动添加记忆"""
    content: str
    source_mode: str = "manual"
    source_phase: str = ""
    related_blocks: list = []


class MemoryUpdate(PydanticBaseModel):
    """更新记忆"""
    content: Optional[str] = None
    related_blocks: Optional[list] = None


# ============== Routes ==============

@router.get("/{project_id}", response_model=List[MemoryResponse])
def list_memories(project_id: str, include_global: bool = False, db: Session = Depends(get_db)):
    """获取项目的全部记忆，按创建时间排序。
    
    Args:
        project_id: 项目 ID，传 "_global" 可仅查看全局记忆
        include_global: 是否同时包含全局记忆
    """
    if project_id == "_global":
        memories = db.query(MemoryItem).filter(
            MemoryItem.project_id.is_(None),
        ).order_by(MemoryItem.created_at).all()
    elif include_global:
        from sqlalchemy import or_
        memories = db.query(MemoryItem).filter(
            or_(
                MemoryItem.project_id == project_id,
                MemoryItem.project_id.is_(None),
            )
        ).order_by(MemoryItem.created_at).all()
    else:
        memories = db.query(MemoryItem).filter(
            MemoryItem.project_id == project_id,
        ).order_by(MemoryItem.created_at).all()
    return memories


@router.get("/{project_id}/{memory_id}", response_model=MemoryResponse)
def get_memory(project_id: str, memory_id: str, db: Session = Depends(get_db)):
    """获取单条记忆详情"""
    mem = db.query(MemoryItem).filter(
        MemoryItem.id == memory_id,
        MemoryItem.project_id == project_id,
    ).first()
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    return mem


@router.post("/{project_id}", response_model=MemoryResponse)
def create_memory(project_id: str, data: MemoryCreate, db: Session = Depends(get_db)):
    """手动添加一条记忆。project_id 传 "_global" 创建全局记忆。"""
    content = data.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    actual_project_id = None if project_id == "_global" else project_id

    mem = MemoryItem(
        id=generate_uuid(),
        project_id=actual_project_id,
        content=content,
        source_mode=data.source_mode,
        source_phase=data.source_phase,
        related_blocks=data.related_blocks,
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    logger.info("Created memory for project %s: %s", project_id, content[:60])
    return mem


@router.put("/{project_id}/{memory_id}", response_model=MemoryResponse)
def update_memory(
    project_id: str,
    memory_id: str,
    data: MemoryUpdate,
    db: Session = Depends(get_db),
):
    """更新记忆内容"""
    mem = db.query(MemoryItem).filter(
        MemoryItem.id == memory_id,
        MemoryItem.project_id == project_id,
    ).first()
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")

    if data.content is not None:
        content = data.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="Content cannot be empty")
        mem.content = content
    if data.related_blocks is not None:
        mem.related_blocks = data.related_blocks

    db.commit()
    db.refresh(mem)
    logger.info("Updated memory %s: %s", memory_id, mem.content[:60])
    return mem


@router.delete("/{project_id}/{memory_id}")
def delete_memory(project_id: str, memory_id: str, db: Session = Depends(get_db)):
    """删除一条记忆"""
    mem = db.query(MemoryItem).filter(
        MemoryItem.id == memory_id,
        MemoryItem.project_id == project_id,
    ).first()
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")

    db.delete(mem)
    db.commit()
    logger.info("Deleted memory %s from project %s", memory_id, project_id)
    return {"message": "Memory deleted"}

