// frontend/components/template-selector.test.tsx
// 功能: 覆盖流程模板选择器的日文文案渲染
// 主要测试: TemplateSelector
// 数据结构: PhaseTemplate

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLIENT_UI_LOCALE_STORAGE_KEY } from "@/lib/project-locale";
import TemplateSelector from "./template-selector";

const apiMocks = vi.hoisted(() => ({
  list: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    phaseTemplateAPI: {
      ...actual.phaseTemplateAPI,
      list: apiMocks.list,
    },
    blockAPI: {
      ...actual.blockAPI,
      applyTemplate: vi.fn(),
    },
  };
});

describe("TemplateSelector", () => {
  const originalLanguage = navigator.language;

  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.localStorage.setItem(CLIENT_UI_LOCALE_STORAGE_KEY, "ja-JP");
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: "zh-CN",
    });
    apiMocks.list.mockResolvedValue([
      {
        id: "template-1",
        name: "講座テンプレート",
        description: "講座向けの標準テンプレート",
        phases: [
          {
            name: "導入",
            special_handler: null,
            default_fields: [{ name: "概要" }],
          },
        ],
        root_nodes: [],
        is_default: true,
        is_system: true,
      },
    ]);
  });

  afterEach(() => {
    window.localStorage.clear();
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: originalLanguage,
    });
    cleanup();
  });

  it("renders japanese copy when persisted ui locale is ja-JP", async () => {
    render(<TemplateSelector />);

    await waitFor(() => {
      expect(screen.getByText("フローテンプレートを選択")).toBeInTheDocument();
    });

    expect(screen.getByText("既定")).toBeInTheDocument();
    expect(screen.getByText("システム")).toBeInTheDocument();
    expect(screen.getByText("1 個のコンテナノード・1 個の内容ブロックを含みます")).toBeInTheDocument();
    expect(
      screen.getByText(
        (_, element) =>
          element?.tagName === "P"
          && (element.textContent?.includes("テンプレート選択後、対応するフローフェーズと既定フィールドが自動作成されます。") ?? false),
      ),
    ).toBeInTheDocument();
  });
});
