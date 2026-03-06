// frontend/components/project-structure-draft-editor.test.tsx
// 功能: 覆盖草稿编辑器的共享/聚合模板导入主链，确保模板结构会写回统一 payload
// 主要测试: ProjectStructureDraftEditor
// 数据结构: ProjectStructureDraftPayload / FieldTemplate / TemplateNode

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FieldTemplate, ProjectStructureDraftPayload } from "@/lib/api";
import { ProjectStructureDraftEditor } from "./project-structure-draft-editor";

vi.mock("./settings/template-tree-editor", () => ({
  TemplateTreeEditor: () => <div>mock-template-tree-editor</div>,
}));

function makePayload(): ProjectStructureDraftPayload {
  return {
    chunks: [
      { chunk_id: "chunk-1", title: "第一段", content: "alpha", order_index: 0 },
    ],
    plans: [
      {
        plan_id: "plan-1",
        name: "方案一",
        target_chunk_ids: ["chunk-1"],
        root_nodes: [],
      },
    ],
    shared_root_nodes: [],
    aggregate_root_nodes: [],
    ui_state: {},
  };
}

function makeTemplates(): FieldTemplate[] {
  return [
    {
      id: "template-1",
      name: "结构模板",
      description: "",
      category: "content",
      schema_version: 1,
      fields: [],
      root_nodes: [
        {
          template_node_id: "field-a",
          name: "摘要",
          block_type: "field",
          depends_on_template_node_ids: ["field-b"],
          children: [],
        },
        {
          template_node_id: "field-b",
          name: "正文",
          block_type: "field",
          children: [],
        },
      ],
      created_at: null,
    },
  ];
}

describe("ProjectStructureDraftEditor", () => {
  beforeEach(() => {
    vi.spyOn(crypto, "randomUUID")
      .mockReturnValueOnce("shared-field-a")
      .mockReturnValueOnce("shared-field-b")
      .mockReturnValueOnce("aggregate-field-a")
      .mockReturnValueOnce("aggregate-field-b");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("imports shared and aggregate templates into payload with fresh ids", () => {
    const onChange = vi.fn();

    render(
      <ProjectStructureDraftEditor
        payload={makePayload()}
        availableModels={[]}
        fieldTemplates={makeTemplates()}
        projectBlocks={[]}
        onChange={onChange}
      />,
    );

    const comboboxes = screen.getAllByRole("combobox");
    const buttons = screen.getAllByRole("button", { name: "导入模板结构" });

    fireEvent.change(comboboxes[1], { target: { value: "template-1" } });
    fireEvent.click(buttons[1]);

    const sharedPayload = onChange.mock.calls[0][0] as ProjectStructureDraftPayload;
    expect(sharedPayload.shared_root_nodes).toHaveLength(2);
    expect(sharedPayload.shared_root_nodes[0].template_node_id).toBe("shared-field-a");
    expect(sharedPayload.shared_root_nodes[0].depends_on_template_node_ids).toEqual(["shared-field-b"]);

    fireEvent.change(comboboxes[2], { target: { value: "template-1" } });
    fireEvent.click(buttons[2]);

    const aggregatePayload = onChange.mock.calls[1][0] as ProjectStructureDraftPayload;
    expect(aggregatePayload.aggregate_root_nodes).toHaveLength(2);
    expect(aggregatePayload.aggregate_root_nodes[0].template_node_id).toBe("aggregate-field-a");
    expect(aggregatePayload.aggregate_root_nodes[0].depends_on_template_node_ids).toEqual(["aggregate-field-b"]);
  });
});
