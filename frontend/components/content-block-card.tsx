// frontend/components/content-block-card.tsx
// 功能: 紧凑版 ContentBlock 卡片，用于阶段视图中显示字段的所有设置
// 支持不同类型：phase（阶段）显示子节点数量和进入按钮，field（字段）显示完整编辑功能
// 包含：名称、状态、AI提示词、依赖、约束、need_review、auto_generate、模型覆盖(M5)、生成/编辑/删除按钮
// 编辑入口: 仅 hover 编辑按钮 + 空内容区域点击，已移除内容区域单击进入编辑

"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { blockAPI, modelsAPI } from "@/lib/api";
import { useBlockGeneration } from "@/lib/hooks/useBlockGeneration";
import type { ContentBlock, ModelInfo } from "@/lib/api";
import type { PreQuestion } from "@/lib/preQuestions";
import { useUiIsJa } from "@/lib/ui-locale";
import {
  countAnsweredPreQuestions,
  countAnsweredRequiredPreQuestions,
  countMissingRequiredPreQuestions,
  createPreQuestion,
  normalizePreAnswers,
  normalizePreQuestions,
} from "@/lib/preQuestions";
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
  Copy,
  Check,
  Cpu,
  Sparkles,
} from "lucide-react";

interface ContentBlockCardProps {
  block: ContentBlock;
  projectId: string;
  projectLocale?: string | null;
  allBlocks?: ContentBlock[];  // 用于依赖选择
  onUpdate?: () => void;
  onBlockUpdated?: (block: ContentBlock) => void;
  onSelect?: () => void;  // 点击选中此块（用于进入子组/分组）
}

function getBlockStatusLabel(status: string, isJa: boolean, needsRegeneration = false) {
  if (needsRegeneration) return isJa ? "再生成待ち" : "待重生成";
  if (status === "completed") return isJa ? "完了" : "已完成";
  if (status === "in_progress") return isJa ? "生成中" : "生成中";
  if (status === "failed") return isJa ? "失敗" : "失败";
  return isJa ? "待機中" : "待处理";
}

function getBlockStatusClass(status: string, needsRegeneration = false) {
  if (needsRegeneration) return "bg-sky-600/20 text-sky-400";
  if (status === "completed") return "bg-emerald-600/20 text-emerald-400";
  if (status === "in_progress") return "bg-amber-600/20 text-amber-400";
  if (status === "failed") return "bg-red-600/20 text-red-400";
  return "bg-zinc-700 text-zinc-400";
}

