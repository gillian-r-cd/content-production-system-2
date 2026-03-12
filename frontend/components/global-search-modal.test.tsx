import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GlobalSearchModal } from "./global-search-modal";

const apiMocks = vi.hoisted(() => ({
  search: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    projectAPI: {
      ...actual.projectAPI,
      search: apiMocks.search,
      replace: apiMocks.replace,
    },
  };
});

describe("GlobalSearchModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.search.mockResolvedValue({ results: [], total_matches: 0 });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders japanese search and replace copy when locale is ja-JP", async () => {
    render(
      <GlobalSearchModal
        projectId="project-1"
        projectLocale="ja-JP"
        open
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByPlaceholderText("プロジェクト内のすべての内容を検索...")).toBeInTheDocument();

    fireEvent.click(screen.getByTitle("置換"));

    expect(screen.getByPlaceholderText("置換後の文字列...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "すべて置換 (0)" })).toBeInTheDocument();
  });
});
