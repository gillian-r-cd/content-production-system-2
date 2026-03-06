// frontend/components/settings/template-tree-editor.tsx
// 功能: 模板树编辑器，统一编辑 FieldTemplate.root_nodes 与 PhaseTemplate.root_nodes
// 主要组件: TemplateTreeEditor
// 数据结构: TemplateNode（递归树节点，含 depends_on_template_node_ids / children）

"use client";

import type { ModelInfo, TemplateNode } from "@/lib/api";
import { FormField, TagInput } from "./shared";

function createTemplateNode(blockType: TemplateNode["block_type"] = "field"): TemplateNode {
  return {
    template_node_id: crypto.randomUUID(),
    name: "",
    block_type: blockType,
    ai_prompt: "",
    content: "",
    pre_questions: [],
    depends_on_template_node_ids: [],
    constraints: {},
    special_handler: null,
    need_review: true,
    auto_generate: false,
    is_collapsed: false,
    model_override: null,
    children: [],
  };
}

function cloneNodes(nodes: TemplateNode[]): TemplateNode[] {
  return JSON.parse(JSON.stringify(nodes));
}

function flattenNodes(nodes: TemplateNode[]): TemplateNode[] {
  return nodes.flatMap((node) => [node, ...flattenNodes(node.children || [])]);
}

function updateNodeById(
  nodes: TemplateNode[],
  nodeId: string,
  updater: (node: TemplateNode) => TemplateNode,
): TemplateNode[] {
  return nodes.map((node) => {
    if (node.template_node_id === nodeId) {
      return updater(node);
    }
    if (node.children?.length) {
      return { ...node, children: updateNodeById(node.children, nodeId, updater) };
    }
    return node;
  });
}

function removeNodeById(nodes: TemplateNode[], nodeId: string): TemplateNode[] {
  return nodes
    .filter((node) => node.template_node_id !== nodeId)
    .map((node) => ({
      ...node,
      children: removeNodeById(node.children || [], nodeId),
      depends_on_template_node_ids: (node.depends_on_template_node_ids || []).filter((id) => id !== nodeId),
    }));
}

function addChildNode(nodes: TemplateNode[], parentId: string, child: TemplateNode): TemplateNode[] {
  return updateNodeById(nodes, parentId, (node) => ({
    ...node,
    children: [...(node.children || []), child],
  }));
}

function moveNode(nodes: TemplateNode[], nodeId: string, direction: "up" | "down"): TemplateNode[] {
  const next = cloneNodes(nodes);

  function moveInList(list: TemplateNode[]): boolean {
    const index = list.findIndex((node) => node.template_node_id === nodeId);
    if (index >= 0) {
      const target = direction === "up" ? index - 1 : index + 1;
      if (target < 0 || target >= list.length) return true;
      [list[index], list[target]] = [list[target], list[index]];
      return true;
    }
    return list.some((node) => moveInList(node.children || []));
  }

  moveInList(next);
  return next;
}

interface TemplateTreeEditorProps {
  nodes: TemplateNode[];
  onChange: (nodes: TemplateNode[]) => void;
  availableModels: ModelInfo[];
  topLevelLabel?: string;
  emptyText?: string;
}

interface NodeEditorProps {
  node: TemplateNode;
  level: number;
  nodes: TemplateNode[];
  onChange: (nodes: TemplateNode[]) => void;
  availableModels: ModelInfo[];
}

/** 类型 → 名称 placeholder 映射 */
const TYPE_PLACEHOLDER: Record<string, string> = {
  phase: "阶段名称",
  group: "分组名称",
  field: "内容块名称",
};

