// frontend/components/eval-panel.tsx
// 功能: Eval 评估面板 - 展示评估结果和历史运行

"use client";

import { useState, useEffect } from "react";
import { evalAPI, EvalRun, EvalTrial } from "@/lib/api";
import { cn } from "@/lib/utils";

interface EvalPanelProps {
  projectId: string;
  className?: string;
}

const ROLE_INFO: Record<string, { name: string; icon: string; color: string }> = {
  coach: { name: "教练", icon: "🎯", color: "text-blue-400" },
  editor: { name: "编辑", icon: "✍️", color: "text-green-400" },
  expert: { name: "专家", icon: "🔬", color: "text-purple-400" },
  consumer: { name: "消费者", icon: "👤", color: "text-yellow-400" },
  seller: { name: "销售", icon: "💰", color: "text-red-400" },
};

export function EvalPanel({ projectId, className }: EvalPanelProps) {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<EvalRun | null>(null);
  const [trials, setTrials] = useState<EvalTrial[]>([]);
  const [selectedTrial, setSelectedTrial] = useState<EvalTrial | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadRuns();
  }, [projectId]);

  const loadRuns = async () => {
    try {
      const data = await evalAPI.listRuns(projectId);
      setRuns(data);
      if (data.length > 0 && !selectedRun) {
        setSelectedRun(data[0]);
        loadTrials(data[0].id);
      }
    } catch (err) {
      console.error("加载评估运行失败:", err);
    }
  };

  const loadTrials = async (runId: string) => {
    try {
      const data = await evalAPI.getTrials(runId);
      setTrials(data);
    } catch (err) {
      console.error("加载 Trial 失败:", err);
    }
  };

  const handleRunEval = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const result = await evalAPI.runEval({
        project_id: projectId,
        name: `评估运行 #${runs.length + 1}`,
      });
      setSelectedRun(result);
      await loadRuns();
      await loadTrials(result.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "评估失败");
    } finally {
      setIsRunning(false);
    }
  };

  const handleRunSingleTrial = async (role: string) => {
    setIsRunning(true);
    setError(null);
    try {
      const result = await evalAPI.runSingleTrial({
        project_id: projectId,
        role,
        interaction_mode: role === "consumer" || role === "seller" ? "dialogue" : "review",
      });
      setSelectedTrial(result);
      await loadRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : "评估失败");
    } finally {
      setIsRunning(false);
    }
  };

  const ScoreBar = ({ score, max = 10 }: { score: number; max?: number }) => {
    const pct = (score / max) * 100;
    const color = pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-yellow-500" : "bg-red-500";
    return (
      <div className="flex items-center gap-2">
        <div className="w-24 h-2 bg-surface-3 rounded-full overflow-hidden">
          <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
        </div>
        <span className="text-sm font-mono">{score.toFixed(1)}</span>
      </div>
    );
  };

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Header */}
      <div className="p-4 border-b border-surface-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">📊 内容评估</h2>
          <button
            onClick={handleRunEval}
            disabled={isRunning}
            className={cn(
              "px-4 py-2 rounded-lg text-sm font-medium transition-all",
              isRunning
                ? "bg-surface-3 text-muted cursor-not-allowed"
                : "bg-brand-500 text-white hover:bg-brand-600"
            )}
          >
            {isRunning ? "评估中..." : "运行完整评估"}
          </button>
        </div>
        {error && (
          <div className="mt-2 p-2 bg-red-500/10 text-red-400 text-sm rounded-lg">{error}</div>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        {/* Quick role buttons */}
        <div className="p-4 border-b border-surface-3">
          <div className="text-sm text-muted mb-2">单项评估：</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(ROLE_INFO).map(([role, info]) => (
              <button
                key={role}
                onClick={() => handleRunSingleTrial(role)}
                disabled={isRunning}
                className="px-3 py-1.5 bg-surface-2 hover:bg-surface-3 rounded-lg text-sm transition-colors disabled:opacity-50"
              >
                {info.icon} {info.name}
              </button>
            ))}
          </div>
        </div>

        {/* Run history */}
        {runs.length > 0 ? (
          <div className="p-4 space-y-4">
            {/* Run selector */}
            <div className="flex gap-2 overflow-x-auto">
              {runs.map((run) => (
                <button
                  key={run.id}
                  onClick={() => { setSelectedRun(run); loadTrials(run.id); }}
                  className={cn(
                    "px-3 py-2 rounded-lg text-sm whitespace-nowrap transition-colors",
                    selectedRun?.id === run.id
                      ? "bg-brand-500/20 text-brand-400 border border-brand-500/30"
                      : "bg-surface-2 hover:bg-surface-3"
                  )}
                >
                  <div className="font-medium">{run.name}</div>
                  <div className="text-xs text-muted">
                    {run.overall_score ? `${run.overall_score}/10` : run.status}
                  </div>
                </button>
              ))}
            </div>

            {/* Selected run details */}
            {selectedRun && (
              <div className="space-y-4">
                {/* Overall score */}
                {selectedRun.overall_score && (
                  <div className="p-4 bg-surface-2 rounded-xl">
                    <div className="flex items-center justify-between">
                      <span className="text-muted">综合评分</span>
                      <span className="text-2xl font-bold">
                        {selectedRun.overall_score}/10
                      </span>
                    </div>
                    <ScoreBar score={selectedRun.overall_score} />
                  </div>
                )}

                {/* Role scores */}
                {Object.keys(selectedRun.role_scores || {}).length > 0 && (
                  <div className="p-4 bg-surface-2 rounded-xl space-y-3">
                    <div className="text-sm font-medium">各角色评分</div>
                    {Object.entries(selectedRun.role_scores).map(([role, score]) => {
                      const info = ROLE_INFO[role] || { name: role, icon: "📋", color: "text-gray-400" };
                      return (
                        <div key={role} className="flex items-center justify-between">
                          <span className={cn("text-sm", info.color)}>
                            {info.icon} {info.name}
                          </span>
                          <ScoreBar score={score} />
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Summary */}
                {selectedRun.summary && (
                  <div className="p-4 bg-surface-2 rounded-xl">
                    <div className="text-sm font-medium mb-2">综合诊断</div>
                    <div className="text-sm text-muted whitespace-pre-wrap">{selectedRun.summary}</div>
                  </div>
                )}

                {/* Trials */}
                {trials.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-sm font-medium">评估详情</div>
                    {trials.map((trial) => {
                      const info = ROLE_INFO[trial.role] || { name: trial.role, icon: "📋", color: "text-gray-400" };
                      return (
                        <button
                          key={trial.id}
                          onClick={() => setSelectedTrial(selectedTrial?.id === trial.id ? null : trial)}
                          className="w-full p-3 bg-surface-2 rounded-lg text-left hover:bg-surface-3 transition-colors"
                        >
                          <div className="flex items-center justify-between">
                            <span className={cn("text-sm font-medium", info.color)}>
                              {info.icon} {info.name}
                              <span className="text-muted ml-2 font-normal">
                                ({trial.interaction_mode})
                              </span>
                            </span>
                            <span className="text-sm font-mono">
                              {trial.overall_score ? `${trial.overall_score}/10` : trial.status}
                            </span>
                          </div>
                          
                          {/* Expanded trial details */}
                          {selectedTrial?.id === trial.id && (
                            <div className="mt-3 space-y-2 border-t border-surface-3 pt-3">
                              {/* Dimension scores */}
                              {trial.result?.scores && Object.entries(trial.result.scores).map(([dim, score]) => (
                                <div key={dim} className="flex items-center justify-between text-sm">
                                  <span className="text-muted">{dim}</span>
                                  <ScoreBar score={Number(score)} />
                                </div>
                              ))}
                              
                              {/* Summary */}
                              {trial.result?.summary && (
                                <div className="text-sm text-muted mt-2 whitespace-pre-wrap">
                                  {trial.result.summary}
                                </div>
                              )}
                              
                              {/* Dialogue nodes (if any) */}
                              {trial.nodes && trial.nodes.length > 0 && trial.interaction_mode === "dialogue" && (
                                <div className="mt-2 space-y-1">
                                  <div className="text-xs text-muted">对话记录：</div>
                                  {trial.nodes.map((node, i) => {
                                    const roleLabel: Record<string, string> = {
                                      consumer: "🗣 消费者",
                                      seller: "💼 销售",
                                      content_rep: "📄 内容",
                                    };
                                    return (
                                      <div key={i} className="text-xs p-2 bg-surface-1 rounded">
                                        <span className="font-medium">{roleLabel[node.role] || node.role}</span>
                                        <span className="text-muted ml-1">(第{node.turn || "?"}轮)</span>
                                        <div className="mt-1">{node.content}</div>
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                              
                              {/* Cost info */}
                              <div className="text-xs text-muted mt-2">
                                Tokens: {trial.tokens_in} in / {trial.tokens_out} out | 
                                Cost: ${trial.cost?.toFixed(4) || "0"}
                              </div>
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 text-muted">
            <div className="text-4xl mb-4">📊</div>
            <p className="text-lg mb-2">暂无评估记录</p>
            <p className="text-sm mb-6">运行评估来获取内容质量反馈</p>
            <button
              onClick={handleRunEval}
              disabled={isRunning}
              className="px-6 py-2.5 bg-brand-500 text-white rounded-lg hover:bg-brand-600 transition-colors disabled:opacity-50"
            >
              {isRunning ? "评估中..." : "开始评估"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
