// frontend/components/content-panel.tsx
// 功能: 中栏内容展示面板，根据选中的 ContentBlock 类型渲染不同界面
// 主要组件: ContentPanel（导出）
// 特殊处理: 意图分析、消费者调研（ResearchPanel）、内涵设计（ProposalSelector）、外延设计（ChannelSelector）
// P2-5a: FieldCard / DependencyModal / ConstraintsModal 已删除（2026-02-14）

"use client";

import { useRef, useState, useCallback } from "react";
import type { ContentBlock, AgentSelectionRef } from "@/lib/api";
import { formatProjectText, isJaProjectLocale, projectUiText } from "@/lib/project-locale";
import { useUiLocale } from "@/lib/ui-locale";
import { ContentBlockEditor } from "./content-block-editor";
import { ContentBlockCard } from "./content-block-card";
import { ChannelSelector } from "./channel-selector";
import { ResearchPanel } from "./research-panel";
import { EvalPhasePanel } from "./eval-phase-panel";
import { ProposalSelector } from "./proposal-selector";
import { X, LayoutGrid } from "lucide-react";

export type ViewLayout = "single" | "split2" | "split3" | "grid4";

interface ContentPanelProps {
  projectId: string | null;
  projectLocale?: string | null;
  selectedBlock?: ContentBlock | null;
  allBlocks?: ContentBlock[];
  onFieldsChange?: () => void;
  /** 版本创建后通知父组件刷新项目列表 */
  onVersionCreated?: () => void;
  onBlockUpdated?: (block: ContentBlock) => void;
  onBlockSelect?: (block: ContentBlock) => void;
  /** M3: 将消息发送到 Agent 对话面板（Eval 诊断→Agent 修改桥接） */
  onSendToAgent?: (message: string) => void;
  /** B: 将选中文字+内容块引用发送到 Agent Panel 输入框上方 */
  onSendSelectionToAgent?: (ref: AgentSelectionRef) => void;
  /** 多视图布局模式 */
  viewLayout?: ViewLayout;
  /** 各槽位对应的内容块（最多4个） */
  slotBlocks?: (ContentBlock | null)[];
  /** 当前激活的槽位（侧边栏点击填入此槽） */
  activeSlotIndex?: number;
  /** 槽位聚焦回调 */
  onSlotFocus?: (index: number) => void;
  /** 关闭槽位回调 */
  onSlotClose?: (index: number) => void;
}

