// 功能: 覆盖 ContentBlock 同步工具的核心行为，避免状态同步再次退回有损比较
// 主要测试: syncToken 基于 updated_at、replaceBlockInTree 局部回写、flattenBlockTree 扁平化
// 数据结构: ContentBlock / ContentBlockSnapshot

import { describe, expect, it } from "vitest";

import type { ContentBlock } from "@/lib/api";
import {
  buildBlockTreeSyncToken,
  createContentBlockSnapshot,
  replaceBlockInFlat,
  replaceBlockInTree,
} from "./content-block-sync";

function buildBlock(overrides: Partial<ContentBlock> & Pick<ContentBlock, "id" | "name">): ContentBlock {
  return {
    id: overrides.id,
    project_id: overrides.project_id || "project-1",
    parent_id: overrides.parent_id || null,
    name: overrides.name,
    block_type: overrides.block_type || "field",
    depth: overrides.depth || 0,
    order_index: overrides.order_index || 0,
    content: overrides.content || "",
    status: overrides.status || "pending",
    ai_prompt: overrides.ai_prompt || "",
    constraints: overrides.constraints || {},
    pre_questions: overrides.pre_questions || [],
    pre_answers: overrides.pre_answers || {},
    depends_on: overrides.depends_on || [],
    special_handler: overrides.special_handler || null,
    need_review: overrides.need_review ?? false,
    auto_generate: overrides.auto_generate ?? false,
    needs_regeneration: overrides.needs_regeneration ?? false,
    is_collapsed: overrides.is_collapsed ?? false,
    model_override: overrides.model_override ?? null,
    children: overrides.children || [],
    created_at: overrides.created_at || "2026-03-13T00:00:00",
    updated_at: overrides.updated_at || "2026-03-13T00:00:00",
    version_warning: overrides.version_warning ?? null,
    affected_blocks: overrides.affected_blocks ?? null,
  };
}

describe("content-block-sync", () => {
  it("changes the tree sync token when only updated_at changes", () => {
    const firstTree = [buildBlock({ id: "block-1", name: "标题", content: "AB", updated_at: "2026-03-13T00:00:00" })];
    const secondTree = [buildBlock({ id: "block-1", name: "标题", content: "CD", updated_at: "2026-03-13T00:00:01" })];

    expect(buildBlockTreeSyncToken(secondTree)).not.toBe(buildBlockTreeSyncToken(firstTree));
  });

  it("preserves existing children when locally writing back a field snapshot", () => {
    const child = buildBlock({
      id: "child-1",
      name: "子块",
      parent_id: "group-1",
      depth: 1,
      content: "旧内容",
    });
    const tree = [
      buildBlock({
        id: "group-1",
        name: "分组",
        block_type: "group",
        children: [child],
      }),
    ];

    const updatedChild = buildBlock({
      id: "child-1",
      name: "子块",
      parent_id: "group-1",
      depth: 1,
      content: "新内容",
      updated_at: "2026-03-13T00:00:01",
    });

    const nextTree = replaceBlockInTree(tree, updatedChild);

    expect(nextTree).not.toBe(tree);
    expect(nextTree[0].children[0].content).toBe("新内容");
  });

  it("builds a flat snapshot for dependency lookups", () => {
    const child = buildBlock({
      id: "child-1",
      name: "子块",
      parent_id: "group-1",
      depth: 1,
      content: "内容",
    });
    const snapshot = createContentBlockSnapshot([
      buildBlock({
        id: "group-1",
        name: "分组",
        block_type: "group",
        children: [child],
      }),
    ]);

    expect(snapshot.tree).toHaveLength(1);
    expect(snapshot.flat.map((block) => block.id)).toEqual(["group-1", "child-1"]);
    expect(snapshot.flat[0].children).toEqual([]);
    expect(replaceBlockInFlat(snapshot.flat, { ...child, content: "已更新" })[1].content).toBe("已更新");
  });
});
