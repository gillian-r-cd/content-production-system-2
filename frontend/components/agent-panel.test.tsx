import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentPanel } from "./agent-panel";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const apiMocks = vi.hoisted(() => ({
  listModes: vi.fn(),
  listTemplates: vi.fn(),
  listConversations: vi.fn(),
  createConversation: vi.fn(),
  getConversationMessages: vi.fn(),
  getAgentSettings: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    modesAPI: {
      ...actual.modesAPI,
      list: apiMocks.listModes,
      listTemplates: apiMocks.listTemplates,
    },
    agentAPI: {
      ...actual.agentAPI,
      listConversations: apiMocks.listConversations,
      createConversation: apiMocks.createConversation,
      getConversationMessages: apiMocks.getConversationMessages,
    },
    settingsAPI: {
      ...actual.settingsAPI,
      getAgentSettings: apiMocks.getAgentSettings,
    },
  };
});

vi.mock("@/lib/utils", async () => {
  const actual = await vi.importActual<typeof import("@/lib/utils")>("@/lib/utils");
  return {
    ...actual,
    requestNotificationPermission: vi.fn(),
    sendNotification: vi.fn(),
  };
});

describe("AgentPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    HTMLElement.prototype.scrollIntoView = vi.fn();
    apiMocks.listConversations.mockResolvedValue([]);
    apiMocks.listTemplates.mockResolvedValue([]);
    apiMocks.createConversation.mockResolvedValue({
      id: "conv-1",
      project_id: "project-1",
      mode_id: "mode-1",
      mode: "助手",
      title: "新会话",
      status: "active",
      bootstrap_policy: "memory_only",
      last_message_at: null,
      message_count: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    apiMocks.getConversationMessages.mockResolvedValue([]);
    apiMocks.getAgentSettings.mockResolvedValue({ tools: [] });
  });

  afterEach(() => {
    cleanup();
  });

  it("does not show role manager empty state while modes are still loading", async () => {
    const modesDeferred = deferred<Array<{
      id: string;
      name: string;
      project_id: string | null;
      display_name: string;
      description: string;
      system_prompt: string;
      icon: string;
      is_system: boolean;
      is_template: boolean;
      sort_order: number;
    }>>();
    apiMocks.listModes.mockReturnValue(modesDeferred.promise);

    render(<AgentPanel projectId="project-1" allBlocks={[]} />);

    expect(screen.getByText("AI Agent")).toBeInTheDocument();
    expect(screen.queryByText("当前项目还没有角色")).not.toBeInTheDocument();

    modesDeferred.resolve([
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

    await waitFor(() => {
      expect(screen.getByText("助手")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(apiMocks.listModes).toHaveBeenCalledTimes(1);
    });
  });

  it("shows inline empty state first and opens manager as overlay on demand", async () => {
    apiMocks.listModes.mockResolvedValue([]);

    render(<AgentPanel projectId="project-1" allBlocks={[]} />);

    expect(await screen.findByText("当前项目还没有 Agent 角色")).toBeInTheDocument();
    expect(screen.queryByText("当前项目还没有角色")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "配置角色" }));

    expect(await screen.findByText("角色名称和提示词由当前项目维护，简介为可选项")).toBeInTheDocument();
    expect(await screen.findByText("当前项目还没有角色")).toBeInTheDocument();
  });

  it("renders japanese empty state when project locale is ja-JP", async () => {
    apiMocks.listModes.mockResolvedValue([]);

    render(<AgentPanel projectId="project-1" projectLocale="ja-JP" allBlocks={[]} />);

    expect(await screen.findByText("このプロジェクトにはまだ Agent 役割がありません")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "役割を設定" })).toBeInTheDocument();
  });
});
