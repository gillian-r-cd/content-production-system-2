// frontend/components/eval-phase-panel.tsx
// 功能: 评估阶段主面板（三 Tab：人物画像 / 任务配置 / 评估报告）
// 主要组件: EvalPhasePanel, EvalV2TaskConfigPanel, EvalV2ReportPanel
// 数据结构:
//   - ContentBlock(eval_persona_setup/eval_task_config/eval_report) 作为 UI 锚点
//   - Eval V2 API: Task 容器 + TrialConfig + TrialResult + TaskAnalysis

"use client";

import React, { useState, useEffect, useCallback } from "react";
import { blockAPI, evalV2API, graderAPI } from "@/lib/api";
import type { ContentBlock } from "@/lib/api";
import type { EvalV2Task, EvalV2TrialConfig, GraderData } from "@/lib/api";
import { useUiIsJa } from "@/lib/ui-locale";
import { EvalPersonaSetup } from "./eval-field-editors";
import { sendNotification } from "@/lib/utils";
import { Users, SlidersHorizontal, BarChart3, Loader2, Play, Pause, Square, Pencil, Trash2, Plus, X, RefreshCw, Eye } from "lucide-react";

interface EvalPhasePanelProps {
  projectId: string | null;
  projectLocale?: string | null;
  onFieldsChange?: () => void;
  /** M3: 将消息发送到 Agent 对话面板 */
  onSendToAgent?: (message: string) => void;
  initialTab?: "persona" | "config" | "report";
}

export function EvalPhasePanel({ projectId, projectLocale, onFieldsChange, onSendToAgent, initialTab = "persona" }: EvalPhasePanelProps) {
  const isJa = useUiIsJa(projectLocale);
  const [personaBlock, setPersonaBlock] = useState<ContentBlock | null>(null);
  const [configBlock, setConfigBlock] = useState<ContentBlock | null>(null);
  const [reportBlock, setReportBlock] = useState<ContentBlock | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"persona" | "config" | "report">(initialTab);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  // 加载或创建 eval 专用 ContentBlocks（统一三个锚点）
  const loadOrCreateEvalBlocks = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      // 尝试获取已有的 eval blocks
      const tree = await blockAPI.getProjectBlocks(projectId);
      const allBlocks: ContentBlock[] = [];
      const flatten = (blocks: ContentBlock[]) => {
        for (const b of blocks) {
          allBlocks.push(b);
          if (b.children) flatten(b.children);
        }
      };
      flatten(tree.blocks || []);

      let persona = allBlocks.find(b => b.special_handler === "eval_persona_setup");
      let config = allBlocks.find(b => b.special_handler === "eval_task_config");
      let report = allBlocks.find(b => b.special_handler === "eval_report");

      // 如果不存在，创建它们
      if (!persona) {
        persona = await blockAPI.create({
          project_id: projectId,
          name: isJa ? "ペルソナ設定" : "人物画像设置",
          block_type: "field",
          content: JSON.stringify({ personas: [] }, null, 2),
          special_handler: "eval_persona_setup",
          order_index: 99,
        });
      }
      if (!config) {
        config = await blockAPI.create({
          project_id: projectId,
          name: isJa ? "評価タスク設定" : "评估任务配置",
          block_type: "field",
          content: "",
          special_handler: "eval_task_config",
          order_index: 100,
        });
      }
      if (!report) {
        report = await blockAPI.create({
          project_id: projectId,
          name: isJa ? "評価レポート" : "评估报告",
          block_type: "field",
          content: "",
          special_handler: "eval_report",
          order_index: 101,
        });
      }

      setPersonaBlock(persona);
      setConfigBlock(config);
      setReportBlock(report);
    } catch (e) {
      console.error("加载评估配置失败:", e);
    } finally {
      setLoading(false);
    }
  }, [projectId, isJa]);

  useEffect(() => {
    loadOrCreateEvalBlocks();
  }, [loadOrCreateEvalBlocks]);

  const handleUpdate = () => {
    loadOrCreateEvalBlocks();
    onFieldsChange?.();
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-purple-400 mx-auto mb-3" />
          <p className="text-zinc-400 text-sm">{isJa ? "評価パネルを読み込み中..." : "正在加载评估面板..."}</p>
        </div>
      </div>
    );
  }

  if (!projectId) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-zinc-500">{isJa ? "先にプロジェクトを選択してください" : "请先选择项目"}</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Tab 切换 */}
      <div className="p-4 border-b border-surface-3">
        <h1 className="text-xl font-bold text-zinc-100 mb-3">{isJa ? "評価" : "评估"}</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setActiveTab("persona")}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === "persona"
                ? "bg-sky-500/20 text-sky-300 border border-sky-500/30"
                : "bg-surface-2 text-zinc-400 hover:text-zinc-200 border border-transparent"
            }`}
          >
            <Users className="w-4 h-4" />
            {isJa ? "ペルソナ" : "人物画像"}
          </button>
          <button
            onClick={() => setActiveTab("config")}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === "config"
                ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                : "bg-surface-2 text-zinc-400 hover:text-zinc-200 border border-transparent"
            }`}
          >
            <SlidersHorizontal className="w-4 h-4" />
            {isJa ? "評価設定" : "评估配置"}
          </button>
          <button
            onClick={() => setActiveTab("report")}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === "report"
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                : "bg-surface-2 text-zinc-400 hover:text-zinc-200 border border-transparent"
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            {isJa ? "評価レポート" : "评估报告"}
          </button>
        </div>
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === "persona" && personaBlock && (
          <EvalPersonaSetup block={personaBlock} projectId={projectId} projectLocale={projectLocale} onUpdate={handleUpdate} />
        )}
        {activeTab === "config" && personaBlock && configBlock && (
          <EvalV2TaskConfigPanel
            projectId={projectId}
            projectLocale={projectLocale}
            personaBlock={personaBlock}
            onUpdate={handleUpdate}
          />
        )}
        {activeTab === "report" && reportBlock && (
          <EvalV2ReportPanel
            projectId={projectId}
            projectLocale={projectLocale}
            onSendToAgent={onSendToAgent}
            onUpdate={handleUpdate}
          />
        )}
      </div>
    </div>
  );
}

function getTaskStatusLabel(status: string | undefined, isJa: boolean): string {
  if (status === "running") return isJa ? "実行中" : "运行中";
  if (status === "paused") return isJa ? "一時停止" : "已暂停";
  if (status === "completed") return isJa ? "完了" : "已完成";
  if (status === "failed") return isJa ? "失敗" : "失败";
  if (status === "pausing") return isJa ? "一時停止要求中" : "暂停请求中";
  if (status === "stopping") return isJa ? "停止要求中" : "终止请求中";
  return status || (isJa ? "未開始" : "未开始");
}

interface EvalV2TaskConfigPanelProps {
  projectId: string;
  projectLocale?: string | null;
  personaBlock: ContentBlock;
  onUpdate?: () => void;
}

