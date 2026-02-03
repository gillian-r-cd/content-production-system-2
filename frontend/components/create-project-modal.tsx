// frontend/components/create-project-modal.tsx
// 功能: 创建项目对话框，包含创作者特质选择和DeepResearch开关

"use client";

import { useState, useEffect } from "react";
import { settingsAPI, projectAPI } from "@/lib/api";
import type { CreatorProfile, Project } from "@/lib/api";

interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (project: Project) => void;
}

export function CreateProjectModal({
  isOpen,
  onClose,
  onCreated,
}: CreateProjectModalProps) {
  const [name, setName] = useState("");
  const [creatorProfileId, setCreatorProfileId] = useState<string>("");
  const [useDeepResearch, setUseDeepResearch] = useState(true);
  const [creatorProfiles, setCreatorProfiles] = useState<CreatorProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 加载创作者特质列表
  useEffect(() => {
    if (isOpen) {
      loadCreatorProfiles();
    }
  }, [isOpen]);

  const loadCreatorProfiles = async () => {
    try {
      const profiles = await settingsAPI.listCreatorProfiles();
      setCreatorProfiles(profiles);
      // 如果有默认的，自动选中第一个
      if (profiles.length > 0 && !creatorProfileId) {
        setCreatorProfileId(profiles[0].id);
      }
    } catch (err) {
      console.error("加载创作者特质失败:", err);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!name.trim()) {
      setError("请输入项目名称");
      return;
    }
    
    if (!creatorProfileId) {
      setError("请选择创作者特质");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const project = await projectAPI.create({
        name: name.trim(),
        creator_profile_id: creatorProfileId,
        use_deep_research: useDeepResearch,
      });
      onCreated(project);
      // 重置表单
      setName("");
      setCreatorProfileId(creatorProfiles[0]?.id || "");
      setUseDeepResearch(true);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* 背景遮罩 */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* 对话框 */}
      <div className="relative w-full max-w-md bg-surface-1 border border-surface-3 rounded-xl shadow-2xl">
        <div className="p-6">
          <h2 className="text-xl font-semibold text-zinc-100 mb-6">
            新建内容项目
          </h2>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* 项目名称 */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                项目名称 <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如：产品发布内容策划"
                className="w-full px-4 py-2.5 bg-surface-2 border border-surface-3 rounded-lg text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                autoFocus
              />
            </div>

            {/* 创作者特质 */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                创作者特质 <span className="text-red-400">*</span>
              </label>
              {creatorProfiles.length === 0 ? (
                <div className="p-4 bg-amber-900/20 border border-amber-700/50 rounded-lg">
                  <p className="text-sm text-amber-200">
                    还没有创作者特质，请先在{" "}
                    <a
                      href="/settings"
                      className="underline hover:text-amber-100"
                    >
                      后台设置
                    </a>{" "}
                    中创建。
                  </p>
                </div>
              ) : (
                <select
                  value={creatorProfileId}
                  onChange={(e) => setCreatorProfileId(e.target.value)}
                  className="w-full px-4 py-2.5 bg-surface-2 border border-surface-3 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  <option value="">请选择...</option>
                  {creatorProfiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.name}
                    </option>
                  ))}
                </select>
              )}
              {creatorProfileId && (
                <p className="mt-2 text-xs text-zinc-500">
                  创作者特质将作为所有内容生成的全局上下文
                </p>
              )}
            </div>

            {/* DeepResearch 开关 */}
            <div className="flex items-center justify-between p-4 bg-surface-2 rounded-lg">
              <div>
                <p className="text-sm font-medium text-zinc-200">
                  启用 DeepResearch
                </p>
                <p className="text-xs text-zinc-500 mt-1">
                  消费者调研阶段将使用网络搜索获取更深入的用户洞察
                </p>
              </div>
              <button
                type="button"
                onClick={() => setUseDeepResearch(!useDeepResearch)}
                className={`relative w-12 h-6 rounded-full transition-colors ${
                  useDeepResearch ? "bg-brand-600" : "bg-zinc-600"
                }`}
              >
                <span
                  className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                    useDeepResearch ? "left-7" : "left-1"
                  }`}
                />
              </button>
            </div>

            {/* 错误提示 */}
            {error && (
              <div className="p-3 bg-red-900/20 border border-red-700/50 rounded-lg">
                <p className="text-sm text-red-300">{error}</p>
              </div>
            )}

            {/* 按钮 */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={loading || !name.trim() || !creatorProfileId}
                className="px-5 py-2 text-sm bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
              >
                {loading ? "创建中..." : "创建项目"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

