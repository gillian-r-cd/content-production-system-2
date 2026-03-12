// frontend/app/workspace/page.tsx
// 功能: 内容生产工作台主页面
// 主要组件: WorkspacePage
// 主要数据结构: ProjectFamily（按 parent_version_id 链分组的版本族谱）
// 版本管理: 项目选择器按版本族分组渲染，支持展开/折叠历史版本，支持创建新版本

"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { WorkspaceLayout } from "@/components/layout/workspace-layout";
import { ProgressPanel } from "@/components/progress-panel";
import { ContentPanel } from "@/components/content-panel";
import { AgentPanel } from "@/components/agent-panel";
import { CreateProjectModal } from "@/components/create-project-modal";
import { GlobalSearchModal } from "@/components/global-search-modal";
import { ProjectAutoSplitModal } from "@/components/project-auto-split-modal";
import { projectAPI, startAllReadyBlocks } from "@/lib/api";
import { formatProjectText, normalizeProjectLocale, persistClientLocale, projectUiText, resolveClientLocale } from "@/lib/project-locale";
import { requestNotificationPermission } from "@/lib/utils";
import type { Project, ContentBlock, AgentSelectionRef } from "@/lib/api";
import { Copy, Trash2, ChevronDown, ChevronRight, CheckSquare, Square, X, Download, Upload, Search, Plus, History } from "lucide-react";

// ===== 版本族谱分组 =====
// 将扁平的项目列表按 parent_version_id 链分组为版本族
interface ProjectFamily {
  rootId: string;       // 族谱根项目 ID（version 最小的那个）
  name: string;         // 项目名称（取最新版本的名称）
  latest: Project;      // 最新版本
  versions: Project[];  // 所有版本，按 version 降序
}

function groupProjectsByFamily(projects: Project[]): ProjectFamily[] {
  if (projects.length === 0) return [];

  // 建立 id → project 映射
  const byId = new Map<string, Project>();
  for (const p of projects) byId.set(p.id, p);

  // 检查是否有任何项目有 parent_version_id（用于判断是否需要 fallback）
  const hasParentLinks = projects.some(p => p.parent_version_id !== null);

  // 按族谱分组的映射：key → project[]
  const familyMap = new Map<string, Project[]>();

  if (hasParentLinks) {
    // 优先使用 parent_version_id 链分组
    const rootCache = new Map<string, string>();
    function findRoot(pid: string): string {
      if (rootCache.has(pid)) return rootCache.get(pid)!;
      const p = byId.get(pid);
      if (!p || !p.parent_version_id || !byId.has(p.parent_version_id)) {
        rootCache.set(pid, pid);
        return pid;
      }
      const root = findRoot(p.parent_version_id);
      rootCache.set(pid, root);
      return root;
    }

    for (const p of projects) {
      const root = findRoot(p.id);
      if (!familyMap.has(root)) familyMap.set(root, []);
      familyMap.get(root)!.push(p);
    }
  } else {
    // Fallback: 按项目名称分组（兼容旧数据，所有 parent_version_id 为 null 的情况）
    for (const p of projects) {
      if (!familyMap.has(p.name)) familyMap.set(p.name, []);
      familyMap.get(p.name)!.push(p);
    }
  }

  // 转换为 ProjectFamily 数组
  const families: ProjectFamily[] = [];
  for (const [key, members] of familyMap) {
    members.sort((a, b) => b.version - a.version);
    // rootId: 优先用版本最小的那个的 id，fallback 时用 name 作为 key 的替代
    const rootProject = members[members.length - 1]; // version 最小的
    families.push({
      rootId: hasParentLinks ? key : rootProject.id,
      name: members[0].name,  // 最新版本的名称
      latest: members[0],
      versions: members,
    });
  }

  // 按最新版本的更新时间降序排列
  families.sort((a, b) => {
    const ta = new Date(a.latest.updated_at || a.latest.created_at).getTime();
    const tb = new Date(b.latest.updated_at || b.latest.created_at).getTime();
    return tb - ta;
  });

  return families;
}

