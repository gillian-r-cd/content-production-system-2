import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContentTreeTemplateSaveModal } from "./content-tree-template-save-modal";

const apiMocks = vi.hoisted(() => ({
  saveProjectTemplate: vi.fn(),
  saveBlockTemplate: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    projectAPI: {
      ...actual.projectAPI,
      saveAsFieldTemplate: apiMocks.saveProjectTemplate,
    },
    blockAPI: {
      ...actual.blockAPI,
      saveAsFieldTemplate: apiMocks.saveBlockTemplate,
    },
  };
});

describe("ContentTreeTemplateSaveModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.saveProjectTemplate.mockResolvedValue({
      template: { name: "项目模板" },
      warnings: [],
    });
    apiMocks.saveBlockTemplate.mockResolvedValue({
      template: { name: "节点模板" },
      warnings: [],
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("submits project template save request", async () => {
    render(
      <ContentTreeTemplateSaveModal
        open
        scope={{ type: "project", projectId: "project-1", label: "测试项目" }}
        onClose={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "保存模板" }));

    await waitFor(() => {
      expect(apiMocks.saveProjectTemplate).toHaveBeenCalledWith("project-1", {
        name: "测试项目 模板",
        description: "",
        category: "通用",
      });
    });
  });

  it("submits block template save request", async () => {
    render(
      <ContentTreeTemplateSaveModal
        open
        scope={{ type: "block", blockId: "block-1", label: "测试节点" }}
        onClose={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "保存模板" }));

    await waitFor(() => {
      expect(apiMocks.saveBlockTemplate).toHaveBeenCalledWith("block-1", {
        name: "测试节点 模板",
        description: "",
        category: "通用",
      });
    });
  });
});
