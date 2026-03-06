// frontend/lib/project-split-utils.ts
// 功能: 自动拆分草稿中 chunk 编辑的纯函数工具，承载调序、合并、再拆等可回归逻辑
// 主要函数: normalizeChunkOrder / mergeChunkWithNeighbor / resplitChunk / mergePayloadChunks / resplitPayloadChunk
// 数据结构: ProjectStructureChunk[] / ProjectStructureDraftPayload / ChunkResplitResult

import type {
  DraftDependencyRef,
  ProjectStructureChunk,
  ProjectStructureDraftPayload,
  TemplateNode,
} from "./api";

export type ChunkResplitMode = "paragraph" | "separator";

export interface ChunkResplitResult {
  chunks?: ProjectStructureChunk[];
  error?: string;
}

type CreateId = () => string;

function defaultCreateId(): string {
  return crypto.randomUUID();
}

function clonePayload(payload: ProjectStructureDraftPayload): ProjectStructureDraftPayload {
  return JSON.parse(JSON.stringify(payload));
}

function mapTemplateNodes(
  nodes: TemplateNode[] = [],
  mapper: (node: TemplateNode) => TemplateNode,
): TemplateNode[] {
  return nodes.map((node) => {
    const mappedChildren = mapTemplateNodes(node.children || [], mapper);
    return mapper({ ...node, children: mappedChildren });
  });
}

function dedupeChunkIds(chunkIds: string[]): string[] {
  return chunkIds.filter((chunkId, index) => chunkIds.indexOf(chunkId) === index);
}

function rewriteRefs(
  refs: DraftDependencyRef[] = [],
  chunkIdMap: Record<string, string[]>,
): DraftDependencyRef[] {
  const nextRefs: DraftDependencyRef[] = [];

  for (const ref of refs) {
    if (!ref.chunk_id) {
      nextRefs.push(ref);
      continue;
    }
    const mappedChunkIds = chunkIdMap[ref.chunk_id];
    if (!mappedChunkIds) {
      nextRefs.push(ref);
      continue;
    }
    for (const chunkId of mappedChunkIds) {
      nextRefs.push({ ...ref, chunk_id: chunkId });
    }
  }

  return nextRefs.filter((ref, index) => {
    const key = JSON.stringify(ref);
    return nextRefs.findIndex((item) => JSON.stringify(item) === key) === index;
  });
}

function rewritePayloadChunkRefs(
  payload: ProjectStructureDraftPayload,
  chunkIdMap: Record<string, string[]>,
): ProjectStructureDraftPayload {
  const next = clonePayload(payload);
  next.shared_root_nodes = mapTemplateNodes(next.shared_root_nodes, (node) => ({
    ...node,
    draft_dependency_refs: rewriteRefs(node.draft_dependency_refs, chunkIdMap),
  }));
  next.aggregate_root_nodes = mapTemplateNodes(next.aggregate_root_nodes, (node) => ({
    ...node,
    draft_dependency_refs: rewriteRefs(node.draft_dependency_refs, chunkIdMap),
  }));
  next.plans = next.plans.map((plan) => ({
    ...plan,
    target_chunk_ids: dedupeChunkIds(
      plan.target_chunk_ids.flatMap((chunkId) => chunkIdMap[chunkId] || [chunkId]),
    ),
    root_nodes: mapTemplateNodes(plan.root_nodes, (node) => ({
      ...node,
      draft_dependency_refs: rewriteRefs(node.draft_dependency_refs, chunkIdMap),
    })),
  }));
  return next;
}

export function normalizeChunkOrder(chunks: ProjectStructureChunk[]): ProjectStructureChunk[] {
  return chunks.map((chunk, index) => ({
    ...chunk,
    order_index: index,
  }));
}

export function mergeChunkWithNeighbor(
  chunks: ProjectStructureChunk[],
  chunkId: string,
  direction: "up" | "down",
  createId: CreateId = defaultCreateId,
): ProjectStructureChunk[] {
  const index = chunks.findIndex((chunk) => chunk.chunk_id === chunkId);
  if (index < 0) return chunks;

  const targetIndex = direction === "up" ? index - 1 : index + 1;
  if (targetIndex < 0 || targetIndex >= chunks.length) return chunks;

  const firstIndex = Math.min(index, targetIndex);
  const secondIndex = Math.max(index, targetIndex);
  const first = chunks[firstIndex];
  const second = chunks[secondIndex];
  const mergedChunk: ProjectStructureChunk = {
    chunk_id: createId(),
    title: `${first.title} / ${second.title}`.trim(),
    content: [first.content, second.content].filter(Boolean).join("\n\n"),
    order_index: firstIndex,
  };

  return normalizeChunkOrder([
    ...chunks.slice(0, firstIndex),
    mergedChunk,
    ...chunks.slice(secondIndex + 1),
  ]);
}

