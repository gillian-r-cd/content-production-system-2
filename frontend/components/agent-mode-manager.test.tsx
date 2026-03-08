import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentModeManager } from "./agent-mode-manager";

const apiMocks = vi.hoisted(() => ({
  list: vi.fn(),
  listTemplates: vi.fn(),
  importTemplates: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  delete: vi.fn(),
}));

const notifyMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    modesAPI: {
      ...actual.modesAPI,
      list: apiMocks.list,
      listTemplates: apiMocks.listTemplates,
      importTemplates: apiMocks.importTemplates,
      create: apiMocks.create,
      update: apiMocks.update,
      delete: apiMocks.delete,
    },
  };
});

vi.mock("@/lib/utils", async () => {
  const actual = await vi.importActual<typeof import("@/lib/utils")>("@/lib/utils");
  return {
    ...actual,
    sendNotification: notifyMock,
  };
});

describe("AgentModeManager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows empty state and imports templates into project roles", async () => {
    apiMocks.list
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: "mode-1",
          name: "mode_1",
          project_id: "project-1",
          display_name: "助手",
          description: "",
          system_prompt: "你是助手",
          icon: "A",
          is_system: false,
          is_template: false,
          sort_order: 0,
        },
      ]);
    apiMocks.listTemplates.mockResolvedValue([
      {
        id: "tpl-1",
        name: "assistant",
        project_id: null,
        display_name: "助手",
        description: "",
        system_prompt: "你是助手",
        icon: "A",
        is_system: true,
        is_template: true,
        sort_order: 0,
      },
    ]);
    apiMocks.importTemplates.mockResolvedValue({
      imported: [{ id: "mode-1" }],
      skipped_count: 0,
    });

    const onSelectMode = vi.fn();

    render(
      <AgentModeManager
        projectId="project-1"
        activeModeId={null}
        onSelectMode={onSelectMode}
        onClose={() => {}}
      />,
    );

    expect(await screen.findByText("当前项目还没有角色")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "导入默认模板" }));

    await waitFor(() => {
      expect(apiMocks.importTemplates).toHaveBeenCalledWith("project-1");
    });
    await waitFor(() => {
      expect(onSelectMode).toHaveBeenCalledWith("mode-1");
    });
  });

  it("creates a role with optional empty description", async () => {
    apiMocks.list.mockResolvedValue([]);
    apiMocks.listTemplates.mockResolvedValue([]);
    apiMocks.create.mockResolvedValue({
      id: "mode-2",
      name: "mode_2",
      project_id: "project-1",
      display_name: "增长教练",
      description: "",
      system_prompt: "你是增长教练",
      icon: "G",
      is_system: false,
      is_template: false,
      sort_order: 0,
    });

    render(
      <AgentModeManager
        projectId="project-1"
        activeModeId={null}
        onSelectMode={() => {}}
        onClose={() => {}}
      />,
    );

    fireEvent.change(await screen.findByPlaceholderText("例如：增长教练"), {
      target: { value: "增长教练" },
    });
    fireEvent.change(screen.getByPlaceholderText("🤖"), {
      target: { value: "G" },
    });
    fireEvent.change(
      screen.getByPlaceholderText("定义这个角色如何理解任务、如何说话、应该优先关注什么。"),
      { target: { value: "你是增长教练" } },
    );

    fireEvent.click(screen.getByRole("button", { name: "创建角色" }));

    await waitFor(() => {
      expect(apiMocks.create).toHaveBeenCalledWith({
        project_id: "project-1",
        display_name: "增长教练",
        description: "",
        icon: "G",
        system_prompt: "你是增长教练",
      });
    });
  });

  it("keeps import action clickable when template list is empty", async () => {
    apiMocks.list
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: "mode-legacy",
          name: "mode_legacy",
          project_id: "project-1",
          display_name: "助手",
          description: "",
          system_prompt: "你是助手",
          icon: "A",
          is_system: false,
          is_template: false,
          sort_order: 0,
        },
      ]);
    apiMocks.listTemplates.mockResolvedValue([]);
    apiMocks.importTemplates.mockResolvedValue({
      imported: [{ id: "mode-legacy" }],
      skipped_count: 0,
    });

    render(
      <AgentModeManager
        projectId="project-1"
        activeModeId={null}
        onSelectMode={() => {}}
        onClose={() => {}}
      />,
    );

    const importButton = await screen.findByRole("button", { name: "导入默认模板" });
    expect(importButton).toBeEnabled();

    fireEvent.click(importButton);

    await waitFor(() => {
      expect(apiMocks.importTemplates).toHaveBeenCalledWith("project-1");
    });
  });
});
