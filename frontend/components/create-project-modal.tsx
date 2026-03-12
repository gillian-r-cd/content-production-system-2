// frontend/components/create-project-modal.tsx
// 功能: 创建项目对话框，支持两步流程：基本信息 → 选择模板，并按 locale 同步创作者特质与模板资产
// 主要组件: CreateProjectModal
// 集成: TemplateSelector 用于选择流程模板

"use client";

import { useState, useEffect } from "react";
import { settingsAPI, projectAPI, blockAPI } from "@/lib/api";
import type { CreatorProfile, Project, TemplateNode } from "@/lib/api";
import { resolveClientLocale } from "@/lib/project-locale";

// 统一模板项（仅展示结构模板树）
interface TemplateItem {
  id: string;
  name: string;
  description: string;
  phases: Array<{
    name: string;
    block_type: string;
    special_handler: string | null;
    order_index: number;
    default_fields: Array<{
      name: string;
      block_type: string;
      ai_prompt?: string;
      content?: string;
    }>;
  }>;
  root_nodes?: TemplateNode[];
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
  locale?: string;
  description?: string;
  category?: string;
  fields?: FieldTemplateLikeField[];
  root_nodes?: TemplateNode[];
}
import { ChevronLeft, ChevronRight, Check, Folder, Lightbulb, Users, PlayCircle, BarChart3 } from "lucide-react";

interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (project: Project) => void;
}

type Step = "info" | "template";

const PROJECT_LOCALES = [
  { value: "zh-CN", label: "简体中文" },
  { value: "ja-JP", label: "日本語" },
];

const UI_TEXT = {
  "zh-CN": {
    title: "新建内容项目",
    step1: "1. 基本信息",
    step2: "2. 流程设置",
    projectName: "项目名称",
    projectNamePlaceholder: "例如：产品发布内容策划",
    projectLanguage: "项目语言",
    creatorProfile: "创作者特质",
    noProfile: "还没有创作者特质，请先在后台设置中创建。",
    selectPlaceholder: "请选择...",
    deepResearch: "启用 DeepResearch",
    deepResearchHint: "消费者调研阶段将使用网络搜索获取更深入的用户洞察",
    templateTitle: "选择流程模板",
    templateHint: "所有项目使用灵活架构，支持自定义阶段和内容块",
    emptyTemplate: "从零开始",
    emptyTemplateHint: "创建空白项目，自由添加组和字段",
    defaultTag: "默认",
    previous: "上一步",
    cancel: "取消",
    next: "下一步",
    creating: "创建中...",
    create: "创建项目",
    needName: "请输入项目名称",
    needProfile: "请选择创作者特质",
    needRequired: "请填写必要信息",
    createFailed: "创建失败",
  },
  "ja-JP": {
    title: "新規コンテンツプロジェクト",
    step1: "1. 基本情報",
    step2: "2. フロー設定",
    projectName: "プロジェクト名",
    projectNamePlaceholder: "例: 新製品ローンチのコンテンツ企画",
    projectLanguage: "プロジェクト言語",
    creatorProfile: "クリエイタープロファイル",
    noProfile: "利用可能なクリエイタープロファイルがありません。先に設定画面で作成してください。",
    selectPlaceholder: "選択してください...",
    deepResearch: "DeepResearch を有効化",
    deepResearchHint: "顧客調査フェーズで Web 検索を使い、より深いインサイトを取得します。",
    templateTitle: "フローテンプレートを選択",
    templateHint: "すべてのプロジェクトは柔軟アーキテクチャを使用し、段階と内容ブロックを自由に構成できます。",
    emptyTemplate: "ゼロから開始",
    emptyTemplateHint: "空のプロジェクトを作成し、グループやブロックを自由に追加します。",
    defaultTag: "既定",
    previous: "戻る",
    cancel: "キャンセル",
    next: "次へ",
    creating: "作成中...",
    create: "プロジェクトを作成",
    needName: "プロジェクト名を入力してください",
    needProfile: "クリエイタープロファイルを選択してください",
    needRequired: "必須項目を入力してください",
    createFailed: "プロジェクトの作成に失敗しました",
  },
} as const;

// 特殊处理器图标
const specialHandlerIcons: Record<string, React.ReactNode> = {
  intent: <Lightbulb className="w-4 h-4 text-amber-400" />,
  research: <Users className="w-4 h-4 text-blue-400" />,
  simulate: <PlayCircle className="w-4 h-4 text-purple-400" />,
  evaluate: <BarChart3 className="w-4 h-4 text-emerald-400" />,
};

function flattenTemplateNodes(nodes: TemplateNode[] = []): TemplateNode[] {
  return nodes.flatMap((node) => [node, ...flattenTemplateNodes(node.children || [])]);
}

function countFieldNodes(nodes: TemplateNode[] = []): number {
  return flattenTemplateNodes(nodes).filter((node) => node.block_type === "field").length;
}

