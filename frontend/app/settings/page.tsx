// frontend/app/settings/page.tsx
// 功能: 后台设置页面 - 用户友好的可视化编辑器
// 主要组件: SettingsPage

"use client";

import { useState, useEffect, useRef } from "react";
import { settingsAPI } from "@/lib/api";
import type { CreatorProfile } from "@/lib/api";
import { Download, Upload } from "lucide-react";

type Tab = "prompts" | "profiles" | "templates" | "channels" | "simulators" | "agent" | "logs";

// ============== 导入导出按钮组件 ==============
interface ImportExportButtonsProps {
  onExportAll: () => Promise<void>;
  onExportSingle?: (id: string) => Promise<void>;
  onImport: (data: any[]) => Promise<void>;
  typeName: string;  // 如 "字段模板"
}

function ImportExportButtons({ onExportAll, onImport, typeName }: ImportExportButtonsProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setImporting(true);
    try {
      const text = await file.text();
      const json = JSON.parse(text);
      
      // 支持两种格式：直接数组 或 { data: [...] }
      const data = Array.isArray(json) ? json : (json.data || []);
      await onImport(data);
      alert(`导入${typeName}成功！`);
    } catch (err) {
      console.error("导入失败:", err);
      alert(`导入失败: ${err instanceof Error ? err.message : "文件格式错误"}`);
    } finally {
      setImporting(false);
      // 清空 input 以便重复选择同一文件
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  return (
    <div className="flex items-center gap-2">
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        onChange={handleFileChange}
        className="hidden"
      />
      <button
        onClick={handleImportClick}
        disabled={importing}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors disabled:opacity-50"
      >
        <Upload className="w-4 h-4" />
        {importing ? "导入中..." : "导入"}
      </button>
      <button
        onClick={onExportAll}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
      >
        <Download className="w-4 h-4" />
        导出全部
      </button>
    </div>
  );
}

// 单个项目导出按钮
function SingleExportButton({ onExport, title }: { onExport: () => Promise<void>; title?: string }) {
  const [exporting, setExporting] = useState(false);
  
  const handleClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setExporting(true);
    try {
      await onExport();
    } finally {
      setExporting(false);
    }
  };
  
  return (
    <button
      onClick={handleClick}
      disabled={exporting}
      className="px-2 py-1 text-xs bg-surface-3 hover:bg-surface-4 rounded text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-50"
      title={title || "导出"}
    >
      <Download className="w-3.5 h-3.5" />
    </button>
  );
}

// 下载 JSON 文件的工具函数
function downloadJSON(data: any, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("prompts");
  const [profiles, setProfiles] = useState<CreatorProfile[]>([]);
  const [templates, setTemplates] = useState<any[]>([]);
  const [channels, setChannels] = useState<any[]>([]);
  const [simulators, setSimulators] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);
  const [prompts, setPrompts] = useState<any[]>([]);
  const [agentSettings, setAgentSettings] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, [activeTab]);

  const loadData = async () => {
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
        case "channels":
          setChannels(await settingsAPI.listChannels());
          break;
        case "simulators":
          setSimulators(await settingsAPI.listSimulators());
          break;
        case "agent":
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
  };

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: "prompts", label: "系统提示词", icon: "📝" },
    { id: "profiles", label: "创作者特质", icon: "👤" },
    { id: "templates", label: "字段模板", icon: "📋" },
    { id: "channels", label: "渠道管理", icon: "📢" },
    { id: "simulators", label: "模拟器", icon: "🎭" },
    { id: "agent", label: "Agent设置", icon: "🤖" },
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
              {activeTab === "channels" && <ChannelsSection channels={channels} onRefresh={loadData} />}
              {activeTab === "simulators" && <SimulatorsSection simulators={simulators} onRefresh={loadData} />}
              {activeTab === "agent" && <AgentSettingsSection settings={agentSettings} onRefresh={loadData} />}
              {activeTab === "logs" && <LogsSection logs={logs} onRefresh={loadData} />}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

// ============== 通用组件 ==============

function FormField({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-zinc-300 mb-1.5">{label}</label>
      {children}
      {hint && <p className="text-xs text-zinc-500 mt-1">{hint}</p>}
    </div>
  );
}

function TagInput({ value, onChange, placeholder }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [input, setInput] = useState("");
  
  const addTag = () => {
    if (input.trim() && !value.includes(input.trim())) {
      onChange([...value, input.trim()]);
      setInput("");
    }
  };
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addTag();
    }
  };
  
  const removeTag = (tag: string) => {
    onChange(value.filter(v => v !== tag));
  };
  
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {value.map((tag) => (
          <span key={tag} className="inline-flex items-center gap-1 px-2 py-1 bg-brand-600/20 text-brand-400 rounded-lg text-sm">
            {tag}
            <button onClick={() => removeTag(tag)} className="hover:text-red-400">×</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || "输入后按回车添加..."}
          className="flex-1 px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <button
          type="button"
          onClick={addTag}
          disabled={!input.trim()}
          className="px-3 py-2 bg-brand-600 hover:bg-brand-700 disabled:bg-zinc-700 disabled:cursor-not-allowed text-white rounded-lg text-sm transition-colors"
        >
          添加
        </button>
      </div>
      {value.length === 0 && (
        <p className="text-xs text-zinc-500">输入问题后按 Enter 键或点击「添加」按钮</p>
      )}
    </div>
  );
}

function KeyValueEditor({ value, onChange, keyLabel, valueLabel, keyPlaceholder, valuePlaceholder }: {
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
  keyLabel?: string;
  valueLabel?: string;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
}) {
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  
  const entries = Object.entries(value || {});
  
  const addPair = () => {
    if (newKey.trim() && newValue.trim()) {
      onChange({ ...value, [newKey.trim()]: newValue.trim() });
      setNewKey("");
      setNewValue("");
    }
  };
  
  const removePair = (key: string) => {
    const { [key]: _, ...rest } = value;
    onChange(rest);
  };
  
  const updateValue = (key: string, newVal: string) => {
    onChange({ ...value, [key]: newVal });
  };
  
  return (
    <div className="space-y-3">
      {entries.map(([k, v]) => (
        <div key={k} className="flex gap-2 items-center">
          <input
            value={k}
            disabled
            className="w-1/3 px-3 py-2 bg-surface-3 border border-surface-3 rounded-lg text-zinc-400 text-sm"
          />
          <input
            value={v}
            onChange={(e) => updateValue(k, e.target.value)}
            className="flex-1 px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <button onClick={() => removePair(k)} className="px-2 py-2 text-red-400 hover:text-red-300">
            ×
          </button>
        </div>
      ))}
      <div className="flex gap-2 items-center pt-2 border-t border-surface-3">
        <input
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
          placeholder={keyPlaceholder || "属性名"}
          className="w-1/3 px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <input
          value={newValue}
          onChange={(e) => setNewValue(e.target.value)}
          placeholder={valuePlaceholder || "属性值"}
          className="flex-1 px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <button onClick={addPair} className="px-3 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm">
          添加
        </button>
      </div>
    </div>
  );
}

