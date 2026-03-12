// frontend/components/suggestion-card.tsx
// 功能: Suggestion Card / SuggestionGroup 组件 — Agent 修改建议的展示与交互
// 主要组件: SuggestionCard, SuggestionGroup, UndoToast
// 数据结构: SuggestionCardData (pending/accepted/rejected/superseded/undone)
// 交互: 应用(confirm API) / 拒绝(confirm API) / 追问(注入上下文) / 部分应用(partial)

"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useUiIsJa } from "@/lib/ui-locale";
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
  // 关联的 AI 消息 ID — 用于在消息流中 inline 渲染卡片
  messageId?: string;
  // 产生此卡片的 Agent 模式（用于按 mode 隔离渲染）
  mode?: string;
  // Undo 信息（confirm API 返回后填充）
  entity_id?: string;
  version_id?: string;
}

interface SuggestionCardProps {
  data: SuggestionCardData;
  projectId: string;
  projectLocale?: string | null;
  onStatusChange: (id: string, status: SuggestionStatus, undoInfo?: { entity_id: string; version_id: string }) => void;
  onFollowUp: (data: SuggestionCardData) => void;
  onContentUpdate?: () => void;
}

// ============== Undo Toast ==============

export interface RollbackTarget {
  entity_id: string;
  version_id: string;
}

interface UndoToastProps {
  entityId: string;
  versionId: string;
  targetField: string;
  projectLocale?: string | null;
  onUndo: () => void;
  onExpire: () => void;
  /** Group 全部撤回时使用：多个 rollback 目标 */
  rollbackTargets?: RollbackTarget[];
}

export function UndoToast({ entityId, versionId, targetField, projectLocale, onUndo, onExpire, rollbackTargets }: UndoToastProps) {
  const isJa = useUiIsJa(projectLocale);
  const [remaining, setRemaining] = useState(15);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    timerRef.current = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          // 异步调用 onExpire，避免在 setState updater 内触发父组件 setState
          setTimeout(onExpire, 0);
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
      // 如果有多个 rollback 目标（Group 全部撤回），并行回滚
      const targets = rollbackTargets && rollbackTargets.length > 0
        ? rollbackTargets.filter((t) => t.version_id)
        : versionId ? [{ entity_id: entityId, version_id: versionId }] : [];

      const results = await Promise.allSettled(
        targets.map((t) =>
          fetch(`${API_BASE}/api/versions/${t.entity_id}/rollback/${t.version_id}`, {
            method: "POST",
          })
        )
      );

      const allOk = results.every((r) => r.status === "fulfilled" && (r.value as Response).ok);
      if (allOk) {
        onUndo();
      } else {
        const failed = results.filter((r) => r.status === "rejected" || !(r.value as Response).ok);
        console.error(`Rollback: ${results.length - failed.length}/${results.length} succeeded`);
        // 部分成功也执行 onUndo（用户可通过版本历史面板处理剩余的）
        onUndo();
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
        {isJa ? `変更を「${targetField}」へ適用しました` : `修改已应用到「${targetField}」`}
      </span>
      <button
        onClick={handleUndo}
        disabled={loading}
        className="px-2 py-1 text-xs text-amber-400 hover:text-amber-300 hover:bg-surface-3 rounded transition-colors disabled:opacity-50"
      >
        {loading ? (isJa ? "取り消し中..." : "撤回中...") : (isJa ? "↩ 元に戻す" : "↩ 撤回")}
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

function getStatusLabels(isJa: boolean): Record<SuggestionStatus, string> {
  return {
    pending: "",
    accepted: isJa ? "✓ 適用済み" : "✓ 已应用",
    rejected: isJa ? "却下済み" : "已拒绝",
    superseded: isJa ? "↪ 新しい提案で置換済み" : "↪ 已被新建议替代",
    undone: isJa ? "↩ 取り消し済み" : "↩ 已撤回",
  };
}

export function SuggestionCard({ data, projectId, projectLocale, onStatusChange, onFollowUp, onContentUpdate }: SuggestionCardProps) {
  const isJa = useUiIsJa(projectLocale);
  const [loading, setLoading] = useState(false);

  // 状态样式映射
  const statusStyles: Record<SuggestionStatus, string> = {
    pending: "border-l-4 border-l-blue-500 bg-surface-2",
    accepted: "border-l-4 border-l-green-500 bg-surface-2 opacity-80",
    rejected: "border-l-4 border-l-zinc-600 bg-surface-2 opacity-50",
    superseded: "border-l-4 border-l-zinc-600 bg-surface-2 opacity-60 border-dashed",
    undone: "border-l-4 border-l-zinc-600 border-dashed bg-surface-2 opacity-50",
  };

  const statusLabels = getStatusLabels(isJa);

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
            {isJa ? `対象: ${data.target_field} · ${data.edits_count} 件の変更` : `目标: ${data.target_field} · ${data.edits_count} 处修改`}
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
          {isJa ? "理由" : "原因"}: {data.reason}
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
            {loading ? (isJa ? "処理中..." : "处理中...") : (isJa ? "✅ 適用" : "✅ 应用")}
          </button>
          <button
            onClick={() => callConfirmAPI("reject")}
            disabled={loading}
            className="px-3 py-1.5 text-xs bg-surface-4 hover:bg-zinc-600 text-zinc-300 rounded transition-colors disabled:opacity-50"
          >
            {isJa ? "❌ 却下" : "❌ 拒绝"}
          </button>
          <button
            onClick={() => onFollowUp(data)}
            disabled={loading}
            className="px-3 py-1.5 text-xs bg-surface-4 hover:bg-zinc-600 text-zinc-300 rounded transition-colors disabled:opacity-50"
          >
            {isJa ? "💬 追質問" : "💬 追问"}
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
            {isJa ? "この版をそのまま適用" : "仍然应用此版本"}
          </button>
        </div>
      )}
    </div>
  );
}

