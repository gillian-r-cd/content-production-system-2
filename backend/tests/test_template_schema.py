import pytest

from core.template_schema import (
    instantiate_template_nodes,
    normalize_field_template_payload,
    phase_template_to_root_nodes,
)


def test_normalize_legacy_field_template_payload_wraps_into_tree():
    normalized, errors = normalize_field_template_payload(
        template_name="文章模板",
        fields=[
            {"name": "主题", "ai_prompt": "生成主题"},
            {"name": "大纲", "ai_prompt": "生成大纲", "depends_on": ["主题"]},
        ],
    )

    assert errors == []
    assert normalized["schema_version"] == 2
    assert len(normalized["root_nodes"]) == 1
    root = normalized["root_nodes"][0]
    assert root["name"] == "文章模板"
    assert root["block_type"] == "phase"
    assert len(root["children"]) == 2

    topic_node = root["children"][0]
    outline_node = root["children"][1]
    assert outline_node["depends_on_template_node_ids"] == [topic_node["template_node_id"]]


def test_instantiate_template_nodes_remaps_dependencies_to_block_ids():
    normalized, _ = normalize_field_template_payload(
        template_name="课程模板",
        fields=[
            {"name": "目标"},
            {"name": "大纲", "depends_on": ["目标"]},
        ],
    )

    blocks = instantiate_template_nodes(
        project_id="project-1",
        root_nodes=normalized["root_nodes"],
        parent_id=None,
        base_depth=0,
        start_order_index=0,
    )

    by_name = {block["name"]: block for block in blocks}
    assert by_name["课程模板"]["depth"] == 0
    assert by_name["目标"]["depth"] == 1
    assert by_name["大纲"]["depends_on"] == [by_name["目标"]["id"]]


def test_phase_template_to_root_nodes_keeps_phase_handlers_and_nested_fields():
    root_nodes, errors = phase_template_to_root_nodes([
        {
            "name": "调研",
            "block_type": "phase",
            "special_handler": "research",
            "order_index": 0,
            "default_fields": [
                {"name": "用户画像", "block_type": "field"},
            ],
        }
    ])

    assert errors == []
    assert len(root_nodes) == 1
    assert root_nodes[0]["special_handler"] == "research"
    assert root_nodes[0]["children"][0]["name"] == "用户画像"
