// frontend/components/project-auto-split-modal.tsx
// 功能: 项目级自动拆分内容主弹窗，负责加载/保存草稿、执行拆分、校验并应用到项目树
// 主要组件: ProjectAutoSplitModal
// 数据结构: ProjectStructureDraft / ProjectStructureDraftPayload / ProjectStructureChunk

"use client";

import { useEffect, useMemo, useState } from "react";
import {
  blockAPI,
  modelsAPI,
  projectStructureDraftAPI,
  settingsAPI,
  type ContentBlock,
  type FieldTemplate,
  type ModelInfo,
  type ProjectStructureDraft,
  type ProjectStructureDraftPayload,
  type TemplateNode,
} from "@/lib/api";
import { ProjectSplitChunkList } from "./project-split-chunk-list";
import { ProjectStructureDraftEditor } from "./project-structure-draft-editor";

interface ProjectAutoSplitModalProps {
  open: boolean;
  projectId: string | null;
  onClose: () => void;
  onApplied?: () => void;
}

function emptyPayload(): ProjectStructureDraftPayload {
  return {
    chunks: [],
    plans: [],
    shared_root_nodes: [],
    aggregate_root_nodes: [],
    ui_state: {},
  };
}

function normalizeDraft(draft: ProjectStructureDraft): ProjectStructureDraft {
  return {
    ...draft,
    draft_payload: draft.draft_payload || emptyPayload(),
  };
}

