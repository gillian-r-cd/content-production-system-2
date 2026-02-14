// frontend/components/settings/agent-settings-section.tsx
// 功能: Agent 设置 — 工具、技能配置

"use client";

import { useState, useEffect } from "react";
import { settingsAPI } from "@/lib/api";
import { FormField } from "./shared";

export function AgentSettingsSection({ settings, onRefresh }: { settings: any; onRefresh: () => void }) {
  const [editForm, setEditForm] = useState<any>(settings || { tools: [], skills: [] });
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
      name: "内容块生成", 
      icon: "✍️", 
      desc: "根据上下文和依赖关系生成内容块内容",
      defaultPrompt: "你是一个专业的内容创作者。基于上下文和依赖内容块，生成高质量的内容。\n遵循创作者特质、保持风格一致性。"
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
      desc: "添加/删除/移动组和内容块，修改项目结构",
      defaultPrompt: "你是项目架构师。根据用户的自然语言描述，识别需要进行的架构操作（添加组/内容块、删除、移动），\n并调用相应的操作函数完成修改。"
    },
    { 
      id: "outline_generator", 
      name: "大纲生成", 
      icon: "📋", 
      desc: "基于项目上下文生成内容大纲",
      defaultPrompt: "你是一个内容策划专家。基于项目意图和消费者调研结果，\n生成结构化的内容大纲，包括主题、章节、关键点和预计内容块。"
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

      </div>
    </div>
  );
}
