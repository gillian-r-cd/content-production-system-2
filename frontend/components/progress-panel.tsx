// frontend/components/progress-panel.tsx
// 功能: 左栏项目进度面板，树形架构视图
// 主要组件: ProgressPanel
// P0-1: 统一使用 ContentBlock，已移除 fields/ProjectField 依赖
// 已移除: Agent自主权设置（AutonomySettingsModal）— 不再由传统流程设置

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import type { Project, ContentBlock } from "@/lib/api";
import { blockAPI, runAutoTriggerChain } from "@/lib/api";
import BlockTree from "./block-tree";
// lucide-react icons removed: view toggle已移除

// 辅助函数：将树形结构扁平化为数组（用于依赖选择）
function flattenBlocks(blocks: ContentBlock[]): ContentBlock[] {
  const result: ContentBlock[] = [];
  const flatten = (blockList: ContentBlock[]) => {
    for (const block of blockList) {
      result.push(block);
      if (block.children && block.children.length > 0) {
        flatten(block.children);
      }
    }
  };
  flatten(blocks);
  return result;
}

// PHASE_SPECIAL_HANDLERS, FIXED_TOP_PHASES, DRAGGABLE_PHASES, FIXED_BOTTOM_PHASES
// 均从 @/lib/utils 导入（统一来源: backend/core/phase_config.py）

interface ProgressPanelProps {
  project: Project | null;
  blocksRefreshKey?: number;  // 外部触发 ContentBlocks 重新加载
  onPhaseClick?: (phase: string) => void;
  onPhaseReorder?: (newPhaseOrder: string[]) => Promise<void>;
  onBlockSelect?: (block: ContentBlock) => void;
  onBlocksChange?: (blocks: ContentBlock[]) => void;  // 当内容块加载/变化时通知父组件
  onProjectChange?: () => void;  // 项目数据变化时通知父组件刷新
}

export function ProgressPanel({
  project,
  blocksRefreshKey = 0,
  onPhaseClick,
  onPhaseReorder: _onPhaseReorder,
  onBlockSelect,
  onBlocksChange,
}: ProgressPanelProps) {
  // P0-1: 传统视图已移除，统一使用树形架构
  const [contentBlocks, setContentBlocks] = useState<ContentBlock[]>([]);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [isLoadingBlocks, setIsLoadingBlocks] = useState(false);
  const initialBlocksLoadDone = useRef(false);  // 标记初次加载是否完成
  const prevBlocksSignature = useRef("");  // 用于比较 blocks 是否实际变化
  
  
  useEffect(() => {
    // 切换项目时重置初次加载标记，确保新项目首次显示 spinner
    initialBlocksLoadDone.current = false;
    prevBlocksSignature.current = "";
  }, [project?.id]);
  
  // ===== 加载内容块 =====
  // P0-1: 统一使用 ContentBlock API，classic 和 tree 视图都需要
  useEffect(() => {
    if (project?.id) {
      loadContentBlocks();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id, blocksRefreshKey]);
  
  // 辅助函数：计算 blocks 签名，用于比较是否实际变化
  const computeBlocksSignature = useCallback((blocks: ContentBlock[]): string => {
    return flattenBlocks(blocks)
      .map(b => `${b.id}|${b.status}|${(b.content || "").length}|${b.name}|${b.ai_prompt ? 1 : 0}|${b.need_review ? 1 : 0}|${(b.depends_on || []).length}`)
      .join(",");
  }, []);
  
  // 辅助函数：仅在数据实际变化时调用 onBlocksChange
  const notifyBlocksChangeIfNeeded = useCallback((blocks: ContentBlock[]) => {
    const flat = flattenBlocks(blocks);
    const sig = computeBlocksSignature(blocks);
    if (sig !== prevBlocksSignature.current) {
      prevBlocksSignature.current = sig;
      onBlocksChange?.(flat);
    }
  }, [computeBlocksSignature, onBlocksChange]);
  
  const loadContentBlocks = async () => {
    if (!project?.id) return;
    
    // 只在首次加载时显示 spinner，后续静默刷新
    if (!initialBlocksLoadDone.current) {
      setIsLoadingBlocks(true);
    }
    try {
      // P0-1: 统一从 ContentBlock API 加载
      const data = await blockAPI.getProjectBlocks(project.id);
      if (data.blocks && data.blocks.length > 0) {
        setContentBlocks(data.blocks);
        notifyBlocksChangeIfNeeded(data.blocks);
      } else {
        setContentBlocks([]);
        notifyBlocksChangeIfNeeded([]);
      }
      
      // 前端驱动自动触发链
      runAutoTriggerChain(project.id, () => {
        blockAPI.getProjectBlocks(project.id).then((freshData) => {
          if (freshData.blocks) {
            setContentBlocks(freshData.blocks);
            notifyBlocksChangeIfNeeded(freshData.blocks);
          }
        }).catch(console.error);
      }).catch(console.error);
    } catch (err) {
      console.error("加载内容块失败:", err);
      setContentBlocks([]);
      notifyBlocksChangeIfNeeded([]);
    } finally {
      setIsLoadingBlocks(false);
      initialBlocksLoadDone.current = true;
    }
  };
  
  // P0-1: buildVirtualBlocksFromFields 已移除（不再从 ProjectField 构建虚拟块）
  
  // P0-1: handleMigrateToBlocks 已移除（所有项目都已统一为 ContentBlock 架构）

  const handleBlockSelect = (block: ContentBlock) => {
    setSelectedBlockId(block.id);
    onBlockSelect?.(block);
    
    // 如果是阶段类型，也触发 onPhaseClick
    if (block.block_type === "phase" && block.special_handler) {
      const phaseMap: Record<string, string> = {
        intent: "intent",
        research: "research",
        evaluate: "evaluate",
      };
      const phase = phaseMap[block.special_handler];
      if (phase) {
        onPhaseClick?.(phase);
      }
    }
  };

  return (
    <div className="p-4">
      {/* 项目信息 */}
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-zinc-100">
          {project?.name || "未选择项目"}
        </h2>
        {project && (
          <p className="text-sm text-zinc-500 mt-1">
            版本 {project.version}
          </p>
        )}
      </div>
      
      {/* P0-1: 视图切换已移除，所有项目使用树形架构 */}

      {/* 内容结构 - 树形视图 */}
      {project && (
        <div className="space-y-1">
          <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">
            内容结构
          </h3>
          
          {isLoadingBlocks ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full" />
            </div>
          ) : contentBlocks.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-zinc-500 mb-3">尚未创建内容块</p>
              <p className="text-xs text-zinc-600">
                与 Agent 对话或手动添加内容块开始项目
              </p>
            </div>
          ) : null}
          
          {/* P0-1: 统一使用 ContentBlock 架构，始终可编辑 */}
          <BlockTree
            blocks={contentBlocks}
            projectId={project.id}
            selectedBlockId={selectedBlockId}
            onSelectBlock={handleBlockSelect}
            onBlocksChange={loadContentBlocks}
            editable={true}
          />
        </div>
      )}

      {/* 分隔线 */}
      <div className="my-6 border-t border-surface-3" />

      {/* 快捷操作 */}
      <div className="space-y-2">
        <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">
          快捷操作
        </h3>
        
        <button className="w-full px-3 py-2 text-sm text-left text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors">
          + 新建版本
        </button>
        
        <button className="w-full px-3 py-2 text-sm text-left text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors">
          查看历史版本
        </button>
        
        <button className="w-full px-3 py-2 text-sm text-left text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors">
          导出内容
        </button>
      </div>

    </div>
  );
}

