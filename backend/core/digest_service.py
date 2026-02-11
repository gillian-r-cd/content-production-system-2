# backend/core/digest_service.py
"""
内容块摘要服务
在内容块更新后异步生成一句话摘要
构建全量内容块索引注入 system prompt
"""
import asyncio
import logging

from core.llm import llm_mini
from langchain_core.messages import HumanMessage
from core.models.project_field import ProjectField
from core.models.content_block import ContentBlock
from core.database import get_db

logger = logging.getLogger("digest")


async def generate_digest(content: str) -> str:
    """
    用小模型生成一句话摘要

    输入: content - 内容块内容（取前 3000 字）
    输出: 摘要字符串（<=200 字符），内容过短返回 ""
    """
    if not content or len(content.strip()) < 10:
        return ""
    messages = [
        HumanMessage(
            content=f"用一句话概括以下内容的核心主题和要点（不超过50字，只输出摘要本身）：\n\n{content[:3000]}"
        ),
    ]
    try:
        response = await llm_mini.ainvoke(messages)
        return response.content.strip()[:200]
    except Exception as e:
        logger.warning(f"[Digest] 生成摘要失败: {e}")
        return ""


def trigger_digest_update(entity_id: str, entity_type: str, content: str):
    """
    非阻塞地触发摘要更新。在内容块保存后调用。

    输入:
        entity_id   - ProjectField.id 或 ContentBlock.id
        entity_type - "field" | "block"
        content     - 内容块内容
    输出: 无（后台执行）
    """
    async def _do_update():
        try:
            digest = await generate_digest(content)
            if not digest:
                return
            db = next(get_db())
            try:
                if entity_type == "field":
                    entity = db.query(ProjectField).filter_by(id=entity_id).first()
                else:
                    entity = db.query(ContentBlock).filter_by(id=entity_id).first()
                if entity:
                    entity.digest = digest
                    db.commit()
                    logger.info(f"[Digest] {entity_type} {entity_id[:8]}: {digest[:50]}")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[Digest] 更新失败: {e}")

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_do_update())
        else:
            asyncio.run(_do_update())
    except RuntimeError:
        pass


def build_field_index(project_id: str) -> str:
    """
    构建项目的全量内容块摘要索引。

    输入: project_id
    输出: 格式化字符串（每行一个内容块: "- 名称 [状态]: 摘要"），空项目返回 ""
    """
    db = next(get_db())
    try:
        entries = []
        fields = db.query(ProjectField).filter(
            ProjectField.project_id == project_id,
        ).all()
        for f in fields:
            status_label = {
                "pending": "待生成", "generating": "生成中",
                "completed": "已完成", "failed": "失败",
            }.get(f.status, f.status)
            digest = getattr(f, 'digest', None) or (
                "（有内容，摘要生成中）" if f.content else "（空）"
            )
            entries.append(f"- {f.name} [{status_label}]: {digest}")

        blocks = db.query(ContentBlock).filter(
            ContentBlock.project_id == project_id,
            ContentBlock.block_type == "field",
            ContentBlock.deleted_at == None,  # noqa: E711
        ).all()
        for b in blocks:
            status_label = {
                "pending": "待处理", "in_progress": "进行中",
                "completed": "已完成",
            }.get(b.status, b.status)
            digest = getattr(b, 'digest', None) or (
                "（有内容，摘要生成中）" if b.content else "（空）"
            )
            entries.append(f"- {b.name} [{status_label}]: {digest}")

        return "\n".join(entries) if entries else ""
    finally:
        db.close()
