// frontend/components/project-auto-split-modal.test.tsx
// 功能: 覆盖自动拆分弹窗的主链约束，验证校验前禁用应用、校验后展示预览、编辑后重新失效
// 主要测试: ProjectAutoSplitModal
// 数据结构: ProjectStructureDraft / TemplateNode

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectAutoSplitModal } from "./project-auto-split-modal";

const apiMocks = vi.hoisted(() => ({
  getAutoSplitDraft: vi.fn(),
  updateAutoSplitDraft: vi.fn(),
  splitAutoSplitDraft: vi.fn(),
  validateAutoSplitDraft: vi.fn(),
  applyAutoSplitDraft: vi.fn(),
  listModels: vi.fn(),
  listFieldTemplates: vi.fn(),
  getProjectBlocks: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    blockAPI: {
      ...actual.blockAPI,
      getProjectBlocks: apiMocks.getProjectBlocks,
    },
    modelsAPI: {
      ...actual.modelsAPI,
      list: apiMocks.listModels,
    },
    projectStructureDraftAPI: {
      getAutoSplitDraft: apiMocks.getAutoSplitDraft,
      updateAutoSplitDraft: apiMocks.updateAutoSplitDraft,
      splitAutoSplitDraft: apiMocks.splitAutoSplitDraft,
      validateAutoSplitDraft: apiMocks.validateAutoSplitDraft,
      applyAutoSplitDraft: apiMocks.applyAutoSplitDraft,
    },
    settingsAPI: {
      ...actual.settingsAPI,
      listFieldTemplates: apiMocks.listFieldTemplates,
    },
  };
});

vi.mock("./project-split-chunk-list", () => ({
  ProjectSplitChunkList: ({
    payload,
    onChange,
  }: {
    payload: {
      chunks: Array<{ chunk_id: string; title: string; content: string; order_index: number }>;
      plans: unknown[];
      shared_root_nodes: unknown[];
      aggregate_root_nodes: unknown[];
      ui_state: Record<string, unknown>;
    };
    onChange: (payload: unknown) => void;
  }) => (
    <button
      type="button"
      onClick={() => {
        const first = payload.chunks[0];
        onChange({
          ...payload,
          chunks: [
            { ...first, title: `${first.title}（已编辑）` },
            ...payload.chunks.slice(1),
          ],
        });
      }}
    >
      mock-edit-chunks
    </button>
  ),
}));

vi.mock("./project-structure-draft-editor", () => ({
  ProjectStructureDraftEditor: () => <div>mock-structure-editor</div>,
}));

function makeDraft(status: "draft" | "validated" | "applied" = "draft") {
  return {
    id: "draft-1",
    project_id: "project-1",
    draft_type: "auto_split" as const,
    name: "自动拆分内容",
    status,
    source_text: "alpha\n\nbeta",
    split_config: {
      mode: "count" as const,
      target_count: 2,
      overlap_chars: 0,
      title_prefix: "",
      rule_prompt: "",
      max_chars_per_chunk: 1200,
    },
    draft_payload: {
      chunks: [
        { chunk_id: "chunk-1", title: "片段一", content: "alpha", order_index: 0 },
      ],
      plans: [],
      shared_root_nodes: [],
      aggregate_root_nodes: [],
      ui_state: {},
    },
    validation_errors: [],
    last_validated_at: status === "draft" ? null : "2026-03-06T14:00:00",
    apply_count: 0,
    last_applied_at: null,
    created_at: null,
    updated_at: null,
  };
}

describe("ProjectAutoSplitModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.listModels.mockResolvedValue({
      models: [],
      current_default: { main: "", mini: "" },
      env_provider: "",
    });
    apiMocks.listFieldTemplates.mockResolvedValue([]);
    apiMocks.getProjectBlocks.mockResolvedValue({
      project_id: "project-1",
      blocks: [],
      total_count: 0,
    });
    apiMocks.updateAutoSplitDraft.mockImplementation(async (_projectId: string, data: { draft_payload?: unknown }) => ({
      ...makeDraft("draft"),
      draft_payload: data.draft_payload ?? makeDraft("draft").draft_payload,
    }));
    apiMocks.applyAutoSplitDraft.mockResolvedValue({
      message: "ok",
      blocks_created: 3,
      summary: {},
      draft: makeDraft("applied"),
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("disables apply until validation succeeds and shows preview after validate", async () => {
    apiMocks.getAutoSplitDraft.mockResolvedValue(makeDraft("draft"));
    apiMocks.validateAutoSplitDraft.mockResolvedValue({
      draft: makeDraft("validated"),
      validation_errors: [],
      summary: { chunk_count: 1, compiled_node_count: 2 },
      preview_root_nodes: [
        {
          template_node_id: "node-1",
          name: "批次组",
          block_type: "group",
          children: [
            {
              template_node_id: "node-2",
              name: "摘要",
              block_type: "field",
              children: [],
            },
          ],
        },
      ],
    });

    render(
      <ProjectAutoSplitModal open projectId="project-1" onClose={() => {}} onApplied={() => {}} />
    );

    const applyButton = await screen.findByRole("button", { name: "应用到项目" });
    expect(applyButton).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "校验" }));

    await screen.findByText("应用前结构预览");
    expect(screen.getByText("分组 / 批次组 (1)")).toBeInTheDocument();
    expect(screen.getByText("内容块 / 摘要")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "应用到项目" })).toBeEnabled();
  });

  it("invalidates validated state after local edits and blocks apply again", async () => {
    apiMocks.getAutoSplitDraft.mockResolvedValue(makeDraft("validated"));

    render(
      <ProjectAutoSplitModal open projectId="project-1" onClose={() => {}} onApplied={() => {}} />
    );

    const applyButton = await screen.findByRole("button", { name: "应用到项目" });
    expect(applyButton).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "mock-edit-chunks" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "应用到项目" })).toBeDisabled();
    });
    expect(screen.getByText("当前已有 1 个 chunk，修改后需先重新校验")).toBeInTheDocument();
  });

  it("applies a validated draft without re-saving it first", async () => {
    const onClose = vi.fn();
    const onApplied = vi.fn();
    apiMocks.getAutoSplitDraft.mockResolvedValue(makeDraft("validated"));

    render(
      <ProjectAutoSplitModal open projectId="project-1" onClose={onClose} onApplied={onApplied} />
    );

    const applyButton = await screen.findByRole("button", { name: "应用到项目" });
    expect(applyButton).toBeEnabled();

    fireEvent.click(applyButton);

    await waitFor(() => {
      expect(apiMocks.applyAutoSplitDraft).toHaveBeenCalledWith("project-1");
    });
    expect(apiMocks.updateAutoSplitDraft).not.toHaveBeenCalled();
    expect(onApplied).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
