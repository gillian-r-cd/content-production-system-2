// 功能: 前端 UI locale Hook，优先使用当前活跃项目/调用方显式传入的 locale，并在缺失时回退到持久化 UI 语言
// 主要导出: resolveUiLocale, useUiLocale, useUiIsJa
// 数据结构: 依赖 project-locale 中的 locale 归一化与持久化 key

"use client";

import { useEffect, useState } from "react";

import {
  CLIENT_UI_LOCALE_STORAGE_KEY,
  isJaProjectLocale,
  normalizeProjectLocale,
} from "./project-locale";

export function resolveUiLocale(fallbackLocale?: string | null): "zh-CN" | "ja-JP" {
  if (fallbackLocale) {
    return normalizeProjectLocale(fallbackLocale);
  }

  if (typeof window !== "undefined") {
    try {
      const storedLocale = window.localStorage.getItem(CLIENT_UI_LOCALE_STORAGE_KEY);
      if (storedLocale) {
        return normalizeProjectLocale(storedLocale);
      }
    } catch {
      // Ignore storage errors and continue to fallback sources.
    }
  }

  if (typeof navigator !== "undefined") {
    return normalizeProjectLocale(navigator.language);
  }

  if (typeof document !== "undefined") {
    const documentLocale = document.documentElement?.lang;
    if (documentLocale) {
      return normalizeProjectLocale(documentLocale);
    }
  }

  return "zh-CN";
}

export function useUiLocale(fallbackLocale?: string | null) {
  const [locale, setLocale] = useState<"zh-CN" | "ja-JP">(() => resolveUiLocale(fallbackLocale));

  useEffect(() => {
    const syncLocale = () => {
      setLocale(resolveUiLocale(fallbackLocale));
    };

    syncLocale();
    window.addEventListener("storage", syncLocale);

    return () => {
      window.removeEventListener("storage", syncLocale);
    };
  }, [fallbackLocale]);

  return locale;
}

export function useUiIsJa(fallbackLocale?: string | null) {
  return isJaProjectLocale(useUiLocale(fallbackLocale));
}
