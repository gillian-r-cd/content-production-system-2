# 功能: 项目/内容块树的 Markdown 导出、范围 JSON 导出、子树转内容块模板
# 主要函数: export_project_markdown, export_block_bundle, build_field_template_from_blocks
# 数据结构: ContentBlock 运行态树、content_block_bundle 导出格式、FieldTemplate.root_nodes

"""
内容树导出服务

统一承载以下能力：
- 项目级 Markdown 导出
- 组/内容块级范围 JSON 导出
- 项目/组/内容块转内容块模板
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from core.models import ContentBlock, Project
from core.pre_question_utils import normalize_pre_answers, normalize_pre_questions
from core.template_schema import normalize_field_template_payload


@dataclass
class FieldTemplateBuildResult:
    root_nodes: list[dict[str, Any]]
    warnings: list[str]
    summary: dict[str, int]


def _list_active_project_blocks(db: Session, project_id: str) -> list[ContentBlock]:
    return (
        db.query(ContentBlock)
        .filter(
            ContentBlock.project_id == project_id,
            ContentBlock.deleted_at == None,  # noqa: E711
        )
        .order_by(ContentBlock.depth.asc(), ContentBlock.order_index.asc(), ContentBlock.created_at.asc())
        .all()
    )


def _sort_blocks(blocks: list[ContentBlock]) -> list[ContentBlock]:
    return sorted(
        blocks,
        key=lambda block: (
            block.order_index,
            block.created_at.isoformat() if block.created_at else "",
            block.id,
        ),
    )


def _build_children_map(blocks: list[ContentBlock]) -> tuple[dict[str, ContentBlock], dict[str | None, list[ContentBlock]]]:
    block_by_id = {block.id: block for block in blocks}
    children_map: dict[str | None, list[ContentBlock]] = {}
    for block in blocks:
        children_map.setdefault(block.parent_id, []).append(block)
    for parent_id, siblings in list(children_map.items()):
        children_map[parent_id] = _sort_blocks(siblings)
    return block_by_id, children_map


def _collect_subtree_ids(root_id: str, children_map: dict[str | None, list[ContentBlock]]) -> list[str]:
    ordered_ids: list[str] = []

    def _walk(current_id: str) -> None:
        ordered_ids.append(current_id)
        for child in children_map.get(current_id, []):
            _walk(child.id)

    _walk(root_id)
    return ordered_ids


def _serialize_block_record(block: ContentBlock) -> dict[str, Any]:
    normalized_questions = normalize_pre_questions(block.pre_questions or [])
    return {
        "id": block.id,
        "project_id": block.project_id,
        "parent_id": block.parent_id,
        "name": block.name,
        "block_type": block.block_type,
        "depth": block.depth,
        "order_index": block.order_index,
        "content": block.content or "",
        "status": block.status or "pending",
        "ai_prompt": block.ai_prompt or "",
        "constraints": deepcopy(block.constraints or {}),
        "pre_questions": normalized_questions,
        "pre_answers": normalize_pre_answers(block.pre_answers or {}, normalized_questions),
        "guidance_input": getattr(block, "guidance_input", "") or "",
        "guidance_output": getattr(block, "guidance_output", "") or "",
        "depends_on": list(block.depends_on or []),
        "special_handler": block.special_handler,
        "need_review": bool(block.need_review),
        "auto_generate": bool(getattr(block, "auto_generate", False)),
        "is_collapsed": bool(block.is_collapsed),
        "model_override": getattr(block, "model_override", None),
        "digest": getattr(block, "digest", None),
        "created_at": block.created_at.isoformat() if block.created_at else None,
        "updated_at": block.updated_at.isoformat() if block.updated_at else None,
    }


def _format_markdown_heading(level: int, title: str) -> str:
    safe_level = max(1, min(level, 6))
    return f"{'#' * safe_level} {title}"


def _render_blocks_to_markdown(
    roots: list[ContentBlock],
    children_map: dict[str | None, list[ContentBlock]],
    *,
    start_heading_level: int,
) -> str:
    lines: list[str] = []

    def _walk(block: ContentBlock, heading_level: int) -> None:
        lines.append(_format_markdown_heading(heading_level, block.name))
        lines.append("")
        content = (block.content or "").strip()
        if content:
            lines.append(content)
            lines.append("")
        for child in children_map.get(block.id, []):
            _walk(child, heading_level + 1)

    for root in roots:
        _walk(root, start_heading_level)

    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def export_project_markdown(db: Session, project_id: str) -> dict[str, str]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("项目不存在")

    blocks = _list_active_project_blocks(db, project_id)
    _, children_map = _build_children_map(blocks)
    roots = children_map.get(None, [])

    lines = [_format_markdown_heading(1, project.name), ""]
    body = _render_blocks_to_markdown(roots, children_map, start_heading_level=2)
    if body:
        lines.append(body)
    markdown = "\n".join(lines).rstrip()
    return {
        "markdown": markdown,
        "filename": f"{project.name}.md",
    }


def export_block_markdown(db: Session, block_id: str) -> dict[str, str]:
    block = (
        db.query(ContentBlock)
        .filter(ContentBlock.id == block_id, ContentBlock.deleted_at == None)  # noqa: E711
        .first()
    )
    if not block:
        raise ValueError("内容块不存在")

    blocks = _list_active_project_blocks(db, block.project_id)
    block_by_id, children_map = _build_children_map(blocks)
    root = block_by_id.get(block_id)
    if not root:
        raise ValueError("内容块不存在")

    markdown = _render_blocks_to_markdown([root], children_map, start_heading_level=1)
    return {
        "markdown": markdown,
        "filename": f"{root.name}.md",
    }


def export_block_bundle(db: Session, block_id: str) -> dict[str, Any]:
    block = (
        db.query(ContentBlock)
        .filter(ContentBlock.id == block_id, ContentBlock.deleted_at == None)  # noqa: E711
        .first()
    )
    if not block:
        raise ValueError("内容块不存在")

    all_blocks = _list_active_project_blocks(db, block.project_id)
    block_by_id, children_map = _build_children_map(all_blocks)
    ordered_ids = _collect_subtree_ids(block_id, children_map)
    selected_ids = set(ordered_ids)
    selected_blocks = [block_by_id[item_id] for item_id in ordered_ids if item_id in block_by_id]

    external_dependencies: list[dict[str, str]] = []
    for item in selected_blocks:
        for dep_id in item.depends_on or []:
            if dep_id in selected_ids:
                continue
            external_dependencies.append(
                {
                    "block_id": item.id,
                    "block_name": item.name,
                    "depends_on_block_id": dep_id,
                }
            )

    field_count = sum(1 for item in selected_blocks if item.block_type == "field")
    group_count = sum(1 for item in selected_blocks if item.block_type == "group")

    return {
        "export_version": "1.0",
        "type": "content_block_bundle",
        "scope": block.block_type,
        "source_project_id": block.project_id,
        "source_root_block_id": block.id,
        "content_blocks": [_serialize_block_record(item) for item in selected_blocks],
        "meta": {
            "root_name": block.name,
            "node_count": len(selected_blocks),
            "field_count": field_count,
            "group_count": group_count,
            "has_external_dependencies": bool(external_dependencies),
            "external_dependencies": external_dependencies,
        },
    }


def _build_template_root_nodes_from_scope(
    roots: list[ContentBlock],
    children_map: dict[str | None, list[ContentBlock]],
) -> FieldTemplateBuildResult:
    selected_ids: set[str] = set()
    ordered_blocks: list[ContentBlock] = []

    def _collect(block: ContentBlock) -> None:
        selected_ids.add(block.id)
        ordered_blocks.append(block)
        for child in children_map.get(block.id, []):
            _collect(child)

    for root in roots:
        _collect(root)

    template_id_map = {block.id: f"block-{block.id}" for block in ordered_blocks}
    warnings: list[str] = []

    def _convert(block: ContentBlock) -> dict[str, Any]:
        local_depends_on = [template_id_map[dep_id] for dep_id in (block.depends_on or []) if dep_id in selected_ids]
        external_depends_on = [dep_id for dep_id in (block.depends_on or []) if dep_id not in selected_ids]
        if external_depends_on:
            warnings.append(f"节点「{block.name}」存在范围外依赖，保存模板时已忽略。")
        return {
            "template_node_id": template_id_map[block.id],
            "name": block.name,
            "block_type": block.block_type,
            "special_handler": block.special_handler,
            "ai_prompt": block.ai_prompt or "",
            "content": block.content or "",
            "pre_questions": normalize_pre_questions(block.pre_questions or []),
            "constraints": deepcopy(block.constraints or {}),
            "depends_on_template_node_ids": local_depends_on,
            "need_review": bool(block.need_review),
            "auto_generate": bool(getattr(block, "auto_generate", False)),
            "is_collapsed": bool(block.is_collapsed),
            "model_override": getattr(block, "model_override", None),
            "children": [_convert(child) for child in children_map.get(block.id, [])],
        }

    root_nodes = [_convert(root) for root in roots]
    normalized, errors = normalize_field_template_payload(
        template_name=roots[0].name if len(roots) == 1 else "导出模板",
        fields=[],
        root_nodes=root_nodes,
    )
    warnings.extend(errors)
    deduped_warnings = list(dict.fromkeys(warnings))

    return FieldTemplateBuildResult(
        root_nodes=normalized["root_nodes"],
        warnings=deduped_warnings,
        summary={
            "root_count": len(roots),
            "node_count": len(ordered_blocks),
            "field_count": sum(1 for block in ordered_blocks if block.block_type == "field"),
            "group_count": sum(1 for block in ordered_blocks if block.block_type == "group"),
            "warning_count": len(deduped_warnings),
        },
    )


def build_field_template_from_project(db: Session, project_id: str) -> FieldTemplateBuildResult:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("项目不存在")

    blocks = _list_active_project_blocks(db, project_id)
    _, children_map = _build_children_map(blocks)
    roots = children_map.get(None, [])
    if not roots:
        raise ValueError("当前项目没有可保存的内容树")

    return _build_template_root_nodes_from_scope(roots, children_map)


def build_field_template_from_block(db: Session, block_id: str) -> FieldTemplateBuildResult:
    block = (
        db.query(ContentBlock)
        .filter(ContentBlock.id == block_id, ContentBlock.deleted_at == None)  # noqa: E711
        .first()
    )
    if not block:
        raise ValueError("内容块不存在")

    blocks = _list_active_project_blocks(db, block.project_id)
    block_by_id, children_map = _build_children_map(blocks)
    root = block_by_id.get(block_id)
    if not root:
        raise ValueError("内容块不存在")

    return _build_template_root_nodes_from_scope([root], children_map)
