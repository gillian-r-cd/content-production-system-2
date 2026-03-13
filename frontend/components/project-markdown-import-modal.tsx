// 功能: 项目级 Markdown 批量导入弹窗，负责文件读取、模式选择与确认导入
// 主要组件: ProjectMarkdownImportModal
// 数据结构: MarkdownImportFilePayload（name/path/content）+ import_mode

"use client";

import { useMemo, useRef, useState } from "react";
import { FileText, Upload } from "lucide-react";

import { projectAPI } from "@/lib/api";
import { formatProjectText, projectUiText } from "@/lib/project-locale";
import { sendNotification } from "@/lib/utils";

type MarkdownImportMode = "heading_tree" | "raw_file";

interface MarkdownImportFilePayload {
  name: string;
  path?: string;
  content: string;
}

export function ProjectMarkdownImportModal({
  open,
  projectId,
  projectLocale,
  onClose,
  onImported,
}: {
  open: boolean;
  projectId: string;
  projectLocale?: string | null;
  onClose: () => void;
  onImported?: () => void;
}) {
  const t = projectUiText(projectLocale);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<MarkdownImportFilePayload[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [importMode, setImportMode] = useState<MarkdownImportMode>("heading_tree");
  const [importing, setImporting] = useState(false);

  const selectedLabel = useMemo(() => {
    if (files.length === 0) return "";
    if (files.length === 1) {
      return formatProjectText(t.markdownImportReselectFiles, { name: files[0].name });
    }
    return formatProjectText(t.markdownImportSelectedFiles, { count: files.length });
  }, [files, t.markdownImportReselectFiles, t.markdownImportSelectedFiles]);

  if (!open) return null;

  const resetState = () => {
    setFiles([]);
    setError(null);
    setImportMode("heading_tree");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleClose = () => {
    if (importing) return;
    resetState();
    onClose();
  };

  const handleChooseFiles = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(event.target.files || []);
    if (selectedFiles.length === 0) return;

    try {
      const loadedFiles = await Promise.all(
        selectedFiles.map(async (file) => ({
          name: file.name,
          path: file.webkitRelativePath || file.name,
          content: await file.text(),
        })),
      );
      setFiles(loadedFiles);
      setError(null);
    } catch (fileError) {
      console.error("读取 Markdown 文件失败:", fileError);
      setFiles([]);
      setError(fileError instanceof Error ? fileError.message : t.markdownImportFailed);
    }
  };

  const handleImport = async () => {
    if (files.length === 0) {
      setError(t.markdownImportChooseFirst);
      return;
    }
    setImporting(true);
    setError(null);
    try {
      // #region agent log
      fetch("http://127.0.0.1:7242/ingest/41308a22-a688-4d62-9d81-f84e13dbaa44",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({runId:"markdown-import-initial",hypothesisId:"H3",location:"frontend/components/project-markdown-import-modal.tsx:99",message:"markdown import submit",data:{projectId,importMode,fileCount:files.length,fileNames:files.map((file)=>file.name),filePaths:files.map((file)=>file.path||file.name)},timestamp:Date.now()})}).catch(()=>{});
      // #endregion
      const result = await projectAPI.importMarkdownFiles(projectId, {
        import_mode: importMode,
        files,
      });
      sendNotification(t.markdownImportDoneTitle, result.message);
      resetState();
      onImported?.();
      onClose();
    } catch (importError) {
      console.error("导入 Markdown 失败:", importError);
      // #region agent log
      fetch("http://127.0.0.1:7242/ingest/41308a22-a688-4d62-9d81-f84e13dbaa44",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({runId:"markdown-import-initial",hypothesisId:"H3",location:"frontend/components/project-markdown-import-modal.tsx:108",message:"markdown import failed in modal",data:{projectId,importMode,fileCount:files.length,errorMessage:importError instanceof Error ? importError.message : String(importError)},timestamp:Date.now()})}).catch(()=>{});
      // #endregion
      setError(importError instanceof Error ? importError.message : t.markdownImportFailed);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={handleClose}>
      <div
        className="w-full max-w-2xl rounded-xl border border-surface-3 bg-surface-1 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-surface-3 px-5 py-4">
          <h3 className="text-base font-semibold text-zinc-100">{t.importMarkdownTitle}</h3>
          <p className="mt-1 text-xs text-zinc-500">{t.importMarkdownDescription}</p>
        </div>

        <div className="space-y-4 px-5 py-4">
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.markdown,text/markdown"
            multiple
            className="hidden"
            onChange={handleFileChange}
          />

          <button
            type="button"
            onClick={handleChooseFiles}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-surface-3 bg-surface-2 px-4 py-6 text-sm text-zinc-300 hover:bg-surface-3"
          >
            <Upload className="h-4 w-4" />
            {selectedLabel || t.markdownImportSelectFiles}
          </button>

          <div className="rounded-lg border border-surface-3 bg-surface-2 px-4 py-3">
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">{t.markdownImportModeLabel}</div>
            <div className="space-y-2">
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-surface-3 px-3 py-3 text-sm text-zinc-200 hover:border-brand-500/40">
                <input
                  type="radio"
                  name="markdown-import-mode"
                  className="mt-0.5"
                  checked={importMode === "heading_tree"}
                  onChange={() => setImportMode("heading_tree")}
                />
                <div>
                  <div className="font-medium">{t.markdownImportModeHeadingTree}</div>
                  <div className="mt-1 text-xs text-zinc-500">{t.markdownImportModeHeadingTreeDesc}</div>
                </div>
              </label>
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-surface-3 px-3 py-3 text-sm text-zinc-200 hover:border-brand-500/40">
                <input
                  type="radio"
                  name="markdown-import-mode"
                  className="mt-0.5"
                  checked={importMode === "raw_file"}
                  onChange={() => setImportMode("raw_file")}
                />
                <div>
                  <div className="font-medium">{t.markdownImportModeRawFile}</div>
                  <div className="mt-1 text-xs text-zinc-500">{t.markdownImportModeRawFileDesc}</div>
                </div>
              </label>
            </div>
          </div>

          {files.length > 0 && (
            <div className="rounded-lg border border-surface-3 bg-surface-2 px-4 py-3 text-sm text-zinc-300">
              <div className="mb-2 flex items-center justify-between text-xs text-zinc-500">
                <span>{formatProjectText(t.markdownImportSelectedFiles, { count: files.length })}</span>
                <span>{t.markdownImportFileCount}: {files.length}</span>
              </div>
              <div className="max-h-48 space-y-2 overflow-y-auto">
                {files.map((file) => (
                  <div key={file.path || file.name} className="flex items-start gap-2 rounded-lg border border-surface-3 px-3 py-2">
                    <FileText className="mt-0.5 h-4 w-4 text-zinc-500" />
                    <div className="min-w-0">
                      <div className="truncate text-sm text-zinc-200">{file.name}</div>
                      <div className="truncate text-xs text-zinc-500">{file.path || file.name}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-xs text-zinc-500">
            <div>{t.markdownImportFallbackHint}</div>
            <div className="mt-1">{t.markdownImportFooter}</div>
          </div>

          {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-surface-3 px-5 py-4">
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg bg-surface-3 px-4 py-2 text-sm text-zinc-200 hover:bg-surface-4"
          >
            {t.cancel}
          </button>
          <button
            type="button"
            onClick={handleImport}
            disabled={importing || files.length === 0}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {importing ? t.markdownImportSubmitting : t.importMarkdown}
          </button>
        </div>
      </div>
    </div>
  );
}
