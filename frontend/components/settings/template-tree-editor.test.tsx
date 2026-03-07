// frontend/components/settings/template-tree-editor.test.tsx
// 功能: 覆盖模板树编辑器里的当前 chunk 依赖开关，确保它是逐字段可选而非方案级默认
// 主要测试: TemplateTreeEditor
// 数据结构: TemplateNode[] / DraftDependencyOption[]

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DraftDependencyOption, TemplateNode } from "@/lib/api";
import { TemplateTreeEditor } from "./template-tree-editor";

function makeNodes(): TemplateNode[] {
  return [
    {
      template_node_id: "field-1",
      name: "摘要",
      block_type: "field",
      ai_prompt: "",
      content: "",
      pre_questions: [],
      depends_on_template_node_ids: [],
      constraints: {},
      special_handler: null,
      need_review: true,
      auto_generate: false,
      is_collapsed: false,
      model_override: null,
      draft_dependency_refs: [],
      children: [],
    },
  ];
}

function makeOptions(): DraftDependencyOption[] {
  return [
    {
      id: "current-source",
      label: "当前 chunk 的源内容块",
      ref: { ref_type: "chunk_source", chunk_id: "current" },
    },
    {
      id: "project-1",
      label: "项目 / 已有内容块",
      ref: { ref_type: "project_block", block_id: "project-block-1" },
    },
  ];
}

describe("TemplateTreeEditor", () => {
  afterEach(() => {
    cleanup();
  });

  it("treats current chunk dependency as a per-node toggle", () => {
    const onChange = vi.fn();

    render(
      <TemplateTreeEditor
        nodes={makeNodes()}
        onChange={onChange}
        availableModels={[]}
        topLevelCreateTypes={["field"]}
        externalDependencyOptions={makeOptions()}
      />,
    );

    const currentChunkToggle = screen.getByLabelText("依赖当前 chunk 的源内容块");
    fireEvent.click(currentChunkToggle);

    const nextNodes = onChange.mock.calls[0][0] as TemplateNode[];
    expect(nextNodes[0].draft_dependency_refs).toEqual([
      { ref_type: "chunk_source", chunk_id: "current" },
    ]);
    expect(screen.getByText("项目 / 已有内容块")).toBeInTheDocument();
    expect(screen.getAllByText("当前 chunk 依赖")).toHaveLength(1);
  });
});
