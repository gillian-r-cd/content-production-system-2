// frontend/app/workspace/page.tsx
// 功能: 内容生产工作台主页面
// 主要组件: WorkspacePage

"use client";

import { useState, useEffect, useRef } from "react";
import { WorkspaceLayout } from "@/components/layout/workspace-layout";
import { ProgressPanel } from "@/components/progress-panel";
import { ContentPanel } from "@/components/content-panel";
import { AgentPanel } from "@/components/agent-panel";
import { CreateProjectModal } from "@/components/create-project-modal";
import { projectAPI, fieldAPI, agentAPI } from "@/lib/api";
import type { Project, Field, ContentBlock } from "@/lib/api";
import { Copy, Trash2, ChevronDown, CheckSquare, Square, X } from "lucide-react";

export default function WorkspacePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [fields, setFields] = useState<Field[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);  // 用于触发子组件刷新
  const [selectedBlock, setSelectedBlock] = useState<ContentBlock | null>(null); // 树形视图选中的内容块
  const [allBlocks, setAllBlocks] = useState<ContentBlock[]>([]); // 所有内容块（用于依赖选择）
  const [showProjectMenu, setShowProjectMenu] = useState(false); // 项目下拉菜单
  const projectMenuRef = useRef<HTMLDivElement>(null);
  
  // 批量选择相关状态
  const [isBatchMode, setIsBatchMode] = useState(false);
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (projectMenuRef.current && !projectMenuRef.current.contains(e.target as Node)) {
        setShowProjectMenu(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // 加载项目列表
  useEffect(() => {
    loadProjects();
  }, []);

  // 加载当前项目的字段 & 记住选中项目
  useEffect(() => {
    if (currentProject) {
      loadFields(currentProject.id);
      localStorage.setItem("lastProjectId", currentProject.id);
    }
  }, [currentProject?.id]);

  const loadProjects = async () => {
    try {
      const data = await projectAPI.list();
      setProjects(data);
      
      // 恢复上次选中的项目，或自动选择第一个
      if (data.length > 0 && !currentProject) {
        const savedId = localStorage.getItem("lastProjectId");
        const saved = savedId ? data.find((p: Project) => p.id === savedId) : null;
        setCurrentProject(saved || data[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载项目失败");
    } finally {
      setLoading(false);
    }
  };

  const loadFields = async (projectId: string) => {
    try {
      const data = await fieldAPI.listByProject(projectId);
      setFields(data);
    } catch (err) {
      console.error("加载字段失败:", err);
    }
  };

  const handlePhaseClick = (phase: string) => {
    if (currentProject) {
      setCurrentProject({
        ...currentProject,
        current_phase: phase,
      });
    }
  };

  const handlePhaseReorder = async (newPhaseOrder: string[]) => {
    if (!currentProject) return;
    
    try {
      // 更新本地状态
      setCurrentProject({
        ...currentProject,
        phase_order: newPhaseOrder,
      });
      
      // 保存到服务器
      await projectAPI.update(currentProject.id, { phase_order: newPhaseOrder });
    } catch (err) {
      console.error("更新阶段顺序失败:", err);
    }
  };

  const handleAutonomyChange = async (autonomy: Record<string, boolean>) => {
    if (!currentProject) return;
    
    try {
      // 更新本地状态
      setCurrentProject({
        ...currentProject,
        agent_autonomy: autonomy,
      });
      
      // 保存到服务器
      await projectAPI.update(currentProject.id, { agent_autonomy: autonomy });
    } catch (err) {
      console.error("更新自主权设置失败:", err);
    }
  };

  const handleFieldUpdate = async (fieldId: string, content: string) => {
    try {
      await fieldAPI.update(fieldId, { content });
      // 重新加载字段
      if (currentProject) {
        loadFields(currentProject.id);
      }
    } catch (err) {
      console.error("更新字段失败:", err);
    }
  };

  const handleSendMessage = async (message: string): Promise<string> => {
    if (!currentProject) {
      throw new Error("请先选择项目");
    }

    const response = await agentAPI.chat(
      currentProject.id,
      message,
      { currentPhase: currentProject.current_phase }
    );

    // 完整更新项目状态（phase_status + current_phase）
    if (response.phase_status || response.phase) {
      setCurrentProject({
        ...currentProject,
        phase_status: response.phase_status || currentProject.phase_status,
        current_phase: response.phase || currentProject.current_phase,
      });
    }

    // 重新加载字段
    loadFields(currentProject.id);

    return response.message;
  };

  const handleBlockSelect = (block: ContentBlock) => {
    setSelectedBlock(block);
    console.log("选中内容块:", block.name, block.block_type);
  };

  // 当 allBlocks 更新时，同步更新 selectedBlock 的内容（保持数据同步）
  useEffect(() => {
    if (selectedBlock && allBlocks.length > 0) {
      // 递归查找匹配的 block
      const findBlock = (blocks: ContentBlock[], id: string): ContentBlock | null => {
        for (const block of blocks) {
          if (block.id === id) return block;
          if (block.children) {
            const found = findBlock(block.children, id);
            if (found) return found;
          }
        }
        return null;
      };
      
      const updatedBlock = findBlock(allBlocks, selectedBlock.id);
      if (updatedBlock && JSON.stringify(updatedBlock) !== JSON.stringify(selectedBlock)) {
        setSelectedBlock(updatedBlock);
      }
    }
  }, [allBlocks]);

  const handleCreateProject = () => {
    setShowCreateModal(true);
  };

  const handleProjectCreated = (project: Project) => {
    setProjects([...projects, project]);
    setCurrentProject(project);
  };

  const handleDuplicateProject = async (projectId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const duplicated = await projectAPI.duplicate(projectId);
      setProjects([...projects, duplicated]);
      setCurrentProject(duplicated);
      setShowProjectMenu(false);
    } catch (err) {
      console.error("复制项目失败:", err);
      setError("复制项目失败");
    }
  };

  const handleDeleteProject = async (projectId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定删除此项目？此操作将删除项目的所有数据，包括字段和对话记录。")) return;
    
    try {
      await projectAPI.delete(projectId);
      const newProjects = projects.filter(p => p.id !== projectId);
      setProjects(newProjects);
      if (currentProject?.id === projectId) {
        setCurrentProject(newProjects[0] || null);
      }
      setShowProjectMenu(false);
    } catch (err) {
      console.error("删除项目失败:", err);
      setError("删除项目失败");
    }
  };

  // 批量选择相关函数
  const toggleProjectSelection = (projectId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const newSelected = new Set(selectedProjectIds);
    if (newSelected.has(projectId)) {
      newSelected.delete(projectId);
    } else {
      newSelected.add(projectId);
    }
    setSelectedProjectIds(newSelected);
  };

  const toggleSelectAll = () => {
    if (selectedProjectIds.size === projects.length) {
      setSelectedProjectIds(new Set());
    } else {
      setSelectedProjectIds(new Set(projects.map(p => p.id)));
    }
  };

  const exitBatchMode = () => {
    setIsBatchMode(false);
    setSelectedProjectIds(new Set());
  };

  const handleBatchDelete = async () => {
    if (selectedProjectIds.size === 0) return;
    
    const count = selectedProjectIds.size;
    if (!confirm(`确定删除选中的 ${count} 个项目？此操作将删除所有选中项目的数据，包括字段和对话记录。`)) return;
    
    setIsDeleting(true);
    try {
      // 逐个删除
      const deletePromises = Array.from(selectedProjectIds).map(id => 
        projectAPI.delete(id).catch(err => {
          console.error(`删除项目 ${id} 失败:`, err);
          return null; // 失败的返回 null
        })
      );
      
      await Promise.all(deletePromises);
      
      // 更新项目列表
      const newProjects = projects.filter(p => !selectedProjectIds.has(p.id));
      setProjects(newProjects);
      
      // 如果当前项目被删除，切换到第一个项目
      if (currentProject && selectedProjectIds.has(currentProject.id)) {
        setCurrentProject(newProjects[0] || null);
      }
      
      // 退出批量模式
      exitBatchMode();
    } catch (err) {
      console.error("批量删除失败:", err);
      setError("批量删除失败");
    } finally {
      setIsDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-surface-0">
        <div className="text-zinc-400">加载中...</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      {/* 顶部导航 */}
      <header className="h-14 flex-shrink-0 border-b border-surface-3 bg-surface-1 flex items-center justify-between px-4">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold bg-gradient-to-r from-brand-400 to-brand-600 bg-clip-text text-transparent">
            内容生产系统
          </h1>
          
          {/* 项目选择器（带复制/删除功能） */}
          <div className="relative" ref={projectMenuRef}>
            <button
              onClick={() => setShowProjectMenu(!showProjectMenu)}
              className="flex items-center gap-2 px-3 py-1.5 bg-surface-2 border border-surface-3 rounded-lg text-sm text-zinc-200 hover:border-surface-4 min-w-[200px] justify-between"
            >
              <span className="truncate">
                {currentProject ? `${currentProject.name} (v${currentProject.version})` : "选择项目"}
              </span>
              <ChevronDown className="w-4 h-4 text-zinc-400" />
            </button>
            
            {showProjectMenu && (
              <div className="absolute top-full left-0 mt-1 w-96 bg-surface-1 border border-surface-3 rounded-lg shadow-xl z-50 overflow-hidden">
                {/* 顶部操作栏 */}
                <div className="px-3 py-2 border-b border-surface-3 flex items-center justify-between bg-surface-2">
                  {isBatchMode ? (
                    <>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={toggleSelectAll}
                          className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200"
                        >
                          {selectedProjectIds.size === projects.length ? (
                            <CheckSquare className="w-4 h-4 text-brand-400" />
                          ) : (
                            <Square className="w-4 h-4" />
                          )}
                          全选
                        </button>
                        <span className="text-xs text-zinc-500">
                          已选 {selectedProjectIds.size} / {projects.length}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleBatchDelete}
                          disabled={selectedProjectIds.size === 0 || isDeleting}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          {isDeleting ? "删除中..." : "批量删除"}
                        </button>
                        <button
                          onClick={exitBatchMode}
                          className="p-1 text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded"
                          title="退出批量模式"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <span className="text-xs text-zinc-500">{projects.length} 个项目</span>
                      <button
                        onClick={() => setIsBatchMode(true)}
                        className="text-xs text-zinc-400 hover:text-zinc-200"
                        disabled={projects.length === 0}
                      >
                        批量管理
                      </button>
                    </>
                  )}
                </div>
                
                {/* 项目列表 */}
                <div className="max-h-72 overflow-y-auto py-1">
                  {projects.length === 0 ? (
                    <div className="px-3 py-4 text-sm text-zinc-500 text-center">暂无项目</div>
                  ) : (
                    projects.map((p) => (
                      <div
                        key={p.id}
                        className={`flex items-center gap-2 px-3 py-2 hover:bg-surface-2 cursor-pointer group ${
                          !isBatchMode && currentProject?.id === p.id ? "bg-brand-600/10" : ""
                        } ${isBatchMode && selectedProjectIds.has(p.id) ? "bg-brand-600/10" : ""}`}
                        onClick={(e) => {
                          if (isBatchMode) {
                            toggleProjectSelection(p.id, e);
                          } else {
                            setCurrentProject(p);
                            setShowProjectMenu(false);
                          }
                        }}
                      >
                        {/* 批量选择复选框 */}
                        {isBatchMode && (
                          <div className="flex-shrink-0">
                            {selectedProjectIds.has(p.id) ? (
                              <CheckSquare className="w-4 h-4 text-brand-400" />
                            ) : (
                              <Square className="w-4 h-4 text-zinc-500" />
                            )}
                          </div>
                        )}
                        
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-zinc-200 truncate">{p.name}</div>
                          <div className="text-xs text-zinc-500">v{p.version}</div>
                        </div>
                        
                        {/* 单项操作按钮（非批量模式） */}
                        {!isBatchMode && (
                          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button
                              onClick={(e) => handleDuplicateProject(p.id, e)}
                              className="p-1.5 hover:bg-surface-3 rounded text-zinc-400 hover:text-brand-400"
                              title="复制项目"
                            >
                              <Copy className="w-4 h-4" />
                            </button>
                            <button
                              onClick={(e) => handleDeleteProject(p.id, e)}
                              className="p-1.5 hover:bg-surface-3 rounded text-zinc-400 hover:text-red-400"
                              title="删除项目"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
          
          <button
            onClick={handleCreateProject}
            className="px-3 py-1.5 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors"
          >
            + 新建项目
          </button>
        </div>

        <div className="flex items-center gap-4">
          <a
            href="/settings"
            className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            后台设置
          </a>
        </div>
      </header>

      {/* 三栏布局 */}
      <div className="flex-1 overflow-hidden">
        <WorkspaceLayout
          leftPanel={
            <ProgressPanel
              project={currentProject}
              fields={fields}
              onPhaseClick={handlePhaseClick}
              onPhaseReorder={handlePhaseReorder}
              onAutonomyChange={handleAutonomyChange}
              onBlockSelect={handleBlockSelect}
              onBlocksChange={setAllBlocks}
              onProjectChange={async () => {
                // 刷新项目数据（获取最新的 use_flexible_architecture 等）
                if (currentProject) {
                  const updatedProject = await projectAPI.get(currentProject.id);
                  setCurrentProject(updatedProject);
                }
              }}
            />
          }
          centerPanel={
            <ContentPanel
              projectId={currentProject?.id || null}
              currentPhase={currentProject?.current_phase || "intent"}
              phaseStatus={currentProject?.phase_status || {}}
              fields={fields}
              selectedBlock={selectedBlock}
              allBlocks={allBlocks}
              useFlexibleArchitecture={currentProject?.use_flexible_architecture || false}
              onFieldUpdate={handleFieldUpdate}
              onFieldsChange={() => currentProject && loadFields(currentProject.id)}
              onBlockSelect={handleBlockSelect}
              onPhaseAdvance={async () => {
                // 阶段推进后，刷新项目、字段和对话历史
                if (currentProject) {
                  const updatedProject = await projectAPI.get(currentProject.id);
                  setCurrentProject(updatedProject);
                  await loadFields(currentProject.id);
                  // 触发右侧面板刷新（通过重新渲染 AgentPanel）
                  setRefreshKey(prev => prev + 1);
                }
              }}
            />
          }
          rightPanel={
            <AgentPanel
              key={refreshKey}  // 触发刷新
              projectId={currentProject?.id || null}
              fields={fields}
              onSendMessage={handleSendMessage}
              onContentUpdate={async () => {
                // Agent生成内容后，刷新字段和项目状态
                if (currentProject) {
                  await loadFields(currentProject.id);
                  // 重新加载项目以获取最新的phase_status
                  const updatedProject = await projectAPI.get(currentProject.id);
                  setCurrentProject(updatedProject);
                }
              }}
            />
          }
        />
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="fixed bottom-4 right-4 px-4 py-2 bg-red-600 text-white rounded-lg">
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-2 text-red-200 hover:text-white"
          >
            ✕
          </button>
        </div>
      )}

      {/* 创建项目对话框 */}
      <CreateProjectModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={handleProjectCreated}
      />
    </div>
  );
}