export function ContentPanel({
  projectId,
  projectLocale,
  selectedBlock,
  allBlocks = [],
  onFieldsChange,
  onVersionCreated,
  onBlockUpdated,
  onBlockSelect,
  onSendToAgent,
  onSendSelectionToAgent,
  viewLayout = "single",
  slotBlocks = [null, null, null, null],
  activeSlotIndex = 0,
  onSlotFocus,
  onSlotClose,
}: ContentPanelProps) {
  const uiLocale = useUiLocale(projectLocale);
  const t = projectUiText(uiLocale);
  const isJa = isJaProjectLocale(uiLocale);

  // ===== 多视图拖拽布局状态（各模式独立保持） =====
  const multiViewRef = useRef<HTMLDivElement>(null);
  // split2: 左栏宽度 %（右栏 flex-1 自动填满）
  const [split2LeftPct, setSplit2LeftPct] = useState(50);
  // split3: 前两栏宽度 %（第三栏 flex-1 自动填满）
  const [split3Pcts, setSplit3Pcts] = useState<[number, number]>([33.33, 33.33]);
  // grid4: 左列宽度 % + 上行高度 %（其余 flex-1 填满）
  const [grid4LeftPct, setGrid4LeftPct] = useState(50);
  const [grid4TopPct, setGrid4TopPct] = useState(50);

  // 列拖拽：传入 startPct（鼠标按下时的当前值）避免闭包旧值问题
  const startColDrag = useCallback((
    e: React.MouseEvent,
    startPct: number,
    setPct: (v: number) => void,
    minPct = 15,
    maxPct = 80,
  ) => {
    e.preventDefault();
    const container = multiViewRef.current;
    if (!container) return;
    const totalW = container.getBoundingClientRect().width;
    const startX = e.clientX;
    const onMove = (ev: MouseEvent) => {
      const dx = ev.clientX - startX;
      setPct(Math.min(maxPct, Math.max(minPct, startPct + (dx / totalW) * 100)));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, []);

  // 行拖拽（仅 grid4 使用）
  const startRowDrag = useCallback((e: React.MouseEvent, startPct: number) => {
    e.preventDefault();
    const container = multiViewRef.current;
    if (!container) return;
    const totalH = container.getBoundingClientRect().height;
    const startY = e.clientY;
    const onMove = (ev: MouseEvent) => {
      const dy = ev.clientY - startY;
      setGrid4TopPct(Math.min(80, Math.max(20, startPct + (dy / totalH) * 100)));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, []);

  // ===== 早期返回（在所有Hooks之后）=====

  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-500">
        <div className="text-center">
          <p className="text-lg mb-2">{t.chooseOrCreateProject}</p>
          <p className="text-sm">{t.chooseProjectHint}</p>
        </div>
      </div>
    );
  }

  // ===== 多视图模式（优先于单视图所有逻辑） =====
  if (viewLayout !== "single") {
    // 单个槽位渲染（复用于所有多视图布局）
    const renderSlot = (i: number, style: React.CSSProperties) => {
      const slotBlock = slotBlocks[i] ?? null;
      const isActive = activeSlotIndex === i;
      return (
        <div
          key={i}
          style={style}
          className={`relative overflow-hidden flex flex-col min-w-0 min-h-0 ${isActive ? "ring-2 ring-inset ring-brand-500/40" : ""}`}
          onClick={() => { if (!isActive) onSlotFocus?.(i); }}
        >
          {slotBlock ? (
            <>
              <div className="flex-1 overflow-y-auto min-h-0">
                <ContentBlockEditor
                  key={slotBlock.id}
                  block={slotBlock}
                  compact={true}
                  projectId={projectId}
                  projectLocale={projectLocale}
                  allBlocks={allBlocks}
                  onUpdate={onFieldsChange}
                  onVersionCreated={onVersionCreated}
                  onBlockUpdated={onBlockUpdated}
                  onSendToAgent={onSendToAgent}
                  onSendSelectionToAgent={onSendSelectionToAgent}
                />
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); onSlotClose?.(i); }}
                className="absolute top-2 right-8 z-20 w-5 h-5 flex items-center justify-center rounded bg-surface-2/80 text-zinc-500 hover:text-red-400 hover:bg-surface-3 transition-colors"
                title={isJa ? "このペインを閉じる" : "关闭此窗格"}
              >
                <X className="w-3 h-3" />
              </button>
            </>
          ) : (
            <div
              className="flex-1 flex flex-col items-center justify-center gap-3 text-zinc-600 cursor-pointer hover:text-zinc-400 transition-colors select-none"
              onClick={() => onSlotFocus?.(i)}
            >
              <LayoutGrid className="w-8 h-8" />
              <p className="text-sm text-center px-6">
                {isJa ? "左のツリーから内容ブロックを選択してください" : "从左侧目录点击内容块以添加到此窗格"}
              </p>
            </div>
          )}
        </div>
      );
    };

    // 列分隔拖拽条
    const ColHandle = ({ startPct, setPct, minPct = 15, maxPct = 85 }: {
      startPct: number;
      setPct: (v: number) => void;
      minPct?: number;
      maxPct?: number;
    }) => (
      <div
        className="w-1 flex-shrink-0 bg-surface-3 hover:bg-brand-500/60 cursor-col-resize transition-colors select-none"
        onMouseDown={(e) => startColDrag(e, startPct, setPct, minPct, maxPct)}
      />
    );

    // 行分隔拖拽条（grid4 专用）
    const RowHandle = ({ startPct }: { startPct: number }) => (
      <div
        className="h-1 flex-shrink-0 bg-surface-3 hover:bg-brand-500/60 cursor-row-resize transition-colors select-none"
        onMouseDown={(e) => startRowDrag(e, startPct)}
      />
    );

    if (viewLayout === "split2") {
      return (
        <div ref={multiViewRef} className="h-full flex flex-row overflow-hidden">
          {renderSlot(0, { width: `${split2LeftPct}%`, flexShrink: 0 })}
          <ColHandle startPct={split2LeftPct} setPct={setSplit2LeftPct} />
          {renderSlot(1, { flex: 1 })}
        </div>
      );
    }

    if (viewLayout === "split3") {
      return (
        <div ref={multiViewRef} className="h-full flex flex-row overflow-hidden">
          {renderSlot(0, { width: `${split3Pcts[0]}%`, flexShrink: 0 })}
          <ColHandle
            startPct={split3Pcts[0]}
            setPct={(v) => setSplit3Pcts([v, split3Pcts[1]])}
            maxPct={100 - split3Pcts[1] - 15}
          />
          {renderSlot(1, { width: `${split3Pcts[1]}%`, flexShrink: 0 })}
          <ColHandle
            startPct={split3Pcts[1]}
            setPct={(v) => setSplit3Pcts([split3Pcts[0], v])}
            minPct={15}
            maxPct={100 - split3Pcts[0] - 15}
          />
          {renderSlot(2, { flex: 1 })}
        </div>
      );
    }

    // grid4
    return (
      <div ref={multiViewRef} className="h-full flex flex-row overflow-hidden">
        {/* 左列 */}
        <div style={{ width: `${grid4LeftPct}%`, flexShrink: 0 }} className="flex flex-col min-h-0">
          {renderSlot(0, { flex: 1 })}
          <RowHandle startPct={grid4TopPct} />
          {renderSlot(2, { flex: 1 })}
        </div>
        <ColHandle startPct={grid4LeftPct} setPct={setGrid4LeftPct} />
        {/* 右列 */}
        <div style={{ flex: 1 }} className="flex flex-col min-h-0">
          {renderSlot(1, { flex: 1 })}
          <RowHandle startPct={grid4TopPct} />
          {renderSlot(3, { flex: 1 })}
        </div>
      </div>
    );
  }

  // ===== 树形视图选中内容块时，显示该块详情 =====
  
  // 处理分组块点击
  if (selectedBlock && selectedBlock.block_type === "group") {
    const selectedPhase = selectedBlock.special_handler;
    
    // ===== 意图分析阶段特殊处理 =====
    if (selectedPhase === "intent") {
      const intentContent = selectedBlock.content?.trim();
      if (intentContent) {
        return (
          <ContentBlockEditor
            key={selectedBlock.id}
            block={selectedBlock}
            projectId={projectId}
            projectLocale={projectLocale}
            allBlocks={allBlocks}
            onUpdate={onFieldsChange}
            onVersionCreated={onVersionCreated}
            onBlockUpdated={onBlockUpdated}
            onSendToAgent={onSendToAgent}
            onSendSelectionToAgent={onSendSelectionToAgent}
          />
        );
      } else {
        return (
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="text-6xl mb-4">💬</div>
            <h2 className="text-xl font-bold text-zinc-200 mb-2">{t.intentAnalysis}</h2>
            <p className="text-zinc-400 max-w-md">
              {t.intentEmptyHint}
            </p>
            <p className="text-zinc-500 text-sm mt-4">
              {t.intentEmptySubHint}
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
              projectLocale={projectLocale}
              fieldId={selectedBlock.id}
              content={normalizedContent}
              onUpdate={onFieldsChange}
              onAdvance={onFieldsChange}
            />
          );
        }
        return (
          <ContentBlockEditor
            key={selectedBlock.id}
            block={selectedBlock}
            projectId={projectId}
            projectLocale={projectLocale}
            allBlocks={allBlocks}
            onUpdate={onFieldsChange}
            onVersionCreated={onVersionCreated}
            onBlockUpdated={onBlockUpdated}
            onSendToAgent={onSendToAgent}
            onSendSelectionToAgent={onSendSelectionToAgent}
          />
        );
      } else {
        return (
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="text-6xl mb-4">🔍</div>
            <h2 className="text-xl font-bold text-zinc-200 mb-2">{t.research}</h2>
            <p className="text-zinc-400 max-w-md">
              {t.researchEmptyHint}
            </p>
            <p className="text-zinc-500 text-sm mt-4">
              {t.researchEmptySubHint}
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
          projectLocale={projectLocale}
          onFieldsChange={onFieldsChange}
          onSendToAgent={onSendToAgent}
        />
      );
    }
    
    // 有子节点的分组：显示子块卡片列表
    if (selectedBlock.children && selectedBlock.children.length > 0) {
      const groupCount = selectedBlock.children.filter(c => c.block_type === "group").length;
      const fieldCount = selectedBlock.children.filter(c => c.block_type === "field").length;
      const otherCount = selectedBlock.children.length - groupCount - fieldCount;
      
      const parts = [];
      if (groupCount > 0) parts.push(formatProjectText(t.childGroups, { count: groupCount }));
      if (fieldCount > 0) parts.push(formatProjectText(t.childBlocks, { count: fieldCount }));
      if (otherCount > 0) parts.push(formatProjectText(t.childOthers, { count: otherCount }));
      const description = parts.join(" / ") || t.noContent;
      
      return (
        <div className="h-full flex flex-col">
          <div className="p-4 border-b border-surface-3">
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 text-xs rounded bg-amber-600/20 text-amber-400">{t.groupTag}</span>
              <h1 className="text-xl font-bold text-zinc-100">{selectedBlock.name}</h1>
            </div>
            <p className="text-zinc-500 text-sm mt-1">
              {formatProjectText(t.includes, { description })}
            </p>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <div className="space-y-3">
              {selectedBlock.children.map((child) => (
                <ContentBlockCard
                  key={child.id}
                  block={child}
                  projectId={projectId || ""}
                  projectLocale={projectLocale}
                  allBlocks={allBlocks}
                  onUpdate={onFieldsChange}
                  onBlockUpdated={onBlockUpdated}
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
        <p className="text-sm">{t.emptyGroupHint}</p>
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
          projectLocale={projectLocale}
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
              projectLocale={projectLocale}
            fieldId={selectedBlock.id}
            content={normalizedContent}
            onUpdate={onFieldsChange}
            onAdvance={onFieldsChange}
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
              <h1 className="text-xl font-bold text-zinc-100">{isJa ? "内包設計" : "内涵设计"}</h1>
              <p className="text-zinc-500 text-sm mt-1">
                {isJa ? "案を 1 つ選択し、確認後に内包制作段階へ進みます" : "选择一个方案，确认后将进入内涵生产阶段"}
              </p>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <ProposalSelector
                projectId={projectId}
                projectLocale={projectLocale}
                fieldId={selectedBlock.id}
                content={selectedBlock.content}
                onConfirm={() => {
                  onFieldsChange?.();
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
              <h1 className="text-xl font-bold text-zinc-100">{isJa ? "外延設計" : "外延设计"}</h1>
              <p className="text-zinc-500 text-sm mt-1">
                {isJa ? "利用する配信チャネルを選択し、確認後に外延制作へ進みます" : "选择要使用的传播渠道，确认后进入外延生产"}
              </p>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <ChannelSelector
                projectId={projectId}
                projectLocale={projectLocale}
                fieldId={selectedBlock.id}
                content={selectedBlock.content}
                onConfirm={() => {
                  onFieldsChange?.();
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
            <h2 className="text-xl font-bold text-zinc-200 mb-2">{isJa ? "意図分析" : "意图分析"}</h2>
            <p className="text-zinc-400 max-w-md">
              {isJa ? "意図分析は AI Agent との対話で完了します。右側の対話欄で「開始」と入力してフローを始めてください。" : "意图分析由 AI Agent 通过对话完成。请在右侧对话框中输入\"开始\"来启动意图分析流程。"}
            </p>
            <p className="text-zinc-500 text-sm mt-4">
              {isJa ? "Agent が 3 つの質問でプロジェクト意図を整理します。" : "Agent 会问你 3 个问题来了解你的项目意图。"}
            </p>
          </div>
        );
      }
    }
    
    // 默认：使用 ContentBlockEditor
    return (
      <ContentBlockEditor
        key={selectedBlock.id}
        block={selectedBlock}
        projectId={projectId}
        projectLocale={projectLocale}
        allBlocks={allBlocks}
        onUpdate={onFieldsChange}
        onVersionCreated={onVersionCreated}
        onBlockUpdated={onBlockUpdated}
        onSendToAgent={onSendToAgent}
        onSendSelectionToAgent={onSendSelectionToAgent}
      />
    );
  }
  
  // 没有选中块时提示用户
  if (!selectedBlock) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center">
        <div className="text-6xl mb-4">🌲</div>
        <h2 className="text-xl font-bold text-zinc-200 mb-2">{isJa ? "ツリー構造モード" : "树形架构模式"}</h2>
        <p className="text-zinc-400 max-w-md">
          {isJa ? "左側のツリー構造からグループまたはフィールドを選択して、内容を確認・編集してください。" : "请在左侧树形结构中选择一个组或字段来查看和编辑内容。"}
        </p>
      </div>
    );
  }

  // 兜底：未知块类型也用 ContentBlockEditor
  return (
    <ContentBlockEditor
      key={selectedBlock.id}
      block={selectedBlock}
      projectId={projectId}
      projectLocale={projectLocale}
      allBlocks={allBlocks}
      onUpdate={onFieldsChange}
      onVersionCreated={onVersionCreated}
      onBlockUpdated={onBlockUpdated}
      onSendToAgent={onSendToAgent}
      onSendSelectionToAgent={onSendSelectionToAgent}
    />
  );
}
