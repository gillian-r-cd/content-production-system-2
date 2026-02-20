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
import { GlobalSearchModal } from "@/components/global-search-modal";
import { projectAPI } from "@/lib/api";
import { requestNotificationPermission } from "@/lib/utils";
import type { Project, ContentBlock } from "@/lib/api";
import { Copy, Trash2, ChevronDown, CheckSquare, Square, X, Download, Upload, Search } from "lucide-react";

export default function WorkspacePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  // P0-1: fields state 已移除，统一使用 allBlocks (ContentBlock)
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);  // 用于触发子组件刷新
  const [blocksRefreshKey, setBlocksRefreshKey] = useState(0); // 用于触发 ContentBlocks 刷新
  const [selectedBlock, setSelectedBlock] = useState<ContentBlock | null>(null); // 树形视图选中的内容块
  const [allBlocks, setAllBlocks] = useState<ContentBlock[]>([]); // 所有内容块（用于依赖选择）
  const [showProjectMenu, setShowProjectMenu] = useState(false); // 项目下拉菜单
  const projectMenuRef = useRef<HTMLDivElement>(null);
  const importFileRef = useRef<HTMLInputElement>(null);
  
  // 批量选择相关状态
  const [isBatchMode, setIsBatchMode] = useState(false);
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);
  
  // 全局搜索
  const [showSearch, setShowSearch] = useState(false);
  
  // M3: Eval 诊断→Agent 修改桥接（中栏组件设置消息，右栏 AgentPanel 消费）
  const [pendingAgentMessage, setPendingAgentMessage] = useState<string | null>(null);

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

  // 全局搜索快捷键 Cmd/Ctrl+Shift+F
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === "f") {
        e.preventDefault();
        if (currentProject) {
          setShowSearch(true);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentProject]);

  // 加载项目列表 + 请求通知权限
  useEffect(() => {
    loadProjects();
    requestNotificationPermission();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 项目切换时：记住选中项目 & 重置工作区状态
  // 原则：项目是数据隔离的最高边界，切换项目 = 重置一切工作区状态
  useEffect(() => {
    if (currentProject) {
      localStorage.setItem("lastProjectId", currentProject.id);
    }
    // 清除旧项目残留状态 —— 新项目的数据会由各自的 useEffect 重新加载
    setSelectedBlock(null);
    setAllBlocks([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const handlePhaseClick = (phase: string) => {
    if (currentProject) {
      setCurrentProject({
        ...currentProject,
        current_phase: phase,
      });
      // 清除 selectedBlock，让 ContentPanel 显示阶段的完整内容视图
      setSelectedBlock(null);
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
      console.error("更新组顺序失败:", err);
    }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    if (!confirm("确定删除此项目？此操作将删除项目的所有数据，包括内容块和对话记录。")) return;
    
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
    if (!confirm(`确定删除选中的 ${count} 个项目？此操作将删除所有选中项目的数据，包括内容块和对话记录。`)) return;
    
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

  // ============== 项目导出 ==============
  const handleExportProject = async (projectId: string, projectName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const data = await projectAPI.exportProject(projectId, false);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${projectName}_export_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setShowProjectMenu(false);
    } catch (err) {
      console.error("导出项目失败:", err);
      setError("导出项目失败");
    }
  };

  // ============== 项目导入 ==============
  const handleImportProject = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const data = JSON.parse(text);

      if (!data.project) {
        setError("无效的项目导出文件：缺少 project 数据");
        return;
      }

      const result = await projectAPI.importProject(data, true);
      // 刷新项目列表并选中新导入的项目
      const updatedProjects = await projectAPI.list();
      setProjects(updatedProjects);
      if (result.project) {
        setCurrentProject(result.project);
      }
      setShowProjectMenu(false);
      alert(`✅ ${result.message}\n\n导入统计:\n• 内容块: ${result.stats.content_blocks}\n• 内容块: ${result.stats.project_fields}\n• 对话记录: ${result.stats.chat_messages}\n• 版本历史: ${result.stats.content_versions}\n• 模拟记录: ${result.stats.simulation_records}\n• 评估运行: ${result.stats.eval_runs}\n• 生成日志: ${result.stats.generation_logs}`);
    } catch (err) {
      console.error("导入项目失败:", err);
      setError(err instanceof Error ? `导入失败: ${err.message}` : "导入项目失败");
    } finally {
      // 重置文件输入
      if (importFileRef.current) {
        importFileRef.current.value = "";
      }
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
                              onClick={(e) => handleExportProject(p.id, p.name, e)}
                              className="p-1.5 hover:bg-surface-3 rounded text-zinc-400 hover:text-green-400"
                              title="导出项目"
                            >
                              <Download className="w-4 h-4" />
                            </button>
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
          <button
            onClick={() => importFileRef.current?.click()}
            className="px-3 py-1.5 text-sm bg-surface-2 hover:bg-surface-3 border border-surface-3 rounded-lg transition-colors flex items-center gap-1.5 text-zinc-300"
            title="从JSON文件导入项目"
          >
            <Upload className="w-3.5 h-3.5" />
            导入项目
          </button>
          <input
            ref={importFileRef}
            type="file"
            accept=".json"
            className="hidden"
            onChange={handleImportProject}
          />
        </div>

        <div className="flex items-center gap-4">
          {currentProject && (
            <button
              onClick={() => setShowSearch(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors"
              title="全局搜索替换 (⌘⇧F)"
            >
              <Search className="w-3.5 h-3.5" />
              搜索
            </button>
          )}
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
              blocksRefreshKey={blocksRefreshKey}
              onPhaseClick={handlePhaseClick}
              onPhaseReorder={handlePhaseReorder}
              onBlockSelect={handleBlockSelect}
              onBlocksChange={setAllBlocks}
              onProjectChange={async () => {
                // 刷新项目数据
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
              selectedBlock={selectedBlock}
              allBlocks={allBlocks}
              onFieldsChange={() => {
                if (currentProject) {
                  // 刷新 ContentBlocks（确保树形视图和内容面板同步）
                  setBlocksRefreshKey(prev => prev + 1);
                }
              }}
              onBlockSelect={handleBlockSelect}
              onPhaseAdvance={async () => {
                // 阶段推进后，刷新项目和对话历史
                if (currentProject) {
                  const updatedProject = await projectAPI.get(currentProject.id);
                  setCurrentProject(updatedProject);
                  // ===== 关键修复：切换 selectedBlock 到新组的虚拟块 =====
                  // 防止停留在旧阶段的选中状态导致视觉上"跳过"新组
                  const newPhase = updatedProject.current_phase;
                  setSelectedBlock({
                    id: `virtual_phase_${newPhase}`,
                    project_id: currentProject.id,
                    parent_id: null,
                    name: newPhase,
                    block_type: "phase",
                    depth: 0,
                    content: "",
                    status: "in_progress",
                    ai_prompt: "",
                    depends_on: [],
                    special_handler: newPhase,
                    pre_questions: [],
                    pre_answers: {},
                    need_review: false,
                    is_collapsed: false,
                    order_index: 0,
                    children: [],
                    created_at: null,
                    updated_at: null,
                  } as ContentBlock);
                  // 触发右侧面板刷新（通过重新渲染 AgentPanel）
                  setRefreshKey(prev => prev + 1);
                  // 同时刷新 ContentBlocks 树
                  setBlocksRefreshKey(prev => prev + 1);
                }
              }}
              onSendToAgent={setPendingAgentMessage}
            />
          }
          rightPanel={
            <AgentPanel
              key={`${currentProject?.id || "none"}-${refreshKey}`}  // 项目切换时销毁重建，refreshKey 保留阶段推进刷新
              projectId={currentProject?.id || null}
              currentPhase={currentProject?.current_phase}
              allBlocks={allBlocks}
              onContentUpdate={async () => {
                // Agent生成内容后，刷新内容块和项目状态
                if (currentProject) {
                  const updatedProject = await projectAPI.get(currentProject.id);
                  setCurrentProject(updatedProject);
                  setBlocksRefreshKey(prev => prev + 1);
                }
              }}
              externalMessage={pendingAgentMessage}
              onExternalMessageConsumed={() => setPendingAgentMessage(null)}
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

      {/* 全局搜索替换 */}
      {currentProject && (
        <GlobalSearchModal
          projectId={currentProject.id}
          open={showSearch}
          onClose={() => setShowSearch(false)}
          onNavigateToField={(fieldId) => {
            // P0-1: 统一通过 allBlocks 定位内容块
            const findBlockRecursive = (blocks: ContentBlock[], id: string): ContentBlock | null => {
              for (const b of blocks) {
                if (b.id === id) return b;
                if (b.children) {
                  const found = findBlockRecursive(b.children, id);
                  if (found) return found;
                }
              }
              return null;
            };
            const block = findBlockRecursive(allBlocks, fieldId);
            if (block) {
              setSelectedBlock(block);
            }
            setShowSearch(false);
          }}
          onContentUpdate={() => {
            setRefreshKey(prev => prev + 1);
            setBlocksRefreshKey(prev => prev + 1);
          }}
        />
      )}

      {/* P0-1: 版本警告弹窗已移除，版本管理统一在 ContentBlock 编辑器中处理 */}
    </div>
  );
}

