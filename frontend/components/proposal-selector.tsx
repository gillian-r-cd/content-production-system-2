// frontend/components/proposal-selector.tsx
// 功能: 内涵设计方案编辑器（全功能）
// 支持: 编辑方案名称/描述、编辑/添加/删除/重排字段、从模板导入字段、
//       添加/删除自定义方案、确认后导入到内涵生产
// 数据: 读写 ProjectField 的 content（JSON proposals 格式）

"use client";

import React, { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { fieldAPI, settingsAPI } from "@/lib/api";
import {
  Check, Send, ChevronDown, ChevronUp, FileText, ArrowRight,
  Plus, Trash2, X, Save, PackagePlus,
  Copy, ArrowUp, ArrowDown, Settings2, BookTemplate,
} from "lucide-react";

// ============== Types ==============

interface ProposalField {
  id: string;
  name: string;
  field_type: string;
  ai_prompt: string;
  depends_on: string[];
  order: number;
  need_review: boolean;
  constraints?: Record<string, any>;
  pre_questions?: string[];
}

interface Proposal {
  id: string;
  name: string;
  description: string;
  fields: ProposalField[];
}

interface ProposalsData {
  proposals: Proposal[];
  confirmed?: boolean;
  selected_proposal_id?: string;
  error?: string;
}

interface FieldTemplateItem {
  id: string;
  name: string;
  description: string;
  category: string;
  fields: Array<{
    name: string;
    type?: string;
    field_type?: string;
  ai_prompt?: string;
    pre_questions?: string[];
    depends_on?: string[];
    dependency_type?: string;
  }>;
}

interface ProposalSelectorProps {
  projectId: string;
  fieldId: string;
  content: string;
  onConfirm: () => void;
  onFieldsCreated?: () => void;
  onSave?: () => void;
}

// ============== Helpers ==============

let _nextId = 1;
function genId(prefix = "item") {
  return `${prefix}_${Date.now()}_${_nextId++}`;
}

function cloneProposals(data: ProposalsData): ProposalsData {
  return JSON.parse(JSON.stringify(data));
}

// ============== Sub-components ==============

/** 单个字段的内联编辑器 */
function FieldEditor({
  field,
  allFields,
  onUpdate,
  onDelete,
  onMoveUp,
  onMoveDown,
  isFirst,
  isLast,
  readOnly,
}: {
  field: ProposalField;
  allFields: ProposalField[];
  onUpdate: (updated: ProposalField) => void;
  onDelete: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  isFirst: boolean;
  isLast: boolean;
  readOnly: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="group bg-surface-2 rounded-lg border border-surface-3 hover:border-surface-4 transition-colors">
      {/* 字段头部 - 概要行 */}
      <div className="flex items-center gap-2 px-3 py-2">
        {/* 拖拽把手 + 上下移动 */}
        {!readOnly && (
          <div className="flex flex-col gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
            <button onClick={onMoveUp} disabled={isFirst} className="text-zinc-600 hover:text-zinc-300 disabled:opacity-20" title="上移">
              <ArrowUp className="w-3 h-3" />
            </button>
            <button onClick={onMoveDown} disabled={isLast} className="text-zinc-600 hover:text-zinc-300 disabled:opacity-20" title="下移">
              <ArrowDown className="w-3 h-3" />
            </button>
          </div>
        )}

        {/* 字段名 */}
        <div className="flex-1 min-w-0 flex items-center gap-2">
          <FileText className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
          {readOnly ? (
            <span className="text-sm font-medium text-zinc-300 truncate">{field.name}</span>
          ) : (
            <input
              value={field.name}
              onChange={e => onUpdate({ ...field, name: e.target.value })}
              className="text-sm font-medium text-zinc-300 bg-transparent border-none outline-none flex-1 min-w-0 
                         focus:ring-1 focus:ring-brand-500/30 rounded px-1 -mx-1"
              placeholder="字段名称"
            />
          )}
          {field.need_review && (
            <span className="text-[10px] px-1.5 py-0.5 bg-amber-500/10 text-amber-400 rounded shrink-0">需确认</span>
          )}
          <span className="text-[10px] text-zinc-600 shrink-0">{field.field_type}</span>
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={() => setExpanded(!expanded)} className="p-1 text-zinc-500 hover:text-zinc-300 rounded" title="展开编辑">
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <Settings2 className="w-3.5 h-3.5" />}
          </button>
          {!readOnly && (
            <button onClick={onDelete} className="p-1 text-zinc-600 hover:text-red-400 rounded opacity-0 group-hover:opacity-100 transition-opacity" title="删除字段">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* 展开的编辑面板 */}
      {expanded && (
        <div className="border-t border-surface-3 px-3 py-3 space-y-3">
          {/* AI 提示词 */}
          <div>
            <label className="text-xs text-zinc-500 mb-1 block">AI 提示词</label>
            <textarea
              value={field.ai_prompt || ""}
              onChange={e => onUpdate({ ...field, ai_prompt: e.target.value })}
              readOnly={readOnly}
              rows={3}
              className="w-full text-sm text-zinc-300 bg-surface-1 border border-surface-3 rounded-lg p-2 resize-y
                         focus:outline-none focus:ring-1 focus:ring-brand-500/30 read-only:opacity-60"
              placeholder="描述这个字段的生成要求..."
            />
          </div>

          {/* 字段类型 + 是否需要确认 */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-xs text-zinc-500">类型</label>
              <select
                value={field.field_type}
                onChange={e => onUpdate({ ...field, field_type: e.target.value })}
                disabled={readOnly}
                className="text-xs bg-surface-1 border border-surface-3 rounded px-2 py-1 text-zinc-300
                           focus:outline-none focus:ring-1 focus:ring-brand-500/30 disabled:opacity-60"
              >
                <option value="text">文本</option>
                <option value="richtext">富文本</option>
                <option value="list">列表</option>
                <option value="structured">结构化</option>
              </select>
            </div>
            <label className="flex items-center gap-1.5 text-xs text-zinc-500 cursor-pointer">
              <input
                type="checkbox"
                checked={field.need_review}
                onChange={e => onUpdate({ ...field, need_review: e.target.checked })}
                disabled={readOnly}
                className="rounded border-zinc-600 bg-surface-1 text-brand-500 focus:ring-brand-500/30"
              />
              需人工确认
            </label>
          </div>

          {/* 依赖字段 */}
          <div>
            <label className="text-xs text-zinc-500 mb-1 block">依赖字段（可多选）</label>
            <div className="flex flex-wrap gap-1.5">
              {allFields.filter(f => f.id !== field.id).map(other => {
                // 依赖可能存的是 id 或 name，两种都兼容
                const isSelected = (field.depends_on || []).some(
                  d => d === other.id || d === other.name
                );
                return (
                  <button
                    key={other.id}
                    onClick={() => {
                      if (readOnly) return;
                      if (isSelected) {
                        // 移除（兼容 id 和 name 两种格式）
                        const newDeps = field.depends_on.filter(
                          d => d !== other.id && d !== other.name
                        );
                        onUpdate({ ...field, depends_on: newDeps });
                      } else {
                        // 添加（统一用 name，便于后续创建字段时引用）
                        onUpdate({ ...field, depends_on: [...(field.depends_on || []), other.name] });
                      }
                    }}
                    className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                      isSelected
                        ? "border-brand-500/50 bg-brand-500/15 text-brand-300"
                        : "border-surface-3 text-zinc-500 hover:border-zinc-500 hover:text-zinc-300"
                    } ${readOnly ? "cursor-default" : "cursor-pointer"}`}
                  >
                    {other.name}
                  </button>
                );
              })}
              {allFields.filter(f => f.id !== field.id).length === 0 && (
                <span className="text-xs text-zinc-600 italic">无其他字段可引用</span>
              )}
            </div>
          </div>

          {/* 当前依赖展示 */}
          {field.depends_on && field.depends_on.length > 0 && (
            <div className="flex items-center gap-1 text-[10px] text-zinc-600">
              <ArrowRight className="w-3 h-3" />
              <span>当前依赖: {field.depends_on.map(d => {
                const resolved = allFields.find(f => f.id === d || f.name === d);
                return resolved?.name || d;
              }).join(", ")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** 从模板导入字段的下拉面板 */
function TemplateImporter({
  onImportFields,
  onClose,
}: {
  onImportFields: (fields: ProposalField[], templateName: string) => void;
  onClose: () => void;
}) {
  const [templates, setTemplates] = useState<FieldTemplateItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [selectedFieldNames, setSelectedFieldNames] = useState<Set<string>>(new Set());

  useEffect(() => {
    (async () => {
      try {
        const data = await settingsAPI.listFieldTemplates();
        setTemplates(data);
      } catch (e) {
        console.error("加载模板失败:", e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const selectedTemplate = templates.find(t => t.id === selectedTemplateId);

  const handleImport = () => {
    if (!selectedTemplate) return;
    const fieldsToImport = selectedTemplate.fields
      .filter(f => selectedFieldNames.has(f.name))
      .map((f, i) => ({
        id: genId("tmpl"),
          name: f.name,
        field_type: f.type || f.field_type || "richtext",
        ai_prompt: f.ai_prompt || "",
        depends_on: f.depends_on || [],
        order: i + 1,
        need_review: true,
        pre_questions: f.pre_questions || [],
      }));
    onImportFields(fieldsToImport, selectedTemplate.name);
    onClose();
  };

  if (loading) {
    return <div className="p-4 text-sm text-zinc-500">加载模板中...</div>;
  }

  return (
    <div className="bg-surface-1 border border-surface-3 rounded-xl p-4 space-y-3 shadow-xl">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-zinc-200">从字段模板导入</h4>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><X className="w-4 h-4" /></button>
      </div>

      {templates.length === 0 ? (
        <p className="text-sm text-zinc-500">暂无可用模板</p>
      ) : (
        <>
          {/* 模板选择 */}
          <select
            value={selectedTemplateId || ""}
            onChange={e => {
              setSelectedTemplateId(e.target.value || null);
              setSelectedFieldNames(new Set());
            }}
            className="w-full text-sm bg-surface-2 border border-surface-3 rounded-lg px-3 py-2 text-zinc-300
                       focus:outline-none focus:ring-1 focus:ring-brand-500/30"
          >
            <option value="">选择模板...</option>
            {templates.map(t => (
              <option key={t.id} value={t.id}>{t.name} ({t.fields.length} 个字段)</option>
            ))}
          </select>

          {/* 字段勾选 */}
          {selectedTemplate && (
            <div className="space-y-1 max-h-48 overflow-y-auto">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-zinc-500">选择要导入的字段</span>
                <button
                  onClick={() => {
                    if (selectedFieldNames.size === selectedTemplate.fields.length) {
                      setSelectedFieldNames(new Set());
                    } else {
                      setSelectedFieldNames(new Set(selectedTemplate.fields.map(f => f.name)));
                    }
                  }}
                  className="text-xs text-brand-400 hover:text-brand-300"
                >
                  {selectedFieldNames.size === selectedTemplate.fields.length ? "取消全选" : "全选"}
                </button>
              </div>
              {selectedTemplate.fields.map(f => (
                <label key={f.name} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-surface-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedFieldNames.has(f.name)}
                    onChange={e => {
                      const next = new Set(selectedFieldNames);
                      if (e.target.checked) next.add(f.name); else next.delete(f.name);
                      setSelectedFieldNames(next);
                    }}
                    className="rounded border-zinc-600 bg-surface-1 text-brand-500 focus:ring-brand-500/30"
                  />
                  <span className="text-sm text-zinc-300">{f.name}</span>
                  {f.ai_prompt && <span className="text-[10px] text-zinc-600 truncate max-w-[200px]">{f.ai_prompt.slice(0, 40)}...</span>}
                </label>
              ))}
            </div>
          )}

          <button
            onClick={handleImport}
            disabled={selectedFieldNames.size === 0}
            className="w-full py-2 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm font-medium 
                       disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            导入 {selectedFieldNames.size} 个字段
          </button>
        </>
      )}
    </div>
  );
}

// ============== Main Component ==============

export function ProposalSelector({
  projectId,
  fieldId,
  content,
  onConfirm,
  onFieldsCreated,
  onSave,
}: ProposalSelectorProps) {
  // 解析初始数据，确保每个 proposal / field 都有唯一 id
  const initialData = useMemo<ProposalsData>(() => {
    try {
      const raw = JSON.parse(content);
      let proposals: Proposal[];
      if (raw.proposals && Array.isArray(raw.proposals)) {
        proposals = raw.proposals;
      } else if (Array.isArray(raw)) {
        proposals = raw;
      } else {
        return { proposals: [], error: "未找到方案数据" };
      }

      // 补全缺失的 id，避免 React key 冲突
      const ensured = proposals.map((p: any, pi: number) => ({
        ...p,
        id: p.id || genId(`proposal_${pi}`),
        fields: Array.isArray(p.fields)
          ? p.fields.map((f: any, fi: number) => ({
              ...f,
              id: f.id || genId(`field_${pi}_${fi}`),
            }))
          : [],
      }));

      return { ...raw, proposals: ensured };
    } catch {
      return { proposals: [], error: "JSON 解析失败" };
    }
  }, [content]);

  const [data, setData] = useState<ProposalsData>(initialData);
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [expandedProposalId, setExpandedProposalId] = useState<string | null>(null);
  const [isConfirmed, setIsConfirmed] = useState(initialData.confirmed === true);
  const [isCreatingFields, setIsCreatingFields] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showTemplateImporter, setShowTemplateImporter] = useState<string | null>(null); // proposalId or null
  const [showNewProposalTemplate, setShowNewProposalTemplate] = useState(false);
  const [dirty, setDirty] = useState(false);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // 自动保存：任何修改后 1.5s 自动保存
  const autoSave = useCallback(async (newData: ProposalsData) => {
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(async () => {
      try {
        setIsSaving(true);
        await fieldAPI.update(fieldId, {
          content: JSON.stringify(newData, null, 2),
        });
        setDirty(false);
        onSave?.();
      } catch (e) {
        console.error("自动保存失败:", e);
      } finally {
        setIsSaving(false);
      }
    }, 1500);
  }, [fieldId, onSave]);

  // 更新数据的统一入口
  const updateData = useCallback((updater: (prev: ProposalsData) => ProposalsData) => {
    setData(prev => {
      const next = updater(cloneProposals(prev));
      setDirty(true);
      autoSave(next);
      return next;
    });
  }, [autoSave]);

  // 手动保存
  const handleManualSave = async () => {
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    try {
      setIsSaving(true);
      await fieldAPI.update(fieldId, {
        content: JSON.stringify(data, null, 2),
      });
      setDirty(false);
      onSave?.();
    } catch (e) {
      console.error("保存失败:", e);
      alert("保存失败");
    } finally {
      setIsSaving(false);
    }
  };

  // ============== 方案操作 ==============

  // 添加空方案
  const addEmptyProposal = () => {
    updateData(prev => ({
        ...prev,
      proposals: [
        ...prev.proposals,
        {
          id: genId("proposal"),
          name: `自定义方案 ${prev.proposals.length + 1}`,
          description: "用户自定义的内容生产方案",
          fields: [],
        },
      ],
    }));
  };

  // 从模板创建方案
  const addProposalFromTemplate = (templateFields: ProposalField[], templateName: string) => {
    updateData(prev => ({
      ...prev,
      proposals: [
        ...prev.proposals,
        {
          id: genId("proposal"),
          name: templateName,
          description: `基于「${templateName}」模板创建`,
          fields: templateFields.map((f, i) => ({ ...f, order: i + 1 })),
        },
      ],
    }));
    setShowNewProposalTemplate(false);
  };

  // 删除方案
  const deleteProposal = (proposalId: string) => {
    if (!confirm("确定删除此方案？")) return;
    updateData(prev => ({
      ...prev,
      proposals: prev.proposals.filter(p => p.id !== proposalId),
    }));
    if (selectedProposalId === proposalId) setSelectedProposalId(null);
    if (expandedProposalId === proposalId) setExpandedProposalId(null);
  };

  // 复制方案
  const duplicateProposal = (proposalId: string) => {
    updateData(prev => {
      const src = prev.proposals.find(p => p.id === proposalId);
      if (!src) return prev;
      const copy: Proposal = {
        ...JSON.parse(JSON.stringify(src)),
        id: genId("proposal"),
        name: src.name + " (副本)",
      };
      copy.fields = copy.fields.map((f: ProposalField) => ({ ...f, id: genId("field") }));
      return { ...prev, proposals: [...prev.proposals, copy] };
    });
  };

  // 更新方案名称/描述
  const updateProposalMeta = (proposalId: string, key: "name" | "description", value: string) => {
    updateData(prev => ({
      ...prev,
      proposals: prev.proposals.map(p =>
        p.id === proposalId ? { ...p, [key]: value } : p
      ),
    }));
  };

  // ============== 字段操作 ==============

  // 更新某方案的某字段
  const updateField = (proposalId: string, fieldId: string, updated: ProposalField) => {
    updateData(prev => ({
      ...prev,
      proposals: prev.proposals.map(p =>
        p.id === proposalId
          ? { ...p, fields: p.fields.map(f => f.id === fieldId ? updated : f) }
          : p
      ),
    }));
  };

  // 删除某方案的某字段
  const deleteField = (proposalId: string, fieldId: string) => {
    updateData(prev => ({
      ...prev,
      proposals: prev.proposals.map(p =>
        p.id === proposalId
          ? { ...p, fields: p.fields.filter(f => f.id !== fieldId).map((f, i) => ({ ...f, order: i + 1 })) }
          : p
      ),
    }));
  };

  // 添加新空字段
  const addEmptyField = (proposalId: string) => {
    updateData(prev => ({
      ...prev,
      proposals: prev.proposals.map(p =>
        p.id === proposalId
          ? {
              ...p,
              fields: [
                ...p.fields,
                {
                  id: genId("field"),
                  name: "新字段",
      field_type: "richtext",
                  ai_prompt: "",
      depends_on: [],
                  order: p.fields.length + 1,
      need_review: true,
      },
              ],
            }
          : p
      ),
    }));
    };
    
  // 从模板导入字段到指定方案
  const importFieldsToProposal = (proposalId: string, importedFields: ProposalField[]) => {
    updateData(prev => ({
      ...prev,
      proposals: prev.proposals.map(p =>
        p.id === proposalId
          ? {
              ...p,
              fields: [
                ...p.fields,
                ...importedFields.map((f, i) => ({
                  ...f,
                  id: genId("field"),
                  order: p.fields.length + i + 1,
                })),
              ],
            }
          : p
      ),
    }));
  };

  // 上移/下移字段
  const moveField = (proposalId: string, fieldId: string, direction: "up" | "down") => {
    updateData(prev => ({
        ...prev,
      proposals: prev.proposals.map(p => {
        if (p.id !== proposalId) return p;
        const sorted = [...p.fields].sort((a, b) => a.order - b.order);
        const idx = sorted.findIndex(f => f.id === fieldId);
        if (idx < 0) return p;
        const swapIdx = direction === "up" ? idx - 1 : idx + 1;
        if (swapIdx < 0 || swapIdx >= sorted.length) return p;
        [sorted[idx], sorted[swapIdx]] = [sorted[swapIdx], sorted[idx]];
        return { ...p, fields: sorted.map((f, i) => ({ ...f, order: i + 1 })) };
      }),
    }));
  };

  // ============== 确认并创建字段 ==============

  const handleConfirm = async () => {
    const proposal = data.proposals.find(p => p.id === selectedProposalId);
    if (!proposal) {
      alert("请先选择一个方案");
      return;
    }

    setIsCreatingFields(true);
    try {
      // 两轮创建：proposal 中 depends_on 可能存 field ID（LLM 生成）或 name（UI 编辑），需统一转为实际字段 ID
      const sortedFields = [...proposal.fields].sort((a, b) => a.order - b.order);

      // 第一轮：创建所有字段（不带依赖），建立 proposalId/name → realId 映射
      const proposalToRealId: Record<string, string> = {};
      const createdEntries: Array<{ fieldId: string; deps: string[] }> = [];

      for (const pField of sortedFields) {
        const created = await fieldAPI.create({
          project_id: projectId,
          name: pField.name,
          phase: "produce_inner",
          field_type: pField.field_type || "richtext",
          ai_prompt: pField.ai_prompt || "",
          status: "pending",
          need_review: pField.need_review !== false,
          dependencies: { depends_on: [], dependency_type: "all" },
          constraints: pField.constraints || {},
        });
        // 映射 proposal 内的 field id 和 name → 实际创建的 field id
        if (pField.id) proposalToRealId[pField.id] = created.id;
        proposalToRealId[pField.name] = created.id;
        createdEntries.push({ fieldId: created.id, deps: pField.depends_on || [] });
      }

      // 第二轮：将 depends_on 中的 proposalId/name 转换为实际字段 ID 并更新
      for (const entry of createdEntries) {
        if (entry.deps.length > 0) {
          const realDepsIds = entry.deps
            .map(dep => proposalToRealId[dep])
            .filter(Boolean);
          if (realDepsIds.length > 0) {
            await fieldAPI.update(entry.fieldId, {
              dependencies: { depends_on: realDepsIds, dependency_type: "all" },
            });
          }
        }
      }

      // 保存确认状态
      const confirmedData: ProposalsData = {
        ...data,
        selected_proposal_id: proposal.id,
        confirmed: true,
      };
      await fieldAPI.update(fieldId, {
        content: JSON.stringify(confirmedData, null, 2),
        status: "completed",
      });

      setIsConfirmed(true);
      setData(confirmedData);
      onFieldsCreated?.();
      onConfirm();
    } catch (err) {
      console.error("创建字段失败:", err);
      alert("创建字段失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsCreatingFields(false);
    }
  };

  // ============== 重新选择方案 ==============

  const handleResetConfirm = async () => {
    if (!confirm("重新选择方案将删除当前内涵生产阶段的所有字段，确定继续？")) return;

    setIsResetting(true);
    try {
      // 1. 删除已创建的 produce_inner 字段
      const produceFields = await fieldAPI.listByProject(projectId, "produce_inner");
      for (const f of produceFields) {
        await fieldAPI.delete(f.id);
      }

      // 2. 重置确认状态并保存
      const resetData: ProposalsData = {
        ...data,
        confirmed: false,
        selected_proposal_id: undefined,
      };
      await fieldAPI.update(fieldId, {
        content: JSON.stringify(resetData, null, 2),
        status: "in_progress",
      });

      setIsConfirmed(false);
      setSelectedProposalId(null);
      setData(resetData);
      onFieldsCreated?.(); // 通知父组件刷新字段列表
    } catch (err) {
      console.error("重置方案失败:", err);
      alert("重置失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsResetting(false);
    }
  };

  // ============== Render ==============

  // 即使无方案，也继续渲染（允许用户手动添加自定义方案）

  const readOnly = isConfirmed;
            
            return (
    <div className="space-y-5">
      {/* 顶部栏 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-200">内涵设计方案</h2>
          <p className="text-sm text-zinc-500 mt-0.5">
            {readOnly
              ? `已确认方案「${data.proposals.find(p => p.id === data.selected_proposal_id)?.name || ""}」`
              : `${data.proposals.length} 个方案 · 编辑后自动保存 · 选择一个确认后进入内涵生产`}
          </p>
                </div>
        <div className="flex items-center gap-2">
          {dirty && !readOnly && (
            <span className="text-xs text-amber-400 animate-pulse">未保存</span>
          )}
          {isSaving && (
            <span className="text-xs text-zinc-500">保存中...</span>
          )}
          {!readOnly && (
            <button onClick={handleManualSave} className="p-1.5 text-zinc-400 hover:text-zinc-200 rounded-lg hover:bg-surface-2" title="立即保存">
              <Save className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* 方案列表 */}
      <div className="space-y-4">
        {data.proposals.length === 0 && (
          <div className="text-center py-8 text-zinc-500">
            <p className="text-sm">暂无方案。</p>
            <p className="text-xs mt-1 text-zinc-600">
              在右侧对话框输入"开始"生成 AI 方案，或点击下方按钮手动添加。
            </p>
                </div>
              )}
        {data.proposals.map((proposal, pIndex) => {
          const isSelected = selectedProposalId === proposal.id;
          const isExpanded = expandedProposalId === proposal.id;
          const sortedFields = [...proposal.fields].sort((a, b) => a.order - b.order);

          return (
            <div
              key={proposal.id}
              className={`
                rounded-xl border transition-all overflow-hidden
                ${isSelected ? "border-brand-500/50 bg-brand-500/5 ring-1 ring-brand-500/20" : "border-surface-3 bg-surface-2"}
                ${readOnly ? "opacity-80" : ""}
              `}
            >
              {/* 方案头部 */}
              <div className="px-4 py-3 flex items-start gap-3">
                {/* 选中圆圈 */}
                            <button
                  onClick={() => !readOnly && setSelectedProposalId(isSelected ? null : proposal.id)}
                  className={`mt-0.5 w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors
                    ${isSelected ? "border-brand-500 bg-brand-500" : "border-zinc-600 hover:border-zinc-400"}
                    ${readOnly ? "cursor-default" : "cursor-pointer"}`}
                >
                  {isSelected && <Check className="w-3 h-3 text-white" />}
                            </button>

                {/* 方案信息 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-600/20 text-purple-400 font-medium shrink-0">
                      方案 {pIndex + 1}
                        </span>
                    {readOnly ? (
                      <h3 className="font-semibold text-zinc-200 truncate">{proposal.name}</h3>
                    ) : (
                          <input
                        value={proposal.name}
                        onChange={e => updateProposalMeta(proposal.id, "name", e.target.value)}
                        className="font-semibold text-zinc-200 bg-transparent border-none outline-none flex-1 min-w-0
                                   focus:ring-1 focus:ring-brand-500/30 rounded px-1 -mx-1"
                        placeholder="方案名称"
                      />
                        )}
                      </div>
                  {readOnly ? (
                    <p className="text-sm text-zinc-400">{proposal.description}</p>
                  ) : (
                    <input
                      value={proposal.description}
                      onChange={e => updateProposalMeta(proposal.id, "description", e.target.value)}
                      className="text-sm text-zinc-400 bg-transparent border-none outline-none w-full
                                 focus:ring-1 focus:ring-brand-500/30 rounded px-1 -mx-1"
                      placeholder="方案描述..."
                    />
                  )}
                  <div className="flex items-center gap-2 mt-1.5 text-xs text-zinc-500">
                    <FileText className="w-3 h-3" />
                    <span>{sortedFields.length} 个字段</span>
                    {!isExpanded && sortedFields.length > 0 && (
                      <span className="text-zinc-600 truncate">· {sortedFields.map(f => f.name).join(" → ")}</span>
                    )}
                  </div>
                    </div>

                {/* 方案操作按钮 */}
                <div className="flex items-center gap-1 shrink-0">
                  <button onClick={() => setExpandedProposalId(isExpanded ? null : proposal.id)}
                    className="p-1.5 text-zinc-500 hover:text-zinc-300 rounded-lg hover:bg-surface-3"
                    title={isExpanded ? "收起" : "展开编辑"}>
                    {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>
                  {!readOnly && (
                    <>
                      <button onClick={() => duplicateProposal(proposal.id)}
                        className="p-1.5 text-zinc-600 hover:text-zinc-300 rounded-lg hover:bg-surface-3"
                        title="复制方案">
                        <Copy className="w-3.5 h-3.5" />
                        </button>
                      <button onClick={() => deleteProposal(proposal.id)}
                        className="p-1.5 text-zinc-600 hover:text-red-400 rounded-lg hover:bg-surface-3"
                        title="删除方案">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </>
                      )}
                    </div>
      </div>

              {/* 展开：字段列表 + 操作 */}
              {isExpanded && (
                <div className="border-t border-surface-3">
                  {/* 字段列表 */}
                  <div className="p-3 space-y-2">
                    {sortedFields.length === 0 && (
                      <p className="text-sm text-zinc-600 italic text-center py-4">暂无字段，请添加</p>
                    )}
                    {sortedFields.map((field, fi) => (
                      <FieldEditor
                        key={field.id}
            field={field}
                        allFields={sortedFields}
                        onUpdate={updated => updateField(proposal.id, field.id, updated)}
                        onDelete={() => deleteField(proposal.id, field.id)}
                        onMoveUp={() => moveField(proposal.id, field.id, "up")}
                        onMoveDown={() => moveField(proposal.id, field.id, "down")}
                        isFirst={fi === 0}
                        isLast={fi === sortedFields.length - 1}
                        readOnly={readOnly}
                      />
                ))}
              </div>

                  {/* 添加字段操作栏 */}
                  {!readOnly && (
                    <div className="border-t border-surface-3 px-3 py-2.5 flex items-center gap-2">
          <button
                        onClick={() => addEmptyField(proposal.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 
                                   bg-surface-1 hover:bg-surface-3 rounded-lg border border-surface-3 transition-colors"
          >
                        <Plus className="w-3.5 h-3.5" />
                        添加字段
          </button>
          <button
                        onClick={() => setShowTemplateImporter(showTemplateImporter === proposal.id ? null : proposal.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200
                                   bg-surface-1 hover:bg-surface-3 rounded-lg border border-surface-3 transition-colors"
          >
                        <BookTemplate className="w-3.5 h-3.5" />
                        从模板导入
          </button>
        </div>
                  )}

                  {/* 模板导入面板 */}
                  {showTemplateImporter === proposal.id && (
                    <div className="px-3 pb-3">
                      <TemplateImporter
                        onImportFields={(fields, _tplName) => importFieldsToProposal(proposal.id, fields)}
                        onClose={() => setShowTemplateImporter(null)}
                      />
      </div>
                  )}
                </div>
              )}
    </div>
  );
        })}
        </div>

      {/* 添加方案操作栏 */}
      {!readOnly && (
        <div className="flex items-center gap-2">
              <button
            onClick={addEmptyProposal}
            className="flex items-center gap-1.5 px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200
                       bg-surface-2 hover:bg-surface-3 rounded-lg border border-dashed border-surface-4 transition-colors"
          >
            <Plus className="w-4 h-4" />
            添加自定义方案
              </button>
          <button
            onClick={() => setShowNewProposalTemplate(!showNewProposalTemplate)}
            className="flex items-center gap-1.5 px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200
                       bg-surface-2 hover:bg-surface-3 rounded-lg border border-dashed border-surface-4 transition-colors"
          >
            <PackagePlus className="w-4 h-4" />
            从模板创建方案
          </button>
        </div>
      )}

      {/* 从模板创建整个方案 */}
      {showNewProposalTemplate && !readOnly && (
        <div className="mt-2">
          <TemplateImporter
            onImportFields={(fields, templateName) => {
              addProposalFromTemplate(fields, templateName || "模板方案");
            }}
            onClose={() => setShowNewProposalTemplate(false)}
            />
          </div>
      )}

      {/* 底部确认栏 */}
      <div className="flex items-center justify-between pt-4 border-t border-surface-3">
        {readOnly ? (
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 text-green-400">
              <Check className="w-5 h-5" />
              <span>已确认方案，字段已导入内涵生产阶段</span>
            </div>
            <button
              onClick={handleResetConfirm}
              disabled={isResetting}
              className="ml-auto px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200
                         bg-surface-2 hover:bg-surface-3 rounded-lg border border-surface-3 transition-colors
                         disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isResetting ? "重置中..." : "重新选择方案"}
            </button>
          </div>
        ) : (
          <>
            <p className="text-sm text-zinc-500">
              {selectedProposalId
                ? `已选择「${data.proposals.find(p => p.id === selectedProposalId)?.name}」（${
                    data.proposals.find(p => p.id === selectedProposalId)?.fields.length || 0
                  } 个字段）`
                : "点击方案左侧圆圈选中，然后点击确认"}
            </p>
          <button
              onClick={handleConfirm}
              disabled={!selectedProposalId || isCreatingFields}
              className="px-5 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm font-medium
                         flex items-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isCreatingFields ? "创建中..." : (
                <><Send className="w-4 h-4" />确认并进入内涵生产</>
              )}
          </button>
          </>
        )}
      </div>
    </div>
  );
}
