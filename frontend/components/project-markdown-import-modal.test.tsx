// 功能: 验证项目级 Markdown 导入弹窗会读取文件并按选定模式调用 API
// 主要测试: locale 文案、文件读取、import_mode 透传
// 数据结构: MarkdownImportFilePayload

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectMarkdownImportModal } from "./project-markdown-import-modal";

const { importMarkdownFilesMock, sendNotificationMock } = vi.hoisted(() => ({
  importMarkdownFilesMock: vi.fn(),
  sendNotificationMock: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  projectAPI: {
    importMarkdownFiles: importMarkdownFilesMock,
  },
}));

vi.mock("@/lib/utils", () => ({
  sendNotification: sendNotificationMock,
}));

describe("ProjectMarkdownImportModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    importMarkdownFilesMock.mockResolvedValue({
      message: "已导入 1 个 Markdown 文件，新增 2 个内容块",
      import_mode: "raw_file",
      file_count: 1,
      root_count: 1,
      blocks_created: 2,
      warning_count: 0,
      warnings: [],
      files: [],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  it("renders japanese locale copy", () => {
    render(
      <ProjectMarkdownImportModal
        open
        projectId="project-1"
        projectLocale="ja-JP"
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("Markdown からインポート")).toBeInTheDocument();
    expect(screen.getByText("見出しツリーとして取り込む")).toBeInTheDocument();
    expect(screen.getByText("原稿ファイルとして取り込む")).toBeInTheDocument();
  });

  it("reads files and submits the selected import mode", async () => {
    const onClose = vi.fn();
    const onImported = vi.fn();
    const { container } = render(
      <ProjectMarkdownImportModal
        open
        projectId="project-1"
        projectLocale="zh-CN"
        onClose={onClose}
        onImported={onImported}
      />,
    );

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const markdownFile = new File(["# 标题\n内容"], "demo.md", { type: "text/markdown" });

    fireEvent.change(fileInput, {
      target: { files: [markdownFile] },
    });

    await waitFor(() => {
      expect(screen.getAllByText("demo.md").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByText("按原文件导入"));
    fireEvent.click(screen.getByRole("button", { name: "导入 Markdown" }));

    await waitFor(() => {
      expect(importMarkdownFilesMock).toHaveBeenCalledWith("project-1", {
        import_mode: "raw_file",
        files: [
          {
            name: "demo.md",
            path: "demo.md",
            content: "# 标题\n内容",
          },
        ],
      });
    });

    expect(sendNotificationMock).toHaveBeenCalledWith("Markdown 导入完成", "已导入 1 个 Markdown 文件，新增 2 个内容块");
    expect(onImported).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
