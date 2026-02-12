// frontend/components/simulation-panel.tsx
// 功能: 消费者模拟阶段专用面板
// 主要组件: SimulationPanel, SimulationCard, SimulationDetailModal
// 包含: 人物小传选择、模拟记录卡片（可展开）、新建模拟、查看详情/日志

"use client";

import { useState, useEffect, useCallback } from "react";
import { simulationAPI, settingsAPI } from "@/lib/api";
import type { SimulationRecord, PersonaFromResearch, Persona } from "@/lib/api";
import { ChevronDown, ChevronRight, Play, RotateCcw, Trash2, Eye, Terminal, User, FileText, Clock, CheckCircle, AlertCircle, Loader2 } from "lucide-react";

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
  const [expandedSimId, setExpandedSimId] = useState<string | null>(null);
  const [detailSimId, setDetailSimId] = useState<string | null>(null);
  const [runningSimIds, setRunningSimIds] = useState<Set<string>>(new Set());
  
  // Escape 键关闭弹窗
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showCreateModal) setShowCreateModal(false);
        else if (detailSimId) setDetailSimId(null);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [showCreateModal, detailSimId]);

  const loadData = useCallback(async (isPolling = false) => {
    try {
      // 并行加载，但单独处理错误
      const [simsResult, personaResult, simListResult] = await Promise.allSettled([
        simulationAPI.list(projectId),
        simulationAPI.getPersonasFromResearch(projectId),
        settingsAPI.listSimulators(),
      ]);
      
      // 处理模拟记录
      if (simsResult.status === "fulfilled") {
        setSimulations(simsResult.value);
        const running = new Set(simsResult.value.filter(s => s.status === "running").map(s => s.id));
        setRunningSimIds(running);
      } else {
        // 轮询时静默失败，不打印错误
        if (!isPolling) {
          console.error("加载模拟记录失败:", simsResult.reason);
        }
      }
      
      // 处理人物小传
      if (personaResult.status === "fulfilled") {
        setPersonas(personaResult.value);
      } else {
        if (!isPolling) {
          console.error("加载人物小传失败:", personaResult.reason);
          setPersonas([]);
        }
      }
      
      // 处理模拟器列表
      if (simListResult.status === "fulfilled") {
        setSimulators(simListResult.value);
      } else {
        if (!isPolling) {
          console.error("加载模拟器列表失败:", simListResult.reason);
        }
      }
    } catch (err) {
      // 轮询时静默失败
      if (!isPolling) {
        console.error("加载模拟数据失败:", err);
      }
    } finally {
      if (!isPolling) {
        setLoading(false);
      }
    }
  }, [projectId]);

  useEffect(() => {
    loadData(false);  // 首次加载，显示错误
  }, [loadData]);

  // 轮询更新运行中的模拟状态
  useEffect(() => {
    if (runningSimIds.size === 0) return;
    
    const interval = setInterval(() => {
      loadData(true);  // 轮询时静默失败
    }, 3000); // 每3秒轮询一次
    
    return () => clearInterval(interval);
  }, [runningSimIds.size, loadData]);

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此模拟记录？")) return;
    try {
      await simulationAPI.delete(id);
      loadData();
    } catch (err) {
      alert("删除失败");
    }
  };

  const handleRunSimulation = async (id: string) => {
    try {
      setRunningSimIds(prev => new Set([...prev, id]));
      await simulationAPI.run(id);
      loadData();
    } catch (err) {
      alert("启动模拟失败: " + (err instanceof Error ? err.message : "未知错误"));
      setRunningSimIds(prev => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const getFieldNames = (fieldIds: string[]) => {
    return fieldIds.map(id => {
      const field = fields.find(f => f.id === id);
      return field?.name || id.substring(0, 8) + "...";
    });
  };

  const getSimulatorName = (simId: string) => {
    return simulators.find(s => s.id === simId)?.name || simId;
  };

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center text-zinc-500">
        <Loader2 className="w-5 h-5 animate-spin mr-2" />
        加载中...
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto h-full overflow-y-auto">
      {/* 标题 */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-zinc-100">消费者模拟</h1>
        <p className="text-zinc-500 mt-1">
          模拟目标用户体验内容，收集真实反馈
        </p>
      </div>

      {/* 人物小传选择 */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-zinc-200 flex items-center gap-2">
            <User className="w-5 h-5" />
            可用人物小传
          </h2>
          <span className="text-xs text-zinc-500">来自消费者调研</span>
        </div>
        
        {personas.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {personas.map((persona, idx) => (
              <div
                key={idx}
                className="p-4 bg-surface-2 border border-surface-3 rounded-xl hover:border-surface-4 transition-colors"
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

      {/* 模拟记录 */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-zinc-200 flex items-center gap-2">
            <FileText className="w-5 h-5" />
            模拟记录
          </h2>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm transition-colors flex items-center gap-2"
          >
            <Play className="w-4 h-4" />
            新建模拟
          </button>
        </div>

        {simulations.length > 0 ? (
          <div className="space-y-3">
            {simulations.map((sim) => (
              <SimulationCard
                key={sim.id}
                simulation={sim}
                simulatorName={getSimulatorName(sim.simulator_id)}
                fieldNames={getFieldNames(sim.target_field_ids || [])}
                isExpanded={expandedSimId === sim.id}
                isRunning={runningSimIds.has(sim.id)}
                onToggleExpand={() => setExpandedSimId(expandedSimId === sim.id ? null : sim.id)}
                onRun={() => handleRunSimulation(sim.id)}
                onDelete={() => handleDelete(sim.id)}
                onViewDetail={() => setDetailSimId(sim.id)}
              />
            ))}
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

      {/* 模拟详情弹窗 */}
      {detailSimId && (
        <SimulationDetailModal
          simulation={simulations.find(s => s.id === detailSimId)!}
          simulatorName={getSimulatorName(simulations.find(s => s.id === detailSimId)?.simulator_id || "")}
          fieldNames={getFieldNames(simulations.find(s => s.id === detailSimId)?.target_field_ids || [])}
          onClose={() => setDetailSimId(null)}
        />
      )}
    </div>
  );
}

// ============== 模拟卡片组件 ==============
interface SimulationCardProps {
  simulation: SimulationRecord;
  simulatorName: string;
  fieldNames: string[];
  isExpanded: boolean;
  isRunning: boolean;
  onToggleExpand: () => void;
  onRun: () => void;
  onDelete: () => void;
  onViewDetail: () => void;
}

function SimulationCard({
  simulation,
  simulatorName,
  fieldNames,
  isExpanded,
  isRunning,
  onToggleExpand,
  onRun,
  onDelete,
  onViewDetail,
}: SimulationCardProps) {
  const sim = simulation;
  const hasScores = Object.keys(sim.feedback?.scores || {}).length > 0;
  const avgScore = hasScores
    ? Object.values(sim.feedback.scores).reduce((a, b) => a + b, 0) / Object.keys(sim.feedback.scores).length
    : 0;

  const statusConfig = {
    pending: { icon: Clock, color: "text-zinc-400", bg: "bg-zinc-600/20", label: "待开始" },
    running: { icon: Loader2, color: "text-yellow-400", bg: "bg-yellow-600/20", label: "运行中" },
    completed: { icon: CheckCircle, color: "text-green-400", bg: "bg-green-600/20", label: "已完成" },
    failed: { icon: AlertCircle, color: "text-red-400", bg: "bg-red-600/20", label: "失败" },
  };
  
  const status = statusConfig[sim.status as keyof typeof statusConfig] || statusConfig.pending;
  const StatusIcon = status.icon;

  return (
    <div className="bg-surface-2 border border-surface-3 rounded-xl overflow-hidden">
      {/* 头部 - 可点击展开 */}
      <div 
        className="p-4 cursor-pointer hover:bg-surface-3/50 transition-colors"
        onClick={onToggleExpand}
      >
        <div className="flex items-center gap-4">
          {/* 展开图标 */}
          <div className="text-zinc-500">
            {isExpanded ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
          </div>
          
          {/* 人物信息 */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-zinc-200">{sim.persona?.name || "未知用户"}</span>
              <span className="text-xs text-zinc-500">({sim.persona?.source || "custom"})</span>
            </div>
            <div className="text-xs text-zinc-500 mt-1 truncate">
              {simulatorName} · {fieldNames.length > 0 ? fieldNames.join(", ") : "全部内容"}
            </div>
          </div>
          
          {/* 状态 */}
          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full ${status.bg}`}>
            <StatusIcon className={`w-3.5 h-3.5 ${status.color} ${isRunning ? "animate-spin" : ""}`} />
            <span className={`text-xs ${status.color}`}>{status.label}</span>
          </div>
          
          {/* 评分 */}
          {hasScores && (
            <div className="text-right">
              <div className="text-lg font-semibold text-zinc-200">{avgScore.toFixed(1)}</div>
              <div className="text-xs text-zinc-500">平均分</div>
            </div>
          )}
          
          {/* 开始/重新运行按钮 - 直接在头部，无需展开 */}
          {(sim.status === "pending" || sim.status === "completed" || sim.status === "failed") && (
            <button
              onClick={(e) => { e.stopPropagation(); onRun(); }}
              disabled={isRunning}
              className={`px-3 py-1.5 rounded-lg text-sm flex items-center gap-1.5 transition-colors ${
                sim.status === "pending"
                  ? "bg-brand-600 hover:bg-brand-700 text-white"
                  : "bg-surface-3 hover:bg-surface-4 text-zinc-300"
              } disabled:opacity-50`}
            >
              {sim.status === "pending" ? (
                <>
                  <Play className="w-4 h-4" />
                  开始
                </>
              ) : (
                <>
                  <RotateCcw className="w-4 h-4" />
                  重跑
                </>
              )}
            </button>
          )}
          
          {/* 时间 */}
          <div className="text-xs text-zinc-500 w-20 text-right">
            {new Date(sim.created_at).toLocaleDateString()}
          </div>
        </div>
      </div>
      
      {/* 展开内容 */}
      {isExpanded && (
        <div className="border-t border-surface-3">
          {/* 人物小传 */}
          <div className="p-4 bg-surface-1/50">
            <div className="text-xs text-zinc-500 mb-2">人物小传</div>
            <div className="text-sm text-zinc-300">
              <div className="font-medium">{sim.persona?.name}</div>
              <div className="text-xs text-zinc-500 mt-1">{sim.persona?.background}</div>
              <div className="mt-2 line-clamp-3">{sim.persona?.story}</div>
            </div>
          </div>
          
          {/* 反馈结果 */}
          {sim.status === "completed" && hasScores && (
            <div className="p-4 border-t border-surface-3">
              <div className="text-xs text-zinc-500 mb-3">反馈评分</div>
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {Object.entries(sim.feedback.scores || {}).map(([dim, score]) => (
                  <div key={dim} className="bg-surface-1 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-zinc-300">{dim}</span>
                      <span className={`text-lg font-semibold ${
                        score >= 7 ? "text-green-400" : score >= 5 ? "text-yellow-400" : "text-red-400"
                      }`}>{score}</span>
                    </div>
                    {sim.feedback.comments?.[dim] && (
                      <p className="text-xs text-zinc-500 line-clamp-2">{sim.feedback.comments[dim]}</p>
                    )}
                  </div>
                ))}
              </div>
              
              {/* 总体评价 */}
              {sim.feedback.overall && (
                <div className="mt-4 p-3 bg-surface-1 rounded-lg">
                  <div className="text-xs text-zinc-500 mb-1">总体评价</div>
                  <p className="text-sm text-zinc-300">{sim.feedback.overall}</p>
                </div>
              )}
            </div>
          )}
          
          {/* 失败信息 */}
          {sim.status === "failed" && sim.feedback?.error && (
            <div className="p-4 border-t border-surface-3">
              <div className="p-3 bg-red-600/10 border border-red-600/30 rounded-lg">
                <div className="text-xs text-red-400 mb-1">错误信息</div>
                <p className="text-sm text-red-300">{sim.feedback.error}</p>
              </div>
            </div>
          )}
          
          {/* 操作按钮 */}
          <div className="p-4 border-t border-surface-3 flex items-center gap-2">
            {sim.status === "pending" && (
              <button
                onClick={(e) => { e.stopPropagation(); onRun(); }}
                className="px-3 py-1.5 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm flex items-center gap-1.5 transition-colors"
              >
                <Play className="w-4 h-4" />
                开始模拟
              </button>
            )}
            
            {(sim.status === "completed" || sim.status === "failed") && (
              <button
                onClick={(e) => { e.stopPropagation(); onRun(); }}
                className="px-3 py-1.5 bg-surface-3 hover:bg-surface-4 rounded-lg text-sm flex items-center gap-1.5 transition-colors"
              >
                <RotateCcw className="w-4 h-4" />
                重新运行
              </button>
            )}
            
            {sim.status === "completed" && (
              <button
                onClick={(e) => { e.stopPropagation(); onViewDetail(); }}
                className="px-3 py-1.5 bg-surface-3 hover:bg-surface-4 rounded-lg text-sm flex items-center gap-1.5 transition-colors"
              >
                <Terminal className="w-4 h-4" />
                查看日志
              </button>
            )}
            
            <div className="flex-1" />
            
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              className="px-3 py-1.5 text-red-400 hover:bg-red-600/20 rounded-lg text-sm flex items-center gap-1.5 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              删除
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ============== 模拟详情弹窗 ==============
interface SimulationDetailModalProps {
  simulation: SimulationRecord;
  simulatorName: string;
  fieldNames: string[];
  onClose: () => void;
}

function SimulationDetailModal({
  simulation,
  simulatorName,
  fieldNames,
  onClose,
}: SimulationDetailModalProps) {
  const [activeTab, setActiveTab] = useState<"feedback" | "log">("feedback");
  const sim = simulation;
  const log = sim.interaction_log;
  
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* 头部 */}
        <div className="px-6 py-4 border-b border-surface-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-zinc-200">模拟详情</h3>
              <p className="text-sm text-zinc-500 mt-1">
                {sim.persona?.name} · {simulatorName}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-zinc-500 hover:text-zinc-300 text-xl"
            >
              ×
            </button>
          </div>
          
          {/* Tab 切换 */}
          <div className="flex gap-4 mt-4">
            <button
              onClick={() => setActiveTab("feedback")}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                activeTab === "feedback"
                  ? "bg-brand-600 text-white"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Eye className="w-4 h-4 inline mr-1.5" />
              反馈结果
            </button>
            <button
              onClick={() => setActiveTab("log")}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                activeTab === "log"
                  ? "bg-brand-600 text-white"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Terminal className="w-4 h-4 inline mr-1.5" />
              系统日志
            </button>
          </div>
        </div>
        
        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === "feedback" ? (
            <div className="space-y-6">
              {/* 目标内容 & 完成状态 */}
              <div className="flex flex-wrap items-center gap-4">
                <div className="flex-1">
                  <h4 className="text-sm font-medium text-zinc-400 mb-2">模拟目标</h4>
                  <div className="flex flex-wrap gap-2">
                    {fieldNames.length > 0 ? (
                      fieldNames.map((name, idx) => (
                        <span key={idx} className="px-2 py-1 bg-surface-3 rounded text-sm text-zinc-300">
                          {name}
                        </span>
                      ))
                    ) : (
                      <span className="text-zinc-500">全部内容</span>
                    )}
                  </div>
                </div>
                
                {/* 完成状态（体验式模拟） */}
                {(log as any)?.task_completed !== undefined && (
                  <div className="text-right">
                    <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${
                      (log as any).task_completed 
                        ? "bg-green-600/20 text-green-400 border border-green-600/30" 
                        : "bg-yellow-600/20 text-yellow-400 border border-yellow-600/30"
                    }`}>
                      {(log as any).task_completed ? "✓ 任务完成" : "○ 任务未完成"}
                    </div>
                    {(log as any).time_estimate && (
                      <div className="text-xs text-zinc-500 mt-1">预计耗时：{(log as any).time_estimate}</div>
                    )}
                  </div>
                )}
              </div>
              
              {/* ===== 体验式模拟：探索步骤 ===== */}
              {Array.isArray((log as any)?.steps) && (log as any).steps.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-zinc-400 mb-3 flex items-center gap-2">
                    <span className="w-5 h-5 rounded-full bg-brand-600/20 text-brand-400 flex items-center justify-center text-xs">⟳</span>
                    探索过程 ({(log as any).steps.length} 步)
                  </h4>
                  <div className="space-y-3">
                    {((log as any).steps as any[]).map((step: any, idx: number) => (
                      <div key={idx} className="bg-surface-1 rounded-lg overflow-hidden">
                        <div 
                          className="p-4 cursor-pointer hover:bg-surface-2 transition-colors"
                          onClick={(e) => {
                            const content = (e.currentTarget as HTMLElement).nextElementSibling;
                            if (content) {
                              content.classList.toggle("hidden");
                            }
                          }}
                        >
                          <div className="flex items-start gap-3">
                            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-brand-600/30 text-brand-300 flex items-center justify-center text-xs font-medium">
                              {step.step || idx + 1}
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm text-zinc-200 font-medium line-clamp-2">{step.action}</p>
                              <p className="text-xs text-zinc-500 mt-1">点击展开详情</p>
                            </div>
                          </div>
                        </div>
                        <div className="hidden border-t border-surface-3 p-4 space-y-3 bg-surface-2/50">
                          {/* 行动 */}
                          <div>
                            <div className="text-xs text-blue-400 font-medium mb-1">💭 行动</div>
                            <p className="text-sm text-zinc-300">{step.action}</p>
                          </div>
                          {/* 结果 */}
                          {step.result && (
                            <div>
                              <div className="text-xs text-green-400 font-medium mb-1">📋 发现</div>
                              <p className="text-sm text-zinc-300">{step.result}</p>
                            </div>
                          )}
                          {/* 感受 */}
                          {step.feeling && (
                            <div>
                              <div className="text-xs text-purple-400 font-medium mb-1">💡 感受</div>
                              <p className="text-sm text-zinc-400 italic">"{step.feeling}"</p>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* ===== 亮点 & 痛点 ===== */}
              {(Array.isArray((log as any)?.delights) || Array.isArray((log as any)?.pain_points)) && (
                <div className="grid md:grid-cols-2 gap-4">
                  {/* 亮点 */}
                  {Array.isArray((log as any)?.delights) && (log as any).delights.length > 0 && (
                    <div className="bg-green-600/5 border border-green-600/20 rounded-lg p-4">
                      <h4 className="text-sm font-medium text-green-400 mb-3 flex items-center gap-2">
                        ✨ 亮点 ({(log as any).delights.length})
                      </h4>
                      <ul className="space-y-2">
                        {((log as any).delights as string[]).map((item: string, idx: number) => (
                          <li key={idx} className="text-sm text-zinc-300 flex gap-2">
                            <span className="text-green-400 flex-shrink-0">+</span>
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {/* 痛点 */}
                  {Array.isArray((log as any)?.pain_points) && (log as any).pain_points.length > 0 && (
                    <div className="bg-red-600/5 border border-red-600/20 rounded-lg p-4">
                      <h4 className="text-sm font-medium text-red-400 mb-3 flex items-center gap-2">
                        ⚠️ 痛点 ({(log as any).pain_points.length})
                      </h4>
                      <ul className="space-y-2">
                        {((log as any).pain_points as string[]).map((item: string, idx: number) => (
                          <li key={idx} className="text-sm text-zinc-300 flex gap-2">
                            <span className="text-red-400 flex-shrink-0">−</span>
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
              
              {/* ===== 改进建议 ===== */}
              {Array.isArray((log as any)?.suggestions) && (log as any).suggestions.length > 0 && (
                <div className="bg-yellow-600/5 border border-yellow-600/20 rounded-lg p-4">
                  <h4 className="text-sm font-medium text-yellow-400 mb-3 flex items-center gap-2">
                    💡 改进建议 ({(log as any).suggestions.length})
                  </h4>
                  <ul className="space-y-2">
                    {((log as any).suggestions as string[]).map((item: string, idx: number) => (
                      <li key={idx} className="text-sm text-zinc-300 flex gap-2">
                        <span className="text-yellow-400 flex-shrink-0">{idx + 1}.</span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              
              {/* 评分详情 */}
              {Object.keys(sim.feedback?.scores || {}).length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-zinc-400 mb-3">评分详情</h4>
                  <div className="space-y-4">
                    {Object.entries(sim.feedback.scores || {}).map(([dim, score]) => (
                      <div key={dim} className="bg-surface-1 rounded-lg p-4">
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-medium text-zinc-200">{dim}</span>
                          <div className="flex items-center gap-2">
                            {/* 评分条 */}
                            <div className="w-32 h-2 bg-surface-3 rounded-full overflow-hidden">
                              <div 
                                className={`h-full rounded-full ${
                                  score >= 7 ? "bg-green-500" : score >= 5 ? "bg-yellow-500" : "bg-red-500"
                                }`}
                                style={{ width: `${(score as number) * 10}%` }}
                              />
                            </div>
                            <span className={`text-lg font-bold ${
                              score >= 7 ? "text-green-400" : score >= 5 ? "text-yellow-400" : "text-red-400"
                            }`}>{score}</span>
                          </div>
                        </div>
                        {sim.feedback.comments?.[dim] && (
                          <p className="text-sm text-zinc-400">{sim.feedback.comments[dim]}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* 总体评价 */}
              {sim.feedback?.overall && (
                <div>
                  <h4 className="text-sm font-medium text-zinc-400 mb-2">总体评价</h4>
                  <div className="bg-surface-1 rounded-lg p-4">
                    <p className="text-zinc-300">{sim.feedback.overall}</p>
                  </div>
                </div>
              )}
              
              {/* 是否推荐 */}
              {(log as any)?.would_recommend !== undefined && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-zinc-500">是否会推荐：</span>
                  <span className={`font-medium ${(log as any).would_recommend ? "text-green-400" : "text-red-400"}`}>
                    {(log as any).would_recommend ? "✓ 会推荐" : "✗ 不会推荐"}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-6">
              {/* 系统提示词输入 */}
              {log && typeof log === "object" && (
                <>
                  {/* 输入内容 */}
                  {(log as any).input && (
                    <div>
                      <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-blue-600/20 text-blue-400 rounded text-xs">INPUT</span>
                        模拟输入内容
                      </h4>
                      <pre className="bg-zinc-900 rounded-lg p-4 text-sm text-zinc-300 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
                        {(log as any).input}
                      </pre>
                    </div>
                  )}
                  
                  {/* 系统提示词 */}
                  {(log as any).system_prompt && (
                    <div>
                      <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-purple-600/20 text-purple-400 rounded text-xs">SYSTEM</span>
                        系统提示词
                      </h4>
                      <pre className="bg-zinc-900 rounded-lg p-4 text-sm text-zinc-300 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
                        {(log as any).system_prompt}
                      </pre>
                    </div>
                  )}
                  
                  {/* 输出内容 */}
                  {(log as any).output && (
                    <div>
                      <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-green-600/20 text-green-400 rounded text-xs">OUTPUT</span>
                        模型输出
                      </h4>
                      <pre className="bg-zinc-900 rounded-lg p-4 text-sm text-zinc-300 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
                        {(log as any).output}
                      </pre>
                    </div>
                  )}
                  
                  {/* 对话历史（对话式模拟 - 新格式：log.dialogue） */}
                  {(log as any).type === "dialogue" && Array.isArray((log as any).dialogue) && (
                    <div className="space-y-6">
                      {/* 对话双方的系统提示词 */}
                      <div className="grid md:grid-cols-2 gap-4">
                        {/* 用户侧系统提示词 */}
                        {(log as any).user_system_prompt && (
                          <div>
                            <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
                              <span className="px-2 py-0.5 bg-blue-600/20 text-blue-400 rounded text-xs">PERSONA</span>
                              {(log as any).user_name || "用户"} 系统提示词
                            </h4>
                            <pre className="bg-zinc-900 rounded-lg p-3 text-xs text-zinc-300 overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto">
                              {(log as any).user_system_prompt}
                            </pre>
                          </div>
                        )}
                        
                        {/* 内容侧系统提示词 */}
                        {(log as any).content_system_prompt && (
                          <div>
                            <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
                              <span className="px-2 py-0.5 bg-purple-600/20 text-purple-400 rounded text-xs">CONTENT</span>
                              {(log as any).content_name || "内容"} 系统提示词
                            </h4>
                            <pre className="bg-zinc-900 rounded-lg p-3 text-xs text-zinc-300 overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto">
                              {(log as any).content_system_prompt}
                            </pre>
                          </div>
                        )}
                      </div>
                      
                      {/* 对话记录 */}
                      <div>
                        <h4 className="text-sm font-medium text-zinc-400 mb-3">对话记录</h4>
                        <div className="space-y-3">
                          {((log as any).dialogue as any[]).map((msg: any, idx: number) => (
                            <div 
                              key={idx} 
                              className={`p-3 rounded-lg ${
                                msg.role === "user" 
                                  ? "bg-blue-600/10 border border-blue-600/30 ml-0 mr-8" 
                                  : "bg-purple-600/10 border border-purple-600/30 ml-8 mr-0"
                              }`}
                            >
                              <div className="flex items-center gap-2 mb-1">
                                <span className={`text-xs font-medium ${
                                  msg.role === "user" ? "text-blue-400" : "text-purple-400"
                                }`}>
                                  [{msg.name || (msg.role === "user" ? "用户" : "内容")}]
                                </span>
                                {msg.turn && (
                                  <span className="text-xs text-zinc-600">第{msg.turn}轮</span>
                                )}
                              </div>
                              <p className="text-sm text-zinc-300 whitespace-pre-wrap">{msg.content}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                      
                      {/* 评估系统提示词 */}
                      {(log as any).eval_system_prompt && (
                        <div>
                          <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
                            <span className="px-2 py-0.5 bg-yellow-600/20 text-yellow-400 rounded text-xs">EVAL</span>
                            评估系统提示词
                          </h4>
                          <pre className="bg-zinc-900 rounded-lg p-3 text-xs text-zinc-300 overflow-x-auto whitespace-pre-wrap max-h-32 overflow-y-auto">
                            {(log as any).eval_system_prompt}
                          </pre>
                        </div>
                      )}
                      
                      {/* 评估输出 */}
                      {(log as any).eval_output && (
                        <div>
                          <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
                            <span className="px-2 py-0.5 bg-green-600/20 text-green-400 rounded text-xs">EVAL OUTPUT</span>
                            评估原始输出
                          </h4>
                          <pre className="bg-zinc-900 rounded-lg p-3 text-xs text-zinc-300 overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto">
                            {(log as any).eval_output}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                  
                  {/* 旧格式对话历史（向后兼容） */}
                  {Array.isArray(log) && (
                    <div>
                      <h4 className="text-sm font-medium text-zinc-400 mb-2">对话历史</h4>
                      <div className="space-y-3">
                        {log.map((msg: any, idx: number) => (
                          <div key={idx} className={`p-3 rounded-lg ${
                            msg.role === "user" ? "bg-blue-600/10 border border-blue-600/30" : "bg-surface-1"
                          }`}>
                            <div className="text-xs text-zinc-500 mb-1">
                              {msg.name || (msg.role === "user" ? "用户" : "助手")}
                            </div>
                            <p className="text-sm text-zinc-300 whitespace-pre-wrap">{msg.content}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* 如果日志为空或格式不明 */}
                  {!((log as any).input || (log as any).system_prompt || (log as any).output || (log as any).dialogue || Array.isArray(log)) && (
                    <div>
                      <h4 className="text-sm font-medium text-zinc-400 mb-2">原始日志</h4>
                      <pre className="bg-zinc-900 rounded-lg p-4 text-sm text-zinc-300 overflow-x-auto whitespace-pre-wrap">
                        {JSON.stringify(log, null, 2)}
                      </pre>
                    </div>
                  )}
                </>
              )}
              
              {!log && (
                <div className="text-center text-zinc-500 py-8">
                  暂无日志数据
                </div>
              )}
            </div>
          )}
        </div>
        
        {/* 底部 */}
        <div className="px-6 py-4 border-t border-surface-3 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg text-sm"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}

// ============== 新建模拟弹窗 ==============
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

  // 可选的内容块（已完成的内涵/外延字段）
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
                <div className="space-y-2 max-h-48 overflow-y-auto">
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
              <div className="text-sm text-zinc-500">暂无已完成的内容块</div>
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