export function ContentBlockCard({ 
  block, 
  projectId, 
  projectLocale,
  allBlocks = [], 
  onUpdate,
  onBlockUpdated,
  onSelect 
}: ContentBlockCardProps) {
  // P0-1: 统一使用 blockAPI（已移除 fieldAPI/isVirtual 分支）
  const isJa = useUiIsJa(projectLocale);
  
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
  const [preQuestions, setPreQuestions] = useState<PreQuestion[]>(normalizePreQuestions(block.pre_questions || []));
  const [preAnswers, setPreAnswers] = useState<Record<string, string>>(
    normalizePreAnswers(block.pre_answers || {}, normalizePreQuestions(block.pre_questions || [])),
  );
  const [isSavingPreAnswers, setIsSavingPreAnswers] = useState(false);
  const [preAnswersSaved, setPreAnswersSaved] = useState(false);
  const [preQuestionsExpanded, setPreQuestionsExpanded] = useState(false);
  const hasPreQuestions = preQuestions.length > 0;
  const showPreQuestionsSection = block.block_type === "field";
  const [newPreQuestion, setNewPreQuestion] = useState("");
  const answeredPreQuestionCount = countAnsweredPreQuestions(preQuestions, preAnswers);
  const answeredRequiredPreQuestionCount = countAnsweredRequiredPreQuestions(preQuestions, preAnswers);
  const requiredPreQuestionCount = preQuestions.filter((item) => item.required).length;
  const missingRequiredPreQuestionCount = countMissingRequiredPreQuestions(preQuestions, preAnswers);

  // M5: 模型覆盖
  const [modelOverride, setModelOverride] = useState<string>(block.model_override || "");
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [showModelSelector, setShowModelSelector] = useState(false);
  const modelBtnRef = useRef<HTMLButtonElement>(null);
  const [modelDropdownPos, setModelDropdownPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const pollStatusRef = useRef(block.status);
  const pollUpdatedAtRef = useRef(block.updated_at || "");

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
    isGenerating, generatingContent, canGenerate, unmetDependencies, missingPrompt,
    handleGenerate: _handleGenerate, handleStop: _handleStop,
  } = useBlockGeneration({
    block, projectId, projectLocale, allBlocks,
    preQuestions,
    preAnswers, hasPreQuestions,
    onUpdate,
    onContentReady: (content) => setEditedContent(content),
  });

  const handleGenerate = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsExpanded(true); // Card 特有：自动展开显示生成内容
    setIsEditing(false);
    await _handleGenerate();
  };

  const handleStopGeneration = (e: React.MouseEvent) => {
    e.stopPropagation();
    _handleStop();
  };

  const onUpdateRef = useRef(onUpdate);
  const onBlockUpdatedRef = useRef(onBlockUpdated);

  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);

  useEffect(() => {
    onBlockUpdatedRef.current = onBlockUpdated;
  }, [onBlockUpdated]);

  const applyUpdatedBlock = useCallback((updatedBlock: ContentBlock, refreshTree = false) => {
    onBlockUpdatedRef.current?.(updatedBlock);
    if (refreshTree) {
      onUpdateRef.current?.();
    }
    return updatedBlock;
  }, []);

  const updateCurrentBlock = useCallback(async (
    payload: Parameters<typeof blockAPI.update>[1],
    options?: { refreshTree?: boolean },
  ) => {
    const updatedBlock = await blockAPI.update(block.id, payload);
    return applyUpdatedBlock(updatedBlock, options?.refreshTree ?? false);
  }, [applyUpdatedBlock, block.id]);

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
      const normalizedQuestions = normalizePreQuestions(preQuestions);
      const normalizedAnswers: Record<string, string> = {};
      for (const question of normalizedQuestions) {
        const value = (preAnswers[question.id] || "").trim();
        if (value) {
          normalizedAnswers[question.id] = value;
        }
      }
      const updatedBlock = await updateCurrentBlock({
        pre_questions: normalizedQuestions,
        pre_answers: normalizedAnswers,
      });
      setPreQuestions(normalizePreQuestions(updatedBlock.pre_questions || []));
      setPreAnswers(normalizePreAnswers(updatedBlock.pre_answers || {}, updatedBlock.pre_questions || []));
      setPreAnswersSaved(true);
      setTimeout(() => setPreAnswersSaved(false), 2000);
    } catch (err) {
      console.error("保存答案失败:", err);
      alert((isJa ? "保存に失敗しました: " : "保存失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
    } finally {
      setIsSavingPreAnswers(false);
    }
  };
  
  // 可选的依赖（排除自己和自己的子节点）
  const availableDependencies = allBlocks.filter(b => {
    if (b.id === block.id) return false;
    if (b.parent_id === block.id) return false;
    return b.block_type === "field";
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
    const normalizedQuestions = normalizePreQuestions(block.pre_questions || []);
    setPreQuestions(normalizedQuestions);
    setPreAnswers(normalizePreAnswers(block.pre_answers || {}, normalizedQuestions));
    // M5: 同步 model_override
    setModelOverride(block.model_override || "");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block.id, block.content, block.name, block.ai_prompt, block.depends_on, block.pre_answers, block.pre_questions, block.model_override, block.updated_at]);

  useEffect(() => {
    pollStatusRef.current = block.status;
    pollUpdatedAtRef.current = block.updated_at || "";
  }, [block.status, block.updated_at, block.needs_regeneration]);

  const handleAddPreQuestion = (required = false) => {
    const question = newPreQuestion.trim();
    if (!question) return;
    if (preQuestions.some((item) => item.question === question)) return;
    setPreQuestions((prev) => [...prev, createPreQuestion(question, required)]);
    setNewPreQuestion("");
    setPreAnswersSaved(false);
  };

  const handleRemovePreQuestion = (questionId: string) => {
    setPreQuestions((prev) => prev.filter((item) => item.id !== questionId));
    setPreAnswers((prev) => {
      const next = { ...prev };
      delete next[questionId];
      return next;
    });
    setPreAnswersSaved(false);
  };

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
      const updatedBlock = await updateCurrentBlock({ model_override: modelId });
      setModelOverride(updatedBlock.model_override || "");
      setShowModelSelector(false);
      sendNotification(modelId ? (isJa ? `モデルを設定しました: ${modelId}` : `已设置模型: ${modelId}`) : (isJa ? "既定モデルに戻しました" : "已恢复为默认模型"), "success");
    } catch (err: unknown) {
      console.error("保存模型覆盖失败:", err);
      sendNotification((isJa ? "モデルの保存に失敗しました: " : "保存模型失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")), "error");
    }
  };

  // 后端会自动调度依赖更新链；当前块如果正在自动重生成或等待被自动重生成，则轮询刷新。
  useEffect(() => {
    if ((block.status === "in_progress" || (block.auto_generate && block.needs_regeneration)) && !isGenerating) {
      const pollInterval = setInterval(async () => {
        try {
          const fresh = await blockAPI.get(block.id);
          if (fresh.status !== pollStatusRef.current || (fresh.updated_at || "") !== pollUpdatedAtRef.current) {
            onBlockUpdatedRef.current?.(fresh);
            onUpdateRef.current?.();
          }
        } catch {
          // 静默忽略轮询错误
        }
      }, 2000);
      return () => clearInterval(pollInterval);
    }
  }, [block.auto_generate, block.id, block.needs_regeneration, block.status, isGenerating]);

  // 保存名称
  const handleSaveName = async () => {
    if (editedName.trim() && editedName !== block.name) {
      try {
        const updatedBlock = await updateCurrentBlock({ name: editedName.trim() });
        setEditedName(updatedBlock.name);
      } catch (err) {
        console.error("更新名称失败:", err);
        alert((isJa ? "名前の更新に失敗しました: " : "更新名称失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
        setEditedName(block.name);
      }
    }
    setIsEditingName(false);
  };

  // 保存内容
  const handleSaveContent = async () => {
    try {
      const updatedBlock = await updateCurrentBlock({ content: editedContent }, { refreshTree: true });
      setIsEditing(false);
      setEditedContent(updatedBlock.content || "");
    } catch (err) {
      console.error("保存失败:", err);
      alert((isJa ? "保存に失敗しました: " : "保存失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
    }
  };

  // 保存 AI 提示词
  const handleSavePrompt = async () => {
    try {
      const updatedBlock = await updateCurrentBlock({
        ai_prompt: editedPrompt,
      });
      setEditedPrompt(updatedBlock.ai_prompt || "");
      setSavedPrompt(updatedBlock.ai_prompt || "");
      setShowPromptModal(false);
    } catch (err) {
      console.error("保存提示词失败:", err);
      alert((isJa ? "プロンプトの保存に失敗しました: " : "保存提示词失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
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
      alert((isJa ? "プロンプト生成に失敗しました: " : "生成提示词失败: ") + (e instanceof Error ? e.message : (isJa ? "不明なエラー" : "未知错误")));
    } finally {
      setGeneratingPrompt(false);
    }
  };

  // 保存依赖
  const handleSaveDependencies = async () => {
    try {
      const updatedBlock = await updateCurrentBlock({ depends_on: selectedDependencies });
      setSelectedDependencies(updatedBlock.depends_on || []);
      setShowDependencyModal(false);
    } catch (err) {
      console.error("保存依赖失败:", err);
      alert((isJa ? "依存関係の保存に失敗しました: " : "保存依赖失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
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
    if (!confirm(isJa ? `「${block.name}」を削除しますか？この操作は元に戻せません。` : `确定要删除「${block.name}」吗？此操作不可撤销。`)) return;
    try {
      await blockAPI.delete(block.id);
      onUpdate?.();
    } catch (err) {
      console.error("删除失败:", err);
      alert((isJa ? "削除に失敗しました: " : "删除失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
    }
  };

  // 切换 need_review 状态
  const handleToggleNeedReview = async () => {
    try {
      await updateCurrentBlock({ need_review: !block.need_review }, { refreshTree: true });
    } catch (err) {
      console.error("切换审核状态失败:", err);
    }
  };

  // 切换 auto_generate 状态
  const handleToggleAutoGenerate = async () => {
    try {
      await updateCurrentBlock({ auto_generate: !block.auto_generate });
    } catch (err) {
      console.error("切换自动生成失败:", err);
    }
  };

  // 判断是否是容器类型（分组）
  const isContainer = block.block_type === "group";
  const childCount = block.children?.length || 0;
  
  // 容器类型的图标
  const getContainerIcon = () => {
    if (block.block_type === "group") {
      return isExpanded ? <FolderOpen className="w-4 h-4 text-amber-400" /> : <Folder className="w-4 h-4 text-amber-400" />;
    }
    return <FileText className="w-4 h-4 text-blue-400" />;
  };

  // ========== 容器类型（分组）的渲染 ==========
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
              <span className="px-2 py-0.5 text-xs rounded flex-shrink-0 bg-amber-600/20 text-amber-400">
                {isJa ? "子グループ" : "子组"}
              </span>
              
              {/* 子节点数量 */}
              {childCount > 0 && (
                <span className="text-xs text-zinc-500">
                  {isJa ? `${childCount} 件を含む` : `包含 ${childCount} 项`}
                </span>
              )}
              
              {/* 状态标签 */}
              <span className={`px-2 py-0.5 text-xs rounded flex-shrink-0 ${getBlockStatusClass(block.status, block.needs_regeneration)}`}>
                {getBlockStatusLabel(block.status, isJa, block.needs_regeneration)}
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
                title={isJa ? "削除" : "删除"}
              >
                <Trash2 className="w-4 h-4" />
              </button>
              <span className="text-zinc-500 text-sm flex items-center gap-1">
                {isJa ? "クリックして開く" : "点击进入"}
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
      "intent_analysis": { icon: "💬", title: isJa ? "意図分析" : "意图分析", desc: isJa ? "Agent との対話で完了します。クリックして内容ブロックを開いてください" : "由 Agent 通过对话完成，请点击进入内容块查看" },
      "intent": { icon: "💬", title: isJa ? "意図分析" : "意图分析", desc: isJa ? "Agent との対話で完了します。クリックして内容ブロックを開いてください" : "由 Agent 通过对话完成，请点击进入内容块查看" },
      "consumer_research": { icon: "🔍", title: isJa ? "顧客調査" : "消费者调研", desc: isJa ? "DeepResearch の結果と顧客ペルソナを含みます" : "包含 DeepResearch 调研结果和消费者画像" },
      "research": { icon: "🔍", title: isJa ? "顧客調査" : "消费者调研", desc: isJa ? "DeepResearch の結果と顧客ペルソナを含みます" : "包含 DeepResearch 调研结果和消费者画像" },
      "consumer_simulation": { icon: "🎭", title: isJa ? "顧客シミュレーション" : "消费者模拟", desc: isJa ? "顧客体験とフィードバックをシミュレートします" : "模拟消费者体验和反馈" },
      "simulate": { icon: "🎭", title: isJa ? "顧客シミュレーション" : "消费者模拟", desc: isJa ? "顧客体験とフィードバックをシミュレートします" : "模拟消费者体验和反馈" },
    };
    const info = specialLabels[specialHandler] || { icon: "⚡", title: specialHandler, desc: isJa ? "特殊処理用の内容ブロック" : "特殊处理内容块" };
    
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
              <span className={`px-2 py-0.5 text-xs rounded flex-shrink-0 ${getBlockStatusClass(block.status, block.needs_regeneration)}`}>
                {getBlockStatusLabel(block.status, isJa, block.needs_regeneration)}
              </span>
            </div>
            <span className="text-zinc-500 text-sm flex items-center gap-1 flex-shrink-0">
              {isJa ? "クリックして開く" : "点击进入"}
              <ChevronRight className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-1.5 text-xs text-zinc-500 pl-8">
            {info.desc}
          </div>
          {block.content && (
            <div className="mt-1 text-xs text-emerald-500 pl-8">
              {isJa ? "✓ 内容あり" : "✓ 已有内容"}
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
                title={isJa ? "クリックして名前を編集" : "点击编辑名称"}
              >
                {block.name}
              </span>
            )}
            
              {/* 状态标签 */}
              <span className={`px-2 py-0.5 text-xs rounded flex-shrink-0 ${getBlockStatusClass(block.status, block.needs_regeneration)}`}>
                {getBlockStatusLabel(block.status, isJa, block.needs_regeneration)}
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
              title={savedPrompt ? (isJa ? "プロンプトを表示 / 編集" : "查看/编辑提示词") : (isJa ? "プロンプト未設定" : "未配置提示词")}
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
                ? `${isJa ? "依存" : "依赖"}: ${dependencyBlocks.map(d => d.name).join(", ")}` 
                : (isJa ? "依存なし（クリックして設定）" : "无依赖（点击配置）")}
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
              title={block.need_review ? (isJa ? "手動確認が必要（クリックで切替）" : "需要人工确认（点击切换）") : (isJa ? "確認不要（クリックで切替）" : "无需确认（点击切换）")}
            >
              {block.need_review ? <ShieldCheck className="w-4 h-4" /> : <Zap className="w-4 h-4" />}
            </button>

            {/* 自动生成标记：所有 field 类型块均可切换 */}
            {block.block_type === "field" && (
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
                title={block.auto_generate ? (isJa ? "自動生成（依存準備完了で自動実行、クリックで切替）" : "自动生成（依赖就绪时自动触发，点击切换）") : (isJa ? "手動実行（クリックで自動生成へ切替）" : "手动触发（点击切换为自动生成）")}
              >
                <Sparkles className="w-4 h-4" />
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
                title={modelOverride ? `${isJa ? "モデル" : "模型"}: ${modelOverride}` : (isJa ? "既定モデルを使用（クリックで切替）" : "使用默认模型（点击切换）")}
              >
                <Cpu className="w-4 h-4" />
              </button>
            </div>
            
            {/* 生成/重新生成按钮：有内容显示 RefreshCw（重新生成），无内容显示 Play（首次生成） */}
            {!isGenerating && (
              <button
                onClick={handleGenerate}
                disabled={!canGenerate}
                className={`p-1.5 rounded transition-colors ${
                  !canGenerate
                    ? "text-zinc-600 cursor-not-allowed"
                    : block.content
                    ? "text-amber-400 hover:bg-amber-600/20"
                    : "text-brand-400 hover:bg-brand-600/20"
                }`}
                title={
                  !canGenerate
                    ? missingPrompt
                      ? (isJa ? "プロンプト未設定" : "未配置提示词")
                      : unmetDependencies.length > 0
                      ? `${isJa ? "依存内容が未準備です" : "依赖内容未就绪"}: ${unmetDependencies.map(d => d.name).join(", ")}`
                      : (isJa ? "必須ヒアリング未回答" : "必答提问未回答")
                    : block.content ? (isJa ? "再生成" : "重新生成") : (isJa ? "内容を生成" : "生成内容")
                }
              >
                {block.content ? <RefreshCw className="w-4 h-4" /> : <Play className="w-4 h-4" />}
              </button>
            )}
            
            {isGenerating && (
              <button
                onClick={handleStopGeneration}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/30 rounded transition-colors"
                title={isJa ? "生成を停止" : "停止生成"}
              >
                <Square className="w-3 h-3" />
                {isJa ? "停止" : "停止"}
              </button>
            )}

            {/* 版本历史按钮 */}
            {block.content && !isGenerating && (
              <VersionHistoryButton
                entityId={block.id}
                entityName={block.name}
                projectLocale={projectLocale}
                onRollback={() => onUpdate?.()}
              />
            )}
            
            {/* 删除按钮 */}
            <button
              onClick={handleDelete}
              className="p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-600/10 rounded transition-colors"
              title={isJa ? "削除" : "删除"}
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
              <Workflow className="w-3 h-3 inline" /> {isJa ? `依存 ${dependencyBlocks.length} 件` : `依赖 ${dependencyBlocks.length} 项`}
              {dependencyBlocks.some(d => d.status !== "completed") && (
                <span className="text-red-400">{isJa ? "（未完了）" : "（未完成）"}</span>
              )}
            </span>
          )}
          
          {/* 需要审核 */}
          {block.need_review && (
            <span className="text-amber-400 flex items-center gap-1"><ShieldCheck className="w-3 h-3" /> {isJa ? "確認必要" : "需确认"}</span>
          )}
        </div>
      </div>
      
      {/* 展开的详情区域 */}
      {isExpanded && (
        <div className="border-t border-surface-3">
          {/* 生成前提问区域 */}
          {showPreQuestionsSection && (
            <div className="bg-amber-900/10 border-b border-amber-600/20">
              <button
                onClick={() => setPreQuestionsExpanded((v) => !v)}
                className="w-full flex items-center justify-between px-4 py-3 text-left"
              >
                <span className="text-amber-400 text-sm font-medium flex items-center gap-1.5">
                  {preQuestionsExpanded
                    ? <ChevronDown className="w-3.5 h-3.5" />
                    : <ChevronRight className="w-3.5 h-3.5" />}
                  {hasPreQuestions
                    ? (isJa
                      ? `生成前ヒアリング（必須 ${answeredRequiredPreQuestionCount}/${requiredPreQuestionCount}、全回答 ${answeredPreQuestionCount}/${preQuestions.length}）`
                      : `生成前提问（必答 ${answeredRequiredPreQuestionCount}/${requiredPreQuestionCount}，全部已答 ${answeredPreQuestionCount}/${preQuestions.length}）`)
                    : (isJa ? "生成前ヒアリング" : "生成前提问")}
                </span>
                {preAnswersSaved && (
                  <span className="text-xs text-green-400">{isJa ? "✓ 保存済み" : "✓ 已保存"}</span>
                )}
              </button>
              {preQuestionsExpanded && (
                <div className="px-4 pb-4">
                  <div className="flex justify-end mb-3">
                    <button
                      onClick={handleSavePreAnswers}
                      disabled={isSavingPreAnswers}
                      className="px-3 py-1 text-xs bg-amber-600 hover:bg-amber-700 disabled:bg-amber-800 text-white rounded transition-colors"
                    >
                      {isSavingPreAnswers ? (isJa ? "保存中..." : "保存中...") : (isJa ? "回答を保存" : "保存回答")}
                    </button>
                  </div>
                  <div className="space-y-3">
                    {hasPreQuestions ? (
                      preQuestions.map((question, idx) => (
                        <div key={question.id} className="space-y-2 rounded-lg border border-amber-500/15 bg-surface-1/60 p-3">
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={question.question}
                              onChange={(e) => {
                                const nextQuestion = e.target.value;
                                setPreQuestions((prev) => prev.map((item) => (
                                  item.id === question.id
                                    ? { ...item, question: nextQuestion }
                                    : item
                                )));
                                setPreAnswersSaved(false);
                              }}
                              placeholder={isJa ? `${idx + 1}. 質問を入力` : `${idx + 1}. 输入问题`}
                              className="flex-1 rounded border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                            />
                            <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                              <input
                                type="checkbox"
                                checked={question.required}
                                onChange={(e) => {
                                  setPreQuestions((prev) => prev.map((item) => (
                                    item.id === question.id
                                      ? { ...item, required: e.target.checked }
                                      : item
                                  )));
                                  setPreAnswersSaved(false);
                                }}
                              />
                              {isJa ? "必須" : "必答"}
                            </label>
                            <button
                              onClick={() => handleRemovePreQuestion(question.id)}
                              className="px-2 py-0.5 text-xs bg-red-600/20 text-red-300 rounded hover:bg-red-600/30"
                            >
                              {isJa ? "削除" : "删除"}
                            </button>
                          </div>
                          <input
                            type="text"
                            value={preAnswers[question.id] || ""}
                            onChange={(e) => {
                              const newAnswers = { ...preAnswers, [question.id]: e.target.value };
                              setPreAnswers(newAnswers);
                              setPreAnswersSaved(false);
                            }}
                            className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                            placeholder={question.required ? (isJa ? "必須質問への回答を入力してください..." : "请输入必答问题的回答...") : (isJa ? "任意回答: 空欄可" : "选答：可留空")}
                          />
                        </div>
                      ))
                    ) : (
                      <div className="rounded-lg border border-dashed border-amber-500/30 bg-surface-1/60 px-4 py-3 text-sm text-zinc-500">
                        {isJa ? "生成前ヒアリングはまだありません。先に質問を追加し、回答を保存すると、生成時にそれらが文脈へ入ります。" : "还没有生成前提问。你可以先添加问题，再保存回答，生成时这些问答会进入上下文。"}
                      </div>
                    )}
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <input
                      type="text"
                      value={newPreQuestion}
                      onChange={(e) => setNewPreQuestion(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          handleAddPreQuestion();
                        }
                      }}
                      className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                      placeholder={isJa ? "生成前ヒアリングを追加..." : "新増生成前提问..."}
                    />
                    <button
                      onClick={() => handleAddPreQuestion(false)}
                      className="px-3 py-2 text-xs bg-surface-3 text-zinc-200 rounded hover:bg-surface-4"
                    >
                      {isJa ? "任意質問を追加" : "添加选答题"}
                    </button>
                    <button
                      onClick={() => handleAddPreQuestion(true)}
                      className="px-3 py-2 text-xs bg-amber-600/80 text-white rounded hover:bg-amber-600"
                    >
                      {isJa ? "必須質問を追加" : "添加必答题"}
                    </button>
                  </div>
                  <p className="mt-3 text-xs text-zinc-500">
                    {missingRequiredPreQuestionCount > 0
                      ? (isJa ? `必須質問があと ${missingRequiredPreQuestionCount} 件未回答です。必須質問が残っていると「すべて開始」と手動生成を実行できません。` : `还有 ${missingRequiredPreQuestionCount} 个必答问题未回答；必答题会阻止"全部开始"和手动生成。`)
                      : (isJa ? "入力後は「回答を保存」をクリックしてください。回答は生成内容の文脈として AI に渡されます。任意質問は空欄でも構いません。" : "填写完毕后请点击「保存回答」按钮，答案会作为生成内容的上下文传递给 AI；选答题可留空。")}
                  </p>
                </div>
              )}
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
                    <p className="text-zinc-500 animate-pulse">{isJa ? "内容を生成中..." : "正在生成内容..."}</p>
                  )}
                  <span className="inline-block w-2 h-4 bg-brand-500 animate-pulse ml-0.5" />
                </div>
              </div>
            ) : block.status === "in_progress" && !block.content ? (
              /* 后台生成中（用户导航离开后回来） */
              <div className="flex items-center gap-2 py-4 justify-center">
                <span className="inline-block w-2 h-4 bg-brand-500 animate-pulse" />
                <span className="text-sm text-brand-400 animate-pulse">{isJa ? "バックグラウンドで生成中です。しばらくお待ちください..." : "后台生成中，请稍候..."}</span>
              </div>
            ) : isEditing ? (
              <div className="space-y-3">
                <textarea
                  value={editedContent}
                  onChange={(e) => setEditedContent(e.target.value)}
                  className="w-full bg-surface-1 border border-surface-3 rounded-lg p-3 text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none font-mono text-sm min-h-[150px]"
                  placeholder={isJa ? "ここで内容を編集..." : "在此编辑内容..."}
                />
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => {
                      setEditedContent(block.content || "");
                      setIsEditing(false);
                    }}
                    className="px-3 py-1.5 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
                  >
                    {isJa ? "キャンセル" : "取消"}
                  </button>
                  <button
                    onClick={handleSaveContent}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
                  >
                    <Save className="w-4 h-4" />
                    {isJa ? "保存" : "保存"}
                  </button>
                </div>
              </div>
            ) : (
              <div 
                className="min-h-[80px] group"
              >
                {block.content ? (
                  <div className="relative">
                    <div className="absolute top-0 right-0 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleCopyContent(e); }}
                        className="flex items-center gap-1 px-2 py-1 text-xs bg-surface-3 text-zinc-400 hover:text-zinc-200 rounded"
                        title={isJa ? "全文をコピー（Markdown 形式）" : "复制全文（Markdown格式）"}
                      >
                        {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
                        {copied ? (isJa ? "コピー済み" : "已复制") : (isJa ? "コピー" : "复制")}
                      </button>
                      <button 
                        onClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
                        className="flex items-center gap-1 px-2 py-1 text-xs bg-surface-3 text-zinc-400 hover:text-zinc-200 rounded"
                      >
                        <Pencil className="w-3 h-3" />
                        {isJa ? "編集" : "编辑"}
                      </button>
                    </div>
                    <div className="prose prose-invert prose-sm max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ table: ({ children, ...props }) => (<div className="table-wrapper"><table {...props}>{children}</table></div>) }}>{block.content}</ReactMarkdown>
                    </div>
                  </div>
                ) : (
                  <div
                    className="flex flex-col items-center justify-center py-6 text-zinc-500 border-2 border-dashed border-surface-3 rounded-lg cursor-pointer"
                    onClick={() => setIsEditing(true)}
                  >
                    <Pencil className="w-6 h-6 mb-2 opacity-50" />
                    <p className="text-sm">{isJa ? "ここをクリックして内容を編集" : "点击此处编辑内容"}</p>
                    <p className="text-xs mt-1">{isJa ? "または「生成」ボタンで AI に生成させてください" : "或使用「生成」按钮让 AI 生成"}</p>
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
              <h3 className="text-lg font-semibold text-zinc-200">{isJa ? `AI プロンプトを編集 - ${block.name}` : `编辑 AI 提示词 - ${block.name}`}</h3>
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
                placeholder={isJa ? "この内容ブロック生成時に使う AI プロンプトを入力..." : "输入 AI 生成此内容块时使用的提示词..."}
              />
              <p className="text-xs text-zinc-500">
                {isJa ? "このプロンプトはプロジェクト文脈（クリエイター特性、意図、ユーザーペルソナ）と一緒に AI へ送られ、内容生成に使われます。" : "提示词会与项目上下文（创作者特质、意图、用户画像）一起发送给 AI，用于生成内容。"}
              </p>

              {/* 🤖 用 AI 生成提示词 */}
              <div className="p-3 bg-surface-2/50 border border-surface-3 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs text-zinc-400">{isJa ? "🤖 AI でプロンプトを生成" : "🤖 用 AI 生成提示词"}</span>
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={aiPromptPurpose}
                    onChange={(e) => setAiPromptPurpose(e.target.value)}
                    placeholder={isJa ? "内容ブロックの目的を簡潔に説明。例: 商品の主要価値を紹介する" : "简述内容块目的，如：介绍产品核心卖点"}
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
                        {isJa ? "生成中..." : "生成中..."}
                      </>
                    ) : (isJa ? "AI 生成" : "AI 生成")}
                  </button>
                </div>
              </div>
            </div>
            <div className="px-5 py-4 border-t border-surface-3 flex justify-end gap-3">
              <button
                onClick={() => setShowPromptModal(false)}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
              >
                {isJa ? "キャンセル" : "取消"}
              </button>
              <button
                onClick={handleSavePrompt}
                className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg"
              >
                {isJa ? "保存" : "保存"}
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
              <h3 className="text-lg font-semibold text-zinc-200">{isJa ? `依存関係を設定 - ${block.name}` : `设置依赖 - ${block.name}`}</h3>
              <button 
                onClick={() => setShowDependencyModal(false)}
                className="p-1 text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5">
              <p className="text-sm text-zinc-400 mb-4">
                {isJa ? `「${block.name}」が依存する内容ブロックを選択します。依存先が完了してからこの内容を生成できます。` : `选择「${block.name}」依赖的内容块。只有依赖的内容块完成后，才能生成此内容。`}
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
                              {dep.special_handler === "intent" ? (isJa ? "意図分析" : "意图分析") :
                               dep.special_handler === "research" ? (isJa ? "顧客調査" : "消费者调研") :
                               dep.special_handler === "evaluate" ? (isJa ? "評価結果" : "评估结果") : dep.special_handler}
                            </span>
                          )}
                          <span className={`px-1.5 py-0.5 text-xs rounded ${
                            dep.status === "completed"
                              ? "bg-emerald-600/20 text-emerald-400"
                              : (dep.content && dep.content.trim() !== "")
                              ? "bg-amber-600/20 text-amber-400"
                              : "bg-zinc-700 text-zinc-400"
                          }`}>
                            {dep.needs_regeneration
                              ? (isJa ? "再生成待ち" : "待重生成")
                              : dep.status === "completed"
                                ? getBlockStatusLabel(dep.status, isJa)
                                : (dep.content && dep.content.trim() !== "")
                                  ? (isJa ? "確認待ち" : "待确认")
                                  : (isJa ? "未完了" : "未完成")}
                          </span>
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-zinc-500">
                  {isJa ? "選択できる依存内容ブロックはありません" : "暂无可选的依赖内容块"}
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
                {isJa ? "キャンセル" : "取消"}
              </button>
              <button
                onClick={handleSaveDependencies}
                className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg"
              >
                {isJa ? "保存" : "保存"}
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
            <p className="text-xs text-zinc-500">{isJa ? `「${block.name}」のモデルを選択` : `为「${block.name}」选择模型`}</p>
          </div>
          <div className="max-h-48 overflow-y-auto">
            <button
              onClick={() => handleSaveModelOverride("")}
              className={`w-full text-left px-3 py-2 text-xs hover:bg-surface-3 transition-colors ${
                !modelOverride ? "text-brand-400 bg-brand-600/10" : "text-zinc-300"
              }`}
            >
              {isJa ? "全体既定に従う" : "跟随全局默认"}
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
