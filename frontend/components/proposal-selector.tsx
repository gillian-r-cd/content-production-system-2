// frontend/components/proposal-selector.tsx
// 功能: 内涵设计方案选择组件
// 主要功能: 展示3个方案、方案选择、字段编辑、确认进入下一阶段
// 新增功能: 添加字段模板、字段编辑、约束配置

"use client";

import { useState, useMemo, useEffect } from "react";
import { fieldAPI, agentAPI, settingsAPI } from "@/lib/api";

// 方案中的字段定义
interface ProposalField {
  id: string;
  name: string;
  field_type: string;
  ai_prompt: string;
  depends_on: string[];
  order: number;
  need_review: boolean;
  constraints?: {
    max_length?: number | null;
    output_format?: string;
    structure?: string | null;
    example?: string | null;
  };
}

// 方案定义
interface Proposal {
  id: string;
  name: string;
  description: string;
  fields: ProposalField[];
}

// 方案数据结构
interface ProposalsData {
  proposals: Proposal[];
  selected_proposal?: string | null;
  error?: string;
}

interface ProposalSelectorProps {
  projectId: string;
  fieldId: string;  // 存储方案的字段ID（用于保存修改）
  content: string;  // JSON格式的方案内容
  onConfirm: () => void;  // 确认后的回调
  onFieldsCreated?: () => void;  // 字段创建后的回调
  onSave?: () => void;  // 保存后的回调
}