function EvalV2TaskConfigPanel({ projectId, projectLocale, personaBlock, onUpdate }: EvalV2TaskConfigPanelProps) {
  const isJa = useUiIsJa(projectLocale);
  const [tasks, setTasks] = useState<EvalV2Task[]>([]);
  const [graders, setGraders] = useState<GraderData[]>([]);
  const [projectBlocks, setProjectBlocks] = useState<{ id: string; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ name: string; description: string; trial_configs: EvalV2TrialConfig[] }>({
    name: "",
    description: "",
    trial_configs: [],
  });
  const personas = parsePersonas(personaBlock.content);

  const loadData = useCallback(async (silent: boolean = false) => {
    if (!silent) setLoading(true);
    try {
      const [taskResp, graderResp, blockTree] = await Promise.all([
        evalV2API.listTasks(projectId),
        graderAPI.listForProject(projectId),
        blockAPI.getProjectBlocks(projectId).catch(() => ({ blocks: [] })),
      ]);
      setTasks(taskResp.tasks || []);
      setGraders(graderResp || []);
      const fields: { id: string; name: string }[] = [];
      const flatten = (blocks: ContentBlock[]) => {
        for (const b of blocks) {
          if (b.block_type === "field" && !b.special_handler?.startsWith("eval_")) {
            fields.push({ id: b.id, name: b.name });
          }
          if (b.children) flatten(b.children);
        }
      };
      flatten(blockTree.blocks || []);
      setProjectBlocks(fields);
    } catch (e: unknown) {
      sendNotification(`${isJa ? "評価タスクの読み込みに失敗しました" : "加载评估任务失败"}: ${errorMessage(e, isJa)}`, "error");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadData(false);
  }, [loadData]);

  useEffect(() => {
    const hasRunning = tasks.some((t) => t.status === "running" || t.progress?.is_running || t.progress?.pause_requested);
    if (!hasRunning) return;
    const timer = setInterval(() => {
      loadData(true);
    }, 1000);
    return () => clearInterval(timer);
  }, [tasks, loadData]);

  const newTrial = (): EvalV2TrialConfig => ({
    name: isJa ? "新しいトライアル" : "新试验",
    form_type: "assessment",
    target_block_ids: [],
    grader_ids: graders.length > 0 ? [graders[0].id] : [],
    grader_weights: {},
    repeat_count: 1,
    probe: "",
    form_config: {},
    order_index: draft.trial_configs.length,
  });

  const openCreate = () => {
    setEditingTaskId(null);
    setDraft({
      name: "",
      description: "",
      trial_configs: [newTrial()],
    });
    setShowModal(true);
  };

  const openEdit = (task: EvalV2Task) => {
    setEditingTaskId(task.id);
    setDraft({
      name: task.name,
      description: task.description || "",
      trial_configs: (task.trial_configs || []).map((t, idx) => ({
        ...t,
        order_index: t.order_index ?? idx,
      })),
    });
    setShowModal(true);
  };

  const saveTask = async () => {
    if (!draft.name.trim()) {
      sendNotification(isJa ? "タスク名は必須です" : "任务名称不能为空", "error");
      return;
    }
    if (!draft.trial_configs.length) {
      sendNotification(isJa ? "少なくとも1件のトライアル設定が必要です" : "至少需要一个试验配置", "error");
      return;
    }
    setSaving(true);
    try {
      if (editingTaskId) {
        await evalV2API.updateTask(editingTaskId, draft);
      } else {
        await evalV2API.createTask(projectId, draft);
      }
      setShowModal(false);
      await loadData();
      onUpdate?.();
      sendNotification(isJa ? "評価タスクを保存しました" : "评估任务已保存", "success");
    } catch (e: unknown) {
      sendNotification(`${isJa ? "保存に失敗しました" : "保存失败"}: ${errorMessage(e, isJa)}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const executeTask = async (taskId: string) => {
    try {
      await evalV2API.startTask(taskId);
      await loadData(true);
      onUpdate?.();
      sendNotification(isJa ? "タスクを開始しました" : "任务已开始执行", "success");
    } catch (e: unknown) {
      sendNotification(`${isJa ? "実行に失敗しました" : "执行失败"}: ${errorMessage(e, isJa)}`, "error");
    }
  };

  const pauseTask = async (taskId: string) => {
    try {
      await evalV2API.pauseTask(taskId);
      await loadData(true);
      sendNotification(isJa ? "タスクの一時停止を要求しました" : "已请求暂停任务", "success");
    } catch (e: unknown) {
      sendNotification(`${isJa ? "一時停止に失敗しました" : "暂停失败"}: ${errorMessage(e, isJa)}`, "error");
    }
  };

  const resumeTask = async (taskId: string) => {
    try {
      const resp = await evalV2API.resumeTask(taskId);
      await loadData(true);
      sendNotification(resp?.message || (isJa ? "タスクを再開しました" : "任务已恢复执行"), "success");
    } catch (e: unknown) {
      sendNotification(`${isJa ? "再開に失敗しました" : "恢复失败"}: ${errorMessage(e, isJa)}`, "error");
    }
  };

  const stopTask = async (taskId: string) => {
    try {
      await evalV2API.stopTask(taskId);
      await loadData(true);
      sendNotification(isJa ? "タスクの停止を要求しました" : "已请求终止任务", "success");
    } catch (e: unknown) {
      sendNotification(`${isJa ? "停止に失敗しました" : "停止失败"}: ${errorMessage(e, isJa)}`, "error");
    }
  };

  const executeAll = async () => {
    try {
      await evalV2API.executeAll(projectId);
      await loadData();
      onUpdate?.();
      sendNotification(isJa ? "一括実行が完了しました" : "批量执行已完成", "success");
    } catch (e: unknown) {
      sendNotification(`${isJa ? "一括実行に失敗しました" : "批量执行失败"}: ${errorMessage(e, isJa)}`, "error");
    }
  };

  const deleteTask = async (taskId: string) => {
    if (!confirm(isJa ? "この評価タスクを削除しますか？" : "确认删除这个评估任务吗？")) return;
    try {
      await evalV2API.deleteTask(taskId);
      await loadData();
      onUpdate?.();
      sendNotification(isJa ? "タスクを削除しました" : "任务已删除", "success");
    } catch (e: unknown) {
      sendNotification(`${isJa ? "削除に失敗しました" : "删除失败"}: ${errorMessage(e, isJa)}`, "error");
    }
  };

  const updateTrial = (idx: number, patch: Partial<EvalV2TrialConfig>) => {
    const next = [...draft.trial_configs];
    next[idx] = { ...next[idx], ...patch };
    setDraft({ ...draft, trial_configs: next });
  };

  const renderTrialFormConfig = (trial: EvalV2TrialConfig, idx: number) => {
    const cfg = trial.form_config || {};
    if (trial.form_type === "review" || trial.form_type === "experience") {
      const selected = String(cfg.persona_id || "");
      return (
        <div>
          <label className="text-xs text-zinc-400">{isJa ? "ペルソナ" : "画像"}</label>
          <select
            className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
            value={selected}
            onChange={(e) => updateTrial(idx, { form_config: { ...cfg, persona_id: e.target.value } })}
          >
            <option value="">{isJa ? "ペルソナを選択" : "请选择画像"}</option>
            {personas.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      );
    }
    if (trial.form_type === "scenario") {
      return (
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="text-xs text-zinc-400">{isJa ? "ロールAのペルソナ" : "角色A画像"}</label>
            <select
              className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
              value={String(cfg.role_a_persona_id || "")}
              onChange={(e) => updateTrial(idx, { form_config: { ...cfg, role_a_persona_id: e.target.value } })}
            >
              <option value="">{isJa ? "選択してください" : "请选择"}</option>
              {personas.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-400">{isJa ? "ロールBのペルソナ" : "角色B画像"}</label>
            <select
              className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
              value={String(cfg.role_b_persona_id || "")}
              onChange={(e) => updateTrial(idx, { form_config: { ...cfg, role_b_persona_id: e.target.value } })}
            >
              <option value="">{isJa ? "選択してください" : "请选择"}</option>
              {personas.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-400">{isJa ? "最大ターン数" : "最大轮数"}</label>
            <input
              type="number"
              min={1}
              max={20}
              className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
              value={Number(cfg.max_turns || 5)}
              onChange={(e) => updateTrial(idx, { form_config: { ...cfg, max_turns: Number(e.target.value || 5) } })}
            />
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-zinc-100">{isJa ? "タスク設定" : "任务配置"}</h3>
        <div className="flex gap-2">
          <button className="px-3 py-2 text-sm rounded bg-surface-2 border border-surface-3 hover:bg-surface-3" onClick={executeAll}>
            {isJa ? "すべて実行" : "全部运行"}
          </button>
          <button className="px-3 py-2 text-sm rounded bg-brand-500 text-white hover:bg-brand-600 flex items-center gap-1.5" onClick={openCreate}>
            <Plus className="w-4 h-4" />
            {isJa ? "タスクを追加" : "添加任务"}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-zinc-400 text-sm py-6">{isJa ? "読み込み中..." : "加载中..."}</div>
      ) : tasks.length === 0 ? (
        <div className="border border-dashed border-surface-3 rounded-lg p-8 text-center text-zinc-500 text-sm">
          {isJa ? "評価タスクはまだありません。「タスクを追加」をクリックして最初のタスクを作成してください。" : "暂无评估任务，点击“添加任务”创建第一个任务。"}
        </div>
      ) : (
        <div className="space-y-2">
          {tasks.map((task) => (
            <div key={task.id} className="border border-surface-3 rounded-lg px-3 py-2 flex items-center justify-between">
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-100 truncate">{task.name}</div>
                <div className="text-xs text-zinc-500 mt-1">
                  {task.trial_configs.length} {isJa ? "件のトライアル" : "个试验"} · {isJa ? "状態" : "状态"}: {getTaskStatusLabel(task.progress?.pause_requested ? "pausing" : task.progress?.stop_requested ? "stopping" : task.status, isJa)}
                </div>
                {typeof task.progress?.percent === "number" && (
                  <div className="mt-2 w-56">
                    <div className="h-1.5 bg-surface-2 rounded overflow-hidden">
                      <div
                        className="h-full bg-brand-500 transition-all"
                        style={{ width: `${task.progress.percent}%` }}
                      />
                    </div>
                    <div className="text-[11px] text-zinc-500 mt-1">
                      {isJa ? "進捗" : "进度"} {task.progress.completed || 0}/{task.progress.total || 0} ({task.progress.percent}%)
                      {task.progress.pause_requested ? (isJa ? " · 一時停止中..." : " · 暂停中...") : ""}
                    </div>
                  </div>
                )}
              </div>
              <div className="flex gap-1">
                {task.status === "running" || task.progress?.is_running ? (
                  <>
                    <button className="p-2 rounded hover:bg-surface-2 text-amber-300" onClick={() => pauseTask(task.id)} title={isJa ? "一時停止" : "暂停"}>
                      <Pause className="w-4 h-4" />
                    </button>
                    <button className="p-2 rounded hover:bg-surface-2 text-red-300" onClick={() => stopTask(task.id)} title={isJa ? "停止" : "终止"}>
                      <Square className="w-4 h-4" />
                    </button>
                  </>
                ) : task.status === "paused" ? (
                  <button className="p-2 rounded hover:bg-surface-2 text-emerald-300" onClick={() => resumeTask(task.id)} title={isJa ? "再開" : "恢复"}>
                    <Play className="w-4 h-4" />
                  </button>
                ) : (
                  <button className="p-2 rounded hover:bg-surface-2 text-zinc-300" onClick={() => executeTask(task.id)} title={isJa ? "開始" : "开始"}>
                    <Play className="w-4 h-4" />
                  </button>
                )}
                <button className="p-2 rounded hover:bg-surface-2 text-zinc-300" onClick={() => openEdit(task)} title={isJa ? "編集" : "编辑"}>
                  <Pencil className="w-4 h-4" />
                </button>
                <button className="p-2 rounded hover:bg-surface-2 text-red-400" onClick={() => deleteTask(task.id)} title={isJa ? "削除" : "删除"}>
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="w-full max-w-4xl max-h-[90vh] overflow-y-auto bg-surface-0 border border-surface-3 rounded-xl">
            <div className="px-4 py-3 border-b border-surface-3 flex items-center justify-between">
              <div className="text-zinc-100 font-semibold">{editingTaskId ? (isJa ? "タスクを編集" : "编辑任务") : (isJa ? "タスクを追加" : "添加任务")}</div>
              <button className="p-1.5 rounded hover:bg-surface-2 text-zinc-400" onClick={() => setShowModal(false)}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-zinc-400">{isJa ? "タスク名" : "任务名称"}</label>
                  <input
                    className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-3 py-2 text-sm"
                    value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-400">{isJa ? "タスク説明" : "任务描述"}</label>
                  <input
                    className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-3 py-2 text-sm"
                    value={draft.description}
                    onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  />
                </div>
              </div>

              <div className="space-y-3">
                {draft.trial_configs.map((trial, idx) => (
                  <div key={idx} className="border border-surface-3 rounded-lg p-3 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-medium text-zinc-200">{isJa ? `トライアル ${idx + 1}` : `试验 ${idx + 1}`}</div>
                      <button
                        className="text-xs text-red-400 hover:text-red-300"
                        onClick={() => setDraft({
                          ...draft,
                          trial_configs: draft.trial_configs.filter((_, i) => i !== idx).map((t, i) => ({ ...t, order_index: i })),
                        })}
                        disabled={draft.trial_configs.length <= 1}
                      >
                        {isJa ? "削除" : "删除"}
                      </button>
                    </div>
                    <div className="grid grid-cols-4 gap-2">
                      <div className="col-span-2">
                        <label className="text-xs text-zinc-400">{isJa ? "トライアル名" : "试验名称"}</label>
                        <input
                          className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
                          value={trial.name}
                          onChange={(e) => updateTrial(idx, { name: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-zinc-400">{isJa ? "形式" : "形态"}</label>
                        <select
                          className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
                          value={trial.form_type}
                          onChange={(e) => updateTrial(idx, { form_type: e.target.value as EvalV2TrialConfig["form_type"] })}
                        >
                          <option value="assessment">{isJa ? "直接判定" : "直接判定"}</option>
                          <option value="review">{isJa ? "視点レビュー" : "视角审查"}</option>
                          <option value="experience">{isJa ? "体験評価" : "消费体验"}</option>
                          <option value="scenario">{isJa ? "シナリオシミュレーション" : "场景模拟"}</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-zinc-400">{isJa ? "実行回数" : "执行次数"}</label>
                        <input
                          type="number"
                          min={1}
                          className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
                          value={trial.repeat_count}
                          onChange={(e) => updateTrial(idx, { repeat_count: Math.max(1, Number(e.target.value || 1)) })}
                        />
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-xs text-zinc-400">
                          {isJa ? "評価対象の内容ブロック" : "评估内容块"}
                          {trial.target_block_ids.length > 0
                            ? ` (${trial.target_block_ids.length}/${projectBlocks.length})`
                            : (isJa ? ` (未選択 = 全 ${projectBlocks.length} 件)` : ` (不选 = 全部 ${projectBlocks.length} 个)`)}
                        </label>
                        <button
                          type="button"
                          className="text-xs text-zinc-500 hover:text-zinc-300"
                          onClick={() => {
                            const allSelected = trial.target_block_ids.length === projectBlocks.length;
                            updateTrial(idx, { target_block_ids: allSelected ? [] : projectBlocks.map(b => b.id) });
                          }}
                        >
                          {trial.target_block_ids.length === projectBlocks.length ? (isJa ? "全選択を解除" : "清除全选") : (isJa ? "すべて選択" : "全选")}
                        </button>
                      </div>
                      {projectBlocks.length > 0 ? (
                        <div className="grid grid-cols-2 gap-1 max-h-36 overflow-y-auto border border-surface-3 rounded p-2 bg-surface-1">
                          {projectBlocks.map((b) => {
                            const checked = trial.target_block_ids.includes(b.id);
                            return (
                              <label key={b.id} className={`text-xs flex items-center gap-1.5 p-1.5 rounded cursor-pointer transition-colors ${checked ? "text-blue-300 bg-blue-500/10" : "text-zinc-400 hover:text-zinc-300"}`}>
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => {
                                    const ids = checked
                                      ? trial.target_block_ids.filter(id => id !== b.id)
                                      : [...trial.target_block_ids, b.id];
                                    updateTrial(idx, { target_block_ids: ids });
                                  }}
                                  className="accent-blue-500"
                                />
                                <span className="truncate">{b.name}</span>
                              </label>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="text-xs text-zinc-500 p-2 border border-surface-3 rounded bg-surface-1">
                          {isJa ? "プロジェクト内に内容ブロックがありません" : "项目中暂无内容块"}
                        </div>
                      )}
                    </div>

                    {renderTrialFormConfig(trial, idx)}

                    <div>
                      <label className="text-xs text-zinc-400">{isJa ? "注目点（任意）" : "焦点（可选）"}</label>
                      <input
                        className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
                        value={trial.probe || ""}
                        onChange={(e) => updateTrial(idx, { probe: e.target.value })}
                      />
                    </div>

                    <div>
                      <label className="text-xs text-zinc-400 block mb-1">{isJa ? "評価器" : "评分器"}</label>
                      <div className="grid grid-cols-2 gap-1.5">
                        {graders.map((g) => {
                          const checked = trial.grader_ids.includes(g.id);
                          return (
                            <label key={g.id} className="text-xs text-zinc-300 flex items-center gap-2 p-2 border border-surface-3 rounded">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    updateTrial(idx, { grader_ids: [...trial.grader_ids, g.id] });
                                  } else {
                                    updateTrial(idx, { grader_ids: trial.grader_ids.filter((id) => id !== g.id) });
                                  }
                                }}
                              />
                              <span>{g.name}</span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <button
                className="px-3 py-2 text-sm rounded bg-surface-2 border border-surface-3 hover:bg-surface-3 flex items-center gap-1.5"
                onClick={() => setDraft({
                  ...draft,
                  trial_configs: [...draft.trial_configs, { ...newTrial(), order_index: draft.trial_configs.length }],
                })}
              >
                <Plus className="w-4 h-4" />
                {isJa ? "トライアルを追加" : "添加试验"}
              </button>
            </div>
            <div className="px-4 py-3 border-t border-surface-3 flex justify-end gap-2">
              <button className="px-3 py-2 text-sm rounded bg-surface-2 border border-surface-3" onClick={() => setShowModal(false)}>
                {isJa ? "キャンセル" : "取消"}
              </button>
              <button className="px-3 py-2 text-sm rounded bg-brand-500 text-white disabled:opacity-50" onClick={saveTask} disabled={saving}>
                {saving ? (isJa ? "保存中..." : "保存中...") : (isJa ? "保存" : "保存")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface EvalV2ReportPanelProps {
  projectId: string;
  projectLocale?: string | null;
  onUpdate?: () => void;
  onSendToAgent?: (message: string) => void;
}

interface EvalExecutionRow {
  task_id: string;
  batch_id: string;
  task_name: string;
  overall?: number | null;
  status?: string;
  trial_count?: number | null;
  executed_at?: string;
}

interface SuggestionStateRow {
  source: string;
  suggestion: string;
  status?: string;
}

interface ScoreEvidenceItem {
  grader_name?: string;
  dimension?: string;
  score?: number | string | null;
  evidence?: string;
}

interface GraderResultItem {
  grader_name?: string;
  feedback?: string;
}

interface ProcessStep {
  type?: string;
  stage?: string;
  role?: string;
  content?: string;
  block_id?: string;
  block_title?: string;
  data?: unknown;
}

interface LLMCallItem {
  step?: string;
  tokens_in?: number;
  tokens_out?: number;
  cost?: number;
  input?: {
    system_prompt?: string;
    user_message?: string;
  };
  output?: unknown;
}

interface EvalTrialDetail {
  id: string;
  trial_config_name?: string;
  form_type: string;
  repeat_index: number;
  overall_score?: number | null;
  status?: string;
  llm_calls?: LLMCallItem[];
  dimension_scores?: Record<string, number | null | undefined>;
  overall_comment?: string;
  score_evidence?: ScoreEvidenceItem[];
  grader_results?: GraderResultItem[];
  improvement_suggestions?: string[];
  process?: ProcessStep[];
}

interface EvalTaskBatchDetail {
  trials?: EvalTrialDetail[];
}

interface DiagnosisPattern {
  title?: string;
  frequency?: string;
}

interface DiagnosisSuggestion {
  title?: string;
  detail?: string;
}

interface DiagnosisResult {
  patterns?: DiagnosisPattern[];
  suggestions?: DiagnosisSuggestion[];
}

function EvalV2ReportPanel({ projectId, projectLocale, onUpdate, onSendToAgent }: EvalV2ReportPanelProps) {
  const isJa = useUiIsJa(projectLocale);
  const [rows, setRows] = useState<EvalExecutionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [selectedExecution, setSelectedExecution] = useState<EvalExecutionRow | null>(null);
  const [detail, setDetail] = useState<EvalTaskBatchDetail | null>(null);
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [expandedPromptTrialId, setExpandedPromptTrialId] = useState<string | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [sentSuggestionKeys, setSentSuggestionKeys] = useState<Record<string, boolean>>({});

  const loadReport = useCallback(async () => {
    setLoading(true);
    try {
      const data = await evalV2API.executionReport(projectId);
      setRows(data.executions || []);
      setSelectedKeys([]);
    } catch (e: unknown) {
      sendNotification(`${isJa ? "レポートの読み込みに失敗しました" : "加载报告失败"}: ${errorMessage(e, isJa)}`, "error");
    } finally {
      setLoading(false);
    }
  }, [projectId, isJa]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const openExecution = async (execution: EvalExecutionRow) => {
    setSelectedExecution(execution);
    try {
      const [detailResp, diagResp, stateResp] = await Promise.all([
        evalV2API.taskBatch(execution.task_id, execution.batch_id),
        evalV2API.getTaskDiagnosis(execution.task_id, execution.batch_id),
        evalV2API.getSuggestionStates(execution.task_id, execution.batch_id),
      ]);
      setDetail(detailResp);
      setDiagnosis(diagResp.analysis || null);
      const stateMap: Record<string, boolean> = {};
      for (const s of ((stateResp as { states?: SuggestionStateRow[] }).states || [])) {
        if ((s.status || "") === "applied") {
          stateMap[`${s.source}::${s.suggestion}`] = true;
        }
      }
      setSentSuggestionKeys(stateMap);
    } catch (e: unknown) {
      sendNotification(`${isJa ? "タスク詳細の読み込みに失敗しました" : "加载任务详情失败"}: ${errorMessage(e, isJa)}`, "error");
    }
  };

  const keyOf = (r: EvalExecutionRow) => `${r.task_id}::${r.batch_id}`;

  const toggleSelect = (r: EvalExecutionRow) => {
    const key = keyOf(r);
    setSelectedKeys((prev) => (prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]));
  };

  const deleteOne = async (r: EvalExecutionRow) => {
    if (!confirm(
      isJa
        ? `この記録を削除しますか？\nタスク: ${r.task_name}\nバッチ: ${String(r.batch_id || "").slice(0, 8)}`
        : `确认删除记录？\n任务: ${r.task_name}\n批次: ${String(r.batch_id || "").slice(0, 8)}`,
    )) return;
    setDeleting(true);
    try {
      await evalV2API.deleteTaskBatch(r.task_id, r.batch_id);
      if (selectedExecution && selectedExecution.task_id === r.task_id && selectedExecution.batch_id === r.batch_id) {
        setSelectedExecution(null);
        setDetail(null);
        setDiagnosis(null);
      }
      await loadReport();
      onUpdate?.();
      sendNotification(isJa ? "記録を削除しました" : "记录已删除", "success");
    } catch (e: unknown) {
      sendNotification(`${isJa ? "削除に失敗しました" : "删除失败"}: ${errorMessage(e, isJa)}`, "error");
    } finally {
      setDeleting(false);
    }
  };

  const deleteSelected = async () => {
    if (!selectedKeys.length) return;
    if (!confirm(isJa ? `選択中の ${selectedKeys.length} 件の記録を一括削除しますか？` : `确认批量删除 ${selectedKeys.length} 条记录吗？`)) return;
    const items = selectedKeys.map((k) => {
      const [task_id, batch_id] = k.split("::");
      return { task_id, batch_id };
    });
    setDeleting(true);
    try {
      await evalV2API.batchDeleteExecutions(projectId, items);
      if (
        selectedExecution &&
        items.some((x) => x.task_id === selectedExecution.task_id && x.batch_id === selectedExecution.batch_id)
      ) {
        setSelectedExecution(null);
        setDetail(null);
        setDiagnosis(null);
      }
      await loadReport();
      onUpdate?.();
      sendNotification(isJa ? `${items.length} 件の記録を削除しました` : `已删除 ${items.length} 条记录`, "success");
    } catch (e: unknown) {
      sendNotification(`${isJa ? "一括削除に失敗しました" : "批量删除失败"}: ${errorMessage(e, isJa)}`, "error");
    } finally {
      setDeleting(false);
    }
  };

  const runDiagnosis = async () => {
    if (!selectedExecution) return;
    setDiagnosing(true);
    try {
      const out = await evalV2API.runTaskDiagnosisForBatch(selectedExecution.task_id, selectedExecution.batch_id);
      setDiagnosis(out.analysis || null);
      onUpdate?.();
      sendNotification(isJa ? "トライアル横断分析を生成しました" : "跨 Trial 分析已生成", "success");
    } catch (e: unknown) {
      sendNotification(`${isJa ? "分析に失敗しました" : "分析失败"}: ${errorMessage(e, isJa)}`, "error");
    } finally {
      setDiagnosing(false);
    }
  };

  const sendSuggestionToAgent = async (source: string, suggestion: string) => {
    if (!onSendToAgent) return;
    if (!selectedExecution) return;
    const key = `${source}::${suggestion}`;
    const msg = isJa
      ? `以下の評価提案に基づいて内容を修正してください。\n出典: ${source}\n提案: ${suggestion}\n要件: まず実行可能な編集方針を示し、その後に確認可能な修正案を出力してください。`
      : `请根据评估建议修改内容。\n来源: ${source}\n建议: ${suggestion}\n要求: 先给出可执行编辑方案，并输出可确认的修改建议。`;
    try {
      await evalV2API.markSuggestionApplied(selectedExecution.task_id, selectedExecution.batch_id, {
        source,
        suggestion,
        status: "applied",
      });
      onSendToAgent(msg);
      setSentSuggestionKeys((prev) => ({ ...prev, [key]: true }));
      sendNotification(isJa ? "提案を Agent パネルへ送信しました" : "建议已发送到 Agent 面板", "success");
    } catch (e: unknown) {
      sendNotification(`${isJa ? "送信に失敗しました" : "发送失败"}: ${errorMessage(e, isJa)}`, "error");
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-zinc-100">{isJa ? "評価レポート" : "评估报告"}</h3>
        <div className="flex items-center gap-2">
          <button
            className="px-3 py-2 text-sm rounded bg-red-500/15 border border-red-500/40 text-red-300 hover:bg-red-500/25 disabled:opacity-50"
            onClick={deleteSelected}
            disabled={deleting || selectedKeys.length === 0}
          >
            {isJa ? `一括削除 (${selectedKeys.length})` : `批量删除 (${selectedKeys.length})`}
          </button>
          <button className="px-3 py-2 text-sm rounded bg-surface-2 border border-surface-3 hover:bg-surface-3 flex items-center gap-1.5" onClick={loadReport}>
            <RefreshCw className="w-4 h-4" />
            {isJa ? "更新" : "刷新"}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-zinc-400 text-sm py-6">{isJa ? "読み込み中..." : "加载中..."}</div>
      ) : rows.length === 0 ? (
        <div className="border border-dashed border-surface-3 rounded-lg p-8 text-center text-zinc-500 text-sm">
          {isJa ? "実行記録はまだありません。先にタスク設定でタスクを実行してください。" : "暂无执行记录。请先在任务配置页执行任务。"}
        </div>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <div
              key={`${r.task_id}-${r.batch_id}`}
              className="w-full text-left border border-surface-3 rounded-lg px-3 py-2 hover:bg-surface-2 transition-colors"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <input
                    type="checkbox"
                    checked={selectedKeys.includes(keyOf(r))}
                    onChange={() => toggleSelect(r)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <button className="text-left min-w-0" onClick={() => openExecution(r)}>
                    <div className="text-sm font-medium text-zinc-100 truncate">{r.task_name}</div>
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <div className="text-sm text-zinc-300">{typeof r.overall === "number" ? r.overall.toFixed(2) : "-"}</div>
                  <button
                    className="text-xs px-2 py-1 rounded border border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20"
                    onClick={() => deleteOne(r)}
                    disabled={deleting}
                  >
                    {isJa ? "削除" : "删除"}
                  </button>
                </div>
              </div>
              <div className="text-xs text-zinc-500 mt-1">{isJa ? "状態" : "状态"}: {getTaskStatusLabel(r.status, isJa)} · {isJa ? "実行時刻" : "执行时间"}: {r.executed_at || "-"} · {isJa ? "バッチ" : "批次"}: {String(r.batch_id || "").slice(0, 8)}</div>
            </div>
          ))}
        </div>
      )}

      {selectedExecution && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="w-full max-w-5xl max-h-[90vh] overflow-y-auto bg-surface-0 border border-surface-3 rounded-xl">
            <div className="px-4 py-3 border-b border-surface-3 flex items-center justify-between">
              <div>
                <div className="text-zinc-100 font-semibold">{selectedExecution.task_name}</div>
                <div className="text-xs text-zinc-500 mt-1">{isJa ? "総合点" : "总分"}: {typeof selectedExecution.overall === "number" ? selectedExecution.overall.toFixed(2) : "-"} · {isJa ? "バッチ" : "批次"}: {String(selectedExecution.batch_id || "").slice(0, 8)}</div>
              </div>
              <button className="p-1.5 rounded hover:bg-surface-2 text-zinc-400" onClick={() => { setSelectedExecution(null); setDetail(null); setDiagnosis(null); setExpandedPromptTrialId(null); setSentSuggestionKeys({}); }}>
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 space-y-4">
              <div className="border border-surface-3 rounded-lg p-3">
                <div className="text-sm font-medium text-zinc-100 mb-2">{isJa ? "概要指標" : "总览指标"}</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                  <div className="bg-surface-1 border border-surface-3 rounded px-2 py-1.5">
                    <div className="text-zinc-500 text-xs">{isJa ? "総合点" : "总分"}</div>
                    <div className="text-zinc-100 font-medium">{typeof selectedExecution.overall === "number" ? selectedExecution.overall.toFixed(2) : "-"}</div>
                  </div>
                  <div className="bg-surface-1 border border-surface-3 rounded px-2 py-1.5">
                    <div className="text-zinc-500 text-xs">{isJa ? "バッチ状態" : "批次状态"}</div>
                    <div className="text-zinc-100 font-medium">{getTaskStatusLabel(selectedExecution.status, isJa)}</div>
                  </div>
                  <div className="bg-surface-1 border border-surface-3 rounded px-2 py-1.5">
                    <div className="text-zinc-500 text-xs">{isJa ? "トライアル数" : "试验数"}</div>
                    <div className="text-zinc-100 font-medium">{selectedExecution.trial_count ?? "-"}</div>
                  </div>
                  <div className="bg-surface-1 border border-surface-3 rounded px-2 py-1.5">
                    <div className="text-zinc-500 text-xs">{isJa ? "実行時刻" : "执行时间"}</div>
                    <div className="text-zinc-100 font-medium">{selectedExecution.executed_at || "-"}</div>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-zinc-100">{isJa ? "トライアル詳細" : "试验详情"}</div>
                {(detail?.trials || []).map((t) => (
                  <div key={t.id} className="border border-surface-3 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="text-sm text-zinc-100">
                        {t.trial_config_name || (isJa ? `トライアル ${t.form_type}` : `试验 ${t.form_type}`)} · {isJa ? `${t.repeat_index + 1} 回目` : `第 ${t.repeat_index + 1} 次`}
                      </div>
                      <div className="text-sm text-zinc-300">{typeof t.overall_score === "number" ? t.overall_score.toFixed(2) : "-"}</div>
                    </div>
                    <div className="text-xs text-zinc-500">{isJa ? "状態" : "状态"}: {getTaskStatusLabel(t.status, isJa)} · {isJa ? "LLM 呼び出し" : "LLM调用"}: {(t.llm_calls || []).length}</div>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(t.dimension_scores || {}).length === 0 ? (
                        <span className="text-xs text-zinc-500">{isJa ? "このトライアルにはまだ評価軸別スコアがありません" : "本 Trial 暂无维度分"}</span>
                      ) : (
                        Object.entries(t.dimension_scores || {}).map(([dim, score]) => (
                          <span key={dim} className="text-xs bg-surface-2 border border-surface-3 rounded px-2 py-1 text-zinc-300">
                            {dim}: {typeof score === "number" ? score.toFixed(2) : "-"}
                          </span>
                        ))
                      )}
                    </div>
                    <div>
                      <button
                        className="text-xs px-2 py-1 rounded bg-surface-2 border border-surface-3 hover:bg-surface-3 flex items-center gap-1.5"
                        onClick={() => setExpandedPromptTrialId(expandedPromptTrialId === t.id ? null : t.id)}
                      >
                        <Eye className="w-3.5 h-3.5" />
                        {expandedPromptTrialId === t.id ? (isJa ? "過程と呼び出し詳細を折りたたむ" : "收起过程与调用明细") : (isJa ? "過程と呼び出し詳細を見る" : "查看过程与调用明细")}
                      </button>
                    </div>
                    <div className="bg-surface-1 border border-surface-3 rounded p-2">
                      <div className="text-xs text-zinc-500 mb-1">{isJa ? "トライアル総評" : "Trial 总评"}</div>
                      <div className="text-xs text-zinc-300 whitespace-pre-wrap">
                        {t.overall_comment || (isJa ? "このトライアルにはまだ総評がありません。" : "本 Trial 暂无总评。")}
                      </div>
                    </div>
                    <div className="bg-surface-1 border border-surface-3 rounded p-2">
                      <div className="text-xs text-zinc-500 mb-1">{isJa ? "採点根拠" : "评分依据"}</div>
                      {(t.score_evidence || []).length === 0 ? (
                        <div className="text-xs text-zinc-500">{isJa ? "採点根拠はまだありません" : "暂无评分依据"}</div>
                      ) : (
                        <div className="space-y-1.5">
                          {(t.score_evidence || []).map((ev, evIdx: number) => (
                            <div key={evIdx} className="text-xs text-zinc-300">
                              <span className="text-zinc-500">[{ev.grader_name || (isJa ? "評価器" : "评分器")} · {ev.dimension || (isJa ? "総合" : "综合")} · {ev.score ?? "-"}]</span>{" "}
                              {ev.evidence || ""}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    {(t.grader_results || []).map((gr, i: number) => (
                      <div key={i} className="bg-surface-1 border border-surface-3 rounded p-2 text-sm">
                        <div className="text-zinc-200">{gr.grader_name}</div>
                        <div className="text-zinc-400 text-xs mt-1 whitespace-pre-wrap">{gr.feedback || (isJa ? "フィードバックなし" : "无反馈")}</div>
                      </div>
                    ))}
                    <div className="bg-surface-1 border border-surface-3 rounded p-2">
                      <div className="text-xs text-zinc-500 mb-1">{isJa ? "修正提案" : "修改建议"}</div>
                      {collectTrialSuggestions(t).length === 0 ? (
                        <div className="text-xs text-zinc-500">{isJa ? "独立した修正提案はまだありません" : "暂无独立修改建议"}</div>
                      ) : (
                        <div className="space-y-1.5">
                          {collectTrialSuggestions(t).map((sg: string, sgIdx: number) => {
                            const source = `${selectedExecution.task_name} / ${(t.trial_config_name || t.form_type || "trial")} #${sgIdx + 1}`;
                            const stateKey = `${source}::${sg}`;
                            return (
                              <div key={sgIdx} className="flex items-center justify-between bg-surface-2 border border-surface-3 rounded px-2 py-1.5">
                                <span className="text-xs text-zinc-300">{sg}</span>
                                {onSendToAgent && (
                                  <button
                                    className="text-xs px-2 py-1 rounded bg-brand-500/20 text-brand-300 hover:bg-brand-500/30 disabled:opacity-60"
                                    onClick={() => sendSuggestionToAgent(source, sg)}
                                    disabled={!!sentSuggestionKeys[stateKey]}
                                  >
                                    {sentSuggestionKeys[stateKey] ? (isJa ? "修正済み" : "已修改") : (isJa ? "Agent に修正依頼" : "让Agent修改")}
                                  </button>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    {expandedPromptTrialId === t.id && (
                      <div className="border border-surface-3 rounded p-2 bg-surface-1 space-y-2">
                        <div className="text-xs text-zinc-300">{isJa ? "過程の再生" : "过程回放"}</div>
                        {(t.form_type === "assessment" || t.form_type === "review") ? (
                          <div className="text-xs text-zinc-500">
                            {isJa ? "この評価形式は採点結果が中心のため、過程再生は表示しません。上の「採点根拠」を確認してください。" : "该评估形态以评分结论为主，不展示过程回放；请查看上方“评分依据”。"}
                          </div>
                        ) : (t.process || []).length === 0 ? (
                          <div className="text-xs text-zinc-500">{isJa ? "過程記録はありません" : "无过程记录"}</div>
                        ) : (
                          (t.process || []).map((p, idx: number) => (
                            <div key={idx} className="border border-surface-3 rounded bg-surface-0 p-2 space-y-1">
                              <div className="text-xs text-zinc-400">
                                #{idx + 1} · {p.stage || p.type || "dialogue_step"}
                              </div>
                              <div className="text-[11px] text-zinc-300 whitespace-pre-wrap">
                                {formatProcessStep(t.form_type, p, isJa)}
                              </div>
                            </div>
                          ))
                        )}

                        <div className="text-xs text-zinc-300 mt-2">{isJa ? "LLM 呼び出し詳細（各回の入力 / 出力）" : "LLM 调用明细（逐次输入 / 输出）"}</div>
                        {(t.llm_calls || []).length === 0 ? (
                          <div className="text-xs text-zinc-500">{isJa ? "呼び出し記録はありません" : "无调用记录"}</div>
                        ) : (
                          (t.llm_calls || []).map((c, idx: number) => (
                            <div key={idx} className="border border-surface-3 rounded bg-surface-0 p-2 space-y-2">
                              <div className="text-xs text-zinc-400">
                                #{idx + 1} · {isJa ? "ステップ" : "step"}: {c.step || "-"} · {isJa ? "入出力" : "in/out"}: {c.tokens_in ?? 0}/{c.tokens_out ?? 0} · {isJa ? "費用" : "cost"}: {typeof c.cost === "number" ? c.cost.toFixed(6) : "0.000000"}
                              </div>
                              <div className="border border-surface-3 rounded p-2 bg-surface-1">
                                <div className="text-[11px] text-zinc-500 mb-1">{isJa ? "入力 / システム" : "Input / system"}</div>
                                <div className="text-[11px] text-zinc-300 whitespace-pre-wrap">{c.input?.system_prompt || ""}</div>
                              </div>
                              <div className="border border-surface-3 rounded p-2 bg-surface-1">
                                <div className="text-[11px] text-zinc-500 mb-1">{isJa ? "入力 / ユーザー" : "Input / user"}</div>
                                <div className="text-[11px] text-zinc-300 whitespace-pre-wrap">{c.input?.user_message || ""}</div>
                              </div>
                              <div className="border border-surface-3 rounded p-2 bg-surface-1">
                                <div className="text-[11px] text-zinc-500 mb-1">{isJa ? "出力" : "Output"}</div>
                                <div className="text-[11px] text-zinc-300 whitespace-pre-wrap">{formatAnyData(c.output || "")}</div>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="border border-surface-3 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-zinc-100">{isJa ? "トライアル横断分析" : "跨 Trial 分析"}</div>
                  <button
                    className="px-3 py-1.5 text-xs rounded bg-surface-2 border border-surface-3 hover:bg-surface-3 disabled:opacity-50"
                    onClick={runDiagnosis}
                    disabled={diagnosing}
                  >
                    {diagnosing ? (isJa ? "生成中..." : "生成中...") : (isJa ? "分析を生成" : "生成分析")}
                  </button>
                </div>
                {!diagnosis ? (
                  <div className="text-xs text-zinc-500">{isJa ? "分析結果はまだありません" : "暂无分析结果"}</div>
                ) : (
                  <div className="space-y-2">
                    {(diagnosis.patterns || []).map((p, i: number) => (
                      <div key={i} className="text-sm text-zinc-300">- {p.title} ({p.frequency})</div>
                    ))}
                    {(diagnosis.suggestions || []).map((s, i: number) => (
                      <div key={i} className="bg-surface-1 border border-surface-3 rounded p-2">
                        <div className="text-sm text-zinc-200">{s.title}</div>
                        <div className="text-xs text-zinc-400 mt-1">{s.detail}</div>
                        {onSendToAgent && (
                          <button
                            className="mt-2 text-xs px-2 py-1 rounded bg-brand-500/20 text-brand-300 hover:bg-brand-500/30 disabled:opacity-60"
                            onClick={() => sendSuggestionToAgent(`${selectedExecution.task_name} / ${isJa ? "トライアル横断分析" : "跨Trial分析"}`, String(s.detail || s.title || ""))}
                            disabled={!!sentSuggestionKeys[`${selectedExecution.task_name} / ${isJa ? "トライアル横断分析" : "跨Trial分析"}::${String(s.detail || s.title || "")}`]}
                          >
                            {sentSuggestionKeys[`${selectedExecution.task_name} / ${isJa ? "トライアル横断分析" : "跨Trial分析"}::${String(s.detail || s.title || "")}`] ? (isJa ? "修正済み" : "已修改") : (isJa ? "Agent に修正依頼" : "让Agent修改")}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function parsePersonas(content: string): Array<{ id: string; name: string }> {
  try {
    const data: unknown = JSON.parse(content || "{}");
    const personaOwner = isRecord(data) ? data : {};
    const personas = Array.isArray(personaOwner.personas) ? personaOwner.personas : [];
    return personas
      .filter((p): p is { id: string; name: string } => isRecord(p) && typeof p.id === "string" && typeof p.name === "string")
      .map((p) => ({ id: p.id, name: p.name }));
  } catch {
    return [];
  }
}

function errorMessage(error: unknown, isJa: boolean = false): string {
  if (error instanceof Error) return error.message;
  return String(error ?? (isJa ? "不明なエラー" : "未知错误"));
}

function collectTrialSuggestions(trial: EvalTrialDetail): string[] {
  if (Array.isArray(trial?.improvement_suggestions) && trial.improvement_suggestions.length > 0) {
    return Array.from(new Set(trial.improvement_suggestions.map((x) => String(x || "").trim()).filter((x: string) => x.length > 0)));
  }
  const fallback: string[] = [];
  for (const gr of trial?.grader_results || []) {
    fallback.push(...extractSuggestions(String(gr?.feedback || "")));
  }
  return Array.from(new Set(fallback));
}

function formatProcessStep(formType: string, step: ProcessStep, isJa: boolean = false): string {
  if (!step) return "";
  if (typeof step?.role === "string" || typeof step?.content === "string") {
    return `[${step.role || "assistant"}]\n${step.content || ""}`;
  }
  if (formType === "experience") {
    if (step.type === "plan") {
      const data = isRecord(step.data) ? step.data : {};
      const rawPlan = Array.isArray(data.plan) ? data.plan : [];
      const goal = String(data.overall_goal || "").trim();
      const lines = rawPlan.map((x, i: number) => {
        const item = isRecord(x) ? x : {};
        return `${i + 1}. ${String(item.block_title || item.block_id || (isJa ? "内容ブロック" : "内容块"))}：${String(item.reason || "")}`;
      });
      return [isJa ? `探索目標：${goal || "未設定"}` : `探索目标：${goal || "未提供"}`, ...lines].join("\n");
    }
    if (step.type === "per_block") {
      const d = isRecord(step.data) ? step.data : {};
      return [
        isJa ? `内容ブロック：${step?.block_title || step?.block_id || "未設定"}` : `内容块：${step?.block_title || step?.block_id || "未命名"}`,
        isJa ? `発見：${String(d.discovery || "未設定")}` : `发现：${String(d.discovery || "未提供")}`,
        isJa ? `疑問：${String(d.doubt || "なし")}` : `疑问：${String(d.doubt || "无")}`,
        isJa ? `不足：${String(d.missing || "なし")}` : `缺失：${String(d.missing || "无")}`,
        isJa ? `感想：${String(d.feeling || "未設定")}` : `感受：${String(d.feeling || "未提供")}`,
        isJa ? `評価：${typeof d.score === "number" ? d.score : "-"}` : `评分：${typeof d.score === "number" ? d.score : "-"}`,
      ].join("\n");
    }
    if (step.type === "summary") {
      const d = isRecord(step.data) ? step.data : {};
      const addressed = Array.isArray(d.concerns_addressed) ? d.concerns_addressed.map(String).join("、") : (isJa ? "なし" : "无");
      const unaddressed = Array.isArray(d.concerns_unaddressed) ? d.concerns_unaddressed.map(String).join("、") : (isJa ? "なし" : "无");
      return [
        isJa ? `全体印象：${String(d.overall_impression || "未設定")}` : `总体印象：${String(d.overall_impression || "未提供")}`,
        isJa ? `満たされた関心：${addressed}` : `已满足关切：${addressed}`,
        isJa ? `未解消の関心：${unaddressed}` : `未满足关切：${unaddressed}`,
        isJa ? `結論：${String(d.summary || "未設定")}` : `结论：${String(d.summary || "未提供")}`,
      ].join("\n");
    }
  }
  return formatAnyData(step?.data ?? step);
}

function extractSuggestions(feedback: string): string[] {
  if (!feedback || typeof feedback !== "string") return [];
  const changeKeywords = ["建议", "需要", "应当", "应", "优化", "改", "补充", "删除", "避免", "修正", "调整", "简化", "明确", "改善", "見直し", "修正", "調整", "削除", "追加", "補足", "明確化", "簡潔化", "最適化"];
  const positiveOnlyKeywords = ["高质量", "优秀", "不错", "清晰", "有条理", "有深度", "完整", "稳定", "较好", "很好", "友好", "高品質", "優秀", "明確", "良い", "良好", "完全", "安定", "わかりやすい"];
  const lines = feedback
    .split(/\n|。|；|;/g)
    .map((s) => s.trim())
    .filter((s) => s.length >= 8)
    .filter((s) => changeKeywords.some((k) => s.includes(k)))
    .filter((s) => !positiveOnlyKeywords.some((k) => s.includes(k) && !changeKeywords.some((ck) => s.includes(ck))));
  return Array.from(new Set(lines)).slice(0, 4);
}

function formatAnyData(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

