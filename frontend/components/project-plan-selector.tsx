// frontend/components/project-plan-selector.tsx
// 功能: 编辑自动拆分草稿中的编排方案列表，每个方案独立承载 chunk 选择、模板导入与结构树
// 主要组件: ProjectPlanSelector
// 数据结构: ProjectStructurePlan[] / ProjectStructureChunk[] / TemplateNode[]

"use client";

import type {
  DraftDependencyOption,
  FieldTemplate,
  ModelInfo,
  ProjectStructureChunk,
  ProjectStructurePlan,
} from "@/lib/api";
import { ProjectTemplateImportBar } from "./project-template-import-bar";
import { TemplateTreeEditor } from "./settings/template-tree-editor";

interface ProjectPlanSelectorProps {
  plans: ProjectStructurePlan[];
  chunks: ProjectStructureChunk[];
  availableModels: ModelInfo[];
  fieldTemplates: FieldTemplate[];
  sharedNodeOptions: DraftDependencyOption[];
  projectBlockOptions: DraftDependencyOption[];
  onAddPlan: () => void;
  onPatchPlan: (planId: string, patch: Partial<ProjectStructurePlan>) => void;
  onRemovePlan: (planId: string) => void;
  onImportTemplate: (planId: string, template: FieldTemplate) => void;
}

export function ProjectPlanSelector({
  plans,
  chunks,
  availableModels,
  fieldTemplates,
  sharedNodeOptions,
  projectBlockOptions,
  onAddPlan,
  onPatchPlan,
  onRemovePlan,
  onImportTemplate,
}: ProjectPlanSelectorProps) {
  return (
    <section className="space-y-4 rounded-xl border border-surface-3 bg-surface-1 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-zinc-200">编排方案</h3>
          <p className="text-xs text-zinc-500 mt-1">
            配置视图按方案组织，最终应用时仍按 chunk 顺序展开。
          </p>
        </div>
        <button
          type="button"
          onClick={onAddPlan}
          className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs text-white hover:bg-brand-700"
        >
          + 新编排方案
        </button>
      </div>

      {!plans.length ? (
        <div className="rounded-lg border border-dashed border-surface-3 px-4 py-6 text-sm text-zinc-500">
          还没有编排方案。你可以先拆出 chunk，再新增一个方案并选择要作用到哪些 chunk。
        </div>
      ) : (
        <div className="space-y-4">
          {plans.map((plan) => (
            <div key={plan.plan_id} className="rounded-xl border border-surface-3 bg-surface-0 p-4 space-y-4">
              <div className="flex items-center gap-3">
                <input
                  value={plan.name}
                  onChange={(e) => onPatchPlan(plan.plan_id, { name: e.target.value })}
                  className="flex-1 rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                  placeholder="方案名称"
                />
                <button
                  type="button"
                  onClick={() => onRemovePlan(plan.plan_id)}
                  className="rounded bg-red-600/20 px-2 py-1 text-xs text-red-400"
                >
                  删除方案
                </button>
              </div>

              <div className="space-y-2">
                <div className="text-xs text-zinc-400">作用到哪些 chunk</div>
                <div className="flex flex-wrap gap-2">
                  {chunks.map((chunk) => {
                    const checked = plan.target_chunk_ids.includes(chunk.chunk_id);
                    return (
                      <label
                        key={chunk.chunk_id}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-surface-3 bg-surface-2 px-3 py-1.5 text-xs text-zinc-300"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            const next = new Set(plan.target_chunk_ids);
                            if (e.target.checked) next.add(chunk.chunk_id);
                            else next.delete(chunk.chunk_id);
                            onPatchPlan(plan.plan_id, { target_chunk_ids: [...next] });
                          }}
                        />
                        {chunk.title || chunk.chunk_id.slice(0, 8)}
                      </label>
                    );
                  })}
                  {!chunks.length && (
                    <span className="text-xs text-zinc-500">还没有 chunk，可先执行拆分。</span>
                  )}
                </div>
              </div>

              <ProjectTemplateImportBar
                title={`${plan.name || "当前方案"}模板`}
                templates={fieldTemplates}
                onImport={(template) => onImportTemplate(plan.plan_id, template)}
              />

              <TemplateTreeEditor
                nodes={plan.root_nodes || []}
                onChange={(nodes) => onPatchPlan(plan.plan_id, { root_nodes: nodes })}
                availableModels={availableModels}
                topLevelLabel="方案结构"
                emptyText="还没有结构，先添加顶层内容块或分组。"
                topLevelCreateTypes={["field", "group"]}
                externalDependencyOptions={[
                  {
                    id: `current-source:${plan.plan_id}`,
                    label: "当前 chunk 的源内容块",
                    ref: { ref_type: "chunk_source", chunk_id: "current" },
                  },
                  ...sharedNodeOptions,
                  ...projectBlockOptions,
                ]}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
