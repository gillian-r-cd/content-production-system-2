// frontend/components/settings/templates-section.tsx
// 功能: 内容块模板管理（可视化编辑器）

"use client";

import { useState } from "react";
import { settingsAPI } from "@/lib/api";
import { FormField, TagInput, ImportExportButtons, SingleExportButton, downloadJSON } from "./shared";

interface TemplateField {
  name: string;
  type?: string;
  ai_prompt?: string;
  content?: string;
  pre_questions?: string[];
  depends_on?: string[];
  need_review?: boolean;
  auto_generate?: boolean;
}

interface FieldTemplateItem {
  id: string;
  name: string;
  description?: string;
  category?: string;
  fields?: TemplateField[];
}

interface TemplateEditForm {
  name: string;
  description: string;
  category: string;
  fields: TemplateField[];
}

export function TemplatesSection({ templates, onRefresh }: { templates: FieldTemplateItem[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<TemplateEditForm>({ name: "", description: "", category: "通用", fields: [] });
  const [isCreating, setIsCreating] = useState(false);

  const handleExportAll = async () => {
    try {
      const result = await settingsAPI.exportFieldTemplates();
      downloadJSON(result, `field_templates_${new Date().toISOString().split("T")[0]}.json`);
    } catch {
      alert("导出失败");
    }
  };

  const handleExportSingle = async (id: string) => {
    try {
      const result = await settingsAPI.exportFieldTemplates(id);
      const template = templates.find(t => t.id === id);
      downloadJSON(result, `field_template_${template?.name || id}.json`);
    } catch {
      alert("导出失败");
    }
  };

  const handleImport = async (data: unknown[]) => {
    await settingsAPI.importFieldTemplates(data);
    onRefresh();
  };

  const handleCreate = () => {
    setIsCreating(true);
    setEditForm({ name: "", description: "", category: "通用", fields: [] });
  };

  const handleEdit = (template: FieldTemplateItem) => {
    setEditingId(template.id);
    setEditForm({
      name: template.name || "",
      description: template.description || "",
      category: template.category || "通用",
      fields: template.fields || [],
    });
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await settingsAPI.createFieldTemplate(editForm);
      } else {
        await settingsAPI.updateFieldTemplate(editingId!, editForm);
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
      await settingsAPI.deleteFieldTemplate(id);
      onRefresh();
    } catch {
      alert("删除失败");
    }
  };

  // 字段编辑辅助函数
  const addField = () => {
    setEditForm({
      ...editForm,
      fields: [...(editForm.fields || []), { name: "", type: "richtext", ai_prompt: "", content: "", pre_questions: [], depends_on: [], auto_generate: false }],
    });
  };

  const updateField = (index: number, key: keyof TemplateField, value: unknown) => {
    const newFields = [...editForm.fields];
    newFields[index] = { ...newFields[index], [key]: value as never };
    setEditForm({ ...editForm, fields: newFields });
  };

  const removeField = (index: number) => {
    const newFields = editForm.fields.filter((_, i: number) => i !== index);
    setEditForm({ ...editForm, fields: newFields });
  };

  const moveField = (index: number, direction: "up" | "down") => {
    const newIndex = direction === "up" ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= editForm.fields.length) return;
    const newFields = [...editForm.fields];
    [newFields[index], newFields[newIndex]] = [newFields[newIndex], newFields[index]];
    setEditForm({ ...editForm, fields: newFields });
  };

  const renderForm = () => (
    <div className="p-5 bg-surface-2 border border-brand-500/50 rounded-xl mb-4">
      <div className="space-y-5">
        <div className="grid grid-cols-3 gap-4">
          <FormField label="模板名称">
            <input
              type="text"
              value={editForm.name || ""}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              placeholder="如：产品介绍模板"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
          <FormField label="分类">
            <input
              type="text"
              value={editForm.category || ""}
              onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
              placeholder="如：营销、教育"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
          <FormField label="描述">
            <input
              type="text"
              value={editForm.description || ""}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              placeholder="模板用途说明"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
        </div>

        {/* 内容块列表 */}
        <div className="border-t border-surface-3 pt-4">
          <div className="flex justify-between items-center mb-4">
            <h4 className="text-sm font-medium text-zinc-300">内容块列表</h4>
            <button onClick={addField} className="px-3 py-1 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg">
              + 添加内容块
            </button>
          </div>

          {(editForm.fields || []).length === 0 ? (
            <div className="text-center py-8 text-zinc-500 border border-dashed border-surface-3 rounded-lg">
              还没有内容块，点击「添加内容块」开始
            </div>
          ) : (
            <div className="space-y-4">
              {(editForm.fields || []).map((field, index: number) => (
                <div key={index} className="p-4 bg-surface-1 border border-surface-3 rounded-lg">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-500 text-sm">#{index + 1}</span>
                      <div className="flex gap-1">
                        <button
                          onClick={() => moveField(index, "up")}
                          disabled={index === 0}
                          className="px-2 py-1 text-xs bg-surface-3 rounded disabled:opacity-30"
                        >
                          ↑
                        </button>
                        <button
                          onClick={() => moveField(index, "down")}
                          disabled={index === editForm.fields.length - 1}
                          className="px-2 py-1 text-xs bg-surface-3 rounded disabled:opacity-30"
                        >
                          ↓
                        </button>
                      </div>
                    </div>
                    <button onClick={() => removeField(index)} className="text-red-400 hover:text-red-300 text-sm">
                      删除
                    </button>
                  </div>

                  <div className="grid grid-cols-2 gap-4 mb-3">
                    <FormField label="内容块名称">
                      <input
                        type="text"
                        value={field.name || ""}
                        onChange={(e) => updateField(index, "name", e.target.value)}
                        placeholder="如：产品定位"
                        className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                      />
                    </FormField>
                    <FormField label="内容块类型">
                      <select
                        value={field.type || "text"}
                        onChange={(e) => updateField(index, "type", e.target.value)}
                        className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                      >
                        <option value="text">短文本</option>
                        <option value="longtext">长文本</option>
                        <option value="markdown">Markdown</option>
                        <option value="list">列表</option>
                      </select>
                    </FormField>
                  </div>

                  <FormField label="AI 生成提示词" hint="指导 AI 如何生成这个内容块的内容">
                    <textarea
                      value={field.ai_prompt || ""}
                      onChange={(e) => updateField(index, "ai_prompt", e.target.value)}
                      placeholder="请根据项目意图和消费者画像，生成一段简洁有力的产品定位..."
                      rows={3}
                      className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                    />
                  </FormField>

                  <div className="mt-3">
                    <FormField label="预置内容" hint="模板自带的初始内容（可选，应用模板时将自动填入编辑区）">
                      <textarea
                        value={field.content || ""}
                        onChange={(e) => updateField(index, "content", e.target.value)}
                        placeholder="在此输入模板自带的初始内容，如固定前置说明、框架模板等..."
                        rows={3}
                        className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                      />
                    </FormField>
                  </div>

                  <div className="mt-3">
                    <FormField label="生成前提问" hint="生成前需要用户回答的问题（可选）">
                      <TagInput
                        value={field.pre_questions || []}
                        onChange={(v) => updateField(index, "pre_questions", v)}
                        placeholder="输入问题后按回车，如：目标用户是谁？"
                      />
                    </FormField>
                  </div>

                  {index > 0 && (
                    <div className="mt-3">
                      <FormField label="依赖内容块" hint="选择这个内容块依赖的其他内容块（它们的内容会作为生成上下文）">
                        <div className="flex flex-wrap gap-2">
                          {editForm.fields.slice(0, index).map((f, i: number) => (
                            <label key={i} className="flex items-center gap-2 text-sm text-zinc-300">
                              <input
                                type="checkbox"
                                checked={(field.depends_on || []).includes(f.name)}
                                onChange={(e) => {
                                  const deps = field.depends_on || [];
                                  if (e.target.checked) {
                                    updateField(index, "depends_on", [...deps, f.name]);
                                  } else {
                                    updateField(index, "depends_on", deps.filter((d: string) => d !== f.name));
                                  }
                                }}
                              />
                              {f.name || `内容块 ${i + 1}`}
                            </label>
                          ))}
                        </div>
                      </FormField>
                    </div>
                  )}

                  {/* need_review + auto_generate */}
                  <div className="mt-3 flex items-center gap-4">
                    <label className="flex items-center gap-2 text-xs text-zinc-400">
                      <input
                        type="checkbox"
                        checked={field.need_review !== false}
                        onChange={(e) => updateField(index, "need_review", e.target.checked)}
                      />
                      需要人工确认
                    </label>
                    {/* 自动生成：仅非首个内容块显示（第一个内容块没有上游依赖，无法自动触发） */}
                    {index > 0 && (
                      <label className="flex items-center gap-2 text-xs text-zinc-400">
                        <input
                          type="checkbox"
                          checked={field.auto_generate === true}
                          onChange={(e) => updateField(index, "auto_generate", e.target.checked)}
                        />
                        自动生成（依赖就绪时自动触发）
                      </label>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex gap-2 pt-2">
          <button onClick={handleSave} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">保存</button>
          <button onClick={() => { setEditingId(null); setIsCreating(false); }} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">取消</button>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">内容块模板</h2>
          <p className="text-sm text-zinc-500 mt-1">定义可复用的内容块结构，创建项目时可以引用</p>
        </div>
        <div className="flex items-center gap-3">
          <ImportExportButtons
            typeName="内容块模板"
            onExportAll={handleExportAll}
            onImport={handleImport}
          />
          <button onClick={handleCreate} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">
            + 新建模板
          </button>
        </div>
      </div>

      {isCreating && renderForm()}

      <div className="grid gap-4">
        {templates.map((template) => (
          <div key={template.id}>
            {editingId === template.id ? renderForm() : (
              <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-zinc-200">{template.name}</h3>
                      <span className="text-xs bg-surface-3 px-2 py-1 rounded-full text-zinc-400">{template.category}</span>
                    </div>
                    <p className="text-sm text-zinc-500 mt-1">{template.description}</p>
                    {(template.fields || []).length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {(template.fields || []).map((f, i: number) => (
                          <span key={i} className="text-xs bg-brand-600/10 text-brand-400 px-2 py-1 rounded">
                            {f.name}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <SingleExportButton onExport={() => handleExportSingle(template.id)} title="导出此模板" />
                    <button onClick={() => handleEdit(template)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">编辑</button>
                    <button onClick={() => handleDelete(template.id)} className="px-3 py-1 text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg">删除</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
        {templates.length === 0 && !isCreating && (
          <div className="text-center py-12 text-zinc-500">
            还没有内容块模板，点击上方「新建模板」创建一个
          </div>
        )}
      </div>
    </div>
  );
}
