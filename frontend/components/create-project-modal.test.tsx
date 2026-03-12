// frontend/components/create-project-modal.test.tsx
// 功能: 覆盖创建项目弹窗的 locale 切换链路，确保切换项目语言后会自动切到同 locale 的创作者特质
// 主要测试: CreateProjectModal
// 数据结构: CreatorProfile[] / FieldTemplateLike[]

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CreateProjectModal } from "./create-project-modal";
import { CLIENT_UI_LOCALE_STORAGE_KEY } from "@/lib/project-locale";

const apiMocks = vi.hoisted(() => ({
  listCreatorProfiles: vi.fn(),
  listFieldTemplates: vi.fn(),
  createProject: vi.fn(),
  applyTemplate: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    settingsAPI: {
      ...actual.settingsAPI,
      listCreatorProfiles: apiMocks.listCreatorProfiles,
      listFieldTemplates: apiMocks.listFieldTemplates,
    },
    projectAPI: {
      ...actual.projectAPI,
      create: apiMocks.createProject,
    },
    blockAPI: {
      ...actual.blockAPI,
      applyTemplate: apiMocks.applyTemplate,
    },
  };
});

describe("CreateProjectModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    apiMocks.listCreatorProfiles.mockResolvedValue([
      {
        id: "profile-zh",
        name: "中文特质",
        locale: "zh-CN",
        description: "中文 profile",
        traits: {},
        created_at: "",
      },
      {
        id: "profile-ja",
        name: "日本語プロファイル",
        locale: "ja-JP",
        description: "日本語 profile",
        traits: {},
        created_at: "",
      },
    ]);
    apiMocks.listFieldTemplates.mockResolvedValue([]);
    apiMocks.createProject.mockResolvedValue({ id: "project-1" });
    apiMocks.applyTemplate.mockResolvedValue(undefined);
  });

  afterEach(() => {
    window.localStorage.clear();
    cleanup();
  });

  it("defaults to the persisted japanese ui locale when the modal opens", async () => {
    window.localStorage.setItem(CLIENT_UI_LOCALE_STORAGE_KEY, "ja-JP");

    render(
      <CreateProjectModal
        isOpen
        onClose={vi.fn()}
        onCreated={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("新規コンテンツプロジェクト")).toBeInTheDocument();
    });

    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    expect(selects[0].value).toBe("ja-JP");
    expect(selects[1].value).toBe("profile-ja");
    expect(screen.getByText("日本語プロファイル")).toBeInTheDocument();
  });

  it("switches creator profile selection to the matching locale when project language changes", async () => {
    render(
      <CreateProjectModal
        isOpen
        onClose={vi.fn()}
        onCreated={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("新建内容项目")).toBeInTheDocument();
    });

    await waitFor(() => {
      const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
      expect(selects[1].value).toBe("profile-zh");
    });

    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "ja-JP" },
    });

    await waitFor(() => {
      const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
      expect(selects[0].value).toBe("ja-JP");
      expect(selects[1].value).toBe("profile-ja");
    });

    expect(screen.getByText("日本語プロファイル")).toBeInTheDocument();
    expect(screen.queryByText("中文特质")).not.toBeInTheDocument();
  });

  it("renders japanese template metrics when the persisted ui locale is ja-JP", async () => {
    window.localStorage.setItem(CLIENT_UI_LOCALE_STORAGE_KEY, "ja-JP");
    apiMocks.listCreatorProfiles.mockResolvedValue([
      {
        id: "profile-ja",
        name: "日本語プロファイル",
        locale: "ja-JP",
        description: "日本語 profile",
        traits: {},
        created_at: "",
      },
    ]);
    apiMocks.listFieldTemplates.mockResolvedValue([
      {
        id: "template-ja",
        name: "日本語テンプレート",
        locale: "ja-JP",
        description: "日本語 template",
        root_nodes: [
          {
            template_node_id: "group-node",
            name: "導入",
            block_type: "group",
            children: [
              {
                template_node_id: "field-node",
                name: "概要",
                block_type: "field",
                content: "初期内容",
                children: [],
              },
            ],
          },
        ],
      },
    ]);

    render(
      <CreateProjectModal
        isOpen
        onClose={vi.fn()}
        onCreated={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("新規コンテンツプロジェクト")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("例: 新製品ローンチのコンテンツ企画"), {
      target: { value: "ja-template-project" },
    });
    fireEvent.click(screen.getByRole("button", { name: "次へ" }));

    await waitFor(() => {
      const summaryMatches = screen.getAllByText((_, element) => {
        const content = element?.textContent || "";
        return content.includes("1 個のグループ")
          && content.includes("1 個の内容ブロック")
          && content.includes("1 件の初期内容あり");
      });
      expect(summaryMatches.length).toBeGreaterThan(0);
    });
  });
});
