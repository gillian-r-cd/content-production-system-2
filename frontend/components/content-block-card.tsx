// frontend/components/content-block-card.tsx
// 功能: 紧凑版 ContentBlock 卡片，用于阶段视图中显示字段的所有设置
// 支持不同类型：phase（阶段）显示子节点数量和进入按钮，field（字段）显示完整编辑功能
// 包含：名称、状态、AI提示词、依赖、约束、need_review、auto_generate、模型覆盖(M5)、生成/编辑/删除按钮

"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { blockAPI, runAutoTriggerChain, modelsAPI } from "@/lib/api";
import { useBlockGeneration } from "@/lib/hooks/useBlockGeneration";
import type { ContentBlock, ModelInfo } from "@/lib/api";
import { VersionHistoryButton } from "./version-history";
import { sendNotification } from "@/lib/utils";
import { 
  Play,
  Square,
  MessageSquarePlus,
  Workflow,
  ShieldCheck,
  Zap,
  Pencil,
  Save, 
  Trash2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  X,
  Folder,
  FolderOpen,
  FileText,
  Layers,
  Copy,
  Check,
  Cpu,
} from "lucide-react";

interface ContentBlockCardProps {
  block: ContentBlock;
  projectId: string;
  allBlocks?: ContentBlock[];  // 用于依赖选择
  onUpdate?: () => void;
  onSelect?: () => void;  // 点击选中此块（用于进入子组/分组）
}

