// frontend/components/project-draft-dependency-selector.tsx
// 功能: 草稿态依赖选择器，统一渲染自动拆分弹窗中的外部依赖勾选区
// 主要组件: ProjectDraftDependencySelector
// 数据结构: DraftDependencyOption[] / DraftDependencyRef[]

"use client";

import type { DraftDependencyOption, DraftDependencyRef } from "@/lib/api";
import { FormField, useSettingsUiIsJa } from "./settings/shared";

interface ProjectDraftDependencySelectorProps {
  value: DraftDependencyRef[];
  options: DraftDependencyOption[];
  label?: string;
  hint?: string;
  onChange: (next: DraftDependencyRef[]) => void;
}

function refKey(ref: DraftDependencyRef): string {
  return JSON.stringify(ref);
}

export function ProjectDraftDependencySelector({
  value,
  options,
  label,
  hint,
  onChange,
}: ProjectDraftDependencySelectorProps) {
  const isJa = useSettingsUiIsJa();
  const resolvedLabel = label || (isJa ? "外部依存" : "外部依赖");
  const resolvedHint = hint || (isJa ? "現在のプラン外にある草稿ノードや既存のプロジェクト内容ブロックへの依存を選択します" : "依赖当前方案外的草稿节点或项目已有内容块");

  if (!options.length) return null;

  const selectedKeys = new Set((value || []).map(refKey));

  return (
    <FormField label={resolvedLabel} hint={resolvedHint}>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const key = refKey(option.ref);
          const checked = selectedKeys.has(key);
          return (
            <label key={option.id} className="flex items-center gap-1.5 text-xs text-zinc-300">
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => {
                  const next = [...(value || [])];
                  const index = next.findIndex((ref) => refKey(ref) === key);
                  if (e.target.checked && index < 0) {
                    next.push(option.ref);
                  }
                  if (!e.target.checked && index >= 0) {
                    next.splice(index, 1);
                  }
                  onChange(next);
                }}
              />
              {option.label}
            </label>
          );
        })}
      </div>
    </FormField>
  );
}
