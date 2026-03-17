// frontend/components/content-block-editor.tsx
// 功能: ContentBlock 完整编辑器，用于树形视图中选中的内容块
// 提供与 FieldCard 相同的功能：编辑内容、AI 提示词、约束、依赖、生成等
// 优化: 轮询改为先检查数据变化再触发全局刷新，避免每3秒级联重渲染
// Inline AI: 选中文字浮动工具栏（改写/扩展/精简/对话改/问问Agent）+ diff 卡片
// 编辑入口: 仅 hover 编辑按钮 + 空内容区域点击，已移除内容区域单击进入编辑

"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { blockAPI, projectAPI, agentAPI, modelsAPI } from "@/lib/api";
import { useBlockGeneration } from "@/lib/hooks/useBlockGeneration";
import {
  countAnsweredPreQuestions,
  countAnsweredRequiredPreQuestions,
  countMissingRequiredPreQuestions,
  createPreQuestion,
  normalizePreAnswers,
  normalizePreQuestions,
} from "@/lib/preQuestions";
import { sendNotification } from "@/lib/utils";
import { useUiIsJa } from "@/lib/ui-locale";
import type { ContentBlock, ModelInfo, AgentSelectionRef } from "@/lib/api";
import type { PreQuestion } from "@/lib/preQuestions";
import { getEvalFieldEditor } from "./eval-field-editors";
import { VersionHistoryButton } from "./version-history";
import { 
  FileText, 
  Folder, 
  ChevronRight,
  ChevronDown, 
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
  X,
  Copy,
  Check,
  Sparkles,
  Loader2,
  Cpu,
  SlidersHorizontal,
} from "lucide-react";

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

