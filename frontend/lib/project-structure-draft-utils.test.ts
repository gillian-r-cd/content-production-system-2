// frontend/lib/project-structure-draft-utils.test.ts
// 功能: 覆盖自动拆分草稿模板导入工具，确保节点克隆、依赖重映射与内容节点筛选稳定
// 主要测试: cloneTemplateNodesWithNewIds / importTemplateNodes / flattenContentNodes
// 数据结构: TemplateNode[] / FieldTemplate

import { describe, expect, it } from "vitest";
import type { FieldTemplate, TemplateNode } from "./api";
import {
  cloneTemplateNodesWithNewIds,
  flattenContentNodes,
  importTemplateNodes,
} from "./project-structure-draft-utils";

function makeTemplateNodes(): TemplateNode[] {
  return [
    {
      template_node_id: "group-1",
      name: "章节组",
      block_type: "group",
      children: [
        {
          template_node_id: "field-1",
          name: "摘要",
          block_type: "field",
          depends_on_template_node_ids: ["field-2", "external-id"],
          children: [],
        },
        {
          template_node_id: "field-2",
          name: "正文",
          block_type: "field",
          children: [],
        },
      ],
    },
  ];
}

describe("project-structure-draft-utils", () => {
  it("clones template nodes with fresh ids and remaps internal dependencies", () => {
    const createdIds = ["new-group", "new-field-1", "new-field-2"];
    const cloned = cloneTemplateNodesWithNewIds(
      makeTemplateNodes(),
      () => createdIds.shift() || "fallback-id",
    );

    expect(cloned[0].template_node_id).toBe("new-group");
    expect(cloned[0].children?.[0].template_node_id).toBe("new-field-1");
    expect(cloned[0].children?.[1].template_node_id).toBe("new-field-2");
    expect(cloned[0].children?.[0].depends_on_template_node_ids).toEqual(["new-field-2", "external-id"]);

    const original = makeTemplateNodes();
    expect(original[0].template_node_id).toBe("group-1");
    expect(original[0].children?.[0].depends_on_template_node_ids).toEqual(["field-2", "external-id"]);
  });

  it("imports template nodes after existing nodes and keeps current data unchanged when template is empty", () => {
    const currentNodes: TemplateNode[] = [
      {
        template_node_id: "existing-field",
        name: "已有结构",
        block_type: "field",
        children: [],
      },
    ];
    const template: FieldTemplate = {
      id: "template-1",
      name: "文章模板",
      description: "",
      category: "通用",
      schema_version: 2,
      fields: [],
      root_nodes: makeTemplateNodes(),
      created_at: null,
      updated_at: null,
    };

    const imported = importTemplateNodes(currentNodes, template, (() => {
      const ids = ["new-group", "new-field-1", "new-field-2"];
      return () => ids.shift() || "fallback-id";
    })());

    expect(imported).toHaveLength(2);
    expect(imported[0].template_node_id).toBe("existing-field");
    expect(imported[1].template_node_id).toBe("new-group");
    expect(importTemplateNodes(currentNodes, undefined)).toBe(currentNodes);
  });

  it("normalizes legacy types and flattens field nodes for dependency options", () => {
    const nodes: TemplateNode[] = [
      {
        template_node_id: "phase-1",
        name: "阶段",
        block_type: "group",
        children: [
          {
            template_node_id: "group-1",
            name: "分组",
            block_type: "group",
            children: [
              {
                template_node_id: "field-1",
                name: "摘要",
                block_type: "field",
                children: [],
              },
              {
                template_node_id: "proposal-1",
                name: "提议",
                block_type: "field",
                children: [],
              },
            ],
          },
        ],
      },
    ];

    expect(flattenContentNodes(nodes).map((node) => node.template_node_id)).toEqual(["field-1", "proposal-1"]);
  });
});
