// 功能: 覆盖工作台项目管理的批量删除链路，确保删除结果以服务端返回和刷新后的项目列表为准
// 主要测试: WorkspacePage
// 数据结构: Project / projectAPI.batchDelete 响应

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import WorkspacePage from "./page";

const apiMocks = vi.hoisted(() => ({
  listProjects: vi.fn(),
  batchDeleteProjects: vi.fn(),
  requestNotificationPermission: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    projectAPI: {
      ...actual.projectAPI,
      list: apiMocks.listProjects,
      batchDelete: apiMocks.batchDeleteProjects,
      delete: vi.fn(),
      duplicate: vi.fn(),
      createVersion: vi.fn(),
      get: vi.fn(),
      exportProject: vi.fn(),
      importProject: vi.fn(),
    },
    startAllReadyBlocks: vi.fn(),
  };
});

vi.mock("@/lib/utils", async () => {
  const actual = await vi.importActual<typeof import("@/lib/utils")>("@/lib/utils");
  return {
    ...actual,
    requestNotificationPermission: apiMocks.requestNotificationPermission,
  };
});

vi.mock("@/components/layout/workspace-layout", () => ({
  WorkspaceLayout: ({ leftPanel, centerPanel, rightPanel }: { leftPanel: ReactNode; centerPanel: ReactNode; rightPanel: ReactNode }) => (
    <div>
      <div>{leftPanel}</div>
      <div>{centerPanel}</div>
      <div>{rightPanel}</div>
    </div>
  ),
}));

vi.mock("@/components/progress-panel", () => ({
  ProgressPanel: () => <div>progress-panel</div>,
}));

vi.mock("@/components/content-panel", () => ({
  ContentPanel: () => <div>content-panel</div>,
}));

vi.mock("@/components/agent-panel", () => ({
  AgentPanel: () => <div>agent-panel</div>,
}));

vi.mock("@/components/create-project-modal", () => ({
  CreateProjectModal: () => null,
}));

vi.mock("@/components/global-search-modal", () => ({
  GlobalSearchModal: () => null,
}));

vi.mock("@/components/project-auto-split-modal", () => ({
  ProjectAutoSplitModal: () => null,
}));

function buildProject(id: string, name: string) {
  return {
    id,
    name,
    locale: "zh-CN",
    version: 1,
    version_note: "",
    parent_version_id: null,
    creator_profile_id: null,
    current_phase: "intent",
    phase_order: ["intent"],
    phase_status: { intent: "pending" },
    agent_autonomy: {},
    golden_context: {},
    use_deep_research: true,
    use_flexible_architecture: true,
    created_at: "2026-03-12T00:00:00",
    updated_at: "2026-03-12T00:00:00",
  };
}

describe("WorkspacePage batch delete", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const alpha = buildProject("project-alpha", "Alpha");
    const beta = buildProject("project-beta", "Beta");

    apiMocks.listProjects
      .mockResolvedValueOnce([alpha, beta])
      .mockResolvedValueOnce([alpha, beta])
      .mockResolvedValueOnce([beta]);
    apiMocks.batchDeleteProjects.mockResolvedValue({
      ok: true,
      deleted_ids: ["project-alpha"],
      deleted_count: 1,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    cleanup();
  });

  it("refreshes the project list from the backend after batch delete and switches away from a deleted current project", async () => {
    render(<WorkspacePage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Alpha \(v1\)/ })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Alpha \(v1\)/ }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "批量管理" })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "批量管理" }));

    fireEvent.click(screen.getByText("Alpha"));

    const deleteButton = screen.getByRole("button", { name: "批量删除" });
    await waitFor(() => {
      expect(deleteButton).not.toBeDisabled();
    });
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(apiMocks.batchDeleteProjects).toHaveBeenCalledWith(["project-alpha"]);
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Beta \(v1\)/ })).toBeInTheDocument();
    });

    expect(apiMocks.listProjects).toHaveBeenCalledTimes(3);
  });
});
