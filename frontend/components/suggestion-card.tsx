// frontend/components/suggestion-card.tsx
// 功能: Suggestion Card 组件 — Agent 修改建议的展示与交互
// 主要组件: SuggestionCard, UndoToast
// 数据结构: SuggestionCardData (pending/accepted/rejected/superseded/undone)
// 交互: 应用(confirm API) / 拒绝(confirm API) / 追问(注入上下文)

"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import { API_BASE } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

// ============== Types ==============

export type SuggestionStatus = "pending" | "accepted" | "rejected" | "superseded" | "undone";

export interface SuggestionCardData {
  id: string;
  target_field: string;
  summary: string;
  reason?: string;
  diff_preview: string;
  edits_count: number;
  group_id?: string;
  group_summary?: string;
  status: SuggestionStatus;
  // Undo 信息（confirm API 返回后填充）
  entity_id?: string;
  version_id?: string;
}

interface SuggestionCardProps {
  data: SuggestionCardData;
  projectId: string;
  onStatusChange: (id: string, status: SuggestionStatus, undoInfo?: { entity_id: string; version_id: string }) => void;
  onFollowUp: (data: SuggestionCardData) => void;
  onContentUpdate?: () => void;
}

// ============== Undo Toast ==============

interface UndoToastProps {
  entityId: string;
  versionId: string;
  targetField: string;
  onUndo: () => void;
  onExpire: () => void;
}

export function UndoToast({ entityId, versionId, targetField, onUndo, onExpire }: UndoToastProps) {
  const [remaining, setRemaining] = useState(15);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    timerRef.current = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          onExpire();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [onExpire]);

  const handleUndo = async () => {
    if (loading) return;
    setLoading(true);
    if (timerRef.current) clearInterval(timerRef.current);
    try {
      const resp = await fetch(`${API_BASE}/api/versions/${entityId}/rollback/${versionId}`, {
        method: "POST",
      });
      if (resp.ok) {
        onUndo();
      } else {
        console.error("Rollback failed:", await resp.text());
      }
    } catch (e) {
      console.error("Rollback error:", e);
    } finally {
      setLoading(false);
    }
  };

  const progress = (remaining / 15) * 100;

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-surface-2 border border-surface-3 rounded-lg shadow-lg animate-in slide-in-from-bottom-2">
      <span className="text-sm text-zinc-300">
        修改已应用到「{targetField}」
      </span>
      <button
        onClick={handleUndo}
        disabled={loading}
        className="px-2 py-1 text-xs text-amber-400 hover:text-amber-300 hover:bg-surface-3 rounded transition-colors disabled:opacity-50"
      >
        {loading ? "撤回中..." : "↩ 撤回"}
      </button>
      <div className="w-16 h-1 bg-surface-4 rounded-full overflow-hidden">
        <div
          className="h-full bg-amber-500 transition-all duration-1000 ease-linear"
          style={{ width: `${progress}%` }}
        />
      </div>
      <span className="text-xs text-zinc-500">{remaining}s</span>
    </div>
  );
}

// ============== SuggestionCard ==============

