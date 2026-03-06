// frontend/components/project-template-import-bar.tsx
// 功能: 自动拆分草稿中的模板导入条，统一承载从 FieldTemplate 导入 root_nodes 的交互
// 主要组件: ProjectTemplateImportBar
// 数据结构: FieldTemplate[]

"use client";

import { useState } from "react";
import type { FieldTemplate } from "@/lib/api";

interface ProjectTemplateImportBarProps {
  title: string;
  templates: FieldTemplate[];
  onImport: (template: FieldTemplate) => void;
}

export function ProjectTemplateImportBar({
  title,
  templates,
  onImport,
}: ProjectTemplateImportBarProps) {
  const [selectedTemplateId, setSelectedTemplateId] = useState("");

  if (!templates.length) {
    return (
      <div className="rounded-lg border border-dashed border-surface-3 px-4 py-3 text-xs text-zinc-500">
        {title}：当前还没有可复用的内容块模板，可先去设置页维护 `FieldTemplate`。
      </div>
    );
  }

  const selectedTemplate = templates.find((template) => template.id === selectedTemplateId);

  return (
    <div className="flex items-center gap-3 rounded-xl border border-surface-3 bg-surface-0 px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium text-zinc-300">{title}</div>
        <div className="mt-1 text-xs text-zinc-500">
          直接复用后台内容块模板的 `root_nodes`，导入时会重建节点 ID，避免污染草稿里的依赖关系。
        </div>
      </div>
      <select
        value={selectedTemplateId}
        onChange={(e) => setSelectedTemplateId(e.target.value)}
        className="min-w-[220px] rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
      >
        <option value="">选择内容块模板</option>
        {templates.map((template) => (
          <option key={template.id} value={template.id}>
            {template.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={!selectedTemplate}
        onClick={() => {
          if (!selectedTemplate) return;
          onImport(selectedTemplate);
        }}
        className="rounded-lg bg-brand-600 px-3 py-2 text-sm text-white hover:bg-brand-700 disabled:opacity-50"
      >
        导入模板结构
      </button>
    </div>
  );
}
