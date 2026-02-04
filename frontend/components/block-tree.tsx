// frontend/components/block-tree.tsx
// 功能: 树形内容块展示组件
// 主要组件: BlockTree, BlockNode
// 数据结构: ContentBlock 树形结构

"use client";

import { useState, useCallback } from "react";
import {
  ChevronRight,
  ChevronDown,
  Plus,
  Trash2,
  GripVertical,
  FileText,
  Folder,
  Lightbulb,
  Users,
  PlayCircle,
  BarChart3,
  MoreHorizontal,
  Edit2,
  Copy,
  ArrowRight,
  Undo2,
} from "lucide-react";
import { ContentBlock, blockAPI } from "@/lib/api";

interface UndoHistoryItem {
  history_id: string;
  block_name: string;
  children_count: number;
}

interface BlockTreeProps {
  blocks: ContentBlock[];
  projectId: string;
  selectedBlockId?: string | null;
  onSelectBlock?: (block: ContentBlock) => void;
  onBlocksChange?: () => void;
  editable?: boolean;
}

interface BlockNodeProps {
  block: ContentBlock;
  level: number;
  selectedBlockId?: string | null;
  onSelectBlock?: (block: ContentBlock) => void;
  onBlocksChange?: () => void;
  editable?: boolean;
  onDragStart?: (block: ContentBlock) => void;
  onDragOver?: (block: ContentBlock, position: "before" | "after" | "inside") => void;
  onDragEnd?: () => void;
  dragTarget?: { blockId: string; position: "before" | "after" | "inside" } | null;
  onDeleteSuccess?: (historyItem: UndoHistoryItem) => void;
}

// 状态颜色
const statusColors: Record<string, string> = {
  pending: "bg-zinc-600",
  in_progress: "bg-amber-500",
  completed: "bg-emerald-500",
  failed: "bg-red-500",
};

// 特殊处理器图标
const specialHandlerIcons: Record<string, React.ReactNode> = {
  intent: <Lightbulb className="w-4 h-4" />,
  research: <Users className="w-4 h-4" />,
  simulate: <PlayCircle className="w-4 h-4" />,
  evaluate: <BarChart3 className="w-4 h-4" />,
};

// 块类型图标
const blockTypeIcons: Record<string, React.ReactNode> = {
  phase: <Folder className="w-4 h-4" />,
  field: <FileText className="w-4 h-4" />,
  proposal: <Copy className="w-4 h-4" />,
  group: <Folder className="w-4 h-4" />,
};

