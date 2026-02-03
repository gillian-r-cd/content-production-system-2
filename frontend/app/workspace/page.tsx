// frontend/app/workspace/page.tsx
// 功能: 内容生产工作台主页面
// 主要组件: WorkspacePage

"use client";

import { useState, useEffect } from "react";
import { WorkspaceLayout } from "@/components/layout/workspace-layout";
import { ProgressPanel } from "@/components/progress-panel";
import { ContentPanel } from "@/components/content-panel";
import { AgentPanel } from "@/components/agent-panel";
import { CreateProjectModal } from "@/components/create-project-modal";
import { projectAPI, fieldAPI, agentAPI } from "@/lib/api";
import type { Project, Field } from "@/lib/api";

export default function WorkspacePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [fields, setFields] = useState<Field[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // 加载项目列表
  useEffect(() => {
    loadProjects();
  }, []);

  // 加载当前项目的字段
  useEffect(() => {
    if (currentProject) {
      loadFields(currentProject.id);
    }
  }, [currentProject?.id]);

  const loadProjects = async () => {
    try {
      const data = await projectAPI.list();
      setProjects(data);
      
      // 自动选择第一个项目
      if (data.length > 0 && !currentProject) {
        setCurrentProject(data[0]);
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
      currentProject.current_phase
    );

    // 更新项目状态
    if (response.phase_status) {
      setCurrentProject({
        ...currentProject,
        phase_status: response.phase_status,
      });
    }

    // 重新加载字段
    loadFields(currentProject.id);

    return response.message;
  };

  const handleCreateProject = () => {
    setShowCreateModal(true);
  };

  const handleProjectCreated = (project: Project) => {
    setProjects([...projects, project]);
    setCurrentProject(project);
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
          
          {/* 项目选择器 */}
          <select
            value={currentProject?.id || ""}
            onChange={(e) => {
              const project = projects.find((p) => p.id === e.target.value);
              setCurrentProject(project || null);
            }}
            className="px-3 py-1.5 bg-surface-2 border border-surface-3 rounded-lg text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">选择项目</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} (v{p.version})
              </option>
            ))}
          </select>
          
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
              onPhaseClick={handlePhaseClick}
              onPhaseReorder={handlePhaseReorder}
              onAutonomyChange={handleAutonomyChange}
            />
          }
          centerPanel={
            <ContentPanel
              projectId={currentProject?.id || null}
              currentPhase={currentProject?.current_phase || "intent"}
              fields={fields}
              onFieldUpdate={handleFieldUpdate}
              onFieldsChange={() => currentProject && loadFields(currentProject.id)}
            />
          }
          rightPanel={
            <AgentPanel
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

