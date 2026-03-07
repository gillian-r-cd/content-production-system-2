import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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
});
