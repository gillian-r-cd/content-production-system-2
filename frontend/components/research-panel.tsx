// frontend/components/research-panel.tsx
// 功能: 消费者调研报告展示面板
// 主要功能: 展示调研报告、人物卡片可勾选、内容可编辑

"use client";

import { useState, useMemo, useCallback } from "react";
import { fieldAPI, blockAPI } from "@/lib/api";

// 人物小传类型 - 匹配实际 AI 输出格式
interface Persona {
  id: string;
  name: string;
  basic_info: {
    age?: number | string;
    gender?: string;
    city?: string;
    education?: string;
    occupation?: string;
    income_range?: string;
    tech_background?: string;
    ai_usage_status?: string;
    // 兼容旧格式
    age_range?: string;
    industry?: string;
    position?: string;
    [key: string]: string | number | undefined;
  };
  background: string;
  pain_points: string[];
  selected: boolean;
}

// 消费者画像类型 - 匹配实际 AI 输出格式
interface ConsumerProfile {
  age_range?: string;
  occupation?: string[] | string;  // 可能是数组或字符串
  characteristics?: string[];
  behaviors?: string[];
  [key: string]: string | string[] | undefined;
}

// 调研报告类型 - 完整匹配实际格式
interface ResearchData {
  summary: string;
  consumer_profile: ConsumerProfile;
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
  isBlock?: boolean;  // true = 使用 blockAPI 保存（ContentBlock），false/undefined = 使用 fieldAPI（ProjectField）
}

