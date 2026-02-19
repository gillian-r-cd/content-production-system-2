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
import { EvalPersonaSetup } from "./eval-field-editors";
import { sendNotification } from "@/lib/utils";
import { Users, SlidersHorizontal, BarChart3, Loader2, Play, Pause, Square, Pencil, Trash2, Plus, X, RefreshCw, Eye } from "lucide-react";

interface EvalPhasePanelProps {
  projectId: string | null;
  onFieldsChange?: () => void;
  /** M3: 将消息发送到 Agent 对话面板 */
  onSendToAgent?: (message: string) => void;
  initialTab?: "persona" | "config" | "report";
}

export function EvalPhasePanel({ projectId, onFieldsChange, onSendToAgent, initialTab = "persona" }: EvalPhasePanelProps) {
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
          name: "人物画像设置",
          block_type: "field",
          content: JSON.stringify({ personas: [] }, null, 2),
          special_handler: "eval_persona_setup",
          order_index: 99,
        });
      }
      if (!config) {
        config = await blockAPI.create({
          project_id: projectId,
          name: "评估任务配置",
          block_type: "field",
          content: "",
          special_handler: "eval_task_config",
          order_index: 100,
        });
      }
      if (!report) {
        report = await blockAPI.create({
          project_id: projectId,
          name: "评估报告",
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
  }, [projectId]);

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
          <p className="text-zinc-400 text-sm">正在加载评估面板...</p>
        </div>
      </div>
    );
  }

  if (!projectId) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-zinc-500">请先选择项目</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Tab 切换 */}
      <div className="p-4 border-b border-surface-3">
        <h1 className="text-xl font-bold text-zinc-100 mb-3">评估</h1>
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
            人物画像
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
            评估配置
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
            评估报告
          </button>
        </div>
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === "persona" && personaBlock && (
          <EvalPersonaSetup block={personaBlock} projectId={projectId} onUpdate={handleUpdate} />
        )}
        {activeTab === "config" && personaBlock && configBlock && (
          <EvalV2TaskConfigPanel
            projectId={projectId}
            personaBlock={personaBlock}
            onUpdate={handleUpdate}
          />
        )}
        {activeTab === "report" && reportBlock && (
          <EvalV2ReportPanel
            projectId={projectId}
            onSendToAgent={onSendToAgent}
            onUpdate={handleUpdate}
          />
        )}
      </div>
    </div>
  );
}

interface EvalV2TaskConfigPanelProps {
  projectId: string;
  personaBlock: ContentBlock;
  onUpdate?: () => void;
}

