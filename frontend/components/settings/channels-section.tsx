// frontend/components/settings/channels-section.tsx
// 功能: 渠道管理

"use client";

import { useState } from "react";
import { settingsAPI } from "@/lib/api";
import { FormField, LOCALE_OPTIONS, LocaleBadge, useSettingsUiIsJa, useSettingsUiLocale } from "./shared";

interface ChannelItem {
  id: string;
  name: string;
  locale?: string;
  description?: string;
  platform?: string;
  prompt_template?: string;
}

interface ChannelEditForm {
  name: string;
  locale: string;
  description: string;
  platform: string;
  prompt_template: string;
}

export function ChannelsSection({ channels, onRefresh }: { channels: ChannelItem[]; onRefresh: () => void }) {
  const uiLocale = useSettingsUiLocale();
  const isJa = useSettingsUiIsJa();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<ChannelEditForm>({ name: "", locale: uiLocale, description: "", platform: "social", prompt_template: "" });
  const [isCreating, setIsCreating] = useState(false);

  const PLATFORM_OPTIONS = [
    { value: "social", label: isJa ? "SNS" : "社交媒体", desc: isJa ? "X、小红书、TikTok など" : "小红书、微博、抖音等" },
    { value: "article", label: isJa ? "長文プラットフォーム" : "长文平台", desc: isJa ? "公式アカウント、知乎、ブログなど" : "公众号、知乎、博客等" },
    { value: "doc", label: isJa ? "ドキュメント" : "文档", desc: isJa ? "PPT、PDF、マニュアルなど" : "PPT、PDF、手册等" },
    { value: "web", label: isJa ? "Web ページ" : "网页", desc: isJa ? "LP、公式サイトなど" : "落地页、官网等" },
    { value: "email", label: isJa ? "メール" : "邮件", desc: isJa ? "EDM、ニュースレターなど" : "EDM、通讯等" },
    { value: "other", label: isJa ? "その他" : "其他", desc: "" },
  ];

  const handleCreate = () => {
    setIsCreating(true);
    setEditForm({ name: "", locale: uiLocale, description: "", platform: "social", prompt_template: "" });
  };

  const handleEdit = (channel: ChannelItem) => {
    setEditingId(channel.id);
    setEditForm({
      name: channel.name || "",
      locale: channel.locale || uiLocale,
      description: channel.description || "",
      platform: channel.platform || "social",
      prompt_template: channel.prompt_template || "",
    });
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await settingsAPI.createChannel(editForm);
      } else {
        await settingsAPI.updateChannel(editingId!, editForm);
      }
      setEditingId(null);
      setIsCreating(false);
      onRefresh();
    } catch {
      alert(isJa ? "保存に失敗しました" : "保存失败");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(isJa ? "このチャネルを削除しますか？" : "确定删除此渠道？")) return;
    try {
      await settingsAPI.deleteChannel(id);
      onRefresh();
    } catch {
      alert(isJa ? "削除に失敗しました" : "删除失败");
    }
  };

  const renderForm = () => (
    <div className="p-5 bg-surface-2 border border-brand-500/50 rounded-xl mb-4">
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <FormField label={isJa ? "チャネル名" : "渠道名称"}>
            <input
              type="text"
              value={editForm.name || ""}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              placeholder={isJa ? "例：小红书、営業提案資料" : "如：小红书、销售PPT"}
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
              placeholder={isJa ? "チャネル用途の説明" : "渠道用途说明"}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
        </div>

        <FormField label={isJa ? "プラットフォーム種別" : "平台类型"}>
          <div className="grid grid-cols-3 gap-3">
            {PLATFORM_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                  editForm.platform === opt.value
                    ? "border-brand-500 bg-brand-600/10"
                    : "border-surface-3 hover:border-surface-4"
                }`}
              >
                <input
                  type="radio"
                  value={opt.value}
                  checked={editForm.platform === opt.value}
                  onChange={(e) => setEditForm({ ...editForm, platform: e.target.value })}
                  className="sr-only"
                />
                <div className="text-sm text-zinc-200">{opt.label}</div>
                {opt.desc && <div className="text-xs text-zinc-500">{opt.desc}</div>}
              </label>
            ))}
          </div>
        </FormField>

        <FormField label={isJa ? "内容生成プロンプト" : "内容生成提示词"} hint={isJa ? "このチャネル向けに AI がどのように内容生成すべきかを指示します" : "指导 AI 如何为这个渠道生成内容"}>
          <textarea
            value={editForm.prompt_template || ""}
            onChange={(e) => setEditForm({ ...editForm, prompt_template: e.target.value })}
            placeholder={isJa ? "以下の内容を小红书向けに再構成してください。要件:&#10;1. タイトルは目を引くこと&#10;2. 適切な絵文字を使うこと&#10;3. 500字以内に収めること..." : "请将以下内容改编为适合小红书的格式，要求：&#10;1. 标题吸引人&#10;2. 使用合适的表情符号&#10;3. 控制在 500 字以内..."}
            rows={5}
            className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
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
          <h2 className="text-xl font-semibold text-zinc-100">{isJa ? "チャネル管理" : "渠道管理"}</h2>
          <p className="text-sm text-zinc-500 mt-1">{isJa ? "内容を公開する配信チャネルを定義します。外部展開コンテンツ生成時に利用されます" : "定义内容要发布的平台渠道，外延生产时使用"}</p>
        </div>
        <button onClick={handleCreate} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">{isJa ? "+ 新規チャネル" : "+ 新建渠道"}</button>
      </div>

      {isCreating && renderForm()}

      <div className="grid gap-4 md:grid-cols-2">
        {channels.map((channel) => (
          <div key={channel.id}>
            {editingId === channel.id ? renderForm() : (
              <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl h-full">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-zinc-200">{channel.name}</h3>
                      <LocaleBadge locale={channel.locale} />
                    </div>
                    <p className="text-sm text-zinc-500 mt-1">{channel.description}</p>
                    <span className="inline-block mt-2 text-xs bg-surface-3 px-2 py-1 rounded-full text-zinc-400">
                      {PLATFORM_OPTIONS.find(p => p.value === channel.platform)?.label || channel.platform}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => handleEdit(channel)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">{isJa ? "編集" : "编辑"}</button>
                    <button onClick={() => handleDelete(channel.id)} className="px-3 py-1 text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg">{isJa ? "削除" : "删除"}</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
        {channels.length === 0 && !isCreating && (
          <div className="md:col-span-2 text-center py-12 text-zinc-500">
            {isJa ? "チャネルはまだありません。上の「新規チャネル」をクリックして作成してください" : "还没有渠道，点击上方「新建渠道」创建一个"}
          </div>
        )}
      </div>
    </div>
  );
}
