// 功能: 回归测试 ContentPanel 在切换 selectedBlock.id 时会重新挂载编辑器
// 主要测试: `key={selectedBlock.id}` 是否生效，避免编辑器跨块复用旧本地状态
// 数据结构: ContentBlock

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ContentBlock } from "@/lib/api";
import { ContentPanel } from "./content-panel";

const editorMountSpy = vi.hoisted(() => vi.fn());

vi.mock("./content-block-editor", () => ({
  ContentBlockEditor: ({ block }: { block: ContentBlock }) => {
    React.useEffect(() => {
      editorMountSpy(block.id);
    }, [block.id]);

    return <div data-testid="content-block-editor">{block.id}</div>;
  },
}));

vi.mock("./content-block-card", () => ({
  ContentBlockCard: ({ block }: { block: ContentBlock }) => <div>{block.id}</div>,
}));

vi.mock("./channel-selector", () => ({
  ChannelSelector: () => <div>channel-selector</div>,
}));

vi.mock("./research-panel", () => ({
  ResearchPanel: () => <div>research-panel</div>,
}));

vi.mock("./eval-phase-panel", () => ({
  EvalPhasePanel: () => <div>eval-phase-panel</div>,
}));

vi.mock("./proposal-selector", () => ({
  ProposalSelector: () => <div>proposal-selector</div>,
}));

function buildBlock(id: string): ContentBlock {
  return {
    id,
    project_id: "project-1",
    parent_id: null,
    name: `内容块 ${id}`,
    block_type: "field",
    depth: 0,
    order_index: 0,
    content: `内容 ${id}`,
    status: "completed",
    ai_prompt: "",
    constraints: {},
    pre_questions: [],
    pre_answers: {},
    depends_on: [],
    special_handler: null,
    need_review: false,
    auto_generate: false,
    needs_regeneration: false,
    is_collapsed: false,
    model_override: null,
    children: [],
    created_at: "2026-03-13T00:00:00",
    updated_at: "2026-03-13T00:00:00",
  };
}

describe("ContentPanel editor remount", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("remounts the editor when selectedBlock.id changes", () => {
    const firstBlock = buildBlock("block-a");
    const secondBlock = buildBlock("block-b");

    const { rerender } = render(
      <ContentPanel
        projectId="project-1"
        projectLocale="zh-CN"
        selectedBlock={firstBlock}
        allBlocks={[firstBlock, secondBlock]}
      />,
    );

    expect(screen.getByTestId("content-block-editor")).toHaveTextContent("block-a");
    expect(editorMountSpy).toHaveBeenCalledTimes(1);
    expect(editorMountSpy).toHaveBeenNthCalledWith(1, "block-a");

    rerender(
      <ContentPanel
        projectId="project-1"
        projectLocale="zh-CN"
        selectedBlock={secondBlock}
        allBlocks={[firstBlock, secondBlock]}
      />,
    );

    expect(screen.getByTestId("content-block-editor")).toHaveTextContent("block-b");
    expect(editorMountSpy).toHaveBeenCalledTimes(2);
    expect(editorMountSpy).toHaveBeenNthCalledWith(2, "block-b");
  });
});
