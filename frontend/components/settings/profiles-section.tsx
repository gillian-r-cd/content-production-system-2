// frontend/components/settings/profiles-section.tsx
// 功能: 创作者特质管理

"use client";

import { useState } from "react";
import { settingsAPI } from "@/lib/api";
import type { CreatorProfile } from "@/lib/api";
import { FormField, ImportExportButtons, SingleExportButton, downloadJSON } from "./shared";

interface ProfileEditForm {
  name: string;
  description: string;
  traits: Record<string, string>;
}

export function ProfilesSection({ profiles, onRefresh }: { profiles: CreatorProfile[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<ProfileEditForm>({ name: "", description: "", traits: {} });
  const [isCreating, setIsCreating] = useState(false);

  // 预定义的特质类型
  const TRAIT_SUGGESTIONS = [
    { key: "tone", label: "语调风格", placeholder: "如：专业但亲和、轻松幽默" },
    { key: "vocabulary", label: "词汇偏好", placeholder: "如：行业术语丰富、通俗易懂" },
    { key: "personality", label: "人格特点", placeholder: "如：理性、感性、务实" },
    { key: "taboos", label: "禁忌内容", placeholder: "如：过度营销、夸大其词" },
  ];

  const handleExportAll = async () => {
    try {
      const result = await settingsAPI.exportCreatorProfiles();
      downloadJSON(result, `creator_profiles_${new Date().toISOString().split("T")[0]}.json`);
    } catch {
      alert("导出失败");
    }
  };

  const handleExportSingle = async (id: string) => {
    try {
      const result = await settingsAPI.exportCreatorProfiles(id);
      const profile = profiles.find(p => p.id === id);
      downloadJSON(result, `creator_profile_${profile?.name || id}.json`);
    } catch {
      alert("导出失败");
    }
  };

  const handleImport = async (data: unknown[]) => {
    await settingsAPI.importCreatorProfiles(data);
    onRefresh();
  };

  const handleCreate = () => {
    setIsCreating(true);
    setEditForm({ name: "", description: "", traits: {} });
  };

  const handleEdit = (profile: CreatorProfile) => {
    setEditingId(profile.id);
    setEditForm({
      name: profile.name || "",
      description: profile.description || "",
      traits: (profile.traits || {}) as Record<string, string>,
    });
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await settingsAPI.createCreatorProfile(editForm);
      } else {
        await settingsAPI.updateCreatorProfile(editingId!, editForm);
      }
      setEditingId(null);
      setIsCreating(false);
      onRefresh();
    } catch (err) {
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此创作者特质？")) return;
    try {
      await settingsAPI.deleteCreatorProfile(id);
      onRefresh();
    } catch {
      alert("删除失败");
    }
  };

  const updateTrait = (key: string, value: string) => {
    setEditForm({
      ...editForm,
      traits: { ...editForm.traits, [key]: value },
    });
  };

  const renderForm = () => (
    <div className="p-5 bg-surface-2 border border-brand-500/50 rounded-xl mb-4">
      <div className="space-y-5">
        <FormField label="特质名称" hint="给这个创作者特质起一个容易识别的名字">
          <input
            type="text"
            value={editForm.name || ""}
            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
            placeholder="如：专业严谨型、亲和幽默型"
            className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
          />
        </FormField>
        
        <FormField label="适用场景" hint="简单描述这个特质适合什么类型的内容">
          <input
            type="text"
            value={editForm.description || ""}
            onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
            placeholder="如：适合 B2B、技术类、专业培训内容"
            className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
          />
        </FormField>

        <div className="border-t border-surface-3 pt-4">
          <h4 className="text-sm font-medium text-zinc-300 mb-4">特质详情</h4>
          <div className="space-y-4">
            {TRAIT_SUGGESTIONS.map((trait) => (
              <FormField key={trait.key} label={trait.label}>
                <input
                  type="text"
                  value={editForm.traits?.[trait.key] || ""}
                  onChange={(e) => updateTrait(trait.key, e.target.value)}
                  placeholder={trait.placeholder}
                  className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
                />
              </FormField>
            ))}
          </div>
        </div>

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
          <h2 className="text-xl font-semibold text-zinc-100">创作者特质</h2>
          <p className="text-sm text-zinc-500 mt-1">定义不同的创作风格，创建项目时可以选择</p>
        </div>
        <div className="flex items-center gap-3">
          <ImportExportButtons
            typeName="创作者特质"
            onExportAll={handleExportAll}
            onImport={handleImport}
          />
          <button onClick={handleCreate} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">
            + 新建特质
          </button>
        </div>
      </div>

      {isCreating && renderForm()}

      <div className="grid gap-4">
        {profiles.map((profile) => (
          <div key={profile.id}>
            {editingId === profile.id ? renderForm() : (
              <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <h3 className="font-medium text-zinc-200 text-lg">{profile.name}</h3>
                    <p className="text-sm text-zinc-500 mt-1">{profile.description}</p>
                    {profile.traits && Object.keys(profile.traits).length > 0 && (
                      <div className="mt-4 grid grid-cols-2 gap-3">
                        {Object.entries(profile.traits).map(([key, value]) => (
                          <div key={key} className="text-sm">
                            <span className="text-zinc-500">{key}：</span>
                            <span className="text-zinc-300">{String(value)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <SingleExportButton onExport={() => handleExportSingle(profile.id)} title="导出此特质" />
                    <button onClick={() => handleEdit(profile)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">编辑</button>
                    <button onClick={() => handleDelete(profile.id)} className="px-3 py-1 text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg">删除</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
        {profiles.length === 0 && !isCreating && (
          <div className="text-center py-12 text-zinc-500">
            还没有创作者特质，点击上方「新建特质」创建一个
          </div>
        )}
      </div>
    </div>
  );
}