// ============== SuggestionGroup ==============

interface SuggestionGroupProps {
  groupId: string;
  groupSummary: string;
  cards: SuggestionCardData[];
  projectId: string;
  projectLocale?: string | null;
  onStatusChange: (id: string, status: SuggestionStatus, undoInfo?: { entity_id: string; version_id: string }) => void;
  onFollowUp: (data: SuggestionCardData) => void;
  onContentUpdate?: () => void;
  // 批量操作：全部应用/全部拒绝后回调（携带多个 undoInfo）
  onGroupApplied?: (results: Array<{ card_id: string; entity_id: string; version_id: string }>) => void;
}

export function SuggestionGroup({
  groupId,
  groupSummary,
  cards,
  projectId,
  projectLocale,
  onStatusChange,
  onFollowUp,
  onContentUpdate,
  onGroupApplied,
}: SuggestionGroupProps) {
  const isJa = useUiIsJa(projectLocale);
  const [selected, setSelected] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    cards.forEach((c) => { init[c.id] = true; });
    return init;
  });
  const [loading, setLoading] = useState(false);

  const pendingCards = cards.filter((c) => c.status === "pending");
  const allDone = pendingCards.length === 0;
  const selectedCount = pendingCards.filter((c) => selected[c.id]).length;

  const toggleCard = (cardId: string) => {
    setSelected((prev) => ({ ...prev, [cardId]: !prev[cardId] }));
  };

  // 批量应用（partial: 仅勾选的 card）
  const handleGroupAccept = useCallback(async () => {
    if (loading) return;
    const toApply = pendingCards.filter((c) => selected[c.id]);
    if (toApply.length === 0) return;
    setLoading(true);

    try {
      const resp = await fetch(`${API_BASE}/api/agent/confirm-suggestion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          suggestion_id: groupId,
          action: toApply.length === pendingCards.length ? "accept" : "partial",
          accepted_card_ids: toApply.map((c) => c.id),
        }),
      });

      if (!resp.ok) {
        console.error("Group confirm failed:", await resp.text());
        return;
      }

      const result = await resp.json();
      if (result.success && result.applied_cards) {
        // 逐 card 更新状态
        for (const applied of result.applied_cards) {
          onStatusChange(applied.card_id, "accepted", {
            entity_id: applied.entity_id,
            version_id: applied.version_id,
          });
        }
        // 未勾选的 card 保持 pending
        if (onContentUpdate) onContentUpdate();
        if (onGroupApplied) onGroupApplied(result.applied_cards);
      }
    } catch (e) {
      console.error("Group confirm error:", e);
    } finally {
      setLoading(false);
    }
  }, [loading, pendingCards, selected, projectId, groupId, onStatusChange, onContentUpdate, onGroupApplied]);

  // 全部拒绝
  const handleGroupReject = useCallback(async () => {
    if (loading) return;
    setLoading(true);

    try {
      const resp = await fetch(`${API_BASE}/api/agent/confirm-suggestion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          suggestion_id: groupId,
          action: "reject",
        }),
      });

      if (!resp.ok) {
        console.error("Group reject failed:", await resp.text());
        return;
      }

      const result = await resp.json();
      if (result.success) {
        pendingCards.forEach((c) => onStatusChange(c.id, "rejected"));
      }
    } catch (e) {
      console.error("Group reject error:", e);
    } finally {
      setLoading(false);
    }
  }, [loading, pendingCards, projectId, groupId, onStatusChange]);

  // 追问：基于整组
  const handleGroupFollowUp = useCallback(() => {
    // 用第一个 pending card 的信息 + 整组摘要
    const firstCard = pendingCards[0] || cards[0];
    if (firstCard) {
      onFollowUp({
        ...firstCard,
        summary: groupSummary || firstCard.summary,
      });
    }
  }, [pendingCards, cards, groupSummary, onFollowUp]);

  return (
    <div className="rounded-lg border border-purple-500/30 bg-surface-2 p-4 my-2">
      {/* Group 头部 */}
      <div className="mb-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs px-2 py-0.5 bg-purple-900/30 text-purple-300 rounded">
            {isJa ? `${cards.length} 件の関連変更` : `${cards.length} 项关联修改`}
          </span>
        </div>
        {groupSummary && (
          <p className="text-sm text-zinc-300">{groupSummary}</p>
        )}
      </div>

      {/* 逐 Card 展示（带勾选框） */}
      <div className="space-y-2">
        {cards.map((card) => (
          <div key={card.id} className="flex items-start gap-2">
            {/* 勾选框：仅 pending 状态可勾选 */}
            {card.status === "pending" ? (
              <label className="flex items-center mt-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected[card.id] ?? true}
                  onChange={() => toggleCard(card.id)}
                  className="w-4 h-4 rounded border-zinc-600 bg-surface-3 text-purple-500 focus:ring-purple-500/50"
                />
              </label>
            ) : (
              <div className="w-4 mt-3" />
            )}
            {/* 简化版 Card（不含独立按钮，按钮在 Group 底部统一管理） */}
            <div className="flex-1">
              <GroupItemCard data={card} isJa={isJa} />
            </div>
          </div>
        ))}
      </div>

      {/* Group 底部操作按钮 — 仅有 pending cards 时显示 */}
      {!allDone && (
        <div className="flex gap-2 mt-4 pt-3 border-t border-surface-3">
          <button
            onClick={handleGroupAccept}
            disabled={loading || selectedCount === 0}
            className="px-3 py-1.5 text-xs bg-green-600/80 hover:bg-green-600 text-white rounded transition-colors disabled:opacity-50"
          >
            {loading ? (isJa ? "処理中..." : "处理中...") : selectedCount === pendingCards.length
              ? (isJa ? `✅ すべて適用 (${selectedCount})` : `✅ 全部应用 (${selectedCount})`)
              : (isJa ? `✅ 選択分を適用 (${selectedCount}/${pendingCards.length})` : `✅ 应用已选 (${selectedCount}/${pendingCards.length})`)
            }
          </button>
          <button
            onClick={handleGroupReject}
            disabled={loading}
            className="px-3 py-1.5 text-xs bg-surface-4 hover:bg-zinc-600 text-zinc-300 rounded transition-colors disabled:opacity-50"
          >
            {isJa ? "❌ すべて却下" : "❌ 全部拒绝"}
          </button>
          <button
            onClick={handleGroupFollowUp}
            disabled={loading}
            className="px-3 py-1.5 text-xs bg-surface-4 hover:bg-zinc-600 text-zinc-300 rounded transition-colors disabled:opacity-50"
          >
            {isJa ? "💬 追質問" : "💬 追问"}
          </button>
        </div>
      )}
    </div>
  );
}

