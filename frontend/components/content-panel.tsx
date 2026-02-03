// frontend/components/content-panel.tsx
// 功能: 中栏内容展示面板，支持字段依赖选择和生成
// 主要组件: ContentPanel, FieldCard
// 新增: 依赖选择弹窗、生成按钮、依赖状态显示、模拟阶段特殊面板

"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { PHASE_NAMES } from "@/lib/utils";
import { fieldAPI } from "@/lib/api";
import type { Field } from "@/lib/api";
import { SimulationPanel } from "./simulation-panel";

interface ContentPanelProps {
  projectId: string | null;
  currentPhase: string;
  fields: Field[];
  onFieldUpdate?: (fieldId: string, content: string) => void;
  onFieldsChange?: () => void;
}

export function ContentPanel({
  projectId,
  currentPhase,
  fields,
  onFieldUpdate,
  onFieldsChange,
}: ContentPanelProps) {
  const phaseFields = fields.filter((f) => f.phase === currentPhase);
  const allCompletedFields = fields.filter((f) => f.status === "completed");

  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-500">
        <div className="text-center">
          <p className="text-lg mb-2">请选择或创建一个项目</p>
          <p className="text-sm">在左侧选择项目开始工作</p>
        </div>
      </div>
    );
  }

  // 消费者模拟阶段使用专用面板
  if (currentPhase === "simulate") {
    return (
      <SimulationPanel
        projectId={projectId}
        fields={fields}
        onSimulationCreated={onFieldsChange}
      />
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* 阶段标题 */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-zinc-100">
          {PHASE_NAMES[currentPhase] || currentPhase}
        </h1>
        <p className="text-zinc-500 mt-1">
          {getPhaseDescription(currentPhase)}
        </p>
      </div>

      {/* 字段列表 */}
      {phaseFields.length > 0 ? (
        <div className="space-y-6">
          {phaseFields.map((field) => (
            <FieldCard
              key={field.id}
              field={field}
              allFields={fields}
              onUpdate={(content) => onFieldUpdate?.(field.id, content)}
              onFieldsChange={onFieldsChange}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-zinc-500">
          <p>当前阶段暂无内容</p>
          <p className="text-sm mt-2">
            在右侧与 AI Agent 对话开始生产内容
          </p>
        </div>
      )}
    </div>
  );
}

interface FieldCardProps {
  field: Field;
  allFields: Field[];
  onUpdate?: (content: string) => void;
  onFieldsChange?: () => void;
}

function FieldCard({ field, allFields, onUpdate, onFieldsChange }: FieldCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [content, setContent] = useState(field.content);
  const [showDependencyModal, setShowDependencyModal] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatingContent, setGeneratingContent] = useState("");

  useEffect(() => {
    setContent(field.content);
  }, [field.content]);

  // 获取依赖字段信息
  const dependsOnIds = field.dependencies?.depends_on || [];
  const dependencyFields = allFields.filter((f) => dependsOnIds.includes(f.id));
  const unmetDependencies = dependencyFields.filter((f) => f.status !== "completed");
  const canGenerate = unmetDependencies.length === 0;

  const handleSave = () => {
    onUpdate?.(content);
    setIsEditing(false);
  };

  const handleGenerate = async () => {
    if (!canGenerate) {
      alert(`请先完成依赖字段: ${unmetDependencies.map(f => f.name).join(", ")}`);
      return;
    }

    setIsGenerating(true);
    setGeneratingContent("");

    try {
      // 使用流式生成
      const response = await fetch(`http://localhost:8000/api/fields/${field.id}/generate/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pre_answers: field.pre_answers || {} }),
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const text = decoder.decode(value);
          const lines = text.split("\n");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.chunk) {
                  setGeneratingContent((prev) => prev + data.chunk);
                }
                if (data.done) {
                  onFieldsChange?.();
                }
              } catch {}
            }
          }
        }
      }
    } catch (err) {
      console.error("生成失败:", err);
      alert("生成失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsGenerating(false);
    }
  };

  const handleUpdateDependencies = async (newDependsOn: string[]) => {
    try {
      await fieldAPI.update(field.id, {
        dependencies: {
          depends_on: newDependsOn,
          dependency_type: field.dependencies?.dependency_type || "all",
        },
      });
      onFieldsChange?.();
      setShowDependencyModal(false);
    } catch (err) {
      alert("更新依赖失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  return (
    <div className="bg-surface-2 rounded-xl border border-surface-3 overflow-hidden">
      {/* 字段头部 */}
      <div className="px-4 py-3 border-b border-surface-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-medium text-zinc-200">{field.name}</h3>
            <div className="flex items-center gap-2 mt-1">
              <span className={`text-xs px-2 py-0.5 rounded ${
                field.status === "completed" 
                  ? "bg-green-600/20 text-green-400"
                  : field.status === "generating"
                  ? "bg-yellow-600/20 text-yellow-400"
                  : "bg-zinc-600/20 text-zinc-400"
              }`}>
                {field.status === "completed" ? "已生成" 
                  : field.status === "generating" ? "生成中..." 
                  : "待生成"}
              </span>
            </div>
          </div>
          
          <div className="flex gap-2">
            {field.status !== "completed" && !isGenerating && (
              <button
                onClick={handleGenerate}
                disabled={!canGenerate}
                className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                  canGenerate
                    ? "bg-brand-600 hover:bg-brand-700 text-white"
                    : "bg-zinc-700 text-zinc-500 cursor-not-allowed"
                }`}
                title={canGenerate ? "生成内容" : `依赖未满足: ${unmetDependencies.map(f => f.name).join(", ")}`}
              >
                生成
              </button>
            )}
            
            {isEditing ? (
              <>
                <button
                  onClick={handleSave}
                  className="px-3 py-1 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors"
                >
                  保存
                </button>
                <button
                  onClick={() => {
                    setContent(field.content);
                    setIsEditing(false);
                  }}
                  className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
                >
                  取消
                </button>
              </>
            ) : (
              <button
                onClick={() => setIsEditing(true)}
                className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
              >
                编辑
              </button>
            )}
          </div>
        </div>

        {/* 依赖关系显示 */}
        <div className="mt-2 flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setShowDependencyModal(true)}
            className="text-xs text-zinc-500 hover:text-zinc-300 flex items-center gap-1"
          >
            <span>📎 依赖:</span>
            {dependencyFields.length > 0 ? (
              dependencyFields.map((df) => (
                <span
                  key={df.id}
                  className={`px-1.5 py-0.5 rounded text-xs ${
                    df.status === "completed"
                      ? "bg-green-600/20 text-green-400"
                      : "bg-red-600/20 text-red-400"
                  }`}
                >
                  {df.name}
                </span>
              ))
            ) : (
              <span className="text-zinc-600">无</span>
            )}
            <span className="text-zinc-600 ml-1">（点击编辑）</span>
          </button>
        </div>
      </div>

      {/* 字段内容 */}
      <div className="p-4">
        {isGenerating ? (
          <div className="bg-surface-1 border border-surface-3 rounded-lg p-3">
            <div className="text-xs text-brand-400 mb-2">正在生成...</div>
            <div className="whitespace-pre-wrap text-zinc-300 animate-pulse">
              {generatingContent || "⏳ 准备中..."}
            </div>
          </div>
        ) : isEditing ? (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full min-h-[200px] bg-surface-1 border border-surface-3 rounded-lg p-3 text-zinc-200 resize-y focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        ) : (
          <div className="prose prose-invert max-w-none prose-headings:text-zinc-100 prose-p:text-zinc-300 prose-li:text-zinc-300 prose-strong:text-zinc-200">
            {field.content ? (
              <ReactMarkdown>{field.content}</ReactMarkdown>
            ) : (
              <p className="text-zinc-500 italic">暂无内容，点击"生成"按钮开始</p>
            )}
          </div>
        )}
      </div>

      {/* 依赖选择弹窗 */}
      {showDependencyModal && (
        <DependencyModal
          field={field}
          allFields={allFields}
          onClose={() => setShowDependencyModal(false)}
          onSave={handleUpdateDependencies}
        />
      )}
    </div>
  );
}

interface DependencyModalProps {
  field: Field;
  allFields: Field[];
  onClose: () => void;
  onSave: (dependsOn: string[]) => void;
}

function DependencyModal({ field, allFields, onClose, onSave }: DependencyModalProps) {
  const [selectedIds, setSelectedIds] = useState<string[]>(
    field.dependencies?.depends_on || []
  );

  // 可选的依赖字段（排除自己）
  const availableFields = allFields.filter((f) => f.id !== field.id);

  const toggleField = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden">
        <div className="px-4 py-3 border-b border-surface-3">
          <h3 className="font-medium text-zinc-200">设置依赖关系</h3>
          <p className="text-xs text-zinc-500 mt-1">
            选择生成"{field.name}"前需要先完成的字段
          </p>
        </div>

        <div className="p-4 max-h-[50vh] overflow-y-auto space-y-2">
          {availableFields.length > 0 ? (
            availableFields.map((f) => (
              <label
                key={f.id}
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-surface-3 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selectedIds.includes(f.id)}
                  onChange={() => toggleField(f.id)}
                  className="rounded"
                />
                <div className="flex-1">
                  <div className="text-sm text-zinc-200">{f.name}</div>
                  <div className="text-xs text-zinc-500">
                    {f.phase} · {f.status === "completed" ? "已完成" : "未完成"}
                  </div>
                </div>
                <span
                  className={`w-2 h-2 rounded-full ${
                    f.status === "completed" ? "bg-green-500" : "bg-zinc-600"
                  }`}
                />
              </label>
            ))
          ) : (
            <p className="text-zinc-500 text-center py-4">暂无可选的依赖字段</p>
          )}
        </div>

        <div className="px-4 py-3 border-t border-surface-3 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
          >
            取消
          </button>
          <button
            onClick={() => onSave(selectedIds)}
            className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

function getPhaseDescription(phase: string): string {
  const descriptions: Record<string, string> = {
    intent: "澄清内容生产的核心意图和目标",
    research: "调研目标用户，了解痛点和需求",
    design_inner: "设计内容生产方案和大纲",
    produce_inner: "生产核心内容",
    design_outer: "设计外延传播方案",
    produce_outer: "为各渠道生产营销内容",
    simulate: "模拟用户体验，收集反馈",
    evaluate: "全面评估内容质量",
  };
  return descriptions[phase] || "";
}