function NodeEditor({ node, level, nodes, onChange, availableModels }: NodeEditorProps) {
  const blockType = node.block_type || "field";
  const isContentBlock = blockType === "field";
  const hasChildren = (node.children || []).length > 0;
  const isCollapsed = node.is_collapsed === true;

  const patchNode = (patch: Partial<TemplateNode>) => {
    onChange(updateNodeById(nodes, node.template_node_id, (current) => ({ ...current, ...patch })));
  };

  const toggleCollapse = () => patchNode({ is_collapsed: !isCollapsed });

  // 只有内容块才需要依赖选项
  const dependencyOptions = isContentBlock
    ? flattenNodes(nodes).filter((item) => item.template_node_id !== node.template_node_id && item.block_type === "field")
    : [];

  return (
    <div className="space-y-3 rounded-xl border border-surface-3 bg-surface-1 p-4" style={{ marginLeft: level * 16 }}>
      {/* 标题栏：始终可见 */}
      <div className="flex items-center gap-2">
        <button
          onClick={toggleCollapse}
          className="flex-shrink-0 rounded p-0.5 text-zinc-400 hover:text-zinc-200"
          title={isCollapsed ? "展开" : "折叠"}
        >
          {isCollapsed ? "▶" : "▼"}
        </button>
        <input
          value={node.name || ""}
          onChange={(e) => patchNode({ name: e.target.value })}
          placeholder={TYPE_PLACEHOLDER[blockType] || "名称"}
          className="flex-1 rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
        />
        <select
          value={blockType}
          onChange={(e) => patchNode({ block_type: e.target.value as TemplateNode["block_type"] })}
          className="rounded-lg border border-surface-3 bg-surface-2 px-2 py-2 text-xs text-zinc-300"
        >
          <option value="phase">阶段</option>
          <option value="group">分组</option>
          <option value="field">内容块</option>
        </select>
        <button
          onClick={() => onChange(moveNode(nodes, node.template_node_id, "up"))}
          className="rounded bg-surface-3 px-2 py-1 text-xs text-zinc-300"
        >
          ↑
        </button>
        <button
          onClick={() => onChange(moveNode(nodes, node.template_node_id, "down"))}
          className="rounded bg-surface-3 px-2 py-1 text-xs text-zinc-300"
        >
          ↓
        </button>
        <button
          onClick={() => onChange(removeNodeById(nodes, node.template_node_id))}
          className="rounded bg-red-600/20 px-2 py-1 text-xs text-red-400"
        >
          删除
        </button>
        {isCollapsed && hasChildren && (
          <span className="text-xs text-zinc-500">{node.children?.length} 个子项</span>
        )}
      </div>

      {/* 以下内容：折叠时隐藏 */}
      {!isCollapsed && (
        <>
          {/* ====== 内容块专属配置 ====== */}
          {isContentBlock && (
            <>
              <FormField label="模型" hint="此内容块使用的 AI 模型，留空则使用项目默认模型">
                <select
                  value={node.model_override || ""}
                  onChange={(e) => patchNode({ model_override: e.target.value || null })}
                  className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                >
                  <option value="">默认</option>
                  {availableModels.map((model) => (
                    <option key={model.id} value={model.id}>{model.name}</option>
                  ))}
                </select>
              </FormField>

              <div className="grid grid-cols-2 gap-4">
                <label className="flex items-center gap-2 text-xs text-zinc-400">
                  <input
                    type="checkbox"
                    checked={node.need_review !== false}
                    onChange={(e) => patchNode({ need_review: e.target.checked })}
                  />
                  需要人工确认
                  <span className="text-zinc-600">— AI 生成后仍需用户确认才算完成</span>
                </label>
                <label className="flex items-center gap-2 text-xs text-zinc-400">
                  <input
                    type="checkbox"
                    checked={node.auto_generate === true}
                    onChange={(e) => patchNode({ auto_generate: e.target.checked })}
                  />
                  自动生成
                  <span className="text-zinc-600">— 依赖就绪时自动触发 AI 生成</span>
                </label>
              </div>

              <FormField label="生成前提问" hint="生成前需要用户回答的问题，答案会注入 AI 提示词">
                <TagInput
                  value={node.pre_questions || []}
                  onChange={(value) => patchNode({ pre_questions: value })}
                  placeholder="输入问题后回车"
                />
              </FormField>

              {dependencyOptions.length > 0 && (
                <FormField label="依赖" hint="生成此内容块前需要先完成的其他内容块">
                  <div className="flex flex-wrap gap-2">
                    {dependencyOptions.map((option) => {
                      const checked = (node.depends_on_template_node_ids || []).includes(option.template_node_id);
                      return (
                        <label key={option.template_node_id} className="flex items-center gap-1.5 text-xs text-zinc-300">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) => {
                              const next = new Set(node.depends_on_template_node_ids || []);
                              if (e.target.checked) next.add(option.template_node_id);
                              else next.delete(option.template_node_id);
                              patchNode({ depends_on_template_node_ids: [...next] });
                            }}
                          />
                          {option.name || option.template_node_id.slice(0, 8)}
                        </label>
                      );
                    })}
                  </div>
                </FormField>
              )}

              <FormField label="AI 提示词" hint="生成此内容块时给 AI 的指令，会与项目上下文一起发送">
                <textarea
                  value={node.ai_prompt || ""}
                  onChange={(e) => patchNode({ ai_prompt: e.target.value })}
                  rows={4}
                  className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                />
              </FormField>
              <FormField label="预置内容" hint="应用模板后预填到内容块的初始内容">
                <textarea
                  value={node.content || ""}
                  onChange={(e) => patchNode({ content: e.target.value })}
                  rows={4}
                  className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm text-zinc-200"
                />
              </FormField>
            </>
          )}

          {/* ====== 子项操作：所有类型都有 ====== */}
          <div className="flex items-center gap-2 border-t border-surface-3 pt-3">
            <button
              onClick={() => onChange(addChildNode(nodes, node.template_node_id, createTemplateNode("field")))}
              className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs text-white"
            >
              + 子内容块
            </button>
            <button
              onClick={() => onChange(addChildNode(nodes, node.template_node_id, createTemplateNode("group")))}
              className="rounded-lg bg-surface-3 px-3 py-1.5 text-xs text-zinc-300"
            >
              + 子分组
            </button>
            {hasChildren && <span className="text-xs text-zinc-500">{node.children?.length} 个子项</span>}
          </div>

          {node.children?.length ? (
            <div className="space-y-3">
              {node.children.map((child) => (
                <NodeEditor
                  key={child.template_node_id}
                  node={child}
                  level={level + 1}
                  nodes={nodes}
                  onChange={onChange}
                  availableModels={availableModels}
                />
              ))}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

export function TemplateTreeEditor({
  nodes,
  onChange,
  availableModels,
  topLevelLabel = "模板结构",
  emptyText = "还没有添加内容，先添加顶层阶段或分组。",
}: TemplateTreeEditorProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-zinc-300">{topLevelLabel}</h4>
        <div className="flex gap-2">
          <button
            onClick={() => onChange([...(nodes || []), createTemplateNode("phase")])}
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs text-white"
          >
            + 顶层阶段
          </button>
          <button
            onClick={() => onChange([...(nodes || []), createTemplateNode("group")])}
            className="rounded-lg bg-surface-3 px-3 py-1.5 text-xs text-zinc-300"
          >
            + 顶层分组
          </button>
        </div>
      </div>

      {!nodes.length ? (
        <div className="rounded-lg border border-dashed border-surface-3 py-8 text-center text-zinc-500">
          {emptyText}
        </div>
      ) : (
        <div className="space-y-3">
          {nodes.map((node) => (
            <NodeEditor
              key={node.template_node_id}
              node={node}
              level={0}
              nodes={nodes}
              onChange={onChange}
              availableModels={availableModels}
            />
          ))}
        </div>
      )}
    </div>
  );
}
