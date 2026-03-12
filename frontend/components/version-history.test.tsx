import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLIENT_UI_LOCALE_STORAGE_KEY } from "@/lib/project-locale";
import { VersionHistoryButton } from "./version-history";

const apiMocks = vi.hoisted(() => ({
  listVersions: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    versionAPI: {
      ...actual.versionAPI,
      list: apiMocks.listVersions,
      rollback: vi.fn(),
    },
  };
});

describe("VersionHistoryButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.localStorage.setItem(CLIENT_UI_LOCALE_STORAGE_KEY, "ja-JP");
    apiMocks.listVersions.mockResolvedValue({
      versions: [
        {
          id: "ver-1",
          version_number: 3,
          content: "test content",
          source: "manual",
          created_at: new Date().toISOString(),
        },
      ],
    });
  });

  afterEach(() => {
    window.localStorage.clear();
    cleanup();
  });

  it("renders chinese button and panel copy when the active project locale is zh-CN", async () => {
    render(
      <VersionHistoryButton
        entityId="block-1"
        entityName="イントロ"
        projectLocale="zh-CN"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "版本" }));

    expect(await screen.findByText("版本历史 - イントロ")).toBeInTheDocument();
    expect(screen.getByTitle("预览内容")).toBeInTheDocument();
    expect(screen.getByTitle("回滚到版本 v3")).toBeInTheDocument();

    await waitFor(() => {
      expect(apiMocks.listVersions).toHaveBeenCalledWith("block-1");
    });
  });
});
