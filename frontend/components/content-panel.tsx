// frontend/components/content-panel.tsx
// 功能: 中栏内容展示面板，根据选中的 ContentBlock 类型渲染不同界面
// 主要组件: ContentPanel（导出）
// 特殊处理: 意图分析、消费者调研（ResearchPanel）、内涵设计（ProposalSelector）、外延设计（ChannelSelector）
// P2-5a: FieldCard / DependencyModal / ConstraintsModal 已删除（2026-02-14）

"use client";

import { PROJECT_PHASES } from "@/lib/utils";
import { agentAPI } from "@/lib/api";
import type { ContentBlock } from "@/lib/api";
import { ContentBlockEditor } from "./content-block-editor";
import { ContentBlockCard } from "./content-block-card";
import { ChannelSelector } from "./channel-selector";
import { ResearchPanel } from "./research-panel";
import { EvalPhasePanel } from "./eval-phase-panel";
import { ProposalSelector } from "./proposal-selector";

interface ContentPanelProps {
  projectId: string | null;
  currentPhase: string;
  phaseStatus?: Record<string, string>;
  selectedBlock?: ContentBlock | null;
  allBlocks?: ContentBlock[];
  onFieldsChange?: () => void;
  /** 版本创建后通知父组件刷新项目列表 */
  onVersionCreated?: () => void;
  onPhaseAdvance?: () => void;
  onBlockSelect?: (block: ContentBlock) => void;
  /** M3: 将消息发送到 Agent 对话面板（Eval 诊断→Agent 修改桥接） */
  onSendToAgent?: (message: string) => void;
}

