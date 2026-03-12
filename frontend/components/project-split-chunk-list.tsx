// frontend/components/project-split-chunk-list.tsx
// 功能: 编辑项目级自动拆分草稿中的 chunks，支持改标题、改正文、调序、删除、合并、再拆和手动补块
// 主要组件: ProjectSplitChunkList
// 数据结构: ProjectStructureChunk[]

"use client";

import { useState } from "react";
import type { ProjectStructureChunk, ProjectStructureDraftPayload } from "@/lib/api";
import { useUiIsJa } from "@/lib/ui-locale";
import {
  mergePayloadChunks,
  normalizeChunkOrder,
  removePayloadChunk,
  resplitPayloadChunk,
  type ChunkResplitMode,
} from "@/lib/project-split-utils";

interface ProjectSplitChunkListProps {
  payload: ProjectStructureDraftPayload;
  projectLocale?: string | null;
  onChange: (payload: ProjectStructureDraftPayload) => void;
}

export function ProjectSplitChunkList({ payload, projectLocale, onChange }: ProjectSplitChunkListProps) {
  const isJa = useUiIsJa(projectLocale);
  const chunks = payload.chunks || [];
  const [resplitChunkId, setResplitChunkId] = useState<string | null>(null);
  const [resplitMode, setResplitMode] = useState<ChunkResplitMode>("paragraph");
  const [customSeparator, setCustomSeparator] = useState("");
  const [resplitError, setResplitError] = useState<string | null>(null);

  const patchChunk = (chunkId: string, patch: Partial<ProjectStructureChunk>) => {
    onChange({
      ...payload,
      chunks: normalizeChunkOrder(chunks.map((chunk) => (
        chunk.chunk_id === chunkId ? { ...chunk, ...patch } : chunk
      ))),
    });
  };

  const moveChunk = (chunkId: string, direction: "up" | "down") => {
    const next = JSON.parse(JSON.stringify(chunks)) as ProjectStructureChunk[];
    const index = next.findIndex((chunk) => chunk.chunk_id === chunkId);
    if (index < 0) return;
    const target = direction === "up" ? index - 1 : index + 1;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onChange({
      ...payload,
      chunks: normalizeChunkOrder(next),
    });
  };

  const removeChunk = (chunkId: string) => {
    onChange(removePayloadChunk(payload, chunkId));
  };

  const mergeChunks = (chunkId: string, direction: "up" | "down") => {
    onChange(mergePayloadChunks(payload, chunkId, direction));
    setResplitChunkId(null);
    setResplitError(null);
  };

  const applyResplit = (chunk: ProjectStructureChunk) => {
    const result = resplitPayloadChunk(payload, chunk.chunk_id, resplitMode, customSeparator);
    if (result.error) {
      setResplitError(result.error);
      return;
    }
    if (!result.payload) return;
    onChange(result.payload);
    setResplitChunkId(null);
    setResplitError(null);
  };

  const addChunk = () => {
    onChange({
      ...payload,
      chunks: [
        ...normalizeChunkOrder(chunks),
        {
          chunk_id: crypto.randomUUID(),
          title: isJa ? `内容チャンク ${String(chunks.length + 1).padStart(2, "0")}` : `内容片段 ${String(chunks.length + 1).padStart(2, "0")}`,
          content: "",
          order_index: chunks.length,
        },
      ],
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-200">{isJa ? "分割結果" : "拆分结果"}</h3>
        <button
          type="button"
          onClick={addChunk}
          className="rounded-lg bg-surface-3 px-3 py-1.5 text-xs text-zinc-200 hover:bg-surface-4"
        >
          {isJa ? "+ chunk を手動追加" : "+ 手动补一个 chunk"}
        </button>
      </div>

      {!chunks.length ? (
        <div className="rounded-xl border border-dashed border-surface-3 px-4 py-8 text-center text-sm text-zinc-500">
          {isJa ? "chunk はまだありません。先に一度分割するか、手動で chunk を追加してください。" : "还没有 chunk，先执行一次拆分，或手动补一个 chunk。"}
        </div>
      ) : (
        <div className="space-y-3">
          {chunks.map((chunk, index) => (
            <div key={chunk.chunk_id} className="rounded-xl border border-surface-3 bg-surface-1 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-500 w-10">#{index + 1}</span>
                <input
                  value={chunk.title}
                  onChange={(e) => patchChunk(chunk.chunk_id, { title: e.target.value })}
                  placeholder={isJa ? "chunk タイトル" : "chunk 标题"}
                  className="flex-1 rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                />
                <button
                  type="button"
                  onClick={() => moveChunk(chunk.chunk_id, "up")}
                  className="rounded bg-surface-3 px-2 py-1 text-xs text-zinc-300"
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => moveChunk(chunk.chunk_id, "down")}
                  className="rounded bg-surface-3 px-2 py-1 text-xs text-zinc-300"
                >
                  ↓
                </button>
                <button
                  type="button"
                  onClick={() => removeChunk(chunk.chunk_id)}
                  className="rounded bg-red-600/20 px-2 py-1 text-xs text-red-400"
                >
                  {isJa ? "削除" : "删除"}
                </button>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => mergeChunks(chunk.chunk_id, "up")}
                  disabled={index === 0}
                  className="rounded bg-surface-3 px-2 py-1 text-xs text-zinc-300 disabled:opacity-50"
                >
                  {isJa ? "上と結合" : "与上合并"}
                </button>
                <button
                  type="button"
                  onClick={() => mergeChunks(chunk.chunk_id, "down")}
                  disabled={index === chunks.length - 1}
                  className="rounded bg-surface-3 px-2 py-1 text-xs text-zinc-300 disabled:opacity-50"
                >
                  {isJa ? "下と結合" : "与下合并"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setResplitChunkId(resplitChunkId === chunk.chunk_id ? null : chunk.chunk_id);
                    setResplitMode("paragraph");
                    setCustomSeparator("");
                    setResplitError(null);
                  }}
                  className="rounded bg-surface-3 px-2 py-1 text-xs text-zinc-300"
                >
                  {isJa ? "再分割" : "再拆"}
                </button>
              </div>

              <textarea
                value={chunk.content}
                onChange={(e) => patchChunk(chunk.chunk_id, { content: e.target.value })}
                rows={6}
                placeholder={isJa ? "chunk 本文" : "chunk 正文"}
                className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
              />

              {resplitChunkId === chunk.chunk_id && (
                <div className="space-y-3 rounded-lg border border-surface-3 bg-surface-0 p-3">
                  <div className="flex items-center gap-3">
                    <select
                      value={resplitMode}
                      onChange={(e) => {
                        setResplitMode(e.target.value as "paragraph" | "separator");
                        setResplitError(null);
                      }}
                      className="rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                    >
                      <option value="paragraph">{isJa ? "段落の空行で再分割" : "按段落空行再拆"}</option>
                      <option value="separator">{isJa ? "カスタム区切り文字で再分割" : "按自定义分隔符再拆"}</option>
                    </select>
                    {resplitMode === "separator" && (
                      <input
                        value={customSeparator}
                        onChange={(e) => {
                          setCustomSeparator(e.target.value);
                          setResplitError(null);
                        }}
                        placeholder={isJa ? "区切り文字を入力。例: ###" : "输入分隔符，如 ###"}
                        className="flex-1 rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                      />
                    )}
                    <button
                      type="button"
                      onClick={() => applyResplit(chunk)}
                      className="rounded-lg bg-brand-600 px-3 py-2 text-sm text-white hover:bg-brand-700"
                    >
                      {isJa ? "再分割を実行" : "执行再拆"}
                    </button>
                  </div>
                  {resplitError && (
                    <div className="text-xs text-amber-300">{resplitError}</div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
