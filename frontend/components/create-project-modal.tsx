// frontend/components/create-project-modal.tsx
// 功能: 创建项目对话框，支持两步流程：基本信息 → 选择模板
// 主要组件: CreateProjectModal
// 集成: TemplateSelector 用于选择流程模板

"use client";

import { useState, useEffect } from "react";
import { settingsAPI, projectAPI, blockAPI, phaseTemplateAPI } from "@/lib/api";
import type { CreatorProfile, Project, PhaseTemplate } from "@/lib/api";

// 统一模板项（同时展示 PhaseTemplate 和 FieldTemplate）
interface TemplateItem {
  id: string;
  name: string;
  description: string;
  source: "phase" | "field"; // 区分来源
  phases: PhaseTemplate["phases"];
  is_default: boolean;
  fieldCount: number;
  contentCount: number; // 有预置内容的字段数
}

interface FieldTemplateLikeField {
  name: string;
  ai_prompt?: string;
  content?: string;
}

interface FieldTemplateLike {
  id: string;
  name: string;
  description?: string;
  category?: string;
  fields?: FieldTemplateLikeField[];
}
import { ChevronLeft, ChevronRight, Check, Folder, Lightbulb, Users, PlayCircle, BarChart3 } from "lucide-react";

interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (project: Project) => void;
}

type Step = "info" | "template";

// 特殊处理器图标
const specialHandlerIcons: Record<string, React.ReactNode> = {
  intent: <Lightbulb className="w-4 h-4 text-amber-400" />,
  research: <Users className="w-4 h-4 text-blue-400" />,
  simulate: <PlayCircle className="w-4 h-4 text-purple-400" />,
  evaluate: <BarChart3 className="w-4 h-4 text-emerald-400" />,
};

