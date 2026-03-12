// frontend/components/settings/model-settings-section.tsx
// 功能: 模型配置 — 全局默认 LLM 模型选择
// M5: 用户在此选择全局默认的主模型和轻量模型

"use client";

import { useState, useEffect, useCallback } from "react";
import { modelsAPI, settingsAPI } from "@/lib/api";
import type { ModelInfo, AgentSettingsData } from "@/lib/api";
import { useSettingsUiIsJa } from "./shared";

interface ModelSettingsSectionProps {
  settings: AgentSettingsData | null;
  onRefresh: () => void;
}

export function ModelSettingsSection({ settings, onRefresh }: ModelSettingsSectionProps) {
  const isJa = useSettingsUiIsJa();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [envProvider, setEnvProvider] = useState<string>("openai");
  const [envDefault, setEnvDefault] = useState<{ main: string; mini: string }>({ main: "", mini: "" });

  const [defaultModel, setDefaultModel] = useState<string>(settings?.default_model || "");
  const [defaultMiniModel, setDefaultMiniModel] = useState<string>(settings?.default_mini_model || "");
  const [isSaving, setIsSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // 加载可用模型列表
  const loadModels = useCallback(async () => {
    try {
      const resp = await modelsAPI.list();
      setModels(resp.models);
      setEnvProvider(resp.env_provider);
      setEnvDefault(resp.current_default);
      setLoadError(null);
    } catch (err) {
      console.error("加载模型列表失败:", err);
      setLoadError(isJa ? "利用可能なモデル一覧を読み込めません。バックエンドが起動しているか確認してください" : "无法加载可用模型列表，请检查后端是否运行");
    }
  }, [isJa]);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  useEffect(() => {
    if (settings) {
      setDefaultModel(settings.default_model || "");
      setDefaultMiniModel(settings.default_mini_model || "");
    }
  }, [settings]);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await settingsAPI.updateAgentSettings({
        default_model: defaultModel || null,
        default_mini_model: defaultMiniModel || null,
      });
      onRefresh();
      alert(isJa ? "モデル設定を保存しました" : "模型配置已保存");
    } catch (err) {
      console.error("保存失败:", err);
      alert((isJa ? "保存に失敗しました: " : "保存失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
    } finally {
      setIsSaving(false);
    }
  };

  // 按 tier 分组
  const mainModels = models.filter(m => m.tier === "main");
  const miniModels = models.filter(m => m.tier === "mini");

  // 当前生效的模型（考虑覆盖链）
  const effectiveMain = defaultModel || envDefault.main;
  const effectiveMini = defaultMiniModel || envDefault.mini;

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">{isJa ? "モデル設定" : "模型配置"}</h2>
          <p className="text-sm text-zinc-500 mt-1">
            {isJa ? "グローバル既定の LLM モデルを選択します。内容ブロックごとに上書きも可能です。" : "选择全局默认的 LLM 模型。内容块可单独覆盖此设置。"}
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg disabled:opacity-50 text-white"
        >
          {isSaving ? (isJa ? "保存中..." : "保存中...") : (isJa ? "設定を保存" : "保存配置")}
        </button>
      </div>

      {loadError && (
        <div className="mb-4 p-3 bg-red-900/20 border border-red-500/30 rounded-lg text-sm text-red-400">
          {loadError}
        </div>
      )}

      <div className="space-y-6">
        {/* 当前环境信息 */}
        <div className="p-4 bg-surface-2 border border-surface-3 rounded-xl">
          <h3 className="font-medium text-zinc-200 mb-3 flex items-center gap-2">
            <span>🔧</span> {isJa ? "環境設定" : "环境配置"}
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-zinc-500">{isJa ? "現在の Provider:" : "当前 Provider："}</span>
              <span className="text-zinc-200 ml-1">{envProvider.toUpperCase()}</span>
            </div>
            <div>
              <span className="text-zinc-500">{isJa ? "利用可能な Provider:" : "可用 Provider："}</span>
              <span className="text-zinc-200 ml-1">
                {[...new Set(models.map(m => m.provider))].map(p => p.toUpperCase()).join(", ") || (isJa ? "なし" : "无")}
              </span>
            </div>
            <div>
              <span className="text-zinc-500">{isJa ? ".env 既定のメインモデル:" : ".env 默认主模型："}</span>
              <span className="text-zinc-300 ml-1 font-mono text-xs">{envDefault.main}</span>
            </div>
            <div>
              <span className="text-zinc-500">{isJa ? ".env 既定の軽量モデル:" : ".env 默认轻量模型："}</span>
              <span className="text-zinc-300 ml-1 font-mono text-xs">{envDefault.mini}</span>
            </div>
          </div>
        </div>

        {/* 全局默认主模型 */}
        <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
          <h3 className="font-medium text-zinc-200 mb-2 flex items-center gap-2">
            <span>🧠</span> {isJa ? "既定のメインモデル" : "默认主模型"}
          </h3>
          <p className="text-sm text-zinc-500 mb-4">
            {isJa ? "内容生成や Agent 対話など主要タスクに使われます。空欄の場合は .env の既定値を使います。" : "用于内容生成、Agent 对话等主要任务。留空则使用 .env 中的默认值。"}
          </p>
          <select
            value={defaultModel}
            onChange={e => setDefaultModel(e.target.value)}
            className="w-full px-3 py-2.5 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 appearance-none cursor-pointer"
          >
            <option value="">{isJa ? `.env 既定値を使用 (${envDefault.main})` : `使用 .env 默认 (${envDefault.main})`}</option>
            {mainModels.map(m => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.provider.toUpperCase()}) — {m.id}
              </option>
            ))}
            {/* Also show mini models as an option for main (user might want a cheaper model) */}
            {miniModels.map(m => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.provider.toUpperCase()}) — {m.id} {isJa ? "[軽量]" : "[轻量]"}
              </option>
            ))}
          </select>
          <div className="mt-2 text-xs text-zinc-500">
            {isJa ? "現在有効:" : "当前生效："}<span className="text-brand-400 font-mono">{effectiveMain}</span>
          </div>
        </div>

        {/* 全局默认轻量模型 */}
        <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
          <h3 className="font-medium text-zinc-200 mb-2 flex items-center gap-2">
            <span>⚡</span> {isJa ? "既定の軽量モデル" : "默认轻量模型"}
          </h3>
          <p className="text-sm text-zinc-500 mb-4">
            {isJa ? "プロンプト生成やインライン編集など高速タスクに使われます。空欄の場合は .env の既定値を使います。" : "用于快速任务（如提示词生成、内联编辑等）。留空则使用 .env 中的默认值。"}
          </p>
          <select
            value={defaultMiniModel}
            onChange={e => setDefaultMiniModel(e.target.value)}
            className="w-full px-3 py-2.5 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 appearance-none cursor-pointer"
          >
            <option value="">{isJa ? `.env 既定値を使用 (${envDefault.mini})` : `使用 .env 默认 (${envDefault.mini})`}</option>
            {miniModels.map(m => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.provider.toUpperCase()}) — {m.id}
              </option>
            ))}
            {mainModels.map(m => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.provider.toUpperCase()}) — {m.id} {isJa ? "[主力]" : "[主力]"}
              </option>
            ))}
          </select>
          <div className="mt-2 text-xs text-zinc-500">
            {isJa ? "現在有効:" : "当前生效："}<span className="text-brand-400 font-mono">{effectiveMini}</span>
          </div>
        </div>

        {/* 模型覆盖链说明 */}
        <div className="p-4 bg-surface-2/50 border border-surface-3 rounded-xl">
          <h3 className="font-medium text-zinc-300 mb-2 flex items-center gap-2">
            <span>📋</span> {isJa ? "モデル選択の優先順位" : "模型选择优先级"}
          </h3>
          <div className="text-sm text-zinc-400 space-y-1">
            <p>{isJa ? "1. " : "1. "}<strong className="text-zinc-300">{isJa ? "内容ブロック上書き" : "内容块覆盖"}</strong>{isJa ? " — 内容ブロック編集画面で個別指定したモデル（最優先）" : " — 在内容块编辑器中为单个块指定模型（最高优先）"}</p>
            <p>{isJa ? "2. " : "2. "}<strong className="text-zinc-300">{isJa ? "グローバル既定" : "全局默认"}</strong>{isJa ? " — このページで設定する既定モデル（中優先）" : " — 此页面设置的默认模型（中等优先）"}</p>
            <p>{isJa ? "3. " : "3. "}<strong className="text-zinc-300">.env {isJa ? "設定" : "配置"}</strong>{isJa ? " — 環境変数のモデル設定（最低優先 / フォールバック）" : " — 环境变量中的模型配置（最低优先 / 兜底）"}</p>
          </div>
        </div>

        {/* 可用模型列表 */}
        <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
          <h3 className="font-medium text-zinc-200 mb-3 flex items-center gap-2">
            <span>📦</span> {isJa ? "利用可能なモデル一覧" : "可用模型列表"}
          </h3>
          {models.length === 0 ? (
            <p className="text-sm text-zinc-500">{isJa ? "利用可能なモデルが見つかりません。API Key 設定を確認してください。" : "未检测到可用模型，请检查 API Key 配置。"}</p>
          ) : (
            <div className="grid md:grid-cols-2 gap-3">
              {models.map(m => (
                <div
                  key={m.id}
                  className={`p-3 border rounded-lg ${
                    effectiveMain === m.id || effectiveMini === m.id
                      ? "border-brand-500/50 bg-brand-600/10"
                      : "border-surface-3"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-zinc-200 font-medium text-sm">{m.name}</span>
                    <span className={`px-1.5 py-0.5 text-xs rounded ${
                      m.tier === "main" ? "bg-purple-600/20 text-purple-400" : "bg-emerald-600/20 text-emerald-400"
                    }`}>
                      {m.tier === "main" ? (isJa ? "主力" : "主力") : (isJa ? "軽量" : "轻量")}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-zinc-500">{m.provider.toUpperCase()}</span>
                    <span className="text-xs text-zinc-600 font-mono">{m.id}</span>
                  </div>
                  {(effectiveMain === m.id || effectiveMini === m.id) && (
                    <div className="mt-1 text-xs text-brand-400">
                      {effectiveMain === m.id && (isJa ? "現在のメインモデル" : "当前主模型")}
                      {effectiveMain === m.id && effectiveMini === m.id && " / "}
                      {effectiveMini === m.id && (isJa ? "現在の軽量モデル" : "当前轻量模型")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