export function ContentPanel({
  projectId,
  currentPhase,
  selectedBlock,
  allBlocks = [],
  onFieldsChange,
  onVersionCreated,
  onPhaseAdvance,
  onBlockSelect,
  onSendToAgent,
}: ContentPanelProps) {
  const currentPhaseIndex = PROJECT_PHASES.indexOf(currentPhase);
  const isLastPhase = currentPhaseIndex === PROJECT_PHASES.length - 1;
  const nextPhase = isLastPhase ? null : PROJECT_PHASES[currentPhaseIndex + 1];

  // 确认进入下一组
  const handleAdvancePhase = async () => {
    if (!projectId || !nextPhase) return;
    
    try {
      await agentAPI.advance(projectId);
      onPhaseAdvance?.();
    } catch (err) {
      console.error("进入下一组失败:", err);
      alert("进入下一组失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // ===== 早期返回（在所有Hooks之后）=====
  
  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-500">
        <div className="text-center">
          <p className="text-lg mb-2">请选择或创建一个项目</p>
          <p className="text-sm">在左侧选择项目开始工作</p>
        </div>
      </div>
    );
  }

  // ===== 树形视图选中内容块时，显示该块详情 =====
  
  // 处理阶段块/分组块点击（phase 或 group）
  if (selectedBlock && (selectedBlock.block_type === "phase" || selectedBlock.block_type === "group")) {
    const selectedPhase = selectedBlock.special_handler;
    
    // ===== 意图分析阶段特殊处理 =====
    if (selectedPhase === "intent") {
      const intentContent = selectedBlock.content?.trim();
      if (intentContent) {
        return (
          <ContentBlockEditor
            block={selectedBlock}
            projectId={projectId}
            allBlocks={allBlocks}
            onUpdate={onFieldsChange}
            onVersionCreated={onVersionCreated}
            onSendToAgent={onSendToAgent}
          />
        );
      } else {
        return (
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="text-6xl mb-4">💬</div>
            <h2 className="text-xl font-bold text-zinc-200 mb-2">意图分析</h2>
            <p className="text-zinc-400 max-w-md">
              意图分析由 AI Agent 通过对话完成。请在右侧对话框中输入&quot;开始&quot;来启动意图分析流程。
            </p>
            <p className="text-zinc-500 text-sm mt-4">
              Agent 会问你 3 个问题来了解你的项目意图。
            </p>
          </div>
        );
      }
    }
    
    // ===== 消费者调研阶段特殊处理 =====
    if (selectedPhase === "research") {
      const researchContent = selectedBlock.content?.trim();
      if (researchContent) {
        let normalizedContent: string | null = null;
        try {
          const parsed = JSON.parse(researchContent) as Record<string, unknown>;
          if (parsed && (parsed.summary || parsed.consumer_profile || parsed.personas || parsed.pain_points)) {
            const normalized = {
              summary: parsed.summary || "",
              consumer_profile: parsed.consumer_profile || {},
              pain_points: parsed.pain_points || parsed.main_pain_points || [],
              value_propositions: parsed.value_propositions || parsed.value_proposition || [],
              personas: parsed.personas || [],
              sources: parsed.sources || [],
            };
            normalizedContent = JSON.stringify(normalized, null, 2);
          }
        } catch {
          // JSON 解析失败，用 ContentBlockEditor
        }
        if (normalizedContent) {
          return (
            <ResearchPanel
              projectId={projectId}
              fieldId={selectedBlock.id}
              content={normalizedContent}
              onUpdate={onFieldsChange}
              onAdvance={handleAdvancePhase}
            />
          );
        }
        return (
          <ContentBlockEditor
            block={selectedBlock}
            projectId={projectId}
            allBlocks={allBlocks}
            onUpdate={onFieldsChange}
            onVersionCreated={onVersionCreated}
            onSendToAgent={onSendToAgent}
          />
        );
      } else {
        return (
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="text-6xl mb-4">🔍</div>
            <h2 className="text-xl font-bold text-zinc-200 mb-2">消费者调研</h2>
            <p className="text-zinc-400 max-w-md">
              消费者调研由 AI Agent 通过 DeepResearch 工具完成。请在右侧对话框中输入&quot;开始调研&quot;来启动。
            </p>
            <p className="text-zinc-500 text-sm mt-4">
              Agent 会基于你的意图分析结果，搜索相关信息并生成调研报告。
            </p>
          </div>
        );
      }
    }
    
    // ===== 评估阶段特殊处理 =====
    if (selectedPhase === "evaluate") {
      return (
        <EvalPhasePanel
          projectId={projectId}
          onFieldsChange={onFieldsChange}
          onSendToAgent={onSendToAgent}
        />
      );
    }
    
    // 有子节点的阶段/分组：显示子块卡片列表
    if (selectedBlock.children && selectedBlock.children.length > 0) {
      const phaseCount = selectedBlock.children.filter(c => c.block_type === "phase").length;
      const groupCount = selectedBlock.children.filter(c => c.block_type === "group").length;
      const fieldCount = selectedBlock.children.filter(c => c.block_type === "field").length;
      const otherCount = selectedBlock.children.length - phaseCount - groupCount - fieldCount;
      
      const parts = [];
      if (phaseCount > 0) parts.push(`${phaseCount} 个子组`);
      if (groupCount > 0) parts.push(`${groupCount} 个子组`);
      if (fieldCount > 0) parts.push(`${fieldCount} 个内容块`);
      if (otherCount > 0) parts.push(`${otherCount} 个其他`);
      const description = parts.join("、") || "暂无内容";
      
      return (
        <div className="h-full flex flex-col">
          <div className="p-4 border-b border-surface-3">
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 text-xs rounded ${
                selectedBlock.block_type === "phase" 
                  ? "bg-purple-600/20 text-purple-400"
                  : "bg-amber-600/20 text-amber-400"
              }`}>
                {selectedBlock.block_type === "phase" ? "组" : "子组"}
              </span>
              <h1 className="text-xl font-bold text-zinc-100">{selectedBlock.name}</h1>
            </div>
            <p className="text-zinc-500 text-sm mt-1">
              包含 {description}
            </p>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <div className="space-y-3">
              {selectedBlock.children.map((child) => (
                <ContentBlockCard
                  key={child.id}
                  block={child}
                  projectId={projectId || ""}
                  allBlocks={allBlocks}
                  onUpdate={onFieldsChange}
                  onSelect={() => onBlockSelect?.(child)}
                />
              ))}
            </div>
          </div>
        </div>
      );
    }
    
    // 没有子块的组
    return (
      <div className="h-full flex flex-col items-center justify-center text-zinc-500">
        <p className="text-lg mb-2">{selectedBlock.name}</p>
        <p className="text-sm">该组暂无内容块，请在左侧添加</p>
      </div>
    );
  }
  
  // 处理内容块点击（field 类型）
  if (selectedBlock && selectedBlock.block_type === "field") {
    const handler = selectedBlock.special_handler as string | null | undefined;

    // Eval V2: 即使用户点的是 eval 的单个字段块，也统一进入新三 Tab 面板，
    // 避免落回旧的 eval-field-editors 逐字段渲染路径。
    if (
      handler === "eval_persona_setup" ||
      handler === "eval_task_config" ||
      handler === "eval_report"
    ) {
      const initialTab =
        handler === "eval_task_config"
          ? "config"
          : handler === "eval_report"
          ? "report"
          : "persona";
      return (
        <EvalPhasePanel
          projectId={projectId}
          onFieldsChange={onFieldsChange}
          onSendToAgent={onSendToAgent}
          initialTab={initialTab}
        />
      );
    }
    
    // 消费者调研字段 - 检查是否有结构化内容
    if (handler === "consumer_research" || handler === "research") {
      let normalizedContent: string | null = null;
      try {
        const parsed = JSON.parse(selectedBlock.content || "{}") as Record<string, unknown>;
        if (parsed && (parsed.summary || parsed.consumer_profile || parsed.personas || parsed.pain_points)) {
          const normalized = {
            summary: parsed.summary || "",
            consumer_profile: parsed.consumer_profile || {},
            pain_points: parsed.pain_points || parsed.main_pain_points || [],
            value_propositions: parsed.value_propositions || parsed.value_proposition || [],
            personas: parsed.personas || [],
            sources: parsed.sources || [],
          };
          normalizedContent = JSON.stringify(normalized, null, 2);
        }
      } catch {
        // JSON 解析失败，继续使用默认编辑器
      }
      if (normalizedContent) {
        return (
          <ResearchPanel
            projectId={projectId}
            fieldId={selectedBlock.id}
            content={normalizedContent}
            onUpdate={onFieldsChange}
            onAdvance={handleAdvancePhase}
          />
        );
      }
    }
    
    // 内涵设计字段 - 使用 ProposalSelector
    if (handler === "design_inner") {
      let hasProposals = false;
      try {
        const parsed = JSON.parse(selectedBlock.content || "{}") as { proposals?: unknown[] };
        hasProposals = Array.isArray(parsed.proposals) && parsed.proposals.length > 0;
      } catch {
        // JSON 解析失败，使用默认编辑器
      }
      if (hasProposals) {
        return (
          <div className="h-full flex flex-col">
            <div className="p-4 border-b border-surface-3">
              <h1 className="text-xl font-bold text-zinc-100">内涵设计</h1>
              <p className="text-zinc-500 text-sm mt-1">
                选择一个方案，确认后将进入内涵生产阶段
              </p>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <ProposalSelector
                projectId={projectId}
                fieldId={selectedBlock.id}
                content={selectedBlock.content}
                onConfirm={() => {
                  onFieldsChange?.();
                  onPhaseAdvance?.();
                }}
                onFieldsCreated={onFieldsChange}
                onSave={onFieldsChange}
              />
            </div>
          </div>
        );
      }
    }
    
    // 外延设计字段 - 使用 ChannelSelector
    if (handler === "design_outer") {
      let hasChannels = false;
      try {
        const parsed = JSON.parse(selectedBlock.content || "{}") as { channels?: unknown[] };
        hasChannels = Array.isArray(parsed.channels);
      } catch {
        // JSON 解析失败
      }
      if (hasChannels) {
        return (
          <div className="h-full flex flex-col">
            <div className="p-4 border-b border-surface-3">
              <h1 className="text-xl font-bold text-zinc-100">外延设计</h1>
              <p className="text-zinc-500 text-sm mt-1">
                选择要使用的传播渠道，确认后进入外延生产
              </p>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <ChannelSelector
                projectId={projectId}
                fieldId={selectedBlock.id}
                content={selectedBlock.content}
                onConfirm={() => {
                  onFieldsChange?.();
                  onPhaseAdvance?.();
                }}
                onFieldsCreated={onFieldsChange}
                onSave={onFieldsChange}
              />
            </div>
          </div>
        );
      }
    }
    
    // 意图分析字段 - 由 Agent 处理
    if (handler === "intent_analysis" || handler === "intent") {
      const hasContent = selectedBlock.content && selectedBlock.content.trim() !== "";
      if (!hasContent) {
        return (
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="text-6xl mb-4">💬</div>
            <h2 className="text-xl font-bold text-zinc-200 mb-2">意图分析</h2>
            <p className="text-zinc-400 max-w-md">
              意图分析由 AI Agent 通过对话完成。请在右侧对话框中输入&quot;开始&quot;来启动意图分析流程。
            </p>
            <p className="text-zinc-500 text-sm mt-4">
              Agent 会问你 3 个问题来了解你的项目意图。
            </p>
          </div>
        );
      }
    }
    
    // 默认：使用 ContentBlockEditor
    return (
      <ContentBlockEditor
        block={selectedBlock}
        projectId={projectId}
        allBlocks={allBlocks}
        onUpdate={onFieldsChange}
        onVersionCreated={onVersionCreated}
        onSendToAgent={onSendToAgent}
      />
    );
  }
  
  // 没有选中块时提示用户
  if (!selectedBlock) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center">
        <div className="text-6xl mb-4">🌲</div>
        <h2 className="text-xl font-bold text-zinc-200 mb-2">树形架构模式</h2>
        <p className="text-zinc-400 max-w-md">
          请在左侧树形结构中选择一个组或字段来查看和编辑内容。
        </p>
      </div>
    );
  }

  // 兜底：未知块类型也用 ContentBlockEditor
  return (
    <ContentBlockEditor
      block={selectedBlock}
      projectId={projectId}
      allBlocks={allBlocks}
      onUpdate={onFieldsChange}
      onVersionCreated={onVersionCreated}
      onSendToAgent={onSendToAgent}
    />
  );
}
