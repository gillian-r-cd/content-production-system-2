# backend/api/versions.py
# 功能: 版本历史 API（统一服务于 ContentBlock 和 ProjectField）
# 主要路由: /api/versions/{entity_id} (list), /api/versions/{entity_id}/rollback/{version_id} (rollback)

"""
版本历史 API
支持查看历史版本列表和回滚到指定版本
entity_id 可以是 ContentBlock.id 或 ProjectField.id
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging

from core.database import get_db
from core.models import ContentVersion, ContentBlock, ProjectField, generate_uuid

logger = logging.getLogger("versions")

router = APIRouter(prefix="/api/versions", tags=["versions"])


# ============== Schemas ==============

class VersionItem(BaseModel):
    id: str
    version_number: int
    content: str
    source: str
    source_detail: Optional[str] = None
    created_at: str


class VersionListResponse(BaseModel):
    entity_id: str
    entity_name: str
    entity_type: str  # "block" or "field"
    current_content: str
    versions: List[VersionItem]


class RollbackResponse(BaseModel):
    success: bool
    entity_id: str
    restored_version: int
    message: str


# ============== Endpoints ==============

@router.get("/{entity_id}", response_model=VersionListResponse)
def list_versions(entity_id: str, db: Session = Depends(get_db)):
    """获取实体的所有历史版本"""

    # 查找实体（先查 ContentBlock，再查 ProjectField）
    entity_name = ""
    entity_type = ""
    current_content = ""

    block = db.query(ContentBlock).filter(
        ContentBlock.id == entity_id,
        ContentBlock.deleted_at == None,
    ).first()
    if block:
        entity_name = block.name
        entity_type = "block"
        current_content = block.content or ""
    else:
        field = db.query(ProjectField).filter(
            ProjectField.id == entity_id,
        ).first()
        if field:
            entity_name = field.name
            entity_type = "field"
            current_content = field.content or ""
        else:
            raise HTTPException(status_code=404, detail="Entity not found")

    versions = db.query(ContentVersion).filter(
        ContentVersion.block_id == entity_id,
    ).order_by(ContentVersion.version_number.desc()).all()

    return VersionListResponse(
        entity_id=entity_id,
        entity_name=entity_name,
        entity_type=entity_type,
        current_content=current_content,
        versions=[
            VersionItem(
                id=v.id,
                version_number=v.version_number,
                content=v.content,
                source=v.source,
                source_detail=v.source_detail,
                created_at=v.created_at.isoformat() if v.created_at else "",
            )
            for v in versions
        ],
    )


@router.post("/{entity_id}/rollback/{version_id}", response_model=RollbackResponse)
def rollback_version(entity_id: str, version_id: str, db: Session = Depends(get_db)):
    """回滚到指定版本"""

    # 查找目标版本
    target_version = db.query(ContentVersion).filter(
        ContentVersion.id == version_id,
        ContentVersion.block_id == entity_id,
    ).first()
    if not target_version:
        raise HTTPException(status_code=404, detail="Version not found")

    # 查找实体（ContentBlock 或 ProjectField）
    block = db.query(ContentBlock).filter(
        ContentBlock.id == entity_id,
        ContentBlock.deleted_at == None,
    ).first()
    field = None
    if not block:
        field = db.query(ProjectField).filter(
            ProjectField.id == entity_id,
        ).first()

    if not block and not field:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity = block or field
    old_content = entity.content or ""

    # 保存当前内容为新版本（在回滚前留档）
    if old_content.strip():
        max_ver = db.query(ContentVersion.version_number).filter(
            ContentVersion.block_id == entity_id,
        ).order_by(ContentVersion.version_number.desc()).first()
        next_ver = (max_ver[0] + 1) if max_ver else 1
        snapshot = ContentVersion(
            id=generate_uuid(),
            block_id=entity_id,
            version_number=next_ver,
            content=old_content,
            source="rollback_snapshot",
            source_detail=f"before_rollback_to_v{target_version.version_number}",
        )
        db.add(snapshot)

    # 执行回滚
    entity.content = target_version.content
    if hasattr(entity, 'status'):
        entity.status = "completed"

    db.commit()
    db.refresh(entity)

    entity_name = entity.name if hasattr(entity, 'name') else entity_id
    logger.info(f"[版本] 回滚 {entity_name} 到 v{target_version.version_number}")

    return RollbackResponse(
        success=True,
        entity_id=entity_id,
        restored_version=target_version.version_number,
        message=f"已回滚到版本 v{target_version.version_number}",
    )
