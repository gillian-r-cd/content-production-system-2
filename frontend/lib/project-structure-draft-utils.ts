// frontend/lib/project-structure-draft-utils.ts
// 功能: 项目级自动拆分草稿编辑工具，封装模板导入和节点遍历等纯函数逻辑
// 主要函数: flattenNodes / flattenContentNodes / cloneTemplateNodesWithNewIds / importTemplateNodes
// 数据结构: TemplateNode[] / FieldTemplate

import type { FieldTemplate, TemplateNode } from "./api";

type CreateId = () => string;

function defaultCreateId(): string {
  return crypto.randomUUID();
}

export function flattenNodes(nodes: TemplateNode[] = []): TemplateNode[] {
  return nodes.flatMap((node) => [node, ...flattenNodes(node.children || [])]);
}

export function flattenContentNodes(nodes: TemplateNode[] = []): TemplateNode[] {
  return flattenNodes(nodes).filter((node) => node.block_type === "field" || node.block_type === "proposal");
}

export function cloneTemplateNodesWithNewIds(
  nodes: TemplateNode[] = [],
  createId: CreateId = defaultCreateId,
): TemplateNode[] {
  const cloned = JSON.parse(JSON.stringify(nodes)) as TemplateNode[];
  const idMap = new Map<string, string>();

  const assignIds = (items: TemplateNode[]) => {
    for (const node of items) {
      idMap.set(node.template_node_id, createId());
      assignIds(node.children || []);
    }
  };

  const rewriteIds = (items: TemplateNode[]) => {
    for (const node of items) {
      node.template_node_id = idMap.get(node.template_node_id) || createId();
      node.depends_on_template_node_ids = (node.depends_on_template_node_ids || [])
        .map((depId) => idMap.get(depId) || depId);
      rewriteIds(node.children || []);
    }
  };

  assignIds(cloned);
  rewriteIds(cloned);
  return cloned;
}

export function importTemplateNodes(
  currentNodes: TemplateNode[] = [],
  template: FieldTemplate | undefined,
  createId: CreateId = defaultCreateId,
): TemplateNode[] {
  if (!template?.root_nodes?.length) return currentNodes;
  return [...currentNodes, ...cloneTemplateNodesWithNewIds(template.root_nodes, createId)];
}
