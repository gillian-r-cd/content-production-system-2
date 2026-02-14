// frontend/components/eval-phase-panel.tsx
// 功能: 传统流程评估阶段面板，自动创建并管理 eval_task_config 和 eval_report 内容块
// 主要组件: EvalPhasePanel
// 复用 eval-field-editors.tsx 中的 EvalTaskConfig 和 EvalReportPanel

"use client";

import React, { useState, useEffect, useCallback } from "react";
import { blockAPI } from "@/lib/api";
import type { ContentBlock } from "@/lib/api";
import { EvalTaskConfig, EvalReportPanel } from "./eval-field-editors";
import { SlidersHorizontal, BarChart3, Loader2 } from "lucide-react";

interface EvalPhasePanelProps {
  projectId: string | null;
  onFieldsChange?: () => void;
}

export function EvalPhasePanel({ projectId, onFieldsChange }: EvalPhasePanelProps) {
  const [configBlock, setConfigBlock] = useState<ContentBlock | null>(null);
  const [reportBlock, setReportBlock] = useState<ContentBlock | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"config" | "report">("config");

  // 加载或创建 eval 专用 ContentBlocks
  const loadOrCreateEvalBlocks = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      // 尝试获取已有的 eval blocks
      const tree = await blockAPI.getProjectBlocks(projectId);
      const allBlocks: ContentBlock[] = [];
      const flatten = (blocks: ContentBlock[]) => {
        for (const b of blocks) {
          allBlocks.push(b);
          if (b.children) flatten(b.children);
        }
      };
      flatten(tree.blocks || []);

      let config = allBlocks.find(b => b.special_handler === "eval_task_config");
      let report = allBlocks.find(b => b.special_handler === "eval_report");

      // 如果不存在，创建它们
      if (!config) {
        config = await blockAPI.create({
          project_id: projectId,
          name: "评估配置",
          block_type: "field",
          content: "",
          special_handler: "eval_task_config",
          order_index: 100,
        });
      }
      if (!report) {
        report = await blockAPI.create({
          project_id: projectId,
          name: "评估报告",
          block_type: "field",
          content: "",
          special_handler: "eval_report",
          order_index: 101,
        });
      }

      setConfigBlock(config);
      setReportBlock(report);
    } catch (e) {
      console.error("加载评估配置失败:", e);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadOrCreateEvalBlocks();
  }, [loadOrCreateEvalBlocks]);

  const handleUpdate = () => {
    loadOrCreateEvalBlocks();
    onFieldsChange?.();
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-purple-400 mx-auto mb-3" />
          <p className="text-zinc-400 text-sm">正在加载评估面板...</p>
        </div>
      </div>
    );
  }

  if (!projectId) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-zinc-500">请先选择项目</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Tab 切换 */}
      <div className="p-4 border-b border-surface-3">
        <h1 className="text-xl font-bold text-zinc-100 mb-3">评估</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setActiveTab("config")}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === "config"
                ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                : "bg-surface-2 text-zinc-400 hover:text-zinc-200 border border-transparent"
            }`}
          >
            <SlidersHorizontal className="w-4 h-4" />
            评估配置
          </button>
          <button
            onClick={() => setActiveTab("report")}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === "report"
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                : "bg-surface-2 text-zinc-400 hover:text-zinc-200 border border-transparent"
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            评估报告
          </button>
        </div>
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === "config" && configBlock && (
          <EvalTaskConfig
            block={configBlock}
            projectId={projectId}
            onUpdate={handleUpdate}
          />
        )}
        {activeTab === "report" && reportBlock && (
          <EvalReportPanel
            block={reportBlock}
            projectId={projectId}
            onUpdate={handleUpdate}
          />
        )}
      </div>
    </div>
  );
}

