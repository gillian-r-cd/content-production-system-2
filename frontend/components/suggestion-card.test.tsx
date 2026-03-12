import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SuggestionCard, UndoToast } from "./suggestion-card";

describe("SuggestionCard", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    cleanup();
  });

  it("renders japanese suggestion copy when project locale is ja-JP", () => {
    render(
      <SuggestionCard
        data={{
          id: "card-1",
          target_field: "導入",
          summary: "導入文を簡潔にする提案",
          reason: "冗長です",
          diff_preview: "",
          edits_count: 2,
          status: "accepted",
        }}
        projectId="project-1"
        projectLocale="ja-JP"
        onStatusChange={vi.fn()}
        onFollowUp={vi.fn()}
      />,
    );

    expect(screen.getByText("対象: 導入 · 2 件の変更")).toBeInTheDocument();
    expect(screen.getByText("✓ 適用済み")).toBeInTheDocument();
    expect(screen.getByText("理由: 冗長です")).toBeInTheDocument();
  });

  it("renders japanese undo toast copy when project locale is ja-JP", () => {
    render(
      <UndoToast
        entityId="entity-1"
        versionId="version-1"
        targetField="導入"
        projectLocale="ja-JP"
        onUndo={vi.fn()}
        onExpire={vi.fn()}
      />,
    );

    expect(screen.getByText("変更を「導入」へ適用しました")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "↩ 元に戻す" })).toBeInTheDocument();
  });
});