function EvalV2TaskConfigPanel({ projectId, personaBlock, onUpdate }: EvalV2TaskConfigPanelProps) {
  const [tasks, setTasks] = useState<EvalV2Task[]>([]);
  const [graders, setGraders] = useState<GraderData[]>([]);
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
      const [taskResp, graderResp] = await Promise.all([
        evalV2API.listTasks(projectId),
        graderAPI.listForProject(projectId),
      ]);
      setTasks(taskResp.tasks || []);
      setGraders(graderResp || []);
    } catch (e: any) {
      sendNotification(`加载评估任务失败: ${e.message}`, "error");
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
    name: "新试验",
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
      sendNotification("任务名称不能为空", "error");
      return;
    }
    if (!draft.trial_configs.length) {
      sendNotification("至少需要一个试验配置", "error");
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
      sendNotification("评估任务已保存", "success");
    } catch (e: any) {
      sendNotification(`保存失败: ${e.message}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const executeTask = async (taskId: string) => {
    try {
      await evalV2API.startTask(taskId);
      await loadData(true);
      onUpdate?.();
      sendNotification("任务已开始执行", "success");
    } catch (e: any) {
      sendNotification(`执行失败: ${e.message}`, "error");
    }
  };

  const pauseTask = async (taskId: string) => {
    try {
      await evalV2API.pauseTask(taskId);
      await loadData(true);
      sendNotification("已请求暂停任务", "success");
    } catch (e: any) {
      sendNotification(`暂停失败: ${e.message}`, "error");
    }
  };

  const resumeTask = async (taskId: string) => {
    try {
      const resp = await evalV2API.resumeTask(taskId);
      await loadData(true);
      sendNotification(resp?.message || "任务已恢复执行", "success");
    } catch (e: any) {
      sendNotification(`恢复失败: ${e.message}`, "error");
    }
  };

  const stopTask = async (taskId: string) => {
    try {
      await evalV2API.stopTask(taskId);
      await loadData(true);
      sendNotification("已请求终止任务", "success");
    } catch (e: any) {
      sendNotification(`停止失败: ${e.message}`, "error");
    }
  };

  const executeAll = async () => {
    try {
      await evalV2API.executeAll(projectId);
      await loadData();
      onUpdate?.();
      sendNotification("批量执行已完成", "success");
    } catch (e: any) {
      sendNotification(`批量执行失败: ${e.message}`, "error");
    }
  };

  const deleteTask = async (taskId: string) => {
    if (!confirm("确认删除这个评估任务吗？")) return;
    try {
      await evalV2API.deleteTask(taskId);
      await loadData();
      onUpdate?.();
      sendNotification("任务已删除", "success");
    } catch (e: any) {
      sendNotification(`删除失败: ${e.message}`, "error");
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
          <label className="text-xs text-zinc-400">画像</label>
          <select
            className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
            value={selected}
            onChange={(e) => updateTrial(idx, { form_config: { ...cfg, persona_id: e.target.value } })}
          >
            <option value="">请选择画像</option>
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
            <label className="text-xs text-zinc-400">角色A画像</label>
            <select
              className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
              value={String(cfg.role_a_persona_id || "")}
              onChange={(e) => updateTrial(idx, { form_config: { ...cfg, role_a_persona_id: e.target.value } })}
            >
              <option value="">请选择</option>
              {personas.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-400">角色B画像</label>
            <select
              className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
              value={String(cfg.role_b_persona_id || "")}
              onChange={(e) => updateTrial(idx, { form_config: { ...cfg, role_b_persona_id: e.target.value } })}
            >
              <option value="">请选择</option>
              {personas.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-400">最大轮数</label>
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
        <h3 className="text-base font-semibold text-zinc-100">任务配置</h3>
        <div className="flex gap-2">
          <button className="px-3 py-2 text-sm rounded bg-surface-2 border border-surface-3 hover:bg-surface-3" onClick={executeAll}>
            全部运行
          </button>
          <button className="px-3 py-2 text-sm rounded bg-brand-500 text-white hover:bg-brand-600 flex items-center gap-1.5" onClick={openCreate}>
            <Plus className="w-4 h-4" />
            添加任务
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-zinc-400 text-sm py-6">加载中...</div>
      ) : tasks.length === 0 ? (
        <div className="border border-dashed border-surface-3 rounded-lg p-8 text-center text-zinc-500 text-sm">
          暂无评估任务，点击“添加任务”创建第一个任务。
        </div>
      ) : (
        <div className="space-y-2">
          {tasks.map((task) => (
            <div key={task.id} className="border border-surface-3 rounded-lg px-3 py-2 flex items-center justify-between">
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-100 truncate">{task.name}</div>
                <div className="text-xs text-zinc-500 mt-1">
                  {task.trial_configs.length} 个试验 · 状态: {task.progress?.pause_requested ? "pausing" : task.progress?.stop_requested ? "stopping" : task.status}
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
                      进度 {task.progress.completed || 0}/{task.progress.total || 0} ({task.progress.percent}%)
                      {task.progress.pause_requested ? " · 暂停中..." : ""}
                    </div>
                  </div>
                )}
              </div>
              <div className="flex gap-1">
                {task.status === "running" || task.progress?.is_running ? (
                  <>
                    <button className="p-2 rounded hover:bg-surface-2 text-amber-300" onClick={() => pauseTask(task.id)} title="暂停">
                      <Pause className="w-4 h-4" />
                    </button>
                    <button className="p-2 rounded hover:bg-surface-2 text-red-300" onClick={() => stopTask(task.id)} title="终止">
                      <Square className="w-4 h-4" />
                    </button>
                  </>
                ) : task.status === "paused" ? (
                  <button className="p-2 rounded hover:bg-surface-2 text-emerald-300" onClick={() => resumeTask(task.id)} title="恢复">
                    <Play className="w-4 h-4" />
                  </button>
                ) : (
                  <button className="p-2 rounded hover:bg-surface-2 text-zinc-300" onClick={() => executeTask(task.id)} title="开始">
                    <Play className="w-4 h-4" />
                  </button>
                )}
                <button className="p-2 rounded hover:bg-surface-2 text-zinc-300" onClick={() => openEdit(task)} title="编辑">
                  <Pencil className="w-4 h-4" />
                </button>
                <button className="p-2 rounded hover:bg-surface-2 text-red-400" onClick={() => deleteTask(task.id)} title="删除">
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
              <div className="text-zinc-100 font-semibold">{editingTaskId ? "编辑任务" : "添加任务"}</div>
              <button className="p-1.5 rounded hover:bg-surface-2 text-zinc-400" onClick={() => setShowModal(false)}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-zinc-400">任务名称</label>
                  <input
                    className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-3 py-2 text-sm"
                    value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-400">任务描述</label>
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
                      <div className="text-sm font-medium text-zinc-200">试验 {idx + 1}</div>
                      <button
                        className="text-xs text-red-400 hover:text-red-300"
                        onClick={() => setDraft({
                          ...draft,
                          trial_configs: draft.trial_configs.filter((_, i) => i !== idx).map((t, i) => ({ ...t, order_index: i })),
                        })}
                        disabled={draft.trial_configs.length <= 1}
                      >
                        删除
                      </button>
                    </div>
                    <div className="grid grid-cols-4 gap-2">
                      <div className="col-span-2">
                        <label className="text-xs text-zinc-400">试验名称</label>
                        <input
                          className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
                          value={trial.name}
                          onChange={(e) => updateTrial(idx, { name: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-zinc-400">形态</label>
                        <select
                          className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
                          value={trial.form_type}
                          onChange={(e) => updateTrial(idx, { form_type: e.target.value as EvalV2TrialConfig["form_type"] })}
                        >
                          <option value="assessment">直接判定</option>
                          <option value="review">视角审查</option>
                          <option value="experience">消费体验</option>
                          <option value="scenario">场景模拟</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-zinc-400">执行次数</label>
                        <input
                          type="number"
                          min={1}
                          className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
                          value={trial.repeat_count}
                          onChange={(e) => updateTrial(idx, { repeat_count: Math.max(1, Number(e.target.value || 1)) })}
                        />
                      </div>
                    </div>

                    {renderTrialFormConfig(trial, idx)}

                    <div>
                      <label className="text-xs text-zinc-400">焦点（可选）</label>
                      <input
                        className="w-full mt-1 bg-surface-1 border border-surface-3 rounded px-2 py-1.5 text-sm"
                        value={trial.probe || ""}
                        onChange={(e) => updateTrial(idx, { probe: e.target.value })}
                      />
                    </div>

                    <div>
                      <label className="text-xs text-zinc-400 block mb-1">评分器</label>
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
                添加试验
              </button>
            </div>
            <div className="px-4 py-3 border-t border-surface-3 flex justify-end gap-2">
              <button className="px-3 py-2 text-sm rounded bg-surface-2 border border-surface-3" onClick={() => setShowModal(false)}>
                取消
              </button>
              <button className="px-3 py-2 text-sm rounded bg-brand-500 text-white disabled:opacity-50" onClick={saveTask} disabled={saving}>
                {saving ? "保存中..." : "保存"}
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
  onUpdate?: () => void;
  onSendToAgent?: (message: string) => void;
}

function EvalV2ReportPanel({ projectId, onUpdate, onSendToAgent }: EvalV2ReportPanelProps) {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [selectedExecution, setSelectedExecution] = useState<any | null>(null);
  const [detail, setDetail] = useState<any | null>(null);
  const [diagnosis, setDiagnosis] = useState<any | null>(null);
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
    } catch (e: any) {
      sendNotification(`加载报告失败: ${e.message}`, "error");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const openExecution = async (execution: any) => {
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
      for (const s of stateResp.states || []) {
        if ((s.status || "") === "applied") {
          stateMap[`${s.source}::${s.suggestion}`] = true;
        }
      }
      setSentSuggestionKeys(stateMap);
    } catch (e: any) {
      sendNotification(`加载任务详情失败: ${e.message}`, "error");
    }
  };

  const keyOf = (r: any) => `${r.task_id}::${r.batch_id}`;

  const toggleSelect = (r: any) => {
    const key = keyOf(r);
    setSelectedKeys((prev) => (prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]));
  };

  const deleteOne = async (r: any) => {
    if (!confirm(`确认删除记录？\n任务: ${r.task_name}\n批次: ${String(r.batch_id || "").slice(0, 8)}`)) return;
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
      sendNotification("记录已删除", "success");
    } catch (e: any) {
      sendNotification(`删除失败: ${e.message}`, "error");
    } finally {
      setDeleting(false);
    }
  };

  const deleteSelected = async () => {
    if (!selectedKeys.length) return;
    if (!confirm(`确认批量删除 ${selectedKeys.length} 条记录吗？`)) return;
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
      sendNotification(`已删除 ${items.length} 条记录`, "success");
    } catch (e: any) {
      sendNotification(`批量删除失败: ${e.message}`, "error");
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
      sendNotification("跨 Trial 分析已生成", "success");
    } catch (e: any) {
      sendNotification(`分析失败: ${e.message}`, "error");
    } finally {
      setDiagnosing(false);
    }
  };

  const sendSuggestionToAgent = async (source: string, suggestion: string) => {
    if (!onSendToAgent) return;
    if (!selectedExecution) return;
    const key = `${source}::${suggestion}`;
    const msg = `请根据评估建议修改内容。\n来源: ${source}\n建议: ${suggestion}\n要求: 先给出可执行编辑方案，并输出可确认的修改建议。`;
    try {
      await evalV2API.markSuggestionApplied(selectedExecution.task_id, selectedExecution.batch_id, {
        source,
        suggestion,
        status: "applied",
      });
      onSendToAgent(msg);
      setSentSuggestionKeys((prev) => ({ ...prev, [key]: true }));
      sendNotification("建议已发送到 Agent 面板", "success");
    } catch (e: any) {
      sendNotification(`发送失败: ${e.message}`, "error");
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-zinc-100">评估报告</h3>
        <div className="flex items-center gap-2">
          <button
            className="px-3 py-2 text-sm rounded bg-red-500/15 border border-red-500/40 text-red-300 hover:bg-red-500/25 disabled:opacity-50"
            onClick={deleteSelected}
            disabled={deleting || selectedKeys.length === 0}
          >
            批量删除 ({selectedKeys.length})
          </button>
          <button className="px-3 py-2 text-sm rounded bg-surface-2 border border-surface-3 hover:bg-surface-3 flex items-center gap-1.5" onClick={loadReport}>
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-zinc-400 text-sm py-6">加载中...</div>
      ) : rows.length === 0 ? (
        <div className="border border-dashed border-surface-3 rounded-lg p-8 text-center text-zinc-500 text-sm">
          暂无执行记录。请先在任务配置页执行任务。
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
                    删除
                  </button>
                </div>
              </div>
              <div className="text-xs text-zinc-500 mt-1">状态: {r.status} · 执行时间: {r.executed_at || "-"} · batch: {String(r.batch_id || "").slice(0, 8)}</div>
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
                <div className="text-xs text-zinc-500 mt-1">总分: {typeof selectedExecution.overall === "number" ? selectedExecution.overall.toFixed(2) : "-"} · batch: {String(selectedExecution.batch_id || "").slice(0, 8)}</div>
              </div>
              <button className="p-1.5 rounded hover:bg-surface-2 text-zinc-400" onClick={() => { setSelectedExecution(null); setDetail(null); setDiagnosis(null); setExpandedPromptTrialId(null); setSentSuggestionKeys({}); }}>
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 space-y-4">
              <div className="border border-surface-3 rounded-lg p-3">
                <div className="text-sm font-medium text-zinc-100 mb-2">总览指标</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                  <div className="bg-surface-1 border border-surface-3 rounded px-2 py-1.5">
                    <div className="text-zinc-500 text-xs">总分</div>
                    <div className="text-zinc-100 font-medium">{typeof selectedExecution.overall === "number" ? selectedExecution.overall.toFixed(2) : "-"}</div>
                  </div>
                  <div className="bg-surface-1 border border-surface-3 rounded px-2 py-1.5">
                    <div className="text-zinc-500 text-xs">批次状态</div>
                    <div className="text-zinc-100 font-medium">{selectedExecution.status || "-"}</div>
                  </div>
                  <div className="bg-surface-1 border border-surface-3 rounded px-2 py-1.5">
                    <div className="text-zinc-500 text-xs">Trial 数</div>
                    <div className="text-zinc-100 font-medium">{selectedExecution.trial_count ?? "-"}</div>
                  </div>
                  <div className="bg-surface-1 border border-surface-3 rounded px-2 py-1.5">
                    <div className="text-zinc-500 text-xs">执行时间</div>
                    <div className="text-zinc-100 font-medium">{selectedExecution.executed_at || "-"}</div>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-zinc-100">试验详情</div>
                {(detail?.trials || []).map((t: any) => (
                  <div key={t.id} className="border border-surface-3 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="text-sm text-zinc-100">
                        {t.trial_config_name || `试验 ${t.form_type}`} · repeat {t.repeat_index + 1}
                      </div>
                      <div className="text-sm text-zinc-300">{typeof t.overall_score === "number" ? t.overall_score.toFixed(2) : "-"}</div>
                    </div>
                    <div className="text-xs text-zinc-500">状态: {t.status} · LLM调用: {(t.llm_calls || []).length}</div>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(t.dimension_scores || {}).length === 0 ? (
                        <span className="text-xs text-zinc-500">本 Trial 暂无维度分</span>
                      ) : (
                        Object.entries(t.dimension_scores || {}).map(([dim, score]: any) => (
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
                        {expandedPromptTrialId === t.id ? "收起过程与调用明细" : "查看过程与调用明细"}
                      </button>
                    </div>
                    {(t.grader_results || []).map((gr: any, i: number) => (
                      <div key={i} className="bg-surface-1 border border-surface-3 rounded p-2 text-sm">
                        <div className="text-zinc-200">{gr.grader_name}</div>
                        <div className="text-zinc-400 text-xs mt-1 whitespace-pre-wrap">{gr.feedback || "无反馈"}</div>
                        {extractSuggestions(gr.feedback).map((sg, sgIdx) => (
                          <div key={sgIdx} className="mt-2 flex items-center justify-between bg-surface-2 border border-surface-3 rounded px-2 py-1.5">
                            <span className="text-xs text-zinc-300">{sg}</span>
                            {onSendToAgent && (
                              <button
                                className="text-xs px-2 py-1 rounded bg-brand-500/20 text-brand-300 hover:bg-brand-500/30 disabled:opacity-60"
                                onClick={() => sendSuggestionToAgent(`${selectedExecution.task_name} / ${gr.grader_name}`, sg)}
                                disabled={!!sentSuggestionKeys[`${selectedExecution.task_name} / ${gr.grader_name}::${sg}`]}
                              >
                                {sentSuggestionKeys[`${selectedExecution.task_name} / ${gr.grader_name}::${sg}`] ? "已修改" : "让Agent修改"}
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    ))}

                    {expandedPromptTrialId === t.id && (
                      <div className="border border-surface-3 rounded p-2 bg-surface-1 space-y-2">
                        <div className="text-xs text-zinc-300">过程回放</div>
                        {(t.process || []).length === 0 ? (
                          <div className="text-xs text-zinc-500">无过程记录</div>
                        ) : (
                          (t.process || []).map((p: any, idx: number) => (
                            <div key={idx} className="border border-surface-3 rounded bg-surface-0 p-2 space-y-1">
                              <div className="text-xs text-zinc-400">#{idx + 1} · {p.type || "dialogue_step"}</div>
                              {(typeof p?.role === "string" || typeof p?.content === "string") ? (
                                <div className="text-[11px] text-zinc-300 whitespace-pre-wrap">
                                  <span className="text-zinc-500">[{p.role || "assistant"}]</span>{"\n"}{p.content || ""}
                                </div>
                              ) : (
                                <div className="text-[11px] text-zinc-300 whitespace-pre-wrap">
                                  {formatAnyData(p?.data ?? p)}
                                </div>
                              )}
                            </div>
                          ))
                        )}

                        <div className="text-xs text-zinc-300 mt-2">LLM 调用明细（逐次输入 / 输出）</div>
                        {(t.llm_calls || []).length === 0 ? (
                          <div className="text-xs text-zinc-500">无调用记录</div>
                        ) : (
                          (t.llm_calls || []).map((c: any, idx: number) => (
                            <div key={idx} className="border border-surface-3 rounded bg-surface-0 p-2 space-y-2">
                              <div className="text-xs text-zinc-400">
                                #{idx + 1} · step: {c.step || "-"} · in/out: {c.tokens_in ?? 0}/{c.tokens_out ?? 0} · cost: {typeof c.cost === "number" ? c.cost.toFixed(6) : "0.000000"}
                              </div>
                              <div className="border border-surface-3 rounded p-2 bg-surface-1">
                                <div className="text-[11px] text-zinc-500 mb-1">Input / system</div>
                                <div className="text-[11px] text-zinc-300 whitespace-pre-wrap">{c.input?.system_prompt || ""}</div>
                              </div>
                              <div className="border border-surface-3 rounded p-2 bg-surface-1">
                                <div className="text-[11px] text-zinc-500 mb-1">Input / user</div>
                                <div className="text-[11px] text-zinc-300 whitespace-pre-wrap">{c.input?.user_message || ""}</div>
                              </div>
                              <div className="border border-surface-3 rounded p-2 bg-surface-1">
                                <div className="text-[11px] text-zinc-500 mb-1">Output</div>
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
                  <div className="text-sm font-medium text-zinc-100">跨 Trial 分析</div>
                  <button
                    className="px-3 py-1.5 text-xs rounded bg-surface-2 border border-surface-3 hover:bg-surface-3 disabled:opacity-50"
                    onClick={runDiagnosis}
                    disabled={diagnosing}
                  >
                    {diagnosing ? "生成中..." : "生成分析"}
                  </button>
                </div>
                {!diagnosis ? (
                  <div className="text-xs text-zinc-500">暂无分析结果</div>
                ) : (
                  <div className="space-y-2">
                    {(diagnosis.patterns || []).map((p: any, i: number) => (
                      <div key={i} className="text-sm text-zinc-300">- {p.title} ({p.frequency})</div>
                    ))}
                    {(diagnosis.suggestions || []).map((s: any, i: number) => (
                      <div key={i} className="bg-surface-1 border border-surface-3 rounded p-2">
                        <div className="text-sm text-zinc-200">{s.title}</div>
                        <div className="text-xs text-zinc-400 mt-1">{s.detail}</div>
                        {onSendToAgent && (
                          <button
                            className="mt-2 text-xs px-2 py-1 rounded bg-brand-500/20 text-brand-300 hover:bg-brand-500/30 disabled:opacity-60"
                            onClick={() => sendSuggestionToAgent(`${selectedExecution.task_name} / 跨Trial分析`, s.detail || s.title)}
                            disabled={!!sentSuggestionKeys[`${selectedExecution.task_name} / 跨Trial分析::${s.detail || s.title}`]}
                          >
                            {sentSuggestionKeys[`${selectedExecution.task_name} / 跨Trial分析::${s.detail || s.title}`] ? "已修改" : "让Agent修改"}
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
    const data = JSON.parse(content || "{}");
    const personas = Array.isArray(data.personas) ? data.personas : [];
    return personas
      .filter((p: any) => p && typeof p.id === "string" && typeof p.name === "string")
      .map((p: any) => ({ id: p.id, name: p.name }));
  } catch {
    return [];
  }
}

function extractSuggestions(feedback: string): string[] {
  if (!feedback || typeof feedback !== "string") return [];
  const changeKeywords = ["建议", "需要", "应当", "应", "优化", "改", "补充", "删除", "避免", "修正", "调整", "简化", "明确"];
  const positiveOnlyKeywords = ["高质量", "优秀", "不错", "清晰", "有条理", "有深度", "完整", "稳定", "较好", "很好", "友好"];
  const lines = feedback
    .split(/\n|。|；|;/g)
    .map((s) => s.trim())
    .filter((s) => s.length >= 8)
    .filter((s) => changeKeywords.some((k) => s.includes(k)))
    .filter((s) => !positiveOnlyKeywords.some((k) => s.includes(k) && !changeKeywords.some((ck) => s.includes(ck))));
  return Array.from(new Set(lines)).slice(0, 4);
}

function formatAnyData(value: any): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