export function SuggestionCard({ data, projectId, onStatusChange, onFollowUp, onContentUpdate }: SuggestionCardProps) {
  const [loading, setLoading] = useState(false);

  // 状态样式映射
  const statusStyles: Record<SuggestionStatus, string> = {
    pending: "border-l-4 border-l-blue-500 bg-surface-2",
    accepted: "border-l-4 border-l-green-500 bg-surface-2 opacity-80",
    rejected: "border-l-4 border-l-zinc-600 bg-surface-2 opacity-50",
    superseded: "border-l-4 border-l-zinc-600 bg-surface-2 opacity-60 border-dashed",
    undone: "border-l-4 border-l-zinc-600 border-dashed bg-surface-2 opacity-50",
  };

  const statusLabels: Record<SuggestionStatus, string> = {
    pending: "",
    accepted: "✓ 已应用",
    rejected: "已拒绝",
    superseded: "↪ 已被新建议替代",
    undone: "↩ 已撤回",
  };

  const callConfirmAPI = useCallback(async (action: "accept" | "reject") => {
    if (loading) return;
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/agent/confirm-suggestion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          suggestion_id: data.id,
          action,
        }),
      });

      if (!resp.ok) {
        const errText = await resp.text();
        console.error(`Confirm API ${action} failed:`, errText);
        return;
      }

      const result = await resp.json();

      if (action === "accept" && result.success) {
        // 提取 undo 信息
        const appliedCard = result.applied_cards?.[0];
        onStatusChange(data.id, "accepted", appliedCard ? {
          entity_id: appliedCard.entity_id,
          version_id: appliedCard.version_id,
        } : undefined);
        if (onContentUpdate) onContentUpdate();
      } else if (action === "reject" && result.success) {
        onStatusChange(data.id, "rejected");
      }
    } catch (e) {
      console.error(`Confirm API ${action} error:`, e);
    } finally {
      setLoading(false);
    }
  }, [data.id, projectId, loading, onStatusChange, onContentUpdate]);

  const isPending = data.status === "pending";

  return (
    <div className={cn(
      "rounded-lg p-4 my-2 transition-all duration-200",
      statusStyles[data.status],
    )}>
      {/* 头部: summary + target */}
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-zinc-200">
              {data.summary}
            </span>
          </div>
          <span className="text-xs text-zinc-500">
            目标: {data.target_field} · {data.edits_count} 处修改
          </span>
        </div>
        {data.status !== "pending" && (
          <span className={cn(
            "text-xs px-2 py-0.5 rounded",
            data.status === "accepted" && "text-green-400 bg-green-900/20",
            data.status === "rejected" && "text-zinc-500",
            data.status === "superseded" && "text-zinc-500",
            data.status === "undone" && "text-zinc-500",
          )}>
            {statusLabels[data.status]}
          </span>
        )}
      </div>

      {/* Diff 预览 */}
      {data.diff_preview && (
        <div className="my-2 p-3 bg-surface-1 rounded text-sm overflow-x-auto max-h-64 overflow-y-auto">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeRaw]}
            components={{
              del: ({ children }) => <del className="bg-red-900/30 text-red-300 line-through">{children}</del>,
              ins: ({ children }) => <ins className="bg-green-900/30 text-green-300 no-underline">{children}</ins>,
              p: ({ children }) => <p className="mb-1 last:mb-0">{children}</p>,
            }}
          >
            {data.diff_preview}
          </ReactMarkdown>
        </div>
      )}

      {/* 修改原因 */}
      {data.reason && (
        <p className="text-xs text-zinc-500 mt-1 mb-2">
          原因: {data.reason}
        </p>
      )}

      {/* 操作按钮 — 仅 pending 状态显示 */}
      {isPending && (
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => callConfirmAPI("accept")}
            disabled={loading}
            className="px-3 py-1.5 text-xs bg-green-600/80 hover:bg-green-600 text-white rounded transition-colors disabled:opacity-50"
          >
            {loading ? "处理中..." : "✅ 应用"}
          </button>
          <button
            onClick={() => callConfirmAPI("reject")}
            disabled={loading}
            className="px-3 py-1.5 text-xs bg-surface-4 hover:bg-zinc-600 text-zinc-300 rounded transition-colors disabled:opacity-50"
          >
            ❌ 拒绝
          </button>
          <button
            onClick={() => onFollowUp(data)}
            disabled={loading}
            className="px-3 py-1.5 text-xs bg-surface-4 hover:bg-zinc-600 text-zinc-300 rounded transition-colors disabled:opacity-50"
          >
            💬 追问
          </button>
        </div>
      )}

      {/* superseded 状态仍可应用（回退选项） */}
      {data.status === "superseded" && (
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => callConfirmAPI("accept")}
            disabled={loading}
            className="px-3 py-1.5 text-xs bg-surface-4 hover:bg-zinc-600 text-zinc-400 rounded transition-colors disabled:opacity-50"
          >
            仍然应用此版本
          </button>
        </div>
      )}
    </div>
  );
}

