// frontend/components/content-block-editor.tsx
// 功能: ContentBlock 完整编辑器，用于树形视图中选中的内容块
// 提供与 FieldCard 相同的功能：编辑内容、AI 提示词、约束、依赖、生成等
// 优化: 轮询改为先检查数据变化再触发全局刷新，避免每3秒级联重渲染

"use client";

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { blockAPI, fieldAPI, projectAPI, runAutoTriggerChain } from "@/lib/api";
import { useBlockGeneration } from "@/lib/hooks/useBlockGeneration";
import { sendNotification } from "@/lib/utils";
import type { ContentBlock } from "@/lib/api";
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
  SlidersHorizontal,
  ShieldCheck,
  Zap,
  Pencil,
  Save, 
  Trash2,
  RefreshCw,
  X,
  Copy,
  Check
} from "lucide-react";

// ===== 版本警告弹窗组件（含保存新版本功能） =====
function VersionWarningDialog({
  projectId,
  warning,
  affectedBlocks,
  onClose,
  onVersionCreated,
}: {
  projectId: string;
  warning: string;
  affectedBlocks: string[] | null;
  onClose: () => void;
  onVersionCreated: () => void;
}) {
  const [versionNote, setVersionNote] = useState(
    `变更前快照 — ${new Date().toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}`
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSaveVersion = async () => {
    if (saving) return;
    setSaving(true);
    try {
      await projectAPI.createVersion(projectId, versionNote || "上游变更前快照");
      setSaved(true);
      sendNotification("已成功创建新版本快照", "success");
      // 短暂显示成功状态后关闭
      setTimeout(() => onVersionCreated(), 800);
    } catch (err) {
      alert("创建版本失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-surface-1 border border-surface-3 rounded-xl shadow-2xl max-w-md w-full mx-4">
        <div className="px-5 py-4 border-b border-surface-3">
          <h3 className="text-base font-semibold text-amber-400 flex items-center gap-2">
            上游内容变更提醒
          </h3>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-sm text-zinc-300">{warning}</p>
          {affectedBlocks && affectedBlocks.length > 0 && (
            <div className="bg-surface-2 rounded-lg p-3">
              <p className="text-xs text-zinc-400 mb-2">受影响的内容：</p>
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
              <label className="text-xs text-zinc-400">版本备注（可选）</label>
              <input
                type="text"
                value={versionNote}
                onChange={(e) => setVersionNote(e.target.value)}
                placeholder="如：修改某内容块前的快照"
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-brand-500"
              />
            </div>
          )}

          {saved && (
            <div className="flex items-center gap-2 text-sm text-green-400 bg-green-900/20 rounded-lg px-3 py-2">
              <Check className="w-4 h-4" />
              版本已保存
            </div>
          )}
        </div>
        <div className="px-5 py-4 border-t border-surface-3 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 bg-surface-2 hover:bg-surface-3 rounded-lg transition-colors"
          >
            {saved ? "关闭" : "不保存，关闭"}
          </button>
          {!saved && (
            <button
              onClick={handleSaveVersion}
              disabled={saving}
              className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {saving ? "保存中..." : "保存新版本"}
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
  allBlocks?: ContentBlock[];  // 用于依赖选择
  isVirtual?: boolean;  // 是否是虚拟块（来自 ProjectField）
  onUpdate?: () => void;
}

export function ContentBlockEditor({ block, projectId, allBlocks = [], isVirtual = false, onUpdate }: ContentBlockEditorProps) {
  // 判断是否使用 Field API（虚拟块需要更新 ProjectField 表）
  const useFieldAPI = isVirtual || !!block.parent_id?.startsWith("virtual_");
  const [isEditing, setIsEditing] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState(block.name);
  const [editedContent, setEditedContent] = useState(block.content || "");
  const [showPromptModal, setShowPromptModal] = useState(false);
  const [showConstraintsModal, setShowConstraintsModal] = useState(false);
  const [showDependencyModal, setShowDependencyModal] = useState(false);
  
  
  // 编辑状态
  const [editedPrompt, setEditedPrompt] = useState(block.ai_prompt || "");
  const [savedPrompt, setSavedPrompt] = useState(block.ai_prompt || ""); // 本地追踪已保存的提示词
  const [editedConstraints, setEditedConstraints] = useState(block.constraints || {});
  const [selectedDependencies, setSelectedDependencies] = useState<string[]>(block.depends_on || []);
  const [aiPromptPurpose, setAiPromptPurpose] = useState("");
  const [generatingPrompt, setGeneratingPrompt] = useState(false);
  
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
  const [preAnswers, setPreAnswers] = useState<Record<string, string>>(block.pre_answers || {});
  const hasPreQuestions = (block.pre_questions?.length || 0) > 0;
  const [preQuestionsExpanded, setPreQuestionsExpanded] = useState(false);

  // ---- 生成逻辑（通过 Hook 统一管理） ----
  const {
    isGenerating, generatingContent, canGenerate, unmetDependencies,
    handleGenerate: _handleGenerate, handleStop: handleStopGeneration,
  } = useBlockGeneration({
    block, projectId, allBlocks, useFieldAPI,
    preAnswers, hasPreQuestions,
    onUpdate,
    onContentReady: (content) => setEditedContent(content),
  });

  const handleGenerate = async () => {
    // Editor 特有：退出编辑模式以显示流式内容
    setIsEditing(false);
    await _handleGenerate();
  };
  
  // 可选的依赖（排除自己和自己的子节点）
  // 允许选择：1. 所有 field 类型  2. 有特殊处理器的 phase 类型（如消费者调研、意图分析）
  const availableDependencies = allBlocks.filter(b => {
    // 排除自己
    if (b.id === block.id) return false;
    // 排除自己的子节点
    if (b.parent_id === block.id) return false;
    
    // 允许 field 类型
    if (b.block_type === "field") return true;
    // 允许有 special_handler 的 phase（意图分析、消费者调研、模拟、评估）
    if (b.block_type === "phase" && b.special_handler) return true;
    
    return false;
  });
  
  // 分组：特殊阶段 + 普通字段
  const specialDependencies = availableDependencies.filter(
    b => b.block_type === "phase" && b.special_handler
  );
  const fieldDependencies = availableDependencies.filter(
    b => b.block_type === "field"
  );
  
  useEffect(() => {
    // 生成中不要重置内容（会覆盖流式输出）
    // Hook 内部 isGenerating 已自动按 block.id 过滤，不在生成此块时为 false
    if (!isGenerating) {
      setEditedContent(block.content || "");
    }
    setEditedName(block.name);
    setEditedPrompt(block.ai_prompt || "");
    setSavedPrompt(block.ai_prompt || "");
    setEditedConstraints(block.constraints || {});
    setSelectedDependencies(block.depends_on || []);
    setPreAnswers(block.pre_answers || {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block.id, block.content, block.name, block.ai_prompt, block.depends_on, block.pre_answers]);
  
  // ===== 关键修复 1：挂载或切换 block 时，从 API 获取最新状态 =====
  // 解决：用户导航到其他块再回来时，本地缓存的 block 数据可能是旧的
  // （例如后台正在执行 eval，status 已经是 in_progress，但本地缓存还是 pending/completed）
  useEffect(() => {
    if (!block.id || block.id.startsWith("virtual_")) return;
    let cancelled = false;
    
    blockAPI.get(block.id).then(freshBlock => {
      if (cancelled) return;
      // 如果后端状态和本地不一致（例如后端是 in_progress 但本地不是），触发刷新
      if (freshBlock.status !== block.status || freshBlock.content !== block.content) {
        console.log(`[BlockEditor] 检测到数据不同步: block=${block.name}, local_status=${block.status}, server_status=${freshBlock.status}`);
        onUpdate?.(); // 触发整个 allBlocks 刷新
      }
    }).catch(() => {}); // 静默忽略（可能是虚拟块等）
    
    return () => { cancelled = true; };
  }, [block.id]);
  
  // ===== 关键修复 2：如果 block 状态是 in_progress 但当前组件没在流式生成，则轮询刷新 =====
  // 优化：先检查后端数据是否实际变化，只在变化时才触发父组件刷新
  // 避免每3秒无条件调用 onUpdate() 导致整棵树级联重渲染
  const pollStatusRef = useRef(block.status);
  const pollContentLenRef = useRef((block.content || "").length);
  useEffect(() => {
    pollStatusRef.current = block.status;
    pollContentLenRef.current = (block.content || "").length;
  }, [block.status, block.content]);
  
  useEffect(() => {
    if (block.status !== "in_progress" || isGenerating) return;
    if (block.id.startsWith("virtual_")) return;
    
    const pollInterval = setInterval(async () => {
      try {
        const fresh = await blockAPI.get(block.id);
        // 只在状态或内容实际变化时才触发全局刷新
        if (fresh.status !== pollStatusRef.current || 
            (fresh.content || "").length !== pollContentLenRef.current) {
          onUpdate?.();
        }
      } catch {
        // 静默忽略轮询错误
      }
    }, 3000);
    return () => clearInterval(pollInterval);
  }, [block.id, block.status, isGenerating]);
  
  // 保存预提问答案状态
  const [isSavingPreAnswers, setIsSavingPreAnswers] = useState(false);
  const [preAnswersSaved, setPreAnswersSaved] = useState(false);
  
  // 保存预提问答案
  const handleSavePreAnswers = async () => {
    setIsSavingPreAnswers(true);
    try {
      if (useFieldAPI) {
        await fieldAPI.update(block.id, { pre_answers: preAnswers });
      } else {
        await blockAPI.update(block.id, { pre_answers: preAnswers });
      }
      setPreAnswersSaved(true);
      setTimeout(() => setPreAnswersSaved(false), 2000);
      onUpdate?.();
      
      // 前端驱动自动触发链
      if (projectId) {
        runAutoTriggerChain(projectId, () => onUpdate?.()).catch(console.error);
      }
    } catch (err) {
      console.error("保存预提问答案失败:", err);
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsSavingPreAnswers(false);
    }
  };

  // 保存名称
  const handleSaveName = async () => {
    if (editedName.trim() && editedName !== block.name) {
      try {
        if (useFieldAPI) {
          await fieldAPI.update(block.id, { name: editedName.trim() });
        } else {
          await blockAPI.update(block.id, { name: editedName.trim() });
        }
        onUpdate?.();
      } catch (err) {
        console.error("更新名称失败:", err);
        alert("更新名称失败: " + (err instanceof Error ? err.message : "未知错误"));
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
        if (showPromptModal) setShowPromptModal(false);
        else if (showConstraintsModal) setShowConstraintsModal(false);
        else if (showDependencyModal) setShowDependencyModal(false);
        else if (versionWarning) setVersionWarning(null);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [showPromptModal, showConstraintsModal, showDependencyModal, versionWarning]);

  // 保存内容
  const handleSaveContent = async () => {
    try {
      let result: any;
      if (useFieldAPI) {
        result = await fieldAPI.update(block.id, { content: editedContent });
      } else {
        result = await blockAPI.update(block.id, { content: editedContent });
      }
      setIsEditing(false);
      onUpdate?.();
      
      // 检查是否有版本警告
      const warning = result?.version_warning;
      const affected = result?.affected_blocks || result?.affected_fields;
      if (warning) {
        setVersionWarning(warning);
        setAffectedBlocks(affected || null);
      }
    } catch (err) {
      console.error("保存失败:", err);
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
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
    } catch (e: any) {
      alert("生成提示词失败: " + (e.message || "未知错误"));
    } finally {
      setGeneratingPrompt(false);
    }
  };

  // 保存 AI 提示词
  const handleSavePrompt = async () => {
    try {
      if (useFieldAPI) {
        await fieldAPI.update(block.id, { ai_prompt: editedPrompt });
      } else {
        await blockAPI.update(block.id, { ai_prompt: editedPrompt });
      }
      setSavedPrompt(editedPrompt); // 乐观更新本地状态，立即反映到 UI
      setShowPromptModal(false);
      onUpdate?.();
    } catch (err) {
      console.error("保存提示词失败:", err);
      alert("保存提示词失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // 保存约束
  const handleSaveConstraints = async () => {
    try {
      if (useFieldAPI) {
        await fieldAPI.update(block.id, { constraints: editedConstraints });
      } else {
        await blockAPI.update(block.id, { constraints: editedConstraints });
      }
      setShowConstraintsModal(false);
      onUpdate?.();
    } catch (err) {
      console.error("保存约束失败:", err);
      alert("保存约束失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // 保存依赖
  const handleSaveDependencies = async () => {
    try {
      if (useFieldAPI) {
        // ProjectField 的依赖结构不同
        await fieldAPI.update(block.id, { 
          dependencies: { 
            depends_on: selectedDependencies,
            dependency_type: "all"
          }
        });
      } else {
        await blockAPI.update(block.id, { depends_on: selectedDependencies });
      }
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

  // 依赖块详情（UI 中显示依赖名称用）
  const dependencyBlocks = selectedDependencies
    .map(id => allBlocks.find(b => b.id === id))
    .filter(Boolean) as ContentBlock[];

  // 删除内容块
  const handleDelete = async () => {
    if (!confirm(`确定要删除「${block.name}」吗？此操作不可撤销。`)) return;
    try {
      if (useFieldAPI) {
        await fieldAPI.delete(block.id);
      } else {
        await blockAPI.delete(block.id);
      }
      onUpdate?.();
    } catch (err) {
      console.error("删除失败:", err);
      alert("删除失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  return (
    <div className="h-full flex flex-col p-6">
      {/* 面包屑导航 */}
      <div className="flex items-center gap-2 text-sm text-zinc-500 mb-4">
        <Folder className="w-4 h-4" />
        <span>内容块</span>
        <ChevronRight className="w-3 h-3" />
        <FileText className="w-4 h-4" />
        <span className="text-zinc-300">{block.name}</span>
      </div>

      {/* 主编辑卡片 */}
      <div className="flex-1 bg-surface-1 border border-surface-3 rounded-xl overflow-hidden flex flex-col">
        {/* 标题栏 */}
        <div className="px-5 py-4 border-b border-surface-3 flex items-center justify-between">
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
                title="点击编辑名称"
              >
                {block.name} <span className="text-xs text-zinc-600">✏️</span>
              </h2>
            )}
            
            <span className={`px-2 py-0.5 text-xs rounded ${
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
          
          {/* 操作按钮 */}
          <div className="flex items-center gap-2">
            {/* 生成中：显示停止按钮 */}
            {isGenerating && (
              <button
                onClick={handleStopGeneration}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-red-600 hover:bg-red-700 text-white transition-colors"
                title="停止生成"
              >
                <Square className="w-4 h-4" />
                停止生成
              </button>
            )}
            {/* 生成按钮 */}
            {block.status !== "completed" && !isGenerating && (
              <button
                onClick={handleGenerate}
                disabled={!canGenerate}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors ${
                  canGenerate
                    ? "bg-brand-600 hover:bg-brand-700 text-white"
                    : "bg-zinc-700 text-zinc-500 cursor-not-allowed"
                }`}
                title={!canGenerate ? `依赖内容为空: ${unmetDependencies.map(d => d.name).join(", ")}` : "生成内容"}
              >
                <Play className="w-4 h-4" />
                生成
              </button>
            )}
            
            {/* 依赖内容为空警告 */}
            {!canGenerate && !isGenerating && (
              <span className="text-xs text-amber-500" title={`依赖内容为空: ${unmetDependencies.map(d => d.name).join(", ")}`}>
                {unmetDependencies.length}个依赖内容为空
              </span>
            )}
            
            {/* 用户确认按钮：need_review 且有内容但未确认 */}
            {block.need_review && block.status === "in_progress" && block.content && !isGenerating && (
              <button
                onClick={async () => {
                  try {
                    await blockAPI.confirm(block.id);
                    onUpdate?.();
                    // 确认后触发下游自动生成链
                    runAutoTriggerChain(projectId, () => onUpdate?.()).catch(console.error);
                  } catch (err) {
                    console.error("确认失败:", err);
                    alert("确认失败: " + (err instanceof Error ? err.message : "未知错误"));
                  }
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors"
              >
                <Check className="w-4 h-4" /> 确认
              </button>
            )}
            
            {/* 重新生成按钮 */}
            {(block.status === "completed" || (block.status === "in_progress" && block.content)) && !isGenerating && (
              <button
                onClick={handleGenerate}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-500/30 rounded-lg transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                重新生成
              </button>
            )}
            
            {isGenerating && (
              <span className="text-sm text-brand-400 animate-pulse">生成中...</span>
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
              className="p-1.5 text-zinc-500 hover:text-red-400 transition-colors"
              title="删除此内容块"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 配置区域 */}
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
            {savedPrompt ? "已配置提示词" : "未配置提示词"}
          </button>
          
          {/* 约束配置 */}
          <button
            onClick={() => setShowConstraintsModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-surface-4 bg-surface-2 text-zinc-400 hover:bg-surface-3 rounded-lg transition-colors"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            约束配置
            {block.constraints?.max_length && (
              <span className="ml-1 px-1.5 py-0.5 bg-surface-3 rounded text-zinc-500">
                ≤{block.constraints.max_length}字
              </span>
            )}
          </button>
          
          {/* 依赖配置 */}
          <button
            onClick={() => setShowDependencyModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-surface-4 bg-surface-2 text-zinc-400 hover:bg-surface-3 rounded-lg transition-colors"
          >
            <Workflow className="w-3.5 h-3.5" />
            {dependencyBlocks.length > 0 ? (
              <span className="flex items-center gap-1">
                依赖:
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
              <span className="text-zinc-500">无依赖（点击配置）</span>
            )}
          </button>
          
          {/* need_review 状态 */}
          <span className={`flex items-center gap-1 px-2 py-1 text-xs rounded ${
            block.need_review 
              ? "bg-amber-600/10 text-amber-400"
              : "bg-emerald-600/10 text-emerald-400"
          }`}>
            {block.need_review ? <ShieldCheck className="w-3.5 h-3.5" /> : <Zap className="w-3.5 h-3.5" />}
            {block.need_review ? "需要人工确认" : "自动执行"}
          </span>
        </div>

        {/* 生成前提问区域（可折叠） */}
        {hasPreQuestions && (
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
                <span className="text-amber-400 text-sm font-medium">生成前提问</span>
                <span className="text-xs text-zinc-500">
                  ({Object.values(preAnswers).filter(v => v && v.trim()).length}/{block.pre_questions?.length || 0} 已回答)
                </span>
              </div>
              <div className="flex items-center gap-2">
                {preAnswersSaved && (
                  <span className="text-xs text-green-400">✓ 已保存</span>
                )}
              </div>
            </button>
            {preQuestionsExpanded && (
              <div className="px-5 py-4 bg-amber-900/10">
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
                        placeholder="请输入回答..."
                        className="w-full px-3 py-2 bg-surface-2 border border-amber-500/30 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                      />
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between mt-3">
                  <p className="text-xs text-amber-500/60">
                    💡 答案会作为生成内容的上下文传递给 AI
                  </p>
                  <button
                    onClick={handleSavePreAnswers}
                    disabled={isSavingPreAnswers}
                    className="px-3 py-1 text-xs bg-amber-600 hover:bg-amber-700 disabled:bg-amber-800 text-white rounded transition-colors"
                  >
                    {isSavingPreAnswers ? "保存中..." : "保存回答"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 内容区域 */}
        <div className="flex-1 p-5 overflow-y-auto">
          {/* Eval V2 专用字段编辑器 */}
          {block.special_handler && getEvalFieldEditor(block.special_handler) ? (
            (() => {
              const EvalEditor = getEvalFieldEditor(block.special_handler!)!;
              return <EvalEditor block={block} projectId={projectId} onUpdate={onUpdate} />;
            })()
          ) : isEditing ? (
            <div className="h-full flex flex-col gap-3">
              <textarea
                value={editedContent}
                onChange={(e) => setEditedContent(e.target.value)}
                className="flex-1 w-full bg-surface-2 border border-surface-3 rounded-lg p-4 text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none font-mono text-sm"
                placeholder="在此编辑内容..."
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => {
                    setEditedContent(block.content || "");
                    setIsEditing(false);
                  }}
                  className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleSaveContent}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
                >
                  <Save className="w-4 h-4" />
                  保存
                </button>
              </div>
            </div>
          ) : (
            <div 
              className="min-h-[200px] cursor-pointer group"
              onClick={() => setIsEditing(true)}
            >
              {isGenerating ? (
                <div className="prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{generatingContent || "正在生成..."}</ReactMarkdown>
                  <span className="inline-block w-2 h-4 bg-brand-500 animate-pulse" />
                </div>
              ) : block.status === "in_progress" && !block.content ? (
                <div className="flex items-center gap-2 py-8 justify-center">
                  <span className="inline-block w-2 h-4 bg-brand-500 animate-pulse" />
                  <span className="text-sm text-brand-400 animate-pulse">后台生成中，请稍候...</span>
                </div>
              ) : block.content ? (
                <div className="relative">
                  <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                    <button 
                      onClick={(e) => { e.stopPropagation(); handleCopyContent(); }}
                      className="flex items-center gap-1 px-2 py-1 text-xs bg-surface-2 border border-surface-3 text-zinc-400 hover:text-zinc-200 rounded"
                      title="复制全文（Markdown格式）"
                    >
                      {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
                      {copied ? "已复制" : "复制"}
                    </button>
                    <button 
                      onClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
                      className="flex items-center gap-1 px-2 py-1 text-xs bg-surface-2 border border-surface-3 text-zinc-400 hover:text-zinc-200 rounded"
                    >
                      <Pencil className="w-3 h-3" />
                      编辑
                    </button>
                  </div>
                  <div className="prose prose-invert prose-sm max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.content}</ReactMarkdown>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-[200px] text-zinc-500 border-2 border-dashed border-surface-3 rounded-lg">
                  <Pencil className="w-8 h-8 mb-2 opacity-50" />
                  <p>点击此处编辑内容</p>
                  <p className="text-xs mt-1">或使用「生成」按钮让 AI 生成</p>
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
              <h3 className="text-lg font-semibold text-zinc-200">编辑 AI 提示词</h3>
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

      {/* 约束配置弹窗 */}
      {showConstraintsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-lg bg-surface-1 border border-surface-3 rounded-xl shadow-2xl">
            <div className="px-5 py-4 border-b border-surface-3 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-zinc-200">约束配置</h3>
              <button 
                onClick={() => setShowConstraintsModal(false)}
                className="p-1 text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              {/* 最大字数 */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">最大字数</label>
                <input
                  type="number"
                  value={editedConstraints.max_length || ""}
                  onChange={(e) => setEditedConstraints({
                    ...editedConstraints,
                    max_length: e.target.value ? parseInt(e.target.value) : null
                  })}
                  className="w-full bg-surface-2 border border-surface-3 rounded-lg px-3 py-2 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="不限制"
                />
              </div>
              
              {/* 输出格式 */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">输出格式</label>
                <select
                  value={editedConstraints.output_format || "markdown"}
                  onChange={(e) => setEditedConstraints({
                    ...editedConstraints,
                    output_format: e.target.value
                  })}
                  className="w-full bg-surface-2 border border-surface-3 rounded-lg px-3 py-2 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  <option value="markdown">Markdown</option>
                  <option value="plain_text">纯文本</option>
                  <option value="json">JSON</option>
                  <option value="list">列表</option>
                </select>
              </div>
              
              {/* 结构模板 */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">结构模板</label>
                <input
                  type="text"
                  value={editedConstraints.structure || ""}
                  onChange={(e) => setEditedConstraints({
                    ...editedConstraints,
                    structure: e.target.value || null
                  })}
                  className="w-full bg-surface-2 border border-surface-3 rounded-lg px-3 py-2 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="如：标题 + 正文 + 总结"
                />
              </div>
              
              {/* 示例 */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">输出示例</label>
                <textarea
                  value={editedConstraints.example || ""}
                  onChange={(e) => setEditedConstraints({
                    ...editedConstraints,
                    example: e.target.value || null
                  })}
                  rows={3}
                  className="w-full bg-surface-2 border border-surface-3 rounded-lg px-3 py-2 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
                  placeholder="提供一个期望输出的示例..."
                />
              </div>
            </div>
            <div className="px-5 py-4 border-t border-surface-3 flex justify-end gap-3">
              <button
                onClick={() => setShowConstraintsModal(false)}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
              >
                取消
              </button>
              <button
                onClick={handleSaveConstraints}
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-lg bg-surface-1 border border-surface-3 rounded-xl shadow-2xl">
            <div className="px-5 py-4 border-b border-surface-3 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-zinc-200">设置依赖关系</h3>
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
                <div className="space-y-4 max-h-80 overflow-y-auto">
                  {/* 特殊阶段区域 */}
                  {specialDependencies.length > 0 && (
                    <div>
                      <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2 flex items-center gap-1">
                        📌 特殊阶段（可作为上下文引用）
                      </h4>
                      <div className="space-y-2">
                        {specialDependencies.map(dep => (
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
                                <span className="px-1.5 py-0.5 text-xs rounded bg-purple-600/20 text-purple-400">
                                  {dep.special_handler === "intent" ? "意图分析" :
                                   dep.special_handler === "research" ? "消费者调研" :
                                   dep.special_handler === "simulate" ? "模拟测试" :
                                   dep.special_handler === "evaluate" ? "评估结果" : dep.special_handler}
                                </span>
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
                    </div>
                  )}
                  
                  {/* 普通字段区域 */}
                  {fieldDependencies.length > 0 && (
                    <div>
                      <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2 flex items-center gap-1">
                        内容块
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
                                  {dep.status === "completed" ? "已完成" : (dep.content && dep.content.trim() !== "") ? "待确认" : "未完成"}
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
                保存依赖关系
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== 版本警告弹窗 ===== */}
      {versionWarning && (
        <VersionWarningDialog
          projectId={projectId}
          warning={versionWarning}
          affectedBlocks={affectedBlocks}
          onClose={() => { setVersionWarning(null); setAffectedBlocks(null); }}
          onVersionCreated={() => {
            setVersionWarning(null);
            setAffectedBlocks(null);
            onUpdate?.();
          }}
        />
      )}
    </div>
  );
}
