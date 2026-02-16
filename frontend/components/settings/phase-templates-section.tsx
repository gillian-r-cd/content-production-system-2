// frontend/components/settings/phase-templates-section.tsx
// 功能: 流程模板管理（PhaseTemplate - 项目创建时使用的模板）

"use client";

import { useState } from "react";
import { phaseTemplateAPI } from "@/lib/api";
import type { PhaseTemplate } from "@/lib/api";
import { FormField } from "./shared";

export function PhaseTemplatesSection({ templates, onRefresh }: { templates: PhaseTemplate[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<any>({});
  const [isCreating, setIsCreating] = useState(false);

  const handleCreate = () => {
    setIsCreating(true);
    setEditForm({
      name: "",
      description: "",
      phases: [{ name: "默认组", block_type: "phase", special_handler: null, order_index: 0, default_fields: [] }],
    });
  };

  const handleEdit = (template: PhaseTemplate) => {
    setEditingId(template.id);
    setEditForm({
      name: template.name,
      description: template.description,
      phases: JSON.parse(JSON.stringify(template.phases || [])),
    });
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await phaseTemplateAPI.create(editForm);
      } else if (editingId) {
        await phaseTemplateAPI.update(editingId, editForm);
      }
      setEditingId(null);
      setIsCreating(false);
      onRefresh();
    } catch (err) {
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此模板？")) return;
    try {
      await phaseTemplateAPI.delete(id);
      onRefresh();
    } catch (err) {
      alert("删除失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // ---- Phase 操作 ----
  const addPhase = () => {
    const phases = [...(editForm.phases || [])];
    phases.push({
      name: "",
      block_type: "phase",
      special_handler: null,
      order_index: phases.length,
      default_fields: [],
    });
    setEditForm({ ...editForm, phases });
  };

  const updatePhase = (pIdx: number, key: string, value: any) => {
    const phases = [...editForm.phases];
    phases[pIdx] = { ...phases[pIdx], [key]: value };
    setEditForm({ ...editForm, phases });
  };

  const removePhase = (pIdx: number) => {
    const phases = editForm.phases.filter((_: any, i: number) => i !== pIdx);
    // 重新排序 order_index
    phases.forEach((p: any, i: number) => { p.order_index = i; });
    setEditForm({ ...editForm, phases });
  };

  // ---- Field 操作 ----
  const addField = (pIdx: number) => {
    const phases = [...editForm.phases];
    phases[pIdx] = {
      ...phases[pIdx],
      default_fields: [
        ...(phases[pIdx].default_fields || []),
        { name: "", block_type: "field", ai_prompt: "", content: "", pre_questions: [], depends_on: [] },
      ],
    };
    setEditForm({ ...editForm, phases });
  };

  const updateField = (pIdx: number, fIdx: number, key: string, value: any) => {
    const phases = JSON.parse(JSON.stringify(editForm.phases));
    phases[pIdx].default_fields[fIdx][key] = value;
    setEditForm({ ...editForm, phases });
  };

  const removeField = (pIdx: number, fIdx: number) => {
    const phases = JSON.parse(JSON.stringify(editForm.phases));
    phases[pIdx].default_fields.splice(fIdx, 1);
    setEditForm({ ...editForm, phases });
  };

  // 收集所有字段名（用于依赖选择）
  const getAllFieldNames = (excludePIdx: number, excludeFIdx: number): string[] => {
    const names: string[] = [];
    (editForm.phases || []).forEach((phase: any, pIdx: number) => {
      (phase.default_fields || []).forEach((field: any, fIdx: number) => {
        if (pIdx === excludePIdx && fIdx === excludeFIdx) return;
        if (field.name) names.push(field.name);
      });
    });
    return names;
  };

  const SPECIAL_HANDLERS = [
    { value: "", label: "无" },
    { value: "intent", label: "意图分析" },
    { value: "research", label: "消费者调研" },
    { value: "evaluate", label: "评估" },
  ];

  const renderForm = () => (
    <div className="p-5 bg-surface-2 border border-brand-500/50 rounded-xl mb-4">
      <div className="space-y-4">
        {/* 基础信息 */}
        <div className="grid grid-cols-2 gap-4">
          <FormField label="模板名称">
            <input
              value={editForm.name || ""}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
              placeholder="如：UMU 课程模板"
            />
          </FormField>
          <FormField label="描述">
            <input
              value={editForm.description || ""}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
              placeholder="模板的用途说明"
            />
          </FormField>
        </div>

        {/* 组（Phase）列表 */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-semibold text-zinc-200">组结构</h4>
            <button
              onClick={addPhase}
              className="px-3 py-1 text-xs bg-brand-600 hover:bg-brand-700 rounded-lg text-white"
            >
              + 添加组
            </button>
          </div>

          <div className="space-y-4">
            {(editForm.phases || []).map((phase: any, pIdx: number) => (
              <div key={pIdx} className="bg-surface-1 border border-surface-3 rounded-xl p-4">
                {/* Phase header */}
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-xs text-zinc-500 font-mono">#{pIdx + 1}</span>
                  <input
                    value={phase.name || ""}
                    onChange={(e) => updatePhase(pIdx, "name", e.target.value)}
                    className="flex-1 px-3 py-1.5 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                    placeholder="组名称"
                  />
                  <select
                    value={phase.special_handler || ""}
                    onChange={(e) => updatePhase(pIdx, "special_handler", e.target.value || null)}
                    className="px-2 py-1.5 bg-surface-2 border border-surface-3 rounded-lg text-zinc-300 text-xs"
                  >
                    {SPECIAL_HANDLERS.map((h) => (
                      <option key={h.value} value={h.value}>{h.label}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => removePhase(pIdx)}
                    className="text-red-400 hover:text-red-300 text-xs"
                  >
                    删除组
                  </button>
                </div>

                {/* Fields in this phase */}
                <div className="ml-4 space-y-3">
                  {(phase.default_fields || []).map((field: any, fIdx: number) => (
                    <div key={fIdx} className="bg-surface-2 border border-surface-3 rounded-lg p-3 space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-zinc-500 font-mono">
                          #{pIdx + 1}.{fIdx + 1}
                        </span>
                        <input
                          value={field.name || ""}
                          onChange={(e) => updateField(pIdx, fIdx, "name", e.target.value)}
                          className="flex-1 px-2 py-1 bg-surface-1 border border-surface-3 rounded text-zinc-200 text-sm"
                          placeholder="内容块名称"
                        />
                        <select
                          value={field.block_type || "field"}
                          onChange={(e) => updateField(pIdx, fIdx, "block_type", e.target.value)}
                          className="px-2 py-1 bg-surface-1 border border-surface-3 rounded text-zinc-300 text-xs"
                        >
                          <option value="field">内容块</option>
                          <option value="phase">子组</option>
                        </select>
                        <button
                          onClick={() => removeField(pIdx, fIdx)}
                          className="text-red-400 hover:text-red-300 text-xs"
                        >
                          删除
                        </button>
                      </div>

                      {/* AI 提示词 */}
                      <FormField label="AI 生成提示词" hint="指导 AI 如何生成这个内容块的内容">
                        <textarea
                          value={field.ai_prompt || ""}
                          onChange={(e) => updateField(pIdx, fIdx, "ai_prompt", e.target.value)}
                          rows={2}
                          className="w-full px-2 py-1.5 bg-surface-1 border border-surface-3 rounded text-zinc-200 text-sm resize-y"
                          placeholder="请根据项目意图和消费者画像，生成..."
                        />
                      </FormField>

                      {/* 预置内容 */}
                      <FormField label="预置内容" hint="模板自带的初始内容（可选，应用模板时将自动填入编辑区）">
                        <textarea
                          value={field.content || ""}
                          onChange={(e) => updateField(pIdx, fIdx, "content", e.target.value)}
                          rows={3}
                          className="w-full px-2 py-1.5 bg-surface-1 border border-surface-3 rounded text-zinc-200 text-sm resize-y"
                          placeholder="此内容块的预置内容..."
                        />
                      </FormField>

                      {/* 依赖 */}
                      {(() => {
                        const otherNames = getAllFieldNames(pIdx, fIdx);
                        if (otherNames.length === 0) return null;
                        return (
                          <FormField label="依赖内容块" hint="选择这个内容块依赖的其他内容块">
                            <div className="flex flex-wrap gap-2">
                              {otherNames.map((name) => (
                                <label key={name} className="flex items-center gap-1.5 text-xs text-zinc-300">
                                  <input
                                    type="checkbox"
                                    checked={(field.depends_on || []).includes(name)}
                                    onChange={(e) => {
                                      const deps = field.depends_on || [];
                                      if (e.target.checked) {
                                        updateField(pIdx, fIdx, "depends_on", [...deps, name]);
                                      } else {
                                        updateField(pIdx, fIdx, "depends_on", deps.filter((d: string) => d !== name));
                                      }
                                    }}
                                  />
                                  {name}
                                </label>
                              ))}
                            </div>
                          </FormField>
                        );
                      })()}

                      {/* need_review */}
                      <label className="flex items-center gap-2 text-xs text-zinc-400">
                        <input
                          type="checkbox"
                          checked={field.need_review !== false}
                          onChange={(e) => updateField(pIdx, fIdx, "need_review", e.target.checked)}
                        />
                        需要人工确认
                      </label>
                    </div>
                  ))}

                  <button
                    onClick={() => addField(pIdx)}
                    className="text-xs text-brand-400 hover:text-brand-300"
                  >
                    + 添加内容块
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          <button onClick={handleSave} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm">保存</button>
          <button onClick={() => { setEditingId(null); setIsCreating(false); }} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg text-sm">取消</button>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-bold text-zinc-100">流程模板</h2>
          <p className="text-sm text-zinc-500 mt-1">
            创建项目时使用的模板。包含组结构和内容块定义（含预置内容、提示词等）。
          </p>
        </div>
        <button onClick={handleCreate} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm font-medium">
          + 新建模板
        </button>
      </div>

      {(isCreating || editingId) && renderForm()}

      <div className="space-y-3">
        {templates.map((template) => (
          <div key={template.id} className="bg-surface-2 border border-surface-3 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-medium text-zinc-200">{template.name}</h3>
                  {template.is_default && (
                    <span className="px-1.5 py-0.5 text-xs bg-brand-500/20 text-brand-400 rounded">默认</span>
                  )}
                  {template.is_system && (
                    <span className="px-1.5 py-0.5 text-xs bg-zinc-500/20 text-zinc-400 rounded">系统</span>
                  )}
                </div>
                <p className="text-sm text-zinc-500 mt-1">{template.description}</p>
                <div className="flex gap-3 mt-2 text-xs text-zinc-400">
                  <span>{template.phases.length} 个组</span>
                  <span>
                    {template.phases.reduce((sum: number, p: any) => sum + (p.default_fields || []).length, 0)} 个内容块
                  </span>
                  <span>
                    {template.phases.reduce((sum: number, p: any) =>
                      sum + (p.default_fields || []).filter((f: any) => f.content).length, 0
                    )} 个有预置内容
                  </span>
                </div>
              </div>
              <div className="flex gap-2">
                {!template.is_system && (
                  <>
                    <button
                      onClick={() => handleEdit(template)}
                      className="px-3 py-1.5 text-xs text-brand-400 hover:text-brand-300 bg-brand-500/10 hover:bg-brand-500/20 rounded-lg"
                    >
                      编辑
                    </button>
                    <button
                      onClick={() => handleDelete(template.id)}
                      className="px-3 py-1.5 text-xs text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 rounded-lg"
                    >
                      删除
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* 预览：展示组和字段 */}
            <div className="mt-3 space-y-2">
              {template.phases.map((phase: any, pIdx: number) => (
                <div key={pIdx} className="text-xs">
                  <div className="flex items-center gap-1.5 text-zinc-300">
                    <span className="text-zinc-500">📁</span>
                    <span className="font-medium">{phase.name}</span>
                    {phase.special_handler && (
                      <span className="px-1 py-0.5 bg-surface-3 rounded text-zinc-500">{phase.special_handler}</span>
                    )}
                  </div>
                  {(phase.default_fields || []).length > 0 && (
                    <div className="ml-5 mt-1 space-y-0.5">
                      {phase.default_fields.map((f: any, fIdx: number) => (
                        <div key={fIdx} className="flex items-center gap-1.5 text-zinc-500">
                          <span>📄</span>
                          <span>{f.name}</span>
                          {f.ai_prompt && <span className="text-brand-400/60">✨</span>}
                          {f.content && <span className="text-emerald-400/60">📝</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}

        {templates.length === 0 && !isCreating && (
          <div className="text-center py-12 text-zinc-500">
            <p>还没有流程模板</p>
            <p className="text-xs mt-1">点击"新建模板"创建第一个</p>
          </div>
        )}
      </div>
    </div>
  );
}
