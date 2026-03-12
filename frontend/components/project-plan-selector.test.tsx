// frontend/components/project-plan-selector.test.tsx
// 功能: 覆盖编排方案组件的关键交互，验证 chunk 选择和模板导入回调都按预期触发
// 主要测试: ProjectPlanSelector
// 数据结构: ProjectStructurePlan[] / ProjectStructureChunk[] / FieldTemplate[]

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FieldTemplate, ProjectStructureChunk, ProjectStructurePlan } from "@/lib/api";
import { ProjectPlanSelector } from "./project-plan-selector";

const templateTreeEditorSpy = vi.fn();
vi.mock("./settings/template-tree-editor", () => ({
  TemplateTreeEditor: (props: unknown) => {
    templateTreeEditorSpy(props);
    return <div>mock-template-tree-editor</div>;
  },
}));

function makePlan(): ProjectStructurePlan {
  return {
    plan_id: "plan-1",
    name: "文章方案",
    target_chunk_ids: ["chunk-1"],
    root_nodes: [],
  };
}

function makeChunks(): ProjectStructureChunk[] {
  return [
    { chunk_id: "chunk-1", title: "第一段", content: "alpha", order_index: 0 },
    { chunk_id: "chunk-2", title: "第二段", content: "beta", order_index: 1 },
  ];
}

function makeTemplates(): FieldTemplate[] {
  return [
    {
      id: "template-1",
      name: "摘要模板",
      description: "",
      category: "content",
      schema_version: 1,
      fields: [],
      root_nodes: [
        {
          template_node_id: "node-1",
          name: "摘要",
          block_type: "field",
          children: [],
        },
      ],
      created_at: null,
    },
  ];
}

describe("ProjectPlanSelector", () => {
  afterEach(() => {
    cleanup();
    templateTreeEditorSpy.mockClear();
  });

  it("patches selected chunk ids when chunk checkbox changes", () => {
    const onPatchPlan = vi.fn();

    render(
      <ProjectPlanSelector
        plans={[makePlan()]}
        chunks={makeChunks()}
        availableModels={[]}
        fieldTemplates={makeTemplates()}
        sharedNodeOptions={[]}
        projectBlockOptions={[]}
        onAddPlan={() => {}}
        onPatchPlan={onPatchPlan}
        onRemovePlan={() => {}}
        onImportTemplate={() => {}}
      />,
    );

    const secondChunk = screen.getByLabelText("第二段");
    fireEvent.click(secondChunk);

    expect(onPatchPlan).toHaveBeenCalledWith("plan-1", {
      target_chunk_ids: ["chunk-1", "chunk-2"],
    });
  });

  it("imports selected field template into the current plan", () => {
    const onImportTemplate = vi.fn();

    render(
      <ProjectPlanSelector
        plans={[makePlan()]}
        chunks={makeChunks()}
        availableModels={[]}
        fieldTemplates={makeTemplates()}
        sharedNodeOptions={[]}
        projectBlockOptions={[]}
        onAddPlan={() => {}}
        onPatchPlan={() => {}}
        onRemovePlan={() => {}}
        onImportTemplate={onImportTemplate}
      />,
    );

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "template-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "导入模板结构" }));

    expect(onImportTemplate).toHaveBeenCalledWith("plan-1", makeTemplates()[0]);
  });

  it("passes group-field only create types to tree editor", () => {
    render(
      <ProjectPlanSelector
        plans={[makePlan()]}
        chunks={makeChunks()}
        availableModels={[]}
        fieldTemplates={makeTemplates()}
        sharedNodeOptions={[]}
        projectBlockOptions={[]}
        onAddPlan={() => {}}
        onPatchPlan={() => {}}
        onRemovePlan={() => {}}
        onImportTemplate={() => {}}
      />,
    );

    expect(templateTreeEditorSpy).toHaveBeenCalled();
    const firstCall = templateTreeEditorSpy.mock.calls[0][0] as { topLevelCreateTypes?: string[] };
    expect(firstCall.topLevelCreateTypes).toEqual(["field", "group"]);
  });

  it("renders japanese copy when project locale is ja-JP", () => {
    render(
      <ProjectPlanSelector
        plans={[makePlan()]}
        chunks={makeChunks()}
        projectLocale="ja-JP"
        availableModels={[]}
        fieldTemplates={makeTemplates()}
        sharedNodeOptions={[]}
        projectBlockOptions={[]}
        onAddPlan={() => {}}
        onPatchPlan={() => {}}
        onRemovePlan={() => {}}
        onImportTemplate={() => {}}
      />,
    );

    expect(screen.getByText("編成プラン")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+ 新しい編成プラン" })).toBeInTheDocument();
  });
});
