// frontend/app/settings/page.tsx
// 功能: 后台设置页面 — Tab 导航 + 按需数据加载
// 各 Section 组件拆分到 frontend/components/settings/ 目录

"use client";

import { useState, useEffect, useCallback } from "react";
import { settingsAPI, graderAPI, phaseTemplateAPI } from "@/lib/api";
import type { AgentSettingsData, CreatorProfile, GraderData, PhaseTemplate, TemplateNode } from "@/lib/api";
import type { PreQuestion } from "@/lib/preQuestions";

import { SystemPromptsSection } from "@/components/settings/system-prompts-section";
import { ProfilesSection } from "@/components/settings/profiles-section";
import { TemplatesSection } from "@/components/settings/templates-section";
import { PhaseTemplatesSection } from "@/components/settings/phase-templates-section";
import { ChannelsSection } from "@/components/settings/channels-section";
import { GradersSection } from "@/components/settings/graders-section";
import { EvalPromptsSection } from "@/components/settings/eval-prompts-section";
import { AgentSettingsSection } from "@/components/settings/agent-settings-section";
import { ModelSettingsSection } from "@/components/settings/model-settings-section";
import { LogsSection } from "@/components/settings/logs-section";

type Tab = "prompts" | "profiles" | "templates" | "phase_templates" | "channels" | "graders" | "eval_prompts" | "agent" | "models" | "logs";
type SystemPromptItem = { id: string; name: string; phase: string; content?: string };
type EvalPromptItem = {
  id: string;
  phase: string;
  name?: string;
  description?: string;
  content?: string;
};
type FieldTemplateItem = {
  id: string;
  name: string;
  description?: string;
  category?: string;
  schema_version?: number;
  fields?: Array<{
    name: string;
    type?: string;
    ai_prompt?: string;
    content?: string;
    pre_questions?: PreQuestion[];
    depends_on?: string[];
  }>;
  root_nodes?: TemplateNode[];
};
type ChannelItem = { id: string; name: string; description?: string; platform?: string; prompt_template?: string };
type LogItem = { id: string; [key: string]: unknown };

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("prompts");
  const [profiles, setProfiles] = useState<CreatorProfile[]>([]);
  const [templates, setTemplates] = useState<FieldTemplateItem[]>([]);
  const [channels, setChannels] = useState<ChannelItem[]>([]);
  const [graders, setGraders] = useState<GraderData[]>([]);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [prompts, setPrompts] = useState<SystemPromptItem[]>([]);
  const [evalPrompts, setEvalPrompts] = useState<EvalPromptItem[]>([]);
  const [agentSettings, setAgentSettings] = useState<AgentSettingsData | null>(null);
  const [phaseTemplates, setPhaseTemplates] = useState<PhaseTemplate[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      switch (activeTab) {
        case "prompts":
          setPrompts(await settingsAPI.listSystemPrompts());
          break;
        case "profiles":
          setProfiles(await settingsAPI.listCreatorProfiles());
          break;
        case "templates":
          setTemplates(await settingsAPI.listFieldTemplates());
          break;
        case "phase_templates":
          setPhaseTemplates(await phaseTemplateAPI.list());
          break;
        case "channels":
          setChannels(await settingsAPI.listChannels());
          break;
        case "graders":
          setGraders(await graderAPI.list());
          break;
        case "eval_prompts":
          setEvalPrompts(await settingsAPI.listEvalPrompts());
          break;
        case "agent":
        case "models":
          setAgentSettings(await settingsAPI.getAgentSettings());
          break;
        case "logs":
          setLogs(await settingsAPI.listLogs());
          break;
      }
    } catch (err) {
      console.error("加载数据失败:", err);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: "prompts", label: "传统流程提示词", icon: "📝" },
    { id: "profiles", label: "创作者特质", icon: "👤" },
    { id: "templates", label: "内容块模板", icon: "📋" },
    { id: "phase_templates", label: "流程模板", icon: "📐" },
    { id: "channels", label: "渠道管理", icon: "📢" },
    { id: "graders", label: "评分器", icon: "⚖️" },
    { id: "eval_prompts", label: "评估提示词", icon: "🧪" },
    { id: "agent", label: "Agent设置", icon: "🤖" },
    { id: "models", label: "模型配置", icon: "🧠" },
    { id: "logs", label: "调试日志", icon: "📊" },
  ];

  return (
    <div className="min-h-screen bg-surface-0">
      <header className="h-14 border-b border-surface-3 bg-surface-1 flex items-center justify-between px-6">
        <div className="flex items-center gap-4">
          <a href="/workspace" className="text-zinc-400 hover:text-zinc-200 transition-colors">
            ← 返回工作台
          </a>
          <h1 className="text-lg font-semibold text-zinc-100">后台设置</h1>
        </div>
      </header>

      <div className="flex">
        <aside className="w-52 border-r border-surface-3 min-h-[calc(100vh-3.5rem)]">
          <nav className="p-4 space-y-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full px-3 py-2 text-left rounded-lg transition-colors flex items-center gap-2 ${
                  activeTab === tab.id
                    ? "bg-brand-600/20 text-brand-400"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-surface-3"
                }`}
              >
                <span>{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </nav>
        </aside>

        <main className="flex-1 p-6 max-w-5xl">
          {loading ? (
            <div className="text-zinc-500">加载中...</div>
          ) : (
            <>
              {activeTab === "prompts" && <SystemPromptsSection prompts={prompts} onRefresh={loadData} />}
              {activeTab === "profiles" && <ProfilesSection profiles={profiles} onRefresh={loadData} />}
              {activeTab === "templates" && <TemplatesSection templates={templates} onRefresh={loadData} />}
              {activeTab === "phase_templates" && <PhaseTemplatesSection templates={phaseTemplates} onRefresh={loadData} />}
              {activeTab === "channels" && <ChannelsSection channels={channels} onRefresh={loadData} />}
              {activeTab === "graders" && <GradersSection graders={graders} onRefresh={loadData} />}
              {activeTab === "eval_prompts" && <EvalPromptsSection prompts={evalPrompts} onRefresh={loadData} />}
              {activeTab === "agent" && <AgentSettingsSection settings={agentSettings} onRefresh={loadData} />}
              {activeTab === "models" && <ModelSettingsSection settings={agentSettings} onRefresh={loadData} />}
              {activeTab === "logs" && <LogsSection logs={logs} onRefresh={loadData} />}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
