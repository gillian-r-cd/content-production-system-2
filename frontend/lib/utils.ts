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

// ============== 阶段配置（前端镜像） ==============
// 单一真相来源 (SSOT): backend/core/phase_config.py
// 修改阶段定义时，需同步更新后端 PHASE_DEFINITIONS 和此处

/**
 * 阶段完整定义（与后端 PHASE_DEFINITIONS 保持一致）
 */
export interface PhaseDefinition {
  code: string;
  displayName: string;
  specialHandler: string | null;
  position: "top" | "middle" | "bottom";
}

export const PHASE_DEFINITIONS: PhaseDefinition[] = [
  { code: "intent",        displayName: "意图分析",   specialHandler: "intent",   position: "top" },
  { code: "research",      displayName: "消费者调研", specialHandler: "research",  position: "top" },
  { code: "design_inner",  displayName: "内涵设计",   specialHandler: null,        position: "middle" },
  { code: "produce_inner", displayName: "内涵生产",   specialHandler: null,        position: "middle" },
  { code: "design_outer",  displayName: "外延设计",   specialHandler: null,        position: "middle" },
  { code: "produce_outer", displayName: "外延生产",   specialHandler: null,        position: "middle" },
  { code: "evaluate",      displayName: "评估",       specialHandler: "evaluate",  position: "bottom" },
];

// ---- 派生常量（自动从 PHASE_DEFINITIONS 生成） ----

/** 默认阶段顺序 */
export const PROJECT_PHASES = PHASE_DEFINITIONS.map(p => p.code);

/** 代码 → 中文显示名 */
export const PHASE_NAMES: Record<string, string> = Object.fromEntries(
  PHASE_DEFINITIONS.map(p => [p.code, p.displayName])
);

/** 有特殊处理器的阶段 */
export const PHASE_SPECIAL_HANDLERS: Record<string, string> = Object.fromEntries(
  PHASE_DEFINITIONS.filter(p => p.specialHandler).map(p => [p.code, p.specialHandler!])
);

/** 各位置分组 */
export const FIXED_TOP_PHASES = PHASE_DEFINITIONS.filter(p => p.position === "top").map(p => p.code);
export const DRAGGABLE_PHASES = PHASE_DEFINITIONS.filter(p => p.position === "middle").map(p => p.code);
export const FIXED_BOTTOM_PHASES = PHASE_DEFINITIONS.filter(p => p.position === "bottom").map(p => p.code);

/**
 * 阶段状态映射
 */
export const PHASE_STATUS: Record<string, { label: string; color: string }> = {
  pending: { label: "未开始", color: "text-zinc-500" },
  in_progress: { label: "进行中", color: "text-yellow-500" },
  completed: { label: "已完成", color: "text-green-500" },
};


// ============== 浏览器通知 ==============

/**
 * 请求浏览器通知权限
 * 应在用户首次交互时调用（如页面加载后首次点击）
 */
export function requestNotificationPermission() {
  if (typeof window === "undefined") return;
  if (!("Notification" in window)) return;
  if (Notification.permission === "default") {
    Notification.requestPermission().then((perm) => {
      console.log(`[Notification] 用户选择: ${perm}`);
    });
  }
}

// ===== 应用内 Toast 通知队列 =====
let _toastContainer: HTMLDivElement | null = null;

function getToastContainer(): HTMLDivElement {
  if (_toastContainer && document.body.contains(_toastContainer)) return _toastContainer;
  _toastContainer = document.createElement("div");
  _toastContainer.id = "app-toast-container";
  _toastContainer.style.cssText = `
    position: fixed; top: 16px; right: 16px; z-index: 99999;
    display: flex; flex-direction: column; gap: 8px;
    pointer-events: none;
  `;
  document.body.appendChild(_toastContainer);
  return _toastContainer;
}

function showToast(title: string, body: string) {
  if (typeof window === "undefined") return;
  const container = getToastContainer();
  const toast = document.createElement("div");
  toast.style.cssText = `
    background: #1a1a2e; border: 1px solid #7c3aed; border-radius: 12px;
    padding: 12px 16px; max-width: 320px; color: #e4e4e7;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4); pointer-events: auto;
    animation: toast-slide-in 0.3s ease-out;
    font-family: system-ui, -apple-system, sans-serif;
  `;
  toast.innerHTML = `
    <div style="font-weight:600;font-size:13px;color:#a78bfa;margin-bottom:4px">${title}</div>
    <div style="font-size:12px;color:#a1a1aa">${body}</div>
  `;

  // CSS animation
  if (!document.getElementById("toast-animation-style")) {
    const style = document.createElement("style");
    style.id = "toast-animation-style";
    style.textContent = `
      @keyframes toast-slide-in { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
      @keyframes toast-fade-out { from { opacity: 1; } to { opacity: 0; transform: translateY(-10px); } }
    `;
    document.head.appendChild(style);
  }

  container.appendChild(toast);
  // 5 秒后淡出移除
  setTimeout(() => {
    toast.style.animation = "toast-fade-out 0.3s ease-in forwards";
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

/**
 * 发送通知（系统级 + 应用内 Toast）
 * 
 * - 不论页面是否在前台，都会发送
 * - 如果页面在后台且有浏览器权限 → 发送系统通知
 * - 同时始终在应用内显示 Toast 提示
 * 
 * @param title 通知标题
 * @param body 通知正文
 * @param onClick 点击通知后的回调（可选，默认聚焦窗口）
 */
export function sendNotification(title: string, body: string, onClick?: () => void) {
  if (typeof window === "undefined") return;

  // 1. 始终显示应用内 Toast（即使在前台也能看到）
  showToast(title, body);

  // 2. 如果页面不在前台，尝试发送系统级浏览器通知
  if (document.visibilityState !== "visible") {
    if (!("Notification" in window)) return;
    
    // 如果权限是 default，尝试请求（不一定成功）
    if (Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }
    
    if (Notification.permission === "granted") {
      try {
        const notification = new Notification(title, {
          body,
          icon: "/favicon.ico",
          tag: `gen-${Date.now()}`,
          silent: false,
        });
        
        notification.onclick = () => {
          window.focus();
          notification.close();
          onClick?.();
        };
        
        setTimeout(() => notification.close(), 10000);
      } catch (e) {
        console.warn("[Notification] 发送失败:", e);
      }
    }
  }
}