export function mergePayloadChunks(
  payload: ProjectStructureDraftPayload,
  chunkId: string,
  direction: "up" | "down",
): ProjectStructureDraftPayload {
  const index = payload.chunks.findIndex((chunk) => chunk.chunk_id === chunkId);
  if (index < 0) return payload;
  const targetIndex = direction === "up" ? index - 1 : index + 1;
  if (targetIndex < 0 || targetIndex >= payload.chunks.length) return payload;

  const firstIndex = Math.min(index, targetIndex);
  const secondIndex = Math.max(index, targetIndex);
  const first = payload.chunks[firstIndex];
  const second = payload.chunks[secondIndex];
  const mergedChunkId = first.chunk_id;
  const mergedChunks = normalizeChunkOrder([
    ...payload.chunks.slice(0, firstIndex),
    {
      chunk_id: mergedChunkId,
      title: `${first.title} / ${second.title}`.trim(),
      content: [first.content, second.content].filter(Boolean).join("\n\n"),
      order_index: firstIndex,
    },
    ...payload.chunks.slice(secondIndex + 1),
  ]);

  const next = rewritePayloadChunkRefs(payload, {
    [first.chunk_id]: [mergedChunkId],
    [second.chunk_id]: [mergedChunkId],
  });
  next.chunks = mergedChunks;
  return next;
}

export function removePayloadChunk(
  payload: ProjectStructureDraftPayload,
  chunkId: string,
): ProjectStructureDraftPayload {
  const next = rewritePayloadChunkRefs(payload, {
    [chunkId]: [],
  });
  next.chunks = normalizeChunkOrder(
    payload.chunks.filter((chunk) => chunk.chunk_id !== chunkId),
  );
  return next;
}

export function resplitChunk(
  chunks: ProjectStructureChunk[],
  chunkId: string,
  mode: ChunkResplitMode,
  customSeparator: string,
  createId: CreateId = defaultCreateId,
): ChunkResplitResult {
  const chunk = chunks.find((item) => item.chunk_id === chunkId);
  if (!chunk) return { error: "未找到要再拆的 chunk。" };
  if (!chunk.content.trim()) return { error: "当前 chunk 为空，无法再拆。" };
  if (mode === "separator" && !customSeparator) return { error: "请先输入自定义分隔符。" };

  const separator = mode === "paragraph" ? "\n\n" : customSeparator;
  const parts = (mode === "paragraph"
    ? chunk.content.split(/\n{2,}/)
    : chunk.content.split(separator)
  )
    .map((part) => part.trim())
    .filter(Boolean);

  if (parts.length < 2) {
    return { error: "没有拆出多个有效片段，请调整正文或分隔方式。" };
  }

  const index = chunks.findIndex((item) => item.chunk_id === chunkId);
  if (index < 0) return { error: "未找到要再拆的 chunk。" };

  return {
    chunks: normalizeChunkOrder([
      ...chunks.slice(0, index),
      ...parts.map((part, partIndex) => ({
        chunk_id: partIndex === 0 ? chunk.chunk_id : createId(),
        title: `${chunk.title} ${String(partIndex + 1).padStart(2, "0")}`,
        content: part,
        order_index: index + partIndex,
      })),
      ...chunks.slice(index + 1),
    ]),
  };
}

export function resplitPayloadChunk(
  payload: ProjectStructureDraftPayload,
  chunkId: string,
  mode: ChunkResplitMode,
  customSeparator: string,
  createId: CreateId = defaultCreateId,
): { payload?: ProjectStructureDraftPayload; error?: string } {
  const result = resplitChunk(payload.chunks, chunkId, mode, customSeparator, createId);
  if (result.error) return { error: result.error };
  if (!result.chunks) return { error: "再拆失败。" };

  const derivedChunks = result.chunks.filter((chunk) => {
    const originalIndex = payload.chunks.findIndex((item) => item.chunk_id === chunk.chunk_id);
    return originalIndex < 0;
  });
  const nextChunkIds = [chunkId, ...derivedChunks.map((chunk) => chunk.chunk_id)];
  const next = rewritePayloadChunkRefs(payload, {
    [chunkId]: nextChunkIds,
  });
  next.chunks = result.chunks;
  return { payload: next };
}