export function ProposalSelector({
  projectId,
  fieldId,
  content,
  onConfirm,
  onFieldsCreated,
  onSave,
}: ProposalSelectorProps) {
  // 解析方案数据，并添加"自定义方案"（如果不存在）
  const proposalsData = useMemo<ProposalsData>(() => {
    try {
      const data = JSON.parse(content);
      const proposals = data.proposals || [];
      
      // 检查是否已有自定义方案
      const hasCustomProposal = proposals.some((p: Proposal) => p.id === "custom_proposal");
      
      if (!hasCustomProposal) {
        // 添加自定义方案（空方案）
        const customProposal: Proposal = {
          id: "custom_proposal",
          name: "自定义方案",
          description: "从零开始构建您的内容结构，自由添加和编辑字段",
          fields: [],
        };
        proposals.push(customProposal);
      }
      
      return {
        ...data,
        proposals,
      };
    } catch {
      // 解析失败时，至少提供自定义方案
      const customProposal: Proposal = {
        id: "custom_proposal",
        name: "自定义方案",
        description: "从零开始构建您的内容结构，自由添加和编辑字段",
        fields: [],
      };
      return { proposals: [customProposal], error: undefined };
    }
  }, [content]);

  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(
    proposalsData.selected_proposal || proposalsData.proposals?.[0]?.id || null
  );
  const [editedFields, setEditedFields] = useState<Record<string, ProposalField[]>>({});
  const [isConfirming, setIsConfirming] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [confirmedProposalId, setConfirmedProposalId] = useState<string | null>(null);  // 已确认的方案ID
  const [editingDependencyFieldId, setEditingDependencyFieldId] = useState<string | null>(null);
  
  // 字段编辑相关状态
  const [fieldTemplates, setFieldTemplates] = useState<any[]>([]);
  const [showAddTemplateModal, setShowAddTemplateModal] = useState(false);
  const [editingFieldId, setEditingFieldId] = useState<string | null>(null);
  const [showConstraintsModal, setShowConstraintsModal] = useState<string | null>(null);
  
  // 加载字段模板
  useEffect(() => {
    settingsAPI.listFieldTemplates().then(setFieldTemplates).catch(console.error);
  }, []);

  // 跟踪是否有未保存的修改
  useEffect(() => {
    if (Object.keys(editedFields).length > 0) {
      setHasUnsavedChanges(true);
    }
  }, [editedFields]);

  // 保存方案修改到后端
  const saveProposals = async () => {
    if (!fieldId) return;
    
    setIsSaving(true);
    try {
      // 构建更新后的方案数据
      const updatedProposals = proposalsData.proposals.map((proposal) => {
        const editedFieldsForProposal = editedFields[proposal.id];
        if (editedFieldsForProposal) {
          return { ...proposal, fields: editedFieldsForProposal };
        }
        return proposal;
      });
      
      const newContent = JSON.stringify({
        proposals: updatedProposals,
        selected_proposal: selectedProposalId,
      }, null, 2);
      
      // 调用 API 更新字段内容
      await fieldAPI.update(fieldId, { content: newContent });
      
      setHasUnsavedChanges(false);
      onSave?.();
    } catch (err) {
      console.error("保存方案失败:", err);
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsSaving(false);
    }
  };

  // 当前选中的方案
  const selectedProposal = useMemo(() => {
    return proposalsData.proposals?.find((p) => p.id === selectedProposalId) || null;
  }, [proposalsData.proposals, selectedProposalId]);

  // 获取当前方案的字段（可能被编辑过）
  const currentFields = useMemo(() => {
    if (!selectedProposalId) return [];
    return editedFields[selectedProposalId] || selectedProposal?.fields || [];
  }, [selectedProposalId, editedFields, selectedProposal]);

  // 切换字段的 need_review 状态
  const toggleNeedReview = (fieldId: string) => {
    if (!selectedProposalId) return;
    
    const fields = [...currentFields];
    const fieldIndex = fields.findIndex((f) => f.id === fieldId);
    if (fieldIndex !== -1) {
      fields[fieldIndex] = {
        ...fields[fieldIndex],
        need_review: !fields[fieldIndex].need_review,
      };
      setEditedFields((prev) => ({
        ...prev,
        [selectedProposalId]: fields,
      }));
    }
  };

  // 更新字段名称
  const updateFieldName = (fieldId: string, newName: string) => {
    if (!selectedProposalId) return;
    
    const fields = [...currentFields];
    const fieldIndex = fields.findIndex((f) => f.id === fieldId);
    if (fieldIndex !== -1) {
      fields[fieldIndex] = { ...fields[fieldIndex], name: newName };
      setEditedFields((prev) => ({ ...prev, [selectedProposalId]: fields }));
    }
  };

  // 删除字段
  const deleteField = (fieldId: string) => {
    if (!selectedProposalId) return;
    
    const fields = currentFields.filter((f) => f.id !== fieldId);
    // 同时删除对该字段的依赖引用
    const updatedFields = fields.map((f) => ({
      ...f,
      depends_on: f.depends_on.filter((depId) => depId !== fieldId),
    }));
    setEditedFields((prev) => ({ ...prev, [selectedProposalId]: updatedFields }));
  };

  // 更新字段约束
  const updateFieldConstraints = (fieldId: string, constraints: any) => {
    if (!selectedProposalId) return;
    
    const fields = [...currentFields];
    const fieldIndex = fields.findIndex((f) => f.id === fieldId);
    if (fieldIndex !== -1) {
      fields[fieldIndex] = { ...fields[fieldIndex], constraints };
      setEditedFields((prev) => ({ ...prev, [selectedProposalId]: fields }));
    }
    setShowConstraintsModal(null);
  };

  // 从模板添加字段
  const addFieldFromTemplate = (templateFields: any[]) => {
    if (!selectedProposalId) return;
    
    const newFields: ProposalField[] = templateFields.map((tf, idx) => ({
      id: `new_field_${Date.now()}_${idx}`,
      name: tf.name,
      field_type: tf.type || "richtext",
      ai_prompt: tf.ai_prompt || "",
      depends_on: [],  // 从模板添加的字段默认无依赖
      order: currentFields.length + idx + 1,
      need_review: true,
      constraints: {
        max_length: null,
        output_format: "markdown",
        structure: null,
        example: null,
      },
    }));
    
    setEditedFields((prev) => ({
      ...prev,
      [selectedProposalId]: [...currentFields, ...newFields],
    }));
    setShowAddTemplateModal(false);
  };

  // 直接添加空字段（不引用模板）
  const addEmptyField = () => {
    if (!selectedProposalId) return;
    
    const newField: ProposalField = {
      id: `new_field_${Date.now()}`,
      name: `新字段 ${currentFields.length + 1}`,
      field_type: "richtext",
      ai_prompt: "请在这里编写生成提示词...",
      depends_on: [],
      order: currentFields.length + 1,
      need_review: true,
      constraints: {
        max_length: null,
        output_format: "markdown",
        structure: null,
        example: null,
      },
    };
    
    setEditedFields((prev) => ({
      ...prev,
      [selectedProposalId]: [...currentFields, newField],
    }));
    
    // 自动进入编辑模式
    setEditingFieldId(newField.id);
  };

  // 更新字段提示词
  const updateFieldPrompt = (fieldId: string, newPrompt: string) => {
    if (!selectedProposalId) return;
    
    const fields = [...currentFields];
    const fieldIndex = fields.findIndex((f) => f.id === fieldId);
    if (fieldIndex !== -1) {
      fields[fieldIndex] = { ...fields[fieldIndex], ai_prompt: newPrompt };
      setEditedFields((prev) => ({ ...prev, [selectedProposalId]: fields }));
    }
  };

  // 拖拽排序
  const moveField = (fieldId: string, direction: "up" | "down") => {
    if (!selectedProposalId) return;
    
    const fields = [...currentFields];
    const fieldIndex = fields.findIndex((f) => f.id === fieldId);
    if (fieldIndex === -1) return;
    
    const newIndex = direction === "up" ? fieldIndex - 1 : fieldIndex + 1;
    if (newIndex < 0 || newIndex >= fields.length) return;
    
    // 交换位置
    [fields[fieldIndex], fields[newIndex]] = [fields[newIndex], fields[fieldIndex]];
    // 更新 order
    fields.forEach((f, idx) => { f.order = idx + 1; });
    
    setEditedFields((prev) => ({ ...prev, [selectedProposalId]: fields }));
  };

  // 更新字段的依赖关系
  const updateFieldDependencies = (fieldId: string, newDependsOn: string[]) => {
    if (!selectedProposalId) return;
    
    const fields = [...currentFields];
    const fieldIndex = fields.findIndex((f) => f.id === fieldId);
    if (fieldIndex !== -1) {
      fields[fieldIndex] = {
        ...fields[fieldIndex],
        depends_on: newDependsOn,
      };
      setEditedFields((prev) => ({
        ...prev,
        [selectedProposalId]: fields,
      }));
    }
    setEditingDependencyFieldId(null);
  };

  // 当前正在编辑依赖的字段
  const editingDependencyField = currentFields.find((f) => f.id === editingDependencyFieldId);

  // 确认方案，创建实际的字段
  const handleConfirmProposal = async () => {
    if (!selectedProposal || !projectId) return;

    setIsConfirming(true);
    try {
      // 构建临时ID到真实ID的映射
      const tempIdToRealId: Record<string, string> = {};
      
      // 第一步：按顺序创建所有字段（先不设置依赖）
      for (const field of currentFields) {
        const createdField = await fieldAPI.create({
          project_id: projectId,
          name: field.name,
          phase: "produce_inner",  // 字段属于内涵生产阶段
          field_type: field.field_type || "richtext",
          content: "",  // 内容待生产
          status: "pending",
          ai_prompt: field.ai_prompt,
          dependencies: {
            depends_on: [],  // 先创建不带依赖
            dependency_type: "all",
          },
          // 传递约束和自动生成设置
          constraints: (field as any).constraints || undefined,
          need_review: field.need_review,  // 是否需要人工确认
        });
        // 记录临时ID到真实ID的映射
        tempIdToRealId[field.id] = createdField.id;
      }

      // 第二步：更新依赖关系（使用真实ID）
      for (const field of currentFields) {
        if (field.depends_on && field.depends_on.length > 0) {
          const realId = tempIdToRealId[field.id];
          const realDependsOn = field.depends_on
            .map((depId) => tempIdToRealId[depId])
            .filter(Boolean);  // 过滤掉找不到映射的ID
          
          if (realDependsOn.length > 0) {
            await fieldAPI.update(realId, {
              dependencies: {
                depends_on: realDependsOn,
                dependency_type: "all",
              },
            });
          }
        }
      }

      onFieldsCreated?.();
      
      // 记录已确认的方案
      setConfirmedProposalId(selectedProposalId);
      
      // 推进到下一阶段
      await agentAPI.advance(projectId);
      onConfirm();
    } catch (err) {
      console.error("确认方案失败:", err);
      alert("确认方案失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsConfirming(false);
    }
  };

  if (proposalsData.error) {
    return (
      <div className="p-6 text-center text-red-400">
        <p>{proposalsData.error}</p>
        <p className="text-sm mt-2 text-zinc-500">请在右侧对话框让Agent重新生成</p>
      </div>
    );
  }

  if (!proposalsData.proposals || proposalsData.proposals.length === 0) {
    return (
      <div className="p-6 text-center text-zinc-500">
        <p>暂无方案数据</p>
      </div>
    );
  }

  return (
    <div className="h-full flex">
      {/* 左侧：方案目录 */}
      <div className="w-64 border-r border-surface-3 p-4 flex flex-col">
        <h3 className="text-sm font-medium text-zinc-400 mb-4">选择方案</h3>
        <div className="space-y-2 flex-1">
          {proposalsData.proposals.map((proposal, index) => {
            const isConfirmed = confirmedProposalId === proposal.id;
            const isSelected = selectedProposalId === proposal.id;
            
            return (
              <button
                key={proposal.id}
                onClick={() => !confirmedProposalId && setSelectedProposalId(proposal.id)}
                disabled={!!confirmedProposalId}
                className={`w-full text-left p-3 rounded-lg transition-colors ${
                  isConfirmed
                    ? "bg-green-600/20 border border-green-500 text-green-400"
                    : isSelected
                    ? "bg-brand-600/20 border border-brand-500 text-brand-400"
                    : confirmedProposalId
                    ? "bg-surface-2 border border-surface-3 text-zinc-600 cursor-not-allowed"
                    : "bg-surface-2 border border-surface-3 text-zinc-300 hover:bg-surface-3"
                }`}
              >
                <div className="font-medium text-sm flex items-center gap-2">
                  {isConfirmed && <span>✅</span>}
                  {proposal.id === "custom_proposal" ? (
                    <>
                      <span>✏️</span>
                      自定义
                    </>
                  ) : (
                    <>方案 {index + 1}</>
                  )}
                  {isConfirmed && <span className="text-xs bg-green-600/30 px-1.5 py-0.5 rounded">已选中</span>}
                </div>
                <div className="text-xs mt-1 opacity-80 line-clamp-2">
                  {proposal.name}
                </div>
              </button>
            );
          })}
        </div>
        
        {/* 保存和确认按钮 */}
        <div className="mt-4 space-y-2">
          {/* 保存按钮 */}
          {!confirmedProposalId && hasUnsavedChanges && (
            <button
              onClick={saveProposals}
              disabled={isSaving}
              className="w-full py-2.5 bg-surface-3 hover:bg-surface-4 disabled:bg-zinc-700 text-zinc-300 rounded-lg font-medium transition-colors text-sm"
            >
              {isSaving ? "💾 保存中..." : "💾 保存修改"}
            </button>
          )}
          
          {/* 确认按钮 */}
          {confirmedProposalId ? (
            <div className="w-full py-3 bg-green-600/20 text-green-400 border border-green-500/30 rounded-lg font-medium text-center">
              ✅ 已确认并进入生产
            </div>
          ) : (
            <button
              onClick={handleConfirmProposal}
              disabled={!selectedProposalId || isConfirming || (hasUnsavedChanges && currentFields.length > 0)}
              className="w-full py-3 bg-brand-600 hover:bg-brand-700 disabled:bg-zinc-700 disabled:text-zinc-500 rounded-lg font-medium transition-colors"
              title={hasUnsavedChanges && currentFields.length > 0 ? "请先保存修改" : ""}
            >
              {isConfirming ? "确认中..." : hasUnsavedChanges && currentFields.length > 0 ? "⚠️ 请先保存修改" : "✅ 确认并进入生产"}
            </button>
          )}
        </div>
      </div>

      {/* 右侧：方案详情 */}
      <div className="flex-1 p-6 overflow-auto">
        {selectedProposal ? (
          <div>
            <h2 className="text-xl font-bold text-zinc-100 mb-2">
              {selectedProposal.name}
            </h2>
            <p className="text-zinc-400 mb-6">
              {selectedProposal.description}
            </p>

            {/* 字段列表头部 */}
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-zinc-400">
                  内容字段 ({currentFields.length}个)
                </h3>
                <p className="text-xs text-zinc-500 mt-1">
                  拖动调整顺序 · 点击编辑配置
                </p>
              </div>
              {!confirmedProposalId && (
                <div className="flex gap-2">
                  <button
                    onClick={addEmptyField}
                    className="px-3 py-1.5 text-xs bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
                  >
                    + 添加字段
                  </button>
                  <button
                    onClick={() => setShowAddTemplateModal(true)}
                    className="px-3 py-1.5 text-xs bg-surface-3 hover:bg-surface-4 text-zinc-400 hover:text-zinc-200 rounded-lg transition-colors"
                  >
                    📦 从模板添加
                  </button>
                </div>
              )}
            </div>

            <div className="space-y-3">
              {currentFields.map((field, index) => (
                <div
                  key={field.id}
                  className="bg-surface-2 border border-surface-3 rounded-lg p-4 group"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        {/* 排序按钮 */}
                        {!confirmedProposalId && (
                          <div className="flex flex-col gap-0.5">
                            <button
                              onClick={() => moveField(field.id, "up")}
                              disabled={index === 0}
                              className="text-xs text-zinc-500 hover:text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed px-1"
                              title="上移"
                            >
                              ▲
                            </button>
                            <button
                              onClick={() => moveField(field.id, "down")}
                              disabled={index === currentFields.length - 1}
                              className="text-xs text-zinc-500 hover:text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed px-1"
                              title="下移"
                            >
                              ▼
                            </button>
                          </div>
                        )}
                        <span className="text-xs bg-surface-3 px-2 py-0.5 rounded text-zinc-500">
                          {index + 1}
                        </span>
                        {editingFieldId === field.id ? (
                          <input
                            type="text"
                            value={field.name}
                            onChange={(e) => updateFieldName(field.id, e.target.value)}
                            onBlur={() => setEditingFieldId(null)}
                            onKeyDown={(e) => e.key === "Enter" && setEditingFieldId(null)}
                            className="flex-1 bg-surface-1 border border-surface-3 rounded px-2 py-0.5 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-brand-500"
                            autoFocus
                          />
                        ) : (
                          <span 
                            onClick={() => !confirmedProposalId && setEditingFieldId(field.id)}
                            className={`font-medium text-zinc-200 ${!confirmedProposalId ? 'cursor-pointer hover:text-brand-400' : ''}`}
                          >
                            {field.name}
                          </span>
                        )}
                      </div>
                      
                      {/* 依赖关系 + 约束 */}
                      <div className="mt-2 flex items-center gap-3 flex-wrap text-xs">
                        {/* 依赖关系 */}
                        <button
                          onClick={() => !confirmedProposalId && setEditingDependencyFieldId(field.id)}
                          disabled={!!confirmedProposalId}
                          className="text-zinc-500 hover:text-zinc-300 flex items-center gap-1 transition-colors disabled:cursor-not-allowed"
                        >
                          <span>📎</span>
                          {field.depends_on && field.depends_on.length > 0 ? (
                            <span className="flex gap-1 flex-wrap">
                              {field.depends_on.slice(0, 2).map((depId) => {
                                const depField = currentFields.find((f) => f.id === depId);
                                return (
                                  <span key={depId} className="px-1.5 py-0.5 bg-surface-3 rounded text-zinc-400">
                                    {depField?.name?.substring(0, 8) || "?"}
                                  </span>
                                );
                              })}
                              {field.depends_on.length > 2 && <span>+{field.depends_on.length - 2}</span>}
                            </span>
                          ) : (
                            <span className="text-zinc-600">无依赖</span>
                          )}
                        </button>
                        
                        {/* 约束配置 */}
                        <button
                          onClick={() => !confirmedProposalId && setShowConstraintsModal(field.id)}
                          disabled={!!confirmedProposalId}
                          className="text-zinc-500 hover:text-zinc-300 flex items-center gap-1 transition-colors disabled:cursor-not-allowed"
                        >
                          <span>⚙️</span>
                          {field.constraints?.max_length ? (
                            <span className="px-1.5 py-0.5 bg-surface-3 rounded">≤{field.constraints.max_length}字</span>
                          ) : (
                            <span className="text-zinc-600">默认约束</span>
                          )}
                        </button>
                      </div>
                      
                      {/* AI提示词 - 可编辑 */}
                      <div className="mt-3">
                        <label className="text-xs text-zinc-500 mb-1 block">生成提示词：</label>
                        {confirmedProposalId ? (
                          <div className="text-xs text-zinc-400 bg-surface-1 rounded-lg p-2 whitespace-pre-wrap">
                            {field.ai_prompt || "无提示词"}
                          </div>
                        ) : (
                          <textarea
                            value={field.ai_prompt}
                            onChange={(e) => updateFieldPrompt(field.id, e.target.value)}
                            placeholder="请输入AI生成该字段内容时的提示词..."
                            rows={3}
                            className="w-full text-xs bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-3 py-2 text-zinc-300 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-brand-500 resize-none"
                          />
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {/* Checkpoint 开关 */}
                      <button
                        onClick={() => !confirmedProposalId && toggleNeedReview(field.id)}
                        disabled={!!confirmedProposalId}
                        className={`px-3 py-1 text-xs rounded-full transition-colors ${
                          field.need_review
                            ? "bg-amber-500/20 text-amber-400 border border-amber-500/50"
                            : "bg-green-500/20 text-green-400 border border-green-500/50"
                        } ${confirmedProposalId ? 'opacity-50 cursor-not-allowed' : ''}`}
                      >
                        {field.need_review ? "🔍 需确认" : "⚡ 自动"}
                      </button>
                      
                      {/* 删除按钮 */}
                      {!confirmedProposalId && (
                        <button
                          onClick={() => deleteField(field.id)}
                          className="opacity-0 group-hover:opacity-100 p-1.5 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded transition-all"
                          title="删除字段"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-zinc-500">
            请选择一个方案
          </div>
        )}
      </div>

      {/* 依赖编辑弹窗 */}
      {editingDependencyFieldId && editingDependencyField && (
        <DependencyEditModal
          field={editingDependencyField}
          allFields={currentFields}
          onClose={() => setEditingDependencyFieldId(null)}
          onSave={(newDependsOn) => updateFieldDependencies(editingDependencyFieldId, newDependsOn)}
        />
      )}

      {/* 字段模板选择弹窗 */}
      {showAddTemplateModal && (
        <FieldTemplateModal
          templates={fieldTemplates}
          onClose={() => setShowAddTemplateModal(false)}
          onSelect={addFieldFromTemplate}
        />
      )}

      {/* 约束编辑弹窗 */}
      {showConstraintsModal && (() => {
        const field = currentFields.find((f) => f.id === showConstraintsModal);
        if (!field) return null;
        return (
          <FieldConstraintsModal
            field={field}
            onClose={() => setShowConstraintsModal(null)}
            onSave={(constraints) => updateFieldConstraints(showConstraintsModal, constraints)}
          />
        );
      })()}
    </div>
  );
}

// 依赖编辑弹窗组件
interface DependencyEditModalProps {
  field: ProposalField;
  allFields: ProposalField[];
  onClose: () => void;
  onSave: (dependsOn: string[]) => void;
}

function DependencyEditModal({ field, allFields, onClose, onSave }: DependencyEditModalProps) {
  const [selectedIds, setSelectedIds] = useState<string[]>(field.depends_on || []);

  // 可选的依赖字段（排除自己，且只能选择 order 小于当前字段的）
  const availableFields = allFields.filter(
    (f) => f.id !== field.id && f.order < field.order
  );

  const toggleField = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden">
        <div className="px-4 py-3 border-b border-surface-3">
          <h3 className="font-medium text-zinc-200">编辑依赖关系</h3>
          <p className="text-xs text-zinc-500 mt-1">
            选择生成「{field.name}」前需要先完成的字段
          </p>
        </div>

        <div className="p-4 max-h-[50vh] overflow-y-auto space-y-2">
          {availableFields.length > 0 ? (
            availableFields.map((f) => (
              <label
                key={f.id}
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-surface-3 cursor-pointer transition-colors"
              >
                <input
                  type="checkbox"
                  checked={selectedIds.includes(f.id)}
                  onChange={() => toggleField(f.id)}
                  className="rounded accent-brand-500"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs bg-surface-3 px-2 py-0.5 rounded text-zinc-500">
                      {f.order}
                    </span>
                    <span className="text-sm text-zinc-200">{f.name}</span>
                  </div>
                  <div className="text-xs text-zinc-500 mt-1 line-clamp-1">
                    {f.ai_prompt}
                  </div>
                </div>
              </label>
            ))
          ) : (
            <p className="text-zinc-500 text-center py-4">
              没有可选的依赖字段（只能依赖顺序在前的字段）
            </p>
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
            className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

// ============== 字段模板选择弹窗 ==============
interface FieldTemplateModalProps {
  templates: any[];
  onClose: () => void;
  onSelect: (fields: any[]) => void;
}

function FieldTemplateModal({ templates, onClose, onSelect }: FieldTemplateModalProps) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden">
        <div className="px-4 py-3 border-b border-surface-3">
          <h3 className="font-medium text-zinc-200">添加字段模板</h3>
          <p className="text-xs text-zinc-500 mt-1">
            选择一个字段模板添加到当前方案
          </p>
        </div>

        <div className="p-4 max-h-[50vh] overflow-y-auto space-y-2">
          {templates.length > 0 ? (
            templates.map((template) => (
              <button
                key={template.id}
                onClick={() => onSelect(template.fields || [])}
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
            onClick={onClose}
            className="px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  );
}

// ============== 字段约束编辑弹窗 ==============
interface FieldConstraintsModalProps {
  field: ProposalField;
  onClose: () => void;
  onSave: (constraints: any) => void;
}

function FieldConstraintsModal({ field, onClose, onSave }: FieldConstraintsModalProps) {
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
          <h3 className="font-medium text-zinc-200">字段约束配置</h3>
          <p className="text-xs text-zinc-500 mt-1">
            设置「{field.name}」的生成规则
          </p>
        </div>

        <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto">
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
              placeholder="例如：标题 + 正文 + 总结"
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
              placeholder="提供一个期望输出的示例"
              rows={3}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
            />
          </div>
        </div>

        <div className="px-4 py-3 border-t border-surface-3 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
