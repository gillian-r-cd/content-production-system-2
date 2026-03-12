// frontend/components/settings/simulators-section.tsx
// 功能: 模拟器管理

"use client";

import { useState } from "react";
import { settingsAPI } from "@/lib/api";
import { FormField, TagInput, ImportExportButtons, SingleExportButton, downloadJSON, LOCALE_OPTIONS, LocaleBadge, useSettingsUiIsJa, useSettingsUiLocale } from "./shared";

interface SimulatorItem {
  id: string;
  name: string;
  locale?: string;
  description?: string;
  interaction_type: string;
  prompt_template?: string;
  secondary_prompt?: string;
  grader_template?: string;
  evaluation_dimensions?: string[];
  max_turns?: number;
}

interface SimulatorEditForm {
  name: string;
  locale: string;
  description: string;
  interaction_type: string;
  prompt_template: string;
  secondary_prompt: string;
  grader_template: string;
  evaluation_dimensions: string[];
  max_turns: number;
}

export function SimulatorsSection({ simulators, onRefresh }: { simulators: SimulatorItem[]; onRefresh: () => void }) {
  const uiLocale = useSettingsUiLocale();
  const isJa = useSettingsUiIsJa();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<SimulatorEditForm>({
    name: "",
    locale: uiLocale,
    description: "",
    interaction_type: "reading",
    prompt_template: "",
    secondary_prompt: "",
    grader_template: "",
    evaluation_dimensions: [],
    max_turns: 10,
  });
  const [isCreating, setIsCreating] = useState(false);

  const INTERACTION_TYPES = [
    { value: "dialogue", label: isJa ? "対話型" : "对话式", desc: isJa ? "複数ターンの会話を模擬。Chatbot やカスタマーサポート向け" : "模拟多轮对话，适合 Chatbot、客服场景", icon: "💬" },
    { value: "reading", label: isJa ? "閲読型" : "阅读式", desc: isJa ? "全文読後のフィードバック向け。記事や講座に適する" : "阅读全文后给反馈，适合文章、课程", icon: "📖" },
    { value: "decision", label: isJa ? "意思決定型" : "决策式", desc: isJa ? "購買判断を模擬。販売ページや LP 向け" : "模拟购买决策，适合销售页、落地页", icon: "🤔" },
    { value: "exploration", label: isJa ? "探索型" : "探索式", desc: isJa ? "目的を持った探索向け。ヘルプ文書などに適する" : "带目的地探索，适合帮助文档", icon: "🔍" },
  ];

  const handleExportAll = async () => {
    try {
      const result = await settingsAPI.exportSimulators();
      downloadJSON(result, `simulators_${new Date().toISOString().split("T")[0]}.json`);
    } catch {
      alert(isJa ? "エクスポートに失敗しました" : "导出失败");
    }
  };

  const handleExportSingle = async (id: string) => {
    try {
      const result = await settingsAPI.exportSimulators(id);
      const simulator = simulators.find(s => s.id === id);
      downloadJSON(result, `simulator_${simulator?.name || id}.json`);
    } catch {
      alert(isJa ? "エクスポートに失敗しました" : "导出失败");
    }
  };

  const handleImport = async (data: unknown[]) => {
    await settingsAPI.importSimulators(data);
    onRefresh();
  };

  const handleCreate = () => {
    setIsCreating(true);
    setEditForm({ name: "", locale: uiLocale, description: "", interaction_type: "reading", prompt_template: "", secondary_prompt: "", grader_template: "", evaluation_dimensions: [], max_turns: 10 });
  };

  const handleEdit = (simulator: SimulatorItem) => {
    setEditingId(simulator.id);
    setEditForm({
      name: simulator.name || "",
      locale: simulator.locale || uiLocale,
      description: simulator.description || "",
      interaction_type: simulator.interaction_type || "reading",
      prompt_template: simulator.prompt_template || "",
      secondary_prompt: simulator.secondary_prompt || "",
      grader_template: simulator.grader_template || "",
      evaluation_dimensions: simulator.evaluation_dimensions || [],
      max_turns: simulator.max_turns || 10,
    });
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await settingsAPI.createSimulator(editForm);
      } else {
        await settingsAPI.updateSimulator(editingId!, editForm);
      }
      setEditingId(null);
      setIsCreating(false);
      onRefresh();
    } catch {
      alert(isJa ? "保存に失敗しました" : "保存失败");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(isJa ? "このシミュレーターを削除しますか？" : "确定删除此模拟器？")) return;
    try {
      await settingsAPI.deleteSimulator(id);
      onRefresh();
    } catch {
      alert(isJa ? "削除に失敗しました" : "删除失败");
    }
  };

  const renderForm = () => (
    <div className="p-5 bg-surface-2 border border-brand-500/50 rounded-xl mb-4">
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <FormField label={isJa ? "シミュレーター名" : "模拟器名称"}>
            <input
              type="text"
              value={editForm.name || ""}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              placeholder={isJa ? "例: 講座学習シミュレーター" : "如：课程学习模拟器"}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
          <FormField label={isJa ? "言語" : "语言"}>
            <select
              value={editForm.locale}
              onChange={(e) => setEditForm({ ...editForm, locale: e.target.value })}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            >
              {LOCALE_OPTIONS.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </FormField>
          <FormField label={isJa ? "説明" : "描述"}>
            <input
              type="text"
              value={editForm.description || ""}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              placeholder={isJa ? "シミュレーターの用途説明" : "模拟器用途说明"}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
        </div>

        <FormField label={isJa ? "インタラクション種別" : "交互类型"}>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            {INTERACTION_TYPES.map((type) => (
              <label
                key={type.value}
                className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                  editForm.interaction_type === type.value
                    ? "border-brand-500 bg-brand-600/10"
                    : "border-surface-3 hover:border-surface-4"
                }`}
              >
                <input
                  type="radio"
                  value={type.value}
                  checked={editForm.interaction_type === type.value}
                  onChange={(e) => setEditForm({ ...editForm, interaction_type: e.target.value })}
                  className="sr-only"
                />
                <div className="flex items-center gap-2">
                  <span>{type.icon}</span>
                  <span className="text-sm text-zinc-200">{type.label}</span>
                </div>
                <div className="text-xs text-zinc-500 mt-1">{type.desc}</div>
              </label>
            ))}
          </div>
        </FormField>

        {editForm.interaction_type === "dialogue" && (
          <FormField label={isJa ? "最大対話ターン数" : "最大对话轮数"}>
            <input
              type="number"
              value={editForm.max_turns || 10}
              onChange={(e) => setEditForm({ ...editForm, max_turns: parseInt(e.target.value) })}
              min={1}
              max={20}
              className="w-32 px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
        )}

        <FormField label={isJa ? "評価軸" : "评估维度"} hint={isJa ? "ユーザー体験後に採点する評価軸を定義します" : "定义用户体验后需要评分的维度"}>
          <TagInput
            value={editForm.evaluation_dimensions || []}
            onChange={(v) => setEditForm({ ...editForm, evaluation_dimensions: v })}
            placeholder={isJa ? "評価軸を入力して Enter。例: 理解しやすさ、価値認知、行動意欲" : "输入维度名后按回车，如：理解难度、价值感知、行动意愿"}
          />
        </FormField>

        <FormField
          label={editForm.interaction_type === "decision" ? (isJa ? "販売側プロンプト（完全版）" : "销售方提示词（完整版）") : (isJa ? "メインプロンプト（完全版）" : "主提示词（完整版）")}
          hint={isJa ? "このプロンプトはそのまま LLM に送信されます。プレースホルダー: {persona} = 顧客ペルソナ, {content} = 評価対象内容" : "此提示词将完整发送给 LLM。占位符：{persona} = 消费者画像, {content} = 被评内容"}
        >
          <textarea
            value={editForm.prompt_template || ""}
            onChange={(e) => setEditForm({ ...editForm, prompt_template: e.target.value })}
            placeholder={editForm.interaction_type === "decision"
              ? (isJa ? "あなたはこの内容の販売担当です...{content}...{persona}..." : "你是这个内容的销售顾问...{content}...{persona}...")
              : editForm.interaction_type === "dialogue" || editForm.interaction_type === "exploration"
                ? (isJa ? "あなたは実在するユーザーを演じています...{persona}..." : "你正在扮演一位真实用户...{persona}...")
                : (isJa ? "あなたは熟練したコンテンツレビュアーです...{content}..." : "你是一位资深的内容审阅者...{content}...")}
            rows={8}
            className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm font-mono"
          />
        </FormField>

        {/* 对话类模拟器需要第二方提示词 */}
        {(editForm.interaction_type === "dialogue" || editForm.interaction_type === "decision" || editForm.interaction_type === "exploration") && (
          <FormField
            label={editForm.interaction_type === "decision" ? (isJa ? "顧客応答プロンプト" : "消费者回应提示词") : (isJa ? "内容代表 / 第二者プロンプト" : "内容代表/第二方提示词")}
            hint={isJa ? "対話モードで相手側が使う完全版プロンプトです。{content} と {persona} を利用できます" : "对话模式中另一方的完整提示词，支持 {content} 和 {persona}"}
          >
            <textarea
              value={editForm.secondary_prompt || ""}
              onChange={(e) => setEditForm({ ...editForm, secondary_prompt: e.target.value })}
              placeholder={editForm.interaction_type === "decision"
                ? (isJa ? "あなたは実在する見込み顧客です...{persona}..." : "你是一位真实的潜在用户...{persona}...")
                : (isJa ? "あなたは内容の代表者として、以下の内容に厳密に基づいて回答します...{content}..." : "你是内容的代表，严格基于以下内容回答问题...{content}...")}
              rows={6}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm font-mono"
            />
          </FormField>
        )}

        <FormField label={isJa ? "評価プロンプトテンプレート" : "评分提示词模板"} hint={isJa ? "評価や採点に使うプロンプトです。{process} = 対話記録, {content} = 評価対象内容" : "评估/评分时使用的提示词，支持 {process} = 对话记录, {content} = 被评内容"}>
          <textarea
            value={editForm.grader_template || ""}
            onChange={(e) => setEditForm({ ...editForm, grader_template: e.target.value })}
            placeholder={isJa ? "あなたは評価の専門家です...{process}...{content}..." : "你是一位评估专家...{process}...{content}..."}
            rows={6}
            className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm font-mono"
          />
        </FormField>

        <div className="flex gap-2 pt-2">
          <button onClick={handleSave} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">{isJa ? "保存" : "保存"}</button>
          <button onClick={() => { setEditingId(null); setIsCreating(false); }} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">{isJa ? "キャンセル" : "取消"}</button>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">{isJa ? "シミュレーター管理" : "模拟器管理"}</h2>
          <p className="text-sm text-zinc-500 mt-1">{isJa ? "顧客体験シミュレーションの種類と評価軸を設定します" : "配置消费者体验模拟的类型和评估维度"}</p>
        </div>
        <div className="flex items-center gap-3">
          <ImportExportButtons
            typeName={isJa ? "シミュレーター" : "模拟器"}
            onExportAll={handleExportAll}
            onImport={handleImport}
          />
          <button onClick={handleCreate} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">{isJa ? "+ 新規シミュレーター" : "+ 新建模拟器"}</button>
        </div>
      </div>

      {isCreating && renderForm()}

      <div className="grid gap-4">
        {simulators.map((simulator) => {
          const evaluationDimensions = simulator.evaluation_dimensions ?? [];
          return (
          <div key={simulator.id}>
            {editingId === simulator.id ? renderForm() : (
              <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span>{INTERACTION_TYPES.find(t => t.value === simulator.interaction_type)?.icon || "🎭"}</span>
                      <h3 className="font-medium text-zinc-200">{simulator.name}</h3>
                      <LocaleBadge locale={simulator.locale} />
                      <span className="text-xs bg-surface-3 px-2 py-1 rounded-full text-zinc-400">
                        {INTERACTION_TYPES.find(t => t.value === simulator.interaction_type)?.label || simulator.interaction_type}
                      </span>
                    </div>
                    <p className="text-sm text-zinc-500 mt-1">{simulator.description}</p>
                    {evaluationDimensions.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {evaluationDimensions.map((dim: string, i: number) => (
                          <span key={i} className="text-xs bg-brand-600/10 text-brand-400 px-2 py-1 rounded">
                            {dim}
                          </span>
                        ))}
                      </div>
                    )}
                    {/* 提示词预览 */}
                    <div className="mt-3 space-y-2">
                      {simulator.prompt_template && (
                        <div>
                          <span className="text-xs text-zinc-500 font-medium">{isJa ? "メインプロンプト:" : "主提示词："}</span>
                          <pre className="text-xs text-zinc-500 bg-surface-1 border border-surface-3 rounded-lg p-2 mt-1 max-h-20 overflow-auto whitespace-pre-wrap font-mono">
                            {simulator.prompt_template.slice(0, 200)}{simulator.prompt_template.length > 200 ? "..." : ""}
                          </pre>
                        </div>
                      )}
                      {simulator.secondary_prompt && (
                        <div>
                          <span className="text-xs text-zinc-500 font-medium">{isJa ? "第2プロンプト:" : "第二方提示词："}</span>
                          <pre className="text-xs text-zinc-500 bg-surface-1 border border-surface-3 rounded-lg p-2 mt-1 max-h-20 overflow-auto whitespace-pre-wrap font-mono">
                            {simulator.secondary_prompt.slice(0, 200)}{simulator.secondary_prompt.length > 200 ? "..." : ""}
                          </pre>
                        </div>
                      )}
                      {simulator.grader_template && (
                        <div>
                          <span className="text-xs text-zinc-500 font-medium">{isJa ? "評価プロンプト:" : "评分提示词："}</span>
                          <pre className="text-xs text-zinc-500 bg-surface-1 border border-surface-3 rounded-lg p-2 mt-1 max-h-20 overflow-auto whitespace-pre-wrap font-mono">
                            {simulator.grader_template.slice(0, 200)}{simulator.grader_template.length > 200 ? "..." : ""}
                          </pre>
                        </div>
                      )}
                      {!simulator.prompt_template && !simulator.secondary_prompt && !simulator.grader_template && (
                        <span className="text-xs text-zinc-600 italic">{isJa ? "プロンプト未設定" : "未配置提示词"}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                    <SingleExportButton onExport={() => handleExportSingle(simulator.id)} title={isJa ? "このシミュレーターをエクスポート" : "导出此模拟器"} />
                    <button onClick={() => handleEdit(simulator)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">{isJa ? "編集" : "编辑"}</button>
                    <button onClick={() => handleDelete(simulator.id)} className="px-3 py-1 text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg">{isJa ? "削除" : "删除"}</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )})}
        {simulators.length === 0 && !isCreating && (
          <div className="text-center py-12 text-zinc-500">
            {isJa ? "シミュレーターはまだありません。上の「新規シミュレーター」をクリックして作成してください" : "还没有模拟器，点击上方「新建模拟器」创建一个"}
          </div>
        )}
      </div>
    </div>
  );
}
