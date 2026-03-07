# backend/core/content_block_reference.py
# 功能: ContentBlock 稳定引用与名称消歧辅助
# 主要函数: find_block_by_identifier(), build_block_reference_lookup(), build_block_path()
# 数据结构: 统一处理 id: 引用、重名名称报错、路径展示

from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from core.models.content_block import ContentBlock


class DuplicateBlockReferenceError(ValueError):
    """按名称引用内容块时命中多个候选。"""


def list_active_project_blocks(db: Session, project_id: str) -> list[ContentBlock]:
    return db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).order_by(ContentBlock.depth.asc(), ContentBlock.order_index.asc(), ContentBlock.created_at.asc()).all()


def build_blocks_by_id(blocks: Iterable[ContentBlock]) -> dict[str, ContentBlock]:
    return {
        block.id: block
        for block in blocks
        if getattr(block, "id", None)
    }


def build_block_path(block: ContentBlock, blocks_by_id: dict[str, ContentBlock]) -> str:
    names: list[str] = []
    current = block
    visited: set[str] = set()
    while current and getattr(current, "id", None) and current.id not in visited:
        visited.add(current.id)
        names.append(current.name or current.id)
        parent_id = getattr(current, "parent_id", None)
        current = blocks_by_id.get(parent_id) if parent_id else None
    return " / ".join(reversed(names))


def build_block_reference_label(
    block: ContentBlock,
    *,
    blocks_by_id: dict[str, ContentBlock] | None = None,
) -> str:
    label = block.name or block.id
    if blocks_by_id:
        path = build_block_path(block, blocks_by_id)
        if path:
            label = path
    return f"{label} | id:{block.id}"


def build_block_reference_lookup(blocks: Iterable[ContentBlock]) -> dict[str, ContentBlock]:
    block_list = [block for block in blocks if getattr(block, "id", None)]
    lookup: dict[str, ContentBlock] = {}
    name_counts: dict[str, int] = {}

    for block in block_list:
        if block.name:
            name_counts[block.name] = name_counts.get(block.name, 0) + 1

    for block in block_list:
        lookup[block.id] = block
        lookup[f"id:{block.id}"] = block
        if block.name and name_counts.get(block.name) == 1:
            lookup[block.name] = block

    return lookup


def find_block_by_identifier(
    db: Session,
    project_id: str,
    identifier: str,
) -> ContentBlock | None:
    normalized = (identifier or "").strip()
    if not normalized:
        return None

    blocks = list_active_project_blocks(db, project_id)
    lookup = build_block_reference_lookup(blocks)
    direct = lookup.get(normalized)
    if direct:
        return direct

    if normalized.startswith("id:"):
        return None

    name_matches = [block for block in blocks if (block.name or "") == normalized]
    if len(name_matches) > 1:
        blocks_by_id = build_blocks_by_id(blocks)
        candidates = ", ".join(
            build_block_reference_label(block, blocks_by_id=blocks_by_id)
            for block in name_matches[:5]
        )
        raise DuplicateBlockReferenceError(
            f"内容块名称「{normalized}」命中多个结果，请改用 id:块ID 指定。候选：{candidates}"
        )
    if name_matches:
        return name_matches[0]
    return None