// ============== 系统提示词管理 ==============
function SystemPromptsSection({ prompts, onRefresh }: { prompts: any[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<any>({});

  const PHASE_NAMES: Record<string, string> = {
    intent: "意图分析",
    research: "消费者调研",
    design_inner: "内涵设计",
    produce_inner: "内涵生产",
    design_outer: "外延设计",
    produce_outer: "外延生产",
    simulate: "消费者模拟",
    evaluate: "评估",
  };

  const handleEdit = (prompt: any) => {
    setEditingId(prompt.id);
    setEditForm({ ...prompt });
  };

  const handleSave = async () => {
    try {
      await settingsAPI.updateSystemPrompt(editingId!, editForm);
      setEditingId(null);
      onRefresh();
    } catch (err) {
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  const handleExportAll = async () => {
    try {
      const result = await settingsAPI.exportSystemPrompts();
      downloadJSON(result, `system_prompts_${new Date().toISOString().split("T")[0]}.json`);
    } catch (err) {
      alert("导出失败");
    }
  };

  const handleExportSingle = async (id: string) => {
    try {
      const result = await settingsAPI.exportSystemPrompts(id);
      const prompt = prompts.find(p => p.id === id);
      downloadJSON(result, `system_prompt_${prompt?.phase || id}.json`);
    } catch (err) {
      alert("导出失败");
    }
  };

  const handleImport = async (data: any[]) => {
    await settingsAPI.importSystemPrompts(data);
    onRefresh();
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">系统提示词</h2>
          <p className="text-sm text-zinc-500 mt-1">
            每个阶段的系统提示词会自动注入到该阶段的所有 AI 生成任务中
          </p>
        </div>
        <ImportExportButtons
          typeName="系统提示词"
          onExportAll={handleExportAll}
          onImport={handleImport}
        />
      </div>

      <div className="space-y-4">
        {prompts.map((prompt) => (
          <div key={prompt.id} className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
            {editingId === prompt.id ? (
              <div className="space-y-4">
                <FormField label="提示词名称">
                  <input
                    type="text"
                    value={editForm.name || ""}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
                  />
                </FormField>
                <FormField label="适用阶段">
                  <select
                    value={editForm.phase || ""}
                    onChange={(e) => setEditForm({ ...editForm, phase: e.target.value })}
                    className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
                  >
                    {Object.entries(PHASE_NAMES).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </FormField>
                <FormField label="提示词内容" hint="这段内容会作为系统提示词注入到该阶段的每次 AI 调用">
                  <textarea
                    value={editForm.content || ""}
                    onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                    rows={10}
                    className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 font-mono text-sm"
                  />
                </FormField>
                <div className="flex gap-2">
                  <button onClick={handleSave} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">保存</button>
                  <button onClick={() => setEditingId(null)} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">取消</button>
                </div>
              </div>
            ) : (
              <div>
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-medium text-zinc-200">{prompt.name}</h3>
                    <span className="inline-block mt-1 text-xs bg-brand-600/20 text-brand-400 px-2 py-0.5 rounded">
                      {PHASE_NAMES[prompt.phase] || prompt.phase}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <SingleExportButton onExport={() => handleExportSingle(prompt.id)} title="导出此提示词" />
                    <button onClick={() => handleEdit(prompt)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">
                      编辑
                    </button>
                  </div>
                </div>
                <p className="text-sm text-zinc-500 mt-3 whitespace-pre-wrap line-clamp-3">{prompt.content}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ============== 创作者特质管理 ==============
function ProfilesSection({ profiles, onRefresh }: { profiles: CreatorProfile[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<any>({});
  const [isCreating, setIsCreating] = useState(false);

  // 预定义的特质类型
  const TRAIT_SUGGESTIONS = [
    { key: "tone", label: "语调风格", placeholder: "如：专业但亲和、轻松幽默" },
    { key: "vocabulary", label: "词汇偏好", placeholder: "如：行业术语丰富、通俗易懂" },
    { key: "personality", label: "人格特点", placeholder: "如：理性、感性、务实" },
    { key: "taboos", label: "禁忌内容", placeholder: "如：过度营销、夸大其词" },
  ];

  const handleExportAll = async () => {
    try {
      const result = await settingsAPI.exportCreatorProfiles();
      downloadJSON(result, `creator_profiles_${new Date().toISOString().split("T")[0]}.json`);
    } catch (err) {
      alert("导出失败");
    }
  };

  const handleExportSingle = async (id: string) => {
    try {
      const result = await settingsAPI.exportCreatorProfiles(id);
      const profile = profiles.find(p => p.id === id);
      downloadJSON(result, `creator_profile_${profile?.name || id}.json`);
    } catch (err) {
      alert("导出失败");
    }
  };

  const handleImport = async (data: any[]) => {
    await settingsAPI.importCreatorProfiles(data);
    onRefresh();
  };

  const handleCreate = () => {
    setIsCreating(true);
    setEditForm({ name: "", description: "", traits: {} });
  };

  const handleEdit = (profile: CreatorProfile) => {
    setEditingId(profile.id);
    setEditForm({ ...profile });
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await settingsAPI.createCreatorProfile(editForm);
      } else {
        await settingsAPI.updateCreatorProfile(editingId!, editForm);
      }
      setEditingId(null);
      setIsCreating(false);
      onRefresh();
    } catch (err) {
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此创作者特质？")) return;
    try {
      await settingsAPI.deleteCreatorProfile(id);
      onRefresh();
    } catch (err) {
      alert("删除失败");
    }
  };

  const updateTrait = (key: string, value: string) => {
    setEditForm({
      ...editForm,
      traits: { ...editForm.traits, [key]: value },
    });
  };

  const renderForm = () => (
    <div className="p-5 bg-surface-2 border border-brand-500/50 rounded-xl mb-4">
      <div className="space-y-5">
        <FormField label="特质名称" hint="给这个创作者特质起一个容易识别的名字">
          <input
            type="text"
            value={editForm.name || ""}
            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
            placeholder="如：专业严谨型、亲和幽默型"
            className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
          />
        </FormField>
        
        <FormField label="适用场景" hint="简单描述这个特质适合什么类型的内容">
          <input
            type="text"
            value={editForm.description || ""}
            onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
            placeholder="如：适合 B2B、技术类、专业培训内容"
            className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
          />
        </FormField>

        <div className="border-t border-surface-3 pt-4">
          <h4 className="text-sm font-medium text-zinc-300 mb-4">特质详情</h4>
          <div className="space-y-4">
            {TRAIT_SUGGESTIONS.map((trait) => (
              <FormField key={trait.key} label={trait.label}>
                <input
                  type="text"
                  value={editForm.traits?.[trait.key] || ""}
                  onChange={(e) => updateTrait(trait.key, e.target.value)}
                  placeholder={trait.placeholder}
                  className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
                />
              </FormField>
            ))}
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          <button onClick={handleSave} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">保存</button>
          <button onClick={() => { setEditingId(null); setIsCreating(false); }} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">取消</button>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">创作者特质</h2>
          <p className="text-sm text-zinc-500 mt-1">定义不同的创作风格，创建项目时可以选择</p>
        </div>
        <div className="flex items-center gap-3">
          <ImportExportButtons
            typeName="创作者特质"
            onExportAll={handleExportAll}
            onImport={handleImport}
          />
          <button onClick={handleCreate} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">
            + 新建特质
          </button>
        </div>
      </div>

      {isCreating && renderForm()}

      <div className="grid gap-4">
        {profiles.map((profile) => (
          <div key={profile.id}>
            {editingId === profile.id ? renderForm() : (
              <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <h3 className="font-medium text-zinc-200 text-lg">{profile.name}</h3>
                    <p className="text-sm text-zinc-500 mt-1">{profile.description}</p>
                    {profile.traits && Object.keys(profile.traits).length > 0 && (
                      <div className="mt-4 grid grid-cols-2 gap-3">
                        {Object.entries(profile.traits).map(([key, value]) => (
                          <div key={key} className="text-sm">
                            <span className="text-zinc-500">{key}：</span>
                            <span className="text-zinc-300">{String(value)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <SingleExportButton onExport={() => handleExportSingle(profile.id)} title="导出此特质" />
                    <button onClick={() => handleEdit(profile)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">编辑</button>
                    <button onClick={() => handleDelete(profile.id)} className="px-3 py-1 text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg">删除</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
        {profiles.length === 0 && !isCreating && (
          <div className="text-center py-12 text-zinc-500">
            还没有创作者特质，点击上方「新建特质」创建一个
          </div>
        )}
      </div>
    </div>
  );
}

// ============== 字段模板管理（可视化编辑器） ==============
function TemplatesSection({ templates, onRefresh }: { templates: any[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<any>({});
  const [isCreating, setIsCreating] = useState(false);

  const handleExportAll = async () => {
    try {
      const result = await settingsAPI.exportFieldTemplates();
      downloadJSON(result, `field_templates_${new Date().toISOString().split("T")[0]}.json`);
    } catch (err) {
      alert("导出失败");
    }
  };

  const handleExportSingle = async (id: string) => {
    try {
      const result = await settingsAPI.exportFieldTemplates(id);
      const template = templates.find(t => t.id === id);
      downloadJSON(result, `field_template_${template?.name || id}.json`);
    } catch (err) {
      alert("导出失败");
    }
  };

  const handleImport = async (data: any[]) => {
    await settingsAPI.importFieldTemplates(data);
    onRefresh();
  };

  const handleCreate = () => {
    setIsCreating(true);
    setEditForm({ name: "", description: "", category: "通用", fields: [] });
  };

  const handleEdit = (template: any) => {
    setEditingId(template.id);
    setEditForm({ ...template });
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await settingsAPI.createFieldTemplate(editForm);
      } else {
        await settingsAPI.updateFieldTemplate(editingId!, editForm);
      }
      setEditingId(null);
      setIsCreating(false);
      onRefresh();
    } catch (err) {
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此模板？")) return;
    try {
      await settingsAPI.deleteFieldTemplate(id);
      onRefresh();
    } catch (err) {
      alert("删除失败");
    }
  };

  // 字段编辑辅助函数
  const addField = () => {
    setEditForm({
      ...editForm,
      fields: [...(editForm.fields || []), { name: "", type: "richtext", ai_prompt: "", pre_questions: [], depends_on: [] }],
    });
  };

  const updateField = (index: number, key: string, value: any) => {
    const newFields = [...editForm.fields];
    newFields[index] = { ...newFields[index], [key]: value };
    setEditForm({ ...editForm, fields: newFields });
  };

  const removeField = (index: number) => {
    const newFields = editForm.fields.filter((_: any, i: number) => i !== index);
    setEditForm({ ...editForm, fields: newFields });
  };

  const moveField = (index: number, direction: "up" | "down") => {
    const newIndex = direction === "up" ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= editForm.fields.length) return;
    const newFields = [...editForm.fields];
    [newFields[index], newFields[newIndex]] = [newFields[newIndex], newFields[index]];
    setEditForm({ ...editForm, fields: newFields });
  };

  const renderForm = () => (
    <div className="p-5 bg-surface-2 border border-brand-500/50 rounded-xl mb-4">
      <div className="space-y-5">
        <div className="grid grid-cols-3 gap-4">
          <FormField label="模板名称">
            <input
              type="text"
              value={editForm.name || ""}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              placeholder="如：产品介绍模板"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
          <FormField label="分类">
            <input
              type="text"
              value={editForm.category || ""}
              onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
              placeholder="如：营销、教育"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
          <FormField label="描述">
            <input
              type="text"
              value={editForm.description || ""}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              placeholder="模板用途说明"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
        </div>

        {/* 字段列表 */}
        <div className="border-t border-surface-3 pt-4">
          <div className="flex justify-between items-center mb-4">
            <h4 className="text-sm font-medium text-zinc-300">字段列表</h4>
            <button onClick={addField} className="px-3 py-1 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg">
              + 添加字段
            </button>
          </div>

          {(editForm.fields || []).length === 0 ? (
            <div className="text-center py-8 text-zinc-500 border border-dashed border-surface-3 rounded-lg">
              还没有字段，点击「添加字段」开始
            </div>
          ) : (
            <div className="space-y-4">
              {(editForm.fields || []).map((field: any, index: number) => (
                <div key={index} className="p-4 bg-surface-1 border border-surface-3 rounded-lg">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-500 text-sm">#{index + 1}</span>
                      <div className="flex gap-1">
                        <button
                          onClick={() => moveField(index, "up")}
                          disabled={index === 0}
                          className="px-2 py-1 text-xs bg-surface-3 rounded disabled:opacity-30"
                        >
                          ↑
                        </button>
                        <button
                          onClick={() => moveField(index, "down")}
                          disabled={index === editForm.fields.length - 1}
                          className="px-2 py-1 text-xs bg-surface-3 rounded disabled:opacity-30"
                        >
                          ↓
                        </button>
                      </div>
                    </div>
                    <button onClick={() => removeField(index)} className="text-red-400 hover:text-red-300 text-sm">
                      删除
                    </button>
                  </div>

                  <div className="grid grid-cols-2 gap-4 mb-3">
                    <FormField label="字段名称">
                      <input
                        type="text"
                        value={field.name || ""}
                        onChange={(e) => updateField(index, "name", e.target.value)}
                        placeholder="如：产品定位"
                        className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                      />
                    </FormField>
                    <FormField label="字段类型">
                      <select
                        value={field.type || "text"}
                        onChange={(e) => updateField(index, "type", e.target.value)}
                        className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                      >
                        <option value="text">短文本</option>
                        <option value="longtext">长文本</option>
                        <option value="markdown">Markdown</option>
                        <option value="list">列表</option>
                      </select>
                    </FormField>
                  </div>

                  <FormField label="AI 生成提示词" hint="指导 AI 如何生成这个字段的内容">
                    <textarea
                      value={field.ai_prompt || ""}
                      onChange={(e) => updateField(index, "ai_prompt", e.target.value)}
                      placeholder="请根据项目意图和消费者画像，生成一段简洁有力的产品定位..."
                      rows={3}
                      className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                    />
                  </FormField>

                  <div className="mt-3">
                    <FormField label="生成前提问" hint="生成前需要用户回答的问题（可选）">
                      <TagInput
                        value={field.pre_questions || []}
                        onChange={(v) => updateField(index, "pre_questions", v)}
                        placeholder="输入问题后按回车，如：目标用户是谁？"
                      />
                    </FormField>
                  </div>

                  {index > 0 && (
                    <div className="mt-3">
                      <FormField label="依赖字段" hint="选择这个字段依赖的其他字段（它们的内容会作为生成上下文）">
                        <div className="flex flex-wrap gap-2">
                          {editForm.fields.slice(0, index).map((f: any, i: number) => (
                            <label key={i} className="flex items-center gap-2 text-sm text-zinc-300">
                              <input
                                type="checkbox"
                                checked={(field.depends_on || []).includes(f.name)}
                                onChange={(e) => {
                                  const deps = field.depends_on || [];
                                  if (e.target.checked) {
                                    updateField(index, "depends_on", [...deps, f.name]);
                                  } else {
                                    updateField(index, "depends_on", deps.filter((d: string) => d !== f.name));
                                  }
                                }}
                              />
                              {f.name || `字段 ${i + 1}`}
                            </label>
                          ))}
                        </div>
                      </FormField>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex gap-2 pt-2">
          <button onClick={handleSave} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">保存</button>
          <button onClick={() => { setEditingId(null); setIsCreating(false); }} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">取消</button>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">字段模板</h2>
          <p className="text-sm text-zinc-500 mt-1">定义可复用的内容字段结构，创建项目时可以引用</p>
        </div>
        <div className="flex items-center gap-3">
          <ImportExportButtons
            typeName="字段模板"
            onExportAll={handleExportAll}
            onImport={handleImport}
          />
          <button onClick={handleCreate} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">
            + 新建模板
          </button>
        </div>
      </div>

      {isCreating && renderForm()}

      <div className="grid gap-4">
        {templates.map((template) => (
          <div key={template.id}>
            {editingId === template.id ? renderForm() : (
              <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-zinc-200">{template.name}</h3>
                      <span className="text-xs bg-surface-3 px-2 py-1 rounded-full text-zinc-400">{template.category}</span>
                    </div>
                    <p className="text-sm text-zinc-500 mt-1">{template.description}</p>
                    {template.fields?.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {template.fields.map((f: any, i: number) => (
                          <span key={i} className="text-xs bg-brand-600/10 text-brand-400 px-2 py-1 rounded">
                            {f.name}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <SingleExportButton onExport={() => handleExportSingle(template.id)} title="导出此模板" />
                    <button onClick={() => handleEdit(template)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">编辑</button>
                    <button onClick={() => handleDelete(template.id)} className="px-3 py-1 text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg">删除</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
        {templates.length === 0 && !isCreating && (
          <div className="text-center py-12 text-zinc-500">
            还没有字段模板，点击上方「新建模板」创建一个
          </div>
        )}
      </div>
    </div>
  );
}

// ============== 渠道管理 ==============
function ChannelsSection({ channels, onRefresh }: { channels: any[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<any>({});
  const [isCreating, setIsCreating] = useState(false);

  const PLATFORM_OPTIONS = [
    { value: "social", label: "社交媒体", desc: "小红书、微博、抖音等" },
    { value: "article", label: "长文平台", desc: "公众号、知乎、博客等" },
    { value: "doc", label: "文档", desc: "PPT、PDF、手册等" },
    { value: "web", label: "网页", desc: "落地页、官网等" },
    { value: "email", label: "邮件", desc: "EDM、通讯等" },
    { value: "other", label: "其他", desc: "" },
  ];

  const handleCreate = () => {
    setIsCreating(true);
    setEditForm({ name: "", description: "", platform: "social", prompt_template: "", constraints: {} });
  };

  const handleEdit = (channel: any) => {
    setEditingId(channel.id);
    setEditForm({ ...channel });
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await settingsAPI.createChannel(editForm);
      } else {
        await settingsAPI.updateChannel(editingId!, editForm);
      }
      setEditingId(null);
      setIsCreating(false);
      onRefresh();
    } catch (err) {
      alert("保存失败");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此渠道？")) return;
    try {
      await settingsAPI.deleteChannel(id);
      onRefresh();
    } catch (err) {
      alert("删除失败");
    }
  };

  const renderForm = () => (
    <div className="p-5 bg-surface-2 border border-brand-500/50 rounded-xl mb-4">
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <FormField label="渠道名称">
            <input
              type="text"
              value={editForm.name || ""}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              placeholder="如：小红书、销售PPT"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
          <FormField label="描述">
            <input
              type="text"
              value={editForm.description || ""}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              placeholder="渠道用途说明"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
        </div>

        <FormField label="平台类型">
          <div className="grid grid-cols-3 gap-3">
            {PLATFORM_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                  editForm.platform === opt.value
                    ? "border-brand-500 bg-brand-600/10"
                    : "border-surface-3 hover:border-surface-4"
                }`}
              >
                <input
                  type="radio"
                  value={opt.value}
                  checked={editForm.platform === opt.value}
                  onChange={(e) => setEditForm({ ...editForm, platform: e.target.value })}
                  className="sr-only"
                />
                <div className="text-sm text-zinc-200">{opt.label}</div>
                {opt.desc && <div className="text-xs text-zinc-500">{opt.desc}</div>}
              </label>
            ))}
          </div>
        </FormField>

        <FormField label="内容生成提示词" hint="指导 AI 如何为这个渠道生成内容">
          <textarea
            value={editForm.prompt_template || ""}
            onChange={(e) => setEditForm({ ...editForm, prompt_template: e.target.value })}
            placeholder="请将以下内容改编为适合小红书的格式，要求：&#10;1. 标题吸引人&#10;2. 使用合适的表情符号&#10;3. 控制在 500 字以内..."
            rows={5}
            className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
          />
        </FormField>

        <FormField label="内容约束" hint="定义这个渠道的内容限制，如字数、格式等">
          <KeyValueEditor
            value={editForm.constraints || {}}
            onChange={(v) => setEditForm({ ...editForm, constraints: v })}
            keyPlaceholder="约束名，如：max_length"
            valuePlaceholder="约束值，如：500"
          />
        </FormField>

        <div className="flex gap-2 pt-2">
          <button onClick={handleSave} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">保存</button>
          <button onClick={() => { setEditingId(null); setIsCreating(false); }} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">取消</button>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">渠道管理</h2>
          <p className="text-sm text-zinc-500 mt-1">定义内容要发布的平台渠道，外延生产时使用</p>
        </div>
        <button onClick={handleCreate} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">+ 新建渠道</button>
      </div>

      {isCreating && renderForm()}

      <div className="grid gap-4 md:grid-cols-2">
        {channels.map((channel) => (
          <div key={channel.id}>
            {editingId === channel.id ? renderForm() : (
              <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl h-full">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-medium text-zinc-200">{channel.name}</h3>
                    <p className="text-sm text-zinc-500 mt-1">{channel.description}</p>
                    <span className="inline-block mt-2 text-xs bg-surface-3 px-2 py-1 rounded-full text-zinc-400">
                      {PLATFORM_OPTIONS.find(p => p.value === channel.platform)?.label || channel.platform}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => handleEdit(channel)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">编辑</button>
                    <button onClick={() => handleDelete(channel.id)} className="px-3 py-1 text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg">删除</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ============== 模拟器管理 ==============
function SimulatorsSection({ simulators, onRefresh }: { simulators: any[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<any>({});
  const [isCreating, setIsCreating] = useState(false);

  const INTERACTION_TYPES = [
    { value: "dialogue", label: "对话式", desc: "模拟多轮对话，适合 Chatbot、客服场景", icon: "💬" },
    { value: "reading", label: "阅读式", desc: "阅读全文后给反馈，适合文章、课程", icon: "📖" },
    { value: "decision", label: "决策式", desc: "模拟购买决策，适合销售页、落地页", icon: "🤔" },
    { value: "exploration", label: "探索式", desc: "带目的地探索，适合帮助文档", icon: "🔍" },
    { value: "experience", label: "体验式", desc: "完成特定任务，适合产品功能", icon: "✋" },
  ];

  const handleExportAll = async () => {
    try {
      const result = await settingsAPI.exportSimulators();
      downloadJSON(result, `simulators_${new Date().toISOString().split("T")[0]}.json`);
    } catch (err) {
      alert("导出失败");
    }
  };

  const handleExportSingle = async (id: string) => {
    try {
      const result = await settingsAPI.exportSimulators(id);
      const simulator = simulators.find(s => s.id === id);
      downloadJSON(result, `simulator_${simulator?.name || id}.json`);
    } catch (err) {
      alert("导出失败");
    }
  };

  const handleImport = async (data: any[]) => {
    await settingsAPI.importSimulators(data);
    onRefresh();
  };

  const handleCreate = () => {
    setIsCreating(true);
    setEditForm({ name: "", description: "", interaction_type: "reading", prompt_template: "", evaluation_dimensions: [], max_turns: 10 });
  };

  const handleEdit = (simulator: any) => {
    setEditingId(simulator.id);
    setEditForm({ ...simulator });
  };

  const handleSave = async () => {
    try {
      if (isCreating) {
        await settingsAPI.createSimulator(editForm);
      } else {
        await settingsAPI.updateSimulator(editingId!, editForm);
      }
      setEditingId(null);
      setIsCreating(false);
      onRefresh();
    } catch (err) {
      alert("保存失败");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此模拟器？")) return;
    try {
      await settingsAPI.deleteSimulator(id);
      onRefresh();
    } catch (err) {
      alert("删除失败");
    }
  };

  const renderForm = () => (
    <div className="p-5 bg-surface-2 border border-brand-500/50 rounded-xl mb-4">
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <FormField label="模拟器名称">
            <input
              type="text"
              value={editForm.name || ""}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              placeholder="如：课程学习模拟器"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
          <FormField label="描述">
            <input
              type="text"
              value={editForm.description || ""}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              placeholder="模拟器用途说明"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
        </div>

        <FormField label="交互类型">
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            {INTERACTION_TYPES.map((type) => (
              <label
                key={type.value}
                className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                  editForm.interaction_type === type.value
                    ? "border-brand-500 bg-brand-600/10"
                    : "border-surface-3 hover:border-surface-4"
                }`}
              >
                <input
                  type="radio"
                  value={type.value}
                  checked={editForm.interaction_type === type.value}
                  onChange={(e) => setEditForm({ ...editForm, interaction_type: e.target.value })}
                  className="sr-only"
                />
                <div className="flex items-center gap-2">
                  <span>{type.icon}</span>
                  <span className="text-sm text-zinc-200">{type.label}</span>
                </div>
                <div className="text-xs text-zinc-500 mt-1">{type.desc}</div>
              </label>
            ))}
          </div>
        </FormField>

        {editForm.interaction_type === "dialogue" && (
          <FormField label="最大对话轮数">
            <input
              type="number"
              value={editForm.max_turns || 10}
              onChange={(e) => setEditForm({ ...editForm, max_turns: parseInt(e.target.value) })}
              min={1}
              max={20}
              className="w-32 px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            />
          </FormField>
        )}

        <FormField label="评估维度" hint="定义用户体验后需要评分的维度">
          <TagInput
            value={editForm.evaluation_dimensions || []}
            onChange={(v) => setEditForm({ ...editForm, evaluation_dimensions: v })}
            placeholder="输入维度名后按回车，如：理解难度、价值感知、行动意愿"
          />
        </FormField>

        <FormField label="系统提示词模板（可选）" hint="留空将使用默认模板">
          <textarea
            value={editForm.prompt_template || ""}
            onChange={(e) => setEditForm({ ...editForm, prompt_template: e.target.value })}
            placeholder="可使用 {persona} 和 {content} 占位符..."
            rows={4}
            className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
          />
        </FormField>

        <div className="flex gap-2 pt-2">
          <button onClick={handleSave} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">保存</button>
          <button onClick={() => { setEditingId(null); setIsCreating(false); }} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">取消</button>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">模拟器管理</h2>
          <p className="text-sm text-zinc-500 mt-1">配置消费者体验模拟的类型和评估维度</p>
        </div>
        <div className="flex items-center gap-3">
          <ImportExportButtons
            typeName="模拟器"
            onExportAll={handleExportAll}
            onImport={handleImport}
          />
          <button onClick={handleCreate} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg">+ 新建模拟器</button>
        </div>
      </div>

      {isCreating && renderForm()}

      <div className="grid gap-4">
        {simulators.map((simulator) => (
          <div key={simulator.id}>
            {editingId === simulator.id ? renderForm() : (
              <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span>{INTERACTION_TYPES.find(t => t.value === simulator.interaction_type)?.icon || "🎭"}</span>
                      <h3 className="font-medium text-zinc-200">{simulator.name}</h3>
                      <span className="text-xs bg-surface-3 px-2 py-1 rounded-full text-zinc-400">
                        {INTERACTION_TYPES.find(t => t.value === simulator.interaction_type)?.label || simulator.interaction_type}
                      </span>
                    </div>
                    <p className="text-sm text-zinc-500 mt-1">{simulator.description}</p>
                    {simulator.evaluation_dimensions?.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {simulator.evaluation_dimensions.map((dim: string, i: number) => (
                          <span key={i} className="text-xs bg-brand-600/10 text-brand-400 px-2 py-1 rounded">
                            {dim}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <SingleExportButton onExport={() => handleExportSingle(simulator.id)} title="导出此模拟器" />
                    <button onClick={() => handleEdit(simulator)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">编辑</button>
                    <button onClick={() => handleDelete(simulator.id)} className="px-3 py-1 text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg">删除</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ============== Agent设置 ==============
function AgentSettingsSection({ settings, onRefresh }: { settings: any; onRefresh: () => void }) {
  const [editForm, setEditForm] = useState<any>(settings || { tools: [], skills: [], autonomy_defaults: {} });
  const [isSaving, setIsSaving] = useState(false);
  const [editingSkillIndex, setEditingSkillIndex] = useState<number | null>(null);
  const [newSkill, setNewSkill] = useState({ name: "", description: "", prompt: "" });

  useEffect(() => {
    if (settings) setEditForm(settings);
  }, [settings]);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await settingsAPI.updateAgentSettings(editForm);
      onRefresh();
      alert("保存成功");
    } catch (err) {
      alert("保存失败");
    } finally {
      setIsSaving(false);
    }
  };

  // 工具编辑状态
  const [editingToolId, setEditingToolId] = useState<string | null>(null);
  const [toolPrompts, setToolPrompts] = useState<Record<string, string>>(
    editForm.tool_prompts || {}
  );

  useEffect(() => {
    if (settings?.tool_prompts) {
      setToolPrompts(settings.tool_prompts);
    }
  }, [settings]);

  const TOOLS = [
    { 
      id: "deep_research", 
      name: "DeepResearch", 
      icon: "🔍", 
      desc: "网络深度调研，自动搜索和分析目标用户",
      defaultPrompt: "你是一个专业的用户研究专家。基于项目意图，你需要：\n1. 调研目标用户群体的特征和行为\n2. 分析用户的痛点和需求\n3. 生成结构化的消费者调研报告"
    },
    { 
      id: "generate_field", 
      name: "字段生成", 
      icon: "✍️", 
      desc: "根据上下文和依赖关系生成字段内容",
      defaultPrompt: "你是一个专业的内容创作者。基于上下文和依赖字段，生成高质量的内容。\n遵循创作者特质、保持风格一致性。"
    },
    { 
      id: "simulate_consumer", 
      name: "消费者模拟", 
      icon: "🎭", 
      desc: "模拟消费者与内容的交互体验",
      defaultPrompt: "你将扮演一个典型的目标消费者，基于用户画像进行内容体验模拟。\n提供真实的反馈、困惑点和改进建议。"
    },
    { 
      id: "evaluate_content", 
      name: "内容评估", 
      icon: "📊", 
      desc: "根据评估模板评估内容质量并给出建议",
      defaultPrompt: "你是一个内容质量评估专家。根据评估维度对内容进行打分和分析，\n给出具体的改进建议。"
    },
    { 
      id: "architecture_writer", 
      name: "架构操作", 
      icon: "🏗️", 
      desc: "添加/删除/移动阶段和字段，修改项目结构",
      defaultPrompt: "你是项目架构师。根据用户的自然语言描述，识别需要进行的架构操作（添加阶段/字段、删除、移动），\n并调用相应的操作函数完成修改。"
    },
    { 
      id: "outline_generator", 
      name: "大纲生成", 
      icon: "📋", 
      desc: "基于项目上下文生成内容大纲",
      defaultPrompt: "你是一个内容策划专家。基于项目意图和消费者调研结果，\n生成结构化的内容大纲，包括主题、章节、关键点和预计字段。"
    },
    { 
      id: "persona_manager", 
      name: "人物管理", 
      icon: "👥", 
      desc: "创建、编辑、选择消费者画像",
      defaultPrompt: "你是用户研究专家。帮助用户管理消费者画像，\n包括创建新画像、编辑现有画像、推荐合适的画像用于模拟。"
    },
    { 
      id: "skill_manager", 
      name: "技能管理", 
      icon: "⚡", 
      desc: "管理和应用可复用的AI技能",
      defaultPrompt: "你是AI技能管理专家。帮助用户查看、创建、应用可复用的AI技能，\n每个技能是一个可重复使用的提示词模板。"
    },
  ];

  const updateToolPrompt = (toolId: string, prompt: string) => {
    const newPrompts = { ...toolPrompts, [toolId]: prompt };
    setToolPrompts(newPrompts);
    setEditForm({ ...editForm, tool_prompts: newPrompts });
  };

  const PHASES = [
    { id: "intent", name: "意图分析" },
    { id: "research", name: "消费者调研" },
    { id: "design_inner", name: "内涵设计" },
    { id: "produce_inner", name: "内涵生产" },
    { id: "design_outer", name: "外延设计" },
    { id: "produce_outer", name: "外延生产" },
    { id: "simulate", name: "消费者模拟" },
    { id: "evaluate", name: "评估" },
  ];

  const addSkill = () => {
    if (!newSkill.name.trim()) return;
    setEditForm({
      ...editForm,
      skills: [...(editForm.skills || []), { ...newSkill }],
    });
    setNewSkill({ name: "", description: "", prompt: "" });
  };

  const updateSkill = (index: number, key: string, value: string) => {
    const newSkills = [...editForm.skills];
    newSkills[index] = { ...newSkills[index], [key]: value };
    setEditForm({ ...editForm, skills: newSkills });
  };

  const removeSkill = (index: number) => {
    if (!confirm("确定删除这个技能？")) return;
    const newSkills = editForm.skills.filter((_: any, i: number) => i !== index);
    setEditForm({ ...editForm, skills: newSkills });
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">Agent 设置</h2>
          <p className="text-sm text-zinc-500 mt-1">配置 AI Agent 可以使用的工具和自定义技能</p>
        </div>
        <button onClick={handleSave} disabled={isSaving} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg disabled:opacity-50">
          {isSaving ? "保存中..." : "保存设置"}
        </button>
      </div>

      <div className="space-y-6">
        {/* 可用工具 */}
        <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
          <h3 className="font-medium text-zinc-200 mb-4">🛠️ 可用工具</h3>
          <p className="text-sm text-zinc-500 mb-4">选择 Agent 在对话中可以调用的工具，点击工具可编辑其提示词</p>
          <div className="grid md:grid-cols-2 gap-3">
            {TOOLS.map((tool) => (
              <div
                key={tool.id}
                className={`p-4 border rounded-lg transition-colors ${
                  editForm.tools?.includes(tool.id)
                    ? "border-brand-500 bg-brand-600/10"
                    : "border-surface-3"
                }`}
              >
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={editForm.tools?.includes(tool.id) || false}
                    onChange={(e) => {
                      const tools = editForm.tools || [];
                      if (e.target.checked) {
                        setEditForm({ ...editForm, tools: [...tools, tool.id] });
                      } else {
                        setEditForm({ ...editForm, tools: tools.filter((t: string) => t !== tool.id) });
                      }
                    }}
                    className="mt-0.5"
                  />
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span>{tool.icon}</span>
                        <span className="text-zinc-200 font-medium">{tool.name}</span>
                      </div>
                      <button
                        onClick={() => setEditingToolId(editingToolId === tool.id ? null : tool.id)}
                        className="text-xs px-2 py-1 bg-surface-3 hover:bg-surface-4 rounded text-zinc-400 hover:text-zinc-200"
                      >
                        {editingToolId === tool.id ? "收起" : "编辑提示词"}
                      </button>
                    </div>
                    <p className="text-sm text-zinc-500 mt-1">{tool.desc}</p>
                    
                    {/* 提示词编辑区 */}
                    {editingToolId === tool.id && (
                      <div className="mt-3 pt-3 border-t border-surface-3">
                        <label className="block text-xs text-zinc-400 mb-1">工具提示词</label>
                        <textarea
                          value={toolPrompts[tool.id] || tool.defaultPrompt}
                          onChange={(e) => updateToolPrompt(tool.id, e.target.value)}
                          rows={4}
                          className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                          placeholder={tool.defaultPrompt}
                        />
                        <p className="text-xs text-zinc-600 mt-1">
                          此提示词将用于 Agent 调用该工具时的系统指令
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 自定义技能 */}
        <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
          <h3 className="font-medium text-zinc-200 mb-4">⚡ 自定义技能</h3>
          <p className="text-sm text-zinc-500 mb-4">
            技能是 Agent 可以执行的特定任务。你可以在与 Agent 对话时通过 @ 调用技能。
          </p>

          {/* 现有技能列表 */}
          <div className="space-y-3 mb-4">
            {(editForm.skills || []).map((skill: any, index: number) => (
              <div key={index} className="p-4 bg-surface-1 border border-surface-3 rounded-lg">
                {editingSkillIndex === index ? (
                  <div className="space-y-3">
                    <FormField label="技能名称">
                      <input
                        type="text"
                        value={skill.name}
                        onChange={(e) => updateSkill(index, "name", e.target.value)}
                        className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                      />
                    </FormField>
                    <FormField label="技能描述" hint="简要说明这个技能的作用">
                      <input
                        type="text"
                        value={skill.description}
                        onChange={(e) => updateSkill(index, "description", e.target.value)}
                        className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                      />
                    </FormField>
                    <FormField label="技能提示词" hint="Agent 执行这个技能时使用的指令">
                      <textarea
                        value={skill.prompt}
                        onChange={(e) => updateSkill(index, "prompt", e.target.value)}
                        rows={4}
                        className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                      />
                    </FormField>
                    <button onClick={() => setEditingSkillIndex(null)} className="px-3 py-1 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg">
                      完成
                    </button>
                  </div>
                ) : (
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-brand-400">⚡</span>
                        <span className="text-zinc-200 font-medium">{skill.name}</span>
                      </div>
                      <p className="text-sm text-zinc-500 mt-1">{skill.description}</p>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => setEditingSkillIndex(index)} className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg">
                        编辑
                      </button>
                      <button onClick={() => removeSkill(index)} className="px-3 py-1 text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg">
                        删除
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* 添加新技能 */}
          <div className="p-4 border border-dashed border-surface-3 rounded-lg">
            <h4 className="text-sm font-medium text-zinc-400 mb-3">添加新技能</h4>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="text"
                  value={newSkill.name}
                  onChange={(e) => setNewSkill({ ...newSkill, name: e.target.value })}
                  placeholder="技能名称，如：竞品分析"
                  className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                />
                <input
                  type="text"
                  value={newSkill.description}
                  onChange={(e) => setNewSkill({ ...newSkill, description: e.target.value })}
                  placeholder="技能描述"
                  className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                />
              </div>
              <textarea
                value={newSkill.prompt}
                onChange={(e) => setNewSkill({ ...newSkill, prompt: e.target.value })}
                placeholder="技能提示词，如：请分析以下产品的竞品情况，包括..."
                rows={3}
                className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
              />
              <button onClick={addSkill} disabled={!newSkill.name.trim()} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg disabled:opacity-50 text-sm">
                添加技能
              </button>
            </div>
          </div>
        </div>

        {/* 默认自主权设置 */}
        <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
          <h3 className="font-medium text-zinc-200 mb-4">🎛️ 默认自主权设置</h3>
          <p className="text-sm text-zinc-500 mb-4">
            设置 Agent 在各阶段是否默认自主执行（每个项目可以单独覆盖）
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {PHASES.map((phase) => (
              <label key={phase.id} className="flex items-center gap-2 cursor-pointer p-2 rounded-lg hover:bg-surface-3">
                <input
                  type="checkbox"
                  checked={editForm.autonomy_defaults?.[phase.id] !== false}
                  onChange={(e) => {
                    setEditForm({
                      ...editForm,
                      autonomy_defaults: { ...editForm.autonomy_defaults, [phase.id]: e.target.checked },
                    });
                  }}
                />
                <span className="text-sm text-zinc-300">{phase.name}</span>
              </label>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============== 调试日志 ==============
function LogsSection({ logs, onRefresh }: { logs: any[]; onRefresh?: () => void }) {
  const [selectedLog, setSelectedLog] = useState<any>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await onRefresh?.();
    setIsRefreshing(false);
  };

  const handleExport = async (format: "json" | "csv") => {
    try {
      const data = await settingsAPI.exportLogs();
      if (format === "json") {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `logs_${new Date().toISOString().split("T")[0]}.json`;
        a.click();
      }
    } catch (err) {
      alert("导出失败");
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">调试日志</h2>
          <p className="text-sm text-zinc-500 mt-1">查看每次 AI 调用的详细信息</p>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={handleRefresh} 
            disabled={isRefreshing}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:bg-zinc-600 rounded-lg text-white transition-colors"
          >
            {isRefreshing ? "⏳ 刷新中..." : "🔄 刷新"}
          </button>
          <button onClick={() => handleExport("json")} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">
            导出 JSON
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-3">
              <th className="text-left py-3 px-3 text-zinc-500">时间</th>
              <th className="text-left py-3 px-3 text-zinc-500">阶段</th>
              <th className="text-left py-3 px-3 text-zinc-500">操作</th>
              <th className="text-left py-3 px-3 text-zinc-500">模型</th>
              <th className="text-right py-3 px-3 text-zinc-500">Tokens</th>
              <th className="text-right py-3 px-3 text-zinc-500">耗时</th>
              <th className="text-right py-3 px-3 text-zinc-500">成本</th>
              <th className="py-3 px-3"></th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-zinc-500">暂无日志记录</td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id} className="border-b border-surface-3/50 hover:bg-surface-2">
                  <td className="py-3 px-3 text-zinc-400">{log.created_at?.slice(0, 19)}</td>
                  <td className="py-3 px-3 text-zinc-300">{log.phase}</td>
                  <td className="py-3 px-3 text-zinc-300">{log.operation}</td>
                  <td className="py-3 px-3 text-zinc-400 text-xs">{log.model}</td>
                  <td className="py-3 px-3 text-right text-zinc-400">{(log.tokens_in || 0) + (log.tokens_out || 0)}</td>
                  <td className="py-3 px-3 text-right text-zinc-400">{log.duration_ms}ms</td>
                  <td className="py-3 px-3 text-right text-green-400">${(log.cost || 0).toFixed(4)}</td>
                  <td className="py-3 px-3">
                    <button onClick={() => setSelectedLog(log)} className="text-xs text-brand-400 hover:text-brand-300">
                      详情
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 日志详情弹窗 */}
      {selectedLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSelectedLog(null)} />
          <div className="relative w-full max-w-3xl max-h-[80vh] overflow-auto bg-surface-1 border border-surface-3 rounded-xl p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-medium text-zinc-100">日志详情</h3>
              <button onClick={() => setSelectedLog(null)} className="text-zinc-400 hover:text-zinc-200">✕</button>
            </div>
            <div className="space-y-4">
              <div>
                <h4 className="text-sm text-zinc-500 mb-2">输入 (Prompt)</h4>
                <pre className="p-4 bg-surface-2 rounded-lg text-sm text-zinc-300 whitespace-pre-wrap overflow-auto max-h-60">
                  {selectedLog.prompt_input || "无"}
                </pre>
              </div>
              <div>
                <h4 className="text-sm text-zinc-500 mb-2">输出 (Response)</h4>
                <pre className="p-4 bg-surface-2 rounded-lg text-sm text-zinc-300 whitespace-pre-wrap overflow-auto max-h-60">
                  {selectedLog.prompt_output || "无"}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
