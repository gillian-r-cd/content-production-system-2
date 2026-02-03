// frontend/components/content-panel.tsx
// 功能: 中栏内容展示面板，支持字段依赖选择和生成
// 主要组件: ContentPanel, FieldCard
// 新增: 依赖选择弹窗、生成按钮、依赖状态显示、模拟阶段特殊面板

"use client";

import { useState, useEffect, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import { PHASE_NAMES, PROJECT_PHASES } from "@/lib/utils";
import { fieldAPI, agentAPI } from "@/lib/api";
import type { Field } from "@/lib/api";
import { SimulationPanel } from "./simulation-panel";
import { ProposalSelector } from "./proposal-selector";
import { ResearchPanel } from "./research-panel";

interface ContentPanelProps {
  projectId: string | null;
  currentPhase: string;
  phaseStatus?: Record<string, string>;  // 各阶段状态
  fields: Field[];
  onFieldUpdate?: (fieldId: string, content: string) => void;
  onFieldsChange?: () => void;
  onPhaseAdvance?: () => void;  // 阶段推进后的回调
}

export function ContentPanel({
  projectId,
  currentPhase,
  phaseStatus = {},
  fields,
  onFieldUpdate,
  onFieldsChange,
  onPhaseAdvance,
}: ContentPanelProps) {
  const [isAdvancing, setIsAdvancing] = useState(false);
  const [autoGeneratingFieldId, setAutoGeneratingFieldId] = useState<string | null>(null);
  const [showFieldTemplateModal, setShowFieldTemplateModal] = useState(false);
  const [fieldTemplates, setFieldTemplates] = useState<any[]>([]);
  
  const phaseFields = fields.filter((f) => f.phase === currentPhase);
  const allCompletedFields = fields.filter((f) => f.status === "completed");
  const completedFieldIds = new Set(allCompletedFields.map(f => f.id));

  // 加载字段模板
  useEffect(() => {
    import("@/lib/api").then(({ settingsAPI }) => {
      settingsAPI.listFieldTemplates().then(setFieldTemplates).catch(console.error);
    });
  }, []);

  // 添加空字段
  const handleAddEmptyField = async () => {
    if (!projectId) return;
    try {
      await fieldAPI.create({
        project_id: projectId,
        phase: currentPhase,
        name: `新字段 ${phaseFields.length + 1}`,
        field_type: "richtext",
        content: "",
        status: "pending",
        ai_prompt: "",  // 空字符串，在约束弹窗中设置
        dependencies: { depends_on: [], dependency_type: "all" },
        need_review: true,
      });
      onFieldsChange?.();
    } catch (err) {
      console.error("添加字段失败:", err);
      alert("添加字段失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // 从模板添加字段
  const handleAddFromTemplate = async (template: any) => {
    if (!projectId) return;
    try {
      const templateFields = template.fields || [];
      
      // 获取现有字段名以处理重复
      const existingNames = phaseFields.map(f => f.name);
      
      // 生成唯一名称的辅助函数
      const getUniqueName = (baseName: string): string => {
        if (!existingNames.includes(baseName)) {
          existingNames.push(baseName);
          return baseName;
        }
        let counter = 1;
        while (existingNames.includes(`${baseName} ${counter}`)) {
          counter++;
        }
        const uniqueName = `${baseName} ${counter}`;
        existingNames.push(uniqueName);
        return uniqueName;
      };
      
      // 第一轮：创建所有字段，记录 name -> id 映射
      const nameToIdMap: Record<string, string> = {};
      const createdFields: any[] = [];
      
      for (const tf of templateFields) {
        const uniqueName = getUniqueName(tf.name);
        const newField = await fieldAPI.create({
          project_id: projectId,
          phase: currentPhase,
          name: uniqueName,
          field_type: tf.type || "richtext",
          content: "",
          status: "pending",
          ai_prompt: tf.ai_prompt || "",
          pre_questions: tf.pre_questions || [],
          dependencies: { depends_on: [], dependency_type: "all" },
          need_review: true,
        });
        nameToIdMap[tf.name] = newField.id;
        createdFields.push({ field: newField, templateField: tf });
      }
      
      // 第二轮：更新依赖关系（将模板中的字段名转换为实际的字段 ID）
      for (const { field, templateField } of createdFields) {
        const templateDeps = templateField.depends_on || [];
        if (templateDeps.length > 0) {
          const realDepsIds = templateDeps
            .map((depName: string) => nameToIdMap[depName])
            .filter(Boolean);
          
          if (realDepsIds.length > 0) {
            await fieldAPI.update(field.id, {
              dependencies: { depends_on: realDepsIds, dependency_type: "all" },
            });
          }
        }
      }
      
      setShowFieldTemplateModal(false);
      onFieldsChange?.();
    } catch (err) {
      console.error("从模板添加失败:", err);
      alert("从模板添加失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // 自动触发生成：检查是否有字段可以自动生成
  const checkAndAutoGenerate = async () => {
    if (autoGeneratingFieldId) return; // 已有自动生成在进行中
    
    // 找到可以自动生成的字段：pending、need_review=false、依赖已满足
    const autoGeneratableField = phaseFields.find(field => {
      if (field.status !== "pending") return false;
      if (field.need_review !== false) return false; // 需要人工确认的跳过
      
      const dependsOn = field.dependencies?.depends_on || [];
      if (dependsOn.length === 0) return true; // 无依赖
      
      // 检查所有依赖是否完成
      const allDepsCompleted = dependsOn.every(depId => completedFieldIds.has(depId));
      return allDepsCompleted;
    });
    
    if (autoGeneratableField) {
      console.log(`[AutoGen] 自动触发生成: ${autoGeneratableField.name}`);
      setAutoGeneratingFieldId(autoGeneratableField.id);
      
      try {
        // 调用流式生成 API
        const response = await fetch(`http://localhost:8000/api/fields/${autoGeneratableField.id}/generate/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pre_answers: autoGeneratableField.pre_answers || {} }),
        });
        
        // 等待生成完成
        const reader = response.body?.getReader();
        if (reader) {
          while (true) {
            const { done } = await reader.read();
            if (done) break;
          }
        }
        
        // 刷新字段列表
        onFieldsChange?.();
      } catch (err) {
        console.error("[AutoGen] 自动生成失败:", err);
      } finally {
        setAutoGeneratingFieldId(null);
      }
    }
  };

  // 当字段列表变化时，检查是否有字段可以自动生成
  useEffect(() => {
    if (currentPhase === "produce_inner" && phaseFields.length > 0) {
      checkAndAutoGenerate();
    }
  }, [fields, currentPhase]); // 依赖 fields 变化
  
  // 判断当前阶段是否可以进入下一阶段
  const phaseHasContent = phaseFields.length > 0 && phaseFields.some(f => f.status === "completed");
  const currentPhaseIndex = PROJECT_PHASES.indexOf(currentPhase);
  const isLastPhase = currentPhaseIndex === PROJECT_PHASES.length - 1;
  const nextPhase = isLastPhase ? null : PROJECT_PHASES[currentPhaseIndex + 1];
  
  // 内涵设计阶段：检查是否是JSON方案格式（Hooks必须在顶层调用）
  const designInnerField = phaseFields.find(
    (f) => f.phase === "design_inner" && f.name === "内涵设计方案"
  );
  
  // 尝试解析JSON方案（design_inner）
  const isProposalFormat = useMemo(() => {
    if (currentPhase !== "design_inner" || !designInnerField?.content) {
      return false;
    }
    try {
      const data = JSON.parse(designInnerField.content);
      return data.proposals && Array.isArray(data.proposals);
    } catch {
      return false;
    }
  }, [currentPhase, designInnerField?.content]);

  // 消费者调研阶段：检查是否是JSON格式
  const researchField = phaseFields.find(
    (f) => f.phase === "research" && f.name === "消费者调研报告"
  );
  
  const isResearchJsonFormat = useMemo(() => {
    if (currentPhase !== "research" || !researchField?.content) {
      return false;
    }
    try {
      const data = JSON.parse(researchField.content);
      return data.summary && data.personas && Array.isArray(data.personas);
    } catch {
      return false;
    }
  }, [currentPhase, researchField?.content]);
  
  // 确认进入下一阶段
  const handleAdvancePhase = async () => {
    if (!projectId || !nextPhase) return;
    
    setIsAdvancing(true);
    try {
      await agentAPI.advance(projectId);
      onPhaseAdvance?.();
    } catch (err) {
      console.error("进入下一阶段失败:", err);
      alert("进入下一阶段失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsAdvancing(false);
    }
  };

  // ===== 早期返回（在所有Hooks之后）=====
  
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

  // 消费者调研阶段：使用调研面板
  if (currentPhase === "research" && isResearchJsonFormat && researchField) {
    return (
      <ResearchPanel
        projectId={projectId}
        fieldId={researchField.id}
        content={researchField.content}
        onUpdate={onFieldsChange}
        onAdvance={handleAdvancePhase}
      />
    );
  }

  // 如果是方案格式，使用方案选择器
  if (currentPhase === "design_inner" && isProposalFormat && designInnerField) {
    return (
      <div className="h-full flex flex-col">
        <div className="p-4 border-b border-surface-3">
          <h1 className="text-xl font-bold text-zinc-100">
            {PHASE_NAMES[currentPhase] || currentPhase}
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            请选择一个方案，调整字段设置后确认进入生产
          </p>
        </div>
        <div className="flex-1 overflow-hidden">
          <ProposalSelector
            projectId={projectId}
            fieldId={designInnerField.id}
            content={designInnerField.content}
            onConfirm={() => {
              onFieldsChange?.();
              onPhaseAdvance?.();
            }}
            onFieldsCreated={onFieldsChange}
            onSave={onFieldsChange}
          />
        </div>
      </div>
    );
  }

  // 构建字段ID到字段名称的映射（用于显示依赖）
  const fieldNameMap = Object.fromEntries(fields.map(f => [f.id, f.name]));
  
  // 滚动到指定字段
  const scrollToField = (fieldId: string) => {
    const element = document.getElementById(`field-${fieldId}`);
    element?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="h-full flex">
      {/* 内涵生产阶段：左侧字段目录 */}
      {currentPhase === "produce_inner" && phaseFields.length > 0 && (
        <div className="w-56 shrink-0 border-r border-surface-3 p-4 overflow-auto">
          <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">
            字段目录
          </h3>
          <div className="space-y-1">
            {phaseFields.map((field, index) => {
              const deps = field.dependencies?.depends_on || [];
              const depsComplete = deps.every(depId => 
                fields.find(f => f.id === depId)?.status === "completed"
              );
              
              return (
                <button
                  key={field.id}
                  onClick={() => scrollToField(field.id)}
                  className="w-full text-left p-2 rounded-lg hover:bg-surface-3 transition-colors group"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-zinc-600">{index + 1}</span>
                    <span className={`w-2 h-2 rounded-full shrink-0 ${
                      field.status === "completed" ? "bg-green-500" :
                      field.status === "generating" ? "bg-yellow-500 animate-pulse" :
                      "bg-zinc-600"
                    }`} />
                    <span className="text-sm text-zinc-300 truncate flex-1">
                      {field.name}
                    </span>
                  </div>
                  {/* 依赖显示 */}
                  {deps.length > 0 && (
                    <div className="mt-1 ml-6 text-xs text-zinc-600">
                      ← {deps.map(d => fieldNameMap[d] || "?").join(", ")}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
          
          {/* 添加字段按钮 */}
          <div className="mt-4 space-y-2">
            <button
              onClick={() => handleAddEmptyField()}
              className="w-full py-2 text-xs bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
            >
              + 添加字段
            </button>
            <button
              onClick={() => setShowFieldTemplateModal(true)}
              className="w-full py-2 text-xs bg-surface-3 hover:bg-surface-4 text-zinc-400 hover:text-zinc-200 rounded-lg transition-colors"
            >
              📦 从模板添加
            </button>
          </div>
          
          {/* 依赖关系图例 */}
          <div className="mt-6 pt-4 border-t border-surface-3">
            <div className="text-xs text-zinc-600 space-y-1">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <span>已完成</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-yellow-500" />
                <span>生成中</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-zinc-600" />
                <span>待生成</span>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* 主内容区 */}
      <div className="flex-1 overflow-auto p-6 max-w-4xl mx-auto">
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
              <div key={field.id} id={`field-${field.id}`}>
                <FieldCard
                  field={field}
                  allFields={fields}
                  onUpdate={(content) => onFieldUpdate?.(field.id, content)}
                  onFieldsChange={onFieldsChange}
                />
              </div>
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
      
      {/* 确认进入下一阶段按钮 */}
      {phaseHasContent && nextPhase && (() => {
        const isPhaseCompleted = phaseStatus[currentPhase] === "completed";
        
        return (
          <div className="mt-8 pt-6 border-t border-surface-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-zinc-400 text-sm">
                  {isPhaseCompleted ? "✅ 当前阶段已确认" : "当前阶段内容已完成"}
                </p>
                <p className="text-zinc-500 text-xs mt-1">
                  下一阶段：{PHASE_NAMES[nextPhase] || nextPhase}
                </p>
              </div>
              {isPhaseCompleted ? (
                <div className="px-6 py-3 rounded-xl font-medium bg-green-600/20 text-green-400 border border-green-500/30">
                  ✅ 已确认
                </div>
              ) : (
                <button
                  onClick={handleAdvancePhase}
                  disabled={isAdvancing}
                  className={`px-6 py-3 rounded-xl font-medium transition-all ${
                    isAdvancing
                      ? "bg-zinc-700 text-zinc-400 cursor-wait"
                      : "bg-brand-600 hover:bg-brand-700 text-white shadow-lg hover:shadow-brand-600/25"
                  }`}
                >
                  {isAdvancing ? (
                    <span className="flex items-center gap-2">
                      <span className="animate-spin">⏳</span> 处理中...
                    </span>
                  ) : (
                    <span>✅ 确认，进入下一阶段</span>
                  )}
                </button>
              )}
            </div>
          </div>
        );
      })()}
      </div>

      {/* 字段模板选择弹窗 */}
      {showFieldTemplateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden">
            <div className="px-4 py-3 border-b border-surface-3">
              <h3 className="font-medium text-zinc-200">从模板添加字段</h3>
              <p className="text-xs text-zinc-500 mt-1">
                选择一个模板添加到当前阶段
              </p>
            </div>

            <div className="p-4 max-h-[50vh] overflow-y-auto space-y-2">
              {fieldTemplates.length > 0 ? (
                fieldTemplates.map((template) => (
                  <button
                    key={template.id}
                    onClick={() => handleAddFromTemplate(template)}
                    className="w-full text-left p-4 rounded-lg bg-surface-1 border border-surface-3 hover:bg-surface-3 hover:border-brand-500/50 transition-all"
                  >
                    <div className="font-medium text-zinc-200">{template.name}</div>
                    <div className="text-xs text-zinc-500 mt-1">{template.description}</div>
                    <div className="text-xs text-zinc-600 mt-2">
                      📦 {template.fields?.length || 0} 个字段
                    </div>
                  </button>
                ))
              ) : (
                <p className="text-zinc-500 text-center py-8">
                  暂无字段模板，请在后台设置中添加
                </p>
              )}
            </div>

            <div className="px-4 py-3 border-t border-surface-3 flex justify-end">
              <button
                onClick={() => setShowFieldTemplateModal(false)}
                className="px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
              >
                取消
              </button>
            </div>
          </div>
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
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState(field.name);
  const [content, setContent] = useState(field.content);
  const [showDependencyModal, setShowDependencyModal] = useState(false);
  const [showConstraintsModal, setShowConstraintsModal] = useState(false);
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

  const handleUpdateConstraints = async (newConstraints: {
    ai_prompt?: string | null;
    max_length?: number | null;
    output_format?: string;
    structure?: string | null;
    example?: string | null;
  }) => {
    try {
      // 分离 ai_prompt 和 constraints
      const { ai_prompt, ...constraints } = newConstraints;
      
      await fieldAPI.update(field.id, { 
        ai_prompt: ai_prompt || "",
        constraints 
      });
      onFieldsChange?.();
      setShowConstraintsModal(false);
    } catch (err) {
      alert("更新约束失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  const handleSaveName = async () => {
    if (editedName.trim() && editedName !== field.name) {
      try {
        await fieldAPI.update(field.id, { name: editedName.trim() });
        onFieldsChange?.();
      } catch (err) {
        alert("更新名称失败: " + (err instanceof Error ? err.message : "未知错误"));
        setEditedName(field.name);  // 恢复原名称
      }
    }
    setIsEditingName(false);
  };

  const handleDelete = async () => {
    if (!confirm(`确定要删除字段「${field.name}」吗？此操作不可撤销。`)) return;
    try {
      await fieldAPI.delete(field.id);
      onFieldsChange?.();
    } catch (err) {
      alert("删除失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  return (
    <div className="bg-surface-2 rounded-xl border border-surface-3 overflow-hidden">
      {/* 字段头部 */}
      <div className="px-4 py-3 border-b border-surface-3">
        <div className="flex items-center justify-between">
          <div>
            {isEditingName ? (
              <input
                type="text"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                onBlur={handleSaveName}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSaveName();
                  if (e.key === "Escape") {
                    setEditedName(field.name);
                    setIsEditingName(false);
                  }
                }}
                className="font-medium text-zinc-200 bg-surface-1 border border-surface-3 rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-brand-500"
                autoFocus
              />
            ) : (
              <h3 
                className="font-medium text-zinc-200 cursor-pointer hover:text-brand-400 transition-colors"
                onClick={() => setIsEditingName(true)}
                title="点击编辑标题"
              >
                {field.name} <span className="text-xs text-zinc-600">✏️</span>
              </h3>
            )}
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
            {/* 未完成 + 不在生成中：显示生成按钮 */}
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
            
            {/* 已完成：显示重新生成按钮 */}
            {field.status === "completed" && !isGenerating && (
              <button
                onClick={handleGenerate}
                className="px-3 py-1 text-sm bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-500/30 rounded-lg transition-colors"
                title="重新生成内容（会覆盖现有内容）"
              >
                🔄 重新生成
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
            
            {/* 删除按钮 */}
            <button
              onClick={handleDelete}
              className="px-3 py-1 text-sm bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/30 rounded-lg transition-colors"
              title="删除此字段"
            >
              🗑️
            </button>
          </div>
        </div>

        {/* 依赖关系 + 约束显示 */}
        <div className="mt-2 flex items-center gap-4 flex-wrap text-xs">
          {/* 依赖关系 */}
          <button
            onClick={() => setShowDependencyModal(true)}
            className="text-zinc-500 hover:text-zinc-300 flex items-center gap-1"
          >
            <span>📎 依赖:</span>
            {dependencyFields.length > 0 ? (
              dependencyFields.map((df) => (
                <span
                  key={df.id}
                  className={`px-1.5 py-0.5 rounded ${
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
          </button>
          
          {/* 生成配置概览（可点击编辑） */}
          <button
            onClick={() => setShowConstraintsModal(true)}
            className="flex items-center gap-2 text-zinc-600 hover:text-zinc-400 transition-colors flex-wrap"
          >
            {/* AI 提示词状态 */}
            <span className={`flex items-center gap-1 ${
              field.ai_prompt && field.ai_prompt !== "请在这里编写生成提示词..." 
                ? "text-brand-400" 
                : "text-red-400"
            }`}>
              {field.ai_prompt && field.ai_prompt !== "请在这里编写生成提示词..." ? (
                <>
                  <span>✨</span>
                  <span className="px-1.5 py-0.5 bg-brand-600/20 rounded max-w-[150px] truncate" title={field.ai_prompt}>
                    {field.ai_prompt.slice(0, 20)}{field.ai_prompt.length > 20 ? "..." : ""}
                  </span>
                </>
              ) : (
                <>
                  <span>⚠️</span>
                  <span className="px-1.5 py-0.5 bg-red-600/20 rounded">未设置提示词</span>
                </>
              )}
            </span>
            
            {/* 约束标签 */}
            {field.constraints?.max_length ? (
              <span className="px-1.5 py-0.5 bg-surface-3 rounded text-zinc-400" title="最大字数">
                ≤{field.constraints.max_length}字
              </span>
            ) : null}
            {field.constraints?.output_format && field.constraints.output_format !== "markdown" ? (
              <span className="px-1.5 py-0.5 bg-surface-3 rounded text-zinc-400" title="输出格式">
                {field.constraints.output_format}
              </span>
            ) : null}
            
            <span className="text-xs text-zinc-600">（点击配置）</span>
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

      {/* 约束编辑弹窗 */}
      {showConstraintsModal && (
        <ConstraintsModal
          field={field}
          onClose={() => setShowConstraintsModal(false)}
          onSave={handleUpdateConstraints}
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

// ============== 约束编辑弹窗 ==============
interface ConstraintsModalProps {
  field: Field;
  onClose: () => void;
  onSave: (config: {
    ai_prompt?: string | null;
    max_length?: number | null;
    output_format?: string;
    structure?: string | null;
    example?: string | null;
  }) => void;
}

function ConstraintsModal({ field, onClose, onSave }: ConstraintsModalProps) {
  // 核心：AI 生成提示词
  const [aiPrompt, setAiPrompt] = useState(
    field.ai_prompt && field.ai_prompt !== "请在这里编写生成提示词..." 
      ? field.ai_prompt 
      : ""
  );
  const [maxLength, setMaxLength] = useState<string>(
    field.constraints?.max_length?.toString() || ""
  );
  const [outputFormat, setOutputFormat] = useState(
    field.constraints?.output_format || "markdown"
  );
  const [structure, setStructure] = useState(field.constraints?.structure || "");
  const [example, setExample] = useState(field.constraints?.example || "");

  const handleSave = () => {
    onSave({
      ai_prompt: aiPrompt || null,
      max_length: maxLength ? parseInt(maxLength, 10) : null,
      output_format: outputFormat,
      structure: structure || null,
      example: example || null,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden">
        <div className="px-4 py-3 border-b border-surface-3">
          <h3 className="font-medium text-zinc-200">字段生成配置</h3>
          <p className="text-xs text-zinc-500 mt-1">
            设置「{field.name}」的生成提示词和约束
          </p>
        </div>

        <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {/* ⭐ 核心：AI 生成提示词 */}
          <div className="bg-brand-600/10 border border-brand-500/30 rounded-lg p-3">
            <label className="block text-sm text-brand-400 mb-1.5 font-medium">
              ✨ 生成提示词（最重要！）
            </label>
            <textarea
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder="例如：写一段开场白，用轻松幽默的语气介绍本文的主题"
              rows={4}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
            />
            <p className="text-xs text-zinc-500 mt-1.5">
              告诉 AI 这个字段应该生成什么内容。越具体越好！
            </p>
          </div>

          {/* 最大字数 */}
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">
              📏 最大字数
            </label>
            <input
              type="number"
              value={maxLength}
              onChange={(e) => setMaxLength(e.target.value)}
              placeholder="不限制"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            <p className="text-xs text-zinc-600 mt-1">
              留空表示不限制长度
            </p>
          </div>

          {/* 输出格式 */}
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">
              📋 输出格式
            </label>
            <select
              value={outputFormat}
              onChange={(e) => setOutputFormat(e.target.value)}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="markdown">Markdown（富文本）</option>
              <option value="plain_text">纯文本</option>
              <option value="json">JSON 结构化</option>
              <option value="list">列表（每行一项）</option>
            </select>
          </div>

          {/* 结构模板 */}
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">
              🏗️ 结构模板（可选）
            </label>
            <textarea
              value={structure}
              onChange={(e) => setStructure(e.target.value)}
              placeholder="例如：标题 + 正文 + 总结&#10;或：问题 → 原因分析 → 解决方案"
              rows={2}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
            />
          </div>

          {/* 示例输出 */}
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">
              💡 示例输出（可选）
            </label>
            <textarea
              value={example}
              onChange={(e) => setExample(e.target.value)}
              placeholder="提供一个期望输出的示例，帮助 AI 理解格式"
              rows={3}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
            />
          </div>
        </div>

        <div className="px-4 py-3 border-t border-surface-3 flex justify-between">
          <button
            onClick={() => {
              setAiPrompt("");
              setMaxLength("");
              setOutputFormat("markdown");
              setStructure("");
              setExample("");
            }}
            className="px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            重置为默认
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors"
            >
              保存
            </button>
          </div>
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
