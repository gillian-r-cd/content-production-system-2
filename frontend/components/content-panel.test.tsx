// 功能: 覆盖 workspace 中栏的 UI locale 优先级，确保激活项目后 UI 跟随项目语言而不是旧的持久化偏好
// 主要测试: ContentPanel
// 数据结构: CLIENT_UI_LOCALE_STORAGE_KEY / ContentBlock

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { CLIENT_UI_LOCALE_STORAGE_KEY } from "@/lib/project-locale";
import { ContentPanel } from "./content-panel";

describe("ContentPanel locale parity", () => {
  const originalLanguage = navigator.language;

  beforeEach(() => {
    window.localStorage.clear();
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: "zh-CN",
    });
  });

  afterEach(() => {
    window.localStorage.clear();
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: originalLanguage,
    });
    cleanup();
  });

  it("prefers the active project locale over a persisted japanese ui locale", () => {
    window.localStorage.setItem(CLIENT_UI_LOCALE_STORAGE_KEY, "ja-JP");

    render(
      <ContentPanel
        projectId="project-1"
        projectLocale="zh-CN"
        selectedBlock={null}
        allBlocks={[]}
      />,
    );

    expect(screen.getByText("树形架构模式")).toBeInTheDocument();
    expect(
      screen.getByText("请在左侧树形结构中选择一个组或字段来查看和编辑内容。"),
    ).toBeInTheDocument();
  });
});