export function CreateProjectModal({
  isOpen,
  onClose,
  onCreated,
}: CreateProjectModalProps) {
  // Escape 键关闭
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);
  
  // 步骤状态
  const [step, setStep] = useState<Step>("info");
  
  // 基本信息
  const [name, setName] = useState("");
  const [creatorProfileId, setCreatorProfileId] = useState<string>("");
  const [useDeepResearch, setUseDeepResearch] = useState(true);
  const [creatorProfiles, setCreatorProfiles] = useState<CreatorProfile[]>([]);
  
  // 模板选择（统一展示 PhaseTemplate + FieldTemplate）
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [expandedTemplateId, setExpandedTemplateId] = useState<string | null>(null);
  // P0-1: 所有项目都使用 ContentBlock 架构（原 useNewArchitecture 始终为 true）
  
  // 状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 加载数据
  useEffect(() => {
    if (isOpen) {
      loadCreatorProfiles();
      loadTemplates();
      // 重置状态
      setStep("info");
      setName("");
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const loadCreatorProfiles = async () => {
    try {
      const profiles = await settingsAPI.listCreatorProfiles();
      setCreatorProfiles(profiles);
      if (profiles.length > 0 && !creatorProfileId) {
        setCreatorProfileId(profiles[0].id);
      }
    } catch (err) {
      console.error("加载创作者特质失败:", err);
    }
  };
  
  const loadTemplates = async () => {
    try {
      // 同时加载 PhaseTemplate 和 FieldTemplate，统一展示
      const [phaseData, fieldData] = await Promise.all([
        phaseTemplateAPI.list().catch(() => [] as PhaseTemplate[]),
        settingsAPI.listFieldTemplates().catch(() => [] as FieldTemplateLike[]),
      ]);

      const items: TemplateItem[] = [];

      // PhaseTemplate → TemplateItem
      for (const pt of phaseData) {
        const fieldCount = pt.phases.reduce((sum, p) => sum + (p.default_fields || []).length, 0);
        const contentCount = pt.phases.reduce(
          (sum, p) => sum + (p.default_fields || []).filter((f) => f.content).length,
          0
        );
        items.push({
          id: pt.id,
          name: pt.name,
          description: pt.description,
          source: "phase",
          phases: pt.phases,
          is_default: pt.is_default,
          fieldCount,
          contentCount,
        });
      }

      // FieldTemplate → TemplateItem（只有 PhaseTemplate 中不存在同名模板时才显示）
      const phaseNames = new Set(phaseData.map((p) => p.name));
      for (const ft of fieldData) {
        if (phaseNames.has(ft.name)) continue; // 避免重复
        const fields = ft.fields || [];
        items.push({
          id: ft.id,
          name: ft.name,
          description: ft.description || ft.category || "",
          source: "field",
          phases: [
            {
              name: ft.name,
              block_type: "phase",
              special_handler: null,
              order_index: 0,
              default_fields: fields.map((f: FieldTemplateLikeField) => ({
                name: f.name,
                block_type: "field",
                ai_prompt: f.ai_prompt,
                content: f.content,
              })),
            },
          ],
          is_default: false,
          fieldCount: fields.length,
          contentCount: fields.filter((f: FieldTemplateLikeField) => f.content).length,
        });
      }

      setTemplates(items);

      // 默认选中默认模板（如果有）
      const defaultTemplate = items.find((t) => t.is_default);
      if (defaultTemplate) {
        setSelectedTemplateId(defaultTemplate.id);
        setExpandedTemplateId(defaultTemplate.id);
      } else {
        setSelectedTemplateId(null);
      }
    } catch (err) {
      console.error("加载模板失败:", err);
    }
  };

  const handleNextStep = () => {
    if (!name.trim()) {
      setError("请输入项目名称");
      return;
    }
    if (!creatorProfileId) {
      setError("请选择创作者特质");
      return;
    }
    setError(null);
    setStep("template");
  };

  const handlePrevStep = () => {
    setStep("info");
    setError(null);
  };

  const handleSubmit = async () => {
    if (!name.trim() || !creatorProfileId) {
      setError("请填写必要信息");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // 1. 创建项目（P0-1: 始终使用 ContentBlock 架构）
      const project = await projectAPI.create({
        name: name.trim(),
        creator_profile_id: creatorProfileId,
        use_deep_research: useDeepResearch,
        use_flexible_architecture: true,
        phase_order: selectedTemplateId === null ? [] : undefined,
      });
      
      // 2. 如果选择了模板，应用模板
      if (selectedTemplateId) {
        try {
          await blockAPI.applyTemplate(project.id, selectedTemplateId);
        } catch (templateErr) {
          console.warn("应用模板失败，使用传统流程:", templateErr);
        }
      }
      
      onCreated(project);
      
      // 重置表单
      setName("");
      setCreatorProfileId(creatorProfiles[0]?.id || "");
      setUseDeepResearch(true);
      setStep("info");
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
      <div className="relative w-full max-w-lg bg-surface-1 border border-surface-3 rounded-xl shadow-2xl">
        {/* 步骤指示器 */}
        <div className="px-6 pt-6 pb-4 border-b border-surface-3">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-zinc-100">
              新建内容项目
            </h2>
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span className={step === "info" ? "text-brand-400 font-medium" : ""}>
                1. 基本信息
              </span>
              <ChevronRight className="w-3 h-3" />
              <span className={step === "template" ? "text-brand-400 font-medium" : ""}>
                2. 流程设置
              </span>
            </div>
          </div>
          
          {/* 进度条 */}
          <div className="h-1 bg-surface-3 rounded-full overflow-hidden">
            <div 
              className="h-full bg-brand-500 transition-all duration-300"
              style={{ width: step === "info" ? "50%" : "100%" }}
            />
          </div>
        </div>

        <div className="p-6">
          {/* 第一步：基本信息 */}
          {step === "info" && (
            <div className="space-y-5">
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
                      <a href="/settings" className="underline hover:text-amber-100">
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
            </div>
          )}

          {/* 第二步：流程设置 */}
          {step === "template" && (
            <div className="space-y-5">
              {/* 架构选择 */}
              <div className="flex items-center justify-between p-4 bg-surface-2 rounded-lg">
                <div>
                  <p className="text-sm font-medium text-zinc-200">
                    选择流程模板
                  </p>
                  <p className="text-xs text-zinc-500 mt-1">
                    所有项目使用灵活架构，支持自定义阶段和内容块
                  </p>
                </div>
              </div>
              
              {/* 模板选择 */}
              {(
                <div className="space-y-3">
                  <label className="block text-sm font-medium text-zinc-300">
                    选择流程模板
                  </label>
                  
                  <div className="max-h-64 overflow-y-auto space-y-2">
                    {/* 从零开始选项 */}
                    <div
                      className={`
                        border rounded-lg overflow-hidden transition-all cursor-pointer
                        ${selectedTemplateId === null 
                          ? "border-brand-500 bg-brand-500/10" 
                          : "border-surface-3 bg-surface-2 hover:border-surface-2"
                        }
                      `}
                      onClick={() => setSelectedTemplateId(null)}
                    >
                      <div className="flex items-center gap-3 p-3">
                        <div
                          className={`
                            w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0
                            ${selectedTemplateId === null ? "border-brand-500 bg-brand-500" : "border-zinc-600"}
                          `}
                        >
                          {selectedTemplateId === null && <Check className="w-2.5 h-2.5 text-white" />}
                        </div>
                        
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-zinc-200">
                              从零开始
                            </span>
                          </div>
                          <p className="text-xs text-zinc-500 mt-0.5">
                            创建空白项目，自由添加组和字段
                          </p>
                        </div>
                      </div>
                    </div>
                    
                    {/* 已有模板 */}
                    {templates.map((template) => {
                      const isSelected = selectedTemplateId === template.id;
                      const isExpanded = expandedTemplateId === template.id;
                      
                      return (
                        <div
                          key={template.id}
                          className={`
                            border rounded-lg overflow-hidden transition-all cursor-pointer
                            ${isSelected 
                              ? "border-brand-500 bg-brand-500/10" 
                              : "border-surface-3 bg-surface-2 hover:border-surface-2"
                            }
                          `}
                          onClick={() => setSelectedTemplateId(template.id)}
                        >
                          <div className="flex items-center gap-3 p-3">
                            <div
                              className={`
                                w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0
                                ${isSelected ? "border-brand-500 bg-brand-500" : "border-zinc-600"}
                              `}
                            >
                              {isSelected && <Check className="w-2.5 h-2.5 text-white" />}
                            </div>
                            
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium text-zinc-200 truncate">
                                  {template.name}
                                </span>
                                {template.is_default && (
                                  <span className="px-1.5 py-0.5 text-xs bg-brand-500/20 text-brand-400 rounded">
                                    默认
                                  </span>
                                )}
                              </div>
                              <p className="text-xs text-zinc-500 truncate mt-0.5">
                                {template.phases.length} 个组 · {template.fieldCount} 个内容块
                                {template.contentCount > 0 && (
                                  <span className="text-emerald-400/80 ml-1">
                                    ({template.contentCount} 个有预置内容)
                                  </span>
                                )}
                                {template.source === "field" && (
                                  <span className="text-amber-400/80 ml-1">(内容块模板)</span>
                                )}
                              </p>
                            </div>
                            
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setExpandedTemplateId(isExpanded ? null : template.id);
                              }}
                              className="p-1 hover:bg-surface-3 rounded text-zinc-500"
                            >
                              <ChevronRight className={`w-4 h-4 transition-transform ${isExpanded ? "rotate-90" : ""}`} />
                            </button>
                          </div>
                          
                          {/* 阶段预览 */}
                          {isExpanded && (
                            <div className="px-3 pb-3 pt-1 border-t border-surface-3">
                              <div className="space-y-1">
                                {template.phases.map((phase, idx) => (
                                  <div
                                    key={idx}
                                    className="flex items-center gap-2 py-1 px-2 rounded bg-surface-1 text-xs"
                                  >
                                    <span className="text-zinc-600 w-4">{idx + 1}</span>
                                    {phase.special_handler && specialHandlerIcons[phase.special_handler] ? (
                                      specialHandlerIcons[phase.special_handler]
                                    ) : (
                                      <Folder className="w-3.5 h-3.5 text-zinc-500" />
                                    )}
                                    <span className="text-zinc-300">{phase.name}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              
              {/* P0-1: 传统流程提示已移除，所有项目使用 ContentBlock 架构 */}
            </div>
          )}

          {/* 错误提示 */}
          {error && (
            <div className="mt-4 p-3 bg-red-900/20 border border-red-700/50 rounded-lg">
              <p className="text-sm text-red-300">{error}</p>
            </div>
          )}
        </div>

        {/* 按钮区 */}
        <div className="px-6 py-4 border-t border-surface-3 flex justify-between">
          <div>
            {step === "template" && (
              <button
                type="button"
                onClick={handlePrevStep}
                className="flex items-center gap-1 px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
                上一步
              </button>
            )}
          </div>
          
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              取消
            </button>
            
            {step === "info" ? (
              <button
                type="button"
                onClick={handleNextStep}
                disabled={!name.trim() || !creatorProfileId}
                className="flex items-center gap-1 px-5 py-2 text-sm bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
              >
                下一步
                <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={loading}
                className="px-5 py-2 text-sm bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
              >
                {loading ? "创建中..." : "创建项目"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

