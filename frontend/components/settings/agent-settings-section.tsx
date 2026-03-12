// frontend/components/settings/agent-settings-section.tsx
// 功能: Agent 设置 — 工具、技能配置

"use client";

import { useState, useEffect } from "react";
import { settingsAPI } from "@/lib/api";
import { FormField, useSettingsUiIsJa } from "./shared";

interface AgentSkill {
  name: string;
  description: string;
  prompt: string;
}

interface AgentSettingsData {
  tools?: string[];
  skills?: AgentSkill[];
  tool_prompts?: Record<string, string>;
}

export function AgentSettingsSection({ settings, onRefresh }: { settings: AgentSettingsData | null; onRefresh: () => void }) {
  const isJa = useSettingsUiIsJa();
  const [editForm, setEditForm] = useState<AgentSettingsData>(settings || { tools: [], skills: [] });
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
      alert(isJa ? "保存しました" : "保存成功");
    } catch {
      alert(isJa ? "保存に失敗しました" : "保存失败");
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
      desc: isJa ? "ネット上で詳細調査を行い、対象ユーザーを自動で検索・分析します" : "网络深度调研，自动搜索和分析目标用户",
      defaultPrompt: isJa
        ? "あなたは専門のユーザーリサーチ担当です。プロジェクト意図に基づき、次を実行してください:\n1. 対象ユーザー群の特徴と行動を調査する\n2. ユーザーの課題とニーズを分析する\n3. 構造化された顧客調査レポートを生成する"
        : "你是一个专业的用户研究专家。基于项目意图，你需要：\n1. 调研目标用户群体的特征和行为\n2. 分析用户的痛点和需求\n3. 生成结构化的消费者调研报告"
    },
    { 
      id: "generate_field", 
      name: isJa ? "内容ブロック生成" : "内容块生成", 
      icon: "✍️", 
      desc: isJa ? "文脈と依存関係をもとに内容ブロックを生成します" : "根据上下文和依赖关系生成内容块内容",
      defaultPrompt: isJa
        ? "あなたは専門のコンテンツ制作者です。文脈と依存内容ブロックをもとに高品質な内容を生成してください。\nクリエイター特性に従い、文体とトーンの一貫性を保ってください。"
        : "你是一个专业的内容创作者。基于上下文和依赖内容块，生成高质量的内容。\n遵循创作者特质、保持风格一致性。"
    },
    { 
      id: "simulate_consumer", 
      name: isJa ? "顧客シミュレーション" : "消费者模拟", 
      icon: "🎭", 
      desc: isJa ? "顧客と内容のインタラクション体験をシミュレーションします" : "模拟消费者与内容的交互体验",
      defaultPrompt: isJa
        ? "あなたは典型的な対象顧客になりきり、ユーザーペルソナに基づいて内容体験をシミュレーションしてください。\n率直なフィードバック、疑問点、改善提案を提示してください。"
        : "你将扮演一个典型的目标消费者，基于用户画像进行内容体验模拟。\n提供真实的反馈、困惑点和改进建议。"
    },
    { 
      id: "evaluate_content", 
      name: isJa ? "内容評価" : "内容评估", 
      icon: "📊", 
      desc: isJa ? "評価テンプレートに基づいて内容品質を評価し、改善提案を行います" : "根据评估模板评估内容质量并给出建议",
      defaultPrompt: isJa
        ? "あなたはコンテンツ品質評価の専門家です。評価軸に基づいて内容を採点・分析し、\n具体的な改善提案を提示してください。"
        : "你是一个内容质量评估专家。根据评估维度对内容进行打分和分析，\n给出具体的改进建议。"
    },
    { 
      id: "architecture_writer", 
      name: isJa ? "構成操作" : "架构操作", 
      icon: "🏗️", 
      desc: isJa ? "グループや内容ブロックの追加・削除・移動を行い、プロジェクト構造を更新します" : "添加/删除/移动组和内容块，修改项目结构",
      defaultPrompt: isJa
        ? "あなたはプロジェクトアーキテクトです。ユーザーの自然言語指示から必要な構成操作（グループ/内容ブロックの追加、削除、移動）を判断し、\n対応する操作を実行してください。"
        : "你是项目架构师。根据用户的自然语言描述，识别需要进行的架构操作（添加组/内容块、删除、移动），\n并调用相应的操作函数完成修改。"
    },
    { 
      id: "outline_generator", 
      name: isJa ? "アウトライン生成" : "大纲生成", 
      icon: "📋", 
      desc: isJa ? "プロジェクト文脈をもとに内容アウトラインを生成します" : "基于项目上下文生成内容大纲",
      defaultPrompt: isJa
        ? "あなたはコンテンツ企画の専門家です。プロジェクト意図と顧客調査結果をもとに、\nテーマ、章立て、要点、想定内容ブロックを含む構造化アウトラインを生成してください。"
        : "你是一个内容策划专家。基于项目意图和消费者调研结果，\n生成结构化的内容大纲，包括主题、章节、关键点和预计内容块。"
    },
    { 
      id: "persona_manager", 
      name: isJa ? "ペルソナ管理" : "人物管理", 
      icon: "👥", 
      desc: isJa ? "顧客ペルソナの作成・編集・選択を行います" : "创建、编辑、选择消费者画像",
      defaultPrompt: isJa
        ? "あなたはユーザーリサーチの専門家です。顧客ペルソナの管理を支援してください。\n新規作成、既存編集、シミュレーション向けの推奨ペルソナ選定を行います。"
        : "你是用户研究专家。帮助用户管理消费者画像，\n包括创建新画像、编辑现有画像、推荐合适的画像用于模拟。"
    },
    { 
      id: "skill_manager", 
      name: isJa ? "スキル管理" : "技能管理", 
      icon: "⚡", 
      desc: isJa ? "再利用可能な AI スキルを管理・適用します" : "管理和应用可复用的AI技能",
      defaultPrompt: isJa
        ? "あなたは AI スキル管理の専門家です。再利用可能な AI スキルの閲覧、作成、適用を支援してください。\n各スキルは再利用可能なプロンプトテンプレートです。"
        : "你是AI技能管理专家。帮助用户查看、创建、应用可复用的AI技能，\n每个技能是一个可重复使用的提示词模板。"
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
    const newSkills = [...(editForm.skills || [])];
    newSkills[index] = { ...newSkills[index], [key]: value } as AgentSkill;
    setEditForm({ ...editForm, skills: newSkills });
  };

  const removeSkill = (index: number) => {
    if (!confirm(isJa ? "このスキルを削除しますか？" : "确定删除这个技能？")) return;
    const newSkills = (editForm.skills || []).filter((_, i: number) => i !== index);
    setEditForm({ ...editForm, skills: newSkills });
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">{isJa ? "Agent 設定" : "Agent 设置"}</h2>
          <p className="text-sm text-zinc-500 mt-1">{isJa ? "AI Agent が利用できるツールとカスタムスキルを設定します" : "配置 AI Agent 可以使用的工具和自定义技能"}</p>
        </div>
        <button onClick={handleSave} disabled={isSaving} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg disabled:opacity-50">
          {isSaving ? (isJa ? "保存中..." : "保存中...") : (isJa ? "設定を保存" : "保存设置")}
        </button>
      </div>

      <div className="space-y-6">
        {/* 可用工具 */}
        <div className="p-5 bg-surface-2 border border-surface-3 rounded-xl">
          <h3 className="font-medium text-zinc-200 mb-4">{isJa ? "🛠️ 利用可能なツール" : "🛠️ 可用工具"}</h3>
          <p className="text-sm text-zinc-500 mb-4">{isJa ? "Agent が対話中に呼び出せるツールを選択します。ツールをクリックするとプロンプトを編集できます" : "选择 Agent 在对话中可以调用的工具，点击工具可编辑其提示词"}</p>
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
                        {editingToolId === tool.id ? (isJa ? "折りたたむ" : "收起") : (isJa ? "プロンプトを編集" : "编辑提示词")}
                      </button>
                    </div>
                    <p className="text-sm text-zinc-500 mt-1">{tool.desc}</p>
                    
                    {/* 提示词编辑区 */}
                    {editingToolId === tool.id && (
                      <div className="mt-3 pt-3 border-t border-surface-3">
                        <label className="block text-xs text-zinc-400 mb-1">{isJa ? "ツールプロンプト" : "工具提示词"}</label>
                        <textarea
                          value={toolPrompts[tool.id] || tool.defaultPrompt}
                          onChange={(e) => updateToolPrompt(tool.id, e.target.value)}
                          rows={4}
                          className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                          placeholder={tool.defaultPrompt}
                        />
                        <p className="text-xs text-zinc-600 mt-1">
                          {isJa ? "このプロンプトは Agent が当該ツールを呼び出す際のシステム指示として使われます" : "此提示词将用于 Agent 调用该工具时的系统指令"}
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
          <h3 className="font-medium text-zinc-200 mb-4">{isJa ? "⚡ カスタムスキル" : "⚡ 自定义技能"}</h3>
          <p className="text-sm text-zinc-500 mb-4">
            {isJa ? "スキルは Agent が実行できる特定タスクです。対話中に @ で呼び出せます。" : "技能是 Agent 可以执行的特定任务。你可以在与 Agent 对话时通过 @ 调用技能。"}
          </p>

          {/* 现有技能列表 */}
          <div className="space-y-3 mb-4">
            {(editForm.skills || []).map((skill, index: number) => (
              <div key={index} className="p-4 bg-surface-1 border border-surface-3 rounded-lg">
                {editingSkillIndex === index ? (
                  <div className="space-y-3">
                    <FormField label={isJa ? "スキル名" : "技能名称"}>
                      <input
                        type="text"
                        value={skill.name}
                        onChange={(e) => updateSkill(index, "name", e.target.value)}
                        className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                      />
                    </FormField>
                    <FormField label={isJa ? "スキル説明" : "技能描述"} hint={isJa ? "このスキルの役割を簡潔に説明します" : "简要说明这个技能的作用"}>
                      <input
                        type="text"
                        value={skill.description}
                        onChange={(e) => updateSkill(index, "description", e.target.value)}
                        className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                      />
                    </FormField>
                    <FormField label={isJa ? "スキルプロンプト" : "技能提示词"} hint={isJa ? "Agent がこのスキルを実行する際に使う指示" : "Agent 执行这个技能时使用的指令"}>
                      <textarea
                        value={skill.prompt}
                        onChange={(e) => updateSkill(index, "prompt", e.target.value)}
                        rows={4}
                        className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                      />
                    </FormField>
                    <button onClick={() => setEditingSkillIndex(null)} className="px-3 py-1 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg">
                      {isJa ? "完了" : "完成"}
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
                        {isJa ? "編集" : "编辑"}
                      </button>
                      <button onClick={() => removeSkill(index)} className="px-3 py-1 text-sm bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg">
                        {isJa ? "削除" : "删除"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* 添加新技能 */}
          <div className="p-4 border border-dashed border-surface-3 rounded-lg">
            <h4 className="text-sm font-medium text-zinc-400 mb-3">{isJa ? "新しいスキルを追加" : "添加新技能"}</h4>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="text"
                  value={newSkill.name}
                  onChange={(e) => setNewSkill({ ...newSkill, name: e.target.value })}
                  placeholder={isJa ? "スキル名。例: 競合分析" : "技能名称，如：竞品分析"}
                  className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                />
                <input
                  type="text"
                  value={newSkill.description}
                  onChange={(e) => setNewSkill({ ...newSkill, description: e.target.value })}
                  placeholder={isJa ? "スキル説明" : "技能描述"}
                  className="px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
                />
              </div>
              <textarea
                value={newSkill.prompt}
                onChange={(e) => setNewSkill({ ...newSkill, prompt: e.target.value })}
                placeholder={isJa ? "スキルプロンプト。例: 以下の製品の競合状況を分析してください。含める項目は..." : "技能提示词，如：请分析以下产品的竞品情况，包括..."}
                rows={3}
                className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm"
              />
              <button onClick={addSkill} disabled={!newSkill.name.trim()} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg disabled:opacity-50 text-sm">
                {isJa ? "スキルを追加" : "添加技能"}
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
