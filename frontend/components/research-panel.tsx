// frontend/components/research-panel.tsx
// 功能: 消费者调研报告展示面板
// 主要功能: 展示调研报告、人物卡片可勾选、内容可编辑

"use client";

import { useState, useMemo, useCallback } from "react";
import { fieldAPI } from "@/lib/api";

// 人物小传类型
interface Persona {
  id: string;
  name: string;
  basic_info: {
    age_range?: string;
    industry?: string;
    position?: string;
    [key: string]: string | undefined;
  };
  background: string;
  pain_points: string[];
  selected: boolean;
}

// 调研报告类型
interface ResearchData {
  summary: string;
  consumer_profile: Record<string, string>;
  pain_points: string[];
  value_propositions: string[];
  personas: Persona[];
  sources?: string[];
}

interface ResearchPanelProps {
  projectId: string;
  fieldId: string;
  content: string;
  onUpdate?: () => void;
  onAdvance?: () => void;  // 确认进入下一阶段
}

export function ResearchPanel({
  projectId,
  fieldId,
  content,
  onUpdate,
  onAdvance,
}: ResearchPanelProps) {
  // 解析调研数据
  const initialData = useMemo<ResearchData | null>(() => {
    try {
      return JSON.parse(content);
    } catch {
      return null;
    }
  }, [content]);

  const [data, setData] = useState<ResearchData | null>(initialData);
  const [isSaving, setIsSaving] = useState(false);
  const [editingPersonaId, setEditingPersonaId] = useState<string | null>(null);

  // 切换人物选中状态
  const togglePersonaSelected = useCallback((personaId: string) => {
    if (!data) return;
    
    setData({
      ...data,
      personas: data.personas.map((p) =>
        p.id === personaId ? { ...p, selected: !p.selected } : p
      ),
    });
  }, [data]);

  // 更新人物信息
  const updatePersona = useCallback((personaId: string, updates: Partial<Persona>) => {
    if (!data) return;
    
    setData({
      ...data,
      personas: data.personas.map((p) =>
        p.id === personaId ? { ...p, ...updates } : p
      ),
    });
  }, [data]);

  // 保存到服务器
  const handleSave = async () => {
    if (!data) return;
    
    setIsSaving(true);
    try {
      await fieldAPI.update(fieldId, {
        content: JSON.stringify(data, null, 2),
      });
      onUpdate?.();
    } catch (err) {
      console.error("保存失败:", err);
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsSaving(false);
    }
  };

  if (!data) {
    return (
      <div className="p-6 text-center text-red-400">
        <p>调研报告数据解析失败</p>
        <p className="text-sm mt-2 text-zinc-500">请在右侧对话框让Agent重新生成</p>
      </div>
    );
  }

  const selectedCount = data.personas.filter((p) => p.selected).length;

  // 保存并进入下一步
  const handleSaveAndAdvance = async () => {
    await handleSave();
    onAdvance?.();
  };

  return (
    <div className="h-full flex flex-col">
      {/* 可滚动内容区 */}
      <div className="flex-1 overflow-auto p-6 max-w-4xl mx-auto w-full space-y-8">

      {/* 总体概述 */}
      <section className="bg-surface-2 border border-surface-3 rounded-xl p-5">
        <h2 className="text-lg font-semibold text-zinc-200 mb-4">总体概述</h2>
        <textarea
          value={data.summary}
          onChange={(e) => setData({ ...data, summary: e.target.value })}
          className="w-full bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg p-4 text-zinc-300 text-sm min-h-[120px] leading-relaxed focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all resize-none"
        />
      </section>

      {/* 消费者画像 */}
      <section className="bg-surface-2 border border-surface-3 rounded-xl p-5">
        <h2 className="text-lg font-semibold text-zinc-200 mb-4">消费者画像</h2>
        <div className="grid grid-cols-2 gap-4">
          {Object.entries(data.consumer_profile).map(([key, value]) => (
            <div key={key} className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400">{key}</label>
              <input
                type="text"
                value={String(value)}
                onChange={(e) =>
                  setData({
                    ...data,
                    consumer_profile: {
                      ...data.consumer_profile,
                      [key]: e.target.value,
                    },
                  })
                }
                className="w-full bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-3 py-2.5 text-sm text-zinc-300 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all"
              />
            </div>
          ))}
        </div>
      </section>

      {/* 核心痛点 */}
      <section className="bg-surface-2 border border-surface-3 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-zinc-200">核心痛点</h2>
          <button
            onClick={() => setData({ ...data, pain_points: [...data.pain_points, ""] })}
            className="px-3 py-1 text-xs bg-surface-3 hover:bg-surface-4 text-zinc-400 hover:text-zinc-200 rounded-lg transition-colors"
          >
            + 添加痛点
          </button>
        </div>
        <ul className="space-y-3">
          {data.pain_points.map((point, index) => (
            <li key={index} className="group flex items-start gap-3">
              <span className="text-amber-400 mt-2.5 text-lg">•</span>
              <input
                type="text"
                value={point}
                placeholder="输入痛点描述..."
                onChange={(e) => {
                  const newPoints = [...data.pain_points];
                  newPoints[index] = e.target.value;
                  setData({ ...data, pain_points: newPoints });
                }}
                className="flex-1 bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-4 py-2.5 text-sm text-zinc-300 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all"
              />
              <button
                onClick={() => {
                  const newPoints = data.pain_points.filter((_, i) => i !== index);
                  setData({ ...data, pain_points: newPoints });
                }}
                className="opacity-0 group-hover:opacity-100 p-2 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded-lg transition-all"
                title="删除此痛点"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* 价值主张 */}
      <section className="bg-surface-2 border border-surface-3 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-zinc-200">价值主张</h2>
          <button
            onClick={() => setData({ ...data, value_propositions: [...data.value_propositions, ""] })}
            className="px-3 py-1 text-xs bg-surface-3 hover:bg-surface-4 text-zinc-400 hover:text-zinc-200 rounded-lg transition-colors"
          >
            + 添加主张
          </button>
        </div>
        <ul className="space-y-3">
          {data.value_propositions.map((prop, index) => (
            <li key={index} className="group flex items-start gap-3">
              <span className="text-green-400 mt-2.5 text-lg">✓</span>
              <input
                type="text"
                value={prop}
                placeholder="输入价值主张..."
                onChange={(e) => {
                  const newProps = [...data.value_propositions];
                  newProps[index] = e.target.value;
                  setData({ ...data, value_propositions: newProps });
                }}
                className="flex-1 bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-4 py-2.5 text-sm text-zinc-300 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all"
              />
              <button
                onClick={() => {
                  const newProps = data.value_propositions.filter((_, i) => i !== index);
                  setData({ ...data, value_propositions: newProps });
                }}
                className="opacity-0 group-hover:opacity-100 p-2 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded-lg transition-all"
                title="删除此主张"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* 典型用户小传 */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-zinc-200">
            典型用户小传
          </h2>
          <span className="text-sm text-zinc-500">
            已选中 {selectedCount}/{data.personas.length} 个用于模拟
          </span>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.personas.map((persona) => (
            <PersonaCard
              key={persona.id}
              persona={persona}
              isEditing={editingPersonaId === persona.id}
              onToggleSelect={() => togglePersonaSelected(persona.id)}
              onEdit={() => setEditingPersonaId(persona.id)}
              onSaveEdit={() => setEditingPersonaId(null)}
              onUpdate={(updates) => updatePersona(persona.id, updates)}
            />
          ))}
        </div>
      </section>
      
      {/* 底部留白，避免被固定按钮遮挡 */}
      <div className="h-24"></div>
      </div>
      
      {/* 底部固定按钮栏 */}
      <div className="shrink-0 px-6 py-4 border-t border-surface-3 bg-surface-1 flex items-center justify-between">
        <div className="text-sm text-zinc-500">
          已选中 <span className="text-brand-400 font-medium">{selectedCount}</span> 个用户画像用于后续模拟
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="px-5 py-2.5 bg-surface-3 hover:bg-surface-4 disabled:bg-zinc-700 text-zinc-300 rounded-lg text-sm font-medium transition-all"
          >
            {isSaving ? "⏳ 保存中..." : "💾 保存修改"}
          </button>
          <button
            onClick={handleSaveAndAdvance}
            disabled={isSaving}
            className="px-6 py-2.5 bg-brand-600 hover:bg-brand-700 disabled:bg-zinc-700 text-white rounded-lg text-sm font-medium transition-all shadow-lg hover:shadow-brand-600/25"
          >
            ✅ 确认，进入内涵设计
          </button>
        </div>
      </div>
    </div>
  );
}

// 人物卡片组件
interface PersonaCardProps {
  persona: Persona;
  isEditing: boolean;
  onToggleSelect: () => void;
  onEdit: () => void;
  onSaveEdit: () => void;
  onUpdate: (updates: Partial<Persona>) => void;
}

function PersonaCard({
  persona,
  isEditing,
  onToggleSelect,
  onEdit,
  onSaveEdit,
  onUpdate,
}: PersonaCardProps) {
  return (
    <div
      className={`border rounded-xl p-4 transition-all ${
        persona.selected
          ? "bg-surface-2 border-brand-500/50 shadow-lg shadow-brand-500/5"
          : "bg-surface-1 border-surface-3 opacity-70 hover:opacity-90"
      }`}
    >
      {/* 头部：选中和编辑 */}
      <div className="flex items-start justify-between mb-4">
        <button
          onClick={onToggleSelect}
          className={`flex items-center gap-2.5 text-sm font-semibold transition-colors ${
            persona.selected ? "text-brand-400" : "text-zinc-400 hover:text-zinc-300"
          }`}
        >
          <span
            className={`w-5 h-5 rounded-md border-2 flex items-center justify-center text-xs transition-all ${
              persona.selected
                ? "bg-brand-600 border-brand-600 text-white"
                : "border-zinc-600 hover:border-zinc-500"
            }`}
          >
            {persona.selected && "✓"}
          </span>
          {persona.name}
        </button>
        
        {isEditing ? (
          <button
            onClick={onSaveEdit}
            className="px-3 py-1 text-xs font-medium bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
          >
            完成
          </button>
        ) : (
          <button
            onClick={onEdit}
            className="px-3 py-1 text-xs text-zinc-500 hover:text-zinc-300 hover:bg-surface-3 rounded-lg transition-colors"
          >
            编辑
          </button>
        )}
      </div>

      {isEditing ? (
        // 编辑模式
        <div className="space-y-4 text-sm">
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-1.5 block">姓名</label>
            <input
              type="text"
              value={persona.name}
              onChange={(e) => onUpdate({ name: e.target.value })}
              className="w-full bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-3 py-2 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all"
            />
          </div>
          
          {/* 标签编辑 */}
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-1.5 block">基本信息标签</label>
            <div className="space-y-2">
              {Object.entries(persona.basic_info).map(([key, value]) => (
                <div key={key} className="flex items-center gap-2">
                  <span className="text-xs text-zinc-500 w-20 shrink-0">{key}:</span>
                  <input
                    type="text"
                    value={String(value || "")}
                    onChange={(e) => onUpdate({
                      basic_info: { ...persona.basic_info, [key]: e.target.value }
                    })}
                    className="flex-1 bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-all"
                  />
                </div>
              ))}
            </div>
          </div>
          
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-1.5 block">背景简介</label>
            <textarea
              value={persona.background}
              onChange={(e) => onUpdate({ background: e.target.value })}
              className="w-full bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-3 py-2 text-zinc-300 min-h-[80px] focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all resize-none"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-1.5 block">核心痛点（每行一个）</label>
            <textarea
              value={persona.pain_points.join("\n")}
              onChange={(e) =>
                onUpdate({ pain_points: e.target.value.split("\n").filter(Boolean) })
              }
              className="w-full bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-3 py-2 text-zinc-300 min-h-[80px] focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all resize-none"
            />
          </div>
        </div>
      ) : (
        // 展示模式
        <div className="space-y-3 text-sm">
          {/* 基本信息 */}
          <div className="flex flex-wrap gap-2">
            {Object.entries(persona.basic_info).map(([key, value]) => (
              value && (
                <span
                  key={key}
                  className="px-2 py-0.5 bg-surface-3 rounded text-xs text-zinc-400"
                >
                  {value}
                </span>
              )
            ))}
          </div>

          {/* 背景简介 */}
          <p className="text-zinc-400 text-xs line-clamp-3">
            {persona.background}
          </p>

          {/* 核心痛点 */}
          <div>
            <p className="text-xs text-zinc-500 mb-1">痛点:</p>
            <ul className="space-y-0.5">
              {persona.pain_points.slice(0, 3).map((point, i) => (
                <li key={i} className="text-xs text-zinc-400 flex items-start gap-1">
                  <span className="text-amber-400">•</span>
                  <span className="line-clamp-1">{point}</span>
                </li>
              ))}
              {persona.pain_points.length > 3 && (
                <li className="text-xs text-zinc-500">
                  +{persona.pain_points.length - 3} 更多
                </li>
              )}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
