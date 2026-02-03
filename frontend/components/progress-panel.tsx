// frontend/components/progress-panel.tsx
// 功能: 左栏项目进度面板，支持中间4阶段拖拽排序
// 主要组件: ProgressPanel
// 固定阶段: 意图分析、消费者调研在顶部；消费者模拟、评估在底部
// 可拖拽阶段: 内涵设计、内涵生产、外延设计、外延生产

"use client";

import { useState, useRef } from "react";
import { cn, PHASE_NAMES, PHASE_STATUS } from "@/lib/utils";
import type { Project } from "@/lib/api";

// 固定阶段定义
const FIXED_TOP_PHASES = ["intent", "research"];
const DRAGGABLE_PHASES = ["design_inner", "produce_inner", "design_outer", "produce_outer"];
const FIXED_BOTTOM_PHASES = ["simulate", "evaluate"];

interface ProgressPanelProps {
  project: Project | null;
  onPhaseClick?: (phase: string) => void;
  onPhaseReorder?: (phases: string[]) => void;
  onAutonomyChange?: (autonomy: Record<string, boolean>) => void;
}

export function ProgressPanel({
  project,
  onPhaseClick,
  onPhaseReorder,
  onAutonomyChange,
}: ProgressPanelProps) {
  const [showAutonomySettings, setShowAutonomySettings] = useState(false);
  const allPhases = project?.phase_order || [];
  const phaseStatus = project?.phase_status || {};
  const currentPhase = project?.current_phase || "intent";
  
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

  const renderPhaseItem = (phase: string, isDraggable: boolean) => {
    const status = phaseStatus[phase] || "pending";
    const statusInfo = PHASE_STATUS[status] || PHASE_STATUS.pending;
    const isCurrent = phase === currentPhase;
    const isDragging = draggedPhase === phase;
    const isDragOver = dragOverPhase === phase;
    
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
        <button
          onClick={() => onPhaseClick?.(phase)}
          className={cn(
            "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors",
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
          
          {/* 状态标签 */}
          <span className={cn("text-xs", statusInfo.color)}>
            {statusInfo.label}
          </span>
        </button>
      </div>
    );
  };

  return (
    <div className="p-4">
      {/* 项目信息 */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-zinc-100">
          {project?.name || "未选择项目"}
        </h2>
        {project && (
          <p className="text-sm text-zinc-500 mt-1">
            版本 {project.version}
          </p>
        )}
      </div>

      {/* 流程进度 */}
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
