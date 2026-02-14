// frontend/components/eval-field-editors.tsx
// 功能: Eval V2 专用字段编辑器集合
// 5个 special_handler 对应 5 个专用 UI：
//   - eval_persona_setup: 目标消费者画像选择/创建
//   - eval_task_config: 评估任务配置（卡片式）
//   - eval_report: 统一评估报告面板（执行 + 评分 + 诊断 + LLM 日志，合并原 eval_execution/eval_grader_report/eval_diagnosis）

"use client";

import React, { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { evalAPI, blockAPI, graderAPI, settingsAPI } from "@/lib/api";
import { sendNotification } from "@/lib/utils";
import type { ContentBlock, EvalConfig, LLMCall, GraderData } from "@/lib/api";
import {
  Users, Plus, Trash2, Play, SlidersHorizontal, ChevronDown, ChevronRight,
  Eye, Save, RefreshCw, BarChart3, FileText, MessageSquare,
  AlertTriangle, CheckCircle, XCircle, Clock, Zap, Download, Pencil,
} from "lucide-react";


// ============== 通用类型 ==============

interface EvalFieldProps {
  block: ContentBlock;
  projectId: string;
  onUpdate?: () => void;
}

interface PersonaData {
  name: string;
  background: string;
  pain_points?: string[];
  source?: string;
  block_id?: string;
}

interface SimulatorData {
  id: string;
  name: string;
  description: string;
  simulator_type: string;
  interaction_type: string;           // 旧版: reading/dialogue/decision/exploration
  interaction_mode: string;           // 新版: review/dialogue/scenario/exploration
  prompt_template: string;
  secondary_prompt: string;           // 对话模式第二方提示词
  grader_template: string;
  evaluation_dimensions: string[];
  max_turns: number;
  is_preset: boolean;
}

interface TrialConfig {
  name: string;
  target_block_ids: string[];       // 核心：要评估的内容块 ID
  target_block_names: string[];     // 显示用
  simulator_type: string;           // 保留向后兼容
  simulator_id?: string;            // 新: 关联后台配置的模拟器
  simulator_name?: string;          // 显示用
  interaction_mode: string;
  persona_config: Record<string, any>;
  grader_ids: string[];             // 多个 Grader 评分器
  grader_names: string[];           // 显示用
  simulator_config?: Record<string, any>;
  order_index: number;
}

// 兼容旧格式
interface TaskConfig {
  name: string;
  simulator_type: string;
  interaction_mode: string;
  persona_config: Record<string, any>;
  grader_config: Record<string, any>;
  simulator_config?: Record<string, any>;
  target_block_ids?: string[];
  order_index: number;
}


// ============== 通用样式常量 ==============

const CARD = "bg-surface-2 border border-surface-3 rounded-xl";
const CARD_INNER = "bg-surface-1 border border-surface-3 rounded-lg";
const INPUT = "w-full bg-surface-1 border border-surface-3 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all";
const SELECT = "w-full bg-surface-1 border border-surface-3 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all appearance-none";
const TEXTAREA = "w-full bg-surface-1 border border-surface-3 rounded-lg px-3 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all resize-none";
const BTN_PRIMARY = "px-4 py-2 text-sm font-medium rounded-lg transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed";
const LABEL = "text-xs font-medium text-zinc-400 mb-1.5 block";
const EMPTY_STATE = "text-center py-12 border-2 border-dashed border-surface-3 rounded-xl";


// ============== 1. 目标消费者画像 ==============

export function EvalPersonaSetup({ block, projectId, onUpdate }: EvalFieldProps) {
  const [personas, setPersonas] = useState<PersonaData[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);

  useEffect(() => {
    if (block.content) {
      try {
        const data = JSON.parse(block.content);
        setPersonas(data.personas || []);
      } catch { setPersonas([]); }
    }
  }, [block.content]);

  const loadFromResearch = async () => {
    setLoading(true);
    try {
      const resp = await evalAPI.getPersonas(projectId) as any;
      const fetched = resp.personas || [];
      if (fetched.length > 0) {
        setPersonas(fetched);
      } else {
        alert("消费者调研中未找到画像，请先完成消费者调研或手动添加。");
      }
    } catch (e: any) {
      alert("加载失败: " + e.message);
    } finally { setLoading(false); }
  };

  const addPersona = () => {
    setPersonas([...personas, { name: "新消费者画像", background: "", pain_points: [] }]);
    setEditingIdx(personas.length);
  };

  const removePersona = (idx: number) => {
    const newP = [...personas];
    newP.splice(idx, 1);
    setPersonas(newP);
    if (editingIdx === idx) setEditingIdx(null);
  };

  const updatePersona = (idx: number, field: string, value: any) => {
    const newP = [...personas];
    (newP[idx] as any)[field] = value;
    setPersonas(newP);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await blockAPI.update(block.id, {
        content: JSON.stringify({ personas, source: "user_configured" }, null, 2),
        status: "completed",
      });
      onUpdate?.();
    } catch (e: any) {
      alert("保存失败: " + e.message);
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-5">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-100 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center">
            <Users className="w-4.5 h-4.5 text-blue-400" />
          </div>
          目标消费者画像
        </h3>
        <div className="flex gap-2">
          <button onClick={loadFromResearch} disabled={loading}
            className={`${BTN_PRIMARY} bg-blue-500/15 text-blue-400 hover:bg-blue-500/25 border border-blue-500/30`}>
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            从调研加载
          </button>
          <button onClick={addPersona}
            className={`${BTN_PRIMARY} bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 border border-emerald-500/30`}>
            <Plus className="w-4 h-4" /> 手动添加
          </button>
        </div>
      </div>

      {/* 画像列表 */}
      {personas.length === 0 ? (
        <div className={EMPTY_STATE}>
          <Users className="w-10 h-10 mx-auto mb-3 text-zinc-600" />
          <p className="text-zinc-400 font-medium">暂无消费者画像</p>
          <p className="text-sm text-zinc-500 mt-1">点击「从调研加载」或「手动添加」开始配置</p>
        </div>
      ) : (
        <div className="space-y-3">
          {personas.map((p, idx) => (
            <div key={idx} className={`${CARD} overflow-hidden`}>
              {/* 画像头部 */}
              <div className="px-5 py-4 flex items-start justify-between">
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <div className="w-10 h-10 rounded-full bg-brand-500/20 flex items-center justify-center flex-shrink-0 text-lg">
                    👤
                  </div>
                  <div className="flex-1 min-w-0">
                    {editingIdx === idx ? (
                      <input type="text" value={p.name}
                        onChange={(e) => updatePersona(idx, "name", e.target.value)}
                        className={`${INPUT} font-semibold text-base`}
                        placeholder="画像名称"
                        autoFocus />
                    ) : (
                      <h4 className="font-semibold text-base text-zinc-100 truncate">
                        {p.name}
                        {p.source && <span className="text-xs text-zinc-500 font-normal ml-2">来自{p.source}</span>}
                      </h4>
                    )}
                    {editingIdx !== idx && (
                      <p className="text-sm text-zinc-400 mt-1 line-clamp-2">
                        {p.background || "点击编辑添加背景描述..."}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex gap-1 ml-3 flex-shrink-0">
                  <button onClick={() => setEditingIdx(editingIdx === idx ? null : idx)}
                    className="p-2 rounded-lg text-zinc-400 hover:text-brand-400 hover:bg-surface-3 transition-colors"
                    title={editingIdx === idx ? "收起" : "编辑"}>
                    {editingIdx === idx ? <ChevronDown className="w-4 h-4" /> : <Pencil className="w-4 h-4" />}
                  </button>
                  <button onClick={() => removePersona(idx)}
                    className="p-2 rounded-lg text-zinc-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                    title="删除">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* 编辑表单 */}
              {editingIdx === idx && (
                <div className="px-5 pb-5 space-y-4 border-t border-surface-3 pt-4">
                  <div>
                    <label className={LABEL}>背景描述</label>
                    <textarea value={p.background}
                      onChange={(e) => updatePersona(idx, "background", e.target.value)}
                      className={`${TEXTAREA} min-h-[100px]`}
                      placeholder="年龄、职业、兴趣爱好、消费场景、生活方式..." />
                  </div>
                  <div>
                    <label className={LABEL}>核心痛点（每行一个）</label>
                    <textarea value={(p.pain_points || []).join("\n")}
                      onChange={(e) => updatePersona(idx, "pain_points", e.target.value.split("\n").filter(Boolean))}
                      className={`${TEXTAREA} min-h-[80px]`}
                      placeholder="痛点1&#10;痛点2&#10;痛点3" />
                  </div>
                </div>
              )}

              {/* 痛点标签（非编辑模式） */}
              {editingIdx !== idx && p.pain_points && p.pain_points.length > 0 && (
                <div className="px-5 pb-4 flex flex-wrap gap-1.5">
                  {p.pain_points.map((pt, i) => (
                    <span key={i} className="px-2.5 py-1 bg-amber-500/10 text-amber-400 text-xs rounded-md border border-amber-500/20">
                      {pt}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 保存按钮 */}
      {personas.length > 0 && (
        <div className="flex justify-between items-center pt-2">
          <span className="text-sm text-zinc-500">共 {personas.length} 个画像</span>
          <button onClick={handleSave} disabled={saving}
            className={`${BTN_PRIMARY} bg-brand-600 text-white hover:bg-brand-700`}>
            <Save className="w-4 h-4" />
            {saving ? "保存中..." : "保存画像配置"}
          </button>
        </div>
      )}
    </div>
  );
}


// ============== 2. 评估任务配置 ==============

// 模拟器类型图标/颜色映射（基于 simulator_type 或 interaction_type）
const SIM_TYPE_STYLE: Record<string, { icon: string; color: string }> = {
  coach: { icon: "🎯", color: "text-rose-400 bg-rose-500/15 border-rose-500/30" },
  editor: { icon: "✍️", color: "text-amber-400 bg-amber-500/15 border-amber-500/30" },
  expert: { icon: "🔬", color: "text-violet-400 bg-violet-500/15 border-violet-500/30" },
  consumer: { icon: "👤", color: "text-blue-400 bg-blue-500/15 border-blue-500/30" },
  seller: { icon: "💰", color: "text-emerald-400 bg-emerald-500/15 border-emerald-500/30" },
  custom: { icon: "🔧", color: "text-zinc-400 bg-zinc-500/15 border-zinc-500/30" },
  reading: { icon: "📖", color: "text-blue-400 bg-blue-500/15 border-blue-500/30" },
  dialogue: { icon: "💬", color: "text-emerald-400 bg-emerald-500/15 border-emerald-500/30" },
  decision: { icon: "🎯", color: "text-amber-400 bg-amber-500/15 border-amber-500/30" },
  exploration: { icon: "🔍", color: "text-violet-400 bg-violet-500/15 border-violet-500/30" },
};

const INTERACTION_MODES_LOCAL: Record<string, { label: string; desc: string }> = {
  review: { label: "审查模式", desc: "AI 一次性给出完整评审意见" },
  dialogue: { label: "对话模式", desc: "AI 模拟消费者/销售进行多轮对话" },
  reading: { label: "阅读模式", desc: "全盘阅读后给出反馈" },
  decision: { label: "决策模式", desc: "模拟购买/转化决策过程" },
  exploration: { label: "探索模式", desc: "带目的的内容探索" },
  scenario: { label: "场景模式", desc: "在特定场景下测试内容反应" },
};

function getSimStyle(sim?: SimulatorData | null, type?: string) {
  if (sim) {
    return SIM_TYPE_STYLE[sim.simulator_type] || SIM_TYPE_STYLE[sim.interaction_type] || SIM_TYPE_STYLE.custom;
  }
  return SIM_TYPE_STYLE[type || "custom"] || SIM_TYPE_STYLE.custom;
}

const GRADER_TYPES_LOCAL: Record<string, { label: string; desc: string }> = {
  content: { label: "内容评分", desc: "直接评价内容质量" },
  process: { label: "过程评分", desc: "评价互动过程质量" },
  combined: { label: "综合评分", desc: "同时评价内容和过程" },
};

export function EvalTaskConfig({ block, projectId, onUpdate }: EvalFieldProps) {
  const [trials, setTrials] = useState<TrialConfig[]>([]);
  const [personas, setPersonas] = useState<PersonaData[]>([]);
  const [graders, setGraders] = useState<GraderData[]>([]);
  const [simulators, setSimulators] = useState<SimulatorData[]>([]);
  const [projectBlocks, setProjectBlocks] = useState<{id: string; name: string}[]>([]);
  const [saving, setSaving] = useState(false);
  const [expandedTrial, setExpandedTrial] = useState<number | null>(null);
  const [showPrompt, setShowPrompt] = useState<string | null>(null);  // simulator id -> show prompt

  // 加载数据
  useEffect(() => {
    if (block.content) {
      try {
        const data = JSON.parse(block.content);
        setTrials(data.trials || _migrateOldTasks(data.tasks || []));
      } catch { setTrials([]); }
    }
    _loadDeps();
  }, [block.content]);

  const _loadDeps = async () => {
    try {
      const [personaResp, graderList, blockTree, simList] = await Promise.all([
        evalAPI.getPersonas(projectId).catch(() => ({ personas: [] })) as Promise<any>,
        graderAPI.listForProject(projectId).catch(() => []),
        blockAPI.getProjectBlocks(projectId).catch(() => ({ blocks: [] })),
        settingsAPI.listSimulators().catch(() => []) as Promise<SimulatorData[]>,
      ]);
      setPersonas(personaResp.personas || []);
      setGraders(graderList);
      // 过滤掉"体验式"模拟器
      setSimulators((simList || []).filter((s: SimulatorData) => s.interaction_type !== "experience"));
      // 提取所有 field 类型的内容块作为可选内容块（P0-1: 统一使用 blockAPI）
      const fields: {id: string; name: string}[] = [];
      const _flatten = (blocks: any[]) => {
        for (const b of blocks) {
          if (b.block_type === "field" && !b.special_handler?.startsWith("eval_")) {
            fields.push({ id: b.id, name: b.name });
          }
          if (b.children) _flatten(b.children);
        }
      };
      _flatten(blockTree.blocks || []);
      setProjectBlocks(fields);
    } catch { /* ignore */ }
  };

  // 旧格式迁移：tasks → trials
  const _migrateOldTasks = (tasks: TaskConfig[]): TrialConfig[] => {
    return tasks.map((t, i) => ({
      name: t.name,
      target_block_ids: t.target_block_ids || [],
      target_block_names: [],
      simulator_type: t.simulator_type,
      interaction_mode: t.interaction_mode,
      persona_config: t.persona_config || {},
      grader_ids: [],
      grader_names: [],
      simulator_config: t.simulator_config,
      order_index: i,
    }));
  };

  // 添加单个试验
  const addTrial = () => {
    const defaultSim = simulators[0];
    const newTrial: TrialConfig = {
      name: `试验 ${trials.length + 1}`,
      target_block_ids: [],
      target_block_names: [],
      simulator_type: defaultSim?.simulator_type || "custom",
      simulator_id: defaultSim?.id || "",
      simulator_name: defaultSim?.name || "",
      interaction_mode: defaultSim?.interaction_mode || defaultSim?.interaction_type || "review",
      persona_config: {},
      grader_ids: graders.length > 0 ? [graders[0].id] : [],
      grader_names: graders.length > 0 ? [graders[0].name] : [],
      simulator_config: { max_turns: defaultSim?.max_turns || 5 },
      order_index: trials.length,
    };
    setTrials([...trials, newTrial]);
    setExpandedTrial(trials.length);
  };

  // 全回归：每个模拟器 × 全部内容块 创建试验
  const addFullRegression = () => {
    const newTrials: TrialConfig[] = [];
    let order = trials.length;

    // 获取所有内容块
    const targetFields = projectBlocks.length > 0 ? projectBlocks : [{ id: "all", name: "全部内容" }];
    const fieldIds = targetFields.map(f => f.id);
    const fieldNames = targetFields.map(f => f.name);

    // 找匹配的 grader
    const contentGrader = graders.find(g => g.grader_type === "content_only") || graders[0];
    const processGrader = graders.find(g => g.grader_type === "content_and_process") || graders[0];
    const allGraderIds = [contentGrader, processGrader].filter(Boolean).map(g => g!.id);
    const allGraderNames = [contentGrader, processGrader].filter(Boolean).map(g => g!.name);

    if (simulators.length > 0) {
      // 基于实际配置的模拟器生成
      const activePersonas = personas.length > 0 ? personas : [{ name: "典型用户", background: "目标读者" }];

      for (const sim of simulators) {
        const isDialogue = sim.interaction_type === "dialogue" || sim.interaction_mode === "dialogue";
        if (isDialogue) {
          // 对话类模拟器：每个 persona 一个 trial
          for (const persona of activePersonas) {
            newTrials.push({
              name: `${sim.name} · ${persona.name}`,
              target_block_ids: fieldIds,
              target_block_names: fieldNames,
              simulator_type: sim.simulator_type,
              simulator_id: sim.id,
              simulator_name: sim.name,
              interaction_mode: sim.interaction_mode || sim.interaction_type,
              persona_config: persona,
              grader_ids: allGraderIds,
              grader_names: allGraderNames,
              simulator_config: { max_turns: sim.max_turns || 5 },
              order_index: order++,
            });
          }
        } else {
          // 审查/阅读类模拟器：一个 trial 即可
          newTrials.push({
            name: `${sim.name}评估`,
            target_block_ids: fieldIds,
            target_block_names: fieldNames,
            simulator_type: sim.simulator_type,
            simulator_id: sim.id,
            simulator_name: sim.name,
            interaction_mode: sim.interaction_mode || sim.interaction_type,
            persona_config: {},
            grader_ids: contentGrader ? [contentGrader.id] : [],
            grader_names: contentGrader ? [contentGrader.name] : [],
            order_index: order++,
          });
        }
      }
    } else {
      // 后备：无模拟器时用简单默认
      newTrials.push({
        name: "默认内容审查",
        target_block_ids: fieldIds,
        target_block_names: fieldNames,
        simulator_type: "custom",
        interaction_mode: "review",
        persona_config: {},
        grader_ids: contentGrader ? [contentGrader.id] : [],
        grader_names: contentGrader ? [contentGrader.name] : [],
        order_index: order++,
      });
    }

    setTrials([...trials, ...newTrials]);
  };

  const removeTrial = (idx: number) => {
    const newT = [...trials];
    newT.splice(idx, 1);
    newT.forEach((t, i) => t.order_index = i);
    setTrials(newT);
    if (expandedTrial === idx) setExpandedTrial(null);
  };

  const updateTrial = (idx: number, field: string, value: any) => {
    const newT = [...trials];
    (newT[idx] as any)[field] = value;
    setTrials(newT);
  };

  const toggleTargetBlock = (idx: number, blockId: string, blockName: string) => {
    const t = { ...trials[idx] };
    const ids = [...(t.target_block_ids || [])];
    const names = [...(t.target_block_names || [])];
    const pos = ids.indexOf(blockId);
    if (pos >= 0) {
      ids.splice(pos, 1);
      names.splice(pos, 1);
    } else {
      ids.push(blockId);
      names.push(blockName);
    }
    t.target_block_ids = ids;
    t.target_block_names = names;
    const newT = [...trials];
    newT[idx] = t;
    setTrials(newT);
  };

  const selectAllBlocks = (idx: number) => {
    const t = { ...trials[idx] };
    t.target_block_ids = projectBlocks.map(b => b.id);
    t.target_block_names = projectBlocks.map(b => b.name);
    const newT = [...trials];
    newT[idx] = t;
    setTrials(newT);
  };

  const deselectAllBlocks = (idx: number) => {
    const t = { ...trials[idx] };
    t.target_block_ids = [];
    t.target_block_names = [];
    const newT = [...trials];
    newT[idx] = t;
    setTrials(newT);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await blockAPI.update(block.id, {
        content: JSON.stringify({ trials, version: "v2" }, null, 2),
        status: "completed",
      });
      onUpdate?.();
    } catch (e: any) {
      alert("保存失败: " + e.message);
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-5">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-100 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center">
            <SlidersHorizontal className="w-4.5 h-4.5 text-purple-400" />
          </div>
          评估试验配置
          <span className="text-sm font-normal text-zinc-500 ml-2">
            核心：评什么字段 × 谁来评 × 用什么评分器
          </span>
        </h3>
      </div>

      {/* 操作栏 */}
      <div className="flex flex-wrap gap-2">
        <button onClick={addTrial}
          className={`${BTN_PRIMARY} bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 border border-emerald-500/30`}>
          <Plus className="w-4 h-4" /> 添加试验
        </button>
        <button onClick={addFullRegression}
          className={`${BTN_PRIMARY} bg-purple-500/15 text-purple-400 hover:bg-purple-500/25 border border-purple-500/30`}>
          <Zap className="w-4 h-4" /> 全回归模板
        </button>
        <span className="text-xs text-zinc-500 self-center ml-2">
          模拟器: {simulators.length} 个 · 字段: {projectBlocks.length} 个 · 评分器: {graders.length} 个 · 画像: {personas.length} 个
        </span>
      </div>

      {/* 无模拟器提示 */}
      {simulators.length === 0 && (
        <div className="px-4 py-3 bg-amber-500/10 border border-amber-500/20 rounded-lg flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
          <span className="text-sm text-amber-300">
            后台尚未配置模拟器。请到「后台设置 → 模拟器」中添加。模拟器定义了交互方式和提示词。
          </span>
        </div>
      )}

      {/* 试验列表 */}
      {trials.length === 0 ? (
        <div className={EMPTY_STATE}>
          <FileText className="w-10 h-10 mx-auto mb-3 text-zinc-600" />
          <p className="text-zinc-400 font-medium">暂无评估试验</p>
          <p className="text-sm text-zinc-500 mt-1">
            点击「添加试验」逐个配置，或使用「全回归模板」一键创建：全部字段 × 5 种角色
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {trials.map((trial, idx) => {
            const simMatch = simulators.find(s => s.id === trial.simulator_id);
            const style = getSimStyle(simMatch, trial.simulator_type);
            const isExpanded = expandedTrial === idx;
            const targetCount = (trial.target_block_ids || []).length;
            return (
              <div key={idx} className={`${CARD} overflow-hidden transition-all ${isExpanded ? "ring-1 ring-brand-500/30" : ""}`}>
                {/* 试验卡片头部 */}
                <div className="px-5 py-4 flex items-center gap-4 cursor-pointer hover:bg-surface-3/30 transition-colors"
                  onClick={() => setExpandedTrial(isExpanded ? null : idx)}>
                  <div className="w-7 h-7 rounded-full bg-surface-3 flex items-center justify-center flex-shrink-0">
                    <span className="text-xs font-bold text-zinc-400">{idx + 1}</span>
                  </div>
                  <div className="text-xl flex-shrink-0">{style.icon}</div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-zinc-100 text-base truncate">{trial.name}</div>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      {/* 目标字段数 */}
                      <span className="text-xs px-2 py-0.5 rounded-md bg-blue-500/15 text-blue-400 border border-blue-500/30">
                        📄 {targetCount > 0 ? `${targetCount} 个内容块` : "未选内容块"}
                      </span>
                      {/* 模拟器名称 */}
                      <span className={`text-xs px-2 py-0.5 rounded-md border ${style.color}`}>
                        {trial.simulator_name || simMatch?.name || trial.simulator_type}
                      </span>
                      {/* 交互模式 */}
                      <span className="text-xs px-2 py-0.5 rounded-md bg-surface-3 text-zinc-400">
                        {INTERACTION_MODES_LOCAL[trial.interaction_mode]?.label || trial.interaction_mode}
                      </span>
                      {/* 评分器 */}
                      {(trial.grader_names || []).length > 0 && (
                        <span className="text-xs px-2 py-0.5 rounded-md bg-amber-500/15 text-amber-400 border border-amber-500/30">
                          ⚖️ {trial.grader_names.length} 个评分器
                        </span>
                      )}
                      {/* Persona */}
                      {trial.persona_config?.name && (
                        <span className="text-xs text-zinc-500">👤 {trial.persona_config.name}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button onClick={(e) => { e.stopPropagation(); removeTrial(idx); }}
                      className="p-2 rounded-lg text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-colors">
                      <Trash2 className="w-4 h-4" />
                    </button>
                    <div className="p-2 text-zinc-500">
                      {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </div>
                  </div>
                </div>

                {/* 展开的详细配置 */}
                {isExpanded && (
                  <div className="border-t border-surface-3 px-5 py-5 bg-surface-1/50 space-y-5">
                    {/* 试验名称 */}
                    <div>
                      <label className={LABEL}>试验名称</label>
                      <input type="text" value={trial.name}
                        onChange={(e) => updateTrial(idx, "name", e.target.value)}
                        className={INPUT} placeholder="给这个试验起个名字" />
                    </div>

                    {/* ★ 目标字段选择（核心） */}
                    <div className={`${CARD_INNER} p-4`}>
                      <div className="flex items-center justify-between mb-3">
                        <label className="text-sm font-medium text-zinc-200 flex items-center gap-2">
                          📄 评估目标字段
                          <span className="text-xs font-normal text-zinc-500">（核心：要评价什么内容）</span>
                        </label>
                        {(() => {
                          const allSelected = projectBlocks.length > 0 && (trial.target_block_ids || []).length === projectBlocks.length;
                          return (
                            <button onClick={() => allSelected ? deselectAllBlocks(idx) : selectAllBlocks(idx)}
                              className="text-xs px-2.5 py-1 bg-surface-3 hover:bg-surface-4 rounded text-zinc-400 hover:text-zinc-200 transition-colors">
                              {allSelected ? "取消全选" : "全选"}
                            </button>
                          );
                        })()}
                      </div>
                      {projectBlocks.length > 0 ? (
                        <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
                          {projectBlocks.map((b) => {
                            const selected = (trial.target_block_ids || []).includes(b.id);
                            return (
                              <label key={b.id}
                                className={`flex items-center gap-2.5 p-2.5 rounded-lg cursor-pointer transition-all text-sm ${
                                  selected
                                    ? "bg-blue-500/10 border border-blue-500/30 text-blue-300"
                                    : "bg-surface-2 border border-surface-3 text-zinc-400 hover:border-surface-4"
                                }`}>
                                <input type="checkbox" checked={selected}
                                  onChange={() => toggleTargetBlock(idx, b.id, b.name)}
                                  className="accent-blue-500 rounded" />
                                <span className="truncate">{b.name}</span>
                              </label>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="text-sm text-zinc-500">项目中暂无内容块。请先在内容面板中创建内容块。</p>
                      )}
                    </div>

                    {/* 模拟器选择 */}
                    <div className={`${CARD_INNER} p-4`}>
                      <label className="text-sm font-medium text-zinc-200 mb-3 block flex items-center gap-2">
                        🎭 模拟器
                        <span className="text-xs font-normal text-zinc-500">（决定交互方式和提示词，在「后台设置 → 模拟器」管理）</span>
                      </label>
                      {simulators.length > 0 ? (
                        <div className="space-y-2">
                          {simulators.map((sim) => {
                            const selected = trial.simulator_id === sim.id;
                            const simStyle = getSimStyle(sim);
                            return (
                              <div key={sim.id}
                                className={`rounded-lg transition-all border ${
                                  selected
                                    ? "bg-brand-500/10 border-brand-500/30 ring-1 ring-brand-500/20"
                                    : "bg-surface-2 border-surface-3 hover:border-surface-4"
                                }`}>
                                <label className="flex items-center gap-3 p-3 cursor-pointer">
                                  <input type="radio" name={`sim-${idx}`}
                                    checked={selected}
                                    onChange={() => {
                                      updateTrial(idx, "simulator_id", sim.id);
                                      updateTrial(idx, "simulator_name", sim.name);
                                      updateTrial(idx, "simulator_type", sim.simulator_type);
                                      updateTrial(idx, "interaction_mode", sim.interaction_mode || sim.interaction_type);
                                      updateTrial(idx, "simulator_config", {
                                        ...trial.simulator_config,
                                        max_turns: sim.max_turns || 5,
                                        system_prompt: sim.prompt_template || "",
                                        secondary_prompt: sim.secondary_prompt || "",
                                        simulator_name: sim.name,
                                        grader_template: sim.grader_template || "",
                                      });
                                    }}
                                    className="accent-brand-500" />
                                  <span className="text-lg flex-shrink-0">{simStyle.icon}</span>
                                  <div className="flex-1 min-w-0">
                                    <div className="text-sm font-medium text-zinc-200">{sim.name}</div>
                                    <div className="text-xs text-zinc-500 mt-0.5 flex items-center gap-2">
                                      <span className="px-1.5 py-0.5 rounded bg-surface-3">
                                        {INTERACTION_MODES_LOCAL[sim.interaction_mode]?.label
                                          || INTERACTION_MODES_LOCAL[sim.interaction_type]?.label
                                          || sim.interaction_type}
                                      </span>
                                      {sim.description && <span className="truncate">{sim.description}</span>}
                                    </div>
                                  </div>
                                  <button onClick={(e) => {
                                    e.preventDefault();
                                    setShowPrompt(showPrompt === sim.id ? null : sim.id);
                                  }}
                                    className="px-2 py-1 rounded text-xs text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 transition-colors flex items-center gap-1"
                                    title="查看提示词模板">
                                    <Eye className="w-3.5 h-3.5" /> 提示词
                                  </button>
                                </label>
                                {/* 展开提示词 */}
                                {showPrompt === sim.id && (
                                  <div className="px-4 pb-4 border-t border-surface-3 mt-1 pt-3 space-y-3">
                                    {/* 主提示词 */}
                                    <div>
                                      <div className="text-xs font-medium text-blue-400 mb-1.5">
                                        📤 {sim.interaction_type === "decision" ? "销售方提示词" : "主提示词（模拟消费者/审阅者）"}
                                      </div>
                                      <pre className="bg-surface-1 p-3 rounded-lg border border-surface-3 text-xs text-zinc-300 whitespace-pre-wrap max-h-[200px] overflow-y-auto leading-relaxed">
                                        {sim.prompt_template || "(空 — 将使用默认模板)"}
                                      </pre>
                                    </div>
                                    {/* 第二方提示词（对话模式） */}
                                    {(sim.interaction_type === "dialogue" || sim.interaction_type === "decision" || sim.interaction_type === "exploration") && (
                                      <div>
                                        <div className="text-xs font-medium text-emerald-400 mb-1.5">
                                          📥 {sim.interaction_type === "decision" ? "消费者回应提示词" : "内容代表提示词"}
                                        </div>
                                        <pre className="bg-surface-1 p-3 rounded-lg border border-surface-3 text-xs text-zinc-300 whitespace-pre-wrap max-h-[200px] overflow-y-auto leading-relaxed">
                                          {sim.secondary_prompt || "(空 — 将使用默认模板)"}
                                        </pre>
                                      </div>
                                    )}
                                    {/* 评分提示词 */}
                                    {sim.grader_template && (
                                      <div>
                                        <div className="text-xs font-medium text-amber-400 mb-1.5">⚖️ 评分提示词模板</div>
                                        <pre className="bg-surface-1 p-3 rounded-lg border border-surface-3 text-xs text-zinc-300 whitespace-pre-wrap max-h-[150px] overflow-y-auto leading-relaxed">
                                          {sim.grader_template}
                                        </pre>
                                      </div>
                                    )}
                                    {sim.evaluation_dimensions?.length > 0 && (
                                      <div className="flex flex-wrap gap-1.5">
                                        {sim.evaluation_dimensions.map((d, i) => (
                                          <span key={i} className="px-2 py-0.5 bg-surface-3 text-zinc-400 text-xs rounded">
                                            {d}
                                          </span>
                                        ))}
                                      </div>
                                    )}
                                    <p className="text-xs text-zinc-600 italic">💡 在后台设置 → 模拟器 中编辑这些提示词</p>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="text-sm text-zinc-500">暂无模拟器，请到「后台设置 → 模拟器」中创建。</p>
                      )}
                    </div>

                    {/* ★ Grader 评分器选择（多选） */}
                    <div className={`${CARD_INNER} p-4`}>
                      <div className="flex items-center justify-between mb-3">
                        <label className="text-sm font-medium text-zinc-200 flex items-center gap-2">
                          ⚖️ 评分器（Grader）
                          <span className="text-xs font-normal text-zinc-500">可多选，每个试验可用多个评分器打分</span>
                        </label>
                        <span className="text-xs text-zinc-500">{(trial.grader_ids || []).length} / {graders.length} 已选</span>
                      </div>
                      {graders.length > 0 ? (
                        <div className="space-y-2">
                          {graders.map((g) => {
                            const selected = (trial.grader_ids || []).includes(g.id);
                            return (
                              <label key={g.id}
                                className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-all ${
                                  selected
                                    ? "bg-amber-500/10 border border-amber-500/30"
                                    : "bg-surface-2 border border-surface-3 hover:border-surface-4"
                                }`}>
                                <input type="checkbox" checked={selected}
                                  onChange={() => {
                                    const ids = [...(trial.grader_ids || [])];
                                    const names = [...(trial.grader_names || [])];
                                    const pos = ids.indexOf(g.id);
                                    if (pos >= 0) { ids.splice(pos, 1); names.splice(pos, 1); }
                                    else { ids.push(g.id); names.push(g.name); }
                                    updateTrial(idx, "grader_ids", ids);
                                    updateTrial(idx, "grader_names", names);
                                  }}
                                  className="accent-amber-500 rounded" />
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2">
                                    <span className="text-sm font-medium text-zinc-200">{g.is_preset ? "⚖️" : "🔧"} {g.name}</span>
                                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                                      g.grader_type === "content_only"
                                        ? "bg-blue-500/15 text-blue-400"
                                        : "bg-purple-500/15 text-purple-400"
                                    }`}>
                                      {g.grader_type === "content_only" ? "仅评内容" : "评内容+互动"}
                                    </span>
                                  </div>
                                  {g.dimensions.length > 0 && (
                                    <div className="text-xs text-zinc-500 mt-1 truncate">
                                      维度: {g.dimensions.join("、")}
                                    </div>
                                  )}
                                </div>
                              </label>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="text-sm text-zinc-500">
                          暂无评分器。请到「后台设置 → 评分器」中创建。
                        </p>
                      )}
                    </div>

                    {/* Persona 选择（所有模拟器类型均可选择角色画像，影响评估视角） */}
                    {trial.simulator_id && (
                      <div className={`${CARD_INNER} p-4`}>
                        <label className="text-sm font-medium text-zinc-200 mb-2 block">👤 消费者画像 <span className="text-xs font-normal text-zinc-500">（可选，决定评估视角）</span></label>
                        {personas.length > 0 ? (
                          <div className="space-y-2">
                            {personas.map((p, pi) => (
                              <label key={pi}
                                className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-all ${
                                  trial.persona_config?.name === p.name
                                    ? "bg-brand-500/10 border border-brand-500/30 ring-1 ring-brand-500/20"
                                    : "bg-surface-2 border border-surface-3 hover:border-surface-4"
                                }`}>
                                <input type="radio" name={`persona-${idx}`}
                                  checked={trial.persona_config?.name === p.name}
                                  onChange={() => updateTrial(idx, "persona_config", p)}
                                  className="accent-brand-500" />
                                <div className="flex-1 min-w-0">
                                  <div className="text-sm font-medium text-zinc-200">{p.name}</div>
                                  {p.background && (
                                    <div className="text-xs text-zinc-500 mt-0.5 truncate">{p.background}</div>
                                  )}
                                </div>
                              </label>
                            ))}
                          </div>
                        ) : (
                          <p className="text-sm text-zinc-500 mt-1">
                            ⚠️ 请先在「目标消费者画像」字段中配置画像
                          </p>
                        )}
                      </div>
                    )}

                    {/* 对话轮数 */}
                    {trial.interaction_mode !== "review" && (
                      <div>
                        <label className={LABEL}>最大对话轮数</label>
                        <input type="number" min={1} max={20}
                          value={trial.simulator_config?.max_turns || 5}
                          onChange={(e) => updateTrial(idx, "simulator_config", {
                            ...trial.simulator_config, max_turns: parseInt(e.target.value) || 5,
                          })}
                          className={`${INPUT} w-40`} />
                        <p className="text-xs text-zinc-500 mt-1">建议：消费者对话 3-5 轮，销售测试 5-8 轮</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 底部保存 */}
      {trials.length > 0 && (
        <div className="flex justify-between items-center pt-2">
          <span className="text-sm text-zinc-500">共 {trials.length} 个评估试验</span>
          <button onClick={handleSave} disabled={saving}
            className={`${BTN_PRIMARY} bg-brand-600 text-white hover:bg-brand-700`}>
            <Save className="w-4 h-4" />
            {saving ? "保存中..." : "保存试验配置"}
          </button>
        </div>
      )}
    </div>
  );
}


// ============== 3. 评估报告（统一面板：执行 + 评分 + 诊断） ==============

// 计算得分百分比和颜色
function scoreColor(score: number, max: number = 10): string {
  const pct = score / max;
  if (pct >= 0.7) return "text-emerald-400";
  if (pct >= 0.6) return "text-amber-400";
  return "text-red-400";
}
function scoreBg(score: number, max: number = 10): string {
  const pct = score / max;
  if (pct >= 0.7) return "bg-emerald-500";
  if (pct >= 0.6) return "bg-amber-500";
  return "bg-red-500";
}

export function EvalReportPanel({ block, projectId, onUpdate }: EvalFieldProps) {
  const [executing, setExecuting] = useState(false);
  const [reportData, setReportData] = useState<any>(null);
  const [expandedTrial, setExpandedTrial] = useState<number | null>(null);
  const [expandedLLMCall, setExpandedLLMCall] = useState<string | null>(null);
  const [expandedSection, setExpandedSection] = useState<Record<string, boolean>>({});
  const [pollError, setPollError] = useState<string | null>(null);
  const mountedRef = React.useRef(true);

  // 组件卸载时标记
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // ===== 从 block.content 加载报告数据 =====
  useEffect(() => {
    if (block.content) {
      try {
        setReportData(JSON.parse(block.content));
      } catch { setReportData(null); }
    }
  }, [block.content]);

  // ===== 挂载时从 API 获取最新 block 状态 =====
  // 解决：用户导航到其他块再回来时，props 中的 block 可能是缓存的旧数据
  // 需要主动查询 DB 确认是否仍在执行
  useEffect(() => {
    if (!block.id) return;
    let cancelled = false;
    
    blockAPI.get(block.id).then(freshBlock => {
      if (cancelled) return;
      // 如果 DB 中是 in_progress 但本地不是，立即恢复执行状态
      if (freshBlock.status === "in_progress" && !executing) {
        setExecuting(true);
      }
      // 如果数据不同步，触发父组件刷新
      if (freshBlock.status !== block.status || freshBlock.content !== block.content) {
        console.log(`[EvalReport] 数据不同步: local_status=${block.status}, server_status=${freshBlock.status}`);
        onUpdate?.();
      }
    }).catch(() => {}); // 静默忽略
    
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block.id]);

  // ===== 从 block.status 同步执行状态 =====
  useEffect(() => {
    if (block.status === "in_progress") {
      setExecuting(true);
    } else {
      setExecuting(false);
    }
  }, [block.status]);

  // ===== 自管理轮询：执行中时定期刷新 =====
  // 即使用户导航走再回来，只要 block.status 是 in_progress，就会恢复轮询
  useEffect(() => {
    if (!executing) return;
    
    const pollInterval = setInterval(async () => {
      try {
        const freshBlock = await blockAPI.get(block.id);
        if (!mountedRef.current) return;
        
        if (freshBlock.status !== "in_progress") {
          // 执行完成（成功或失败）
          setExecuting(false);
          if (freshBlock.content) {
            try { setReportData(JSON.parse(freshBlock.content)); } catch {}
          }
          onUpdate?.(); // 刷新父组件数据
          // 浏览器通知
          sendNotification(
            "评估执行完成",
            freshBlock.status === "completed" ? "评估报告已生成，点击查看结果" : "评估执行出错，请检查"
          );
        }
      } catch (err) {
        console.error("[EvalReport] 轮询失败:", err);
      }
    }, 3000);
    
    return () => clearInterval(pollInterval);
  }, [executing, block.id]);

  const handleExecute = async () => {
    setExecuting(true);
    setPollError(null);
    
    // Fire-and-forget：发起请求后不等待完成
    // 后端会立即设置 block.status = "in_progress" 并 commit
    // 自管理轮询会检测到完成状态
    evalAPI.generateForBlock(block.id).then(() => {
      // 后端执行完成，刷新数据
      if (mountedRef.current) onUpdate?.();
    }).catch((e: any) => {
      if (!mountedRef.current) return;
      setPollError(e.message || "执行失败");
      setExecuting(false);
    });
  };

  const toggleSection = (key: string) => {
    setExpandedSection(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const trials = reportData?.trials || [];

  // 计算统计数据
  const completedTrials = trials.filter((t: any) => t.status === "completed");
  const failedTrials = trials.filter((t: any) => t.status === "failed");
  const totalLLMCalls = trials.reduce((sum: number, t: any) => sum + (t.llm_calls?.length || 0), 0);
  const totalCost = trials.reduce((sum: number, t: any) => sum + (t.cost || 0), 0);

  // 计算总分（所有 trial 的 overall_score 均分）
  const scoredTrials = completedTrials.filter((t: any) => t.overall_score != null);
  const avgScore = scoredTrials.length > 0
    ? scoredTrials.reduce((sum: number, t: any) => sum + t.overall_score, 0) / scoredTrials.length
    : null;
  const belowStandard = scoredTrials.filter((t: any) => t.overall_score < 6).length;

  return (
    <div className="space-y-5">
      {/* ===== 头部：标题 + 一键执行按钮 ===== */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-100 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
            <BarChart3 className="w-4.5 h-4.5 text-emerald-400" />
          </div>
          评估报告
        </h3>
        <button onClick={handleExecute} disabled={executing || block.status === "in_progress"}
          className={`${BTN_PRIMARY} ${executing || block.status === "in_progress"
            ? "bg-zinc-700 text-zinc-400"
            : "bg-emerald-600 text-white hover:bg-emerald-700 shadow-lg shadow-emerald-900/30"}`}>
          {executing || block.status === "in_progress" ? (
            <><RefreshCw className="w-4 h-4 animate-spin" /> 并行执行中...</>
          ) : trials.length > 0 ? (
            <><RefreshCw className="w-4 h-4" /> 重新执行所有试验</>
          ) : (
            <><Play className="w-4 h-4" /> ▶ 一键并行执行所有试验</>
          )}
        </button>
      </div>
      {/* 执行中提示 */}
      {executing && (
        <div className="flex items-center gap-3 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-sm text-emerald-300">
          <RefreshCw className="w-4 h-4 animate-spin flex-shrink-0" />
          <div>
            <p>正在并行执行所有试验...</p>
            <p className="text-emerald-400/60 text-xs mt-1">可以自由浏览其他内容块，回来后状态会自动恢复。</p>
          </div>
        </div>
      )}
      {/* 执行失败提示 */}
      {block.status === "failed" && !executing && (
        <div className="flex items-center gap-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-300">
          <XCircle className="w-4 h-4 flex-shrink-0" />
          <span>上次执行失败，请检查配置后重新执行。</span>
        </div>
      )}
      {/* API 错误提示 */}
      {pollError && (
        <div className="flex items-center gap-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-300">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>{pollError}</span>
          <button onClick={() => setPollError(null)} className="ml-auto text-zinc-400 hover:text-zinc-200">✕</button>
        </div>
      )}
      {!executing && trials.length === 0 && (
        <p className="text-xs text-zinc-500 -mt-3">
          点击上方按钮将读取「评估任务配置」，并行执行所有 Trial，自动评分，生成综合诊断报告。
        </p>
      )}

      {/* ===== 无数据状态 ===== */}
      {trials.length === 0 ? (
        <div className={EMPTY_STATE}>
          <BarChart3 className="w-10 h-10 mx-auto mb-3 text-zinc-600" />
          <p className="text-zinc-400 font-medium">尚未执行评估</p>
          <p className="text-sm text-zinc-500 mt-1">请先在「评估任务配置」中配置好试验，然后点击执行。</p>
          <p className="text-xs text-zinc-600 mt-2">
            💡 支持多 Task：项目中所有「评估任务配置」块的试验会被自动合并执行。共享画像无需重复配置。
          </p>
        </div>
      ) : (
        <div className="space-y-5">

          {/* ===== 总分面板 ===== */}
          <div className={`${CARD} p-5`}>
            <div className="flex items-center gap-6">
              {/* 总分大数字 */}
              <div className="text-center flex-shrink-0 w-28">
                {avgScore != null ? (
                  <>
                    <div className={`text-4xl font-bold ${scoreColor(avgScore)}`}>
                      {avgScore.toFixed(1)}
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">总均分 / 10</div>
                  </>
                ) : (
                  <>
                    <div className="text-4xl font-bold text-zinc-600">—</div>
                    <div className="text-xs text-zinc-500 mt-1">无评分</div>
                  </>
                )}
              </div>

              {/* 统计网格 */}
              <div className={`grid ${failedTrials.length > 0 ? "grid-cols-5" : "grid-cols-4"} gap-3 flex-1`}>
                <div className="rounded-xl p-3 text-center border border-emerald-500/20 bg-emerald-500/10">
                  <div className="text-xl font-bold text-emerald-400">{completedTrials.length}</div>
                  <div className="text-xs text-emerald-400/70 mt-0.5">完成</div>
                </div>
                {failedTrials.length > 0 && (
                  <div className="rounded-xl p-3 text-center border border-orange-500/20 bg-orange-500/10">
                    <div className="text-xl font-bold text-orange-400">{failedTrials.length}</div>
                    <div className="text-xs text-orange-400/70 mt-0.5">失败</div>
                  </div>
                )}
                <div className="rounded-xl p-3 text-center border border-red-500/20 bg-red-500/10">
                  <div className="text-xl font-bold text-red-400">{belowStandard}</div>
                  <div className="text-xs text-red-400/70 mt-0.5">不达标 (&lt;60%)</div>
                </div>
                <div className="rounded-xl p-3 text-center border border-blue-500/20 bg-blue-500/10">
                  <div className="text-xl font-bold text-blue-400">{totalLLMCalls}</div>
                  <div className="text-xs text-blue-400/70 mt-0.5">LLM 调用</div>
                </div>
                <div className="rounded-xl p-3 text-center border border-amber-500/20 bg-amber-500/10">
                  <div className="text-xl font-bold text-amber-400">¥{totalCost.toFixed(2)}</div>
                  <div className="text-xs text-amber-400/70 mt-0.5">总费用</div>
                </div>
              </div>
            </div>

            {/* 失败提示 */}
            {failedTrials.length > 0 && (
              <div className="mt-3 flex items-center gap-2 px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg">
                <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <span className="text-sm text-red-300">{failedTrials.length} 个试验执行失败</span>
              </div>
            )}
          </div>

          {/* ===== 试验得分卡片列表 ===== */}
          <div className={`${CARD} p-4`}>
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-zinc-300">各试验得分一览</h4>
              <span className="text-xs text-zinc-500">{scoredTrials.length} / {trials.length} 已评分</span>
            </div>
            <div className="space-y-2.5">
              {trials.map((trial: any, idx: number) => {
                const style = getSimStyle(null, trial.simulator_type);
                const score = trial.overall_score;
                const isBelowStd = score != null && score < 6;
                const graderEntries = trial.grader_scores ? Object.entries(trial.grader_scores) : [];
                const hasGraders = graderEntries.length > 0;
                return (
                  <div key={idx}
                    className={`rounded-xl cursor-pointer transition-all hover:bg-surface-3/30 overflow-hidden ${
                      isBelowStd ? "bg-red-500/5 border border-red-500/20" 
                        : expandedTrial === idx ? "bg-surface-2 border border-brand-500/30 ring-1 ring-brand-500/20"
                          : "bg-surface-1 border border-surface-3"
                    }`}
                    onClick={() => setExpandedTrial(expandedTrial === idx ? null : idx)}>
                    {/* 第一行：试验名称 + 总分 */}
                    <div className="px-4 py-3 flex items-center gap-3">
                      <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${
                        isBelowStd ? "bg-red-500/20" : "bg-surface-3"
                      }`}>
                        <span className={`text-xs font-bold ${isBelowStd ? "text-red-400" : "text-zinc-400"}`}>{idx + 1}</span>
                      </div>
                      <span className="text-base flex-shrink-0">{style.icon}</span>
                      <div className="flex-1 min-w-0">
                        <span className="text-sm text-zinc-200 font-medium">
                          {trial.task_name}
                        </span>
                        <div className="flex items-center gap-2 mt-0.5">
                          {trial.simulator_name && (
                            <span className={`text-xs px-1.5 py-0.5 rounded ${style.color}`}>
                              {trial.simulator_name}
                            </span>
                          )}
                          {trial.persona_name && (
                            <span className="text-xs text-zinc-500">👤 {trial.persona_name}</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-3 flex-shrink-0">
                        {isBelowStd && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 border border-red-500/30 font-medium">
                            不达标
                          </span>
                        )}
                        {score != null ? (
                          <div className="text-right">
                            <span className={`text-xl font-bold ${scoreColor(score)}`}>
                              {score}
                            </span>
                            <span className="text-xs text-zinc-500">/10</span>
                          </div>
                        ) : trial.status === "failed" ? (
                          <div className="flex items-center gap-1.5">
                            <XCircle className="w-5 h-5 text-red-400" />
                            <span className="text-xs text-red-400">失败</span>
                          </div>
                        ) : (
                          <Clock className="w-5 h-5 text-zinc-600" />
                        )}
                        {expandedTrial === idx ? <ChevronDown className="w-4 h-4 text-zinc-500" /> : <ChevronRight className="w-4 h-4 text-zinc-500" />}
                      </div>
                    </div>
                    {/* 第二行：各 Grader 分数标签 / 错误信息 */}
                    {trial.status === "failed" && trial.error ? (
                      <div className="px-4 pb-3 -mt-1">
                        <span className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-2.5 py-1 inline-block">
                          ❌ {trial.error.length > 120 ? trial.error.slice(0, 120) + "..." : trial.error}
                        </span>
                      </div>
                    ) : hasGraders ? (
                      <div className="px-4 pb-3 -mt-1 flex flex-wrap gap-2">
                        {graderEntries.map(([gName, gScore]: any) => (
                          <span key={gName} className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border font-medium ${
                            gScore >= 7 ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
                              : gScore >= 6 ? "text-amber-400 bg-amber-500/10 border-amber-500/20"
                                : "text-red-400 bg-red-500/10 border-red-500/20"
                          }`}>
                            ⚖️ {gName}
                            <span className="font-bold">{typeof gScore === 'number' ? gScore.toFixed(1) : gScore}</span>
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>

          {/* ===== 展开的试验详情 ===== */}
          {expandedTrial != null && trials[expandedTrial] && (() => {
            const trial = trials[expandedTrial];
            const idx = expandedTrial;
            const trialStyle = getSimStyle(null, trial.simulator_type);
            return (
              <div className={`${CARD} overflow-hidden ring-1 ring-brand-500/30`}>
                {/* 试验标题栏 */}
                <div className="px-5 py-4 bg-surface-2 flex items-center justify-between border-b border-surface-3">
                  <div className="flex items-center gap-3">
                    <span className="text-xl">{trialStyle.icon}</span>
                    <div>
                      <div className="font-semibold text-zinc-100 text-base">{trial.task_name}</div>
                      <div className="text-xs text-zinc-500 mt-0.5 flex items-center gap-2">
                        <span className={`px-1.5 py-0.5 rounded border ${trialStyle.color}`}>
                          {trial.simulator_name || trial.simulator_type}
                        </span>
                        <span className="px-1.5 py-0.5 rounded bg-surface-3">
                          {INTERACTION_MODES_LOCAL[trial.interaction_mode]?.label || trial.interaction_mode}
                        </span>
                        {trial.persona_name && <span>👤 {trial.persona_name}</span>}
                        <span>{trial.llm_calls?.length || 0} 次 LLM 调用</span>
                      </div>
                    </div>
                  </div>
                  {trial.overall_score != null && (
                    <div className="text-right">
                      <div className={`text-3xl font-bold ${scoreColor(trial.overall_score)}`}>
                        {trial.overall_score}
                      </div>
                      <div className="text-xs text-zinc-500">总分 / 10</div>
                    </div>
                  )}
                </div>

                {/* ---- 失败错误信息 ---- */}
                {trial.status === "failed" && trial.error && (
                  <div className="px-5 py-4 border-t border-red-500/30 bg-red-500/5">
                    <h4 className="text-sm font-medium text-red-400 mb-2 flex items-center gap-2">
                      <XCircle className="w-4 h-4" /> 执行失败
                    </h4>
                    <pre className="text-xs text-red-300/80 bg-red-500/10 p-3 rounded-lg border border-red-500/20 whitespace-pre-wrap break-words font-mono">
                      {trial.error}
                    </pre>
                  </div>
                )}

                {/* ---- Grader 评分详情（核心区域） ---- */}
                {trial.grader_results && trial.grader_results.length > 0 && (
                  <div className="px-5 py-4 border-t border-surface-3 bg-gradient-to-b from-surface-2/50 to-transparent">
                    <h4 className="text-sm font-semibold text-zinc-200 mb-4 flex items-center gap-2">
                      ⚖️ 各 Grader 评分
                      <span className="text-xs text-zinc-500 font-normal">（{trial.grader_results.length} 个评分器独立打分）</span>
                    </h4>
                    {/* Grader 总览栏 */}
                    <div className="flex flex-wrap gap-3 mb-4">
                      {trial.grader_results.map((gr: any, gi: number) => (
                        <div key={gi} className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${
                          gr.overall != null && gr.overall >= 7 ? "border-emerald-500/25 bg-emerald-500/5"
                            : gr.overall != null && gr.overall >= 6 ? "border-amber-500/25 bg-amber-500/5"
                              : gr.overall != null ? "border-red-500/25 bg-red-500/5"
                                : "border-surface-3 bg-surface-2"
                        }`}>
                          <span className="text-xs text-zinc-400">{gr.grader_name || `评分器 ${gi + 1}`}</span>
                          {gr.overall != null && (
                            <span className={`text-base font-bold ${scoreColor(gr.overall)}`}>
                              {typeof gr.overall === 'number' ? gr.overall.toFixed(1) : gr.overall}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                    {/* Grader 详情卡片 */}
                    <div className="space-y-4">
                      {trial.grader_results.map((gr: any, gi: number) => (
                        <div key={gi} className={`${CARD_INNER} p-4`}>
                          <div className="flex items-center justify-between mb-3">
                            <span className="text-sm font-medium text-zinc-200">
                              {gr.grader_name || `评分器 ${gi + 1}`}
                              <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${
                                gr.grader_type === "content_only" ? "bg-blue-500/15 text-blue-400" : "bg-purple-500/15 text-purple-400"
                              }`}>
                                {gr.grader_type === "content_only" ? "仅评内容" : "评内容+互动"}
                              </span>
                            </span>
                            {gr.overall != null && (
                              <span className={`text-lg font-bold ${scoreColor(gr.overall)}`}>
                                {typeof gr.overall === 'number' ? gr.overall.toFixed(1) : gr.overall}<span className="text-xs text-zinc-500">/10</span>
                              </span>
                            )}
                          </div>
                          {/* 分维度评分条 + 评语 */}
                          {gr.scores && Object.keys(gr.scores).length > 0 && (
                            <div className="space-y-2.5">
                              {Object.entries(gr.scores).map(([dim, score]: any) => (
                                <div key={dim}>
                                  <div className="flex items-center gap-3">
                                    <span className="text-xs text-zinc-400 w-28 flex-shrink-0 truncate" title={dim}>{dim}</span>
                                    <div className="flex-1 bg-surface-3 rounded-full h-2.5 overflow-hidden">
                                      <div className={`h-full rounded-full transition-all ${scoreBg(score)}`}
                                        style={{ width: `${(score / 10) * 100}%` }} />
                                    </div>
                                    <span className={`text-sm font-mono font-bold w-8 text-right ${scoreColor(score)}`}>{score}</span>
                                  </div>
                                  {/* 该维度的评语 */}
                                  {gr.comments && gr.comments[dim] && (
                                    <p className="text-xs text-zinc-500 ml-[7.5rem] mt-1 leading-relaxed">{gr.comments[dim]}</p>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                          {/* Grader 综合反馈 */}
                          {gr.feedback && (
                            <div className="mt-3 text-sm text-zinc-300 leading-relaxed bg-surface-2 p-3 rounded-lg border border-surface-3">
                              {gr.feedback}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* ---- 维度评分（兼容旧格式 trial.result.scores） ---- */}
                {!trial.grader_results && trial.result?.scores && Object.keys(trial.result.scores).length > 0 && (
                  <div className="px-5 py-4 bg-surface-1/50">
                    <h4 className="text-sm font-medium text-zinc-300 mb-3">📊 维度评分</h4>
                    <div className="space-y-2">
                      {Object.entries(trial.result.scores).map(([dim, score]: any) => (
                        <div key={dim} className="flex items-center gap-3">
                          <span className="text-xs text-zinc-400 w-24 flex-shrink-0 truncate">{dim}</span>
                          <div className="flex-1 bg-surface-3 rounded-full h-2 overflow-hidden">
                            <div className={`h-full rounded-full transition-all ${scoreBg(score)}`}
                              style={{ width: `${(score / 10) * 100}%` }} />
                          </div>
                          <span className="text-xs font-mono text-zinc-300 w-6 text-right">{score}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* ---- 交互记录 ---- */}
                {trial.nodes && trial.nodes.length > 0 && (
                  <div className="border-t border-surface-3">
                    <div className="px-5 py-3 flex items-center justify-between cursor-pointer hover:bg-surface-3/30 transition-colors"
                      onClick={() => toggleSection(`nodes-${idx}`)}>
                      <h4 className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                        💬 交互记录 ({trial.nodes.length} 轮)
                      </h4>
                      {expandedSection[`nodes-${idx}`] ? <ChevronDown className="w-4 h-4 text-zinc-500" /> : <ChevronRight className="w-4 h-4 text-zinc-500" />}
                    </div>
                    {expandedSection[`nodes-${idx}`] && (
                      <div className="px-5 pb-4 space-y-2.5 max-h-[400px] overflow-y-auto">
                        {trial.nodes.map((node: any, ni: number) => {
                          // 根据 role 确定显示样式
                          const isLeft = node.role === "consumer" || node.role === "user";
                          const roleLabel = node.role === "consumer" ? `🗣 ${trial.persona_name || "消费者"}`
                            : node.role === "seller" ? "💼 销售顾问"
                            : node.role === "system" ? "⚙️ 系统提示"
                            : node.role === "user" ? "📝 评估请求"
                            : node.role === "assistant" ? "🤖 评估反馈"
                            : node.role === "content_rep" ? "📄 内容代表"
                            : `📋 ${node.role}`;
                          const bgClass = node.role === "consumer" || node.role === "user"
                            ? "bg-blue-500/15 text-blue-200 border border-blue-500/20"
                            : node.role === "seller"
                              ? "bg-purple-500/15 text-purple-200 border border-purple-500/20"
                            : node.role === "system"
                              ? "bg-zinc-800/50 text-zinc-400 border border-zinc-700/50"
                              : "bg-surface-3 text-zinc-300";
                          return (
                          <div key={ni} className={`flex ${isLeft ? "justify-start" : "justify-end"}`}>
                            <div className={`max-w-[80%] rounded-xl px-4 py-3 text-sm ${bgClass}`}>
                              <div className="text-xs font-medium mb-1.5 opacity-70">
                                {roleLabel}
                                {node.turn && ` · 第${node.turn}轮`}
                              </div>
                              <div className="leading-relaxed whitespace-pre-wrap">{node.content}</div>
                            </div>
                          </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* ---- LLM 调用日志 ---- */}
                {trial.llm_calls && trial.llm_calls.length > 0 && (
                  <div className="border-t border-surface-3">
                    <div className="px-5 py-3 flex items-center justify-between cursor-pointer hover:bg-surface-3/30 transition-colors"
                      onClick={() => toggleSection(`llm-${idx}`)}>
                      <h4 className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                        <Zap className="w-4 h-4 text-amber-400" />
                        LLM 调用日志 ({trial.llm_calls.length} 次)
                        <span className="text-xs text-zinc-500 font-normal">每次模型调用的完整输入输出</span>
                      </h4>
                      {expandedSection[`llm-${idx}`] ? <ChevronDown className="w-4 h-4 text-zinc-500" /> : <ChevronRight className="w-4 h-4 text-zinc-500" />}
                    </div>
                    {expandedSection[`llm-${idx}`] && (
                      <div className="px-5 pb-4 space-y-2">
                        {trial.llm_calls.map((call: any, ci: number) => {
                          const callKey = `${idx}-${ci}`;
                          const isLLMExpanded = expandedLLMCall === callKey;
                          const stepLabel = call.step || `调用 ${ci + 1}`;
                          const isGrader = stepLabel.includes("grader");
                          const isSimulator = stepLabel.includes("simulator") || stepLabel.includes("consumer") || stepLabel.includes("seller") || stepLabel.includes("content_rep");
                          return (
                            <div key={ci} className={`${CARD_INNER} overflow-hidden`}>
                              <div className="flex items-center justify-between px-4 py-2.5 cursor-pointer hover:bg-surface-2 transition-colors"
                                onClick={() => setExpandedLLMCall(isLLMExpanded ? null : callKey)}>
                                <div className="flex items-center gap-3 text-sm">
                                  {/* 步骤类型标签 */}
                                  <span className={`font-mono px-2 py-0.5 rounded text-xs border ${
                                    isGrader ? "text-amber-400 bg-amber-500/10 border-amber-500/20"
                                      : isSimulator ? "text-blue-400 bg-blue-500/10 border-blue-500/20"
                                        : "text-zinc-400 bg-surface-3 border-surface-3"
                                  }`}>
                                    {isGrader ? "⚖️" : isSimulator ? "🎭" : "🤖"} {stepLabel}
                                  </span>
                                  <span className="text-zinc-500 text-xs">{call.tokens_in || 0}↑ {call.tokens_out || 0}↓</span>
                                  <span className="text-zinc-600 text-xs">{call.duration_ms || 0}ms</span>
                                  {call.cost != null && <span className="text-zinc-600 text-xs">¥{Number(call.cost).toFixed(4)}</span>}
                                </div>
                                {isLLMExpanded ? <ChevronDown className="w-3.5 h-3.5 text-zinc-500" /> : <ChevronRight className="w-3.5 h-3.5 text-zinc-500" />}
                              </div>
                              {isLLMExpanded && (
                                <div className="border-t border-surface-3 p-4 space-y-3 bg-surface-1">
                                  <div>
                                    <div className="text-xs font-medium text-blue-400 mb-1.5 flex items-center gap-1.5">
                                      📤 System Prompt
                                      <span className="text-zinc-600 font-normal">（此次调用传给模型的系统提示词）</span>
                                    </div>
                                    <pre className="bg-surface-2 p-3 rounded-lg border border-surface-3 text-xs text-zinc-300 whitespace-pre-wrap max-h-[300px] overflow-y-auto leading-relaxed">
                                      {call.input?.system_prompt || "(空)"}
                                    </pre>
                                  </div>
                                  <div>
                                    <div className="text-xs font-medium text-emerald-400 mb-1.5 flex items-center gap-1.5">
                                      📤 User Message
                                      <span className="text-zinc-600 font-normal">（传入内容 / 上下文）</span>
                                    </div>
                                    <pre className="bg-surface-2 p-3 rounded-lg border border-surface-3 text-xs text-zinc-300 whitespace-pre-wrap max-h-[300px] overflow-y-auto leading-relaxed">
                                      {call.input?.user_message || "(空)"}
                                    </pre>
                                  </div>
                                  <div>
                                    <div className="text-xs font-medium text-purple-400 mb-1.5 flex items-center gap-1.5">
                                      📥 AI Response
                                      <span className="text-zinc-600 font-normal">（模型输出）</span>
                                    </div>
                                    <pre className="bg-surface-2 p-3 rounded-lg border border-surface-3 text-xs text-zinc-300 whitespace-pre-wrap max-h-[400px] overflow-y-auto leading-relaxed">
                                      {call.output || "(空)"}
                                    </pre>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* ---- 评估总结 ---- */}
                {trial.result?.summary && (
                  <div className="border-t border-surface-3 px-5 py-4 bg-amber-500/5">
                    <h4 className="text-sm font-medium text-amber-400 mb-2">📝 评估总结</h4>
                    <p className="text-sm text-zinc-300 leading-relaxed">{trial.result.summary}</p>
                  </div>
                )}

                {/* ---- 错误信息 ---- */}
                {trial.error && (
                  <div className="border-t border-surface-3 px-5 py-4 bg-red-500/5">
                    <h4 className="text-sm font-medium text-red-400 mb-2">❌ 错误</h4>
                    <pre className="text-xs text-red-300 whitespace-pre-wrap">{trial.error}</pre>
                  </div>
                )}
              </div>
            );
          })()}

          {/* ===== 综合诊断 ===== */}
          {reportData?.diagnosis && (
            <div className={`${CARD} overflow-hidden`}>
              <div className="px-5 py-3 flex items-center justify-between cursor-pointer hover:bg-surface-3/30 transition-colors border-b border-surface-3"
                onClick={() => toggleSection("diagnosis")}>
                <h4 className="text-sm font-medium text-zinc-200 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-400" />
                  综合诊断
                </h4>
                {expandedSection["diagnosis"] ? <ChevronDown className="w-4 h-4 text-zinc-500" /> : <ChevronRight className="w-4 h-4 text-zinc-500" />}
              </div>
              {expandedSection["diagnosis"] && (
                <div className="p-5">
                  <div className="prose prose-sm prose-invert max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{reportData.diagnosis}</ReactMarkdown>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// ============== 入口分发函数 ==============

export function getEvalFieldEditor(handler: string): React.FC<EvalFieldProps> | null {
  const map: Record<string, React.FC<EvalFieldProps>> = {
    "eval_persona_setup": EvalPersonaSetup,
    "eval_task_config": EvalTaskConfig,
    "eval_report": EvalReportPanel,
    // 向后兼容旧 handler 名称
    "eval_execution": EvalReportPanel,
    "eval_grader_report": EvalReportPanel,
    "eval_diagnosis": EvalReportPanel,
  };
  return map[handler] || null;
}
