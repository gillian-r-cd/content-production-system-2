// frontend/components/settings/templates-section.tsx
// 功能: 内容块模板管理，统一编辑 FieldTemplate.root_nodes 树结构
// 主要组件: TemplatesSection
// 数据结构: FieldTemplateItem / TemplateEditForm（使用 root_nodes 作为单一编辑真相）

"use client";

import { useEffect, useState } from "react";
import { settingsAPI, modelsAPI } from "@/lib/api";
import type { ModelInfo, TemplateNode } from "@/lib/api";
import { FormField, ImportExportButtons, SingleExportButton, downloadJSON } from "./shared";
import { TemplateTreeEditor } from "./template-tree-editor";

interface FieldTemplateItem {
  id: string;
  name: string;
  description?: string;
  category?: string;
  schema_version?: number;
  fields?: Array<{ name: string; model_override?: string | null }>;
  root_nodes?: TemplateNode[];
}

interface TemplateEditForm {
  name: string;
  description: string;
  category: string;
  root_nodes: TemplateNode[];
}

export function TemplatesSection({ templates, onRefresh }: { templates: FieldTemplateItem[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<TemplateEditForm>({ name: "", description: "", category: "通用", root_nodes: [] });
  const [isCreating, setIsCreating] = useState(false);
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);

  // 加载可用模型列表
  useEffect(() => {
    modelsAPI.list().then(resp => {
      setAvailableModels(resp.models || []);
    }).catch(() => { /* 模型列表加载失败不阻塞页面 */ });
  }, []);

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
    setEditForm({ name: "", description: "", category: "通用", root_nodes: [] });
  };

  const handleEdit = (template: FieldTemplateItem) => {
    setEditingId(template.id);
    setEditForm({
      name: template.name || "",
      description: template.description || "",
      category: template.category || "通用",
      root_nodes: template.root_nodes || [],
    });
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await settingsAPI.createFieldTemplate({ ...editForm, schema_version: 2 });
      } else {
        await settingsAPI.updateFieldTemplate(editingId!, { ...editForm, schema_version: 2 });
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

        {/* 模板树 */}
        <div className="border-t border-surface-3 pt-4">
          <TemplateTreeEditor
            nodes={editForm.root_nodes}
            onChange={(root_nodes) => setEditForm({ ...editForm, root_nodes })}
            availableModels={availableModels}
            topLevelLabel="模板结构"
            emptyText="还没有添加内容，先添加顶层阶段或分组。"
          />
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
                      <span className="text-xs bg-brand-600/10 px-2 py-1 rounded-full text-brand-400">
                        v{template.schema_version || 1}
                      </span>
                    </div>
                    <p className="text-sm text-zinc-500 mt-1">{template.description}</p>
                    {(template.fields || []).length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {(template.fields || []).map((f, i: number) => (
                          <span key={i} className="text-xs bg-brand-600/10 text-brand-400 px-2 py-1 rounded">
                            {f.name}
                            {f.model_override && (
                              <span className="ml-1 text-zinc-500" title={`模型: ${f.model_override}`}>[{f.model_override}]</span>
                            )}
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
