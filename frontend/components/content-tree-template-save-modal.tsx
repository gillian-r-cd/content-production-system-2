// frontend/components/content-tree-template-save-modal.tsx
// 功能: 为项目级和内容块级内容树提供统一的“保存为内容块模板”弹窗与提交逻辑
// 主要组件: ContentTreeTemplateSaveModal
// 数据结构: project/block 两种 scope，共享模板名称、描述、分类和保存结果提示

"use client";

import { useEffect, useMemo, useState } from "react";

import { blockAPI, projectAPI } from "@/lib/api";
import { useUiIsJa } from "@/lib/ui-locale";
import { sendNotification } from "@/lib/utils";

type TemplateSaveScope =
  | {
      type: "project";
      projectId: string;
      label: string;
    }
  | {
      type: "block";
      blockId: string;
      label: string;
    };

export function ContentTreeTemplateSaveModal({
  open,
  scope,
  projectLocale,
  onClose,
  onSaved,
}: {
  open: boolean;
  scope: TemplateSaveScope | null;
  projectLocale?: string | null;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const isJa = useUiIsJa(projectLocale);
  const [templateName, setTemplateName] = useState("");
  const [templateDescription, setTemplateDescription] = useState("");
  const [templateCategory, setTemplateCategory] = useState(isJa ? "汎用" : "通用");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savingTemplate, setSavingTemplate] = useState(false);

  const defaultTemplateName = useMemo(() => {
    if (!scope) return "";
    return isJa ? `${scope.label} テンプレート` : `${scope.label} 模板`;
  }, [isJa, scope]);

  useEffect(() => {
    if (!open || !scope) return;
    setTemplateName(defaultTemplateName);
    setTemplateDescription("");
    setTemplateCategory(isJa ? "汎用" : "通用");
    setSaveError(null);
  }, [defaultTemplateName, isJa, open, scope]);

  if (!open || !scope) return null;

  const handleSaveTemplate = async () => {
    if (!templateName.trim()) {
      setSaveError(isJa ? "テンプレート名は必須です" : "模板名称不能为空");
      return;
    }

    setSavingTemplate(true);
    setSaveError(null);
    try {
      const result =
        scope.type === "project"
          ? await projectAPI.saveAsFieldTemplate(scope.projectId, {
              name: templateName.trim(),
              description: templateDescription.trim(),
              category: templateCategory.trim() || (isJa ? "汎用" : "通用"),
            })
          : await blockAPI.saveAsFieldTemplate(scope.blockId, {
              name: templateName.trim(),
              description: templateDescription.trim(),
              category: templateCategory.trim() || (isJa ? "汎用" : "通用"),
            });
      const warningText = result.warnings.length > 0 ? (isJa ? `。追加で ${result.warnings.length} 件の注意があります` : `，另有 ${result.warnings.length} 条提示`) : "";
      sendNotification(isJa ? "テンプレートを保存しました" : "模板已保存", isJa ? `テンプレート「${result.template.name}」を作成しました${warningText}` : `已创建模板「${result.template.name}」${warningText}`);
      onClose();
      onSaved?.();
    } catch (error) {
      console.error("保存模板失败:", error);
      setSaveError(error instanceof Error ? error.message : (isJa ? "不明なエラー" : "未知错误"));
    } finally {
      setSavingTemplate(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-xl border border-surface-3 bg-surface-1 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-surface-3 px-5 py-4">
          <h3 className="text-base font-semibold text-zinc-100">{isJa ? "内容ブロックテンプレートとして保存" : "保存为内容块模板"}</h3>
          <p className="mt-1 text-xs text-zinc-500">{isJa ? `現在の範囲「${scope.label}」を再利用可能なテンプレートとして保存します。` : `将当前范围「${scope.label}」沉淀为可复用模板。`}</p>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-zinc-300">{isJa ? "テンプレート名" : "模板名称"}</label>
            <input
              value={templateName}
              onChange={(event) => setTemplateName(event.target.value)}
              className="w-full rounded-lg border border-surface-3 bg-surface-0 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-brand-500"
              placeholder={isJa ? "テンプレート名を入力してください" : "请输入模板名称"}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-zinc-300">{isJa ? "テンプレート説明" : "模板描述"}</label>
            <textarea
              value={templateDescription}
              onChange={(event) => setTemplateDescription(event.target.value)}
              className="min-h-24 w-full rounded-lg border border-surface-3 bg-surface-0 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-brand-500"
              placeholder={isJa ? "任意。テンプレート用途を説明します" : "可选，描述模板用途"}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-zinc-300">{isJa ? "テンプレート分類" : "模板分类"}</label>
            <input
              value={templateCategory}
              onChange={(event) => setTemplateCategory(event.target.value)}
              className="w-full rounded-lg border border-surface-3 bg-surface-0 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-brand-500"
              placeholder={isJa ? "汎用" : "通用"}
            />
          </div>

          <div className="rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-xs text-zinc-500">
            {isJa ? "保存時には構造、プロンプト、依存関係、初期内容を保持します。実行時状態はテンプレートへ書き込みません。" : "保存时会保留结构、提示词、依赖和预置内容，不会把运行态状态一并写入模板。"}
          </div>

          {saveError && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{saveError}</div>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-surface-3 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-surface-3 px-4 py-2 text-sm text-zinc-200 hover:bg-surface-4"
          >
            {isJa ? "キャンセル" : "取消"}
          </button>
          <button
            type="button"
            onClick={handleSaveTemplate}
            disabled={savingTemplate || !templateName.trim()}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {savingTemplate ? (isJa ? "保存中..." : "保存中...") : (isJa ? "テンプレートを保存" : "保存模板")}
          </button>
        </div>
      </div>
    </div>
  );
}
