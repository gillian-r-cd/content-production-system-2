// frontend/components/content-tree-action-items.tsx
// 功能: 为项目级/节点级内容树菜单提供 Markdown 导出、JSON 下载、保存模板入口等统一动作
// 主要组件: ContentTreeActionItems
// 数据结构: project/block 两种 scope，共用相同的导出链路，并把模板保存请求抛给稳定父节点

"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronRight, Download, FileText, Package } from "lucide-react";

import { blockAPI, projectAPI } from "@/lib/api";
import { useUiIsJa } from "@/lib/ui-locale";
import { sendNotification } from "@/lib/utils";

type ContentTreeActionScope =
  | {
      type: "project";
      projectId: string;
      label: string;
    }
  | {
      type: "block";
      blockId: string;
      label: string;
    };

interface ContentTreeActionItemsProps {
  scope: ContentTreeActionScope;
  projectLocale?: string | null;
  closeMenu?: () => void;
  onRequestSaveTemplate?: (scope: ContentTreeActionScope) => void;
}

interface FixedSubmenuPosition {
  top: number;
  left: number;
}

function sanitizeFilename(filename: string): string {
  return filename.replace(/[\\/:*?"<>|]/g, "_");
}

function downloadText(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = sanitizeFilename(filename);
  anchor.click();
  URL.revokeObjectURL(url);
}

function downloadJson(data: unknown, filename: string) {
  downloadText(JSON.stringify(data, null, 2), filename, "application/json");
}

export function ContentTreeActionItems({ scope, projectLocale, closeMenu, onRequestSaveTemplate }: ContentTreeActionItemsProps) {
  const isJa = useUiIsJa(projectLocale);
  const [showDownloadSubmenu, setShowDownloadSubmenu] = useState(false);
  const [submenuPosition, setSubmenuPosition] = useState<FixedSubmenuPosition>({ top: 0, left: 0 });
  const downloadButtonRef = useRef<HTMLButtonElement | null>(null);

  const closeAllMenus = () => {
    setShowDownloadSubmenu(false);
    closeMenu?.();
  };

  const fetchMarkdown = async () => {
    if (scope.type === "project") {
      return projectAPI.exportProjectMarkdown(scope.projectId);
    }
    return blockAPI.exportMarkdown(scope.blockId);
  };

  const fetchJson = async () => {
    if (scope.type === "project") {
      return projectAPI.exportProject(scope.projectId);
    }
    return blockAPI.exportJson(scope.blockId);
  };

  const handleCopyMarkdown = async () => {
    try {
      const result = await fetchMarkdown();
      await navigator.clipboard.writeText(result.markdown);
      sendNotification(isJa ? "Markdown をコピーしました" : "已复制 Markdown", isJa ? `「${scope.label}」をクリップボードにコピーしました` : `「${scope.label}」已复制到剪贴板`);
      closeAllMenus();
    } catch (error) {
      console.error("复制 Markdown 失败:", error);
      sendNotification(isJa ? "コピーに失敗しました" : "复制失败", error instanceof Error ? error.message : (isJa ? "不明なエラー" : "未知错误"));
    }
  };

  const handleDownloadMarkdown = async () => {
    try {
      const result = await fetchMarkdown();
      downloadText(result.markdown, result.filename || `${scope.label}.md`, "text/markdown;charset=utf-8");
      sendNotification(isJa ? "ダウンロードを開始しました" : "已开始下载", isJa ? `Markdown ファイル「${scope.label}」の準備ができました` : `Markdown 文件「${scope.label}」已准备好`);
      closeAllMenus();
    } catch (error) {
      console.error("下载 Markdown 失败:", error);
      sendNotification(isJa ? "ダウンロードに失敗しました" : "下载失败", error instanceof Error ? error.message : (isJa ? "不明なエラー" : "未知错误"));
    }
  };

  const handleDownloadJson = async () => {
    try {
      const result = await fetchJson();
      downloadJson(result, `${scope.label}.json`);
      sendNotification(isJa ? "ダウンロードを開始しました" : "已开始下载", isJa ? `JSON ファイル「${scope.label}」の準備ができました` : `JSON 文件「${scope.label}」已准备好`);
      closeAllMenus();
    } catch (error) {
      console.error("下载 JSON 失败:", error);
      sendNotification(isJa ? "ダウンロードに失敗しました" : "下载失败", error instanceof Error ? error.message : (isJa ? "不明なエラー" : "未知错误"));
    }
  };

  const handleRequestSaveTemplate = () => {
    onRequestSaveTemplate?.(scope);
    closeAllMenus();
  };

  const itemClassName = "w-full flex items-center gap-2 px-3 py-2 text-sm text-zinc-300 hover:bg-surface-2";
  const submenuWidth = 160;

  useEffect(() => {
    if (!showDownloadSubmenu) return;

    const updateSubmenuPosition = () => {
      const trigger = downloadButtonRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const preferredLeft = rect.right + 4;
      const fallbackLeft = rect.left - submenuWidth - 4;
      const resolvedLeft =
        preferredLeft + submenuWidth <= viewportWidth - 8
          ? preferredLeft
          : Math.max(8, fallbackLeft);
      const resolvedTop = Math.min(rect.top, Math.max(8, viewportHeight - 88));

      setSubmenuPosition({
        top: resolvedTop,
        left: resolvedLeft,
      });
    };

    updateSubmenuPosition();
    window.addEventListener("resize", updateSubmenuPosition);
    window.addEventListener("scroll", updateSubmenuPosition, true);
    return () => {
      window.removeEventListener("resize", updateSubmenuPosition);
      window.removeEventListener("scroll", updateSubmenuPosition, true);
    };
  }, [showDownloadSubmenu]);

  return (
    <>
      <button onClick={handleCopyMarkdown} className={itemClassName}>
        <FileText className="w-4 h-4" />
        {isJa ? "Markdown としてコピー" : "复制为 Markdown 格式"}
      </button>

      <div className="relative">
        <button
          ref={downloadButtonRef}
          onClick={() => setShowDownloadSubmenu((previous) => !previous)}
          className={`${itemClassName} justify-between`}
        >
          <span className="flex items-center gap-2">
            <Download className="w-4 h-4" />
            {isJa ? "ダウンロード" : "下载"}
          </span>
          <ChevronRight className="w-4 h-4" />
        </button>

        {showDownloadSubmenu && (
          <div
            className="fixed z-[60] w-40 rounded-lg border border-surface-3 bg-surface-1 shadow-lg"
            style={{
              top: submenuPosition.top,
              left: submenuPosition.left,
            }}
          >
            <button onClick={handleDownloadMarkdown} className={itemClassName}>
              Markdown
            </button>
            <button onClick={handleDownloadJson} className={itemClassName}>
              JSON
            </button>
          </div>
        )}
      </div>

      <button onClick={handleRequestSaveTemplate} className={itemClassName}>
        <Package className="w-4 h-4" />
        {isJa ? "内容ブロックテンプレートとして保存" : "保存为内容块模板"}
      </button>
    </>
  );
}
