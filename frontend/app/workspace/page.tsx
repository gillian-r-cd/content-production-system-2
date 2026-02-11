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
import { projectAPI, fieldAPI, agentAPI } from "@/lib/api";
import { requestNotificationPermission } from "@/lib/utils";
import type { Project, Field, ContentBlock } from "@/lib/api";
import { Copy, Trash2, ChevronDown, CheckSquare, Square, X, Download, Upload, Search } from "lucide-react";

export default function WorkspacePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [fields, setFields] = useState<Field[]>([]);
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

  // 版本警告状态
  const [fieldVersionWarning, setFieldVersionWarning] = useState<string | null>(null);
  const [fieldAffectedNames, setFieldAffectedNames] = useState<string[] | null>(null);

  const handleFieldUpdate = async (fieldId: string, content: string) => {
    try {
      const result = await fieldAPI.update(fieldId, { content });
      // 重新加载字段
      if (currentProject) {
        loadFields(currentProject.id);
      }
      // 检查版本警告
      if (result?.version_warning) {
        setFieldVersionWarning(result.version_warning);
        setFieldAffectedNames(result.affected_fields || null);
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
        setError("无效的项目导出文件：缺少 project 字段");
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
      alert(`✅ ${result.message}\n\n导入统计:\n• 内容块: ${result.stats.content_blocks}\n• 字段: ${result.stats.project_fields}\n• 对话记录: ${result.stats.chat_messages}\n• 版本历史: ${result.stats.content_versions}\n• 模拟记录: ${result.stats.simulation_records}\n• 评估运行: ${result.stats.eval_runs}\n• 生成日志: ${result.stats.generation_logs}`);
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
              fields={fields}
              blocksRefreshKey={blocksRefreshKey}
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
              onFieldsChange={() => {
                if (currentProject) {
                  loadFields(currentProject.id);
                  // 同时刷新 ContentBlocks（确保树形视图和内容面板同步）
                  setBlocksRefreshKey(prev => prev + 1);
                }
              }}
              onBlockSelect={handleBlockSelect}
              onPhaseAdvance={async () => {
                // 阶段推进后，刷新项目、字段和对话历史
                if (currentProject) {
                  const updatedProject = await projectAPI.get(currentProject.id);
                  setCurrentProject(updatedProject);
                  await loadFields(currentProject.id);
                  // ===== 关键修复：切换 selectedBlock 到新阶段的虚拟块 =====
                  // 防止停留在旧阶段的选中状态导致视觉上"跳过"新阶段
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
                    constraints: {},
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
            />
          }
          rightPanel={
            <AgentPanel
              key={refreshKey}  // 触发刷新
              projectId={currentProject?.id || null}
              currentPhase={currentProject?.current_phase}
              fields={fields}
              allBlocks={allBlocks}
              useFlexibleArchitecture={currentProject?.use_flexible_architecture || false}
              onSendMessage={handleSendMessage}
              onContentUpdate={async () => {
                // Agent生成内容后，刷新字段、内容块和项目状态
                if (currentProject) {
                  await loadFields(currentProject.id);
                  // 重新加载项目以获取最新的phase_status
                  const updatedProject = await projectAPI.get(currentProject.id);
                  setCurrentProject(updatedProject);
                  // 刷新内容块（灵活架构）
                  setBlocksRefreshKey(prev => prev + 1);
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

      {/* 全局搜索替换 */}
      {currentProject && (
        <GlobalSearchModal
          projectId={currentProject.id}
          open={showSearch}
          onClose={() => setShowSearch(false)}
          onNavigateToField={(fieldId, fieldType) => {
            // 定位到字段：如果是 block，通过 allBlocks 找到并选中
            if (fieldType === "block") {
              const block = allBlocks.find(b => b.id === fieldId);
              if (block) {
                setSelectedBlock(block);
              }
            } else {
              // 对于 ProjectField，找到对应的阶段并触发 phase click
              const field = fields.find(f => f.id === fieldId);
              if (field && field.phase) {
                handlePhaseClick(field.phase);
              }
            }
            setShowSearch(false);
          }}
          onContentUpdate={() => {
            setRefreshKey(prev => prev + 1);
            setBlocksRefreshKey(prev => prev + 1);
            if (currentProject) loadFields(currentProject.id);
          }}
        />
      )}

      {/* 版本警告弹窗（字段更新触发） */}
      {fieldVersionWarning && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-surface-1 border border-surface-3 rounded-xl shadow-2xl max-w-md w-full mx-4">
            <div className="px-5 py-4 border-b border-surface-3">
              <h3 className="text-base font-semibold text-amber-400 flex items-center gap-2">
                ⚠️ 上游内容变更提醒
              </h3>
            </div>
            <div className="p-5 space-y-3">
              <p className="text-sm text-zinc-300">{fieldVersionWarning}</p>
              {fieldAffectedNames && fieldAffectedNames.length > 0 && (
                <div className="bg-surface-2 rounded-lg p-3">
                  <p className="text-xs text-zinc-400 mb-2">受影响的字段：</p>
                  <ul className="space-y-1">
                    {fieldAffectedNames.map((name, i) => (
                      <li key={i} className="text-sm text-amber-300 flex items-center gap-1.5">
                        <span className="text-amber-400">•</span> {name}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-xs text-zinc-500">
                建议：您可以选择创建新版本来保留修改前的内容，
                或关闭此提示并手动重新生成受影响的字段。
              </p>
            </div>
            <div className="px-5 py-4 border-t border-surface-3 flex justify-end gap-3">
              <button
                onClick={() => { setFieldVersionWarning(null); setFieldAffectedNames(null); }}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 bg-surface-2 hover:bg-surface-3 rounded-lg transition-colors"
              >
                知道了，稍后处理
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

