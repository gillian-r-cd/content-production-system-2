// frontend/lib/hooks/useBlockGeneration.ts
// 功能: ContentBlock 内容生成的共享逻辑（流式 SSE + 依赖检查 + 停止 + 自动触发链）
// 主要导出: useBlockGeneration() 自定义 Hook
// P0-1: 统一使用 blockAPI，已移除 fieldAPI 分支
// 设计原则: 消除 ContentBlockEditor 和 ContentBlockCard 中 ~80 行完全重复的生成逻辑

"use client";

import { useState, useRef, useMemo, useCallback } from "react";
import { blockAPI, runAutoTriggerChain } from "@/lib/api";
import { readSSEStream } from "@/lib/sse";
import { sendNotification } from "@/lib/utils";
import type { ContentBlock } from "@/lib/api";

interface UseBlockGenerationOptions {
  block: ContentBlock;
  projectId: string;
  allBlocks: ContentBlock[];
  /** 预提问答案（生成前先保存） */
  preAnswers?: Record<string, string>;
  /** 是否有预提问 */
  hasPreQuestions?: boolean;
  /** 保存预提问答案的回调（生成前调用） */
  onSavePreAnswers?: () => Promise<void>;
  /** 生成完成/数据变化时的刷新回调 */
  onUpdate?: () => void;
  /** 最终内容就绪时的回调（用于更新 editedContent） */
  onContentReady?: (content: string) => void;
}

interface UseBlockGenerationReturn {
  isGenerating: boolean;
  generatingContent: string;
  canGenerate: boolean;
  unmetDependencies: ContentBlock[];
  /** 触发生成（调用者自行处理 e.stopPropagation 等 UI 层逻辑） */
  handleGenerate: () => Promise<void>;
  /** 停止生成 */
  handleStop: () => void;
}

export function useBlockGeneration({
  block,
  projectId,
  allBlocks,
  preAnswers,
  hasPreQuestions,
  onSavePreAnswers,
  onUpdate,
  onContentReady,
}: UseBlockGenerationOptions): UseBlockGenerationReturn {
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatingContent, setGeneratingContent] = useState("");
  const abortControllerRef = useRef<AbortController | null>(null);
  // 追踪当前正在生成的 blockId，防止 Editor 切换块后状态错乱
  const generatingBlockIdRef = useRef<string | null>(null);

  // ---- 依赖检查 ----
  const dependsOn = block.depends_on || [];
  const dependencyBlocks = useMemo(
    () => dependsOn.map((id) => allBlocks.find((b) => b.id === id)).filter(Boolean) as ContentBlock[],
    [dependsOn, allBlocks],
  );

  const unmetDependencies = useMemo(
    () => dependencyBlocks.filter((d) => !d.content || !d.content.trim() || d.status !== "completed"),
    [dependencyBlocks],
  );

  const canGenerate = unmetDependencies.length === 0;

  // ---- 生成 ----
  const handleGenerate = useCallback(async () => {
    if (!canGenerate) {
      alert(`以下依赖内容为空:\n${unmetDependencies.map((d) => `• ${d.name}`).join("\n")}`);
      return;
    }

    // 保存预提问答案
    if (hasPreQuestions && preAnswers && Object.keys(preAnswers).length > 0) {
      if (onSavePreAnswers) {
        await onSavePreAnswers();
      } else {
        await blockAPI.update(block.id, { pre_answers: preAnswers });
      }
    }

    const currentBlockId = block.id;
    generatingBlockIdRef.current = currentBlockId;
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    setIsGenerating(true);
    setGeneratingContent("");

    try {
      // P0-1: 统一使用 blockAPI 流式生成
      const response = await blockAPI.generateStream(block.id, abortController.signal);
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "生成失败" }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }

      let accumulatedContent = "";

      for await (const data of readSSEStream(response)) {
        if (data.chunk) {
          accumulatedContent += data.chunk as string;
          if (generatingBlockIdRef.current === currentBlockId) {
            setGeneratingContent(accumulatedContent);
          }
        }
        if (data.done) {
          const finalContent = (data.content as string) || accumulatedContent;
          if (generatingBlockIdRef.current === currentBlockId) {
            onContentReady?.(finalContent);
          }
          onUpdate?.();
          sendNotification("内容生成完成", `「${block.name}」已生成完毕，点击查看`);
          if (projectId) {
            runAutoTriggerChain(projectId, () => onUpdate?.()).catch(console.error);
          }
        }
        if (data.error) {
          throw new Error(data.error as string);
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // 用户主动停止，保留已生成的部分内容
        onUpdate?.();
      } else {
        console.error("生成失败:", err);
        if (generatingBlockIdRef.current === currentBlockId) {
          alert("生成失败: " + (err instanceof Error ? err.message : "未知错误"));
        }
      }
    } finally {
      if (generatingBlockIdRef.current === currentBlockId) {
        setIsGenerating(false);
        setGeneratingContent("");
        generatingBlockIdRef.current = null;
        abortControllerRef.current = null;
      }
    }
  }, [
    block.id, block.name, projectId, canGenerate, unmetDependencies,
    preAnswers, hasPreQuestions,
    onSavePreAnswers, onUpdate, onContentReady,
  ]);

  // ---- 停止 ----
  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  // 只有当前 block 正在生成时才报告 isGenerating=true
  // 这样在 Editor 切换 block 时，新 block 不会误显生成中状态
  const isGeneratingThisBlock = isGenerating && generatingBlockIdRef.current === block.id;

  return {
    isGenerating: isGeneratingThisBlock,
    generatingContent: isGeneratingThisBlock ? generatingContent : "",
    canGenerate,
    unmetDependencies,
    handleGenerate,
    handleStop,
  };
}

