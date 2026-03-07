import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { blockAPI, settingsAPI } from "@/lib/api";
import BlockTree from "./block-tree";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    blockAPI: {
      ...actual.blockAPI,
      create: vi.fn(),
      update: vi.fn(),
      move: vi.fn(),
      undo: vi.fn(),
      applyTemplate: vi.fn(),
      delete: vi.fn(),
      duplicate: vi.fn(),
      generate: vi.fn(),
      exportMarkdown: vi.fn(),
      exportJson: vi.fn(),
      saveAsFieldTemplate: vi.fn(),
    },
    projectAPI: {
      ...actual.projectAPI,
      importContentTreeJson: vi.fn(),
      exportProjectMarkdown: vi.fn(),
      exportProject: vi.fn(),
      saveAsFieldTemplate: vi.fn(),
    },
    settingsAPI: {
      ...actual.settingsAPI,
      listFieldTemplates: vi.fn().mockResolvedValue([]),
    },
  };
});

describe("BlockTree", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows the project-level JSON import entry and opens the modal", () => {
    render(
      <BlockTree
        blocks={[]}
        projectId="project-1"
        selectedBlockId={null}
        onBlocksChange={() => {}}
        editable
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "从 JSON 导入" }));

    expect(screen.getByRole("heading", { name: "从 JSON 导入" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "追加导入到当前项目" })).toBeInTheDocument();
  });

  it("opens the project-level template modal immediately in an empty project", () => {
    render(
      <BlockTree
        blocks={[]}
        projectId="project-1"
        selectedBlockId={null}
        onBlocksChange={() => {}}
        editable
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "从模板添加" }));

    expect(settingsAPI.listFieldTemplates).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("heading", { name: "从模板添加内容块" })).toBeInTheDocument();
  });

  it("keeps the project-level template modal mounted across empty-to-non-empty rerenders", () => {
    const { rerender } = render(
      <BlockTree
        blocks={[]}
        projectId="project-1"
        selectedBlockId={null}
        onBlocksChange={() => {}}
        editable
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "从模板添加" }));
    expect(screen.getByRole("heading", { name: "从模板添加内容块" })).toBeInTheDocument();

    rerender(
      <BlockTree
        blocks={[
          {
            id: "block-1",
            project_id: "project-1",
            parent_id: null,
            name: "新内容块",
            block_type: "field",
            depth: 0,
            order_index: 0,
            content: "",
            status: "pending",
            ai_prompt: "",
            constraints: {},
            pre_questions: [],
            pre_answers: {},
            depends_on: [],
            special_handler: null,
            need_review: true,
            auto_generate: false,
            is_collapsed: false,
            model_override: null,
            children: [],
            created_at: "",
            updated_at: "",
          },
        ]}
        projectId="project-1"
        selectedBlockId={null}
        onBlocksChange={() => {}}
        editable
      />,
    );

    expect(screen.getByRole("heading", { name: "从模板添加内容块" })).toBeInTheDocument();
  });

  it("does not open the project-level template modal when adding a top-level field in an empty project", () => {
    render(
      <BlockTree
        blocks={[]}
        projectId="project-1"
        selectedBlockId={null}
        onBlocksChange={() => {}}
        editable
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "添加内容块" }));

    expect(blockAPI.create).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("heading", { name: "从模板添加内容块" })).not.toBeInTheDocument();
  });

  it("opens save-template modal from block action menu", () => {
    render(
      <BlockTree
        blocks={[
          {
            id: "block-1",
            project_id: "project-1",
            parent_id: null,
            name: "场景设计",
            block_type: "group",
            depth: 0,
            order_index: 0,
            content: "",
            status: "pending",
            ai_prompt: "",
            constraints: {},
            pre_questions: [],
            pre_answers: {},
            depends_on: [],
            special_handler: null,
            need_review: true,
            auto_generate: false,
            is_collapsed: false,
            model_override: null,
            children: [],
            created_at: "",
            updated_at: "",
          },
        ]}
        projectId="project-1"
        selectedBlockId={null}
        onBlocksChange={() => {}}
        editable
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "场景设计 操作菜单" }));
    fireEvent.click(screen.getByRole("button", { name: "保存为内容块模板" }));

    expect(screen.getByRole("heading", { name: "保存为内容块模板" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("场景设计 模板")).toBeInTheDocument();
  });
});
