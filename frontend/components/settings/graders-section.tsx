// frontend/components/settings/graders-section.tsx
// 功能: 评分器管理

"use client";

import { useState } from "react";
import { graderAPI } from "@/lib/api";
import type { GraderData } from "@/lib/api";
import { FormField, ImportExportButtons, SingleExportButton, downloadJSON, LOCALE_OPTIONS, LocaleBadge, useSettingsUiIsJa, useSettingsUiLocale } from "./shared";

function getGraderTypeLabels(isJa: boolean): Record<string, { label: string; desc: string; color: string }> {
  return {
    content_only: {
      label: isJa ? "内容のみ評価" : "仅评内容",
      desc: isJa ? "内容品質のみを評価し、対話プロセスは渡しません" : "直接评价内容质量，不传互动过程",
      color: "text-blue-400 bg-blue-500/15 border-blue-500/30",
    },
    content_and_process: {
      label: isJa ? "内容+対話を評価" : "评内容+互动",
      desc: isJa ? "内容と対話プロセスの両方を評価します" : "同时评价内容和互动过程",
      color: "text-purple-400 bg-purple-500/15 border-purple-500/30",
    },
  };
}

export function GradersSection({ graders, onRefresh }: { graders: GraderData[]; onRefresh: () => void }) {
  const uiLocale = useSettingsUiLocale();
  const isJa = useSettingsUiIsJa();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [editForm, setEditForm] = useState<Partial<GraderData>>({});
  const graderTypeLabels = getGraderTypeLabels(isJa);

  // ---- 导入导出 ----
  const handleExportAll = async () => {
    try {
      const result = await graderAPI.exportAll();
      downloadJSON(result, `graders_${new Date().toISOString().split("T")[0]}.json`);
    } catch {
      alert(isJa ? "エクスポートに失敗しました" : "导出失败");
    }
  };

  const handleExportSingle = async (id: string) => {
    try {
      const result = await graderAPI.exportAll(id);
      const grader = graders.find(g => g.id === id);
      downloadJSON(result, `grader_${grader?.name || id}.json`);
    } catch {
      alert(isJa ? "エクスポートに失敗しました" : "导出失败");
    }
  };

  const handleImport = async (data: unknown[]) => {
    await graderAPI.importAll(data);
    onRefresh();
  };

  const startCreate = () => {
    setEditForm({
      name: "",
      locale: uiLocale,
      grader_type: "content_only",
      prompt_template: isJa ? `あなたは内容レビューの専門家です。以下の内容を客観的かつ厳密に評価してください。

【評価対象内容】
{content}

【評価軸】
1. 評価軸1 (1-10): 説明
2. 評価軸2 (1-10): 説明

以下の JSON 形式のみを厳密に出力し、他の内容は出力しないでください:
{{"scores": {{"評価軸1": 点数, "評価軸2": 点数}}, "comments": {{"評価軸1": "講評", "評価軸2": "講評"}}, "feedback": "総合評価と改善提案（100-200字）"}}`
      : `你是一位内容评审专家。请对以下内容进行客观、严谨的评分。

【被评估内容】
{content}

【评估维度】
1. 维度一 (1-10): 描述
2. 维度二 (1-10): 描述

请严格输出以下 JSON 格式，不要输出其他内容：
{{"scores": {{"维度一": 分数, "维度二": 分数}}, "comments": {{"维度一": "评语", "维度二": "评语"}}, "feedback": "整体评价和改进建议（100-200字）"}}`,
      dimensions: [],
      scoring_criteria: {},
    });
    setIsCreating(true);
    setEditingId(null);
  };

  const startEdit = (g: GraderData) => {
    setEditForm({ ...g });
    setEditingId(g.id);
    setIsCreating(false);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setIsCreating(false);
    setEditForm({});
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await graderAPI.create(editForm);
      } else if (editingId) {
        await graderAPI.update(editingId, editForm);
      }
      cancelEdit();
      onRefresh();
    } catch (err: unknown) {
      alert((isJa ? "保存に失敗しました: " : "保存失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(isJa ? "この評価器を削除しますか？" : "确认删除此评分器？")) return;
    try {
      await graderAPI.delete(id);
      onRefresh();
    } catch (err: unknown) {
      alert((isJa ? "削除に失敗しました: " : "删除失败: ") + (err instanceof Error ? err.message : (isJa ? "既定評価器は削除できません" : "预置评分器不可删除")));
    }
  };

  const addDimension = () => {
    const dims = [...(editForm.dimensions || []), ""];
    setEditForm({ ...editForm, dimensions: dims });
  };

  const removeDimension = (idx: number) => {
    const dims = [...(editForm.dimensions || [])];
    dims.splice(idx, 1);
    setEditForm({ ...editForm, dimensions: dims });
  };

  const updateDimension = (idx: number, value: string) => {
    const dims = [...(editForm.dimensions || [])];
    dims[idx] = value;
    setEditForm({ ...editForm, dimensions: dims });
  };

  const renderForm = () => (
    <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl space-y-4">
      <FormField label={isJa ? "評価器名" : "评分器名称"}>
        <input
          type="text"
          value={editForm.name || ""}
          onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
          className="w-full bg-surface-1 border border-surface-3 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
          placeholder={isJa ? "例: 戦略整合評価器" : "如：策略对齐评分器"}
        />
      </FormField>

      <FormField label={isJa ? "言語" : "语言"}>
        <select
          value={editForm.locale || uiLocale}
          onChange={(e) => setEditForm({ ...editForm, locale: e.target.value })}
          className="w-full bg-surface-1 border border-surface-3 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          {LOCALE_OPTIONS.map((item) => (
            <option key={item.value} value={item.value}>{item.label}</option>
          ))}
        </select>
      </FormField>

      <FormField label={isJa ? "評価器タイプ" : "评分器类型"} hint={isJa ? "content_only = 内容のみを LLM に渡して評価; content_and_process = 内容と対話プロセスを渡して評価" : "content_only = 仅传内容给 LLM 评分；content_and_process = 传内容+互动过程"}>
        <select
          value={editForm.grader_type || "content_only"}
          onChange={(e) => setEditForm({ ...editForm, grader_type: e.target.value })}
          className="w-full bg-surface-1 border border-surface-3 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          {Object.entries(graderTypeLabels).map(([k, v]) => (
            <option key={k} value={k}>{v.label} — {v.desc}</option>
          ))}
        </select>
      </FormField>

      <FormField label={isJa ? "評価プロンプト（完全版）" : "评分提示词（完整版）"} hint={isJa ? "このプロンプトはそのまま LLM に送信されます。{content} = 評価対象内容、{process} = 対話プロセス。テンプレートは WYSIWYG です。" : "此提示词将完整发送给 LLM。占位符：{content} = 被评内容，{process} = 互动过程。模板即所见即所得。"}>
        <textarea
          value={editForm.prompt_template || ""}
          onChange={(e) => setEditForm({ ...editForm, prompt_template: e.target.value })}
          rows={12}
          className="w-full bg-surface-1 border border-surface-3 rounded-lg px-3 py-2.5 text-sm text-zinc-200 font-mono focus:outline-none focus:ring-2 focus:ring-brand-500 resize-y"
          placeholder={isJa ? "以下の内容を評価してください:&#10;&#10;【評価内容】&#10;{{content}}&#10;..." : "请评估以下内容：&#10;&#10;【评估内容】&#10;{{content}}&#10;..."}
        />
      </FormField>

      <FormField label={isJa ? "評価軸" : "评分维度"}>
        <div className="space-y-2">
          {(editForm.dimensions || []).map((dim, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type="text"
                value={dim}
                onChange={(e) => updateDimension(idx, e.target.value)}
                className="flex-1 bg-surface-1 border border-surface-3 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder={isJa ? `評価軸 ${idx + 1}` : `维度 ${idx + 1}`}
              />
              <button
                onClick={() => removeDimension(idx)}
                className="px-2 py-2 text-zinc-500 hover:text-red-400 transition-colors"
              >✕</button>
            </div>
          ))}
          <button
            onClick={addDimension}
            className="px-3 py-1.5 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg text-zinc-400 hover:text-zinc-200 transition-colors"
          >{isJa ? "+ 評価軸を追加" : "+ 添加维度"}</button>
        </div>
      </FormField>

      <div className="flex gap-2 pt-2">
        <button onClick={handleSave}
          className="px-4 py-2 bg-brand-600 text-white rounded-lg text-sm hover:bg-brand-700 transition-colors">
          {isCreating ? (isJa ? "作成" : "创建") : (isJa ? "変更を保存" : "保存修改")}
        </button>
        <button onClick={cancelEdit}
          className="px-4 py-2 bg-surface-3 text-zinc-300 rounded-lg text-sm hover:bg-surface-4 transition-colors">
          {isJa ? "キャンセル" : "取消"}
        </button>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">{isJa ? "評価器管理" : "评分器管理"}</h2>
          <p className="text-sm text-zinc-500 mt-1">{isJa ? "Eval 評価で使う評価器を管理します。ここで設定したプロンプトがそのまま LLM に送信されます。" : "管理 Eval 评估使用的评分器。提示词所见即所得：你在这里配的内容就是 LLM 收到的完整提示词。"}</p>
        </div>
        <div className="flex items-center gap-3">
          <ImportExportButtons
            typeName={isJa ? "評価器" : "评分器"}
            onExportAll={handleExportAll}
            onImport={handleImport}
          />
          <button onClick={startCreate}
            className="px-4 py-2 bg-brand-600 text-white rounded-lg text-sm hover:bg-brand-700 transition-colors flex items-center gap-2">
            {isJa ? "+ 新規評価器" : "+ 新建评分器"}
          </button>
        </div>
      </div>

      {isCreating && renderForm()}

      <div className="grid gap-4">
        {graders.map((g) => (
          <div key={g.id}>
            {editingId === g.id ? renderForm() : (
              <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      <h3 className="text-base font-semibold text-zinc-100">{g.name}</h3>
                      <LocaleBadge locale={g.locale} />
                      {g.is_preset && (
                        <span className="text-xs px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
                          {isJa ? "既定" : "预置"}
                        </span>
                      )}
                      <span className={`text-xs px-2 py-0.5 rounded border ${graderTypeLabels[g.grader_type]?.color || "text-zinc-400"}`}>
                        {graderTypeLabels[g.grader_type]?.label || g.grader_type}
                      </span>
                    </div>
                    {g.dimensions.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {g.dimensions.map((d, i) => (
                          <span key={i} className="text-xs px-2 py-0.5 rounded bg-surface-3 text-zinc-400">
                            {d}
                          </span>
                        ))}
                      </div>
                    )}
                    {g.prompt_template && (
                      <>
                        <div className="flex items-center gap-2 mt-2">
                          <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${g.prompt_template.includes("{content}") ? "bg-green-500/15 text-green-400 border border-green-500/30" : "bg-red-500/15 text-red-400 border border-red-500/30"}`}>
                            {g.prompt_template.includes("{content}") ? "✓" : "✗"} {"{content}"}
                          </span>
                          {g.grader_type === "content_and_process" && (
                            <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${g.prompt_template.includes("{process}") ? "bg-green-500/15 text-green-400 border border-green-500/30" : "bg-red-500/15 text-red-400 border border-red-500/30"}`}>
                              {g.prompt_template.includes("{process}") ? "✓" : "✗"} {"{process}"}
                            </span>
                          )}
                          <span className="text-xs text-zinc-600">{isJa ? "← このプロンプトがそのまま LLM に送信されます" : "← 所见即所得：此提示词完整发送给 LLM"}</span>
                        </div>
                        <pre className="mt-2 text-xs text-zinc-500 bg-surface-1 border border-surface-3 rounded-lg p-3 max-h-24 overflow-auto whitespace-pre-wrap font-mono">
                          {g.prompt_template.slice(0, 200)}{g.prompt_template.length > 200 ? "..." : ""}
                        </pre>
                      </>
                    )}
                  </div>
                  <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                    <SingleExportButton onExport={() => handleExportSingle(g.id)} title={isJa ? "この評価器をエクスポート" : "导出此评分器"} />
                    <button onClick={() => startEdit(g)}
                      className="px-3 py-1.5 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg text-zinc-400 hover:text-zinc-200 transition-colors">
                      {isJa ? "編集" : "编辑"}
                    </button>
                    {!g.is_preset && (
                      <button onClick={() => handleDelete(g.id)}
                        className="px-3 py-1.5 text-sm bg-surface-3 hover:bg-red-500/20 rounded-lg text-zinc-400 hover:text-red-400 transition-colors">
                        {isJa ? "削除" : "删除"}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
        {graders.length === 0 && !isCreating && (
          <div className="text-center py-12 text-zinc-500">
            {isJa ? "評価器はまだありません。「新規評価器」をクリックして開始してください" : "暂无评分器，点击「新建评分器」开始"}
          </div>
        )}
      </div>
    </div>
  );
}
