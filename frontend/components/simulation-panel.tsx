// frontend/components/simulation-panel.tsx
// 功能: 消费者模拟阶段专用面板
// 主要组件: SimulationPanel
// 包含: 人物小传选择、模拟记录表格、新建模拟

"use client";

import { useState, useEffect } from "react";
import { simulationAPI, settingsAPI } from "@/lib/api";
import type { SimulationRecord, PersonaFromResearch, Persona } from "@/lib/api";

interface SimulationPanelProps {
  projectId: string;
  fields: any[];
  onSimulationCreated?: () => void;
}

export function SimulationPanel({
  projectId,
  fields,
  onSimulationCreated,
}: SimulationPanelProps) {
  const [simulations, setSimulations] = useState<SimulationRecord[]>([]);
  const [personas, setPersonas] = useState<PersonaFromResearch[]>([]);
  const [simulators, setSimulators] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);

  useEffect(() => {
    loadData();
  }, [projectId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [sims, personaList, simList] = await Promise.all([
        simulationAPI.list(projectId),
        simulationAPI.getPersonasFromResearch(projectId),
        settingsAPI.listSimulators(),
      ]);
      setSimulations(sims);
      setPersonas(personaList);
      setSimulators(simList);
    } catch (err) {
      console.error("加载模拟数据失败:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此模拟记录？")) return;
    try {
      await simulationAPI.delete(id);
      loadData();
    } catch (err) {
      alert("删除失败");
    }
  };

  if (loading) {
    return <div className="p-6 text-zinc-500">加载中...</div>;
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* 标题 */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-zinc-100">消费者模拟</h1>
        <p className="text-zinc-500 mt-1">
          模拟目标用户体验内容，收集反馈
        </p>
      </div>

      {/* 人物小传选择 */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-zinc-200">可用人物小传</h2>
          <span className="text-xs text-zinc-500">来自消费者调研</span>
        </div>
        
        {personas.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2">
            {personas.map((persona, idx) => (
              <div
                key={idx}
                className="p-4 bg-surface-2 border border-surface-3 rounded-xl"
              >
                <h3 className="font-medium text-zinc-200">{persona.name}</h3>
                <p className="text-xs text-zinc-500 mt-1">{persona.background}</p>
                <p className="text-sm text-zinc-400 mt-2 line-clamp-3">
                  {persona.story}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 bg-surface-2 border border-surface-3 rounded-xl text-center text-zinc-500">
            <p>暂无人物小传</p>
            <p className="text-xs mt-1">完成消费者调研后会自动提取人物小传</p>
          </div>
        )}
      </div>

      {/* 模拟记录表格 */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-zinc-200">模拟记录</h2>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm transition-colors"
          >
            + 新建模拟
          </button>
        </div>

        {simulations.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-3">
                  <th className="text-left py-3 px-3 text-zinc-500">人物</th>
                  <th className="text-left py-3 px-3 text-zinc-500">模拟器</th>
                  <th className="text-left py-3 px-3 text-zinc-500">状态</th>
                  <th className="text-right py-3 px-3 text-zinc-500">评分</th>
                  <th className="text-left py-3 px-3 text-zinc-500">时间</th>
                  <th className="text-right py-3 px-3 text-zinc-500">操作</th>
                </tr>
              </thead>
              <tbody>
                {simulations.map((sim) => {
                  const simulator = simulators.find(s => s.id === sim.simulator_id);
                  const avgScore = Object.values(sim.feedback.scores || {}).reduce(
                    (a, b) => a + b, 0
                  ) / (Object.keys(sim.feedback.scores || {}).length || 1);
                  
                  return (
                    <tr key={sim.id} className="border-b border-surface-3/50 hover:bg-surface-2">
                      <td className="py-3 px-3">
                        <div className="font-medium text-zinc-200">{sim.persona.name || "未知"}</div>
                        <div className="text-xs text-zinc-500">{sim.persona.source}</div>
                      </td>
                      <td className="py-3 px-3 text-zinc-300">
                        {simulator?.name || sim.simulator_id}
                      </td>
                      <td className="py-3 px-3">
                        <span className={`px-2 py-0.5 rounded text-xs ${
                          sim.status === "completed" 
                            ? "bg-green-600/20 text-green-400"
                            : sim.status === "running"
                            ? "bg-yellow-600/20 text-yellow-400"
                            : "bg-zinc-600/20 text-zinc-400"
                        }`}>
                          {sim.status === "completed" ? "已完成" 
                            : sim.status === "running" ? "进行中" 
                            : "待开始"}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right">
                        {Object.keys(sim.feedback.scores || {}).length > 0 ? (
                          <span className="text-zinc-200">{avgScore.toFixed(1)}</span>
                        ) : (
                          <span className="text-zinc-500">-</span>
                        )}
                      </td>
                      <td className="py-3 px-3 text-zinc-400">
                        {new Date(sim.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <button
                          onClick={() => handleDelete(sim.id)}
                          className="text-red-400 hover:text-red-300 text-sm"
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-8 bg-surface-2 border border-surface-3 rounded-xl text-center text-zinc-500">
            <p>暂无模拟记录</p>
            <p className="text-xs mt-1">点击"新建模拟"开始消费者模拟</p>
          </div>
        )}
      </div>

      {/* 新建模拟弹窗 */}
      {showCreateModal && (
        <CreateSimulationModal
          projectId={projectId}
          personas={personas}
          simulators={simulators}
          fields={fields}
          onClose={() => setShowCreateModal(false)}
          onCreated={() => {
            setShowCreateModal(false);
            loadData();
            onSimulationCreated?.();
          }}
        />
      )}
    </div>
  );
}

interface CreateSimulationModalProps {
  projectId: string;
  personas: PersonaFromResearch[];
  simulators: any[];
  fields: any[];
  onClose: () => void;
  onCreated: () => void;
}

function CreateSimulationModal({
  projectId,
  personas,
  simulators,
  fields,
  onClose,
  onCreated,
}: CreateSimulationModalProps) {
  const [simulatorId, setSimulatorId] = useState(simulators[0]?.id || "");
  const [personaSource, setPersonaSource] = useState<"research" | "custom">("research");
  const [selectedPersonaIdx, setSelectedPersonaIdx] = useState(0);
  const [customPersona, setCustomPersona] = useState({ name: "", background: "", story: "" });
  const [selectedFieldIds, setSelectedFieldIds] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);

  // 可选的字段（已完成的内涵/外延字段）
  const completedFields = fields.filter(
    (f) => f.status === "completed" && 
    ["produce_inner", "produce_outer"].includes(f.phase)
  );

  const handleCreate = async () => {
    if (!simulatorId) {
      alert("请选择模拟器");
      return;
    }

    const persona: Persona = personaSource === "research" && personas[selectedPersonaIdx]
      ? {
          source: "research",
          name: personas[selectedPersonaIdx].name,
          background: personas[selectedPersonaIdx].background,
          story: personas[selectedPersonaIdx].story,
        }
      : {
          source: "custom",
          name: customPersona.name,
          background: customPersona.background,
          story: customPersona.story,
        };

    if (!persona.name) {
      alert("请填写人物名称");
      return;
    }

    setCreating(true);
    try {
      await simulationAPI.create({
        project_id: projectId,
        simulator_id: simulatorId,
        target_field_ids: selectedFieldIds,
        persona,
      });
      onCreated();
    } catch (err) {
      alert("创建失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-2xl max-h-[85vh] overflow-hidden">
        <div className="px-4 py-3 border-b border-surface-3">
          <h3 className="font-medium text-zinc-200">新建消费者模拟</h3>
        </div>

        <div className="p-4 max-h-[60vh] overflow-y-auto space-y-6">
          {/* 选择模拟器 */}
          <div>
            <label className="block text-sm text-zinc-400 mb-2">模拟器类型</label>
            <select
              value={simulatorId}
              onChange={(e) => setSimulatorId(e.target.value)}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
            >
              {simulators.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} - {s.interaction_type}
                </option>
              ))}
            </select>
          </div>

          {/* 人物来源选择 */}
          <div>
            <label className="block text-sm text-zinc-400 mb-2">人物画像来源</label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  checked={personaSource === "research"}
                  onChange={() => setPersonaSource("research")}
                />
                <span className="text-zinc-200">从消费者调研选择</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  checked={personaSource === "custom"}
                  onChange={() => setPersonaSource("custom")}
                />
                <span className="text-zinc-200">自定义</span>
              </label>
            </div>
          </div>

          {/* 人物选择/输入 */}
          {personaSource === "research" ? (
            <div>
              <label className="block text-sm text-zinc-400 mb-2">选择人物小传</label>
              {personas.length > 0 ? (
                <div className="space-y-2">
                  {personas.map((p, idx) => (
                    <label
                      key={idx}
                      className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer border ${
                        selectedPersonaIdx === idx
                          ? "border-brand-500 bg-brand-600/10"
                          : "border-surface-3 hover:bg-surface-3"
                      }`}
                    >
                      <input
                        type="radio"
                        checked={selectedPersonaIdx === idx}
                        onChange={() => setSelectedPersonaIdx(idx)}
                        className="mt-1"
                      />
                      <div>
                        <div className="font-medium text-zinc-200">{p.name}</div>
                        <div className="text-xs text-zinc-500">{p.background}</div>
                        <div className="text-sm text-zinc-400 mt-1 line-clamp-2">{p.story}</div>
                      </div>
                    </label>
                  ))}
                </div>
              ) : (
                <div className="p-4 text-center text-zinc-500 bg-surface-1 rounded-lg">
                  暂无可用的人物小传，请选择"自定义"
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-zinc-400 mb-1">人物名称</label>
                <input
                  type="text"
                  value={customPersona.name}
                  onChange={(e) => setCustomPersona({ ...customPersona, name: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
                  placeholder="如：张医生"
                />
              </div>
              <div>
                <label className="block text-sm text-zinc-400 mb-1">背景描述</label>
                <input
                  type="text"
                  value={customPersona.background}
                  onChange={(e) => setCustomPersona({ ...customPersona, background: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
                  placeholder="如：某三甲医院主任医师，从业15年"
                />
              </div>
              <div>
                <label className="block text-sm text-zinc-400 mb-1">人物小传</label>
                <textarea
                  value={customPersona.story}
                  onChange={(e) => setCustomPersona({ ...customPersona, story: e.target.value })}
                  rows={4}
                  className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200"
                  placeholder="详细描述人物的背景、需求、痛点等..."
                />
              </div>
            </div>
          )}

          {/* 选择要模拟的内容 */}
          <div>
            <label className="block text-sm text-zinc-400 mb-2">选择要模拟的内容（可选）</label>
            {completedFields.length > 0 ? (
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {completedFields.map((f) => (
                  <label key={f.id} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedFieldIds.includes(f.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedFieldIds([...selectedFieldIds, f.id]);
                        } else {
                          setSelectedFieldIds(selectedFieldIds.filter((id) => id !== f.id));
                        }
                      }}
                    />
                    <span className="text-zinc-200">{f.name}</span>
                    <span className="text-xs text-zinc-500">({f.phase})</span>
                  </label>
                ))}
              </div>
            ) : (
              <div className="text-sm text-zinc-500">暂无已完成的内容字段</div>
            )}
          </div>
        </div>

        <div className="px-4 py-3 border-t border-surface-3 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg"
          >
            取消
          </button>
          <button
            onClick={handleCreate}
            disabled={creating}
            className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg disabled:opacity-50"
          >
            {creating ? "创建中..." : "创建模拟"}
          </button>
        </div>
      </div>
    </div>
  );
}