// ===== 版本警告弹窗组件（含保存新版本功能） =====
function VersionWarningDialog({
  projectId,
  projectLocale,
  warning,
  affectedBlocks,
  onClose,
  onVersionCreated,
}: {
  projectId: string;
  projectLocale?: string | null;
  warning: string;
  affectedBlocks: string[] | null;
  onClose: () => void;
  onVersionCreated: () => void;
}) {
  const isJa = useUiIsJa(projectLocale);
  const [versionNote, setVersionNote] = useState(
    `${isJa ? "変更前スナップショット" : "变更前快照"} — ${new Date().toLocaleString(isJa ? "ja-JP" : "zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}`
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSaveVersion = async () => {
    if (saving) return;
    setSaving(true);
    try {
      await projectAPI.createVersion(projectId, versionNote || (isJa ? "上流変更前スナップショット" : "上游变更前快照"));
      setSaved(true);
      sendNotification(isJa ? "新しいバージョンスナップショットを作成しました" : "已成功创建新版本快照", "success");
      // 短暂显示成功状态后关闭
      setTimeout(() => onVersionCreated(), 800);
    } catch (err) {
      alert((isJa ? "バージョン作成に失敗しました: " : "创建版本失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-surface-1 border border-surface-3 rounded-xl shadow-2xl max-w-md w-full mx-4">
        <div className="px-5 py-4 border-b border-surface-3">
          <h3 className="text-base font-semibold text-amber-400 flex items-center gap-2">
            {isJa ? "上流内容の変更通知" : "上游内容变更提醒"}
          </h3>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-sm text-zinc-300">{warning}</p>
          {affectedBlocks && affectedBlocks.length > 0 && (
            <div className="bg-surface-2 rounded-lg p-3">
              <p className="text-xs text-zinc-400 mb-2">{isJa ? "影響を受ける内容:" : "受影响的内容："}</p>
              <ul className="space-y-1">
                {affectedBlocks.map((name, i) => (
                  <li key={i} className="text-sm text-amber-300 flex items-center gap-1.5">
                    <span className="text-amber-400">•</span> {name}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 保存新版本输入区 */}
          {!saved && (
            <div className="space-y-2 pt-2">
              <label className="text-xs text-zinc-400">{isJa ? "バージョンメモ（任意）" : "版本备注（可选）"}</label>
              <input
                type="text"
                value={versionNote}
                onChange={(e) => setVersionNote(e.target.value)}
                placeholder={isJa ? "例: 特定ブロック修正前のスナップショット" : "如：修改某内容块前的快照"}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-brand-500"
              />
            </div>
          )}

          {saved && (
            <div className="flex items-center gap-2 text-sm text-green-400 bg-green-900/20 rounded-lg px-3 py-2">
              <Check className="w-4 h-4" />
              {isJa ? "バージョンを保存しました" : "版本已保存"}
            </div>
          )}
        </div>
        <div className="px-5 py-4 border-t border-surface-3 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 bg-surface-2 hover:bg-surface-3 rounded-lg transition-colors"
          >
            {saved ? (isJa ? "閉じる" : "关闭") : (isJa ? "保存せず閉じる" : "不保存，关闭")}
          </button>
          {!saved && (
            <button
              onClick={handleSaveVersion}
              disabled={saving}
              className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {saving ? (isJa ? "保存中..." : "保存中...") : (isJa ? "新しいバージョンを保存" : "保存新版本")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}


interface ContentBlockEditorProps {
  block: ContentBlock;
  projectId: string;
  projectLocale?: string | null;
  allBlocks?: ContentBlock[];  // 用于依赖选择
  onUpdate?: () => void;
  /** 版本创建后通知父组件刷新项目列表 */
  onVersionCreated?: () => void;
  onBlockUpdated?: (block: ContentBlock) => void;
  /** M3: 将消息发送到 Agent 对话面板（Eval 诊断→Agent 修改桥接） */
  onSendToAgent?: (message: string) => void;
  /** B: 将选中文字+内容块引用发送到 Agent Panel 输入框上方 */
  onSendSelectionToAgent?: (ref: AgentSelectionRef) => void;
  /** 多视图模式：隐藏面包屑、压缩标题栏高度 */
  compact?: boolean;
}

export function ContentBlockEditor({
  block,
  projectId,
  projectLocale,
  allBlocks = [],
  onUpdate,
  onVersionCreated,
  onBlockUpdated,
  onSendToAgent,
  onSendSelectionToAgent,
  compact = false,
}: ContentBlockEditorProps) {
  const isJa = useUiIsJa(projectLocale);
  // P0-1: 统一使用 blockAPI（已移除 fieldAPI/isVirtual 分支）
  const [isEditing, setIsEditing] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState(block.name);
  const [editedContent, setEditedContent] = useState(block.content || "");
  const [showPromptModal, setShowPromptModal] = useState(false);
  const [showDependencyModal, setShowDependencyModal] = useState(false);
  
  
  // 编辑状态
  const [editedPrompt, setEditedPrompt] = useState(block.ai_prompt || "");
  const [savedPrompt, setSavedPrompt] = useState(block.ai_prompt || ""); // 本地追踪已保存的提示词
  const [selectedDependencies, setSelectedDependencies] = useState<string[]>(block.depends_on || []);
  const [aiPromptPurpose, setAiPromptPurpose] = useState("");
  const [generatingPrompt, setGeneratingPrompt] = useState(false);
  
  // M5: 模型覆盖
  const [modelOverride, setModelOverride] = useState<string>(block.model_override || "");
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [showModelSelector, setShowModelSelector] = useState(false);

  // 配置面板折叠状态：提示词未配置时默认展开（引导用户配置），已配置时默认折叠（节省空间）
  // compact 模式（多视图）下始终默认折叠，最大化内容区域
  const [showSettings, setShowSettings] = useState(compact ? false : !savedPrompt);

  // M4: Inline AI 编辑状态
  const [selectedText, setSelectedText] = useState("");
  const [inlineEditLoading, setInlineEditLoading] = useState(false);
  const [inlineEditResult, setInlineEditResult] = useState<{
    original: string;
    replacement: string;
    diff_preview: string;
  } | null>(null);
  const contentDisplayRef = useRef<HTMLDivElement>(null);
  const [toolbarPosition, setToolbarPosition] = useState<{ top: number; left: number } | null>(null);
  // 保存选中的 Range，用于 CSS Custom Highlight API 持久高亮
  const selectedRangeRef = useRef<Range | null>(null);

  // 运行时注入 ::highlight() CSS 规则（绕过 Turbopack CSS 解析器）
  useEffect(() => {
    if (typeof CSS === "undefined" || !("highlights" in CSS)) return;
    const id = "inline-ai-highlight-style";
    if (document.getElementById(id)) return; // 已有则跳过
    const style = document.createElement("style");
    style.id = id;
    style.textContent = "::highlight(inline-ai-selection) { background-color: rgba(124, 58, 237, 0.3); }";
    document.head.appendChild(style);
    // 不清理：全局只需一份，组件销毁后仍可复用
  }, []);

  // M4+: 对话改内容 — 自由文本输入
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [customInstruction, setCustomInstruction] = useState("");
  const customInputRef = useRef<HTMLInputElement>(null);

  // 复制状态
  const [copied, setCopied] = useState(false);
  const handleCopyContent = () => {
    const content = block.content || editedContent;
    if (content) {
      navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };
  
  // 生成前提问状态
  const [preQuestions, setPreQuestions] = useState<PreQuestion[]>(normalizePreQuestions(block.pre_questions || []));
  const [preAnswers, setPreAnswers] = useState<Record<string, string>>(
    normalizePreAnswers(block.pre_answers || {}, normalizePreQuestions(block.pre_questions || [])),
  );
  const hasPreQuestions = preQuestions.length > 0;
  const showPreQuestionsSection = block.block_type === "field";
  const [preQuestionsExpanded, setPreQuestionsExpanded] = useState(false);
  const [newPreQuestion, setNewPreQuestion] = useState("");
  const answeredPreQuestionCount = countAnsweredPreQuestions(preQuestions, preAnswers);
  const answeredRequiredPreQuestionCount = countAnsweredRequiredPreQuestions(preQuestions, preAnswers);
  const requiredPreQuestionCount = preQuestions.filter((item) => item.required).length;
  const missingRequiredPreQuestionCount = countMissingRequiredPreQuestions(preQuestions, preAnswers);

  // ---- 生成逻辑（通过 Hook 统一管理） ----
  const {
    isGenerating, generatingContent, canGenerate, unmetDependencies, missingPrompt,
    handleGenerate: _handleGenerate, handleStop: handleStopGeneration,
  } = useBlockGeneration({
    block, projectId, projectLocale, allBlocks,
    preQuestions,
    preAnswers, hasPreQuestions,
    onUpdate,
    onContentReady: (content) => setEditedContent(content),
  });

  const handleGenerate = async () => {
    // Editor 特有：退出编辑模式以显示流式内容
    setIsEditing(false);
    await _handleGenerate();
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
  
  // 可选的依赖（排除自己和自己的子节点）
  // 允许选择：所有 field 类型内容块
  const availableDependencies = allBlocks.filter(b => {
    // 排除自己
    if (b.id === block.id) return false;
    // 排除自己的子节点
    if (b.parent_id === block.id) return false;
    
    return b.block_type === "field";
  });
  
  const fieldDependencies = availableDependencies;
  
  useEffect(() => {
    // 生成中不要重置内容（会覆盖流式输出）
    // Hook 内部 isGenerating 已自动按 block.id 过滤，不在生成此块时为 false
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
    // M4: 切换 block 或内容变化时清空 inline edit 状态
    setSelectedText("");
    setToolbarPosition(null);
    setInlineEditResult(null);
    setInlineEditLoading(false);
    // M5: 同步 model_override
    setModelOverride(block.model_override || "");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block.id, block.content, block.name, block.ai_prompt, block.depends_on, block.pre_answers, block.pre_questions, block.model_override, block.updated_at]);

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

  // M5: 加载可用模型列表（仅在组件挂载时加载一次）
  useEffect(() => {
    modelsAPI.list().then(resp => {
      setAvailableModels(resp.models);
    }).catch(() => {
      // 静默忽略（可能后端未启动）
    });
  }, []);
  
  // ===== 关键修复 1：挂载或切换 block 时，从 API 获取最新状态 =====
  // 解决：用户导航到其他块再回来时，本地缓存的 block 数据可能是旧的
  // （例如后台正在执行 eval，status 已经是 in_progress，但本地缓存还是 pending/completed）
  useEffect(() => {
    if (!block.id || block.id.startsWith("virtual_")) return;
    let cancelled = false;
    
    blockAPI.get(block.id).then(freshBlock => {
      if (cancelled) return;
      const snapshot = blockSnapshotRef.current;
      // 如果后端状态或更新时间戳已经领先于本地，立即回写并触发树刷新
      if (
        (freshBlock.updated_at || "") !== snapshot.updatedAt
        || freshBlock.status !== snapshot.status
        || freshBlock.needs_regeneration !== snapshot.needsRegeneration
      ) {
        console.log(`[BlockEditor] 检测到数据不同步: block=${snapshot.name}, local_status=${snapshot.status}, server_status=${freshBlock.status}`);
        onBlockUpdatedRef.current?.(freshBlock);
        onUpdateRef.current?.();
      }
    }).catch(() => {}); // 静默忽略（可能是虚拟块等）
    
    return () => { cancelled = true; };
  }, [block.id]);
  
  // ===== 关键修复 2：如果 block 状态是 in_progress 但当前组件没在流式生成，则轮询刷新 =====
  // 优化：先检查后端数据是否实际变化，只在变化时才触发父组件刷新
  // 避免每3秒无条件调用 onUpdate() 导致整棵树级联重渲染
  const blockSnapshotRef = useRef({
    name: block.name,
    status: block.status,
    content: block.content || "",
    updatedAt: block.updated_at || "",
    needsRegeneration: block.needs_regeneration,
  });
  const pollStatusRef = useRef(block.status);
  const pollUpdatedAtRef = useRef(block.updated_at || "");
  useEffect(() => {
    blockSnapshotRef.current = {
      name: block.name,
      status: block.status,
      content: block.content || "",
      updatedAt: block.updated_at || "",
      needsRegeneration: block.needs_regeneration,
    };
  }, [block.name, block.status, block.content, block.updated_at, block.needs_regeneration]);
  useEffect(() => {
    pollStatusRef.current = block.status;
    pollUpdatedAtRef.current = block.updated_at || "";
  }, [block.status, block.updated_at, block.needs_regeneration]);
  
  useEffect(() => {
    if (!(block.status === "in_progress" || (block.auto_generate && block.needs_regeneration)) || isGenerating) return;
    if (block.id.startsWith("virtual_")) return;
    
    const pollInterval = setInterval(async () => {
      try {
        const fresh = await blockAPI.get(block.id);
        // 只在状态或更新时间戳实际变化时才触发同步
        if (
          fresh.status !== pollStatusRef.current
          || (fresh.updated_at || "") !== pollUpdatedAtRef.current
          || fresh.needs_regeneration !== blockSnapshotRef.current.needsRegeneration
        ) {
          onBlockUpdatedRef.current?.(fresh);
          onUpdateRef.current?.();
        }
      } catch {
        // 静默忽略轮询错误
      }
    }, 3000);
    return () => clearInterval(pollInterval);
  }, [block.auto_generate, block.id, block.needs_regeneration, block.status, isGenerating]);
  
  // 保存预提问答案状态
  const [isSavingPreAnswers, setIsSavingPreAnswers] = useState(false);
  const [preAnswersSaved, setPreAnswersSaved] = useState(false);
  
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
      console.error("保存预提问答案失败:", err);
      alert((isJa ? "保存に失敗しました: " : "保存失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
    } finally {
      setIsSavingPreAnswers(false);
    }
  };

  // 保存名称
  const handleSaveName = async () => {
    if (editedName.trim() && editedName !== block.name) {
      try {
        const updatedBlock = await updateCurrentBlock({ name: editedName.trim() });
        setEditedName(updatedBlock.name);
      } catch (err) {
        console.error("更新名称失败:", err);
      alert((isJa ? "名称更新に失敗しました: " : "更新名称失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
        setEditedName(block.name);
      }
    }
    setIsEditingName(false);
  };

  // 版本警告状态
  const [versionWarning, setVersionWarning] = useState<string | null>(null);
  const [affectedBlocks, setAffectedBlocks] = useState<string[] | null>(null);

  // Escape 键关闭弹窗
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showModelSelector) setShowModelSelector(false);
        else if (showPromptModal) setShowPromptModal(false);
        else if (showDependencyModal) setShowDependencyModal(false);
        else if (versionWarning) setVersionWarning(null);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [showModelSelector, showPromptModal, showDependencyModal, versionWarning]);

  // M5: 点击外部关闭模型选择器
  useEffect(() => {
    if (!showModelSelector) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest("[data-model-selector]")) {
        setShowModelSelector(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showModelSelector]);

  // 保存内容
  const handleSaveContent = async () => {
    try {
      const result = await updateCurrentBlock({ content: editedContent }, { refreshTree: true });
      setIsEditing(false);
      setEditedContent(result.content || "");
      
      // 检查是否有版本警告
      const warning = result?.version_warning;
      const affected = result?.affected_blocks;
      if (warning) {
        setVersionWarning(warning);
        const normalizedAffected = Array.isArray(affected)
          ? affected.map((item) => String(item))
          : null;
        setAffectedBlocks(normalizedAffected);
      }
    } catch (err) {
      console.error("保存失败:", err);
      alert((isJa ? "保存に失敗しました: " : "保存失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
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
        project_id: block.project_id || "",
      });
      setEditedPrompt(result.prompt);
      setAiPromptPurpose("");
    } catch (e: unknown) {
      alert((isJa ? "プロンプト生成に失敗しました: " : "生成提示词失败: ") + (e instanceof Error ? e.message : (isJa ? "不明なエラー" : "未知错误")));
    } finally {
      setGeneratingPrompt(false);
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
      alert((isJa ? "プロンプト保存に失敗しました: " : "保存提示词失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
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

  // M5: 保存模型覆盖
  const handleSaveModelOverride = async (modelId: string) => {
    try {
      // 空字符串 "" 表示清除覆盖（恢复使用全局默认），后端会转为 null
      const updatedBlock = await updateCurrentBlock({ model_override: modelId });
      setModelOverride(updatedBlock.model_override || "");
      setShowModelSelector(false);
      sendNotification(modelId ? (isJa ? `モデルを設定しました: ${modelId}` : `已设置模型: ${modelId}`) : (isJa ? "既定モデルに戻しました" : "已恢复为默认模型"), "success");
    } catch (err) {
      console.error("保存模型覆盖失败:", err);
      sendNotification((isJa ? "モデル保存に失敗しました: " : "保存模型失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")), "error");
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

  // 依赖块详情（UI 中显示依赖名称用）
  const dependencyBlocks = selectedDependencies
    .map(id => allBlocks.find(b => b.id === id))
    .filter(Boolean) as ContentBlock[];

  // 删除内容块
  const handleDelete = async () => {
    if (!confirm(isJa ? `「${block.name}」を削除しますか？この操作は取り消せません。` : `确定要删除「${block.name}」吗？此操作不可撤销。`)) return;
    try {
      await blockAPI.delete(block.id);
      onUpdate?.();
    } catch (err) {
      console.error("删除失败:", err);
      alert((isJa ? "削除に失敗しました: " : "删除失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
    }
  };

  // ===== M4: Inline AI 编辑处理 =====

  /** 应用 CSS Custom Highlight API 持久高亮（焦点移走后仍可见） */
  const applySelectionHighlight = useCallback((range: Range) => {
    try {
      if (typeof CSS !== "undefined" && "highlights" in CSS) {
        const hl = new (globalThis as /* eslint-disable-line @typescript-eslint/no-explicit-any */ any).Highlight(range);
        (CSS as any).highlights.set("inline-ai-selection", hl); // eslint-disable-line @typescript-eslint/no-explicit-any
      }
    } catch { /* 不支持的浏览器静默降级 */ }
  }, []);

  /** 清除 CSS Custom Highlight */
  const clearSelectionHighlight = useCallback(() => {
    try {
      if (typeof CSS !== "undefined" && "highlights" in CSS) {
        (CSS as any).highlights.delete("inline-ai-selection"); // eslint-disable-line @typescript-eslint/no-explicit-any
      }
    } catch { /* noop */ }
    selectedRangeRef.current = null;
  }, []);

  /** 用户在内容展示区域松开鼠标后，检测是否有文本选中 */
  const handleContentMouseUp = useCallback(() => {
    // 短暂延迟，确保浏览器完成 selection 计算
    setTimeout(() => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.toString().trim()) {
        // 没有产生新选中（纯点击）→ 清除旧的选中状态
        if (selectedText || inlineEditResult) {
          setSelectedText("");
          setToolbarPosition(null);
          setInlineEditResult(null);
          setShowCustomInput(false);
          setCustomInstruction("");
          clearSelectionHighlight();
          window.getSelection()?.removeAllRanges();
        }
        return;
      }
      // 确保选中区域在我们的内容展示区域内
      if (!contentDisplayRef.current?.contains(selection.anchorNode)) {
        return;
      }
      const text = selection.toString().trim();
      if (text.length < 2) return; // 忽略过短的选中

      const range = selection.getRangeAt(0);
      const rect = range.getBoundingClientRect();

      // 保存 Range 并应用持久高亮
      selectedRangeRef.current = range.cloneRange();
      applySelectionHighlight(range.cloneRange());

      setSelectedText(text);
      setToolbarPosition({
        top: rect.top - 8,                    // 选区上方
        left: rect.left + rect.width / 2,     // 水平居中
      });
      // 清除之前的结果（新选中 = 新一轮）
      setInlineEditResult(null);
    }, 10);
  }, [selectedText, inlineEditResult, applySelectionHighlight, clearSelectionHighlight]);

  /** 点击工具栏按钮，发起 inline AI 调用 */
  const handleInlineEdit = useCallback(async (operation: "rewrite" | "expand" | "condense" | "custom", instruction?: string) => {
    if (!selectedText || inlineEditLoading) return;
    setInlineEditLoading(true);
    // 收起自定义输入框
    setShowCustomInput(false);
    try {
      const result = await agentAPI.inlineEdit({
        text: selectedText,
        operation,
        context: (block.content || "").slice(0, 500),
        project_id: projectId,
        ...(operation === "custom" && instruction ? { custom_instruction: instruction } : {}),
      });
      setInlineEditResult({
        original: result.original,
        replacement: result.replacement,
        diff_preview: result.diff_preview,
      });
    } catch (err) {
      console.error("[M4] Inline edit failed:", err);
      sendNotification((isJa ? "AI 編集に失敗しました: " : "AI 编辑失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")), "error");
    } finally {
      setInlineEditLoading(false);
    }
  }, [selectedText, inlineEditLoading, block.content, projectId]);

  /** 接受 inline 修改：在原内容中定位并替换 */
  const handleAcceptInlineEdit = useCallback(async () => {
    if (!inlineEditResult || !block.content) return;
    const { original, replacement } = inlineEditResult;

    // 尝试在原始 Markdown 内容中精确查找选中文本
    let newContent = block.content;
    if (newContent.includes(original)) {
      newContent = newContent.replace(original, replacement);
    } else {
      // 回退: 尝试忽略 Markdown 行内标记的匹配
      // 构建一个 regex，在 original 的每个字符之间允许可选的 **, __, ~~, ` 等标记
      const escaped = original.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const flexiblePattern = escaped.split("").join("(?:\\*{1,2}|_{1,2}|~~|`)*");
      const regex = new RegExp(flexiblePattern);
      const match = newContent.match(regex);
      if (match && match.index !== undefined) {
        newContent = newContent.slice(0, match.index) + replacement + newContent.slice(match.index + match[0].length);
      } else {
        // 真的找不到 → 复制到剪贴板让用户手动替换
        await navigator.clipboard.writeText(replacement);
        sendNotification(isJa ? "原文を自動特定できませんでした。修正後のテキストをクリップボードにコピーしたので手動で置き換えてください。" : "无法自动定位原文（可能含格式标记），修改后的文本已复制到剪贴板，请手动替换", "warning");
        setInlineEditResult(null);
        setSelectedText("");
        setToolbarPosition(null);
        clearSelectionHighlight();
        return;
      }
    }

    try {
      const updatedBlock = await updateCurrentBlock({ content: newContent }, { refreshTree: true });
      setEditedContent(updatedBlock.content || "");
      setInlineEditResult(null);
      setSelectedText("");
      setToolbarPosition(null);
      clearSelectionHighlight();
      sendNotification(isJa ? "AI の修正を適用しました" : "已应用 AI 修改", "success");
    } catch (err) {
      console.error("[M4] Apply inline edit failed:", err);
      sendNotification((isJa ? "保存に失敗しました: " : "保存失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")), "error");
    }
  }, [inlineEditResult, block.content, block.id, onUpdate, clearSelectionHighlight]);

  /** 拒绝 inline 修改 */
  const handleRejectInlineEdit = useCallback(() => {
    setInlineEditResult(null);
    setSelectedText("");
    setToolbarPosition(null);
    setShowCustomInput(false);
    setCustomInstruction("");
    clearSelectionHighlight();
    window.getSelection()?.removeAllRanges();
  }, [clearSelectionHighlight]);

  /** 清除选中：点击内容区域外时 */
  useEffect(() => {
    if (!selectedText && !inlineEditResult) return;
    const handleMouseDown = (e: MouseEvent) => {
      // 如果点击的是工具栏/结果面板自身，不清除
      const toolbar = document.getElementById("m4-inline-toolbar");
      if (toolbar?.contains(e.target as Node)) return;
      // 如果点击的是内容展示区域，不清除（由 mouseUp 处理新选中）
      if (contentDisplayRef.current?.contains(e.target as Node)) return;
      // 其他地方 → 清除
      setSelectedText("");
      setToolbarPosition(null);
      setInlineEditResult(null);
      setShowCustomInput(false);
      setCustomInstruction("");
      clearSelectionHighlight();
    };
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, [selectedText, inlineEditResult, clearSelectionHighlight]);

  return (
    <div className="h-full flex flex-col">
      {/* 面包屑导航（compact 多视图模式下隐藏） */}
      {!compact && (
        <div className="flex items-center gap-2 text-sm text-zinc-500 px-4 py-2">
          <Folder className="w-4 h-4" />
          <span>{isJa ? "内容ブロック" : "内容块"}</span>
          <ChevronRight className="w-3 h-3" />
          <FileText className="w-4 h-4" />
          <span className="text-zinc-300">{block.name}</span>
        </div>
      )}

      {/* 主编辑卡片 */}
      <div className="flex-1 bg-surface-1 border-t border-surface-3 overflow-hidden flex flex-col">
        {/* 标题栏 */}
        <div className={`px-5 border-b border-surface-3 flex items-center justify-between ${compact ? "py-2" : "py-4"}`}>
          <div className="flex items-center gap-3">
            {isEditingName ? (
              <input
                type="text"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                onBlur={handleSaveName}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSaveName();
                  if (e.key === "Escape") {
                    setEditedName(block.name);
                    setIsEditingName(false);
                  }
                }}
                className="text-lg font-semibold text-zinc-200 bg-surface-2 border border-surface-3 rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-brand-500"
                autoFocus
              />
            ) : (
              <h2 
                className="text-lg font-semibold text-zinc-200 cursor-pointer hover:text-brand-400 transition-colors"
                onClick={() => setIsEditingName(true)}
                title={isJa ? "クリックして名称を編集" : "点击编辑名称"}
              >
                {block.name} <span className="text-xs text-zinc-600">✏️</span>
              </h2>
            )}
            
            <span className={`px-2 py-0.5 text-xs rounded ${getBlockStatusClass(block.status, block.needs_regeneration)}`}>
              {getBlockStatusLabel(block.status, isJa, block.needs_regeneration)}
            </span>

            {/* 配置面板折叠开关 */}
            <div className="relative">
              <button
                onClick={() => setShowSettings(!showSettings)}
                className={`p-1.5 rounded-md transition-colors ${
                  showSettings
                    ? "bg-surface-3 text-zinc-300"
                    : "text-zinc-500 hover:text-zinc-300 hover:bg-surface-2"
                }`}
                title={
                  showSettings
                    ? (isJa ? "設定を閉じる" : "收起配置")
                    : (!savedPrompt
                        ? (isJa ? "設定を開く（プロンプト未設定）" : "展开配置（提示词未配置）")
                        : (isJa ? "設定を開く" : "展开配置"))
                }
              >
                <SlidersHorizontal className="w-3.5 h-3.5" />
              </button>
              {/* 提示词未配置时，显示小红点警告 */}
              {!savedPrompt && (
                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-red-500 rounded-full pointer-events-none" />
              )}
            </div>
          </div>

          {/* 操作按钮 */}
          <div className="flex items-center gap-2">
            {/* 生成中：显示停止按钮 */}
            {isGenerating && (
              <button
                onClick={handleStopGeneration}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-red-600 hover:bg-red-700 text-white transition-colors"
                title={isJa ? "生成を停止" : "停止生成"}
              >
                <Square className="w-4 h-4" />
                {isJa ? "生成を停止" : "停止生成"}
              </button>
            )}
            {/* 生成按钮：无已有内容时显示（从零创建） */}
            {!block.content && !isGenerating && (
              <button
                onClick={handleGenerate}
                disabled={!canGenerate}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors ${
                  canGenerate
                    ? "bg-brand-600 hover:bg-brand-700 text-white"
                    : "bg-zinc-700 text-zinc-500 cursor-not-allowed"
                }`}
                title={
                  !canGenerate
                    ? missingPrompt
                      ? (isJa ? "AI プロンプトが未設定です。⚙ 設定から先に設定してください" : "未配置 AI 提示词，请先点击 ⚙ 配置")
                      : unmetDependencies.length > 0
                      ? (isJa ? `依存内容が未準備です: ${unmetDependencies.map(d => d.name).join(", ")}` : `依赖内容未就绪: ${unmetDependencies.map(d => d.name).join(", ")}`)
                      : (isJa ? "必須の生成前ヒアリングが未回答です" : "必答生成前提问未回答")
                    : (isJa ? "内容を生成" : "生成内容")
                }
              >
                <Play className="w-4 h-4" />
                {isJa ? "生成" : "生成"}
              </button>
            )}
            
            {/* 生成前置条件警告：提示词 > 依赖 > 必答预提问，按优先级显示 */}
            {!canGenerate && !isGenerating && (
              <span
                className="text-xs text-amber-500"
                title={
                  missingPrompt
                    ? (isJa ? "AI プロンプトが未設定です。⚙ 設定から設定してください" : "请先点击 ⚙ 设置按钮配置 AI 提示词")
                    : unmetDependencies.length > 0
                    ? (isJa ? `依存内容が未準備です: ${unmetDependencies.map(d => d.name).join(", ")}` : `依赖内容未就绪: ${unmetDependencies.map(d => d.name).join(", ")}`)
                    : (isJa ? "必須の生成前ヒアリングが未回答です" : "必答生成前提问未填写")
                }
              >
                {missingPrompt
                  ? (isJa ? "プロンプト未設定" : "未配置提示词")
                  : unmetDependencies.length > 0
                  ? (isJa ? `${unmetDependencies.length} 件の依存未準備` : `${unmetDependencies.length} 个依赖未就绪`)
                  : (isJa ? `必須ヒアリング ${missingRequiredPreQuestionCount} 件未回答` : `${missingRequiredPreQuestionCount} 个必答题未回答`)}
              </span>
            )}
            
            {/* 用户确认按钮：need_review 且有内容但未确认 */}
            {block.need_review && block.status === "in_progress" && block.content && !block.needs_regeneration && !isGenerating && (
              <button
                onClick={async () => {
                  try {
                    const confirmedBlock = await blockAPI.confirm(block.id);
                    applyUpdatedBlock(confirmedBlock, true);
                  } catch (err) {
                    console.error("确认失败:", err);
                    alert((isJa ? "確認に失敗しました: " : "确认失败: ") + (err instanceof Error ? err.message : (isJa ? "不明なエラー" : "未知错误")));
                  }
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors"
              >
                <Check className="w-4 h-4" /> {isJa ? "確認" : "确认"}
              </button>
            )}
            
            {/* 重新生成按钮：有已有内容时显示（替换/重做），与"生成"互斥无重叠 */}
            {block.content && !isGenerating && (
              <button
                onClick={handleGenerate}
                disabled={!canGenerate}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-sm border rounded-lg transition-colors ${
                  canGenerate
                    ? "bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border-amber-500/30"
                    : "bg-zinc-700/50 text-zinc-500 border-zinc-600/30 cursor-not-allowed"
                }`}
                title={
                  !canGenerate
                    ? missingPrompt
                      ? (isJa ? "AI プロンプトが未設定です。⚙ 設定から先に設定してください" : "未配置 AI 提示词，请先点击 ⚙ 配置")
                      : unmetDependencies.length > 0
                      ? (isJa ? `依存内容が未準備です: ${unmetDependencies.map(d => d.name).join(", ")}` : `依赖内容未就绪: ${unmetDependencies.map(d => d.name).join(", ")}`)
                      : (isJa ? "必須の生成前ヒアリングが未回答です" : "必答生成前提问未回答")
                    : (isJa ? "内容を再生成" : "重新生成内容")
                }
              >
                <RefreshCw className="w-4 h-4" />
                {isJa ? "再生成" : "重新生成"}
              </button>
            )}
            
            {isGenerating && (
              <span className="text-sm text-brand-400 animate-pulse">{isJa ? "生成中..." : "生成中..."}</span>
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
              className="p-1.5 text-zinc-500 hover:text-red-400 transition-colors"
              title={isJa ? "この内容ブロックを削除" : "删除此内容块"}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 配置区域（可折叠） — 使用 CSS grid 实现无闪烁高度过渡 */}
        <div className={`grid transition-[grid-template-rows] duration-200 ease-in-out ${showSettings ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}>
        <div className="overflow-hidden">
        <div className="px-5 py-3 border-b border-surface-3 bg-surface-2/50 flex flex-wrap items-center gap-3">
          {/* AI 提示词配置 */}
          <button
            onClick={() => setShowPromptModal(true)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-colors ${
              savedPrompt 
                ? "border-brand-500/30 bg-brand-600/10 text-brand-400 hover:bg-brand-600/20"
                : "border-red-500/30 bg-red-600/10 text-red-400 hover:bg-red-600/20"
            }`}
          >
            <MessageSquarePlus className="w-3.5 h-3.5" />
            {savedPrompt ? (isJa ? "プロンプト設定済み" : "已配置提示词") : (isJa ? "プロンプト未設定" : "未配置提示词")}
          </button>
          
          {/* 依赖配置 */}
          <button
            onClick={() => setShowDependencyModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-surface-4 bg-surface-2 text-zinc-400 hover:bg-surface-3 rounded-lg transition-colors"
          >
            <Workflow className="w-3.5 h-3.5" />
            {dependencyBlocks.length > 0 ? (
              <span className="flex items-center gap-1">
                {isJa ? "依存:" : "依赖:"}
                {dependencyBlocks.map(dep => (
                  <span key={dep.id} className={`px-1.5 py-0.5 rounded ${
                    (dep.content && dep.content.trim() !== "")
                      ? "bg-emerald-600/20 text-emerald-400" 
                      : "bg-red-600/20 text-red-400"
                  }`}>
                    {dep.name}
                  </span>
                ))}
              </span>
            ) : (
              <span className="text-zinc-500">{isJa ? "依存なし（クリックして設定）" : "无依赖（点击配置）"}</span>
            )}
          </button>
          
          {/* need_review 状态（可切换） */}
          <button
            onClick={async () => {
              try {
                await updateCurrentBlock({ need_review: !block.need_review }, { refreshTree: true });
              } catch (err) {
                console.error("切换确认状态失败:", err);
              }
            }}
            className={`flex items-center gap-1 px-2 py-1 text-xs rounded cursor-pointer transition-colors ${
              block.need_review 
                ? "bg-amber-600/10 text-amber-400 hover:bg-amber-600/20"
                : "bg-emerald-600/10 text-emerald-400 hover:bg-emerald-600/20"
            }`}
            title={block.need_review ? (isJa ? "手動確認が必要（クリックで切替）" : "需要人工确认（点击切换）") : (isJa ? "確認不要（クリックで切替）" : "无需确认（点击切换）")}
          >
            {block.need_review ? <ShieldCheck className="w-3.5 h-3.5" /> : <Zap className="w-3.5 h-3.5" />}
            {block.need_review ? (isJa ? "手動確認が必要" : "需要人工确认") : (isJa ? "確認不要" : "无需确认")}
          </button>

          {/* auto_generate 状态（可切换）：所有 field 类型块均可切换 */}
          {block.block_type === "field" && (
            <button
              onClick={async () => {
                try {
                  await updateCurrentBlock({ auto_generate: !block.auto_generate });
                } catch (err) {
                  console.error("切换自动生成失败:", err);
                }
              }}
              className={`flex items-center gap-1 px-2 py-1 text-xs rounded cursor-pointer transition-colors ${
                block.auto_generate
                  ? "bg-blue-600/10 text-blue-400 hover:bg-blue-600/20"
                  : "bg-zinc-600/10 text-zinc-400 hover:bg-zinc-600/20"
              }`}
              title={block.auto_generate ? (isJa ? "自動生成（依存準備完了時に自動実行、クリックで切替）" : "自动生成（依赖就绪时自动触发，点击切换）") : (isJa ? "手動実行（クリックで自動生成へ切替）" : "手动触发（点击切换为自动生成）")}
            >
              <Sparkles className="w-3.5 h-3.5" />
              {block.auto_generate ? (isJa ? "自動生成" : "自动生成") : (isJa ? "手動実行" : "手动触发")}
            </button>
          )}

          {/* M5: 模型覆盖选择（group 类型纯分组无内容，不显示） */}
          {block.block_type !== "group" && (
            <div className="relative" data-model-selector>
              <button
                onClick={() => setShowModelSelector(!showModelSelector)}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                  modelOverride
                    ? "border-purple-500/30 bg-purple-600/10 text-purple-400 hover:bg-purple-600/20"
                    : "border-surface-4 bg-surface-2 text-zinc-500 hover:bg-surface-3 hover:text-zinc-400"
                }`}
              >
                <Cpu className="w-3.5 h-3.5" />
                {modelOverride ? modelOverride : (isJa ? "既定モデル" : "默认模型")}
              </button>

              {showModelSelector && (
                <div className="absolute top-full left-0 mt-1 z-50 w-64 bg-surface-1 border border-surface-3 rounded-lg shadow-xl overflow-hidden">
                  <div className="p-2 border-b border-surface-3">
                    <p className="text-xs text-zinc-500">{isJa ? "この内容ブロックに使うモデルを選択" : "为此内容块选择模型"}</p>
                  </div>
                  <div className="max-h-60 overflow-y-auto">
                    <button
                      onClick={() => handleSaveModelOverride("")}
                      className={`w-full px-3 py-2 text-left text-sm hover:bg-surface-3 transition-colors flex items-center justify-between ${
                        !modelOverride ? "text-brand-400" : "text-zinc-300"
                      }`}
                    >
                      <span>{isJa ? "既定モデルを使用" : "使用默认模型"}</span>
                      {!modelOverride && <Check className="w-3.5 h-3.5" />}
                    </button>
                    {availableModels.map(m => (
                      <button
                        key={m.id}
                        onClick={() => handleSaveModelOverride(m.id)}
                        className={`w-full px-3 py-2 text-left text-sm hover:bg-surface-3 transition-colors flex items-center justify-between ${
                          modelOverride === m.id ? "text-brand-400" : "text-zinc-300"
                        }`}
                      >
                        <span>
                          {m.name}
                          <span className="text-zinc-500 ml-1 text-xs">({m.provider})</span>
                        </span>
                        {modelOverride === m.id && <Check className="w-3.5 h-3.5" />}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* 生成前提问区域（可折叠） — 并入设置面板 */}
        {showPreQuestionsSection && (
          <div className="border-b border-amber-600/20">
            <button
              onClick={() => setPreQuestionsExpanded(!preQuestionsExpanded)}
              className="w-full px-5 py-2.5 flex items-center justify-between bg-amber-900/10 hover:bg-amber-900/20 transition-colors"
            >
              <div className="flex items-center gap-2">
                {preQuestionsExpanded ? (
                  <ChevronDown className="w-4 h-4 text-amber-400" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-amber-400" />
                )}
                <span className="text-amber-400 text-sm font-medium">{isJa ? "生成前ヒアリング" : "生成前提问"}</span>
                <span className="text-xs text-zinc-500">
                  {hasPreQuestions
                    ? (isJa
                      ? `（必須 ${answeredRequiredPreQuestionCount}/${requiredPreQuestionCount}、回答済み ${answeredPreQuestionCount}/${preQuestions.length}）`
                      : `（必答 ${answeredRequiredPreQuestionCount}/${requiredPreQuestionCount}，全部已答 ${answeredPreQuestionCount}/${preQuestions.length}）`)
                    : (isJa ? "（ヒアリング項目はまだありません。クリックして追加）" : "（暂无问题，点击添加）")}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {preAnswersSaved && (
                  <span className="text-xs text-green-400">{isJa ? "✓ 保存済み" : "✓ 已保存"}</span>
                )}
              </div>
            </button>
            {preQuestionsExpanded && (
              <div className="px-5 py-4 bg-amber-900/10">
                <div className="space-y-3">
                  {hasPreQuestions ? (
                    preQuestions.map((question, idx) => (
                      <div key={question.id} className="space-y-2 rounded-lg border border-amber-500/15 bg-surface-2/30 p-3">
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
                            className="flex-1 rounded border border-surface-3 bg-surface-1 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
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
                          placeholder={question.required ? (isJa ? "必須質問への回答を入力..." : "请输入必答问题的回答...") : (isJa ? "任意回答：空欄可" : "选答：可留空")}
                          className="w-full px-3 py-2 bg-surface-2 border border-amber-500/30 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                        />
                      </div>
                    ))
                  ) : (
                    <div className="rounded-lg border border-dashed border-amber-500/30 bg-surface-2/40 px-4 py-3 text-sm text-zinc-500">
                      {isJa ? "生成前ヒアリングはまだありません。先に質問を追加して回答を保存すると、生成時にそれらが文脈として渡されます。" : "还没有生成前提问。你可以先添加问题，再保存回答，生成时这些问答会进入上下文。"}
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
                    placeholder={isJa ? "生成前ヒアリングを追加..." : "新增生成前提问..."}
                    className="flex-1 px-3 py-2 bg-surface-2 border border-amber-500/30 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
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
                <div className="flex items-center justify-between mt-3">
                  <p className="text-xs text-amber-500/60">
                    {missingRequiredPreQuestionCount > 0
                      ? (isJa ? `必須質問があと ${missingRequiredPreQuestionCount} 件未回答です。必須質問が未回答だと「すべて開始」と手動生成を実行できません。` : `还有 ${missingRequiredPreQuestionCount} 个必答问题未回答；必答题会阻止“全部开始”和手动生成。`)
                      : (isJa ? "回答は内容生成時の文脈として AI に渡されます。任意質問は空欄のままで構いません。" : "答案会作为生成内容的上下文传递给 AI；选答题可留空。")}
                  </p>
                  <button
                    onClick={handleSavePreAnswers}
                    disabled={isSavingPreAnswers}
                    className="px-3 py-1 text-xs bg-amber-600 hover:bg-amber-700 disabled:bg-amber-800 text-white rounded transition-colors"
                  >
                    {isSavingPreAnswers ? (isJa ? "保存中..." : "保存中...") : (isJa ? "回答を保存" : "保存回答")}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
        </div>
        </div>

        {/* 内容区域 */}
        <div className="flex-1 p-5 overflow-y-auto">
          {/* Eval V2 专用字段编辑器 */}
          {block.special_handler && getEvalFieldEditor(block.special_handler) ? (
            (() => {
              const EvalEditor = getEvalFieldEditor(block.special_handler!)!;
              return <EvalEditor block={block} projectId={projectId} projectLocale={projectLocale} onUpdate={onUpdate} onSendToAgent={onSendToAgent} />;
            })()
          ) : isEditing ? (
            <div className="h-full flex flex-col gap-3">
              <textarea
                value={editedContent}
                onChange={(e) => setEditedContent(e.target.value)}
                className="flex-1 w-full bg-surface-2 border border-surface-3 rounded-lg p-4 text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none font-mono text-sm"
                placeholder={isJa ? "ここで内容を編集..." : "在此编辑内容..."}
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => {
                    setEditedContent(block.content || "");
                    setIsEditing(false);
                  }}
                  className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  {isJa ? "キャンセル" : "取消"}
                </button>
                <button
                  onClick={handleSaveContent}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
                >
                  <Save className="w-4 h-4" />
                  {isJa ? "保存" : "保存"}
                </button>
              </div>
            </div>
          ) : (
            <div 
              className="min-h-[200px] group"
              onMouseUp={handleContentMouseUp}
            >
              {isGenerating ? (
                <div className="prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{generatingContent || (isJa ? "生成中..." : "正在生成...")}</ReactMarkdown>
                  <span className="inline-block w-2 h-4 bg-brand-500 animate-pulse" />
                </div>
              ) : block.status === "in_progress" && !block.content ? (
                <div className="flex items-center gap-2 py-8 justify-center">
                  <span className="inline-block w-2 h-4 bg-brand-500 animate-pulse" />
                  <span className="text-sm text-brand-400 animate-pulse">{isJa ? "バックグラウンドで生成中です。しばらくお待ちください..." : "后台生成中，请稍候..."}</span>
                </div>
              ) : block.content ? (
                <div ref={contentDisplayRef}>
                  <div className="sticky top-0 z-10 flex justify-end gap-1 pt-2 pr-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button 
                      onClick={(e) => { e.stopPropagation(); handleCopyContent(); }}
                      className="flex items-center gap-1 px-2 py-1 text-xs bg-surface-2 border border-surface-3 text-zinc-400 hover:text-zinc-200 rounded"
                      title={isJa ? "全文をコピー（Markdown形式）" : "复制全文（Markdown格式）"}
                    >
                      {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
                      {copied ? (isJa ? "コピー済み" : "已复制") : (isJa ? "复制" : "复制")}
                    </button>
                    <button 
                      onClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
                      className="flex items-center gap-1 px-2 py-1 text-xs bg-surface-2 border border-surface-3 text-zinc-400 hover:text-zinc-200 rounded"
                    >
                      <Pencil className="w-3 h-3" />
                      {isJa ? "編集" : "编辑"}
                    </button>
                  </div>
                  <div className="prose prose-invert prose-sm max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.content}</ReactMarkdown>
                  </div>
                </div>
              ) : (
                <div
                  className="flex flex-col items-center justify-center h-[200px] text-zinc-500 border-2 border-dashed border-surface-3 rounded-lg cursor-pointer"
                  onClick={() => setIsEditing(true)}
                >
                  <Pencil className="w-8 h-8 mb-2 opacity-50" />
                  <p>{isJa ? "ここをクリックして内容を編集" : "点击此处编辑内容"}</p>
                  <p className="text-xs mt-1">{isJa ? "または「生成」ボタンで AI に生成させます" : "或使用「生成」按钮让 AI 生成"}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* AI 提示词编辑弹窗 */}
      {showPromptModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-2xl bg-surface-1 border border-surface-3 rounded-xl shadow-2xl">
            <div className="px-5 py-4 border-b border-surface-3 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-zinc-200">{isJa ? "AI プロンプトを編集" : "编辑 AI 提示词"}</h3>
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
                {isJa ? "プロンプトはプロジェクト文脈（作成者特性、意図、ユーザー像）と一緒に AI へ送信され、内容生成に使われます。" : "提示词会与项目上下文（创作者特质、意图、用户画像）一起发送给 AI，用于生成内容。"}
              </p>

              {/* 🤖 用 AI 生成提示词 */}
              <div className="p-3 bg-surface-2/50 border border-surface-3 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs text-zinc-400">🤖 {isJa ? "AI でプロンプトを生成" : "用 AI 生成提示词"}</span>
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={aiPromptPurpose}
                    onChange={(e) => setAiPromptPurpose(e.target.value)}
                    placeholder={isJa ? "内容ブロックの目的を簡潔に入力。例: 商品の主要価値を紹介" : "简述内容块目的，如：介绍产品核心卖点"}
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-lg bg-surface-1 border border-surface-3 rounded-xl shadow-2xl">
            <div className="px-5 py-4 border-b border-surface-3 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-zinc-200">{isJa ? "依存関係を設定" : "设置依赖关系"}</h3>
              <button 
                onClick={() => setShowDependencyModal(false)}
                className="p-1 text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5">
              <p className="text-sm text-zinc-400 mb-4">
                {isJa ? `「${block.name}」が依存する内容ブロックを選択します。依存ブロックが完了してからこの内容を生成できます。` : `选择「${block.name}」依赖的内容块。只有依赖的内容块完成后，才能生成此内容。`}
              </p>
              
              {availableDependencies.length > 0 ? (
                <div className="space-y-4 max-h-80 overflow-y-auto">
                  {/* 普通字段区域 */}
                  {fieldDependencies.length > 0 && (
                    <div>
                      <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2 flex items-center gap-1">
                        {isJa ? "内容ブロック" : "内容块"}
                      </h4>
                      <div className="space-y-2">
                        {fieldDependencies.map(dep => (
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
                                <span className={`px-1.5 py-0.5 text-xs rounded ${
                                  dep.status === "completed"
                                    ? "bg-emerald-600/20 text-emerald-400"
                                    : (dep.content && dep.content.trim() !== "")
                                    ? "bg-amber-600/20 text-amber-400"
                                    : "bg-zinc-700 text-zinc-400"
                                }`}>
                                  {dep.status === "completed" ? (isJa ? "完了" : "已完成") : (dep.content && dep.content.trim() !== "") ? (isJa ? "確認待ち" : "待确认") : (isJa ? "未完了" : "未完成")}
                                </span>
                              </div>
                            </div>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-8 text-zinc-500">
                  {isJa ? "選択可能な依存内容ブロックがありません" : "暂无可选的依赖内容块"}
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
                {isJa ? "依存関係を保存" : "保存依赖关系"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== 版本警告弹窗 ===== */}
      {versionWarning && (
        <VersionWarningDialog
          projectId={projectId}
            projectLocale={projectLocale}
          warning={versionWarning}
          affectedBlocks={affectedBlocks}
          onClose={() => { setVersionWarning(null); setAffectedBlocks(null); }}
          onVersionCreated={() => {
            setVersionWarning(null);
            setAffectedBlocks(null);
            onUpdate?.();
            onVersionCreated?.();  // 通知 workspace 刷新项目列表
          }}
        />
      )}

      {/* ===== M4: Inline AI Floating Toolbar ===== */}
      {toolbarPosition && !isEditing && (
        <div
          id="m4-inline-toolbar"
          className="fixed z-50"
          style={{
            top: `${toolbarPosition.top}px`,
            left: `${toolbarPosition.left}px`,
            transform: "translate(-50%, -100%)",
          }}
          onMouseDown={(e) => e.preventDefault()} // 阻止清除文本选中
        >
          {/* 状态 1: AI 处理中 */}
          {inlineEditLoading && (
            <div className="flex items-center gap-2 px-4 py-2 bg-surface-1 border border-brand-500/40 rounded-lg shadow-xl">
              <Loader2 className="w-4 h-4 text-brand-400 animate-spin" />
              <span className="text-sm text-brand-300">{isJa ? "AI が処理中..." : "AI 处理中..."}</span>
            </div>
          )}

          {/* 状态 2: 显示结果面板 */}
          {!inlineEditLoading && inlineEditResult && (
            <div className="w-[480px] max-w-[90vw] bg-surface-1 border border-surface-3 rounded-xl shadow-2xl overflow-hidden">
              <div className="px-4 py-2.5 border-b border-surface-3 flex items-center justify-between">
                <h4 className="text-sm font-medium text-zinc-200 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-brand-400" />
                  {isJa ? "AI 修正提案" : "AI 修改建议"}
                </h4>
                <button
                  onClick={handleRejectInlineEdit}
                  className="p-1 text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="p-4 space-y-3 max-h-[300px] overflow-y-auto">
                {/* 原文 */}
                <div>
                  <span className="text-xs text-zinc-500 mb-1 block">{isJa ? "原文" : "原文"}</span>
                  <div className="px-3 py-2 bg-red-950/30 border border-red-500/20 rounded-lg text-sm text-red-300/80 line-through whitespace-pre-wrap">
                    {inlineEditResult.original}
                  </div>
                </div>
                {/* 修改后 */}
                <div>
                  <span className="text-xs text-zinc-500 mb-1 block">{isJa ? "修正後" : "修改后"}</span>
                  <div className="px-3 py-2 bg-emerald-950/30 border border-emerald-500/20 rounded-lg text-sm text-emerald-300 whitespace-pre-wrap">
                    {inlineEditResult.replacement}
                  </div>
                </div>
              </div>
              <div className="px-4 py-3 border-t border-surface-3 flex justify-end gap-2">
                <button
                  onClick={handleRejectInlineEdit}
                  className="px-3 py-1.5 text-sm text-zinc-400 hover:text-zinc-200 bg-surface-2 hover:bg-surface-3 rounded-lg transition-colors"
                >
                  {isJa ? "却下" : "拒绝"}
                </button>
                <button
                  onClick={handleAcceptInlineEdit}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
                >
                  <Check className="w-3.5 h-3.5" />
                  {isJa ? "修正を適用" : "接受修改"}
                </button>
              </div>
            </div>
          )}

          {/* 状态 3: 选中文本工具栏（默认状态） */}
          {!inlineEditLoading && !inlineEditResult && selectedText && (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-1 px-2 py-1.5 bg-surface-1 border border-surface-3 rounded-lg shadow-xl">
                <Sparkles className="w-3.5 h-3.5 text-brand-400 mr-1" />
                <button
                  onClick={() => handleInlineEdit("rewrite")}
                  className="px-2.5 py-1 text-xs text-zinc-300 hover:text-white hover:bg-brand-600/30 rounded transition-colors"
                >
                  {isJa ? "書き換え" : "改写"}
                </button>
                <div className="w-px h-4 bg-surface-3" />
                <button
                  onClick={() => handleInlineEdit("expand")}
                  className="px-2.5 py-1 text-xs text-zinc-300 hover:text-white hover:bg-brand-600/30 rounded transition-colors"
                >
                  {isJa ? "拡張" : "扩展"}
                </button>
                <div className="w-px h-4 bg-surface-3" />
                <button
                  onClick={() => handleInlineEdit("condense")}
                  className="px-2.5 py-1 text-xs text-zinc-300 hover:text-white hover:bg-brand-600/30 rounded transition-colors"
                >
                  {isJa ? "要約" : "精简"}
                </button>
                <div className="w-px h-4 bg-surface-3" />
                <button
                  onClick={() => {
                    setShowCustomInput(true);
                    setTimeout(() => customInputRef.current?.focus(), 50);
                  }}
                  className="px-2.5 py-1 text-xs text-brand-300 hover:text-white hover:bg-brand-600/30 rounded transition-colors"
                >
                  {isJa ? "指示して修正" : "对话改"}
                </button>
                {onSendSelectionToAgent && (
                  <>
                    <div className="w-px h-4 bg-surface-3" />
                    <button
                      onClick={() => {
                        onSendSelectionToAgent({ blockId: block.id, blockName: block.name, selectedText });
                        setSelectedText("");
                        setToolbarPosition(null);
                        setShowCustomInput(false);
                        setCustomInstruction("");
                        clearSelectionHighlight();
                      }}
                      className="px-2.5 py-1 text-xs text-zinc-300 hover:text-white hover:bg-brand-600/30 rounded transition-colors flex items-center gap-1"
                    >
                      <MessageSquarePlus className="w-3 h-3" />
                      {isJa ? "Agent に相談" : "问问 Agent"}
                    </button>
                  </>
                )}
              </div>
              {/* 对话改：自由输入框 */}
              {showCustomInput && (
                <div className="flex gap-1.5 bg-surface-1 border border-surface-3 rounded-lg shadow-xl px-2 py-1.5">
                  <input
                    ref={customInputRef}
                    type="text"
                    value={customInstruction}
                    onChange={(e) => setCustomInstruction(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && customInstruction.trim()) {
                        handleInlineEdit("custom", customInstruction.trim());
                        setCustomInstruction("");
                      }
                      if (e.key === "Escape") {
                        setShowCustomInput(false);
                        setCustomInstruction("");
                      }
                    }}
                    placeholder={isJa ? "修正の方向性を入力..." : "描述修改方向..."}
                    className="flex-1 min-w-[200px] px-2 py-1 text-xs bg-surface-2 border border-surface-3 rounded text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
                  />
                  <button
                    onClick={() => {
                      if (customInstruction.trim()) {
                        handleInlineEdit("custom", customInstruction.trim());
                        setCustomInstruction("");
                      }
                    }}
                    disabled={!customInstruction.trim()}
                    className="px-2.5 py-1 text-xs bg-brand-600 hover:bg-brand-700 disabled:bg-surface-3 disabled:text-zinc-600 text-white rounded transition-colors"
                  >
                    {isJa ? "送信" : "提交"}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