export default function WorkspacePage() {
  const [browserLocale, setBrowserLocale] = useState<"zh-CN" | "ja-JP" | null>(null);
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
  
  // 版本分组: 展开的族谱 root ID 集合
  const [expandedFamilies, setExpandedFamilies] = useState<Set<string>>(new Set());
  // 版本分组: 新建版本备注输入（正在创建版本的项目 ID）
  const [creatingVersionForId, setCreatingVersionForId] = useState<string | null>(null);
  const [versionNote, setVersionNote] = useState("");
  
  // 全局搜索
  const [showSearch, setShowSearch] = useState(false);
  const [showAutoSplitModal, setShowAutoSplitModal] = useState(false);
  const [isStartAllReadyRunning, setIsStartAllReadyRunning] = useState(false);
  
  // M3: Eval 诊断→Agent 修改桥接（中栏组件设置消息，右栏 AgentPanel 消费）
  const [pendingAgentMessage, setPendingAgentMessage] = useState<string | null>(null);

  // B: 选中文字→Agent Panel 引用上下文
  const [pendingAgentSelection, setPendingAgentSelection] = useState<AgentSelectionRef | null>(null);
  // Workspace UI 必须优先跟随当前项目语言；只有未进入项目时才回退到客户端记住的 locale。
  const uiLocale = normalizeProjectLocale(currentProject?.locale || browserLocale || "zh-CN");
  const t = projectUiText(uiLocale);

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

  useEffect(() => {
    setBrowserLocale(resolveClientLocale());
  }, []);

  useEffect(() => {
    if (!currentProject?.locale && !browserLocale) return;
    const persistedLocale = persistClientLocale(uiLocale);
    if (browserLocale !== persistedLocale) {
      setBrowserLocale(persistedLocale);
    }
    document.title = t.systemName;
  }, [browserLocale, currentProject?.locale, t.systemName, uiLocale]);

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

  // “开始所有已就绪内容块”是长请求；在请求进行中轮询刷新左侧树，确保状态点尽快切到 in_progress。
  useEffect(() => {
    if (!isStartAllReadyRunning || !currentProject?.id) {
      return;
    }

    setBlocksRefreshKey(prev => prev + 1);
    const intervalId = window.setInterval(() => {
      setBlocksRefreshKey(prev => prev + 1);
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [isStartAllReadyRunning, currentProject?.id]);

  const syncProjectList = useCallback((nextProjects: Project[], preferredCurrentProjectId?: string | null) => {
    setProjects(nextProjects);
    setCurrentProject(() => {
      if (nextProjects.length === 0) {
        return null;
      }

      if (preferredCurrentProjectId !== undefined) {
        if (!preferredCurrentProjectId) {
          return nextProjects[0];
        }
        return nextProjects.find((project) => project.id === preferredCurrentProjectId) || nextProjects[0];
      }

      const savedId = localStorage.getItem("lastProjectId");
      return (savedId ? nextProjects.find((project) => project.id === savedId) : null) || nextProjects[0];
    });
  }, []);

  const loadProjects = useCallback(async () => {
    try {
      const data = await projectAPI.list();
      syncProjectList(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.loadingProjectsFailed);
    } finally {
      setLoading(false);
    }
  }, [syncProjectList, t.loadingProjectsFailed]);

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
      setError(t.duplicateProjectFailed);
    }
  };

  const handleDeleteProject = useCallback(async (projectId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(t.deleteProjectConfirm)) return;
    
    try {
      await projectAPI.delete(projectId);
      const updatedProjects = await projectAPI.list();
      const nextCurrentProjectId = currentProject?.id === projectId ? null : currentProject?.id || null;
      syncProjectList(updatedProjects, nextCurrentProjectId);
      setShowProjectMenu(false);
    } catch (err) {
      console.error("删除项目失败:", err);
      setError(t.deleteProjectFailed);
    }
  }, [currentProject?.id, syncProjectList, t.deleteProjectConfirm, t.deleteProjectFailed]);

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
    if (!confirm(formatProjectText(t.batchDeleteConfirm, { count }))) return;
    
    setIsDeleting(true);
    try {
      const targetIds = Array.from(selectedProjectIds);
      const result = await projectAPI.batchDelete(targetIds);
      const deletedIdSet = new Set(result.deleted_ids);
      const updatedProjects = await projectAPI.list();
      const nextCurrentProjectId = currentProject && !deletedIdSet.has(currentProject.id)
        ? currentProject.id
        : null;
      syncProjectList(updatedProjects, nextCurrentProjectId);
      exitBatchMode();
      setShowProjectMenu(false);
    } catch (err) {
      console.error("批量删除失败:", err);
      setError(err instanceof Error ? `${t.batchDeleteFailed}: ${err.message}` : t.batchDeleteFailed);
    } finally {
      setIsDeleting(false);
    }
  };

  // ============== 创建项目新版本 ==============
  const handleCreateVersion = async (projectId: string) => {
    const localeTag = normalizeProjectLocale(uiLocale);
    const timeText = new Date().toLocaleString(localeTag, { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
    const note = versionNote.trim() || formatProjectText(t.snapshotNote, { time: timeText });
    try {
      const newVersion = await projectAPI.createVersion(projectId, note);
      // 新版本加入列表并切换过去
      setProjects(prev => [...prev, newVersion]);
      setCurrentProject(newVersion);
      setCreatingVersionForId(null);
      setVersionNote("");
    } catch (err) {
      console.error("创建版本失败:", err);
      setError(`${t.createVersionFailed}: ${err instanceof Error ? err.message : t.unknownError}`);
    }
  };

  // ============== 版本族谱展开/折叠 ==============
  const toggleFamilyExpand = (rootId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedFamilies(prev => {
      const next = new Set(prev);
      if (next.has(rootId)) {
        next.delete(rootId);
      } else {
        next.add(rootId);
      }
      return next;
    });
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
      setError(t.exportProjectFailed);
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
        setError(t.invalidImportFile);
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
      alert(
        `✅ ${result.message}\n\n${t.importSummaryTitle}:\n• ${t.importContentBlocks}: ${result.stats.content_blocks}\n• ${t.importProjectFields}: ${result.stats.project_fields}\n• ${t.importChatMessages}: ${result.stats.chat_messages}\n• ${t.importContentVersions}: ${result.stats.content_versions}\n• ${t.importSimulationRecords}: ${result.stats.simulation_records}\n• ${t.importEvalRuns}: ${result.stats.eval_runs}\n• ${t.importGenerationLogs}: ${result.stats.generation_logs}`,
      );
    } catch (err) {
      console.error("导入项目失败:", err);
      setError(err instanceof Error ? `${t.importProjectFailed}: ${err.message}` : t.importProjectFailed);
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
        <div className="text-zinc-400">{t.loading}</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      {/* 顶部导航 */}
      <header className="h-14 flex-shrink-0 border-b border-surface-3 bg-surface-1 flex items-center justify-between px-4">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold bg-gradient-to-r from-brand-400 to-brand-600 bg-clip-text text-transparent">
            {t.systemName}
          </h1>
          
          {/* 项目选择器（带复制/删除功能） */}
          <div className="relative" ref={projectMenuRef}>
            <button
              onClick={() => {
                const next = !showProjectMenu;
                setShowProjectMenu(next);
                if (next) {
                  loadProjects().catch(console.error);
                }
              }}
              className="flex items-center gap-2 px-3 py-1.5 bg-surface-2 border border-surface-3 rounded-lg text-sm text-zinc-200 hover:border-surface-4 min-w-[200px] justify-between"
            >
              <span className="truncate">
                {currentProject ? `${currentProject.name} (v${currentProject.version})` : t.selectProject}
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
                          {t.selectAll}
                        </button>
                        <span className="text-xs text-zinc-500">
                          {formatProjectText(t.selectedCount, { selected: selectedProjectIds.size, total: projects.length })}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleBatchDelete}
                          disabled={selectedProjectIds.size === 0 || isDeleting}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          {isDeleting ? t.deleting : t.batchDelete}
                        </button>
                        <button
                          onClick={exitBatchMode}
                          className="p-1 text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded"
                          title={t.exitBatchMode}
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <span className="text-xs text-zinc-500">{formatProjectText(t.projectCount, { count: groupProjectsByFamily(projects).length })}</span>
                      <button
                        onClick={() => setIsBatchMode(true)}
                        className="text-xs text-zinc-400 hover:text-zinc-200"
                        disabled={projects.length === 0}
                      >
                        {t.batchManage}
                      </button>
                    </>
                  )}
                </div>
                
                {/* 项目列表 */}
                <div className="max-h-80 overflow-y-auto py-1">
                  {projects.length === 0 ? (
                    <div className="px-3 py-4 text-sm text-zinc-500 text-center">{t.noProjects}</div>
                  ) : isBatchMode ? (
                    /* 批量模式：扁平渲染所有项目（含版本） */
                    projects.map((p) => (
                      <div
                        key={p.id}
                        className={`flex items-center gap-2 px-3 py-2 hover:bg-surface-2 cursor-pointer ${
                          selectedProjectIds.has(p.id) ? "bg-brand-600/10" : ""
                        }`}
                        onClick={(e) => toggleProjectSelection(p.id, e)}
                      >
                        <div className="flex-shrink-0">
                          {selectedProjectIds.has(p.id) ? (
                            <CheckSquare className="w-4 h-4 text-brand-400" />
                          ) : (
                            <Square className="w-4 h-4 text-zinc-500" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-zinc-200 truncate">{p.name}</div>
                          <div className="text-xs text-zinc-500">v{p.version}</div>
                        </div>
                      </div>
                    ))
                  ) : (
                    /* 正常模式：按版本族分组渲染 */
                    groupProjectsByFamily(projects).map((family) => {
                      const isExpanded = expandedFamilies.has(family.rootId);
                      const hasMultipleVersions = family.versions.length > 1;
                      const isFamilyActive = family.versions.some(v => v.id === currentProject?.id);

                      return (
                        <div key={family.rootId}>
                          {/* 族谱主行（最新版本） */}
                          <div
                            className={`flex items-center gap-2 px-3 py-2 hover:bg-surface-2 cursor-pointer group ${
                              isFamilyActive ? "bg-brand-600/10" : ""
                            }`}
                            onClick={() => {
                              setCurrentProject(family.latest);
                              setShowProjectMenu(false);
                            }}
                          >
                            {/* 展开/折叠箭头 */}
                            {hasMultipleVersions ? (
                              <button
                                onClick={(e) => toggleFamilyExpand(family.rootId, e)}
                                className="flex-shrink-0 p-0.5 text-zinc-500 hover:text-zinc-300"
                              >
                                {isExpanded ? (
                                  <ChevronDown className="w-3.5 h-3.5" />
                                ) : (
                                  <ChevronRight className="w-3.5 h-3.5" />
                                )}
                              </button>
                            ) : (
                              <div className="flex-shrink-0 w-[18px]" />
                            )}

                            <div className="flex-1 min-w-0">
                              <div className="text-sm text-zinc-200 truncate">{family.name}</div>
                              <div className="text-xs text-zinc-500">
                                v{family.latest.version}
                                {hasMultipleVersions && !isExpanded && (
                                  <span className="ml-1.5 text-zinc-600">{formatProjectText(t.versionsCount, { count: family.versions.length })}</span>
                                )}
                              </div>
                            </div>

                            {/* 操作按钮 */}
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              <button
                                onClick={(e) => handleExportProject(family.latest.id, family.name, e)}
                                className="p-1.5 hover:bg-surface-3 rounded text-zinc-400 hover:text-green-400"
                                title={t.exportProjectTitle}
                              >
                                <Download className="w-4 h-4" />
                              </button>
                              <button
                                onClick={(e) => handleDuplicateProject(family.latest.id, e)}
                                className="p-1.5 hover:bg-surface-3 rounded text-zinc-400 hover:text-brand-400"
                                title={t.duplicateProjectTitle}
                              >
                                <Copy className="w-4 h-4" />
                              </button>
                              <button
                                onClick={(e) => handleDeleteProject(family.latest.id, e)}
                                className="p-1.5 hover:bg-surface-3 rounded text-zinc-400 hover:text-red-400"
                                title={t.deleteProjectTitle}
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </div>

                          {/* 展开后的版本列表 */}
                          {isExpanded && (
                            <div className="bg-surface-0/50">
                              {family.versions.map((v) => (
                                <div
                                  key={v.id}
                                  className={`flex items-center gap-2 pl-9 pr-3 py-1.5 hover:bg-surface-2 cursor-pointer group/ver ${
                                    currentProject?.id === v.id ? "bg-brand-600/10" : ""
                                  }`}
                                  onClick={() => {
                                    setCurrentProject(v);
                                    setShowProjectMenu(false);
                                  }}
                                >
                                  <History className="w-3 h-3 text-zinc-600 flex-shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <span className="text-xs font-mono text-zinc-400">v{v.version}</span>
                                    {v.version_note && (
                                      <span className="ml-1.5 text-xs text-zinc-500 truncate">{v.version_note}</span>
                                    )}
                                  </div>
                                  {currentProject?.id === v.id && (
                                    <span className="text-[10px] text-brand-400 flex-shrink-0">{t.current}</span>
                                  )}
                                  {/* 版本行操作 */}
                                  <div className="flex items-center gap-1 opacity-0 group-hover/ver:opacity-100 transition-opacity">
                                    <button
                                      onClick={(e) => handleExportProject(v.id, `${family.name}_v${v.version}`, e)}
                                      className="p-1 hover:bg-surface-3 rounded text-zinc-500 hover:text-green-400"
                                      title={t.exportVersionTitle}
                                    >
                                      <Download className="w-3.5 h-3.5" />
                                    </button>
                                    <button
                                      onClick={(e) => handleDeleteProject(v.id, e)}
                                      className="p-1 hover:bg-surface-3 rounded text-zinc-500 hover:text-red-400"
                                      title={t.deleteVersionTitle}
                                    >
                                      <Trash2 className="w-3.5 h-3.5" />
                                    </button>
                                  </div>
                                </div>
                              ))}
                              {/* 创建新版本 */}
                              {creatingVersionForId === family.latest.id ? (
                                <div className="pl-9 pr-3 py-2 flex items-center gap-2">
                                  <input
                                    type="text"
                                    value={versionNote}
                                    onChange={(e) => setVersionNote(e.target.value)}
                                    placeholder={t.versionNotePlaceholder}
                                    className="flex-1 px-2 py-1 text-xs bg-surface-2 border border-surface-3 rounded text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-brand-500"
                                    autoFocus
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") handleCreateVersion(family.latest.id);
                                      if (e.key === "Escape") { setCreatingVersionForId(null); setVersionNote(""); }
                                    }}
                                  />
                                  <button
                                    onClick={() => handleCreateVersion(family.latest.id)}
                                    className="px-2 py-1 text-xs bg-brand-600 hover:bg-brand-700 text-white rounded"
                                  >
                                    {t.confirm}
                                  </button>
                                  <button
                                    onClick={() => { setCreatingVersionForId(null); setVersionNote(""); }}
                                    className="p-1 text-zinc-400 hover:text-zinc-200"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              ) : (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setCreatingVersionForId(family.latest.id);
                                    setVersionNote("");
                                  }}
                                  className="w-full pl-9 pr-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-300 hover:bg-surface-2 text-left flex items-center gap-1.5"
                                >
                                  <Plus className="w-3 h-3" />
                                  {t.createVersion}
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
          
          <button
            onClick={handleCreateProject}
            className="px-3 py-1.5 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors"
          >
            {t.newProject}
          </button>
          <button
            onClick={() => importFileRef.current?.click()}
            className="px-3 py-1.5 text-sm bg-surface-2 hover:bg-surface-3 border border-surface-3 rounded-lg transition-colors flex items-center gap-1.5 text-zinc-300"
            title={t.importProjectTitle}
          >
            <Upload className="w-3.5 h-3.5" />
            {t.importProject}
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
              title={t.searchTitle}
            >
              <Search className="w-3.5 h-3.5" />
              {t.search}
            </button>
          )}
          <a
            href="/settings"
            className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            {t.settings}
          </a>
        </div>
      </header>

      {/* 三栏布局 */}
      <div className="flex-1 overflow-hidden">
        <WorkspaceLayout
          locale={uiLocale}
          leftPanel={
            <ProgressPanel
              project={currentProject}
              blocksRefreshKey={blocksRefreshKey}
              onBlockSelect={handleBlockSelect}
              onBlocksChange={setAllBlocks}
              onProjectChange={async () => {
                // 刷新项目数据
                if (currentProject) {
                  const updatedProject = await projectAPI.get(currentProject.id);
                  setCurrentProject(updatedProject);
                }
              }}
              onOpenAutoSplit={() => setShowAutoSplitModal(true)}
              onStartAllReady={() => {
                if (!currentProject) return;
                setIsStartAllReadyRunning(true);
                startAllReadyBlocks(currentProject.id, () => {
                  setBlocksRefreshKey(prev => prev + 1);
                }).catch(console.error).finally(() => {
                  setIsStartAllReadyRunning(false);
                  setBlocksRefreshKey(prev => prev + 1);
                });
              }}
            />
          }
          centerPanel={
            <ContentPanel
              projectId={currentProject?.id || null}
              projectLocale={currentProject?.locale}
              selectedBlock={selectedBlock}
              allBlocks={allBlocks}
              onFieldsChange={() => {
                if (currentProject) {
                  // 刷新 ContentBlocks（确保树形视图和内容面板同步）
                  setBlocksRefreshKey(prev => prev + 1);
                }
              }}
              onVersionCreated={async () => {
                // 弹窗创建版本后刷新项目列表，确保新版本可见
                const updatedProjects = await projectAPI.list();
                setProjects(updatedProjects);
              }}
              onBlockSelect={handleBlockSelect}
              onSendToAgent={setPendingAgentMessage}
              onSendSelectionToAgent={setPendingAgentSelection}
            />
          }
          rightPanel={
            <AgentPanel
              key={`${currentProject?.id || "none"}-${refreshKey}`}  // 项目切换时销毁重建，refreshKey 保留阶段推进刷新
              projectId={currentProject?.id || null}
              projectLocale={currentProject?.locale}
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
              externalSelection={pendingAgentSelection}
              onExternalSelectionConsumed={() => setPendingAgentSelection(null)}
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

      <ProjectAutoSplitModal
        open={showAutoSplitModal}
        projectId={currentProject?.id || null}
        projectLocale={currentProject?.locale}
        onClose={() => setShowAutoSplitModal(false)}
        onApplied={() => {
          setBlocksRefreshKey(prev => prev + 1);
        }}
      />

      {/* 全局搜索替换 */}
      {currentProject && (
        <GlobalSearchModal
          projectId={currentProject.id}
          projectLocale={currentProject.locale}
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

