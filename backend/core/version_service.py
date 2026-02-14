# backend/core/version_service.py
# 功能: 内容版本保存的唯一入口
# 主要函数: save_content_version()
# 数据结构: 无（操作 ContentVersion 模型）
#
# 设计原则: 覆写内容前先调用此函数保存旧版本，全系统只此一处实现

"""
内容版本保存服务。

在 agent_tools、api/agent、api/blocks 三处曾各自实现，现统一到此。
"""

import logging
from sqlalchemy.orm import Session

logger = logging.getLogger("version_service")


def save_content_version(
    db: Session,
    entity_id: str,
    old_content: str,
    source: str,
    source_detail: str = None,
) -> None:
    """
    保存旧内容为 ContentVersion（覆写前调用）。

    Args:
        db: 数据库会话（调用者控制 commit）
        entity_id: ContentBlock.id
        old_content: 被覆写的旧内容
        source: 版本来源（manual / ai_generate / ai_regenerate / agent）
        source_detail: 来源补充说明（如具体的修改指令）
    """
    if not old_content or not old_content.strip():
        return  # 空内容不值得保存版本

    try:
        from core.models import ContentVersion, generate_uuid

        max_ver = db.query(ContentVersion.version_number).filter(
            ContentVersion.block_id == entity_id
        ).order_by(ContentVersion.version_number.desc()).first()

        next_ver = (max_ver[0] + 1) if max_ver else 1

        ver = ContentVersion(
            id=generate_uuid(),
            block_id=entity_id,
            version_number=next_ver,
            content=old_content,
            source=source,
            source_detail=source_detail,
        )
        db.add(ver)
        db.flush()  # 立即写入以获得 ID，但不 commit（让调用者控制事务）
        logger.info(f"[版本] 保存 {entity_id[:8]}... v{next_ver} ({source})")
    except Exception as e:
        logger.warning(f"[版本] 保存失败(可忽略): {e}")

