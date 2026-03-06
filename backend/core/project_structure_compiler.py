# backend/core/project_structure_compiler.py
# 功能: 将项目级自动拆分草稿编译为可实例化的统一模板树，并解析草稿态依赖
# 主要函数: compile_project_structure_draft
# 数据结构: 输入 ProjectStructureDraft，输出 root_nodes + validation_errors + summary

"""
项目级结构草稿编译器

设计原则：
- 草稿层只保存 chunks / plans / shared / aggregate
- 编译后统一产出 TemplateNode 兼容树
- 所有草稿态依赖在这里收口，运行态仍只认 ContentBlock.depends_on
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from core.models import ContentBlock, ProjectStructureDraft, generate_uuid
from core.template_schema import iter_template_nodes, normalize_template_nodes


@dataclass
class CompilationResult:
    root_nodes: list[dict[str, Any]]
    validation_errors: list[str]
    summary: dict[str, Any]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    return {
        "chunks": payload.get("chunks") if isinstance(payload.get("chunks"), list) else [],
        "plans": payload.get("plans") if isinstance(payload.get("plans"), list) else [],
        "shared_root_nodes": payload.get("shared_root_nodes") if isinstance(payload.get("shared_root_nodes"), list) else [],
        "aggregate_root_nodes": payload.get("aggregate_root_nodes") if isinstance(payload.get("aggregate_root_nodes"), list) else [],
        "ui_state": payload.get("ui_state") if isinstance(payload.get("ui_state"), dict) else {},
    }


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _clone_nodes_with_new_ids(
    nodes: list[dict[str, Any]],
    *,
    scope: str,
    current_chunk_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    cloned = deepcopy(nodes)
    id_map: dict[str, str] = {}

    for node in iter_template_nodes(cloned):
        old_id = str(node.get("template_node_id") or generate_uuid())
        new_id = generate_uuid()
        id_map[old_id] = new_id
        node["template_node_id"] = new_id
        node["_draft_original_node_id"] = old_id
        node["_draft_scope"] = scope
        node["_draft_current_chunk_id"] = current_chunk_id
        node["draft_dependency_refs"] = deepcopy(
            node.get("draft_dependency_refs") or node.get("depends_on_refs") or []
        )

    for node in iter_template_nodes(cloned):
        remapped_local_ids = [
            id_map.get(dep_id, dep_id)
            for dep_id in (node.get("depends_on_template_node_ids") or [])
        ]
        node["depends_on_template_node_ids"] = _dedupe(remapped_local_ids)

    return cloned, id_map


def _register_registry_nodes(
    registry: dict[str, Any],
    *,
    scope: str,
    nodes: list[dict[str, Any]],
    chunk_id: str | None = None,
) -> None:
    for node in iter_template_nodes(nodes):
        original_id = node.get("_draft_original_node_id")
        if not original_id:
            continue
        if scope == "shared":
            registry["shared_nodes"][original_id] = node["template_node_id"]
        elif scope == "aggregate":
            registry["aggregate_nodes"][original_id] = node["template_node_id"]
        elif scope == "chunk_plan" and chunk_id:
            registry["chunk_plan_nodes"].setdefault(chunk_id, {})[original_id] = node["template_node_id"]


def _cleanup_compiled_nodes(nodes: list[dict[str, Any]]) -> None:
    for node in iter_template_nodes(nodes):
        node.pop("_draft_original_node_id", None)
        node.pop("_draft_scope", None)
        node.pop("_draft_current_chunk_id", None)
        node.pop("depends_on_refs", None)
        if not node.get("draft_dependency_refs"):
            node.pop("draft_dependency_refs", None)
        if not node.get("external_depends_on_block_ids"):
            node.pop("external_depends_on_block_ids", None)


def _resolve_dependency_target(
    ref: dict[str, Any],
    *,
    registry: dict[str, Any],
    current_chunk_id: str | None,
    project_blocks_by_id: dict[str, ContentBlock],
) -> tuple[str | None, str | None]:
    ref_type = str(ref.get("ref_type") or "").strip()
    if ref_type == "project_block":
        block_id = _clean_text(ref.get("block_id"))
        if not block_id:
            return None, "项目块依赖缺少 block_id"
        if block_id not in project_blocks_by_id:
            return None, f"依赖的项目内容块不存在: {block_id}"
        return "external", block_id

    if ref_type == "shared_node":
        node_id = _clean_text(ref.get("node_id"))
        compiled_id = registry["shared_nodes"].get(node_id)
        if not compiled_id:
            return None, f"共享结构依赖节点不存在: {node_id}"
        return "template", compiled_id

    if ref_type == "aggregate_node":
        node_id = _clean_text(ref.get("node_id"))
        compiled_id = registry["aggregate_nodes"].get(node_id)
        if not compiled_id:
            return None, f"聚合结构依赖节点不存在: {node_id}"
        return "template", compiled_id

    if ref_type == "chunk_source":
        chunk_id = _clean_text(ref.get("chunk_id")) or current_chunk_id or ""
        if chunk_id == "current":
            chunk_id = current_chunk_id or ""
        compiled_id = registry["chunk_source_nodes"].get(chunk_id)
        if not compiled_id:
            return None, f"chunk 源内容块不存在: {chunk_id or 'current'}"
        return "template", compiled_id

    if ref_type == "chunk_plan_node":
        chunk_id = _clean_text(ref.get("chunk_id")) or current_chunk_id or ""
        if chunk_id == "current":
            chunk_id = current_chunk_id or ""
        node_id = _clean_text(ref.get("node_id"))
        compiled_id = registry["chunk_plan_nodes"].get(chunk_id, {}).get(node_id)
        if not compiled_id:
            return None, f"chunk 方案节点不存在: chunk={chunk_id or 'current'} node={node_id}"
        return "template", compiled_id

    return None, f"不支持的草稿依赖类型: {ref_type or '空'}"


def _collect_cycle_errors(
    *,
    compiled_nodes: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []
    reported_cycles: set[tuple[str, ...]] = set()

    def _canonical_cycle(cycle_ids: list[str]) -> tuple[str, ...]:
        if not cycle_ids:
            return tuple()
        if len(cycle_ids) == 1:
            return (cycle_ids[0],)
        rotations = [tuple(cycle_ids[index:] + cycle_ids[:index]) for index in range(len(cycle_ids))]
        return min(rotations)

    def _visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            if node_id in path:
                cycle_ids = path[path.index(node_id):]
            else:
                cycle_ids = [node_id]
            canonical = _canonical_cycle(cycle_ids)
            if canonical and canonical not in reported_cycles:
                reported_cycles.add(canonical)
                cycle_names = [
                    compiled_nodes.get(cycle_id, {}).get("name", "未命名节点")
                    for cycle_id in cycle_ids
                ]
                errors.append(f"检测到循环依赖: {' -> '.join(cycle_names)}")
            return

        visiting.add(node_id)
        path.append(node_id)
        node = compiled_nodes.get(node_id) or {}
        for dep_id in node.get("depends_on_template_node_ids") or []:
            if dep_id in compiled_nodes:
                _visit(dep_id)
        path.pop()
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in compiled_nodes:
        _visit(node_id)

    return errors


def compile_project_structure_draft(
    draft: ProjectStructureDraft,
    *,
    existing_project_blocks: list[ContentBlock] | None = None,
    batch_name: str | None = None,
) -> CompilationResult:
    payload = _normalize_payload(draft.draft_payload)
    errors: list[str] = []
    project_blocks = existing_project_blocks or []
    project_blocks_by_id = {block.id: block for block in project_blocks}

    chunks: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    for index, raw_chunk in enumerate(payload["chunks"]):
        if not isinstance(raw_chunk, dict):
            errors.append(f"第 {index + 1} 个 chunk 不是对象")
            continue
        chunk_id = _clean_text(raw_chunk.get("chunk_id")) or generate_uuid()
        if chunk_id in seen_chunk_ids:
            errors.append(f"chunk_id 重复: {chunk_id}")
            continue
        seen_chunk_ids.add(chunk_id)
        title = _clean_text(raw_chunk.get("title")) or f"内容片段 {index + 1:02d}"
        content = _clean_text(raw_chunk.get("content"))
        if not content:
            errors.append(f"chunk「{title}」内容不能为空")
        chunks.append({
            "chunk_id": chunk_id,
            "title": title,
            "content": content,
            "order_index": int(raw_chunk.get("order_index", index)),
        })
    chunks.sort(key=lambda item: item["order_index"])

    normalized_shared, shared_errors = normalize_template_nodes(payload["shared_root_nodes"])
    normalized_aggregate, aggregate_errors = normalize_template_nodes(payload["aggregate_root_nodes"])
    errors.extend(shared_errors)
    errors.extend(aggregate_errors)

    normalized_plans: list[dict[str, Any]] = []
    seen_plan_ids: set[str] = set()
    for index, raw_plan in enumerate(payload["plans"]):
        if not isinstance(raw_plan, dict):
            errors.append(f"第 {index + 1} 个编排方案不是对象")
            continue
        plan_id = _clean_text(raw_plan.get("plan_id")) or generate_uuid()
        if plan_id in seen_plan_ids:
            errors.append(f"plan_id 重复: {plan_id}")
            continue
        seen_plan_ids.add(plan_id)
        normalized_root_nodes, plan_errors = normalize_template_nodes(raw_plan.get("root_nodes") or [])
        errors.extend(plan_errors)
        normalized_plans.append({
            "plan_id": plan_id,
            "name": _clean_text(raw_plan.get("name")) or f"编排方案 {index + 1}",
            "target_chunk_ids": [
                chunk_id for chunk_id in raw_plan.get("target_chunk_ids", [])
                if chunk_id in seen_chunk_ids
            ] if isinstance(raw_plan.get("target_chunk_ids"), list) else [],
            "root_nodes": normalized_root_nodes,
        })

    batch_group = {
        "template_node_id": generate_uuid(),
        "name": batch_name or f"{draft.name or '自动拆分内容'}批次",
        "block_type": "group",
        "children": [],
    }
    compiled_root_nodes = [batch_group]
    compiled_node_lookup: dict[str, dict[str, Any]] = {}
    registry: dict[str, Any] = {
        "shared_nodes": {},
        "aggregate_nodes": {},
        "chunk_source_nodes": {},
        "chunk_plan_nodes": {},
    }

    if normalized_shared:
        shared_group = {
            "template_node_id": generate_uuid(),
            "name": "共享结构",
            "block_type": "group",
            "children": [],
        }
        shared_nodes, _ = _clone_nodes_with_new_ids(normalized_shared, scope="shared")
        shared_group["children"] = shared_nodes
        batch_group["children"].append(shared_group)
        _register_registry_nodes(registry, scope="shared", nodes=shared_nodes)

    for chunk in chunks:
        chunk_group = {
            "template_node_id": generate_uuid(),
            "name": chunk["title"],
            "block_type": "group",
            "children": [],
        }
        source_node = {
            "template_node_id": generate_uuid(),
            "name": chunk["title"],
            "block_type": "field",
            "content": chunk["content"],
            "need_review": False,
            "auto_generate": False,
            "depends_on_template_node_ids": [],
            "external_depends_on_block_ids": [],
            "draft_dependency_refs": [],
            "_draft_scope": "chunk_source",
            "_draft_current_chunk_id": chunk["chunk_id"],
        }
        chunk_group["children"].append(source_node)
        registry["chunk_source_nodes"][chunk["chunk_id"]] = source_node["template_node_id"]

        for plan in normalized_plans:
            if chunk["chunk_id"] not in plan["target_chunk_ids"]:
                continue
            plan_nodes, _ = _clone_nodes_with_new_ids(
                plan["root_nodes"],
                scope="chunk_plan",
                current_chunk_id=chunk["chunk_id"],
            )
            chunk_group["children"].extend(plan_nodes)
            _register_registry_nodes(
                registry,
                scope="chunk_plan",
                nodes=plan_nodes,
                chunk_id=chunk["chunk_id"],
            )

        batch_group["children"].append(chunk_group)

    if normalized_aggregate:
        aggregate_group = {
            "template_node_id": generate_uuid(),
            "name": "聚合结构",
            "block_type": "group",
            "children": [],
        }
        aggregate_nodes, _ = _clone_nodes_with_new_ids(normalized_aggregate, scope="aggregate")
        aggregate_group["children"] = aggregate_nodes
        batch_group["children"].append(aggregate_group)
        _register_registry_nodes(registry, scope="aggregate", nodes=aggregate_nodes)

    for node in iter_template_nodes(compiled_root_nodes):
        compiled_node_lookup[node["template_node_id"]] = node

    for node in iter_template_nodes(compiled_root_nodes):
        refs = node.get("draft_dependency_refs") or []
        current_chunk_id = node.get("_draft_current_chunk_id")
        local_dep_ids = _dedupe(list(node.get("depends_on_template_node_ids") or []))
        external_dep_ids = _dedupe(list(node.get("external_depends_on_block_ids") or []))
        for ref in refs:
            if not isinstance(ref, dict):
                errors.append(f"节点「{node.get('name', '未命名节点')}」包含非法依赖引用")
                continue
            dep_kind, dep_value = _resolve_dependency_target(
                ref,
                registry=registry,
                current_chunk_id=current_chunk_id,
                project_blocks_by_id=project_blocks_by_id,
            )
            if dep_kind == "template" and dep_value:
                local_dep_ids.append(dep_value)
            elif dep_kind == "external" and dep_value:
                external_dep_ids.append(dep_value)
            elif dep_value:
                errors.append(dep_value)

        local_dep_ids = _dedupe(local_dep_ids)
        external_dep_ids = _dedupe(external_dep_ids)

        for dep_id in local_dep_ids:
            dep_node = compiled_node_lookup.get(dep_id)
            if dep_node and dep_node.get("block_type") in {"group", "phase"}:
                errors.append(
                    f"节点「{node.get('name', '未命名节点')}」不能依赖容器节点「{dep_node.get('name', '未命名节点')}」"
                )
        for dep_id in external_dep_ids:
            dep_block = project_blocks_by_id.get(dep_id)
            if dep_block and dep_block.block_type in {"group", "phase"}:
                errors.append(
                    f"节点「{node.get('name', '未命名节点')}」不能依赖项目容器节点「{dep_block.name}」"
                )

        node["depends_on_template_node_ids"] = local_dep_ids
        node["external_depends_on_block_ids"] = external_dep_ids

    errors.extend(_collect_cycle_errors(compiled_nodes=compiled_node_lookup))

    _cleanup_compiled_nodes(compiled_root_nodes)
    summary = {
        "chunk_count": len(chunks),
        "plan_count": len(normalized_plans),
        "shared_node_count": len(list(iter_template_nodes(normalized_shared))),
        "aggregate_node_count": len(list(iter_template_nodes(normalized_aggregate))),
        "compiled_node_count": len(list(iter_template_nodes(compiled_root_nodes))),
    }
    return CompilationResult(
        root_nodes=compiled_root_nodes,
        validation_errors=errors,
        summary=summary,
    )