// ============== GroupItemCard (Group 内的简化单 Card) ==============

function GroupItemCard({ data, isJa }: { data: SuggestionCardData; isJa: boolean }) {
  const statusLabels = getStatusLabels(isJa);
  const statusStyles: Record<SuggestionStatus, string> = {
    pending: "border-l-2 border-l-blue-500/50 bg-surface-1",
    accepted: "border-l-2 border-l-green-500/50 bg-surface-1 opacity-80",
    rejected: "border-l-2 border-l-zinc-600/50 bg-surface-1 opacity-50",
    superseded: "border-l-2 border-l-zinc-600/50 bg-surface-1 opacity-60",
    undone: "border-l-2 border-l-zinc-600/50 bg-surface-1 opacity-50",
  };

  return (
    <div className={cn("rounded p-3 my-1 transition-all", statusStyles[data.status])}>
      <div className="flex items-start justify-between mb-1">
        <div>
          <span className="text-sm font-medium text-zinc-200">{data.summary}</span>
          <span className="text-xs text-zinc-500 ml-2">
            {isJa ? `${data.target_field} · ${data.edits_count} 件の変更` : `${data.target_field} · ${data.edits_count} 处修改`}
          </span>
        </div>
        {data.status !== "pending" && (
          <span className="text-xs text-zinc-500">{statusLabels[data.status]}</span>
        )}
      </div>
      {data.diff_preview && (
        <div className="mt-1 p-2 bg-surface-2 rounded text-xs overflow-x-auto max-h-40 overflow-y-auto">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeRaw]}
            components={{
              del: ({ children }) => <del className="bg-red-900/30 text-red-300 line-through">{children}</del>,
              ins: ({ children }) => <ins className="bg-green-900/30 text-green-300 no-underline">{children}</ins>,
              p: ({ children }) => <p className="mb-0.5 last:mb-0">{children}</p>,
            }}
          >
            {data.diff_preview}
          </ReactMarkdown>
        </div>
      )}
      {data.reason && (
        <p className="text-xs text-zinc-500 mt-1">{isJa ? "理由" : "原因"}: {data.reason}</p>
      )}
    </div>
  );
}

