import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { blockAPI } from "@/lib/api";
import { ProgressPanel } from "./progress-panel";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    blockAPI: {
      ...actual.blockAPI,
      getProjectBlocks: vi.fn().mockResolvedValue({ blocks: [], total_count: 0, project_id: "project-1" }),
    },
    projectAPI: {
      ...actual.projectAPI,
      exportProjectMarkdown: vi.fn(),
      exportProject: vi.fn(),
      saveAsFieldTemplate: vi.fn(),
    },
    runAutoTriggerChain: vi.fn().mockResolvedValue(undefined),
  };
});

vi.mock("./block-tree", () => ({
  default: () => null,
}));

describe("ProgressPanel", () => {
  afterEach(() => {
    cleanup();
  });

  it("explains ready semantics next to the start-all button", async () => {
    render(
      <ProgressPanel
        project={{
          id: "project-1",
          name: "测试项目",
          version: 1,
          version_note: "",
          parent_version_id: null,
          creator_profile_id: null,
          current_phase: "",
          phase_order: [],
          phase_status: {},
          agent_autonomy: {},
          golden_context: {},
          use_deep_research: false,
          created_at: "",
          updated_at: "",
        }}
      />,
    );

    expect(screen.getByRole("button", { name: "开始所有已就绪内容块" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "项目操作菜单" })).toBeInTheDocument();
    expect(screen.getByText("已就绪 = 依赖完成，且所有必答生成前提问已回答。")).toBeInTheDocument();
  });

  it("opens save-template modal from project menu", async () => {
    render(
      <ProgressPanel
        project={{
          id: "project-1",
          name: "测试项目",
          version: 1,
          version_note: "",
          parent_version_id: null,
          creator_profile_id: null,
          current_phase: "",
          phase_order: [],
          phase_status: {},
          agent_autonomy: {},
          golden_context: {},
          use_deep_research: false,
          created_at: "",
          updated_at: "",
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "项目操作菜单" }));
    fireEvent.click(screen.getByRole("button", { name: "保存为内容块模板" }));

    expect(screen.getByRole("heading", { name: "保存为内容块模板" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("测试项目 模板")).toBeInTheDocument();
  });

  it("publishes a fresh snapshot when a block changes with the same content length", async () => {
    const onBlocksChange = vi.fn();
    const getProjectBlocksMock = vi.mocked(blockAPI.getProjectBlocks);

    getProjectBlocksMock
      .mockResolvedValueOnce({
        project_id: "project-1",
        total_count: 1,
        blocks: [{
          id: "block-1",
          project_id: "project-1",
          parent_id: null,
          name: "主标题",
          block_type: "field",
          depth: 0,
          order_index: 0,
          content: "AB",
          status: "completed",
          ai_prompt: "",
          constraints: {},
          depends_on: [],
          special_handler: null,
          need_review: false,
          auto_generate: false,
          is_collapsed: false,
          model_override: null,
          children: [],
          created_at: "2026-03-13T00:00:00",
          updated_at: "2026-03-13T00:00:00",
        }],
      })
      .mockResolvedValueOnce({
        project_id: "project-1",
        total_count: 1,
        blocks: [{
          id: "block-1",
          project_id: "project-1",
          parent_id: null,
          name: "主标题",
          block_type: "field",
          depth: 0,
          order_index: 0,
          content: "CD",
          status: "completed",
          ai_prompt: "",
          constraints: {},
          depends_on: [],
          special_handler: null,
          need_review: false,
          auto_generate: false,
          is_collapsed: false,
          model_override: null,
          children: [],
          created_at: "2026-03-13T00:00:00",
          updated_at: "2026-03-13T00:00:01",
        }],
      });

    const project = {
      id: "project-1",
      name: "测试项目",
      version: 1,
      version_note: "",
      parent_version_id: null,
      creator_profile_id: null,
      current_phase: "",
      phase_order: [],
      phase_status: {},
      agent_autonomy: {},
      golden_context: {},
      use_deep_research: false,
      created_at: "",
      updated_at: "",
    };

    const { rerender } = render(
      <ProgressPanel
        project={project}
        onBlocksChange={onBlocksChange}
      />,
    );

    await waitFor(() => {
      expect(onBlocksChange).toHaveBeenCalledTimes(1);
    });
    expect(onBlocksChange.mock.calls[0][0].flat[0].content).toBe("AB");

    rerender(
      <ProgressPanel
        project={project}
        blocksRefreshKey={1}
        onBlocksChange={onBlocksChange}
      />,
    );

    await waitFor(() => {
      expect(onBlocksChange).toHaveBeenCalledTimes(2);
    });
    expect(onBlocksChange.mock.calls[1][0].flat[0].content).toBe("CD");
    expect(onBlocksChange.mock.calls[1][0].syncToken).not.toBe(onBlocksChange.mock.calls[0][0].syncToken);
  });
});