function countContentNodes(nodes: TemplateNode[] = []): number {
  return flattenTemplateNodes(nodes).filter((node) => !!node.content).length;
}

function formatTemplateStructureSummary(locale: string, groupCount: number, fieldCount: number): string {
  if (locale === "ja-JP") {
    return `${groupCount} 個のグループ · ${fieldCount} 個の内容ブロック`;
  }
  return `${groupCount} 个组 · ${fieldCount} 个内容块`;
}

function formatTemplatePresetSummary(locale: string, contentCount: number): string {
  if (locale === "ja-JP") {
    return `${contentCount} 件の初期内容あり`;
  }
  return `${contentCount} 个有预置内容`;
}

function rootNodesToPreviewPhases(nodes: TemplateNode[] = [], fallbackName: string): TemplateItem["phases"] {
  if (!nodes.length) return [];

  const groupLikeNodes = nodes.filter((node) => node.block_type === "group");
  if (groupLikeNodes.length === nodes.length) {
    return groupLikeNodes.map((node, index) => ({
      name: node.name,
      block_type: node.block_type,
      special_handler: node.special_handler || null,
      order_index: index,
      default_fields: (node.children || []).map((child) => ({
        name: child.name,
        block_type: child.block_type,
        ai_prompt: child.ai_prompt,
        content: child.content,
      })),
    }));
  }

  return [{
    name: fallbackName,
    block_type: "group",
    special_handler: null,
    order_index: 0,
    default_fields: flattenTemplateNodes(nodes)
      .filter((node) => node.block_type === "field")
      .map((node) => ({
        name: node.name,
        block_type: node.block_type,
        ai_prompt: node.ai_prompt,
        content: node.content,
      })),
  }];
}

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
  const [locale, setLocale] = useState<string>(() => resolveClientLocale());
  const [useDeepResearch, setUseDeepResearch] = useState(true);
  const [creatorProfiles, setCreatorProfiles] = useState<CreatorProfile[]>([]);
  
  // 模板选择（统一展示结构模板）
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [expandedTemplateId, setExpandedTemplateId] = useState<string | null>(null);
  // P0-1: 所有项目都使用 ContentBlock 架构（原 useNewArchitecture 始终为 true）
  
  // 状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t = UI_TEXT[locale as keyof typeof UI_TEXT] || UI_TEXT["zh-CN"];

  // 加载数据
  useEffect(() => {
    if (isOpen) {
      const nextLocale = resolveClientLocale();
      // 重置状态
      setStep("info");
      setName("");
      setLocale(nextLocale);
      setCreatorProfiles([]);
      setTemplates([]);
      setCreatorProfileId("");
      setSelectedTemplateId(null);
      setExpandedTemplateId(null);
      setUseDeepResearch(true);
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const loadCreatorProfiles = async (targetLocale: string, isCancelled: () => boolean) => {
    try {
      const profiles = await settingsAPI.listCreatorProfiles();
      if (isCancelled()) return;
      const localizedProfiles = profiles.filter((profile) => (profile.locale || "zh-CN") === targetLocale);
      setCreatorProfiles(localizedProfiles);
      setCreatorProfileId((currentId) => {
        if (localizedProfiles.some((profile) => profile.id === currentId)) {
          return currentId;
        }
        return localizedProfiles[0]?.id || "";
      });
    } catch (err) {
      console.error("加载创作者特质失败:", err);
    }
  };
  
  const loadTemplates = async (targetLocale: string, isCancelled: () => boolean) => {
    try {
      const fieldData = await settingsAPI.listFieldTemplates().catch(() => [] as FieldTemplateLike[]);
      if (isCancelled()) return;
      const localizedTemplates = fieldData.filter((template) => (template.locale || "zh-CN") === targetLocale);

      const items: TemplateItem[] = [];

      // FieldTemplate → TemplateItem
      for (const ft of localizedTemplates) {
        const fields = ft.fields || [];
        const rootNodes = ft.root_nodes || [];
        const previewPhases = rootNodes.length
          ? rootNodesToPreviewPhases(rootNodes, ft.name)
          : [
              {
                name: ft.name,
                block_type: "group",
                special_handler: null,
                order_index: 0,
                default_fields: fields.map((f: FieldTemplateLikeField) => ({
                  name: f.name,
                  block_type: "field",
                  ai_prompt: f.ai_prompt,
                  content: f.content,
                })),
              },
            ];
        items.push({
          id: ft.id,
          name: ft.name,
          description: ft.description || ft.category || "",
          phases: previewPhases,
          root_nodes: rootNodes,
          is_default: false,
          fieldCount: rootNodes.length ? countFieldNodes(rootNodes) : fields.length,
          contentCount: rootNodes.length ? countContentNodes(rootNodes) : fields.filter((f: FieldTemplateLikeField) => f.content).length,
        });
      }

      if (isCancelled()) return;
      setTemplates(items);

      const defaultTemplate = items.find((t) => t.is_default);
      setSelectedTemplateId((currentId) => {
        if (currentId && items.some((template) => template.id === currentId)) {
          return currentId;
        }
        return defaultTemplate?.id || null;
      });
      setExpandedTemplateId((currentId) => {
        if (currentId && items.some((template) => template.id === currentId)) {
          return currentId;
        }
        return defaultTemplate?.id || null;
      });
    } catch (err) {
      console.error("加载模板失败:", err);
    }
  };

  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;
    const isCancelled = () => cancelled;

    setCreatorProfiles([]);
    setTemplates([]);
    setCreatorProfileId("");
    setSelectedTemplateId(null);
    setExpandedTemplateId(null);

    void loadCreatorProfiles(locale, isCancelled);
    void loadTemplates(locale, isCancelled);

    return () => {
      cancelled = true;
    };
  }, [isOpen, locale]);

  const handleNextStep = () => {
    if (!name.trim()) {
      setError(t.needName);
      return;
    }
    if (!creatorProfileId) {
      setError(t.needProfile);
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
      setError(t.needRequired);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // 1. 创建项目（P0-1: 始终使用 ContentBlock 架构）
      const project = await projectAPI.create({
        name: name.trim(),
        creator_profile_id: creatorProfileId,
        locale,
        use_deep_research: useDeepResearch,
        use_flexible_architecture: true,
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
      setCreatorProfileId("");
      setLocale(resolveClientLocale());
      setUseDeepResearch(true);
      setStep("info");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.createFailed);
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
              {t.title}
            </h2>
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span className={step === "info" ? "text-brand-400 font-medium" : ""}>
                {t.step1}
              </span>
              <ChevronRight className="w-3 h-3" />
              <span className={step === "template" ? "text-brand-400 font-medium" : ""}>
                {t.step2}
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
                  {t.projectName} <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t.projectNamePlaceholder}
                  className="w-full px-4 py-2.5 bg-surface-2 border border-surface-3 rounded-lg text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                  autoFocus
                />
              </div>

              {/* 创作者特质 */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  {t.projectLanguage} <span className="text-red-400">*</span>
                </label>
                <select
                  value={locale}
                  onChange={(e) => setLocale(e.target.value)}
                  className="w-full px-4 py-2.5 bg-surface-2 border border-surface-3 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                >
                  {PROJECT_LOCALES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* 创作者特质 */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  {t.creatorProfile} <span className="text-red-400">*</span>
                </label>
                {creatorProfiles.length === 0 ? (
                  <div className="p-4 bg-amber-900/20 border border-amber-700/50 rounded-lg">
                    <p className="text-sm text-amber-200">
                      {t.noProfile}{" "}
                      <a href="/settings" className="underline hover:text-amber-100">
                        /settings
                      </a>{" "}
                    </p>
                  </div>
                ) : (
                  <select
                    value={creatorProfileId}
                    onChange={(e) => setCreatorProfileId(e.target.value)}
                    className="w-full px-4 py-2.5 bg-surface-2 border border-surface-3 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  >
                    <option value="">{t.selectPlaceholder}</option>
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
                    {t.deepResearch}
                  </p>
                  <p className="text-xs text-zinc-500 mt-1">
                    {t.deepResearchHint}
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
                    {t.templateTitle}
                  </p>
                  <p className="text-xs text-zinc-500 mt-1">
                    {t.templateHint}
                  </p>
                </div>
              </div>
              
              {/* 模板选择 */}
              {(
                <div className="space-y-3">
                  <label className="block text-sm font-medium text-zinc-300">
                    {t.templateTitle}
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
                              {t.emptyTemplate}
                            </span>
                          </div>
                          <p className="text-xs text-zinc-500 mt-0.5">
                            {t.emptyTemplateHint}
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
                                    {t.defaultTag}
                                  </span>
                                )}
                              </div>
                              <p className="text-xs text-zinc-500 truncate mt-0.5">
                                {formatTemplateStructureSummary(locale, template.phases.length, template.fieldCount)}
                                {template.contentCount > 0 && (
                                  <span className="text-emerald-400/80 ml-1">
                                    ({formatTemplatePresetSummary(locale, template.contentCount)})
                                  </span>
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
                {t.previous}
              </button>
            )}
          </div>
          
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              {t.cancel}
            </button>
            
            {step === "info" ? (
              <button
                type="button"
                onClick={handleNextStep}
                disabled={!name.trim() || !creatorProfileId}
                className="flex items-center gap-1 px-5 py-2 text-sm bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
              >
                {t.next}
                <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={loading}
                className="px-5 py-2 text-sm bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
              >
                {loading ? t.creating : t.create}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

