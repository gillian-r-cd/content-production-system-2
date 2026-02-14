// frontend/components/settings/system-prompts-section.tsx
// 功能: 传统流程提示词管理

"use client";

import { useState } from "react";
import { settingsAPI } from "@/lib/api";
import { FormField, ImportExportButtons, SingleExportButton, downloadJSON } from "./shared";

export function SystemPromptsSection({ prompts, onRefresh }: { prompts: any[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<any>({});

  const PHASE_NAMES: Record<string, string> = {
    intent: "意图分析",
    research: "消费者调研",
    design_inner: "内涵设计",
    produce_inner: "内涵生产",
    design_outer: "外延设计",
    produce_outer: "外延生产",
    simulate: "消费者模拟",
    evaluate: "评估",
  };

  const handleEdit = (prompt: any) => {
    setEditingId(prompt.id);
    setEditForm({ ...prompt });
  };

  const handleSave = async () => {
    try {
      await settingsAPI.updateSystemPrompt(editingId!, editForm);
      setEditingId(null);
      onRefresh();
    } catch (err) {
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  const handleExportAll = async () => {
    try {
      const result = await settingsAPI.exportSystemPrompts();
      downloadJSON(result, `system_prompts_${new Date().toISOString().split("T")[0]}.json`);
    } catch (err) {
      alert("导出失败");
    }
  };

  const handleExportSingle = async (id: string) => {
    try {
      const result = await settingsAPI.exportSystemPrompts(id);
      const prompt = prompts.find(p => p.id === id);
      downloadJSON(result, `system_prompt_${prompt?.phase || id}.json`);
    } catch (err) {
      alert("导出失败");
    }
  };

  const handleImport = async (data: any[]) => {
    await settingsAPI.importSystemPrompts(data);
    onRefresh();
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">传统流程提示词</h2>
          <p className="text-sm text-zinc-500 mt-1">
            传统流程中各组的提示词。此提示词将完整发送给 LLM，所见即所得。
          </p>
        </div>
        <ImportExportButtons
          typeName="传统流程提示词"
          onExportAll={handleExportAll}
          onImport={handleImport}
        />
      </div>

      <div className="space-y-4">
        {prompts.map((prompt) => (
          <div key={prompt.id} className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
            {editingId === prompt.id ? (
              <div className="space-y-4">
                <FormField label="提示词名称">
                  <input
                    type="text"
                    value={editForm.name || ""}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
                  />
                </FormField>
                <FormField label="适用组">
                  <select
                    value={editForm.phase || ""}
                    onChange={(e) => setEditForm({ ...editForm, phase: e.target.value })}
                    className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
                  >
                    {Object.entries(PHASE_NAMES).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </FormField>
                <FormField label="提示词内容（完整版）" hint="此提示词将完整发送给 LLM，所见即所得。占位符：{creator_profile} = 创作者特质，{dependencies} = 依赖内容块内容，{channel} = 目标渠道">
                  <textarea
                    value={editForm.content || ""}
                    onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                    rows={14}
                    className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 font-mono text-sm resize-y"
                  />
                  <div className="flex items-center gap-2 mt-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${(editForm.content || "").includes("{creator_profile}") ? "bg-green-500/15 text-green-400 border border-green-500/30" : "bg-zinc-700/50 text-zinc-500 border border-zinc-600/30"}`}>
                      {(editForm.content || "").includes("{creator_profile}") ? "✓" : "○"} {"{creator_profile}"}
                    </span>
                    <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${(editForm.content || "").includes("{dependencies}") ? "bg-green-500/15 text-green-400 border border-green-500/30" : "bg-zinc-700/50 text-zinc-500 border border-zinc-600/30"}`}>
                      {(editForm.content || "").includes("{dependencies}") ? "✓" : "○"} {"{dependencies}"}
                    </span>
                    <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${(editForm.content || "").includes("{channel}") ? "bg-green-500/15 text-green-400 border border-green-500/30" : "bg-zinc-700/50 text-zinc-500 border border-zinc-600/30"}`}>
                      {(editForm.content || "").includes("{channel}") ? "✓" : "○"} {"{channel}"}
                    </span>
                  </div>
                </FormField>
                <div className="flex gap-2">
                  <button onClick={handleSave} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">保存</button>
                  <button onClick={() => setEditingId(null)} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">取消</button>
                </div>
              </div>
            ) : (
              <div>
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-medium text-zinc-200">{prompt.name}</h3>
                    <span className="inline-block mt-1 text-xs bg-brand-600/20 text-brand-400 px-2 py-0.5 rounded">
                      {PHASE_NAMES[prompt.phase] || prompt.phase}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <SingleExportButton onExport={() => handleExportSingle(prompt.id)} title="导出此提示词" />
                    <button onClick={() => handleEdit(prompt)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">
                      编辑
                    </button>
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${prompt.content?.includes("{creator_profile}") ? "bg-green-500/15 text-green-400 border border-green-500/30" : "bg-zinc-700/50 text-zinc-500 border border-zinc-600/30"}`}>
                    {prompt.content?.includes("{creator_profile}") ? "✓" : "✗"} {"{creator_profile}"}
                  </span>
                  <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${prompt.content?.includes("{dependencies}") ? "bg-green-500/15 text-green-400 border border-green-500/30" : "bg-zinc-700/50 text-zinc-500 border border-zinc-600/30"}`}>
                    {prompt.content?.includes("{dependencies}") ? "✓" : "○"} {"{dependencies}"}
                  </span>
                  <span className="text-xs text-zinc-600">← 所见即所得</span>
                </div>
                <p className="text-sm text-zinc-500 mt-2 whitespace-pre-wrap line-clamp-3">{prompt.content}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
