// frontend/components/progress-panel.tsx
// 功能: 左栏项目进度面板，支持传统视图和树形视图切换
// 主要组件: ProgressPanel
// 新增: 树形视图集成 BlockTree 组件

"use client";

import { useState, useRef, useEffect } from "react";
import { cn, PHASE_NAMES, PHASE_STATUS } from "@/lib/utils";
import type { Project, ContentBlock, Field } from "@/lib/api";
import { blockAPI } from "@/lib/api";
import BlockTree from "./block-tree";
import { List, GitBranch } from "lucide-react";

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

// 阶段到特殊处理器的映射
const PHASE_SPECIAL_HANDLERS: Record<string, string> = {
  intent: "intent",
  research: "research",
  simulate: "simulate",
  evaluate: "evaluate",
};

// 固定阶段定义
const FIXED_TOP_PHASES = ["intent", "research"];
const DRAGGABLE_PHASES = ["design_inner", "produce_inner", "design_outer", "produce_outer"];
const FIXED_BOTTOM_PHASES = ["simulate", "evaluate"];

type ViewMode = "classic" | "tree";

interface ProgressPanelProps {
  project: Project | null;
  fields?: Field[];  // 传统字段数据，用于构建虚拟树形视图
  onPhaseClick?: (phase: string) => void;
  onPhaseReorder?: (phases: string[]) => void;
  onAutonomyChange?: (autonomy: Record<string, boolean>) => void;
  onBlockSelect?: (block: ContentBlock) => void;
  onBlocksChange?: (blocks: ContentBlock[]) => void;  // 当内容块加载/变化时通知父组件
  onProjectChange?: () => void;  // 项目数据变化时通知父组件刷新
}

