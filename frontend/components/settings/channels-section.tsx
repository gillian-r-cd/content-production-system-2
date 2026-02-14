// frontend/components/settings/channels-section.tsx
// 功能: 渠道管理

"use client";

import { useState } from "react";
import { settingsAPI } from "@/lib/api";
import { FormField, KeyValueEditor } from "./shared";

export function ChannelsSection({ channels, onRefresh }: { channels: any[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<any>({});
  const [isCreating, setIsCreating] = useState(false);

  const PLATFORM_OPTIONS = [
    { value: "social", label: "社交媒体", desc: "小红书、微博、抖音等" },
    { value: "article", label: "长文平台", desc: "公众号、知乎、博客等" },
    { value: "doc", label: "文档", desc: "PPT、PDF、手册等" },
    { value: "web", label: "网页", desc: "落地页、官网等" },
    { value: "email", label: "邮件", desc: "EDM、通讯等" },
    { value: "other", label: "其他", desc: "" },
  ];

  const handleCreate = () => {
    setIsCreating(true);
    setEditForm({ name: "", description: "", platform: "social", prompt_template: "", constraints: {} });
  };

  const handleEdit = (channel: any) => {
    setEditingId(channel.id);
    setEditForm({ ...channel });
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
    } catch (err) {
      alert("保存失败");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此渠道？")) return;
    try {
      await settingsAPI.deleteChannel(id);
      onRefresh();
    } catch (err) {
      alert("删除失败");
    }
  };

  const renderForm = () => (
    <div className="p-5 bg-surface-2 border border-brand-500/50 rounded-xl mb-4">
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <FormField label="渠道名称">
            <input
              type="text"
              value={editForm.name || ""}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              placeholder="如：小红书、销售PPT"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
          <FormField label="描述">
            <input
              type="text"
              value={editForm.description || ""}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              placeholder="渠道用途说明"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
        </div>

        <FormField label="平台类型">
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

        <FormField label="内容生成提示词" hint="指导 AI 如何为这个渠道生成内容">
          <textarea
            value={editForm.prompt_template || ""}
            onChange={(e) => setEditForm({ ...editForm, prompt_template: e.target.value })}
            placeholder="请将以下内容改编为适合小红书的格式，要求：&#10;1. 标题吸引人&#10;2. 使用合适的表情符号&#10;3. 控制在 500 字以内..."
            rows={5}
            className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
          />
        </FormField>

        <FormField label="内容约束" hint="定义这个渠道的内容限制，如字数、格式等">
          <KeyValueEditor
            value={editForm.constraints || {}}
            onChange={(v) => setEditForm({ ...editForm, constraints: v })}
            keyPlaceholder="约束名，如：max_length"
            valuePlaceholder="约束值，如：500"
          />
        </FormField>

        <div className="flex gap-2 pt-2">
          <button onClick={handleSave} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">保存</button>
          <button onClick={() => { setEditingId(null); setIsCreating(false); }} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">取消</button>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">渠道管理</h2>
          <p className="text-sm text-zinc-500 mt-1">定义内容要发布的平台渠道，外延生产时使用</p>
        </div>
        <button onClick={handleCreate} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">+ 新建渠道</button>
      </div>

      {isCreating && renderForm()}

      <div className="grid gap-4 md:grid-cols-2">
        {channels.map((channel) => (
          <div key={channel.id}>
            {editingId === channel.id ? renderForm() : (
              <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl h-full">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-medium text-zinc-200">{channel.name}</h3>
                    <p className="text-sm text-zinc-500 mt-1">{channel.description}</p>
                    <span className="inline-block mt-2 text-xs bg-surface-3 px-2 py-1 rounded-full text-zinc-400">
                      {PLATFORM_OPTIONS.find(p => p.value === channel.platform)?.label || channel.platform}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => handleEdit(channel)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">编辑</button>
                    <button onClick={() => handleDelete(channel.id)} className="px-3 py-1 text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg">删除</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