export function ProjectAutoSplitModal({
  open,
  projectId,
  onClose,
  onApplied,
}: ProjectAutoSplitModalProps) {
  const [draft, setDraft] = useState<ProjectStructureDraft | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [fieldTemplates, setFieldTemplates] = useState<FieldTemplate[]>([]);
  const [projectBlocks, setProjectBlocks] = useState<ContentBlock[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [runningSplit, setRunningSplit] = useState(false);
  const [validating, setValidating] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewSummary, setPreviewSummary] = useState<Record<string, number> | null>(null);
  const [previewRootNodes, setPreviewRootNodes] = useState<TemplateNode[]>([]);

  const canOperate = !!draft && !!projectId;
  const validationErrors = draft?.validation_errors || [];
  const chunkCount = draft?.draft_payload?.chunks?.length || 0;
  const canApply =
    !!canOperate &&
    (draft?.status === "validated" || draft?.status === "applied") &&
    validationErrors.length === 0 &&
    chunkCount > 0;

  const loadDraft = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [draftData, modelsResp, blockTree, templates] = await Promise.all([
        projectStructureDraftAPI.getAutoSplitDraft(projectId),
        modelsAPI.list().catch(() => ({ models: [] as ModelInfo[], current_default: { main: "", mini: "" }, env_provider: "" })),
        blockAPI.getProjectBlocks(projectId).catch(() => ({ project_id: projectId, blocks: [], total_count: 0 })),
        settingsAPI.listFieldTemplates().catch(() => [] as FieldTemplate[]),
      ]);
      const flattenBlocks = (blocks: ContentBlock[]): ContentBlock[] =>
        blocks.flatMap((block) => [block, ...flattenBlocks(block.children || [])]);
      setDraft(normalizeDraft(draftData));
      setAvailableModels(modelsResp.models || []);
      setFieldTemplates(templates || []);
      setProjectBlocks(flattenBlocks(blockTree.blocks || []));
      setPreviewSummary(null);
      setPreviewRootNodes([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载自动拆分草稿失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open || !projectId) return;
    loadDraft().catch(console.error);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !applying) onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, applying, onClose]);

  const patchDraft = (patch: Partial<ProjectStructureDraft>) => {
    if (!draft) return;
    setPreviewSummary(null);
    setPreviewRootNodes([]);
    setDraft({
      ...draft,
      status: "draft",
      validation_errors: [],
      last_validated_at: null,
      ...patch,
      draft_payload: patch.draft_payload || draft.draft_payload,
    });
  };

  const saveDraft = async (): Promise<ProjectStructureDraft | null> => {
    if (!projectId || !draft) return null;
    setSaving(true);
    setError(null);
    try {
      const saved = await projectStructureDraftAPI.updateAutoSplitDraft(projectId, {
        name: draft.name,
        source_text: draft.source_text,
        split_config: draft.split_config,
        draft_payload: draft.draft_payload,
      });
      const normalized = normalizeDraft(saved);
      setDraft(normalized);
      setPreviewSummary(null);
      setPreviewRootNodes([]);
      return normalized;
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存草稿失败");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const handleSplit = async () => {
    if (!projectId || !draft) return;
    setRunningSplit(true);
    setError(null);
    try {
      const resp = await projectStructureDraftAPI.splitAutoSplitDraft(projectId, {
        source_text: draft.source_text,
        split_config: draft.split_config,
      });
      setDraft(normalizeDraft(resp.draft));
      setPreviewSummary(null);
      setPreviewRootNodes([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "自动拆分失败");
    } finally {
      setRunningSplit(false);
    }
  };

  const handleValidate = async () => {
    if (!projectId || !draft) return;
    const saved = await saveDraft();
    if (!saved) return;
    setValidating(true);
    setError(null);
    try {
      const resp = await projectStructureDraftAPI.validateAutoSplitDraft(projectId);
      setDraft(normalizeDraft(resp.draft));
      setPreviewSummary(resp.summary);
      setPreviewRootNodes(resp.preview_root_nodes || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "校验失败");
    } finally {
      setValidating(false);
    }
  };

  const handleApply = async () => {
    if (!projectId || !draft || !canApply) return;
    setApplying(true);
    setError(null);
    try {
      const resp = await projectStructureDraftAPI.applyAutoSplitDraft(projectId);
      setDraft(normalizeDraft(resp.draft));
      setPreviewSummary(resp.summary);
      onApplied?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "应用失败");
    } finally {
      setApplying(false);
    }
  };

  const summaryLines = useMemo(() => {
    if (!previewSummary) return [];
    return [
      `chunk 数: ${previewSummary.chunk_count ?? 0}`,
      `方案数: ${previewSummary.plan_count ?? 0}`,
      `共享节点数: ${previewSummary.shared_node_count ?? 0}`,
      `聚合节点数: ${previewSummary.aggregate_node_count ?? 0}`,
      `编译节点数: ${previewSummary.compiled_node_count ?? 0}`,
    ];
  }, [previewSummary]);

  const previewLines = useMemo(() => {
    const lines: Array<{ key: string; depth: number; label: string }> = [];
    const walk = (nodes: TemplateNode[], depth: number) => {
      nodes.forEach((node) => {
        const childCount = (node.children || []).length;
        const typeLabel =
          node.block_type === "field"
            ? "内容块"
            : node.block_type === "group"
            ? "分组"
            : node.block_type === "phase"
            ? "阶段"
            : "节点";
        lines.push({
          key: `${node.template_node_id}-${depth}`,
          depth,
          label: `${typeLabel} / ${node.name}${childCount > 0 ? ` (${childCount})` : ""}`,
        });
        walk(node.children || [], depth + 1);
      });
    };
    walk(previewRootNodes, 0);
    return lines;
  }, [previewRootNodes]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => !applying && onClose()} />
      <div className="relative mx-4 flex h-[90vh] w-full max-w-7xl flex-col overflow-hidden rounded-xl border border-surface-3 bg-surface-1 shadow-2xl">
        <div className="flex items-start justify-between border-b border-surface-3 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-zinc-100">项目级自动拆分内容</h2>
            <p className="mt-1 text-sm text-zinc-500">
              这里做的是拆分 + 编排，不在弹窗里触发生成。应用后会一次性追加到项目树中。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-surface-2 px-3 py-1.5 text-sm text-zinc-300 hover:bg-surface-3"
          >
            关闭
          </button>
        </div>

        {loading || !draft ? (
          <div className="flex flex-1 items-center justify-center text-zinc-400">加载草稿中...</div>
        ) : (
          <>
            <div className="grid flex-1 grid-cols-[420px_1fr] gap-0 overflow-hidden">
              <div className="overflow-y-auto border-r border-surface-3 p-6 space-y-6">
                <section className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-zinc-300">草稿名称</label>
                    <span className="text-xs text-zinc-500">
                      已应用 {draft.apply_count} 次
                    </span>
                  </div>
                  <input
                    value={draft.name}
                    onChange={(e) => patchDraft({ name: e.target.value })}
                    className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                  />
                </section>

                <section className="space-y-3">
                  <label className="block text-sm font-medium text-zinc-300">原文全文</label>
                  <textarea
                    value={draft.source_text}
                    onChange={(e) => patchDraft({ source_text: e.target.value })}
                    rows={12}
                    placeholder="粘贴要拆分的完整内容"
                    className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                  />
                </section>

                <section className="space-y-3 rounded-xl border border-surface-3 bg-surface-0 p-4">
                  <div className="text-sm font-medium text-zinc-300">拆分配置</div>
                  <select
                    value={draft.split_config.mode}
                    onChange={(e) => patchDraft({
                      split_config: { ...draft.split_config, mode: e.target.value as ProjectStructureDraft["split_config"]["mode"] },
                    })}
                    className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                  >
                    <option value="count">拆成几份</option>
                    <option value="chars">每块多少字</option>
                    <option value="rule">拆分规则</option>
                  </select>

                  {draft.split_config.mode === "count" && (
                    <input
                      type="number"
                      min={1}
                      value={draft.split_config.target_count || 3}
                      onChange={(e) => patchDraft({
                        split_config: { ...draft.split_config, target_count: Number(e.target.value) || 1 },
                      })}
                      className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                    />
                  )}

                  {draft.split_config.mode === "chars" && (
                    <input
                      type="number"
                      min={1}
                      value={draft.split_config.max_chars_per_chunk || 1200}
                      onChange={(e) => patchDraft({
                        split_config: { ...draft.split_config, max_chars_per_chunk: Number(e.target.value) || 1 },
                      })}
                      className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                    />
                  )}

                  {draft.split_config.mode === "rule" && (
                    <textarea
                      value={draft.split_config.rule_prompt || ""}
                      onChange={(e) => patchDraft({
                        split_config: { ...draft.split_config, rule_prompt: e.target.value },
                      })}
                      rows={5}
                      placeholder="说明希望如何按语义拆分"
                      className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                    />
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="mb-1 block text-xs text-zinc-500">重叠字数</label>
                      <input
                        type="number"
                        min={0}
                        value={draft.split_config.overlap_chars || 0}
                        onChange={(e) => patchDraft({
                          split_config: { ...draft.split_config, overlap_chars: Number(e.target.value) || 0 },
                        })}
                        className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs text-zinc-500">标题前缀</label>
                      <input
                        value={draft.split_config.title_prefix || ""}
                        onChange={(e) => patchDraft({
                          split_config: { ...draft.split_config, title_prefix: e.target.value },
                        })}
                        className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                      />
                    </div>
                  </div>
                </section>

                <ProjectSplitChunkList
                  payload={draft.draft_payload}
                  onChange={(draft_payload) => patchDraft({ draft_payload })}
                />
              </div>

              <div className="overflow-y-auto p-6">
                <ProjectStructureDraftEditor
                  payload={draft.draft_payload}
                  availableModels={availableModels}
                  fieldTemplates={fieldTemplates}
                  projectBlocks={projectBlocks}
                  onChange={(draftPayload) => patchDraft({ draft_payload: draftPayload })}
                />
              </div>
            </div>

            <div className="border-t border-surface-3 px-6 py-4 space-y-3">
              {error && (
                <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                  {error}
                </div>
              )}

              {validationErrors.length > 0 && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
                  <div className="text-sm font-medium text-amber-300">校验错误</div>
                  <ul className="mt-2 space-y-1 text-sm text-amber-200">
                    {validationErrors.map((item) => (
                      <li key={item}>- {item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {previewLines.length > 0 && (
                <div className="rounded-lg border border-surface-3 bg-surface-0 px-4 py-3">
                  <div className="text-sm font-medium text-zinc-200">应用前结构预览</div>
                  <div className="mt-2 max-h-48 overflow-y-auto space-y-1 text-xs text-zinc-400">
                    {previewLines.map((line) => (
                      <div
                        key={line.key}
                        className="rounded bg-surface-1 px-2 py-1"
                        style={{ marginLeft: `${line.depth * 16}px` }}
                      >
                        {line.label}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(summaryLines.length > 0 || canOperate) && (
                <div className="flex items-center justify-between gap-4">
                  <div className="text-xs text-zinc-500">
                    {summaryLines.length > 0
                      ? summaryLines.join(" | ")
                      : draft?.status === "draft"
                      ? `当前已有 ${chunkCount} 个 chunk，修改后需先重新校验`
                      : `当前已有 ${chunkCount} 个 chunk`}
                  </div>

                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => saveDraft().catch(console.error)}
                      disabled={!canOperate || saving || runningSplit || validating || applying}
                      className="rounded-lg bg-surface-3 px-4 py-2 text-sm text-zinc-200 hover:bg-surface-4 disabled:opacity-50"
                    >
                      {saving ? "保存中..." : "保存草稿"}
                    </button>
                    <button
                      type="button"
                      onClick={handleSplit}
                      disabled={!canOperate || runningSplit || validating || applying}
                      className="rounded-lg bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:opacity-50"
                    >
                      {runningSplit ? "拆分中..." : "执行拆分"}
                    </button>
                    <button
                      type="button"
                      onClick={handleValidate}
                      disabled={!canOperate || saving || runningSplit || validating || applying}
                      className="rounded-lg bg-surface-3 px-4 py-2 text-sm text-zinc-200 hover:bg-surface-4 disabled:opacity-50"
                    >
                      {validating ? "校验中..." : "校验"}
                    </button>
                    <button
                      type="button"
                      onClick={handleApply}
                      disabled={!canApply || saving || runningSplit || validating || applying}
                      className="rounded-lg bg-emerald-600 px-4 py-2 text-sm text-white hover:bg-emerald-700 disabled:opacity-50"
                    >
                      {applying ? "应用中..." : "应用到项目"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