export function ResearchPanel({
  projectId,
  fieldId,
  content,
  onUpdate,
  onAdvance,
  isBlock = false,
}: ResearchPanelProps) {
  // 解析调研数据（自动补全缺失字段防止渲染崩溃）
  const initialData = useMemo<ResearchData | null>(() => {
    try {
      const raw = JSON.parse(content);
      if (!raw || typeof raw !== "object") return null;
      return {
        summary: raw.summary || "",
        consumer_profile: raw.consumer_profile || {},
        pain_points: raw.pain_points || raw.main_pain_points || [],
        value_propositions: raw.value_propositions || raw.value_proposition || [],
        personas: (raw.personas || []).map((p: any, idx: number) => {
          // background 可能是 string 或 {story, context} 对象
          let bg = p.background || p.story || "";
          if (typeof bg === "object" && bg !== null) {
            bg = bg.story || bg.context || JSON.stringify(bg);
          }
          return {
            id: p.id || `persona_${idx}`,
            name: p.name || `用户 ${idx + 1}`,
            basic_info: p.basic_info || {},
            background: String(bg),
            pain_points: Array.isArray(p.pain_points) ? p.pain_points.map((pt: any) => typeof pt === "string" ? pt : JSON.stringify(pt)) : [],
            selected: p.selected !== undefined ? p.selected : true,
          };
        }),
        sources: raw.sources || [],
      };
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

  // 保存到服务器（自动判断使用 blockAPI 或 fieldAPI）
  const handleSave = async () => {
    if (!data) return;
    
    setIsSaving(true);
    try {
      const payload = { content: JSON.stringify(data, null, 2) };
      if (isBlock) {
        await blockAPI.update(fieldId, payload);
      } else {
        await fieldAPI.update(fieldId, payload);
      }
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

  const selectedCount = (data.personas || []).filter((p) => p.selected).length;

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
        <div className="space-y-5">
          {/* 年龄范围 */}
          {data.consumer_profile.age_range && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400">年龄范围</label>
              <input
                type="text"
                value={data.consumer_profile.age_range}
                onChange={(e) =>
                  setData({
                    ...data,
                    consumer_profile: {
                      ...data.consumer_profile,
                      age_range: e.target.value,
                    },
                  })
                }
                className="w-full bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-3 py-2.5 text-sm text-zinc-300 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all"
              />
            </div>
          )}
          
          {/* 职业（数组） */}
          {data.consumer_profile.occupation && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-zinc-400">职业类型</label>
                <button
                  onClick={() => {
                    const occupations: string[] = Array.isArray(data.consumer_profile.occupation) 
                      ? data.consumer_profile.occupation 
                      : [data.consumer_profile.occupation || ""];
                    setData({
                      ...data,
                      consumer_profile: {
                        ...data.consumer_profile,
                        occupation: [...occupations, ""],
                      },
                    });
                  }}
                  className="px-2 py-0.5 text-xs bg-surface-3 hover:bg-surface-4 text-zinc-400 hover:text-zinc-200 rounded transition-colors"
                >
                  + 添加
                </button>
              </div>
              <div className="space-y-2">
                {(Array.isArray(data.consumer_profile.occupation) 
                  ? data.consumer_profile.occupation 
                  : [data.consumer_profile.occupation]
                ).map((occ, idx) => (
                  <div key={idx} className="flex items-center gap-2 group">
                    <input
                      type="text"
                      value={occ || ""}
                      onChange={(e) => {
                        const occupations: string[] = Array.isArray(data.consumer_profile.occupation) 
                          ? [...data.consumer_profile.occupation]
                          : [data.consumer_profile.occupation || ""];
                        occupations[idx] = e.target.value;
                        setData({
                          ...data,
                          consumer_profile: {
                            ...data.consumer_profile,
                            occupation: occupations,
                          },
                        });
                      }}
                      className="flex-1 bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-3 py-2 text-sm text-zinc-300 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-all"
                    />
                    <button
                      onClick={() => {
                        const occupations = Array.isArray(data.consumer_profile.occupation) 
                          ? data.consumer_profile.occupation.filter((_, i) => i !== idx)
                          : [];
                        setData({
                          ...data,
                          consumer_profile: {
                            ...data.consumer_profile,
                            occupation: occupations,
                          },
                        });
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1.5 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded transition-all"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {/* 特征（数组） */}
          {data.consumer_profile.characteristics && Array.isArray(data.consumer_profile.characteristics) && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-zinc-400">典型特征</label>
                <button
                  onClick={() => setData({
                    ...data,
                    consumer_profile: {
                      ...data.consumer_profile,
                      characteristics: [...(data.consumer_profile.characteristics || []), ""],
                    },
                  })}
                  className="px-2 py-0.5 text-xs bg-surface-3 hover:bg-surface-4 text-zinc-400 hover:text-zinc-200 rounded transition-colors"
                >
                  + 添加
                </button>
              </div>
              <div className="space-y-2">
                {data.consumer_profile.characteristics.map((char, idx) => (
                  <div key={idx} className="flex items-center gap-2 group">
                    <span className="text-brand-400 text-sm">•</span>
                    <input
                      type="text"
                      value={char}
                      onChange={(e) => {
                        const chars = [...(data.consumer_profile.characteristics || [])];
                        chars[idx] = e.target.value;
                        setData({
                          ...data,
                          consumer_profile: {
                            ...data.consumer_profile,
                            characteristics: chars,
                          },
                        });
                      }}
                      className="flex-1 bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-3 py-2 text-sm text-zinc-300 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-all"
                    />
                    <button
                      onClick={() => {
                        const chars = (data.consumer_profile.characteristics || []).filter((_, i) => i !== idx);
                        setData({
                          ...data,
                          consumer_profile: {
                            ...data.consumer_profile,
                            characteristics: chars,
                          },
                        });
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1.5 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded transition-all"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {/* 行为（数组） */}
          {data.consumer_profile.behaviors && Array.isArray(data.consumer_profile.behaviors) && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-zinc-400">典型行为</label>
                <button
                  onClick={() => setData({
                    ...data,
                    consumer_profile: {
                      ...data.consumer_profile,
                      behaviors: [...(data.consumer_profile.behaviors || []), ""],
                    },
                  })}
                  className="px-2 py-0.5 text-xs bg-surface-3 hover:bg-surface-4 text-zinc-400 hover:text-zinc-200 rounded transition-colors"
                >
                  + 添加
                </button>
              </div>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {data.consumer_profile.behaviors.map((behavior, idx) => (
                  <div key={idx} className="flex items-start gap-2 group">
                    <span className="text-green-400 text-sm mt-2.5">→</span>
                    <textarea
                      value={behavior}
                      onChange={(e) => {
                        const behaviors = [...(data.consumer_profile.behaviors || [])];
                        behaviors[idx] = e.target.value;
                        setData({
                          ...data,
                          consumer_profile: {
                            ...data.consumer_profile,
                            behaviors: behaviors,
                          },
                        });
                      }}
                      rows={2}
                      className="flex-1 bg-surface-1 border border-surface-3 hover:border-surface-4 rounded-lg px-3 py-2 text-sm text-zinc-300 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-all resize-none"
                    />
                    <button
                      onClick={() => {
                        const behaviors = (data.consumer_profile.behaviors || []).filter((_, i) => i !== idx);
                        setData({
                          ...data,
                          consumer_profile: {
                            ...data.consumer_profile,
                            behaviors: behaviors,
                          },
                        });
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1.5 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded transition-all"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
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

      {/* 信息来源（DeepResearch引用） */}
      {data.sources && data.sources.length > 0 && (
        <section className="bg-surface-2 border border-surface-3 rounded-xl p-5">
          <h2 className="text-lg font-semibold text-zinc-200 mb-4">
            📚 信息来源 ({data.sources.length})
          </h2>
          <ul className="space-y-2">
            {data.sources.map((source, index) => (
              <li key={index} className="flex items-start gap-2 group">
                <span className="text-zinc-500 text-sm shrink-0">[{index + 1}]</span>
                <a
                  href={source}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-blue-400 hover:text-blue-300 hover:underline break-all transition-colors"
                  title={source}
                >
                  {source.length > 80 ? source.substring(0, 80) + "..." : source}
                </a>
              </li>
            ))}
          </ul>
          <p className="text-xs text-zinc-600 mt-4">
            以上信息来源由 DeepResearch 自动搜索并提取
          </p>
        </section>
      )}
      
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
          {/* 基本信息标签 */}
          <div className="flex flex-wrap gap-1.5">
            {persona.basic_info.age && (
              <span className="px-2 py-0.5 bg-surface-3 rounded text-xs text-zinc-400">
                {persona.basic_info.age}岁
              </span>
            )}
            {persona.basic_info.gender && (
              <span className="px-2 py-0.5 bg-surface-3 rounded text-xs text-zinc-400">
                {persona.basic_info.gender}
              </span>
            )}
            {persona.basic_info.city && (
              <span className="px-2 py-0.5 bg-surface-3 rounded text-xs text-zinc-400">
                {persona.basic_info.city}
              </span>
            )}
            {persona.basic_info.occupation && (
              <span className="px-2 py-0.5 bg-brand-600/20 text-brand-400 rounded text-xs">
                {persona.basic_info.occupation}
              </span>
            )}
            {persona.basic_info.income_range && (
              <span className="px-2 py-0.5 bg-green-600/20 text-green-400 rounded text-xs">
                {persona.basic_info.income_range}
              </span>
            )}
          </div>
          
          {/* AI 使用状态 */}
          {persona.basic_info.ai_usage_status && (
            <div className="text-xs text-zinc-500 bg-surface-1 rounded px-2 py-1.5">
              <span className="text-zinc-400">AI使用:</span> {persona.basic_info.ai_usage_status}
            </div>
          )}

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
                  <span className="line-clamp-2">{point}</span>
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
