// frontend/lib/project-split-utils.test.ts
// 功能: 覆盖自动拆分草稿 chunk 编辑工具的关键回归场景
// 主要测试: mergeChunkWithNeighbor / mergePayloadChunks / resplitPayloadChunk / removePayloadChunk
// 数据结构: ProjectStructureChunk[] / ProjectStructureDraftPayload

import { describe, expect, it } from "vitest";
import type { ProjectStructureChunk, ProjectStructureDraftPayload } from "./api";
import {
  mergeChunkWithNeighbor,
  mergePayloadChunks,
  normalizeChunkOrder,
  removePayloadChunk,
  resplitChunk,
  resplitPayloadChunk,
} from "./project-split-utils";

function makeChunks(): ProjectStructureChunk[] {
  return normalizeChunkOrder([
    { chunk_id: "chunk-1", title: "片段一", content: "alpha", order_index: 0 },
    { chunk_id: "chunk-2", title: "片段二", content: "beta", order_index: 1 },
    { chunk_id: "chunk-3", title: "片段三", content: "gamma", order_index: 2 },
  ]);
}

function makePayload(): ProjectStructureDraftPayload {
  return {
    chunks: normalizeChunkOrder([
      { chunk_id: "chunk-1", title: "片段一", content: "alpha", order_index: 0 },
      { chunk_id: "chunk-2", title: "片段二", content: "beta", order_index: 1 },
      { chunk_id: "chunk-3", title: "片段三", content: "gamma", order_index: 2 },
    ]),
    plans: [
      {
        plan_id: "plan-1",
        name: "方案一",
        target_chunk_ids: ["chunk-1", "chunk-2"],
        root_nodes: [],
      },
    ],
    shared_root_nodes: [],
    aggregate_root_nodes: [
      {
        template_node_id: "aggregate-1",
        name: "聚合输出",
        block_type: "field",
        draft_dependency_refs: [
          { ref_type: "chunk_source", chunk_id: "chunk-2" },
          { ref_type: "chunk_plan_node", chunk_id: "chunk-2", node_id: "summary-node" },
        ],
        children: [],
      },
    ],
    ui_state: {},
  };
}

describe("project split utils", () => {
  it("merges a chunk with its next neighbor", () => {
    const chunks = makeChunks();
    const merged = mergeChunkWithNeighbor(chunks, "chunk-2", "down", () => "merged-1");

    expect(merged).toHaveLength(2);
    expect(merged[0]).toMatchObject({ chunk_id: "chunk-1", order_index: 0 });
    expect(merged[1]).toMatchObject({
      chunk_id: "merged-1",
      title: "片段二 / 片段三",
      content: "beta\n\ngamma",
      order_index: 1,
    });
  });

  it("resplits a chunk by paragraph boundaries", () => {
    const chunks = normalizeChunkOrder([
      {
        chunk_id: "chunk-1",
        title: "片段一",
        content: "第一段\n\n第二段\n\n第三段",
        order_index: 0,
      },
    ]);

    const result = resplitChunk(chunks, "chunk-1", "paragraph", "", (() => {
      let index = 0;
      return () => `new-${++index}`;
    })());

    expect(result.error).toBeUndefined();
    expect(result.chunks).toEqual([
      { chunk_id: "chunk-1", title: "片段一 01", content: "第一段", order_index: 0 },
      { chunk_id: "new-1", title: "片段一 02", content: "第二段", order_index: 1 },
      { chunk_id: "new-2", title: "片段一 03", content: "第三段", order_index: 2 },
    ]);
  });

  it("returns an error when custom separator resplit is invalid", () => {
    const chunks = normalizeChunkOrder([
      { chunk_id: "chunk-1", title: "片段一", content: "only one part", order_index: 0 },
    ]);

    const result = resplitChunk(chunks, "chunk-1", "separator", "###");

    expect(result.chunks).toBeUndefined();
    expect(result.error).toBe("没有拆出多个有效片段，请调整正文或分隔方式。");
  });

  it("migrates plan targets and draft refs when merging payload chunks", () => {
    const payload = makePayload();
    const merged = mergePayloadChunks(payload, "chunk-2", "down");

    expect(merged.chunks.map((chunk) => chunk.chunk_id)).toEqual(["chunk-1", "chunk-2"]);
    expect(merged.plans[0].target_chunk_ids).toEqual(["chunk-1", "chunk-2"]);
    expect(merged.aggregate_root_nodes[0].draft_dependency_refs).toEqual([
      { ref_type: "chunk_source", chunk_id: "chunk-2" },
      { ref_type: "chunk_plan_node", chunk_id: "chunk-2", node_id: "summary-node" },
    ]);
  });

  it("expands plan targets and refs when resplitting a payload chunk", () => {
    const payload = makePayload();
    payload.chunks = normalizeChunkOrder([
      {
        chunk_id: "chunk-2",
        title: "片段二",
        content: "part A\n\npart B",
        order_index: 0,
      },
    ]);
    payload.plans[0].target_chunk_ids = ["chunk-2"];

    const result = resplitPayloadChunk(payload, "chunk-2", "paragraph", "", (() => {
      let index = 0;
      return () => `extra-${++index}`;
    })());

    expect(result.error).toBeUndefined();
    expect(result.payload?.chunks.map((chunk) => chunk.chunk_id)).toEqual(["chunk-2", "extra-1"]);
    expect(result.payload?.plans[0].target_chunk_ids).toEqual(["chunk-2", "extra-1"]);
    expect(result.payload?.aggregate_root_nodes[0].draft_dependency_refs).toEqual([
      { ref_type: "chunk_source", chunk_id: "chunk-2" },
      { ref_type: "chunk_source", chunk_id: "extra-1" },
      { ref_type: "chunk_plan_node", chunk_id: "chunk-2", node_id: "summary-node" },
      { ref_type: "chunk_plan_node", chunk_id: "extra-1", node_id: "summary-node" },
    ]);
  });

  it("removes dangling plan targets and draft refs when deleting a chunk", () => {
    const payload = makePayload();
    const next = removePayloadChunk(payload, "chunk-2");

    expect(next.chunks.map((chunk) => chunk.chunk_id)).toEqual(["chunk-1", "chunk-3"]);
    expect(next.plans[0].target_chunk_ids).toEqual(["chunk-1"]);
    expect(next.aggregate_root_nodes[0].draft_dependency_refs).toEqual([]);
  });
});
