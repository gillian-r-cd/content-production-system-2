// frontend/components/agent-mode-manager.tsx
// 功能: 项目级 Agent 角色管理面板 — 创建、编辑、删除、排序、导入模板
// 主要组件: AgentModeManager
// 数据结构: AgentModeInfo（项目角色实例/系统模板）

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { modesAPI } from "@/lib/api";
import type { AgentModeInfo } from "@/lib/api";
import { useUiIsJa } from "@/lib/ui-locale";
import { sendNotification } from "@/lib/utils";
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2, X } from "lucide-react";

interface AgentModeManagerProps {
  projectId: string;
  projectLocale?: string | null;
  activeModeId: string | null;
  onSelectMode: (modeId: string) => void;
  onClose: () => void;
  onChanged?: (modes: AgentModeInfo[]) => void;
}

interface ModeDraft {
  display_name: string;
  description: string;
  icon: string;
  system_prompt: string;
}

const EMPTY_DRAFT: ModeDraft = {
  display_name: "",
  description: "",
  icon: "🤖",
  system_prompt: "",
};

export function AgentModeManager({
  projectId,
  projectLocale,
  activeModeId,
  onSelectMode,
  onClose,
  onChanged,
}: AgentModeManagerProps) {
  const isJa = useUiIsJa(projectLocale);
  const [modes, setModes] = useState<AgentModeInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingModeId, setEditingModeId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ModeDraft>(EMPTY_DRAFT);
  const onChangedRef = useRef(onChanged);

  const hasModes = modes.length > 0;

  useEffect(() => {
    onChangedRef.current = onChanged;
  }, [onChanged]);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const modeRows = await modesAPI.list(projectId);
      setModes(modeRows);
      onChangedRef.current?.(modeRows);
    } catch (err) {
      console.error("Failed to load agent modes:", err);
      sendNotification(isJa ? "役割一覧の読み込みに失敗しました" : "加载角色列表失败", "error");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const editingMode = useMemo(
    () => modes.find((mode) => mode.id === editingModeId) || null,
    [modes, editingModeId]
  );

  const resetDraft = () => {
    setDraft(EMPTY_DRAFT);
    setEditingModeId(null);
  };

  const startCreate = () => {
    setEditingModeId(null);
    setDraft(EMPTY_DRAFT);
  };

  const startEdit = (mode: AgentModeInfo) => {
    setEditingModeId(mode.id);
    setDraft({
      display_name: mode.display_name,
      description: mode.description || "",
      icon: mode.icon || "🤖",
      system_prompt: mode.system_prompt,
    });
  };

  const reloadAndSelect = async (preferredModeId?: string | null) => {
    const refreshed = await modesAPI.list(projectId);
    setModes(refreshed);
    onChangedRef.current?.(refreshed);
    const nextId =
      (preferredModeId && refreshed.some((mode) => mode.id === preferredModeId) ? preferredModeId : null)
      || refreshed[0]?.id
      || null;
    if (nextId) {
      onSelectMode(nextId);
    }
    return refreshed;
  };

  const handleSave = async () => {
    if (!draft.display_name.trim()) {
      sendNotification(isJa ? "役割名は必須です" : "角色名称不能为空", "error");
      return;
    }
    if (!draft.system_prompt.trim()) {
      sendNotification(isJa ? "役割プロンプトは必須です" : "角色提示词不能为空", "error");
      return;
    }

    try {
      setSaving(true);
      if (editingModeId) {
        await modesAPI.update(editingModeId, {
          display_name: draft.display_name.trim(),
          description: draft.description.trim(),
          icon: draft.icon.trim() || "🤖",
          system_prompt: draft.system_prompt.trim(),
        });
        sendNotification(isJa ? "役割を更新しました" : "角色已更新", "success");
        await reloadAndSelect(editingModeId);
      } else {
        const created = await modesAPI.create({
          project_id: projectId,
          display_name: draft.display_name.trim(),
          description: draft.description.trim(),
          icon: draft.icon.trim() || "🤖",
          system_prompt: draft.system_prompt.trim(),
        });
        sendNotification(isJa ? "役割を作成しました" : "角色已创建", "success");
        await reloadAndSelect(created.id);
      }
      resetDraft();
    } catch (err) {
      console.error("Failed to save agent mode:", err);
      sendNotification(isJa ? "役割の保存に失敗しました" : "保存角色失败", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (mode: AgentModeInfo) => {
    if (!confirm(isJa ? `役割「${mode.display_name}」を削除しますか？` : `确定删除角色「${mode.display_name}」？`)) return;
    try {
      setSaving(true);
      await modesAPI.delete(mode.id);
      sendNotification(isJa ? "役割を削除しました" : "角色已删除", "success");
      const fallbackId = activeModeId === mode.id ? null : activeModeId;
      await reloadAndSelect(fallbackId);
      if (editingModeId === mode.id) {
        resetDraft();
      }
    } catch (err) {
      console.error("Failed to delete agent mode:", err);
      sendNotification(isJa ? "役割の削除に失敗しました" : "删除角色失败", "error");
    } finally {
      setSaving(false);
    }
  };

  const moveMode = async (modeId: string, direction: -1 | 1) => {
    const currentIndex = modes.findIndex((mode) => mode.id === modeId);
    const swapIndex = currentIndex + direction;
    if (currentIndex < 0 || swapIndex < 0 || swapIndex >= modes.length) return;

    const current = modes[currentIndex];
    const target = modes[swapIndex];
    try {
      setSaving(true);
      await Promise.all([
        modesAPI.update(current.id, { sort_order: target.sort_order }),
        modesAPI.update(target.id, { sort_order: current.sort_order }),
      ]);
      await reloadAndSelect(activeModeId);
    } catch (err) {
      console.error("Failed to reorder agent modes:", err);
      sendNotification(isJa ? "役割順の調整に失敗しました" : "调整角色顺序失败", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleImportTemplates = async () => {
    try {
      setSaving(true);
      const result = await modesAPI.importTemplates(projectId);
      const importedCount = result.imported?.length || 0;
      if (importedCount === 0) {
        sendNotification(isJa ? "新たに取り込めるテンプレートはありません" : "没有可导入的新模板", "success");
      } else {
        sendNotification(isJa ? `${importedCount} 件の既定役割を取り込みました` : `已导入 ${importedCount} 个默认角色`, "success");
      }
      const refreshed = await reloadAndSelect(activeModeId);
      if (!editingModeId && refreshed.length > 0) {
        startEdit(refreshed[0]);
      }
    } catch (err) {
      console.error("Failed to import templates:", err);
      const message = err instanceof Error ? err.message : "";
      if (message.includes("No templates found")) {
        sendNotification(isJa ? "取り込める既定テンプレートがありません" : "当前没有可导入的默认模板", "error");
      } else {
        sendNotification(isJa ? "テンプレートの取り込みに失敗しました" : "导入模板失败", "error");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div
        className="relative flex h-[86vh] max-h-[820px] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-surface-3 bg-surface-1 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
      <div className="border-b border-surface-3 px-5 py-4 flex items-center justify-between">
        <div>
          <h2 className="font-semibold text-zinc-100">{isJa ? "Agent 役割" : "Agent 角色"}</h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            {isJa ? "役割名とプロンプトはこのプロジェクトで管理します。説明は任意です。" : "角色名称和提示词由当前项目维护，简介为可选项"}
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-zinc-500 hover:text-zinc-300 p-1 rounded hover:bg-surface-2 transition"
        >
          <X size={16} />
        </button>
      </div>

      <div className="px-5 py-3 border-b border-surface-3 flex items-center gap-2">
        <button
          onClick={startCreate}
          disabled={saving}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-600 text-white text-sm hover:bg-brand-500 disabled:opacity-50 transition"
        >
          <Plus size={14} />
          <span>{isJa ? "役割を新規作成" : "新建角色"}</span>
        </button>
        <button
          onClick={handleImportTemplates}
          disabled={saving || loading}
          className="px-3 py-1.5 rounded-lg border border-surface-3 text-sm text-zinc-300 hover:bg-surface-2 disabled:opacity-50 transition"
        >
          {isJa ? "既定テンプレートを取り込む" : "导入默认模板"}
        </button>
        {loading && (
          <span className="text-xs text-zinc-500">{isJa ? "役割設定を読み込み中..." : "正在加载角色配置..."}</span>
        )}
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-[280px_minmax(0,1fr)]">
        <div className="border-r border-surface-3 overflow-y-auto p-3 space-y-2">
          {loading ? (
            <div className="h-full flex items-center justify-center text-sm text-zinc-500">
              {isJa ? "読み込み中..." : "加载中..."}
            </div>
          ) : !hasModes ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-zinc-500 px-4">
              <p className="text-sm text-zinc-300">{isJa ? "このプロジェクトにはまだ役割がありません" : "当前项目还没有角色"}</p>
              <p className="text-xs mt-1">{isJa ? "役割を新規作成するか、既定テンプレートを取り込んでから編集できます。" : "可以新建角色，或先导入默认模板后再修改。"}</p>
            </div>
          ) : (
            modes.map((mode, index) => (
              <div
                key={mode.id}
                className={`rounded-xl border p-3 transition ${
                  activeModeId === mode.id
                    ? "border-brand-500 bg-brand-500/10"
                    : "border-surface-3 bg-surface-2"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <button
                    onClick={() => onSelectMode(mode.id)}
                    className="flex-1 text-left"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-base leading-none">{mode.icon}</span>
                      <span className="text-sm font-medium text-zinc-100">{mode.display_name}</span>
                    </div>
                    {mode.description && (
                      <p className="text-xs text-zinc-500 mt-1 line-clamp-2">{mode.description}</p>
                    )}
                  </button>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => moveMode(mode.id, -1)}
                      disabled={saving || index === 0}
                      className="p-1 rounded text-zinc-500 hover:text-zinc-300 hover:bg-surface-1 disabled:opacity-40 transition"
                      title={isJa ? "上へ移動" : "上移"}
                    >
                      <ArrowUp size={14} />
                    </button>
                    <button
                      onClick={() => moveMode(mode.id, 1)}
                      disabled={saving || index === modes.length - 1}
                      className="p-1 rounded text-zinc-500 hover:text-zinc-300 hover:bg-surface-1 disabled:opacity-40 transition"
                      title={isJa ? "下へ移動" : "下移"}
                    >
                      <ArrowDown size={14} />
                    </button>
                    <button
                      onClick={() => startEdit(mode)}
                      className="p-1 rounded text-zinc-500 hover:text-zinc-300 hover:bg-surface-1 transition"
                      title={isJa ? "編集" : "编辑"}
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => handleDelete(mode)}
                      disabled={saving}
                      className="p-1 rounded text-zinc-500 hover:text-red-400 hover:bg-surface-1 disabled:opacity-40 transition"
                      title={isJa ? "削除" : "删除"}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="overflow-y-auto p-4">
          <div className="max-w-3xl space-y-4">
            <div>
              <h3 className="text-sm font-medium text-zinc-100">
                {editingMode ? (isJa ? `役割を編集: ${editingMode.display_name}` : `编辑角色：${editingMode.display_name}`) : (isJa ? "役割を新規作成" : "新建角色")}
              </h3>
              <p className="text-xs text-zinc-500 mt-1">
                {isJa ? "必須: 役割名、役割プロンプト。任意: 役割説明、アイコン。" : "必填：角色名称、角色提示词。可选：角色简介、图标。"}
              </p>
            </div>

            <div className="grid gap-4">
              <label className="block">
                <span className="block text-xs text-zinc-400 mb-1.5">{isJa ? "役割名" : "角色名称"}</span>
                <input
                  value={draft.display_name}
                  onChange={(e) => setDraft((prev) => ({ ...prev, display_name: e.target.value }))}
                  className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder={isJa ? "例: グロースコーチ" : "例如：增长教练"}
                />
              </label>

              <label className="block">
                <span className="block text-xs text-zinc-400 mb-1.5">{isJa ? "役割説明（任意）" : "角色简介（可选）"}</span>
                <input
                  value={draft.description}
                  onChange={(e) => setDraft((prev) => ({ ...prev, description: e.target.value }))}
                  className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder={isJa ? "この役割の用途を一言で説明" : "一句话说明这个角色的用途"}
                />
              </label>

              <label className="block">
                <span className="block text-xs text-zinc-400 mb-1.5">{isJa ? "アイコン（任意）" : "图标（可选）"}</span>
                <input
                  value={draft.icon}
                  onChange={(e) => setDraft((prev) => ({ ...prev, icon: e.target.value }))}
                  className="w-32 px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="🤖"
                />
              </label>

              <label className="block">
                <span className="block text-xs text-zinc-400 mb-1.5">{isJa ? "役割プロンプト" : "角色提示词"}</span>
                <textarea
                  value={draft.system_prompt}
                  onChange={(e) => setDraft((prev) => ({ ...prev, system_prompt: e.target.value }))}
                  rows={14}
                  className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-100 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder={isJa ? "この役割がタスクをどう理解し、どう話し、何を優先するかを定義してください。" : "定义这个角色如何理解任务、如何说话、应该优先关注什么。"}
                />
              </label>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-4 py-2 rounded-lg bg-brand-600 text-white text-sm hover:bg-brand-500 disabled:opacity-50 transition"
              >
                {saving ? (isJa ? "保存中..." : "保存中...") : editingMode ? (isJa ? "変更を保存" : "保存修改") : (isJa ? "役割を作成" : "创建角色")}
              </button>
              <button
                onClick={resetDraft}
                disabled={saving}
                className="px-4 py-2 rounded-lg border border-surface-3 text-sm text-zinc-300 hover:bg-surface-2 disabled:opacity-50 transition"
              >
                {isJa ? "リセット" : "重置"}
              </button>
            </div>
          </div>
        </div>
      </div>
      </div>
    </div>
  );
}
