# backend/core/project_structure_apply_service.py
# 功能: 项目级结构草稿应用服务，在单事务中完成编译、校验、实例化和草稿元数据回写
# 主要函数: apply_project_structure_draft
# 数据结构: 输入 ProjectStructureDraft，输出应用结果摘要与创建块数量

"""
项目级结构草稿应用服务

职责：
- 读取草稿并编译
- 在一个数据库事务里实例化 ContentBlock
- 成功后回写草稿校验和应用元数据
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.models import ContentBlock, Project, ProjectStructureDraft
from core.project_structure_compiler import compile_project_structure_draft
from core.template_schema import instantiate_template_nodes


def _ensure_draft_is_applyable(draft: ProjectStructureDraft) -> None:
    if draft.validation_errors:
        raise ValueError("草稿校验未通过，请先修复错误后重新校验")
    if not draft.last_validated_at:
        raise ValueError("草稿尚未校验，请先执行校验")
    if draft.status not in {"validated", "applied"}:
        raise ValueError("草稿尚未校验，请先执行校验")


def apply_project_structure_draft(
    *,
    draft: ProjectStructureDraft,
    db: Session,
    parent_id: str | None = None,
    batch_name: str | None = None,
) -> dict[str, Any]:
    _ensure_draft_is_applyable(draft)

    project = db.query(Project).filter(Project.id == draft.project_id).first()
    if not project:
        raise ValueError("草稿关联的项目不存在")

    existing_blocks = db.query(ContentBlock).filter(
        ContentBlock.project_id == draft.project_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).all()

    compilation = compile_project_structure_draft(
        draft,
        existing_project_blocks=existing_blocks,
        batch_name=batch_name,
    )

    draft.validation_errors = compilation.validation_errors
    draft.last_validated_at = datetime.now()
    draft.status = "validated" if not compilation.validation_errors else "draft"
    flag_modified(draft, "validation_errors")

    if compilation.validation_errors:
        db.commit()
        raise ValueError("; ".join(compilation.validation_errors))

    if parent_id is not None:
        parent_block = db.query(ContentBlock).filter(
            ContentBlock.id == parent_id,
            ContentBlock.project_id == draft.project_id,
            ContentBlock.deleted_at == None,  # noqa: E711
        ).first()
        if not parent_block:
            raise ValueError("目标父内容块不存在")
        base_depth = parent_block.depth + 1
    else:
        base_depth = 0

    start_order_index = db.query(ContentBlock).filter(
        ContentBlock.project_id == draft.project_id,
        ContentBlock.parent_id == parent_id,
        ContentBlock.deleted_at == None,  # noqa: E711
    ).count()

    blocks_to_create = instantiate_template_nodes(
        project_id=draft.project_id,
        root_nodes=compilation.root_nodes,
        parent_id=parent_id,
        base_depth=base_depth,
        start_order_index=start_order_index,
    )

    for block_data in blocks_to_create:
        db.add(ContentBlock(**block_data))

    draft.apply_count = int(draft.apply_count or 0) + 1
    draft.last_applied_at = datetime.now()
    draft.status = "applied"
    db.commit()

    return {
        "message": f"已应用草稿「{draft.name}」",
        "blocks_created": len(blocks_to_create),
        "summary": compilation.summary,
    }
