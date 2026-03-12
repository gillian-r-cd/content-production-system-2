import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  CLIENT_UI_LOCALE_STORAGE_KEY,
  formatProjectText,
  isJaProjectLocale,
  normalizeProjectLocale,
  persistClientLocale,
  projectUiText,
  resolveClientLocale,
} from "./project-locale";

describe("project-locale", () => {
  const originalLanguage = navigator.language;
  const originalDocumentLang = document.documentElement.lang;

  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.lang = "";
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: originalLanguage,
    });
  });

  afterEach(() => {
    window.localStorage.clear();
    document.documentElement.lang = originalDocumentLang;
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: originalLanguage,
    });
  });

  it("normalizes japanese aliases to ja-JP", () => {
    expect(normalizeProjectLocale("ja")).toBe("ja-JP");
    expect(normalizeProjectLocale("jp")).toBe("ja-JP");
    expect(normalizeProjectLocale("ja-JP")).toBe("ja-JP");
  });

  it("falls back to zh-CN for empty or unsupported values", () => {
    expect(normalizeProjectLocale(null)).toBe("zh-CN");
    expect(normalizeProjectLocale("")).toBe("zh-CN");
    expect(normalizeProjectLocale("en-US")).toBe("zh-CN");
  });

  it("returns japanese ui copy for ja projects", () => {
    const text = projectUiText("ja-JP");

    expect(text.systemName).toBe("コンテンツ制作システム");
    expect(text.startAllReady).toBe("準備完了ブロックをすべて開始");
    expect(isJaProjectLocale("ja-JP")).toBe(true);
  });

  it("formats placeholder text with runtime params", () => {
    expect(formatProjectText(projectUiText("ja-JP").version, { version: 3 })).toBe("バージョン 3");
    expect(formatProjectText(projectUiText("zh-CN").selectedCount, { selected: 2, total: 5 })).toBe("已选 2 / 5");
  });

  it("prefers persisted client locale over document and browser locale", () => {
    document.documentElement.lang = "zh-CN";
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: "zh-CN",
    });
    window.localStorage.setItem(CLIENT_UI_LOCALE_STORAGE_KEY, "ja-JP");

    expect(resolveClientLocale()).toBe("ja-JP");
  });

  it("prefers navigator locale over the server-side document lang fallback", () => {
    document.documentElement.lang = "zh-CN";
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: "ja-JP",
    });

    expect(resolveClientLocale()).toBe("ja-JP");
  });

  it("persists normalized client locale to storage and document lang", () => {
    expect(persistClientLocale("ja")).toBe("ja-JP");
    expect(window.localStorage.getItem(CLIENT_UI_LOCALE_STORAGE_KEY)).toBe("ja-JP");
    expect(document.documentElement.lang).toBe("ja-JP");
  });
});
