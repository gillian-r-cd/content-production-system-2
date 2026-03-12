// frontend/components/settings/profiles-section.test.tsx
// 功能: 覆盖创作者特质设置页的 locale 回归，确保 settings 区域跟随持久化 UI locale
// 主要测试: ProfilesSection
// 数据结构: CreatorProfile[] / CLIENT_UI_LOCALE_STORAGE_KEY

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { CLIENT_UI_LOCALE_STORAGE_KEY } from "@/lib/project-locale";
import { ProfilesSection } from "./profiles-section";

describe("ProfilesSection", () => {
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

  it("uses persisted japanese ui locale inside settings even when browser locale is zh-CN", async () => {
    window.localStorage.setItem(CLIENT_UI_LOCALE_STORAGE_KEY, "ja-JP");

    render(<ProfilesSection profiles={[]} onRefresh={() => undefined} />);

    await waitFor(() => {
      expect(screen.getByText("クリエイター特性")).toBeInTheDocument();
    });

    expect(screen.getByText("異なる制作スタイルを定義し、プロジェクト作成時に選択できます")).toBeInTheDocument();
    expect(screen.getByText("クリエイター特性はまだありません。上の「新規特性」をクリックして作成してください")).toBeInTheDocument();
  });

  it("defaults new profiles to ja-JP when settings ui locale is japanese", async () => {
    window.localStorage.setItem(CLIENT_UI_LOCALE_STORAGE_KEY, "ja-JP");

    render(<ProfilesSection profiles={[]} onRefresh={() => undefined} />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "+ 新規特性" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "+ 新規特性" }));

    const localeSelect = screen.getByRole("combobox") as HTMLSelectElement;
    expect(localeSelect.value).toBe("ja-JP");
  });
});
