// frontend/components/agent-panel-group.tsx
// 功能：多窗格 Agent 对话区域，支持 1-3 个 AgentPanel 并列展示
// 每个窗格完全独立（对话、消息、建议卡片、模式），共享只读上下文（项目、内容块）

"use client";

import { useState, useEffect, useCallback } from "react";
import { AgentPanel } from "./agent-panel";
import type { ContentBlock, AgentSelectionRef } from "@/lib/api";

const LS_KEY = "agent-pane-count";
const PER_PANE_WIDTH = 384; // 每格建议宽度（px），用于上报给父组件
const MAX_PANES = 3;
const PANE_LABELS = ["A", "B", "C"] as const;

interface AgentPanelGroupProps {
  projectId: string | null;
  projectLocale?: string | null;
  allBlocks?: ContentBlock[];
  onContentUpdate?: () => void;
  externalMessage?: string | null;
  onExternalMessageConsumed?: () => void;
  externalSelection?: AgentSelectionRef | null;
  onExternalSelectionConsumed?: () => void;
  /** 窗格数量变化时通知父组件（用于自动扩展右栏宽度） */
  onPaneCountChange?: (count: number, targetWidth: number) => void;
}

export function AgentPanelGroup({
  projectId,
  projectLocale,
  allBlocks,
  onContentUpdate,
  externalMessage,
  onExternalMessageConsumed,
  externalSelection,
  onExternalSelectionConsumed,
  onPaneCountChange,
}: AgentPanelGroupProps) {
  // 窗格数量（持久化）
  const [paneCount, setPaneCount] = useState<number>(() => {
    if (typeof window === "undefined") return 1;
    const saved = parseInt(localStorage.getItem(LS_KEY) || "1", 10);
    return Math.min(MAX_PANES, Math.max(1, isNaN(saved) ? 1 : saved));
  });

  // 当前接收外部消息/选区的目标窗格索引（默认第 0 格）
  const [activePaneIndex, setActivePaneIndex] = useState(0);

  // 每个窗格独立的 externalMessage（最多 MAX_PANES 个槽）
  const [paneMessages, setPaneMessages] = useState<(string | null)[]>(
    () => Array(MAX_PANES).fill(null)
  );
  // 每个窗格独立的 externalSelection
  const [paneSelections, setPaneSelections] = useState<(AgentSelectionRef | null)[]>(
    () => Array(MAX_PANES).fill(null)
  );

  // 外部消息到达 → 路由到活跃窗格
  useEffect(() => {
    if (!externalMessage) return;
    setPaneMessages((prev) => {
      const next = [...prev];
      next[activePaneIndex] = externalMessage;
      return next;
    });
    onExternalMessageConsumed?.();
  }, [externalMessage]); // eslint-disable-line react-hooks/exhaustive-deps

  // 外部选区到达 → 路由到活跃窗格
  useEffect(() => {
    if (!externalSelection) return;
    setPaneSelections((prev) => {
      const next = [...prev];
      next[activePaneIndex] = externalSelection;
      return next;
    });
    onExternalSelectionConsumed?.();
  }, [externalSelection]); // eslint-disable-line react-hooks/exhaustive-deps

  // 窗格数量变化时：持久化 + 通知父组件
  const applyPaneCount = useCallback(
    (count: number) => {
      const clamped = Math.min(MAX_PANES, Math.max(1, count));
      setPaneCount(clamped);
      try { localStorage.setItem(LS_KEY, String(clamped)); } catch { /* ignore */ }
      onPaneCountChange?.(clamped, clamped * PER_PANE_WIDTH);
    },
    [onPaneCountChange]
  );

  // 初始化时上报当前窗格数（让父组件在刷新后也能恢复宽度）
  useEffect(() => {
    onPaneCountChange?.(paneCount, paneCount * PER_PANE_WIDTH);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const addPane = useCallback(() => {
    applyPaneCount(paneCount + 1);
  }, [paneCount, applyPaneCount]);

  const closeLastPane = useCallback(() => {
    const newCount = paneCount - 1;
    // 如果活跃窗格是被关闭的那格，退到前一格
    setActivePaneIndex((i) => Math.min(i, newCount - 1));
    applyPaneCount(newCount);
  }, [paneCount, applyPaneCount]);

  return (
    <div className="flex h-full">
      {Array.from({ length: paneCount }, (_, i) => (
        <div
          key={`pane-${i}`}
          className={`flex-1 min-w-0 overflow-hidden flex flex-col${i > 0 ? " border-l border-surface-3" : ""}`}
        >
          <AgentPanel
            // 保持稳定 key（不随 paneCount 变化重建已有窗格）
            key={`agent-pane-${i}`}
            projectId={projectId}
            projectLocale={projectLocale}
            allBlocks={allBlocks}
            onContentUpdate={onContentUpdate}
            externalMessage={paneMessages[i]}
            onExternalMessageConsumed={() =>
              setPaneMessages((prev) => {
                const next = [...prev];
                next[i] = null;
                return next;
              })
            }
            externalSelection={paneSelections[i]}
            onExternalSelectionConsumed={() =>
              setPaneSelections((prev) => {
                const next = [...prev];
                next[i] = null;
                return next;
              })
            }
            // 多窗格控制 props
            paneLabel={paneCount > 1 ? PANE_LABELS[i] : undefined}
            isActivePaneTarget={activePaneIndex === i}
            onSetActivePaneTarget={() => setActivePaneIndex(i)}
            onAddPane={paneCount < MAX_PANES && i === paneCount - 1 ? addPane : undefined}
            onClosePane={paneCount > 1 && i === paneCount - 1 ? closeLastPane : undefined}
          />
        </div>
      ))}
    </div>
  );
}
