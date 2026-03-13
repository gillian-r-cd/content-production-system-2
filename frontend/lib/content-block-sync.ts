// frontend/lib/content-block-sync.ts
// 功能: 统一 ContentBlock 的树/扁平同步、变更令牌计算与局部回写
// 主要导出: flattenBlockTree(), createContentBlockSnapshot(), findBlockInTree(), replaceBlockInTree(), replaceBlockInFlat()
// 数据结构: ContentBlockSnapshot（tree + flat + syncToken），syncToken 基于 updated_at 与树结构生成

import type { ContentBlock } from "@/lib/api";

export interface ContentBlockSnapshot {
  tree: ContentBlock[];
  flat: ContentBlock[];
  syncToken: string;
}

function normalizeFlatBlock(block: ContentBlock): ContentBlock {
  return {
    ...block,
    children: [],
  };
}

function mergeBlockSnapshot(existing: ContentBlock, incoming: ContentBlock): ContentBlock {
  const nextChildren =
    incoming.children && incoming.children.length > 0
      ? incoming.children
      : existing.children;

  return {
    ...existing,
    ...incoming,
    children: nextChildren,
  };
}

export function flattenBlockTree(blocks: ContentBlock[]): ContentBlock[] {
  const flat: ContentBlock[] = [];

  const visit = (blockList: ContentBlock[]) => {
    for (const block of blockList) {
      flat.push(normalizeFlatBlock(block));
      if (block.children && block.children.length > 0) {
        visit(block.children);
      }
    }
  };

  visit(blocks);
  return flat;
}

export function buildBlockSubtreeSyncToken(block: ContentBlock): string {
  const childToken = (block.children || []).map(buildBlockSubtreeSyncToken).join(",");

  return [
    block.id,
    block.updated_at || "",
    block.status || "",
    block.parent_id || "",
    String(block.order_index ?? ""),
    childToken,
  ].join("|");
}

export function buildBlockTreeSyncToken(blocks: ContentBlock[]): string {
  return blocks.map(buildBlockSubtreeSyncToken).join("||");
}

export function createContentBlockSnapshot(tree: ContentBlock[]): ContentBlockSnapshot {
  return {
    tree,
    flat: flattenBlockTree(tree),
    syncToken: buildBlockTreeSyncToken(tree),
  };
}

export function findBlockInTree(blocks: ContentBlock[], blockId: string): ContentBlock | null {
  for (const block of blocks) {
    if (block.id === blockId) {
      return block;
    }
    if (block.children && block.children.length > 0) {
      const nested = findBlockInTree(block.children, blockId);
      if (nested) {
        return nested;
      }
    }
  }
  return null;
}

export function replaceBlockInTree(blocks: ContentBlock[], incoming: ContentBlock): ContentBlock[] {
  let changed = false;

  const nextBlocks = blocks.map((block) => {
    if (block.id === incoming.id) {
      changed = true;
      return mergeBlockSnapshot(block, incoming);
    }

    if (!block.children || block.children.length === 0) {
      return block;
    }

    const nextChildren = replaceBlockInTree(block.children, incoming);
    if (nextChildren !== block.children) {
      changed = true;
      return {
        ...block,
        children: nextChildren,
      };
    }

    return block;
  });

  return changed ? nextBlocks : blocks;
}

export function replaceBlockInFlat(blocks: ContentBlock[], incoming: ContentBlock): ContentBlock[] {
  const normalizedIncoming = normalizeFlatBlock(incoming);
  let changed = false;

  const nextBlocks = blocks.map((block) => {
    if (block.id !== incoming.id) {
      return block;
    }
    changed = true;
    return normalizedIncoming;
  });

  return changed ? nextBlocks : blocks;
}
