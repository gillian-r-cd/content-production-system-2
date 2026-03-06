from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable
import uuid


def generate_uuid() -> str:
    return str(uuid.uuid4())

TEMPLATE_SCHEMA_VERSION = 2
TEMPLATE_NODE_BLOCK_TYPES = {"phase", "group", "field", "proposal"}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _as_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_children(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(item) for item in value if isinstance(item, dict)]


def iter_template_nodes(nodes: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for node in nodes:
        yield node
        yield from iter_template_nodes(node.get("children", []) or [])


def normalize_template_nodes(
    raw_nodes: list[dict[str, Any]] | None,
    *,
    inherited_special_handler: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Normalize template nodes into schema v2.

    - Ensures every node has a stable `template_node_id`
    - Converts legacy `depends_on` names/ids to `depends_on_template_node_ids`
    - Recursively normalizes children and template metadata
    """
    raw_nodes = raw_nodes or []
    errors: list[str] = []

    def _normalize(raw: dict[str, Any], default_type: str, inherited_handler: str | None) -> dict[str, Any]:
        block_type = str(raw.get("block_type") or default_type or "field").strip() or "field"
        if block_type not in TEMPLATE_NODE_BLOCK_TYPES:
            block_type = "field"

        node = {
            "template_node_id": str(raw.get("template_node_id") or raw.get("id") or generate_uuid()),
            "name": str(raw.get("name") or "").strip() or "未命名节点",
            "block_type": block_type,
            "special_handler": raw.get("special_handler", inherited_handler),
            "ai_prompt": str(raw.get("ai_prompt") or ""),
            "content": str(raw.get("content") or ""),
            "field_type": str(raw.get("field_type") or raw.get("type") or ""),
            "dependency_type": str(raw.get("dependency_type") or "all"),
            "constraints": _as_dict(raw.get("constraints")),
            "pre_questions": _as_str_list(raw.get("pre_questions")),
            "need_review": bool(raw.get("need_review", True)),
            "auto_generate": bool(raw.get("auto_generate", False)),
            "is_collapsed": bool(raw.get("is_collapsed", False)),
            "model_override": raw.get("model_override"),
            "guidance_input": str(raw.get("guidance_input") or ""),
            "guidance_output": str(raw.get("guidance_output") or ""),
            "external_depends_on_block_ids": _as_str_list(raw.get("external_depends_on_block_ids")),
            "draft_dependency_refs": [
                deepcopy(item)
                for item in (raw.get("draft_dependency_refs") or raw.get("depends_on_refs") or [])
                if isinstance(item, dict)
            ],
            "children": [],
            "_legacy_depends_on": _as_str_list(raw.get("depends_on")),
            "_depends_on_template_node_ids": _as_str_list(raw.get("depends_on_template_node_ids")),
        }

        child_default_type = "field" if block_type in {"phase", "group"} else "field"
        raw_children = _as_children(raw.get("children"))
        if block_type == "phase" and not raw_children and isinstance(raw.get("default_fields"), list):
            raw_children = _as_children(raw.get("default_fields"))

        node["children"] = [
            _normalize(child, child_default_type, node["special_handler"])
            for child in raw_children
        ]
        return node

    normalized = [_normalize(node, "field", inherited_special_handler) for node in raw_nodes if isinstance(node, dict)]

    id_map: dict[str, dict[str, Any]] = {}
    name_map: dict[str, list[dict[str, Any]]] = {}
    for node in iter_template_nodes(normalized):
        node_id = node["template_node_id"]
        if node_id in id_map:
            new_id = generate_uuid()
            errors.append(f"模板节点 ID 重复，已重写: {node_id} -> {new_id}")
            node["template_node_id"] = new_id
            node_id = new_id
        id_map[node_id] = node
        name_map.setdefault(node["name"], []).append(node)

    for node in iter_template_nodes(normalized):
        resolved: list[str] = []
        seen: set[str] = set()

        for dep in node.pop("_depends_on_template_node_ids", []):
            if dep in id_map and dep not in seen and dep != node["template_node_id"]:
                resolved.append(dep)
                seen.add(dep)
            elif dep and dep not in id_map:
                errors.append(f"节点「{node['name']}」依赖的模板节点 ID 不存在: {dep}")

        for dep in node.pop("_legacy_depends_on", []):
            if dep == node["template_node_id"]:
                continue
            if dep in id_map and dep not in seen:
                resolved.append(dep)
                seen.add(dep)
                continue

            matches = name_map.get(dep, [])
            if len(matches) == 1:
                match_id = matches[0]["template_node_id"]
                if match_id not in seen:
                    resolved.append(match_id)
                    seen.add(match_id)
            elif len(matches) > 1:
                errors.append(f"节点「{node['name']}」按名称依赖「{dep}」存在歧义，请改用 template_node_id")
            elif dep:
                errors.append(f"节点「{node['name']}」依赖的节点不存在: {dep}")

        node["depends_on_template_node_ids"] = resolved

    return normalized, errors


def build_legacy_field_template_root_nodes(
    template_name: str,
    fields: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Wrap legacy flat `fields[]` into a single top-level phase node.
    This preserves the old project application behavior while upgrading storage to tree nodes.
    """
    root_id = generate_uuid()
    children: list[dict[str, Any]] = []
    for idx, field in enumerate(fields or []):
        if not isinstance(field, dict):
            continue
        child = deepcopy(field)
        child.setdefault("template_node_id", field.get("template_node_id") or generate_uuid())
        child.setdefault("block_type", field.get("block_type") or "field")
        child.setdefault("is_collapsed", False)
        child.setdefault("guidance_input", "")
        child.setdefault("guidance_output", "")
        child.setdefault("order_index", idx)
        children.append(child)

    return [{
        "template_node_id": root_id,
        "name": template_name or "模板",
        "block_type": "phase",
        "special_handler": None,
        "is_collapsed": False,
        "children": children,
    }]


def flatten_template_fields(root_nodes: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """
    Produce legacy-compatible `fields[]` from tree nodes.

    Only concrete content nodes are exported here so old UIs can keep working.
    """
    root_nodes = root_nodes or []
    id_to_name = {
        node["template_node_id"]: node["name"]
        for node in iter_template_nodes(root_nodes)
    }
    result: list[dict[str, Any]] = []

    for node in iter_template_nodes(root_nodes):
        if node.get("block_type") not in {"field", "proposal"}:
            continue
        result.append({
            "template_node_id": node["template_node_id"],
            "name": node.get("name", ""),
            "block_type": node.get("block_type", "field"),
            "type": node.get("field_type") or node.get("block_type", "field"),
            "field_type": node.get("field_type") or node.get("block_type", "field"),
            "ai_prompt": node.get("ai_prompt", ""),
            "content": node.get("content", ""),
            "pre_questions": _as_str_list(node.get("pre_questions")),
            "depends_on": [
                id_to_name.get(dep_id, dep_id)
                for dep_id in _as_str_list(node.get("depends_on_template_node_ids"))
            ],
            "depends_on_template_node_ids": _as_str_list(node.get("depends_on_template_node_ids")),
            "dependency_type": node.get("dependency_type", "all") or "all",
            "constraints": _as_dict(node.get("constraints")),
            "need_review": bool(node.get("need_review", True)),
            "auto_generate": bool(node.get("auto_generate", False)),
            "model_override": node.get("model_override"),
            "special_handler": node.get("special_handler"),
            "guidance_input": node.get("guidance_input", ""),
            "guidance_output": node.get("guidance_output", ""),
        })

    return result


def normalize_field_template_payload(
    *,
    template_name: str,
    fields: list[dict[str, Any]] | None = None,
    root_nodes: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    if not root_nodes and not fields:
        return {
            "schema_version": TEMPLATE_SCHEMA_VERSION,
            "root_nodes": [],
            "fields": [],
        }, []
    if root_nodes:
        normalized_root_nodes, errors = normalize_template_nodes(root_nodes)
    else:
        legacy_root_nodes = build_legacy_field_template_root_nodes(template_name, fields)
        normalized_root_nodes, errors = normalize_template_nodes(legacy_root_nodes)

    return {
        "schema_version": TEMPLATE_SCHEMA_VERSION,
        "root_nodes": normalized_root_nodes,
        "fields": flatten_template_fields(normalized_root_nodes),
    }, errors


def phase_template_to_root_nodes(phases: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[str]]:
    raw_nodes: list[dict[str, Any]] = []
    sorted_phases = sorted(
        [deepcopy(phase) for phase in (phases or []) if isinstance(phase, dict)],
        key=lambda item: item.get("order_index", 0),
    )
    for phase in sorted_phases:
        raw_nodes.append({
            "template_node_id": phase.get("template_node_id") or phase.get("id") or generate_uuid(),
            "name": phase.get("name", "未命名阶段"),
            "block_type": phase.get("block_type", "phase") or "phase",
            "special_handler": phase.get("special_handler"),
            "ai_prompt": phase.get("ai_prompt", ""),
            "content": phase.get("content", ""),
            "pre_questions": phase.get("pre_questions", []),
            "depends_on": phase.get("depends_on", []),
            "depends_on_template_node_ids": phase.get("depends_on_template_node_ids", []),
            "constraints": phase.get("constraints", {}),
            "need_review": phase.get("need_review", True),
            "auto_generate": phase.get("auto_generate", False),
            "is_collapsed": phase.get("is_collapsed", False),
            "model_override": phase.get("model_override"),
            "guidance_input": phase.get("guidance_input", ""),
            "guidance_output": phase.get("guidance_output", ""),
            "children": phase.get("children") or phase.get("default_fields") or [],
        })
    return normalize_template_nodes(raw_nodes)


def root_nodes_to_phase_template_phases(root_nodes: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized_root_nodes, _ = normalize_template_nodes(root_nodes or [])

    def _serialize(node: dict[str, Any], order_index: int) -> dict[str, Any]:
        children = node.get("children", []) or []
        payload = {
            "template_node_id": node.get("template_node_id"),
            "name": node.get("name", "未命名节点"),
            "block_type": node.get("block_type", "field"),
            "special_handler": node.get("special_handler"),
            "order_index": order_index,
            "ai_prompt": node.get("ai_prompt", ""),
            "content": node.get("content", ""),
            "pre_questions": _as_str_list(node.get("pre_questions")),
            "depends_on_template_node_ids": _as_str_list(node.get("depends_on_template_node_ids")),
            "constraints": _as_dict(node.get("constraints")),
            "need_review": bool(node.get("need_review", True)),
            "auto_generate": bool(node.get("auto_generate", False)),
            "is_collapsed": bool(node.get("is_collapsed", False)),
            "model_override": node.get("model_override"),
            "guidance_input": node.get("guidance_input", ""),
            "guidance_output": node.get("guidance_output", ""),
        }
        if node.get("block_type") == "phase":
            payload["default_fields"] = [
                _serialize(child, idx)
                for idx, child in enumerate(children)
            ]
        elif children:
            payload["children"] = [
                _serialize(child, idx)
                for idx, child in enumerate(children)
            ]
        return payload

    return [
        _serialize(node, idx)
        for idx, node in enumerate(normalized_root_nodes)
    ]


def instantiate_template_nodes(
    *,
    project_id: str,
    root_nodes: list[dict[str, Any]],
    parent_id: str | None = None,
    base_depth: int = 0,
    start_order_index: int = 0,
) -> list[dict[str, Any]]:
    normalized_root_nodes, _ = normalize_template_nodes(root_nodes)
    node_to_block_id: dict[str, str] = {}
    records: list[dict[str, Any]] = []

    def _walk(nodes: list[dict[str, Any]], current_parent_id: str | None, depth: int, order_offset: int) -> None:
        for index, node in enumerate(nodes):
            block_id = generate_uuid()
            node_to_block_id[node["template_node_id"]] = block_id
            content = str(node.get("content") or "")
            need_review = bool(node.get("need_review", True))
            records.append({
                "id": block_id,
                "project_id": project_id,
                "parent_id": current_parent_id,
                "name": node.get("name", "未命名节点"),
                "block_type": node.get("block_type", "field"),
                "depth": depth,
                "order_index": order_offset + index,
                "content": content,
                "status": ("in_progress" if need_review else "completed") if content else "pending",
                "ai_prompt": node.get("ai_prompt", ""),
                "constraints": _as_dict(node.get("constraints")),
                "pre_questions": _as_str_list(node.get("pre_questions")),
                "special_handler": node.get("special_handler"),
                "need_review": need_review,
                "auto_generate": bool(node.get("auto_generate", False)),
                "is_collapsed": bool(node.get("is_collapsed", False)),
                "model_override": node.get("model_override"),
                "guidance_input": node.get("guidance_input", ""),
                "guidance_output": node.get("guidance_output", ""),
                "external_depends_on_block_ids": _as_str_list(node.get("external_depends_on_block_ids")),
                "_template_node_id": node["template_node_id"],
                "_depends_on_template_node_ids": _as_str_list(node.get("depends_on_template_node_ids")),
            })
            _walk(node.get("children", []) or [], block_id, depth + 1, 0)

    _walk(normalized_root_nodes, parent_id, base_depth, start_order_index)

    for record in records:
        dep_ids: list[str] = []
        for dep_node_id in record.pop("_depends_on_template_node_ids", []):
            dep_block_id = node_to_block_id.get(dep_node_id)
            if dep_block_id:
                dep_ids.append(dep_block_id)
        dep_ids.extend(
            dep_id
            for dep_id in record.pop("external_depends_on_block_ids", [])
            if dep_id and dep_id not in dep_ids
        )
        record["depends_on"] = dep_ids
        record.pop("_template_node_id", None)

    return records