export function ProgressPanel({
  project,
  fields = [],
  onPhaseClick,
  onPhaseReorder,
  onAutonomyChange,
  onProjectChange,
  onBlockSelect,
  onBlocksChange,
}: ProgressPanelProps) {
  const [showAutonomySettings, setShowAutonomySettings] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("viewMode") as ViewMode) || "classic";
    }
    return "classic";
  });
  const [contentBlocks, setContentBlocks] = useState<ContentBlock[]>([]);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [isLoadingBlocks, setIsLoadingBlocks] = useState(false);
  const [isMigrating, setIsMigrating] = useState(false);
  
  // 灵活架构项目强制使用树形视图，锁死传统视图
  const isFlexibleArch = project?.use_flexible_architecture === true;
  
  useEffect(() => {
    if (isFlexibleArch && viewMode !== "tree") {
      setViewMode("tree");
      localStorage.setItem("viewMode", "tree");
    }
  }, [isFlexibleArch, viewMode]);
  
  const allPhases = project?.phase_order || [];
  const phaseStatus = project?.phase_status || {};
  const currentPhase = project?.current_phase || "intent";
  
  // 加载内容块（树形视图用）
  // 对于传统架构，等待 fields 加载完成后再构建虚拟块
  // 对于灵活架构，从后端加载 ContentBlock
  useEffect(() => {
    if (viewMode === "tree" && project?.id) {
      if (project.use_flexible_architecture) {
        // 灵活架构：从后端加载
        loadContentBlocks();
      } else if (fields.length > 0) {
        // 传统架构：等 fields 加载完成后构建虚拟块
        const virtualBlocks = buildVirtualBlocksFromFields(project, fields);
        setContentBlocks(virtualBlocks);
        onBlocksChange?.(flattenBlocks(virtualBlocks));
      }
    }
  }, [viewMode, project?.id, project?.use_flexible_architecture, fields]);
  
  const loadContentBlocks = async () => {
    if (!project?.id) return;
    
    setIsLoadingBlocks(true);
    try {
      // ===== 关键逻辑：根据项目架构决定数据来源 =====
      // 如果项目使用灵活架构（use_flexible_architecture=true），从 ContentBlock 表加载
      // 否则，始终从 ProjectField 构建虚拟块（确保数据同步）
      
      if (project.use_flexible_architecture) {
        // 真正的灵活架构项目：从 ContentBlock 表加载
        const data = await blockAPI.getProjectBlocks(project.id);
        if (data.blocks && data.blocks.length > 0) {
          setContentBlocks(data.blocks);
          // 传递扁平化的块列表，用于依赖选择
          onBlocksChange?.(flattenBlocks(data.blocks));
        } else {
          // 灵活架构但没有数据，显示空状态
          setContentBlocks([]);
          onBlocksChange?.([]);
        }
      } else {
        // 传统架构项目：始终从 ProjectField 构建虚拟块
        // 这确保了树形视图和传统视图显示相同的数据
        const virtualBlocks = buildVirtualBlocksFromFields(project, fields);
        setContentBlocks(virtualBlocks);
        onBlocksChange?.(flattenBlocks(virtualBlocks));
      }
    } catch (err) {
      console.error("加载内容块失败:", err);
      // 失败时从 fields 构建虚拟块
      const virtualBlocks = buildVirtualBlocksFromFields(project, fields);
      setContentBlocks(virtualBlocks);
      onBlocksChange?.(flattenBlocks(virtualBlocks));
    } finally {
      setIsLoadingBlocks(false);
    }
  };
  
  // 从传统 fields 构建虚拟树形结构
  const buildVirtualBlocksFromFields = (project: Project, fields: Field[]): ContentBlock[] => {
    const phaseOrder = project.phase_order || [];
    const phaseStatus = project.phase_status || {};
    
    // 按阶段分组字段
    const fieldsByPhase: Record<string, Field[]> = {};
    for (const field of fields) {
      if (!fieldsByPhase[field.phase]) {
        fieldsByPhase[field.phase] = [];
      }
      fieldsByPhase[field.phase].push(field);
    }
    
    // 为每个阶段创建虚拟的 ContentBlock
    const virtualBlocks: ContentBlock[] = phaseOrder.map((phase, idx) => {
      const phaseFields = fieldsByPhase[phase] || [];
      
      // 阶段块
      const phaseBlock: ContentBlock = {
        id: `virtual_phase_${phase}`,
        project_id: project.id,
        parent_id: null,
        name: PHASE_NAMES[phase] || phase,
        block_type: "phase",
        depth: 0,
        order_index: idx,
        content: "",
        status: phaseStatus[phase] as "pending" | "in_progress" | "completed" | "failed" || "pending",
        ai_prompt: "",
        constraints: {},
        depends_on: [],
        special_handler: PHASE_SPECIAL_HANDLERS[phase] || null,
        need_review: true,
        is_collapsed: false,
        children: phaseFields.map((field, fieldIdx) => ({
          id: field.id,  // 使用真实的 field id
          project_id: project.id,
          parent_id: `virtual_phase_${phase}`,
          name: field.name,
          block_type: "field" as const,
          depth: 1,
          order_index: fieldIdx,
          content: field.content || "",
          status: field.status as "pending" | "in_progress" | "completed" | "failed" || "pending",
          ai_prompt: field.ai_prompt || "",
          constraints: field.constraints || {},
          depends_on: field.dependencies?.depends_on || [],
          special_handler: null,
          need_review: field.need_review,
          is_collapsed: false,
          children: [],
          created_at: field.created_at,
          updated_at: field.updated_at,
        })),
        created_at: null,
        updated_at: null,
      };
      
      return phaseBlock;
    });
    
    return virtualBlocks;
  };
  
  // 迁移传统项目到 content_blocks 架构
  const handleMigrateToBlocks = async () => {
    if (!project?.id) return;
    
    if (!confirm("确定要迁移到灵活架构吗？迁移后可以自由添加/删除/排序阶段和字段。")) {
      return;
    }
    
    setIsMigrating(true);
    try {
      // 调用后端迁移 API
      const result = await blockAPI.migrateProject(project.id);
      
      // 通知父组件刷新项目数据（以获取最新的 use_flexible_architecture）
      // 注意：需要等待父组件更新完成后才能正确加载内容块
      // 这里用 setTimeout 等待一个渲染周期
      await new Promise<void>((resolve) => {
        onProjectChange?.();
        // 给父组件时间更新 project prop
        setTimeout(resolve, 100);
      });
      
      // 迁移成功后，直接从 API 加载真实的 ContentBlocks（不依赖 project prop）
      const data = await blockAPI.getProjectBlocks(project.id);
      if (data.blocks && data.blocks.length > 0) {
        setContentBlocks(data.blocks);
        onBlocksChange?.(flattenBlocks(data.blocks));
      }

      alert(`迁移成功！已创建 ${result.phases_created} 个阶段，迁移 ${result.fields_migrated} 个字段。\n\n请刷新页面以确保所有状态同步。`);
    } catch (err) {
      console.error("迁移失败:", err);
      alert("迁移失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsMigrating(false);
    }
  };

  const handleBlockSelect = (block: ContentBlock) => {
    setSelectedBlockId(block.id);
    onBlockSelect?.(block);
    
    // 如果是阶段类型，也触发 onPhaseClick
    if (block.block_type === "phase" && block.special_handler) {
      const phaseMap: Record<string, string> = {
        intent: "intent",
        research: "research",
        simulate: "simulate",
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

  // 获取阶段下的字段
  const getPhaseFields = (phase: string): Field[] => {
    return fields.filter(f => f.phase === phase);
  };
  
  // 折叠状态
  const [expandedPhases, setExpandedPhases] = useState<Record<string, boolean>>(() => {
    // 默认展开当前阶段
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
    const phaseFields = getPhaseFields(phase);
    const isExpanded = expandedPhases[phase] ?? isCurrent;  // 当前阶段默认展开
    
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
          {/* 无字段时占位 */}
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
                status === "completed" && "bg-green-500",
                status === "in_progress" && "bg-yellow-500",
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
        
        {/* 阶段下的字段列表 */}
        {isExpanded && phaseFields.length > 0 && (
          <div className="ml-6 mt-1 space-y-0.5">
            {phaseFields.map(field => {
              const fieldStatus = field.status || "pending";
              return (
                <button
                  key={field.id}
                  onClick={() => {
                    // 将字段转换为 ContentBlock 格式传递
                    const virtualBlock: ContentBlock = {
                      id: field.id,
                      project_id: project?.id || "",
                      parent_id: `virtual_phase_${phase}`,
                      name: field.name,
                      block_type: "field",
                      depth: 1,
                      order_index: 0,
                      content: field.content || "",
                      status: fieldStatus as "pending" | "in_progress" | "completed" | "failed",
                      ai_prompt: field.ai_prompt || "",
                      constraints: field.constraints || {},
                      depends_on: field.dependencies?.depends_on || [],
                      special_handler: null,
                      need_review: field.need_review,
                      is_collapsed: false,
                      children: [],
                      created_at: field.created_at,
                      updated_at: field.updated_at,
                    };
                    onBlockSelect?.(virtualBlock);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-sm hover:bg-surface-3 transition-colors"
                >
                  {/* 字段状态指示器 */}
                  <div
                    className={cn(
                      "w-1.5 h-1.5 rounded-full flex-shrink-0",
                      fieldStatus === "completed" && "bg-green-500",
                      fieldStatus === "in_progress" && "bg-yellow-500",
                      fieldStatus === "pending" && "bg-zinc-600"
                    )}
                  />
                  {/* 字段名称 */}
                  <span className="flex-1 text-zinc-400 truncate">
                    {field.name}
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
      
      {/* 视图切换 */}
      {project && (
        <div className="flex items-center gap-1 mb-4 p-1 bg-surface-1 rounded-lg">
          <button
            onClick={() => { 
              if (!isFlexibleArch) {
                setViewMode("classic"); 
                localStorage.setItem("viewMode", "classic"); 
              }
            }}
            disabled={isFlexibleArch}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
              isFlexibleArch
                ? "text-zinc-600 cursor-not-allowed opacity-50"
                : viewMode === "classic"
                  ? "bg-surface-3 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
            )}
            title={isFlexibleArch ? "已迁移至树形架构，无法切换回传统视图" : "切换到传统视图"}
          >
            <List className="w-3.5 h-3.5" />
            传统
            {isFlexibleArch && <span className="ml-0.5">🔒</span>}
          </button>
          <button
            onClick={() => { setViewMode("tree"); localStorage.setItem("viewMode", "tree"); }}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
              viewMode === "tree"
                ? "bg-surface-3 text-zinc-200"
                : "text-zinc-500 hover:text-zinc-300"
            )}
          >
            <GitBranch className="w-3.5 h-3.5" />
            树形
          </button>
        </div>
      )}

      {/* 流程进度 - 传统视图 */}
      {viewMode === "classic" && (
        <div className="space-y-1">
          <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">
            流程进度
          </h3>
          
          {/* 顶部固定阶段 */}
          {topPhases.map(phase => renderPhaseItem(phase, false))}
          
          {/* 可拖拽的中间阶段 */}
          {middlePhases.length > 0 && (
            <div className="py-1">
              <div className="text-xs text-zinc-600 px-3 mb-1 flex items-center gap-1">
                <span>↕</span>
                <span>可拖拽调整顺序</span>
              </div>
              {middlePhases.map(phase => renderPhaseItem(phase, true))}
            </div>
          )}
          
          {/* 底部固定阶段 */}
          {bottomPhases.map(phase => renderPhaseItem(phase, false))}
        </div>
      )}
      
      {/* 流程进度 - 树形视图 */}
      {viewMode === "tree" && project && (
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
                可在此添加阶段，或切换到传统视图使用预设流程
              </p>
            </div>
          ) : null}
          
          {/* 判断是否是虚拟树形结构 */}
          {!project.use_flexible_architecture ? (
            <>
              {/* 虚拟结构只读提示 */}
              <div className="mb-3 p-3 bg-amber-900/20 border border-amber-700/30 rounded-lg">
                <p className="text-xs text-amber-300">
                  当前显示传统流程的树形视图（只读）
                </p>
                <button
                  onClick={handleMigrateToBlocks}
                  disabled={isMigrating}
                  className="mt-2 w-full px-3 py-1.5 text-xs bg-brand-600 hover:bg-brand-700 disabled:opacity-50 rounded-lg transition-colors"
                >
                  {isMigrating ? "迁移中..." : "迁移到灵活架构（可编辑）"}
                </button>
              </div>
              <BlockTree
                blocks={contentBlocks}
                projectId={project.id}
                selectedBlockId={selectedBlockId}
                onSelectBlock={handleBlockSelect}
                onBlocksChange={loadContentBlocks}
                editable={false}  // 虚拟结构不可编辑
              />
            </>
          ) : (
            <BlockTree
              blocks={contentBlocks}
              projectId={project.id}
              selectedBlockId={selectedBlockId}
              onSelectBlock={handleBlockSelect}
              onBlocksChange={loadContentBlocks}
              editable={true}  // 真实结构可编辑
            />
          )}
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

  const allPhases = [
    { id: "intent", name: "意图分析", desc: "Agent自动提问并分析意图" },
    { id: "research", name: "消费者调研", desc: "Agent自动调研用户画像" },
    { id: "design_inner", name: "内涵设计", desc: "Agent自动设计内容方案" },
    { id: "produce_inner", name: "内涵生产", desc: "Agent自动生产各字段内容" },
    { id: "design_outer", name: "外延设计", desc: "Agent自动设计传播方案" },
    { id: "produce_outer", name: "外延生产", desc: "Agent自动生产渠道内容" },
    { id: "simulate", name: "消费者模拟", desc: "Agent自动模拟用户体验" },
    { id: "evaluate", name: "评估", desc: "Agent自动评估内容质量" },
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
            设置各阶段Agent是否自动执行，不勾选 = 需要人工确认后才继续
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
