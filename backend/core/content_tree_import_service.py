# 功能: 将项目 JSON 或内容树范围 JSON 追加导入到当前项目
# 主要函数: import_content_tree_json
# 数据结构: 完整项目导出 JSON、content_block_bundle、ContentBlock 运行态记录

"""
内容树导入服务

第一版聚焦“将 JSON 中的内容树追加到当前项目末尾”：
- 支持当前系统完整项目导出 JSON
- 支持 content_block_bundle 范围导出 JSON
- 不覆盖现有节点，只追加新根节点
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from core.models import ContentBlock, Project, generate_uuid
from core.pre_question_utils import normalize_pre_answers, normalize_pre_questions


def _extract_content_blocks(data: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(data, dict):
        raise ValueError("导入内容必须是 JSON 对象")

    if isinstance(data.get("content_blocks"), list):
        if data.get("type") == "content_block_bundle":
            return data.get("content_blocks", []), "content_block_bundle"
        return data.get("content_blocks", []), "project_export"

    raise ValueError("JSON 中缺少 content_blocks，无法执行目录追加导入")


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda item: (
            int(item.get("order_index", 0) or 0),
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
    )


def import_content_tree_json(
    *,
    db: Session,
    project_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("项目不存在")

    raw_blocks, source_type = _extract_content_blocks(data)
    active_records = [
        deepcopy(item)
        for item in raw_blocks
        if isinstance(item, dict) and not item.get("deleted_at")
    ]
    if not active_records:
        raise ValueError("导入文件中没有可追加的内容块")

    record_by_old_id = {
        str(item.get("id")): item
        for item in active_records
        if str(item.get("id") or "").strip()
    }
    if not record_by_old_id:
        raise ValueError("导入文件中的内容块缺少有效 id")

    children_map: dict[str | None, list[dict[str, Any]]] = {}
    for item in active_records:
        parent_id = item.get("parent_id")
        if parent_id not in record_by_old_id:
            parent_id = None
        children_map.setdefault(parent_id, []).append(item)
    for parent_id, siblings in list(children_map.items()):
        children_map[parent_id] = _sort_records(siblings)

    roots = children_map.get(None, [])
    if not roots:
        raise ValueError("导入文件中没有可识别的根节点")

    existing_top_level_count = (
        db.query(ContentBlock)
        .filter(
            ContentBlock.project_id == project_id,
            ContentBlock.parent_id == None,  # noqa: E711
            ContentBlock.deleted_at == None,  # noqa: E711
        )
        .count()
    )

    id_mapping = {old_id: generate_uuid() for old_id in record_by_old_id}
    external_dependency_warnings: list[str] = []
    created_records: list[ContentBlock] = []

    def _walk(record: dict[str, Any], parent_id: str | None, depth: int, order_index: int) -> None:
        old_id = str(record.get("id"))
        new_id = id_mapping[old_id]
        internal_depends_on: list[str] = []
        external_depends_on: list[str] = []
        for dep_id in record.get("depends_on", []) or []:
            dep_text = str(dep_id or "").strip()
            if not dep_text:
                continue
            if dep_text in id_mapping:
                internal_depends_on.append(id_mapping[dep_text])
            else:
                external_depends_on.append(dep_text)
        if external_depends_on:
            external_dependency_warnings.append(
                f"节点「{record.get('name') or old_id}」存在范围外依赖，导入时已忽略。"
            )

        normalized_questions = normalize_pre_questions(record.get("pre_questions", []))
        imported_block = ContentBlock(
            id=new_id,
            project_id=project_id,
            parent_id=parent_id,
            name=str(record.get("name") or "未命名节点"),
            block_type=str(record.get("block_type") or "field"),
            depth=depth,
            order_index=order_index,
            content=str(record.get("content") or ""),
            status=str(record.get("status") or "pending"),
            ai_prompt=str(record.get("ai_prompt") or ""),
            constraints=deepcopy(record.get("constraints") or {}),
            pre_questions=normalized_questions,
            pre_answers=normalize_pre_answers(record.get("pre_answers") or {}, normalized_questions),
            guidance_input=str(record.get("guidance_input") or ""),
            guidance_output=str(record.get("guidance_output") or ""),
            depends_on=internal_depends_on,
            special_handler=record.get("special_handler"),
            need_review=bool(record.get("need_review", True)),
            auto_generate=bool(record.get("auto_generate", False)),
            is_collapsed=bool(record.get("is_collapsed", False)),
            model_override=record.get("model_override"),
            digest=record.get("digest"),
        )
        db.add(imported_block)
        created_records.append(imported_block)

        child_records = children_map.get(old_id, [])
        for child_index, child in enumerate(child_records):
            _walk(child, new_id, depth + 1, child_index)

    for root_index, root in enumerate(roots):
        _walk(root, None, 0, existing_top_level_count + root_index)

    db.commit()

    return {
        "message": f"已追加导入 {len(created_records)} 个内容块",
        "source_type": source_type,
        "blocks_created": len(created_records),
        "root_count": len(roots),
        "warning_count": len(dict.fromkeys(external_dependency_warnings)),
        "warnings": list(dict.fromkeys(external_dependency_warnings)),
    }
