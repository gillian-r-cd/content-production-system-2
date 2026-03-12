// frontend/components/project-structure-draft-editor.tsx
// 功能: 编辑项目级自动拆分草稿中的编排方案、开头内容和结尾内容
// 主要组件: ProjectStructureDraftEditor
// 数据结构: ProjectStructureDraftPayload / ProjectStructurePlan / TemplateNode / DraftDependencyOption

"use client";

import type {
  ContentBlock,
  DraftDependencyOption,
  FieldTemplate,
  ModelInfo,
  ProjectStructureDraftPayload,
  ProjectStructurePlan,
} from "@/lib/api";
import { useUiIsJa } from "@/lib/ui-locale";
import { flattenContentNodes, importTemplateNodes } from "@/lib/project-structure-draft-utils";
import { ProjectPlanSelector } from "./project-plan-selector";
import { ProjectTemplateImportBar } from "./project-template-import-bar";
import { TemplateTreeEditor } from "./settings/template-tree-editor";

interface ProjectStructureDraftEditorProps {
  payload: ProjectStructureDraftPayload;
  projectLocale?: string | null;
  availableModels: ModelInfo[];
  fieldTemplates: FieldTemplate[];
  projectBlocks: ContentBlock[];
  onChange: (payload: ProjectStructureDraftPayload) => void;
}

function clonePayload(payload: ProjectStructureDraftPayload): ProjectStructureDraftPayload {
  return JSON.parse(JSON.stringify(payload));
}

function createPlan(isJa: boolean): ProjectStructurePlan {
  return {
    plan_id: crypto.randomUUID(),
    name: isJa ? "新しい編成プラン" : "新编排方案",
    target_chunk_ids: [],
    root_nodes: [],
  };
}

export function ProjectStructureDraftEditor({
  payload,
  projectLocale,
  availableModels,
  fieldTemplates,
  projectBlocks,
  onChange,
}: ProjectStructureDraftEditorProps) {
  const isJa = useUiIsJa(projectLocale);
  const patchPayload = (patch: Partial<ProjectStructureDraftPayload>) => {
    onChange({ ...clonePayload(payload), ...patch });
  };

  const patchPlan = (planId: string, patch: Partial<ProjectStructurePlan>) => {
    patchPayload({
      plans: payload.plans.map((plan) => (
        plan.plan_id === planId ? { ...plan, ...patch } : plan
      )),
    });
  };

  const removePlan = (planId: string) => {
    patchPayload({
      plans: payload.plans.filter((plan) => plan.plan_id !== planId),
    });
  };

  const addPlan = () => {
    patchPayload({
      plans: [...payload.plans, createPlan(isJa)],
    });
  };

  const sharedNodeOptions: DraftDependencyOption[] = flattenContentNodes(payload.shared_root_nodes).map((node) => ({
    id: `shared:${node.template_node_id}`,
    label: `${isJa ? "冒頭内容" : "开头内容"} / ${node.name || node.template_node_id.slice(0, 8)}`,
    ref: { ref_type: "shared_node", node_id: node.template_node_id },
  }));

  const projectBlockOptions: DraftDependencyOption[] = projectBlocks
    .filter((block) => block.block_type === "field")
    .map((block) => ({
      id: `project:${block.id}`,
      label: `${isJa ? "プロジェクト" : "项目"} / ${block.name}`,
      ref: { ref_type: "project_block", block_id: block.id },
    }));

  const chunkSourceOptions: DraftDependencyOption[] = payload.chunks.map((chunk) => ({
    id: `chunk-source:${chunk.chunk_id}`,
    label: `${isJa ? "chunk ソース" : "chunk 源"} / ${chunk.title}`,
    ref: { ref_type: "chunk_source", chunk_id: chunk.chunk_id },
  }));

  const buildPlanNodeOptionsForAggregate = (): DraftDependencyOption[] => {
    const options: DraftDependencyOption[] = [];
    for (const plan of payload.plans) {
      const nodes = flattenContentNodes(plan.root_nodes);
      for (const chunkId of plan.target_chunk_ids) {
        const chunk = payload.chunks.find((item) => item.chunk_id === chunkId);
        for (const node of nodes) {
          options.push({
            id: `plan-node:${plan.plan_id}:${chunkId}:${node.template_node_id}`,
            label: `${chunk?.title || chunkId} / ${plan.name} / ${node.name || node.template_node_id.slice(0, 8)}`,
            ref: {
              ref_type: "chunk_plan_node",
              chunk_id: chunkId,
              node_id: node.template_node_id,
            },
          });
        }
      }
    }
    return options;
  };

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-surface-3 bg-surface-1 p-4">
        <ProjectTemplateImportBar
          title={isJa ? "冒頭内容テンプレート" : "开头内容模板"}
          projectLocale={projectLocale}
          templates={fieldTemplates}
          onImport={(template) => patchPayload({
            shared_root_nodes: importTemplateNodes(payload.shared_root_nodes || [], template),
          })}
        />
        <TemplateTreeEditor
          nodes={payload.shared_root_nodes || []}
          onChange={(nodes) => patchPayload({ shared_root_nodes: nodes })}
          availableModels={availableModels}
          topLevelLabel={isJa ? "冒頭内容" : "开头内容"}
          emptyText={isJa ? "冒頭内容はまだありません。ここで直接内容ブロックを追加するか、グループで整理できます。" : "还没有开头内容。这里可以直接添加开头内容块，也可以按分组组织。"}
          topLevelCreateTypes={["field", "group"]}
          externalDependencyOptions={projectBlockOptions}
        />
      </section>

      <ProjectPlanSelector
        plans={payload.plans}
        chunks={payload.chunks}
        projectLocale={projectLocale}
        availableModels={availableModels}
        fieldTemplates={fieldTemplates}
        sharedNodeOptions={sharedNodeOptions}
        projectBlockOptions={projectBlockOptions}
        onAddPlan={addPlan}
        onPatchPlan={patchPlan}
        onRemovePlan={removePlan}
        onImportTemplate={(planId, template) => {
          const targetPlan = payload.plans.find((plan) => plan.plan_id === planId);
          patchPlan(planId, {
            root_nodes: importTemplateNodes(targetPlan?.root_nodes || [], template),
          });
        }}
      />

      <section className="rounded-xl border border-surface-3 bg-surface-1 p-4">
        <ProjectTemplateImportBar
          title={isJa ? "末尾内容テンプレート" : "结尾内容模板"}
          projectLocale={projectLocale}
          templates={fieldTemplates}
          onImport={(template) => patchPayload({
            aggregate_root_nodes: importTemplateNodes(payload.aggregate_root_nodes || [], template),
          })}
        />
        <TemplateTreeEditor
          nodes={payload.aggregate_root_nodes || []}
          onChange={(nodes) => patchPayload({ aggregate_root_nodes: nodes })}
          availableModels={availableModels}
          topLevelLabel={isJa ? "末尾内容" : "结尾内容"}
          emptyText={isJa ? "末尾内容はまだありません。最終集約用の内容ブロックを直接追加するか、グループで整理できます。" : "还没有结尾内容。这里可以直接添加最终汇总内容块，也可以按分组组织。"}
          topLevelCreateTypes={["field", "group"]}
          externalDependencyOptions={[
            ...chunkSourceOptions,
            ...buildPlanNodeOptionsForAggregate(),
            ...sharedNodeOptions,
            ...projectBlockOptions,
          ]}
        />
      </section>
    </div>
  );
}
