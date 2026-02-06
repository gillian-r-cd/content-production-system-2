// frontend/components/content-block-editor.tsx
// 功能: ContentBlock 完整编辑器，用于树形视图中选中的内容块
// 提供与 FieldCard 相同的功能：编辑内容、AI 提示词、约束、依赖、生成等

"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { blockAPI, fieldAPI } from "@/lib/api";
import type { ContentBlock } from "@/lib/api";
import { 
  FileText, 
  Folder, 
  ChevronRight, 
  Sparkles, 
  Save, 
  Edit2, 
  Trash2,
  Settings,
  Link,
  RefreshCw,
  X
} from "lucide-react";

interface ContentBlockEditorProps {
  block: ContentBlock;
  projectId: string;
  allBlocks?: ContentBlock[];  // 用于依赖选择
  isVirtual?: boolean;  // 是否是虚拟块（来自 ProjectField）
  onUpdate?: () => void;
}

export function ContentBlockEditor({ block, projectId, allBlocks = [], isVirtual = false, onUpdate }: ContentBlockEditorProps) {
  // 判断是否使用 Field API（虚拟块需要更新 ProjectField 表）
  const useFieldAPI = isVirtual || block.parent_id?.startsWith("virtual_");
  const [isEditing, setIsEditing] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState(block.name);
  const [editedContent, setEditedContent] = useState(block.content || "");
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatingContent, setGeneratingContent] = useState("");
  const [showPromptModal, setShowPromptModal] = useState(false);
  const [showConstraintsModal, setShowConstraintsModal] = useState(false);
  const [showDependencyModal, setShowDependencyModal] = useState(false);
  
  // 编辑状态
  const [editedPrompt, setEditedPrompt] = useState(block.ai_prompt || "");
  const [editedConstraints, setEditedConstraints] = useState(block.constraints || {});
  const [selectedDependencies, setSelectedDependencies] = useState<string[]>(block.depends_on || []);
  
  // 生成前提问状态
  const [preAnswers, setPreAnswers] = useState<Record<string, string>>(block.pre_answers || {});
  const hasPreQuestions = (block.pre_questions?.length || 0) > 0;
  
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
    setEditedContent(block.content || "");
    setEditedName(block.name);
    setEditedPrompt(block.ai_prompt || "");
    setEditedConstraints(block.constraints || {});
    setSelectedDependencies(block.depends_on || []);
    setPreAnswers(block.pre_answers || {});
  }, [block]);
  
  // 保存预提问答案
  const handleSavePreAnswers = async () => {
    try {
      if (useFieldAPI) {
        await fieldAPI.update(block.id, { pre_answers: preAnswers });
      } else {
        await blockAPI.update(block.id, { pre_answers: preAnswers });
      }
      onUpdate?.();
    } catch (err) {
      console.error("保存预提问答案失败:", err);
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

  // 保存内容
  const handleSaveContent = async () => {
    try {
      if (useFieldAPI) {
        await fieldAPI.update(block.id, { content: editedContent });
      } else {
        await blockAPI.update(block.id, { content: editedContent });
      }
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
      if (useFieldAPI) {
        await fieldAPI.update(block.id, { ai_prompt: editedPrompt });
      } else {
        await blockAPI.update(block.id, { ai_prompt: editedPrompt });
      }
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

  // 获取依赖的内容块详情
  const dependencyBlocks = selectedDependencies
    .map(id => allBlocks.find(b => b.id === id))
    .filter(Boolean) as ContentBlock[];

  // 检查依赖是否满足（只要有内容就满足，不需要状态是 completed）
  const unmetDependencies = dependencyBlocks.filter(d => !d.content || !d.content.trim());
  const canGenerate = unmetDependencies.length === 0;

  // 生成内容（使用流式 API）
  const handleGenerate = async () => {
    // 前端检查依赖（只要依赖有内容就可以生成）
    if (!canGenerate) {
      alert(`以下依赖内容为空:\n${unmetDependencies.map(d => `• ${d.name}`).join("\n")}`);
      return;
    }
    
    // 先保存预提问答案
    if (hasPreQuestions && Object.keys(preAnswers).length > 0) {
      await handleSavePreAnswers();
    }
    
    setIsGenerating(true);
    setGeneratingContent("");
    
    try {
      if (useFieldAPI) {
        // 虚拟块使用 Field API 生成，传递预提问答案
        const result = await fieldAPI.generate(block.id, preAnswers);
        setEditedContent(result.content);
        onUpdate?.();
      } else {
        // 使用流式生成（预提问答案已保存到后端）
        const response = await blockAPI.generateStream(block.id);
        if (!response.ok) {
          const error = await response.json().catch(() => ({ detail: "生成失败" }));
          throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const reader = response.body?.getReader();
        if (!reader) throw new Error("无法获取响应流");
        
        const decoder = new TextDecoder();
        let accumulatedContent = "";
        
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");
          
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.chunk) {
                  accumulatedContent += data.chunk;
                  setGeneratingContent(accumulatedContent);
                }
                if (data.done) {
                  setEditedContent(data.content);
                  onUpdate?.();
                }
                if (data.error) {
                  throw new Error(data.error);
                }
              } catch (parseErr) {
                // 忽略解析错误
              }
            }
          }
        }
      }
    } catch (err) {
      console.error("生成失败:", err);
      alert("生成失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsGenerating(false);
      setGeneratingContent("");
    }
  };

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
              "bg-zinc-700 text-zinc-400"
            }`}>
              {block.status === "completed" ? "已完成" :
               block.status === "in_progress" ? "进行中" : "待处理"}
            </span>
          </div>
          
          {/* 操作按钮 */}
          <div className="flex items-center gap-2">
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
                <Sparkles className="w-4 h-4" />
                生成
              </button>
            )}
            
            {/* 依赖内容为空警告 */}
            {!canGenerate && !isGenerating && (
              <span className="text-xs text-amber-500" title={`依赖内容为空: ${unmetDependencies.map(d => d.name).join(", ")}`}>
                ⚠️ {unmetDependencies.length}个依赖内容为空
              </span>
            )}
            
            {/* 重新生成按钮 */}
            {block.status === "completed" && !isGenerating && (
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
              block.ai_prompt 
                ? "border-brand-500/30 bg-brand-600/10 text-brand-400 hover:bg-brand-600/20"
                : "border-red-500/30 bg-red-600/10 text-red-400 hover:bg-red-600/20"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            {block.ai_prompt ? "已配置提示词" : "⚠️ 未配置提示词"}
          </button>
          
          {/* 约束配置 */}
          <button
            onClick={() => setShowConstraintsModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-surface-4 bg-surface-2 text-zinc-400 hover:bg-surface-3 rounded-lg transition-colors"
          >
            <Settings className="w-3.5 h-3.5" />
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
            <Link className="w-3.5 h-3.5" />
            {dependencyBlocks.length > 0 ? (
              <span className="flex items-center gap-1">
                依赖:
                {dependencyBlocks.map(dep => (
                  <span key={dep.id} className={`px-1.5 py-0.5 rounded ${
                    dep.status === "completed" 
                      ? "bg-green-600/20 text-green-400" 
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
          <span className={`px-2 py-1 text-xs rounded ${
            block.need_review 
              ? "bg-amber-600/10 text-amber-400"
              : "bg-green-600/10 text-green-400"
          }`}>
            {block.need_review ? "需要人工确认" : "自动执行"}
          </span>
        </div>

        {/* 生成前提问区域 */}
        {hasPreQuestions && (
          <div className="px-5 py-4 bg-amber-900/10 border-b border-amber-600/20">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-amber-400 text-sm font-medium">📝 生成前请先回答以下问题</span>
              <span className="text-xs text-amber-500/60">（回答后内容将自动保存）</span>
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
                    }}
                    onBlur={handleSavePreAnswers}
                    placeholder="请输入回答..."
                    className="w-full px-3 py-2 bg-surface-2 border border-amber-500/30 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 内容区域 */}
        <div className="flex-1 p-5 overflow-y-auto">
          {isEditing ? (
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
                  <ReactMarkdown>{generatingContent || "正在生成..."}</ReactMarkdown>
                  <span className="inline-block w-2 h-4 bg-brand-500 animate-pulse" />
                </div>
              ) : block.content ? (
                <div className="relative">
                  <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button className="flex items-center gap-1 px-2 py-1 text-xs bg-surface-2 border border-surface-3 text-zinc-400 hover:text-zinc-200 rounded">
                      <Edit2 className="w-3 h-3" />
                      编辑
                    </button>
                  </div>
                  <div className="prose prose-invert prose-sm max-w-none">
                    <ReactMarkdown>{block.content}</ReactMarkdown>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-[200px] text-zinc-500 border-2 border-dashed border-surface-3 rounded-lg">
                  <Edit2 className="w-8 h-8 mb-2 opacity-50" />
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
            <div className="p-5">
              <textarea
                value={editedPrompt}
                onChange={(e) => setEditedPrompt(e.target.value)}
                rows={8}
                className="w-full bg-surface-2 border border-surface-3 rounded-lg p-4 text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
                placeholder="输入 AI 生成此内容块时使用的提示词..."
              />
              <p className="mt-2 text-xs text-zinc-500">
                提示词会与项目上下文（创作者特质、意图、用户画像）一起发送给 AI，用于生成内容。
              </p>
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
                                    ? "bg-green-600/20 text-green-400" 
                                    : "bg-zinc-700 text-zinc-400"
                                }`}>
                                  {dep.status === "completed" ? "已完成" : "未完成"}
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
                        📝 内容字段
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
                                    ? "bg-green-600/20 text-green-400" 
                                    : "bg-zinc-700 text-zinc-400"
                                }`}>
                                  {dep.status === "completed" ? "已完成" : "未完成"}
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
    </div>
  );
}
