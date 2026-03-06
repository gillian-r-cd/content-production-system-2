// frontend/components/settings/phase-templates-section.tsx
// 功能: 流程模板管理，统一编辑 PhaseTemplate.root_nodes 树结构
// 主要组件: PhaseTemplatesSection
// 数据结构: PhaseTemplateEditForm（root_nodes 为单一编辑真相）

"use client";

import { useEffect, useState } from "react";
import { phaseTemplateAPI, modelsAPI } from "@/lib/api";
import type { PhaseTemplate, ModelInfo, TemplateNode } from "@/lib/api";
import { FormField } from "./shared";
import { TemplateTreeEditor } from "./template-tree-editor";

function flattenTemplateNodes(nodes: TemplateNode[] = []): TemplateNode[] {
  return nodes.flatMap((node) => [node, ...flattenTemplateNodes(node.children || [])]);
}

interface PhaseTemplateEditForm {
  name: string;
  description: string;
  root_nodes: TemplateNode[];
}

export function PhaseTemplatesSection({ templates, onRefresh }: { templates: PhaseTemplate[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<PhaseTemplateEditForm>({ name: "", description: "", root_nodes: [] });
  const [isCreating, setIsCreating] = useState(false);
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);

  // 加载可用模型列表
  useEffect(() => {
    modelsAPI.list().then(resp => {
      setAvailableModels(resp.models || []);
    }).catch(() => { /* 模型列表加载失败不阻塞页面 */ });
  }, []);

  const handleCreate = () => {
    setIsCreating(true);
    setEditForm({
      name: "",
      description: "",
      root_nodes: [],
    });
  };

  const handleEdit = (template: PhaseTemplate) => {
    setEditingId(template.id);
    setEditForm({
      name: template.name,
      description: template.description,
      root_nodes: JSON.parse(JSON.stringify(template.root_nodes || [])),
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

        <TemplateTreeEditor
          nodes={editForm.root_nodes}
          onChange={(root_nodes) => setEditForm({ ...editForm, root_nodes })}
          availableModels={availableModels}
          topLevelLabel="流程模板结构"
          emptyText="还没有添加内容，先添加顶层阶段。"
        />

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
                  <span className="px-1.5 py-0.5 text-xs bg-brand-600/10 text-brand-400 rounded">v{template.schema_version}</span>
                </div>
                <p className="text-sm text-zinc-500 mt-1">{template.description}</p>
                {(() => {
                  const flatNodes = flattenTemplateNodes(template.root_nodes || []);
                  const containerCount = flatNodes.filter((node) => node.block_type === "phase" || node.block_type === "group").length;
                  const fieldCount = flatNodes.filter((node) => node.block_type === "field" || node.block_type === "proposal").length;
                  const contentCount = flatNodes.filter((node) => !!node.content).length;
                  return (
                    <div className="flex gap-3 mt-2 text-xs text-zinc-400">
                      <span>{containerCount || template.phases.length} 个阶段/分组</span>
                      <span>{fieldCount || template.phases.reduce((sum: number, p) => sum + (p.default_fields || []).length, 0)} 个内容块</span>
                      <span>{contentCount || template.phases.reduce((sum: number, p) =>
                        sum + (p.default_fields || []).filter((f) => f.content).length, 0
                      )} 个有预置内容</span>
                    </div>
                  );
                })()}
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
              {template.phases.map((phase, pIdx: number) => (
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
                      {phase.default_fields.map((f, fIdx: number) => (
                        <div key={fIdx} className="flex items-center gap-1.5 text-zinc-500">
                          <span>📄</span>
                          <span>{f.name}</span>
                          {f.ai_prompt && <span className="text-brand-400/60">✨</span>}
                          {f.content && <span className="text-emerald-400/60">📝</span>}
                          {f.auto_generate && <span className="text-blue-400/60" title="自动生成"><Sparkles className="w-3 h-3 inline" /></span>}
                          {f.model_override && <span className="text-amber-400/60" title={`模型: ${f.model_override}`}>[{String(f.model_override)}]</span>}
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
            <p className="text-xs mt-1">点击&quot;新建模板&quot;创建第一个</p>
          </div>
        )}
      </div>
    </div>
  );
}
