// frontend/components/progress-panel.tsx
// 功能: 左栏项目进度面板，支持传统视图和树形视图切换
// 主要组件: ProgressPanel
// 新增: 树形视图集成 BlockTree 组件
// P0-1: 统一使用 ContentBlock，已移除 fields/ProjectField 依赖
// 优化: 首次加载才显示 spinner；onBlocksChange 仅在数据实际变化时触发

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { cn, PHASE_NAMES, PHASE_STATUS, PHASE_SPECIAL_HANDLERS, FIXED_TOP_PHASES, DRAGGABLE_PHASES, FIXED_BOTTOM_PHASES } from "@/lib/utils";
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
  onPhaseReorder?: (phases: string[]) => void;
  onAutonomyChange?: (autonomy: Record<string, boolean>) => void;
  onBlockSelect?: (block: ContentBlock) => void;
  onBlocksChange?: (blocks: ContentBlock[]) => void;  // 当内容块加载/变化时通知父组件
  onProjectChange?: () => void;  // 项目数据变化时通知父组件刷新
}

export function ProgressPanel({
  project,
  blocksRefreshKey = 0,
  onPhaseClick,
  onPhaseReorder,
  onAutonomyChange,
  onProjectChange,
  onBlockSelect,
  onBlocksChange,
}: ProgressPanelProps) {
  const [showAutonomySettings, setShowAutonomySettings] = useState(false);
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
  
  const allPhases = project?.phase_order || [];
  const phaseStatus = project?.phase_status || {};
  const currentPhase = project?.current_phase || "intent";
  
  // ===== 加载内容块 =====
  // P0-1: 统一使用 ContentBlock API，classic 和 tree 视图都需要
  useEffect(() => {
    if (project?.id) {
      loadContentBlocks();
    }
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
  
  // 分离固定和可拖拽阶段
  const topPhases = allPhases.filter(p => FIXED_TOP_PHASES.includes(p));
  const middlePhases = allPhases.filter(p => DRAGGABLE_PHASES.includes(p));
  const bottomPhases = allPhases.filter(p => FIXED_BOTTOM_PHASES.includes(p));
  
  // 拖拽状态
  const [draggedPhase, setDraggedPhase] = useState<string | null>(null);
  const [dragOverPhase, setDragOverPhase] = useState<string | null>(null);
  const dragCounter = useRef(0);

  const handleDragStart = (e: React.DragEvent, phase: string) => {
    setDraggedPhase(phase);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", phase);
  };

  const handleDragEnd = () => {
    setDraggedPhase(null);
    setDragOverPhase(null);
    dragCounter.current = 0;
  };

  const handleDragEnter = (e: React.DragEvent, phase: string) => {
    e.preventDefault();
    dragCounter.current++;
    if (DRAGGABLE_PHASES.includes(phase)) {
      setDragOverPhase(phase);
    }
  };

  const handleDragLeave = () => {
    dragCounter.current--;
    if (dragCounter.current === 0) {
      setDragOverPhase(null);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent, targetPhase: string) => {
    e.preventDefault();
    
    if (!draggedPhase || draggedPhase === targetPhase) {
      handleDragEnd();
      return;
    }
    
    // 重新排序中间阶段
    const newMiddle = [...middlePhases];
    const dragIdx = newMiddle.indexOf(draggedPhase);
    const dropIdx = newMiddle.indexOf(targetPhase);
    
    if (dragIdx !== -1 && dropIdx !== -1) {
      newMiddle.splice(dragIdx, 1);
      newMiddle.splice(dropIdx, 0, draggedPhase);
      
      // 重建完整顺序
      const newOrder = [...topPhases, ...newMiddle, ...bottomPhases];
      onPhaseReorder?.(newOrder);
    }
    
    handleDragEnd();
  };

  // P0-1: 从 contentBlocks 中获取某个阶段下的子块（替代旧的 ProjectField 查询）
  const getPhaseBlocks = (phase: string): ContentBlock[] => {
    const phaseBlock = contentBlocks.find(b => b.block_type === "phase" && (b.name === (PHASE_NAMES[phase] || phase) || b.name === phase));
    return phaseBlock?.children || [];
  };
  
  // 折叠状态
  const [expandedPhases, setExpandedPhases] = useState<Record<string, boolean>>(() => {
    // 默认展开当前组
    const initial: Record<string, boolean> = {};
    if (project?.current_phase) {
      initial[project.current_phase] = true;
    }
    return initial;
  });
  
  const togglePhaseExpand = (phase: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedPhases(prev => ({
      ...prev,
      [phase]: !prev[phase]
    }));
  };

  const renderPhaseItem = (phase: string, isDraggable: boolean) => {
    const status = phaseStatus[phase] || "pending";
    const statusInfo = PHASE_STATUS[status] || PHASE_STATUS.pending;
    const isCurrent = phase === currentPhase;
    const isDragging = draggedPhase === phase;
    const isDragOver = dragOverPhase === phase;
    const phaseFields = getPhaseBlocks(phase);
    const isExpanded = expandedPhases[phase] ?? isCurrent;  // 当前组默认展开
    
    return (
      <div
        key={phase}
        draggable={isDraggable}
        onDragStart={isDraggable ? (e) => handleDragStart(e, phase) : undefined}
        onDragEnd={isDraggable ? handleDragEnd : undefined}
        onDragEnter={isDraggable ? (e) => handleDragEnter(e, phase) : undefined}
        onDragLeave={isDraggable ? handleDragLeave : undefined}
        onDragOver={isDraggable ? handleDragOver : undefined}
        onDrop={isDraggable ? (e) => handleDrop(e, phase) : undefined}
        className={cn(
          "relative transition-all duration-150",
          isDragging && "opacity-50",
          isDragOver && "before:absolute before:inset-x-0 before:-top-1 before:h-0.5 before:bg-brand-500"
        )}
      >
        <div className="flex items-center">
          {/* 展开/折叠按钮 */}
          {phaseFields.length > 0 && (
            <button
              onClick={(e) => togglePhaseExpand(phase, e)}
              className="p-1 text-zinc-500 hover:text-zinc-300"
            >
              <span className={cn(
                "inline-block transition-transform text-xs",
                isExpanded ? "rotate-90" : ""
              )}>▶</span>
            </button>
          )}
          {/* 无内容块时占位 */}
          {phaseFields.length === 0 && <span className="w-6" />}
          
          <button
            onClick={() => onPhaseClick?.(phase)}
            className={cn(
              "flex-1 flex items-center gap-3 px-2 py-2 rounded-lg text-left transition-colors",
              isCurrent
                ? "bg-brand-600/20 text-brand-400"
                : "hover:bg-surface-3 text-zinc-300",
              isDraggable && "cursor-grab active:cursor-grabbing"
            )}
          >
            {/* 拖拽手柄 */}
            {isDraggable && (
              <span className="text-zinc-600 text-xs select-none">⋮⋮</span>
            )}
            
            {/* 状态指示器 */}
            <div
              className={cn(
                "w-2 h-2 rounded-full flex-shrink-0",
                status === "completed" && "bg-emerald-500",
                status === "in_progress" && "bg-amber-500",
                status === "pending" && "bg-zinc-600"
              )}
            />
            
            {/* 阶段名称 */}
            <span className="flex-1 text-sm">
              {PHASE_NAMES[phase] || phase}
            </span>
            
            {/* 字段数量 */}
            {phaseFields.length > 0 && (
              <span className="text-xs text-zinc-500">
                {phaseFields.length}
              </span>
            )}
            
            {/* 状态标签 */}
            <span className={cn("text-xs", statusInfo.color)}>
              {statusInfo.label}
            </span>
          </button>
        </div>
        
        {/* 阶段下的内容块列表 */}
        {isExpanded && phaseFields.length > 0 && (
          <div className="ml-6 mt-1 space-y-0.5">
            {phaseFields.map(block => {
              const blockStatus = block.status || "pending";
              return (
                <button
                  key={block.id}
                  onClick={() => {
                    // P0-1: 直接传递 ContentBlock，不再构建虚拟块
                    onBlockSelect?.(block);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-sm hover:bg-surface-3 transition-colors"
                >
                  {/* 字段状态指示器 */}
                  <div
                    className={cn(
                      "w-1.5 h-1.5 rounded-full flex-shrink-0",
                      blockStatus === "completed" && "bg-emerald-500",
                      blockStatus === "in_progress" && "bg-amber-500",
                      blockStatus === "pending" && "bg-zinc-600"
                    )}
                  />
                  {/* 内容块名称 */}
                  <span className="flex-1 text-zinc-400 truncate">
                    {block.name}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
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
        
        <button 
          onClick={() => setShowAutonomySettings(true)}
          className="w-full px-3 py-2 text-sm text-left text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors"
        >
          ⚙ Agent自主权设置
        </button>
        
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

      {/* Agent自主权设置弹窗 */}
      {showAutonomySettings && project && (
        <AutonomySettingsModal
          project={project}
          onClose={() => setShowAutonomySettings(false)}
          onSave={onAutonomyChange}
        />
      )}
    </div>
  );
}

interface AutonomySettingsModalProps {
  project: Project;
  onClose: () => void;
  onSave?: (autonomy: Record<string, boolean>) => void;
}

function AutonomySettingsModal({ project, onClose, onSave }: AutonomySettingsModalProps) {
  const [autonomy, setAutonomy] = useState<Record<string, boolean>>(
    project.agent_autonomy || {}
  );

  // Escape 键关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const allPhases = [
    { id: "intent", name: "意图分析", desc: "Agent自动提问并分析意图" },
    { id: "research", name: "消费者调研", desc: "Agent自动调研用户画像" },
    { id: "design_inner", name: "内涵设计", desc: "Agent自动设计内容方案" },
    { id: "produce_inner", name: "内涵生产", desc: "Agent自动生产各内容块内容" },
    { id: "design_outer", name: "外延设计", desc: "Agent自动设计传播方案" },
    { id: "produce_outer", name: "外延生产", desc: "Agent自动生产渠道内容" },
    { id: "evaluate", name: "评估", desc: "配置评估任务，执行多维度评估" },
  ];

  const handleToggle = (phase: string) => {
    setAutonomy((prev) => ({
      ...prev,
      [phase]: !prev[phase],
    }));
  };

  const handleSave = () => {
    onSave?.(autonomy);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden">
        <div className="px-4 py-3 border-b border-surface-3">
          <h3 className="font-medium text-zinc-200">Agent自主权设置</h3>
          <p className="text-xs text-zinc-500 mt-1">
            设置各组Agent是否自动执行，不勾选 = 需要人工确认后才继续
          </p>
        </div>

        <div className="p-4 max-h-[50vh] overflow-y-auto space-y-3">
          {allPhases.map((phase) => (
            <label
              key={phase.id}
              className="flex items-start gap-3 p-3 rounded-lg hover:bg-surface-3 cursor-pointer"
            >
              <input
                type="checkbox"
                checked={autonomy[phase.id] !== false}
                onChange={() => handleToggle(phase.id)}
                className="mt-0.5 rounded"
              />
              <div className="flex-1">
                <div className="text-sm text-zinc-200">{phase.name}</div>
                <div className="text-xs text-zinc-500 mt-0.5">{phase.desc}</div>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded ${
                autonomy[phase.id] !== false
                  ? "bg-green-600/20 text-green-400"
                  : "bg-yellow-600/20 text-yellow-400"
              }`}>
                {autonomy[phase.id] !== false ? "自动" : "需确认"}
              </span>
            </label>
          ))}
        </div>

        <div className="px-4 py-3 border-t border-surface-3 flex justify-between">
          <div className="flex gap-2">
            <button
              onClick={() => setAutonomy(allPhases.reduce((acc, p) => ({ ...acc, [p.id]: true }), {}))}
              className="px-3 py-1.5 text-xs bg-surface-3 hover:bg-surface-4 rounded-lg"
            >
              全部自动
            </button>
            <button
              onClick={() => setAutonomy(allPhases.reduce((acc, p) => ({ ...acc, [p.id]: false }), {}))}
              className="px-3 py-1.5 text-xs bg-surface-3 hover:bg-surface-4 rounded-lg"
            >
              全部确认
            </button>
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg"
            >
              保存
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
