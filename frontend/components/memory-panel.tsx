// frontend/components/memory-panel.tsx
// 功能: 项目记忆管理面板 — 显示 Agent 记住了什么，允许查看、编辑、删除、手动添加
// 主要组件: MemoryPanel
// 关联: lib/api.ts (memoriesAPI), agent-panel.tsx (集成入口)

"use client";

import { useState, useEffect, useCallback } from "react";
import { memoriesAPI } from "@/lib/api";
import type { MemoryItemInfo } from "@/lib/api";
import { isJaProjectLocale } from "@/lib/project-locale";
import { useUiLocale } from "@/lib/ui-locale";

interface MemoryPanelProps {
  projectId: string;
  projectLocale?: string | null;
  onClose: () => void;
}

function getModeLabels(locale?: string | null): Record<string, string> {
  if (isJaProjectLocale(locale)) {
    return {
      assistant: "アシスタント",
      strategist: "戦略アドバイザー",
      critic: "レビュアー",
      reader: "対象読者",
      creative: "クリエイティブパートナー",
      manual: "手動追加",
    };
  }
  return {
    assistant: "助手",
    strategist: "策略顾问",
    critic: "审稿人",
    reader: "目标读者",
    creative: "创意伙伴",
    manual: "手动添加",
  };
}

export function MemoryPanel({ projectId, projectLocale, onClose }: MemoryPanelProps) {
  const uiLocale = useUiLocale(projectLocale);
  const isJa = isJaProjectLocale(uiLocale);
  const modeLabels = getModeLabels(uiLocale);
  const [memories, setMemories] = useState<MemoryItemInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [saving, setSaving] = useState(false);

  const loadMemories = useCallback(async () => {
    if (!projectId) return;
    try {
      setLoading(true);
      const data = await memoriesAPI.list(projectId);
      setMemories(data);
    } catch (err) {
      console.error("Failed to load memories:", err);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadMemories();
  }, [loadMemories]);

  // 全局记忆用 _global 作为路径参数，项目记忆用 projectId
  const getMemoryScope = (mem: MemoryItemInfo) =>
    mem.project_id === null ? "_global" : projectId;

  const handleDelete = async (memoryId: string) => {
    const mem = memories.find((m) => m.id === memoryId);
    if (!mem) return;
    try {
      await memoriesAPI.delete(getMemoryScope(mem), memoryId);
      setMemories((prev) => prev.filter((m) => m.id !== memoryId));
    } catch (err) {
      console.error("Failed to delete memory:", err);
    }
  };

  const handleStartEdit = (mem: MemoryItemInfo) => {
    setEditingId(mem.id);
    setEditContent(mem.content);
  };

  const handleSaveEdit = async () => {
    if (!editingId || !editContent.trim()) return;
    const mem = memories.find((m) => m.id === editingId);
    if (!mem) return;
    try {
      setSaving(true);
      const updated = await memoriesAPI.update(getMemoryScope(mem), editingId, {
        content: editContent.trim(),
      });
      setMemories((prev) =>
        prev.map((m) => (m.id === editingId ? updated : m))
      );
      setEditingId(null);
      setEditContent("");
    } catch (err) {
      console.error("Failed to update memory:", err);
    } finally {
      setSaving(false);
    }
  };

  const handleAdd = async () => {
    if (!newContent.trim()) return;
    try {
      setSaving(true);
      const created = await memoriesAPI.create(projectId, {
        content: newContent.trim(),
        source_mode: "manual",
      });
      setMemories((prev) => [...prev, created]);
      setNewContent("");
      setShowAddForm(false);
    } catch (err) {
      console.error("Failed to create memory:", err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* 头部 */}
      <div className="border-b border-surface-3 px-4 py-3 flex items-center justify-between">
        <div>
          <h2 className="font-semibold text-zinc-100 flex items-center gap-2">
            <span>🧠</span>
            <span>{isJa ? "プロジェクト記憶" : "项目记忆"}</span>
            <span className="text-xs text-zinc-500 font-normal">
              {isJa ? `${memories.length} 件` : `${memories.length} 条`}
            </span>
          </h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            {isJa ? "Agent が対話から抽出した重要情報を、モード横断で共有します" : "Agent 从对话中提炼的关键信息，跨模式共享"}
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-zinc-500 hover:text-zinc-300 text-sm px-2 py-1 rounded hover:bg-surface-2 transition"
        >
          {isJa ? "対話へ戻る" : "返回对话"}
        </button>
      </div>

      {/* 记忆列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {loading ? (
          <div className="text-center text-zinc-500 py-8">
            <div className="w-4 h-4 border-2 border-zinc-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            {isJa ? "読み込み中..." : "加载中..."}
          </div>
        ) : memories.length === 0 ? (
          <div className="text-center text-zinc-500 py-8">
            <p className="text-2xl mb-2">🧠</p>
            <p>{isJa ? "記憶はまだありません" : "暂无记忆"}</p>
            <p className="text-xs mt-1">
              {isJa ? "Agent と対話すると、重要情報がここに自動保存されます" : "与 Agent 对话后，关键信息会自动提炼保存在这里"}
            </p>
          </div>
        ) : (
          memories.map((mem) => (
            <div
              key={mem.id}
              className="group bg-surface-2 border border-surface-3 rounded-lg px-3 py-2.5 hover:border-zinc-600 transition"
            >
              {editingId === mem.id ? (
                /* 编辑模式 */
                <div className="space-y-2">
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    className="w-full bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm text-zinc-200 resize-none focus:outline-none focus:border-brand-500"
                    rows={2}
                    autoFocus
                  />
                  <div className="flex gap-2 justify-end">
                    <button
                      onClick={() => setEditingId(null)}
                      className="text-xs text-zinc-500 hover:text-zinc-300 px-2 py-1 rounded hover:bg-surface-3"
                    >
                      {isJa ? "キャンセル" : "取消"}
                    </button>
                    <button
                      onClick={handleSaveEdit}
                      disabled={saving || !editContent.trim()}
                      className="text-xs text-brand-300 hover:text-brand-200 px-2 py-1 rounded hover:bg-brand-500/10 disabled:opacity-50"
                    >
                      {saving ? (isJa ? "保存中..." : "保存中...") : (isJa ? "保存" : "保存")}
                    </button>
                  </div>
                </div>
              ) : (
                /* 显示模式 */
                <>
                  <p className="text-sm text-zinc-200 leading-relaxed">
                    {mem.project_id === null && (
                      <span className="text-xs text-amber-500/80 mr-1.5">{isJa ? "[全体]" : "[全局]"}</span>
                    )}
                    {mem.content}
                  </p>
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="text-xs text-zinc-600">
                      {modeLabels[mem.source_mode] || mem.source_mode}
                      {mem.source_phase ? ` / ${mem.source_phase}` : ""}
                    </span>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => handleStartEdit(mem)}
                        className="text-xs text-zinc-500 hover:text-zinc-300 px-1.5 py-0.5 rounded hover:bg-surface-3"
                        title={isJa ? "編集" : "编辑"}
                      >
                        ✏️
                      </button>
                      <button
                        onClick={() => handleDelete(mem.id)}
                        className="text-xs text-zinc-500 hover:text-red-400 px-1.5 py-0.5 rounded hover:bg-surface-3"
                        title={isJa ? "削除" : "删除"}
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          ))
        )}
      </div>

      {/* 底部：添加记忆 */}
      <div className="p-4 border-t border-surface-3">
        {showAddForm ? (
          <div className="space-y-2">
            <textarea
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              placeholder={isJa ? "記録したい情報を入力してください。例: ユーザーは簡潔な文体を好む" : "输入要记住的信息，如：用户偏好简洁风格..."}
              className="w-full bg-surface-1 border border-surface-3 rounded-lg px-3 py-2 text-sm text-zinc-200 resize-none focus:outline-none focus:border-brand-500 placeholder:text-zinc-600"
              rows={2}
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setShowAddForm(false);
                  setNewContent("");
                }}
                className="text-xs text-zinc-500 hover:text-zinc-300 px-3 py-1.5 rounded hover:bg-surface-3"
              >
                {isJa ? "キャンセル" : "取消"}
              </button>
              <button
                onClick={handleAdd}
                disabled={saving || !newContent.trim()}
                className="text-xs bg-brand-600 text-white px-3 py-1.5 rounded hover:bg-brand-500 disabled:opacity-50 transition"
              >
                {saving ? (isJa ? "追加中..." : "添加中...") : (isJa ? "記憶を追加" : "添加记忆")}
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowAddForm(true)}
            className="w-full text-sm text-zinc-500 hover:text-zinc-300 border border-dashed border-surface-3 hover:border-zinc-500 rounded-lg py-2 transition"
          >
            {isJa ? "+ 記憶を手動追加" : "+ 手动添加记忆"}
          </button>
        )}
      </div>
    </div>
  );
}

