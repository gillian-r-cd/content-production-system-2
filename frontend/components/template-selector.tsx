// frontend/components/template-selector.tsx
// 功能: 阶段模板选择器组件
// 主要组件: TemplateSelector
// 用途: 在创建项目或重置流程时选择预设模板

"use client";

import { useState, useEffect } from "react";
import { 
  LayoutTemplate, 
  Check, 
  ChevronRight, 
  Folder, 
  FileText,
  Lightbulb,
  Users,
  PlayCircle,
  BarChart3,
} from "lucide-react";
import { PhaseTemplate, phaseTemplateAPI, blockAPI } from "@/lib/api";

interface TemplateSelectorProps {
  projectId?: string;
  onSelect?: (template: PhaseTemplate) => void;
  onApply?: (template: PhaseTemplate) => void;
  mode?: "select" | "apply"; // select: 仅选择，apply: 选择并应用
}

// 特殊处理器图标
const specialHandlerIcons: Record<string, React.ReactNode> = {
  intent: <Lightbulb className="w-4 h-4 text-amber-400" />,
  research: <Users className="w-4 h-4 text-blue-400" />,
  simulate: <PlayCircle className="w-4 h-4 text-purple-400" />,
  evaluate: <BarChart3 className="w-4 h-4 text-emerald-400" />,
};

export default function TemplateSelector({
  projectId,
  onSelect,
  onApply,
  mode = "select",
}: TemplateSelectorProps) {
  const [templates, setTemplates] = useState<PhaseTemplate[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 加载模板列表
  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await phaseTemplateAPI.list();
      setTemplates(data);
      
      // 默认选中默认模板
      const defaultTemplate = data.find((t) => t.is_default);
      if (defaultTemplate) {
        setSelectedId(defaultTemplate.id);
        setExpandedId(defaultTemplate.id);
      }
    } catch (err) {
      console.error("加载模板失败:", err);
      setError("加载模板失败");
    } finally {
      setIsLoading(false);
    }
  };

  // 处理选择
  const handleSelect = (template: PhaseTemplate) => {
    setSelectedId(template.id);
    onSelect?.(template);
  };

  // 处理应用
  const handleApply = async () => {
    if (!selectedId || !projectId) return;

    const template = templates.find((t) => t.id === selectedId);
    if (!template) return;

    setIsApplying(true);
    try {
      await blockAPI.applyTemplate(projectId, selectedId);
      onApply?.(template);
    } catch (err) {
      console.error("应用模板失败:", err);
      alert("应用模板失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsApplying(false);
    }
  };

  // 切换展开
  const toggleExpand = (templateId: string) => {
    setExpandedId(expandedId === templateId ? null : templateId);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-red-400">
        <p>{error}</p>
        <button
          onClick={loadTemplates}
          className="mt-4 px-4 py-2 bg-surface-2 rounded-lg hover:bg-surface-3 transition-colors"
        >
          重试
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-zinc-400 mb-4">
        <LayoutTemplate className="w-4 h-4" />
        <span>选择流程模板</span>
      </div>

      {/* 模板列表 */}
      <div className="space-y-2">
        {templates.map((template) => {
          const isSelected = selectedId === template.id;
          const isExpanded = expandedId === template.id;

          return (
            <div
              key={template.id}
              className={`
                border rounded-xl overflow-hidden transition-all
                ${isSelected 
                  ? "border-brand-500 bg-brand-500/10" 
                  : "border-surface-3 bg-surface-1 hover:border-surface-2"
                }
              `}
            >
              {/* 模板头部 */}
              <div
                className="flex items-center gap-3 p-4 cursor-pointer"
                onClick={() => handleSelect(template)}
              >
                {/* 选中指示器 */}
                <div
                  className={`
                    w-5 h-5 rounded-full border-2 flex items-center justify-center
                    ${isSelected ? "border-brand-500 bg-brand-500" : "border-zinc-600"}
                  `}
                >
                  {isSelected && <Check className="w-3 h-3 text-white" />}
                </div>

                {/* 模板信息 */}
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-zinc-200">{template.name}</h3>
                    {template.is_default && (
                      <span className="px-2 py-0.5 text-xs bg-brand-500/20 text-brand-400 rounded">
                        默认
                      </span>
                    )}
                    {template.is_system && (
                      <span className="px-2 py-0.5 text-xs bg-zinc-700 text-zinc-400 rounded">
                        系统
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-zinc-500 mt-1 line-clamp-2">
                    {template.description || "无描述"}
                  </p>
                </div>

                {/* 展开按钮 */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleExpand(template.id);
                  }}
                  className={`
                    p-1 rounded hover:bg-surface-2 transition-transform
                    ${isExpanded ? "rotate-90" : ""}
                  `}
                >
                  <ChevronRight className="w-4 h-4 text-zinc-500" />
                </button>
              </div>

              {/* 阶段预览 */}
              {isExpanded && (
                <div className="px-4 pb-4 pt-2 border-t border-surface-3">
                  <div className="text-xs text-zinc-500 mb-2">
                    包含 {template.phases.length} 个阶段
                  </div>
                  <div className="space-y-1">
                    {template.phases.map((phase, idx) => (
                      <div
                        key={idx}
                        className="flex items-center gap-2 py-1.5 px-2 rounded bg-surface-0"
                      >
                        <span className="text-zinc-500 text-xs w-4">{idx + 1}</span>
                        {phase.special_handler && specialHandlerIcons[phase.special_handler] ? (
                          specialHandlerIcons[phase.special_handler]
                        ) : (
                          <Folder className="w-4 h-4 text-zinc-500" />
                        )}
                        <span className="text-sm text-zinc-300">{phase.name}</span>
                        {phase.default_fields && phase.default_fields.length > 0 && (
                          <span className="text-xs text-zinc-600 ml-auto">
                            {phase.default_fields.length} 个字段
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 应用按钮 */}
      {mode === "apply" && projectId && (
        <button
          onClick={handleApply}
          disabled={!selectedId || isApplying}
          className={`
            w-full py-3 rounded-xl font-medium transition-colors
            ${selectedId && !isApplying
              ? "bg-brand-500 text-white hover:bg-brand-600"
              : "bg-surface-2 text-zinc-500 cursor-not-allowed"
            }
          `}
        >
          {isApplying ? (
            <span className="flex items-center justify-center gap-2">
              <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              应用中...
            </span>
          ) : (
            "应用模板"
          )}
        </button>
      )}

      {/* 说明 */}
      <p className="text-xs text-zinc-600 text-center">
        选择模板后，将自动创建对应的流程阶段和默认字段。
        <br />
        你可以随时调整阶段顺序、添加或删除内容。
      </p>
    </div>
  );
}
