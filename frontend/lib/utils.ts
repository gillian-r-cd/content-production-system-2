// frontend/lib/utils.ts
// 功能: 通用工具函数
// 主要函数: cn, formatDate

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * 合并 Tailwind 类名
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * 格式化日期
 */
export function formatDate(dateString: string): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * 项目阶段顺序
 */
export const PROJECT_PHASES = [
  "intent",
  "research",
  "design_inner",
  "produce_inner",
  "design_outer",
  "produce_outer",
  "simulate",
  "evaluate",
];

/**
 * 阶段名称映射
 */
export const PHASE_NAMES: Record<string, string> = {
  intent: "意图分析",
  research: "消费者调研",
  design_inner: "内涵设计",
  produce_inner: "内涵生产",
  design_outer: "外延设计",
  produce_outer: "外延生产",
  simulate: "消费者模拟",
  evaluate: "评估",
};

/**
 * 阶段状态映射
 */
export const PHASE_STATUS: Record<string, { label: string; color: string }> = {
  pending: { label: "未开始", color: "text-zinc-500" },
  in_progress: { label: "进行中", color: "text-yellow-500" },
  completed: { label: "已完成", color: "text-green-500" },
};