export function ContentBlockCard({ 
  block, 
  projectId, 
  allBlocks = [], 
  onUpdate,
  onSelect 
}: ContentBlockCardProps) {
  // P0-1: 统一使用 blockAPI（已移除 fieldAPI/isVirtual 分支）
  
  const [isExpanded, setIsExpanded] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState(block.name);
  const [editedContent, setEditedContent] = useState(block.content || "");
  
  // 模态框状态
  const [showPromptModal, setShowPromptModal] = useState(false);
  const [showDependencyModal, setShowDependencyModal] = useState(false);
  
  // 编辑状态
  const [editedPrompt, setEditedPrompt] = useState(block.ai_prompt || "");
  const [savedPrompt, setSavedPrompt] = useState(block.ai_prompt || ""); // 本地追踪已保存的提示词
  const [selectedDependencies, setSelectedDependencies] = useState<string[]>(block.depends_on || []);
  const [aiPromptPurpose, setAiPromptPurpose] = useState("");
  const [generatingPrompt, setGeneratingPrompt] = useState(false);
  
  // 生成前提问答案
  const [preAnswers, setPreAnswers] = useState<Record<string, string>>(block.pre_answers || {});
  const [isSavingPreAnswers, setIsSavingPreAnswers] = useState(false);
  const [preAnswersSaved, setPreAnswersSaved] = useState(false);
  const hasPreQuestions = (block.pre_questions?.length || 0) > 0;

  // M5: 模型覆盖
  const [modelOverride, setModelOverride] = useState<string>(block.model_override || "");
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [showModelSelector, setShowModelSelector] = useState(false);
  const modelBtnRef = useRef<HTMLButtonElement>(null);
  const [modelDropdownPos, setModelDropdownPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  // Escape 键关闭弹窗 + 点击外部关闭模型选择器
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showModelSelector) setShowModelSelector(false);
        else if (showPromptModal) setShowPromptModal(false);
        else if (showDependencyModal) setShowDependencyModal(false);
      }
    };
    const clickHandler = (e: MouseEvent) => {
      if (showModelSelector) {
        const target = e.target as HTMLElement;
        if (!target.closest("[data-model-selector]")) {
          setShowModelSelector(false);
        }
      }
    };
    window.addEventListener("keydown", handler);
    document.addEventListener("mousedown", clickHandler);
    return () => {
      window.removeEventListener("keydown", handler);
      document.removeEventListener("mousedown", clickHandler);
    };
  }, [showPromptModal, showDependencyModal, showModelSelector]);

  // ---- 生成逻辑（通过 Hook 统一管理） ----
  const {
    isGenerating, generatingContent, canGenerate, unmetDependencies,
    handleGenerate: _handleGenerate, handleStop: _handleStop,
  } = useBlockGeneration({
    block, projectId, allBlocks,
    preAnswers, hasPreQuestions,
    onUpdate,
    onContentReady: (content) => setEditedContent(content),
  });

  const handleGenerate = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!canGenerate) {
      alert(`以下依赖内容为空:\n${unmetDependencies.map(d => `• ${d.name}`).join("\n")}`);
      return;
    }
    setIsExpanded(true); // Card 特有：自动展开显示生成内容
    setIsEditing(false);
    await _handleGenerate();
  };

  const handleStopGeneration = (e: React.MouseEvent) => {
    e.stopPropagation();
    _handleStop();
  };

  const [copied, setCopied] = useState(false);
  
  const handleCopyContent = (e: React.MouseEvent) => {
    e.stopPropagation();
    const content = block.content || editedContent;
    if (content) {
      navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };
  
  // 保存预提问答案
  const handleSavePreAnswers = async () => {
    setIsSavingPreAnswers(true);
    try {
      await blockAPI.update(block.id, { pre_answers: preAnswers });
      setPreAnswersSaved(true);
      setTimeout(() => setPreAnswersSaved(false), 2000);
      onUpdate?.();
      
      // 保存后前端驱动自动触发链
      if (projectId) {
        runAutoTriggerChain(projectId, () => onUpdate?.()).catch(console.error);
      }
    } catch (err) {
      console.error("保存答案失败:", err);
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsSavingPreAnswers(false);
    }
  };
  
  // 可选的依赖（排除自己和自己的子节点）
  const availableDependencies = allBlocks.filter(b => {
    if (b.id === block.id) return false;
    if (b.parent_id === block.id) return false;
    if (b.block_type === "field") return true;
    if (b.block_type === "phase" && b.special_handler) return true;
    return false;
  });
  
  // 获取依赖的内容块详情
  const dependencyBlocks = selectedDependencies
    .map(id => allBlocks.find(b => b.id === id))
    .filter(Boolean) as ContentBlock[];
  
  useEffect(() => {
    // 生成中不要重置内容（会覆盖流式输出）
    if (!isGenerating) {
      setEditedContent(block.content || "");
    }
    setEditedName(block.name);
    setEditedPrompt(block.ai_prompt || "");
    setSavedPrompt(block.ai_prompt || "");
    setSelectedDependencies(block.depends_on || []);
    setPreAnswers(block.pre_answers || {});
    // M5: 同步 model_override
    setModelOverride(block.model_override || "");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block.id, block.content, block.name, block.ai_prompt, block.depends_on, block.pre_answers]);

  // M5: 加载可用模型列表
  useEffect(() => {
    modelsAPI.list().then((data) => {
      setAvailableModels(data.models);
    }).catch(console.error);
  }, []);

  // M5: 打开模型选择器（计算按钮位置，用 fixed 定位避免 overflow-hidden 裁剪）
  const handleToggleModelSelector = useCallback(() => {
    if (!showModelSelector && modelBtnRef.current) {
      const rect = modelBtnRef.current.getBoundingClientRect();
      setModelDropdownPos({ top: rect.bottom + 4, left: Math.max(8, rect.right - 224) }); // 224 = w-56
    }
    setShowModelSelector(prev => !prev);
  }, [showModelSelector]);

  // M5: 保存模型覆盖
  const handleSaveModelOverride = async (modelId: string) => {
    try {
      // 空字符串 "" 表示清除覆盖（恢复使用全局默认），后端会转为 null
      await blockAPI.update(block.id, { model_override: modelId });
      setModelOverride(modelId);
      setShowModelSelector(false);
      onUpdate?.();
      sendNotification(modelId ? `已设置模型: ${modelId}` : "已恢复为默认模型", "success");
    } catch (err: unknown) {
      console.error("保存模型覆盖失败:", err);
      sendNotification("保存模型失败: " + (err instanceof Error ? err.message : "未知错误"), "error");
    }
  };

  // ===== 关键修复：如果 block 状态是 in_progress 但当前组件没在流式生成，则轮询刷新 =====
  useEffect(() => {
    if (block.status === "in_progress" && !isGenerating) {
      const pollInterval = setInterval(() => {
        onUpdate?.(); // 触发父组件刷新数据
      }, 2000);
      return () => clearInterval(pollInterval);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block.status, isGenerating]);

  // 保存名称
  const handleSaveName = async () => {
    if (editedName.trim() && editedName !== block.name) {
      try {
        await blockAPI.update(block.id, { name: editedName.trim() });
        onUpdate?.();
      } catch (err) {
        console.error("更新名称失败:", err);
        alert("更新名称失败: " + (err instanceof Error ? err.message : "未知错误"));
        setEditedName(block.name);
      }
    }
    setIsEditingName(false);
  };

  // 保存内容
  const handleSaveContent = async () => {
    try {
      await blockAPI.update(block.id, { content: editedContent });
      setIsEditing(false);
      onUpdate?.();
    } catch (err) {
      console.error("保存失败:", err);
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // 保存 AI 提示词
  const handleSavePrompt = async () => {
    try {
      await blockAPI.update(block.id, { ai_prompt: editedPrompt });
      setSavedPrompt(editedPrompt); // 乐观更新本地状态，立即反映到 UI
      setShowPromptModal(false);
      onUpdate?.();
    } catch (err) {
      console.error("保存提示词失败:", err);
      alert("保存提示词失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // AI 生成提示词
  const handleGeneratePrompt = async () => {
    if (!aiPromptPurpose.trim()) return;
    setGeneratingPrompt(true);
    try {
      const result = await blockAPI.generatePrompt({
        purpose: aiPromptPurpose,
        field_name: block.name,
        project_id: projectId || "",
      });
      setEditedPrompt(result.prompt);
      setAiPromptPurpose("");
    } catch (e: unknown) {
      alert("生成提示词失败: " + (e instanceof Error ? e.message : "未知错误"));
    } finally {
      setGeneratingPrompt(false);
    }
  };

  // 保存依赖
  const handleSaveDependencies = async () => {
    try {
      await blockAPI.update(block.id, { depends_on: selectedDependencies });
      setShowDependencyModal(false);
      onUpdate?.();
    } catch (err) {
      console.error("保存依赖失败:", err);
      alert("保存依赖失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // 切换依赖选择
  const toggleDependency = (blockId: string) => {
    setSelectedDependencies(prev => 
      prev.includes(blockId) 
        ? prev.filter(id => id !== blockId)
        : [...prev, blockId]
    );
  };

  // （canGenerate / unmetDependencies / handleGenerate / handleStopGeneration 由 useBlockGeneration Hook 提供）

  // 删除内容块
  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`确定要删除「${block.name}」吗？此操作不可撤销。`)) return;
    try {
      await blockAPI.delete(block.id);
      onUpdate?.();
    } catch (err) {
      console.error("删除失败:", err);
      alert("删除失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // 切换 need_review 状态
  const handleToggleNeedReview = async () => {
    try {
      await blockAPI.update(block.id, { need_review: !block.need_review });
      onUpdate?.();
    } catch (err) {
      console.error("切换审核状态失败:", err);
    }
  };

  // 切换 auto_generate 状态
  const handleToggleAutoGenerate = async () => {
    try {
      await blockAPI.update(block.id, { auto_generate: !block.auto_generate });
      onUpdate?.();
    } catch (err) {
      console.error("切换自动生成失败:", err);
    }
  };

  // 判断是否是容器类型（阶段、分组）
  const isContainer = block.block_type === "phase" || block.block_type === "group";
  const childCount = block.children?.length || 0;
  
  // 容器类型的图标
  const getContainerIcon = () => {
    if (block.block_type === "phase") {
      return <Layers className="w-4 h-4 text-purple-400" />;
    }
    if (block.block_type === "group") {
      return isExpanded ? <FolderOpen className="w-4 h-4 text-amber-400" /> : <Folder className="w-4 h-4 text-amber-400" />;
    }
    return <FileText className="w-4 h-4 text-blue-400" />;
  };

  // ========== 容器类型（阶段/分组）的渲染 ==========
  if (isContainer) {
    return (
      <div className="bg-surface-2 border border-surface-3 rounded-lg overflow-hidden">
        <div 
          className="px-4 py-3 cursor-pointer hover:bg-surface-3/50 transition-colors"
          onClick={() => onSelect?.()}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              {/* 类型图标 */}
              {getContainerIcon()}
              
              {/* 名称 */}
              <span className="font-medium text-zinc-200 truncate">
                {block.name}
              </span>
              
              {/* 类型标签 */}
              <span className={`px-2 py-0.5 text-xs rounded flex-shrink-0 ${
                block.block_type === "phase" 
                  ? "bg-purple-600/20 text-purple-400"
                  : "bg-amber-600/20 text-amber-400"
              }`}>
                子组
              </span>
              
              {/* 子节点数量 */}
              {childCount > 0 && (
                <span className="text-xs text-zinc-500">
                  包含 {childCount} 项
                </span>
              )}
              
              {/* 状态标签 */}
              <span className={`px-2 py-0.5 text-xs rounded flex-shrink-0 ${
                block.status === "completed" ? "bg-emerald-600/20 text-emerald-400" :
                block.status === "in_progress" ? "bg-amber-600/20 text-amber-400" :
                block.status === "failed" ? "bg-red-600/20 text-red-400" :
                "bg-zinc-700 text-zinc-400"
              }`}>
                {block.status === "completed" ? "已完成" :
                 block.status === "in_progress" ? "生成中" :
                 block.status === "failed" ? "失败" : "待处理"}
              </span>
            </div>
            
            {/* 进入按钮 */}
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(e);
                }}
                className="p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-600/10 rounded transition-colors"
                title="删除"
              >
                <Trash2 className="w-4 h-4" />
              </button>
              <span className="text-zinc-500 text-sm flex items-center gap-1">
                点击进入
                <ChevronRight className="w-4 h-4" />
              </span>
            </div>
          </div>
          
          {/* 简要信息 */}
          {block.ai_prompt && (
            <div className="mt-2 text-xs text-zinc-500 truncate pl-7">
              💡 {block.ai_prompt.slice(0, 60)}...
            </div>
          )}
        </div>
      </div>
    );
  }

  // ========== 特殊字段类型的紧凑渲染（意图分析、消费者调研、消费者模拟）==========
  const specialHandler = block.special_handler as string | null | undefined;
  const isSpecialField = specialHandler && [
    "intent_analysis", "intent",
    "consumer_research", "research",
    "consumer_simulation", "simulate",
  ].includes(specialHandler);
  
  if (isSpecialField) {
    const specialLabels: Record<string, { icon: string; title: string; desc: string }> = {
      "intent_analysis": { icon: "💬", title: "意图分析", desc: "由 Agent 通过对话完成，请点击进入内容块查看" },
      "intent": { icon: "💬", title: "意图分析", desc: "由 Agent 通过对话完成，请点击进入内容块查看" },
      "consumer_research": { icon: "🔍", title: "消费者调研", desc: "包含 DeepResearch 调研结果和消费者画像" },
      "research": { icon: "🔍", title: "消费者调研", desc: "包含 DeepResearch 调研结果和消费者画像" },
      "consumer_simulation": { icon: "🎭", title: "消费者模拟", desc: "模拟消费者体验和反馈" },
      "simulate": { icon: "🎭", title: "消费者模拟", desc: "模拟消费者体验和反馈" },
    };
    const info = specialLabels[specialHandler] || { icon: "⚡", title: specialHandler, desc: "特殊处理内容块" };
    
    return (
      <div className="bg-surface-2 border border-surface-3 rounded-lg overflow-hidden">
        <div 
          className="px-4 py-3 cursor-pointer hover:bg-surface-3/50 transition-colors"
          onClick={() => onSelect?.()}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <span className="text-xl flex-shrink-0">{info.icon}</span>
              <span className="font-medium text-zinc-200 truncate">{block.name}</span>
              <span className="px-2 py-0.5 text-xs rounded flex-shrink-0 bg-purple-600/20 text-purple-400">
                {info.title}
              </span>
              {/* 状态标签 */}
              <span className={`px-2 py-0.5 text-xs rounded flex-shrink-0 ${
                block.status === "completed" ? "bg-emerald-600/20 text-emerald-400" :
                block.status === "in_progress" ? "bg-amber-600/20 text-amber-400" :
                block.status === "failed" ? "bg-red-600/20 text-red-400" :
                "bg-zinc-700 text-zinc-400"
              }`}>
                {block.status === "completed" ? "已完成" :
                 block.status === "in_progress" ? "生成中" :
                 block.status === "failed" ? "失败" : "待处理"}
              </span>
            </div>
            <span className="text-zinc-500 text-sm flex items-center gap-1 flex-shrink-0">
              点击进入
              <ChevronRight className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-1.5 text-xs text-zinc-500 pl-8">
            {info.desc}
          </div>
          {block.content && (
            <div className="mt-1 text-xs text-emerald-500 pl-8">
              ✓ 已有内容
            </div>
          )}
        </div>
      </div>
    );
  }

  // ========== 字段类型的渲染 ==========
  return (
    <div className="bg-surface-2 border border-surface-3 rounded-lg overflow-hidden">
      {/* 卡片头部 - 始终显示 */}
      <div 
        className="px-4 py-3 cursor-pointer hover:bg-surface-3/50 transition-colors"
        onClick={() => !isGenerating && setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            {/* 展开/折叠图标 */}
            <button 
              className="p-0.5 text-zinc-500 hover:text-zinc-300 flex-shrink-0"
              onClick={(e) => {
                e.stopPropagation();
                if (!isGenerating) setIsExpanded(!isExpanded);
              }}
            >
              {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            
            {/* 内容块图标 */}
            <FileText className="w-4 h-4 text-blue-400 flex-shrink-0" />
            
            {/* 名称（可编辑） */}
            {isEditingName ? (
              <input
                type="text"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                onBlur={handleSaveName}
                onKeyDown={(e) => {
                  e.stopPropagation();
                  if (e.key === "Enter") handleSaveName();
                  if (e.key === "Escape") {
                    setEditedName(block.name);
                    setIsEditingName(false);
                  }
                }}
                onClick={(e) => e.stopPropagation()}
                className="font-medium text-zinc-200 bg-surface-1 border border-surface-3 rounded px-2 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-brand-500 flex-1 min-w-0"
                autoFocus
              />
            ) : (
              <span 
                className="font-medium text-zinc-200 truncate cursor-text hover:text-brand-400 transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  setIsEditingName(true);
                }}
                title="点击编辑名称"
              >
                {block.name}
              </span>
            )}
            
              {/* 状态标签 */}
              <span className={`px-2 py-0.5 text-xs rounded flex-shrink-0 ${
                block.status === "completed" ? "bg-emerald-600/20 text-emerald-400" :
                block.status === "in_progress" ? "bg-amber-600/20 text-amber-400" :
                block.status === "failed" ? "bg-red-600/20 text-red-400" :
                "bg-zinc-700 text-zinc-400"
              }`}>
                {block.status === "completed" ? "已完成" :
                 block.status === "in_progress" ? "生成中" :
                 block.status === "failed" ? "失败" : "待处理"}
              </span>
          </div>
          
          {/* 快速操作按钮 */}
          <div className="flex items-center gap-1 flex-shrink-0 ml-2">
            {/* AI 提示词状态 */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowPromptModal(true);
              }}
              className={`p-1.5 rounded transition-colors ${
                savedPrompt 
                  ? "text-brand-400 hover:bg-brand-600/20" 
                  : "text-red-400 hover:bg-red-600/20"
              }`}
              title={savedPrompt ? "查看/编辑提示词" : "未配置提示词"}
            >
              <MessageSquarePlus className="w-4 h-4" />
            </button>
            
            {/* 依赖状态 */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowDependencyModal(true);
              }}
              className={`p-1.5 rounded transition-colors ${
                dependencyBlocks.length > 0 
                  ? "text-blue-400 hover:bg-blue-600/20" 
                  : "text-zinc-500 hover:bg-surface-3"
              }`}
              title={dependencyBlocks.length > 0 
                ? `依赖: ${dependencyBlocks.map(d => d.name).join(", ")}` 
                : "无依赖（点击配置）"}
            >
              <Workflow className="w-4 h-4" />
            </button>
            
            {/* 需要审核标记 */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleToggleNeedReview();
              }}
              className={`p-1.5 rounded transition-colors ${
                block.need_review 
                  ? "text-amber-400 hover:bg-amber-600/20" 
                  : "text-emerald-400 hover:bg-emerald-600/20"
              }`}
              title={block.need_review ? "需要人工确认（点击切换）" : "自动执行（点击切换）"}
            >
              {block.need_review ? <ShieldCheck className="w-4 h-4" /> : <Zap className="w-4 h-4" />}
            </button>

            {/* 自动生成标记：仅对有依赖的 field 类型块显示 */}
            {block.block_type === "field" && (block.depends_on || []).length > 0 && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleToggleAutoGenerate();
                }}
                className={`p-1.5 rounded transition-colors ${
                  block.auto_generate
                    ? "text-blue-400 hover:bg-blue-600/20"
                    : "text-zinc-500 hover:bg-surface-3"
                }`}
                title={block.auto_generate ? "自动生成（依赖就绪时自动触发，点击切换）" : "手动生成（点击切换为自动）"}
              >
                <Workflow className="w-4 h-4" />
              </button>
            )}

            {/* M5: 模型覆盖 */}
            <div data-model-selector>
              <button
                ref={modelBtnRef}
                onClick={(e) => {
                  e.stopPropagation();
                  handleToggleModelSelector();
                }}
                className={`p-1.5 rounded transition-colors ${
                  modelOverride
                    ? "text-purple-400 hover:bg-purple-600/20"
                    : "text-zinc-500 hover:bg-surface-3"
                }`}
                title={modelOverride ? `模型: ${modelOverride}` : "使用默认模型（点击切换）"}
              >
                <Cpu className="w-4 h-4" />
              </button>
            </div>
            
            {/* 生成按钮 */}
            {!isGenerating && (
              <button
                onClick={handleGenerate}
                disabled={!canGenerate}
                className={`p-1.5 rounded transition-colors ${
                  !canGenerate
                    ? "text-zinc-600 cursor-not-allowed"
                    : block.status === "completed"
                    ? "text-amber-400 hover:bg-amber-600/20"
                    : "text-brand-400 hover:bg-brand-600/20"
                }`}
                title={
                  !canGenerate
                    ? `依赖内容为空: ${unmetDependencies.map(d => d.name).join(", ")}`
                    : block.status === "completed" ? "重新生成" : "生成内容"
                }
              >
                {block.status === "completed" ? <RefreshCw className="w-4 h-4" /> : <Play className="w-4 h-4" />}
              </button>
            )}
            
            {isGenerating && (
              <button
                onClick={handleStopGeneration}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/30 rounded transition-colors"
                title="停止生成"
              >
                <Square className="w-3 h-3" />
                停止
              </button>
            )}

            {/* 版本历史按钮 */}
            {block.content && !isGenerating && (
              <VersionHistoryButton
                entityId={block.id}
                entityName={block.name}
                onRollback={() => onUpdate?.()}
              />
            )}
            
            {/* 删除按钮 */}
            <button
              onClick={handleDelete}
              className="p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-600/10 rounded transition-colors"
              title="删除"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
        
        {/* 简要信息行（始终显示） */}
        <div className="mt-2 flex items-center gap-3 text-xs text-zinc-500 flex-wrap">
          {/* AI 提示词预览 */}
          {block.ai_prompt && (
            <span className="truncate max-w-[200px]" title={block.ai_prompt}>
              💡 {block.ai_prompt.slice(0, 30)}...
            </span>
          )}
          
          {/* 依赖数量 */}
          {dependencyBlocks.length > 0 && (
            <span className="flex items-center gap-1">
              <Workflow className="w-3 h-3 inline" /> 依赖 {dependencyBlocks.length} 项
              {dependencyBlocks.some(d => d.status !== "completed") && (
                <span className="text-red-400">（未完成）</span>
              )}
            </span>
          )}
          
          {/* 需要审核 */}
          {block.need_review && (
            <span className="text-amber-400 flex items-center gap-1"><ShieldCheck className="w-3 h-3" /> 需确认</span>
          )}
        </div>
      </div>
      
      {/* 展开的详情区域 */}
      {isExpanded && (
        <div className="border-t border-surface-3">
          {/* 生成前提问区域 */}
          {hasPreQuestions && (
            <div className="p-4 bg-amber-900/10 border-b border-amber-600/20">
              <div className="flex items-center justify-between mb-3">
                <span className="text-amber-400 text-sm font-medium">生成前请先回答以下问题</span>
                <div className="flex items-center gap-2">
                  {preAnswersSaved && (
                    <span className="text-xs text-green-400">✓ 已保存</span>
                  )}
                  <button
                    onClick={handleSavePreAnswers}
                    disabled={isSavingPreAnswers}
                    className="px-3 py-1 text-xs bg-amber-600 hover:bg-amber-700 disabled:bg-amber-800 text-white rounded transition-colors"
                  >
                    {isSavingPreAnswers ? "保存中..." : "保存回答"}
                  </button>
                </div>
              </div>
              <div className="space-y-3">
                {block.pre_questions?.map((question, idx) => (
                  <div key={idx} className="space-y-1">
                    <label className="text-sm text-zinc-300">{idx + 1}. {question}</label>
                    <input
                      type="text"
                      value={preAnswers[question] || ""}
                      onChange={(e) => {
                        const newAnswers = { ...preAnswers, [question]: e.target.value };
                        setPreAnswers(newAnswers);
                        setPreAnswersSaved(false);
                      }}
                      className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                      placeholder="请输入您的答案..."
                    />
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs text-zinc-500">
                💡 填写完毕后请点击「保存回答」按钮，答案会作为生成内容的上下文传递给 AI
              </p>
            </div>
          )}
          
          {/* 内容区域 */}
          <div className="p-4">
            {isGenerating ? (
              /* 流式生成中 — 实时显示内容 */
              <div className="min-h-[80px]">
                <div className="prose prose-invert prose-sm max-w-none">
                  {generatingContent ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ table: ({ children, ...props }) => (<div className="table-wrapper"><table {...props}>{children}</table></div>) }}>{generatingContent}</ReactMarkdown>
                  ) : (
                    <p className="text-zinc-500 animate-pulse">正在生成内容...</p>
                  )}
                  <span className="inline-block w-2 h-4 bg-brand-500 animate-pulse ml-0.5" />
                </div>
              </div>
            ) : block.status === "in_progress" && !block.content ? (
              /* 后台生成中（用户导航离开后回来） */
              <div className="flex items-center gap-2 py-4 justify-center">
                <span className="inline-block w-2 h-4 bg-brand-500 animate-pulse" />
                <span className="text-sm text-brand-400 animate-pulse">后台生成中，请稍候...</span>
              </div>
            ) : isEditing ? (
              <div className="space-y-3">
                <textarea
                  value={editedContent}
                  onChange={(e) => setEditedContent(e.target.value)}
                  className="w-full bg-surface-1 border border-surface-3 rounded-lg p-3 text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none font-mono text-sm min-h-[150px]"
                  placeholder="在此编辑内容..."
                />
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => {
                      setEditedContent(block.content || "");
                      setIsEditing(false);
                    }}
                    className="px-3 py-1.5 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
                  >
                    取消
                  </button>
                  <button
                    onClick={handleSaveContent}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
                  >
                    <Save className="w-4 h-4" />
                    保存
                  </button>
                </div>
              </div>
            ) : (
              <div 
                className="min-h-[80px] cursor-pointer group"
                onClick={() => setIsEditing(true)}
              >
                {block.content ? (
                  <div className="relative">
                    <div className="absolute top-0 right-0 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleCopyContent(e); }}
                        className="flex items-center gap-1 px-2 py-1 text-xs bg-surface-3 text-zinc-400 hover:text-zinc-200 rounded"
                        title="复制全文（Markdown格式）"
                      >
                        {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
                        {copied ? "已复制" : "复制"}
                      </button>
                      <button 
                        onClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
                        className="flex items-center gap-1 px-2 py-1 text-xs bg-surface-3 text-zinc-400 hover:text-zinc-200 rounded"
                      >
                        <Pencil className="w-3 h-3" />
                        编辑
                      </button>
                    </div>
                    <div className="prose prose-invert prose-sm max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ table: ({ children, ...props }) => (<div className="table-wrapper"><table {...props}>{children}</table></div>) }}>{block.content}</ReactMarkdown>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-6 text-zinc-500 border-2 border-dashed border-surface-3 rounded-lg">
                    <Pencil className="w-6 h-6 mb-2 opacity-50" />
                    <p className="text-sm">点击此处编辑内容</p>
                    <p className="text-xs mt-1">或使用「生成」按钮让 AI 生成</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* AI 提示词编辑弹窗 */}
      {showPromptModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowPromptModal(false)}>
          <div className="w-full max-w-2xl bg-surface-1 border border-surface-3 rounded-xl shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-surface-3 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-zinc-200">编辑 AI 提示词 - {block.name}</h3>
              <button 
                onClick={() => setShowPromptModal(false)}
                className="p-1 text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <textarea
                value={editedPrompt}
                onChange={(e) => setEditedPrompt(e.target.value)}
                rows={8}
                className="w-full bg-surface-2 border border-surface-3 rounded-lg p-4 text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
                placeholder="输入 AI 生成此内容块时使用的提示词..."
              />
              <p className="text-xs text-zinc-500">
                提示词会与项目上下文（创作者特质、意图、用户画像）一起发送给 AI，用于生成内容。
              </p>

              {/* 🤖 用 AI 生成提示词 */}
              <div className="p-3 bg-surface-2/50 border border-surface-3 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs text-zinc-400">🤖 用 AI 生成提示词</span>
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={aiPromptPurpose}
                    onChange={(e) => setAiPromptPurpose(e.target.value)}
                    placeholder="简述内容块目的，如：介绍产品核心卖点"
                    className="flex-1 px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && aiPromptPurpose.trim() && !generatingPrompt) {
                        handleGeneratePrompt();
                      }
                    }}
                  />
                  <button
                    onClick={handleGeneratePrompt}
                    disabled={!aiPromptPurpose.trim() || generatingPrompt}
                    className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white text-sm rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5 whitespace-nowrap"
                  >
                    {generatingPrompt ? (
                      <>
                        <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                        生成中...
                      </>
                    ) : "AI 生成"}
                  </button>
                </div>
              </div>
            </div>
            <div className="px-5 py-4 border-t border-surface-3 flex justify-end gap-3">
              <button
                onClick={() => setShowPromptModal(false)}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
              >
                取消
              </button>
              <button
                onClick={handleSavePrompt}
                className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 依赖选择弹窗 */}
      {showDependencyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowDependencyModal(false)}>
          <div className="w-full max-w-lg bg-surface-1 border border-surface-3 rounded-xl shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-surface-3 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-zinc-200">设置依赖 - {block.name}</h3>
              <button 
                onClick={() => setShowDependencyModal(false)}
                className="p-1 text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5">
              <p className="text-sm text-zinc-400 mb-4">
                选择「{block.name}」依赖的内容块。只有依赖的内容块完成后，才能生成此内容。
              </p>
              
              {availableDependencies.length > 0 ? (
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {availableDependencies.map(dep => (
                    <label
                      key={dep.id}
                      className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                        selectedDependencies.includes(dep.id)
                          ? "bg-brand-600/20 border border-brand-500/50"
                          : "bg-surface-2 border border-surface-3 hover:bg-surface-3"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedDependencies.includes(dep.id)}
                        onChange={() => toggleDependency(dep.id)}
                        className="w-4 h-4 rounded border-surface-4 bg-surface-2 text-brand-600 focus:ring-brand-500"
                      />
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-zinc-200">{dep.name}</span>
                          {dep.special_handler && (
                            <span className="px-1.5 py-0.5 text-xs rounded bg-purple-600/20 text-purple-400">
                              {dep.special_handler === "intent" ? "意图分析" :
                               dep.special_handler === "research" ? "消费者调研" :
                               dep.special_handler === "evaluate" ? "评估结果" : dep.special_handler}
                            </span>
                          )}
                          <span className={`px-1.5 py-0.5 text-xs rounded ${
                            dep.status === "completed"
                              ? "bg-emerald-600/20 text-emerald-400"
                              : (dep.content && dep.content.trim() !== "")
                              ? "bg-amber-600/20 text-amber-400"
                              : "bg-zinc-700 text-zinc-400"
                          }`}>
                            {dep.status === "completed" ? "已完成" : (dep.content && dep.content.trim() !== "") ? "待确认" : "未完成"}
                          </span>
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-zinc-500">
                  暂无可选的依赖内容块
                </div>
              )}
            </div>
            <div className="px-5 py-4 border-t border-surface-3 flex justify-end gap-3">
              <button
                onClick={() => {
                  setSelectedDependencies(block.depends_on || []);
                  setShowDependencyModal(false);
                }}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
              >
                取消
              </button>
              <button
                onClick={handleSaveDependencies}
                className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* M5: 模型选择器下拉菜单 — 用 fixed 定位脱离 overflow-hidden 裁剪 */}
      {showModelSelector && (
        <div
          className="fixed z-[100] w-56 bg-surface-1 border border-surface-3 rounded-lg shadow-xl"
          style={{ top: modelDropdownPos.top, left: modelDropdownPos.left }}
          data-model-selector
          onClick={(e) => e.stopPropagation()}
        >
          <div className="p-2 border-b border-surface-3">
            <p className="text-xs text-zinc-500">为「{block.name}」选择模型</p>
          </div>
          <div className="max-h-48 overflow-y-auto">
            <button
              onClick={() => handleSaveModelOverride("")}
              className={`w-full text-left px-3 py-2 text-xs hover:bg-surface-3 transition-colors ${
                !modelOverride ? "text-brand-400 bg-brand-600/10" : "text-zinc-300"
              }`}
            >
              跟随全局默认
            </button>
            {availableModels.map((m) => (
              <button
                key={m.id}
                onClick={() => handleSaveModelOverride(m.id)}
                className={`w-full text-left px-3 py-2 text-xs hover:bg-surface-3 transition-colors ${
                  modelOverride === m.id ? "text-brand-400 bg-brand-600/10" : "text-zinc-300"
                }`}
              >
                <span>{m.name}</span>
                <span className="ml-2 text-zinc-600">{m.provider}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
