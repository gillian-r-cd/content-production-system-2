import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ContentTreeActionItems } from "./content-tree-action-items";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    blockAPI: {
      ...actual.blockAPI,
      exportMarkdown: vi.fn().mockResolvedValue({ markdown: "# title", filename: "title.md" }),
      exportJson: vi.fn().mockResolvedValue({ ok: true }),
      saveAsFieldTemplate: vi.fn(),
    },
    projectAPI: {
      ...actual.projectAPI,
      exportProjectMarkdown: vi.fn().mockResolvedValue({ markdown: "# title", filename: "title.md" }),
      exportProject: vi.fn().mockResolvedValue({ ok: true }),
      saveAsFieldTemplate: vi.fn(),
    },
  };
});

describe("ContentTreeActionItems", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders download submenu as fixed overlay to avoid sidebar clipping", () => {
    render(
      <div>
        <ContentTreeActionItems scope={{ type: "block", blockId: "block-1", label: "测试块" }} />
      </div>,
    );

    const downloadButton = screen.getByRole("button", { name: "下载" });
    vi.spyOn(downloadButton, "getBoundingClientRect").mockReturnValue({
      x: 240,
      y: 120,
      width: 200,
      height: 40,
      top: 120,
      right: 440,
      bottom: 160,
      left: 240,
      toJSON: () => ({}),
    });

    fireEvent.click(downloadButton);

    const markdownButton = screen.getByRole("button", { name: "Markdown" });
    const submenu = markdownButton.parentElement;
    expect(submenu).not.toBeNull();
    expect(submenu?.className).toContain("fixed");
  });

  it("renders japanese action labels when project locale is ja-JP", () => {
    render(
      <div>
        <ContentTreeActionItems
          scope={{ type: "block", blockId: "block-1", label: "テストブロック" }}
          projectLocale="ja-JP"
        />
      </div>,
    );

    expect(screen.getByRole("button", { name: "Markdown としてコピー" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ダウンロード" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "内容ブロックテンプレートとして保存" })).toBeInTheDocument();
  });
});
