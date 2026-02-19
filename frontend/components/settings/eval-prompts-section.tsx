"use client";

import { useMemo, useState } from "react";
import { evalAPI, settingsAPI } from "@/lib/api";
import { sendNotification } from "@/lib/utils";

const REQUIRED_PLACEHOLDERS: Record<string, string[]> = {
  eval_experience_plan: ["{persona}", "{probe_section}", "{block_list}"],
  eval_experience_per_block: ["{persona}", "{probe_section}", "{exploration_memory}", "{block_title}", "{block_content}"],
  eval_experience_summary: ["{persona}", "{probe_section}", "{all_block_results}"],
  eval_scenario_role_a: ["{persona}", "{content}", "{probe_section}"],
  eval_scenario_role_b: ["{persona}", "{probe_section}"],
  eval_cross_trial_analysis: ["{all_trial_results}"],
};

const PHASE_TO_PROMPT_TYPE: Record<string, string> = {
  eval_experience_plan: "consumer_prompt",
  eval_experience_per_block: "consumer_prompt",
  eval_experience_summary: "consumer_prompt",
  eval_scenario_role_a: "seller_prompt",
  eval_scenario_role_b: "buyer_prompt",
  eval_cross_trial_analysis: "grader_prompt",
};

interface EvalPromptItem {
  id: string;
  phase: string;
  name?: string;
  description?: string;
  content?: string;
}

export function EvalPromptsSection({ prompts, onRefresh }: { prompts: EvalPromptItem[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<EvalPromptItem>>({});
  const [generating, setGenerating] = useState(false);
  const [syncingPresets, setSyncingPresets] = useState(false);

  const sorted = useMemo(
    () => [...prompts].sort((a, b) => String(a.phase || "").localeCompare(String(b.phase || ""))),
    [prompts]
  );

  const beginEdit = (prompt: EvalPromptItem) => {
    setEditingId(prompt.id);
    setEditForm({ ...prompt });
  };

  const save = async () => {
    if (!editingId) return;
    try {
      await settingsAPI.updateEvalPrompt(editingId, {
        name: editForm.name || "",
        content: editForm.content || "",
        description: editForm.description || "",
      });
      setEditingId(null);
      onRefresh();
      sendNotification("评估提示词已保存", "success");
    } catch (e: unknown) {
      sendNotification(`保存失败: ${errorMessage(e)}`, "error");
    }
  };

  const generatePrompt = async () => {
    if (!editForm?.phase) return;
    setGenerating(true);
    try {
      const promptType = PHASE_TO_PROMPT_TYPE[editForm.phase] || "grader_prompt";
      const out = await evalAPI.generatePrompt(promptType, {
        form_type: editForm.phase,
        description: editForm.description || editForm.name || "",
      });
      setEditForm((prev) => ({ ...prev, content: out.generated_prompt || prev.content }));
      sendNotification("AI 提示词已生成，可继续微调后保存", "success");
    } catch (e: unknown) {
      sendNotification(`AI 生成失败: ${errorMessage(e)}`, "error");
    } finally {
      setGenerating(false);
    }
  };

  const syncPresets = async () => {
    setSyncingPresets(true);
    try {
      const out = await settingsAPI.syncEvalPresets();
      sendNotification(
        `同步完成：Grader 新增${out.imported_graders}/更新${out.updated_graders}；Simulator 新增${out.imported_simulators}/更新${out.updated_simulators}`,
        "success"
      );
      onRefresh();
    } catch (e: unknown) {
      sendNotification(`同步失败: ${errorMessage(e)}`, "error");
    } finally {
      setSyncingPresets(false);
    }
  };

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-3">
        <h2 className="text-xl font-semibold text-zinc-100">评估提示词</h2>
        <button
          onClick={syncPresets}
          disabled={syncingPresets}
          className="px-3 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg text-sm disabled:opacity-60"
        >
          {syncingPresets ? "同步中..." : "同步预置 Grader/Simulator"}
        </button>
      </div>
      <p className="text-sm text-zinc-500 mt-1 mb-4">
        管理消费体验/场景模拟/跨Trial分析模板。人物画像提示词在项目评估页管理。
      </p>

      <div className="space-y-4">
        {sorted.map((prompt) => {
          const required = REQUIRED_PLACEHOLDERS[prompt.phase] || [];
          return (
            <div key={prompt.id} className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
              {editingId === prompt.id ? (
                <div className="space-y-3">
                  <div>
                    <div className="text-sm text-zinc-400 mb-1">名称</div>
                    <input
                      value={editForm.name || ""}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
                    />
                  </div>
                  <div>
                    <div className="text-sm text-zinc-400 mb-1">描述</div>
                    <input
                      value={editForm.description || ""}
                      onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                      className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
                    />
                  </div>
                  <div>
                    <div className="text-sm text-zinc-400 mb-1">提示词内容</div>
                    <textarea
                      value={editForm.content || ""}
                      onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                      rows={12}
                      className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 font-mono text-sm resize-y"
                    />
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {required.map((ph) => {
                      const ok = String(editForm.content || "").includes(ph);
                      return (
                        <span
                          key={ph}
                          className={`text-xs px-1.5 py-0.5 rounded font-mono ${
                            ok
                              ? "bg-green-500/15 text-green-400 border border-green-500/30"
                              : "bg-zinc-700/50 text-zinc-500 border border-zinc-600/30"
                          }`}
                        >
                          {ok ? "✓" : "○"} {ph}
                        </span>
                      );
                    })}
                  </div>
                  <div className="flex gap-2">
                    <button onClick={generatePrompt} disabled={generating} className="px-3 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg disabled:opacity-60">
                      {generating ? "生成中..." : "🤖 AI 生成"}
                    </button>
                    <button onClick={save} className="px-3 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg">保存</button>
                    <button onClick={() => setEditingId(null)} className="px-3 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">取消</button>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-medium text-zinc-100">{prompt.name}</div>
                      <div className="text-xs text-zinc-500 mt-1">{prompt.description || prompt.phase}</div>
                    </div>
                    <button onClick={() => beginEdit(prompt)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">
                      编辑
                    </button>
                  </div>
                  <p className="text-sm text-zinc-400 mt-2 whitespace-pre-wrap line-clamp-3">{prompt.content}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error ?? "未知错误");
}