function BlockNode({
  block,
  level,
  selectedBlockId,
  onSelectBlock,
  onBlocksChange,
  editable = true,
  onDragStart,
  onDragOver,
  onDragEnd,
  dragTarget,
  onDeleteSuccess,
}: BlockNodeProps) {
  const [isCollapsed, setIsCollapsed] = useState(block.is_collapsed);
  const [showMenu, setShowMenu] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [newName, setNewName] = useState(block.name);
  const [isLoading, setIsLoading] = useState(false);

  const hasChildren = block.children && block.children.length > 0;
  const isSelected = selectedBlockId === block.id;
  const isDragTarget = dragTarget?.blockId === block.id;

  // 获取显示图标
  const getIcon = () => {
    if (block.special_handler && specialHandlerIcons[block.special_handler]) {
      return specialHandlerIcons[block.special_handler];
    }
    return blockTypeIcons[block.block_type] || <FileText className="w-4 h-4" />;
  };

  // 处理折叠/展开
  const toggleCollapse = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsCollapsed(!isCollapsed);
    
    // 保存折叠状态到后端
    try {
      await blockAPI.update(block.id, { is_collapsed: !isCollapsed });
    } catch (err) {
      console.error("保存折叠状态失败:", err);
    }
  };

  // 处理选择
  const handleSelect = () => {
    onSelectBlock?.(block);
  };

  // 处理重命名
  const handleRename = async () => {
    if (newName.trim() === "") return;
    if (newName === block.name) {
      setIsRenaming(false);
      return;
    }

    setIsLoading(true);
    try {
      await blockAPI.update(block.id, { name: newName.trim() });
      onBlocksChange?.();
    } catch (err) {
      console.error("重命名失败:", err);
      setNewName(block.name);
    } finally {
      setIsLoading(false);
      setIsRenaming(false);
    }
  };

  // 处理删除（软删除，可撤回）
  const handleDelete = async () => {
    if (!confirm(`确定删除「${block.name}」${hasChildren ? "及其所有子内容" : ""}？删除后可撤回。`)) {
      return;
    }

    setIsLoading(true);
    try {
      const result = await blockAPI.delete(block.id);
      // 通知父组件保存撤回信息
      if (result.can_undo && result.history_id) {
        onDeleteSuccess?.({
          history_id: result.history_id,
          block_name: block.name,
          children_count: block.children?.length || 0,
        });
      }
      onBlocksChange?.();
    } catch (err) {
      console.error("删除失败:", err);
      alert("删除失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsLoading(false);
    }
  };

  // 处理添加子块
  const handleAddChild = async (blockType: string) => {
    setIsLoading(true);
    try {
      await blockAPI.create({
        project_id: block.project_id,
        parent_id: block.id,
        name: `新${blockType === "field" ? "字段" : "分组"}`,
        block_type: blockType,
      });
      setIsCollapsed(false);
      onBlocksChange?.();
    } catch (err) {
      console.error("添加子块失败:", err);
      alert("添加失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsLoading(false);
      setShowMenu(false);
    }
  };

  // 处理生成
  const handleGenerate = async () => {
    setIsLoading(true);
    try {
      const result = await blockAPI.generate(block.id);
      onBlocksChange?.();
      console.log("生成结果:", result);
    } catch (err) {
      console.error("生成失败:", err);
      alert("生成失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsLoading(false);
      setShowMenu(false);
    }
  };

  return (
    <div className="select-none">
      {/* 节点本身 */}
      <div
        className={`
          flex items-center gap-1 px-2 py-1.5 rounded-lg cursor-pointer
          transition-all duration-150 group
          ${isSelected ? "bg-brand-500/20 border border-brand-500/50" : "hover:bg-surface-2"}
          ${isDragTarget && dragTarget?.position === "inside" ? "ring-2 ring-brand-500" : ""}
          ${isLoading ? "opacity-50 pointer-events-none" : ""}
        `}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={handleSelect}
        draggable={editable && !isRenaming}
        onDragStart={() => onDragStart?.(block)}
        onDragOver={(e) => {
          e.preventDefault();
          const rect = e.currentTarget.getBoundingClientRect();
          const y = e.clientY - rect.top;
          const position = y < rect.height / 3 ? "before" : y > (rect.height * 2) / 3 ? "after" : "inside";
          onDragOver?.(block, position);
        }}
        onDragEnd={onDragEnd}
      >
        {/* 拖拽手柄 */}
        {editable && (
          <GripVertical className="w-3 h-3 text-zinc-600 opacity-0 group-hover:opacity-100 cursor-grab" />
        )}

        {/* 展开/折叠按钮 */}
        <button
          onClick={toggleCollapse}
          className={`w-4 h-4 flex items-center justify-center ${hasChildren ? "" : "invisible"}`}
        >
          {isCollapsed ? (
            <ChevronRight className="w-3 h-3 text-zinc-500" />
          ) : (
            <ChevronDown className="w-3 h-3 text-zinc-500" />
          )}
        </button>

        {/* 图标 */}
        <span className="text-zinc-400">{getIcon()}</span>

        {/* 名称 */}
        {isRenaming ? (
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onBlur={handleRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleRename();
              if (e.key === "Escape") {
                setNewName(block.name);
                setIsRenaming(false);
              }
            }}
            className="flex-1 bg-surface-0 border border-surface-3 rounded px-1 py-0.5 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-brand-500"
            autoFocus
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className="flex-1 text-sm text-zinc-200 truncate">{block.name}</span>
        )}

        {/* 状态指示器 */}
        <span
          className={`w-2 h-2 rounded-full ${statusColors[block.status] || statusColors.pending}`}
          title={block.status}
        />

        {/* 菜单按钮 */}
        {editable && (
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowMenu(!showMenu);
              }}
              className="p-1 rounded hover:bg-surface-3 opacity-0 group-hover:opacity-100"
            >
              <MoreHorizontal className="w-4 h-4 text-zinc-500" />
            </button>

            {/* 下拉菜单 */}
            {showMenu && (
              <div
                className="absolute right-0 top-full mt-1 w-40 bg-surface-1 border border-surface-3 rounded-lg shadow-lg z-50"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => {
                    setIsRenaming(true);
                    setShowMenu(false);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-zinc-300 hover:bg-surface-2"
                >
                  <Edit2 className="w-4 h-4" />
                  重命名
                </button>

                {block.block_type !== "field" && (
                  <>
                    <button
                      onClick={() => handleAddChild("field")}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-zinc-300 hover:bg-surface-2"
                    >
                      <Plus className="w-4 h-4" />
                      添加字段
                    </button>
                    <button
                      onClick={() => handleAddChild("group")}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-zinc-300 hover:bg-surface-2"
                    >
                      <Folder className="w-4 h-4" />
                      添加分组
                    </button>
                  </>
                )}

                {block.block_type === "field" && block.ai_prompt && (
                  <button
                    onClick={handleGenerate}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-zinc-300 hover:bg-surface-2"
                  >
                    <ArrowRight className="w-4 h-4" />
                    生成内容
                  </button>
                )}

                <hr className="my-1 border-surface-3" />

                <button
                  onClick={handleDelete}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-surface-2"
                >
                  <Trash2 className="w-4 h-4" />
                  删除
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 子节点 */}
      {!isCollapsed && hasChildren && (
        <div className="relative">
          {/* 连接线 */}
          <div
            className="absolute left-0 top-0 bottom-0 border-l border-surface-3"
            style={{ marginLeft: `${level * 16 + 20}px` }}
          />
          
          {block.children.map((child) => (
            <BlockNode
              key={child.id}
              block={child}
              level={level + 1}
              selectedBlockId={selectedBlockId}
              onSelectBlock={onSelectBlock}
              onBlocksChange={onBlocksChange}
              editable={editable}
              onDragStart={onDragStart}
              onDragOver={onDragOver}
              onDragEnd={onDragEnd}
              dragTarget={dragTarget}
              onDeleteSuccess={onDeleteSuccess}
            />
          ))}
        </div>
      )}

      {/* 拖拽位置指示器 */}
      {isDragTarget && dragTarget?.position === "before" && (
        <div
          className="absolute left-0 right-0 h-0.5 bg-brand-500"
          style={{ marginLeft: `${level * 16 + 8}px`, marginTop: "-2px" }}
        />
      )}
      {isDragTarget && dragTarget?.position === "after" && (
        <div
          className="absolute left-0 right-0 h-0.5 bg-brand-500"
          style={{ marginLeft: `${level * 16 + 8}px` }}
        />
      )}
    </div>
  );
}

export default function BlockTree({
  blocks,
  projectId,
  selectedBlockId,
  onSelectBlock,
  onBlocksChange,
  editable = true,
}: BlockTreeProps) {
  const [dragSource, setDragSource] = useState<ContentBlock | null>(null);
  const [dragTarget, setDragTarget] = useState<{
    blockId: string;
    position: "before" | "after" | "inside";
  } | null>(null);
  
  // 撤回历史栈
  const [undoStack, setUndoStack] = useState<UndoHistoryItem[]>([]);
  const [isUndoing, setIsUndoing] = useState(false);

  // 处理删除成功，保存到撤回栈
  const handleDeleteSuccess = useCallback((item: UndoHistoryItem) => {
    setUndoStack(prev => [...prev, item]);
  }, []);

  // 处理撤回
  const handleUndo = useCallback(async () => {
    if (undoStack.length === 0) return;
    
    const lastItem = undoStack[undoStack.length - 1];
    setIsUndoing(true);
    
    try {
      await blockAPI.undo(lastItem.history_id);
      setUndoStack(prev => prev.slice(0, -1));
      onBlocksChange?.();
    } catch (err) {
      console.error("撤回失败:", err);
      alert("撤回失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsUndoing(false);
    }
  }, [undoStack, onBlocksChange]);

  // 处理拖拽开始
  const handleDragStart = useCallback((block: ContentBlock) => {
    setDragSource(block);
  }, []);

  // 处理拖拽经过
  const handleDragOver = useCallback(
    (block: ContentBlock, position: "before" | "after" | "inside") => {
      if (dragSource && dragSource.id !== block.id) {
        setDragTarget({ blockId: block.id, position });
      }
    },
    [dragSource]
  );

  // 处理拖拽结束
  const handleDragEnd = useCallback(async () => {
    if (!dragSource || !dragTarget) {
      setDragSource(null);
      setDragTarget(null);
      return;
    }

    try {
      // 根据位置计算新的 parent_id 和 order_index
      let newParentId: string | null = null;
      let newOrderIndex = 0;

      if (dragTarget.position === "inside") {
        // 移动到目标内部
        newParentId = dragTarget.blockId;
        newOrderIndex = 0;
      } else {
        // 移动到目标之前或之后，需要找到目标的父级和位置
        // 这里简化处理，实际需要更复杂的逻辑
        const targetBlock = findBlockById(blocks, dragTarget.blockId);
        if (targetBlock) {
          newParentId = targetBlock.parent_id;
          newOrderIndex =
            dragTarget.position === "before"
              ? targetBlock.order_index
              : targetBlock.order_index + 1;
        }
      }

      await blockAPI.move(dragSource.id, {
        new_parent_id: newParentId,
        new_order_index: newOrderIndex,
      });

      onBlocksChange?.();
    } catch (err) {
      console.error("移动失败:", err);
      alert("移动失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setDragSource(null);
      setDragTarget(null);
    }
  }, [dragSource, dragTarget, blocks, onBlocksChange]);

  // 添加顶级阶段
  const handleAddPhase = async () => {
    try {
      await blockAPI.create({
        project_id: projectId,
        name: "新阶段",
        block_type: "phase",
      });
      onBlocksChange?.();
    } catch (err) {
      console.error("添加阶段失败:", err);
      alert("添加失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  if (blocks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
        <Folder className="w-12 h-12 mb-4 opacity-50" />
        <p className="text-sm mb-4">暂无内容块</p>
        {editable && (
          <button
            onClick={handleAddPhase}
            className="flex items-center gap-2 px-4 py-2 bg-brand-500 text-white rounded-lg hover:bg-brand-600 transition-colors"
          >
            <Plus className="w-4 h-4" />
            添加阶段
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {/* 撤回按钮 */}
      {undoStack.length > 0 && (
        <div className="flex items-center gap-2 px-2 py-2 mb-2 bg-amber-500/10 border border-amber-500/30 rounded-lg">
          <Undo2 className="w-4 h-4 text-amber-400" />
          <span className="flex-1 text-sm text-amber-300">
            已删除「{undoStack[undoStack.length - 1].block_name}」
            {undoStack[undoStack.length - 1].children_count > 0 && 
              `（含 ${undoStack[undoStack.length - 1].children_count} 个子项）`
            }
          </span>
          <button
            onClick={handleUndo}
            disabled={isUndoing}
            className="px-3 py-1 text-sm bg-amber-600 hover:bg-amber-700 text-white rounded transition-colors disabled:opacity-50"
          >
            {isUndoing ? "撤回中..." : "撤回"}
          </button>
        </div>
      )}
      
      {blocks.map((block) => (
        <BlockNode
          key={block.id}
          block={block}
          level={0}
          selectedBlockId={selectedBlockId}
          onSelectBlock={onSelectBlock}
          onBlocksChange={onBlocksChange}
          editable={editable}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
          dragTarget={dragTarget}
          onDeleteSuccess={handleDeleteSuccess}
        />
      ))}

      {editable && (
        <button
          onClick={handleAddPhase}
          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-zinc-500 hover:text-zinc-300 hover:bg-surface-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          添加阶段
        </button>
      )}
    </div>
  );
}

// 辅助函数：根据 ID 查找块
function findBlockById(blocks: ContentBlock[], id: string): ContentBlock | null {
  for (const block of blocks) {
    if (block.id === id) return block;
    if (block.children) {
      const found = findBlockById(block.children, id);
      if (found) return found;
    }
  }
  return null;
}
