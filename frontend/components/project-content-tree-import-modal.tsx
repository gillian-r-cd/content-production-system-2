// frontend/components/project-content-tree-import-modal.tsx
// 功能: 项目级 JSON 内容树追加导入弹窗，负责文件读取、摘要预览和确认导入
// 主要组件: ProjectContentTreeImportModal
// 数据结构: 完整项目导出 JSON / content_block_bundle / 导入摘要

"use client";

import { useMemo, useRef, useState } from "react";
import { FileJson, Upload } from "lucide-react";

import { projectAPI } from "@/lib/api";
import { sendNotification } from "@/lib/utils";

interface ImportSummary {
  sourceType: string;
  nodeCount: number;
  rootCount: number;
  fieldCount: number;
  groupCount: number;
  externalDependencyCount: number;
}

function buildImportSummary(data: unknown): ImportSummary {
  if (!data || typeof data !== "object") {
    throw new Error("文件内容不是有效的 JSON 对象");
  }

  const payload = data as Record<string, unknown>;
  const blocks = Array.isArray(payload.content_blocks) ? payload.content_blocks : [];
  if (blocks.length === 0) {
    throw new Error("JSON 中缺少 content_blocks，无法执行目录追加导入");
  }

  const activeBlocks = blocks.filter((item) => item && typeof item === "object" && !(item as Record<string, unknown>).deleted_at) as Array<
    Record<string, unknown>
  >;
  const idSet = new Set(activeBlocks.map((item) => String(item.id || "")).filter(Boolean));
  const rootCount = activeBlocks.filter((item) => {
    const parentId = String(item.parent_id || "");
    return !parentId || !idSet.has(parentId);
  }).length;
  const fieldCount = activeBlocks.filter((item) => String(item.block_type || "field") === "field").length;
  const groupCount = activeBlocks.filter((item) => String(item.block_type || "") === "group").length;
  let externalDependencyCount = 0;
  for (const item of activeBlocks) {
    const dependsOn = Array.isArray(item.depends_on) ? item.depends_on : [];
    externalDependencyCount += dependsOn.filter((depId) => !idSet.has(String(depId || ""))).length;
  }

  const sourceType = payload.type === "content_block_bundle" ? "范围导出 JSON" : "项目完整导出 JSON";
  return {
    sourceType,
    nodeCount: activeBlocks.length,
    rootCount,
    fieldCount,
    groupCount,
    externalDependencyCount,
  };
}

export function ProjectContentTreeImportModal({
  open,
  projectId,
  onClose,
  onImported,
}: {
  open: boolean;
  projectId: string;
  onClose: () => void;
  onImported?: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [rawData, setRawData] = useState<unknown>(null);
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  const summary = useMemo(() => {
    if (!rawData) return null;
    try {
      return buildImportSummary(rawData);
    } catch (summaryError) {
      return {
        sourceType: "",
        nodeCount: 0,
        rootCount: 0,
        fieldCount: 0,
        groupCount: 0,
        externalDependencyCount: 0,
        error: summaryError instanceof Error ? summaryError.message : "无法解析导入摘要",
      };
    }
  }, [rawData]);

  if (!open) return null;

  const resetState = () => {
    setRawData(null);
    setFileName("");
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleClose = () => {
    if (importing) return;
    resetState();
    onClose();
  };

  const handleChooseFile = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const json = JSON.parse(text);
      buildImportSummary(json);
      setRawData(json);
      setFileName(file.name);
      setError(null);
    } catch (fileError) {
      console.error("读取导入文件失败:", fileError);
      setRawData(null);
      setFileName(file.name);
      setError(fileError instanceof Error ? fileError.message : "文件格式错误");
    }
  };

  const handleImport = async () => {
    if (!rawData) {
      setError("请先选择一个可导入的 JSON 文件");
      return;
    }
    setImporting(true);
    setError(null);
    try {
      const result = await projectAPI.importContentTreeJson(projectId, rawData);
      const warningText = result.warning_count > 0 ? `，忽略了 ${result.warning_count} 条范围外依赖` : "";
      sendNotification("导入完成", `已追加导入 ${result.blocks_created} 个内容块${warningText}`);
      resetState();
      onImported?.();
      onClose();
    } catch (importError) {
      console.error("导入内容树失败:", importError);
      setError(importError instanceof Error ? importError.message : "导入失败");
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={handleClose}>
      <div
        className="w-full max-w-xl rounded-xl border border-surface-3 bg-surface-1 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-surface-3 px-5 py-4">
          <h3 className="text-base font-semibold text-zinc-100">从 JSON 导入</h3>
          <p className="mt-1 text-xs text-zinc-500">导入内容会追加到当前项目目录末尾，不会覆盖现有结构。</p>
        </div>

        <div className="space-y-4 px-5 py-4">
          <input ref={fileInputRef} type="file" accept=".json" className="hidden" onChange={handleFileChange} />

          <button
            type="button"
            onClick={handleChooseFile}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-surface-3 bg-surface-2 px-4 py-6 text-sm text-zinc-300 hover:bg-surface-3"
          >
            <Upload className="h-4 w-4" />
            {fileName ? `重新选择文件：${fileName}` : "选择 JSON 文件"}
          </button>

          {summary && !("error" in summary) && (
            <div className="rounded-lg border border-surface-3 bg-surface-2 px-4 py-3 text-sm text-zinc-300">
              <div className="mb-2 flex items-center gap-2 text-zinc-200">
                <FileJson className="h-4 w-4" />
                <span>{fileName}</span>
              </div>
              <div className="space-y-1 text-xs text-zinc-400">
                <div>来源类型：{summary.sourceType}</div>
                <div>根节点数：{summary.rootCount}</div>
                <div>总节点数：{summary.nodeCount}</div>
                <div>分组数：{summary.groupCount}</div>
                <div>内容块数：{summary.fieldCount}</div>
                <div>范围外依赖数：{summary.externalDependencyCount}</div>
              </div>
            </div>
          )}

          {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>}

          <div className="rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-xs text-zinc-500">
            第一版只追加导入 `content_blocks`，不会把源文件中的对话、草稿、评分器等外围对象并入当前项目。
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-surface-3 px-5 py-4">
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg bg-surface-3 px-4 py-2 text-sm text-zinc-200 hover:bg-surface-4"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleImport}
            disabled={importing || !rawData}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {importing ? "导入中..." : "追加导入到当前项目"}
          </button>
        </div>
      </div>
    </div>
  );
}
