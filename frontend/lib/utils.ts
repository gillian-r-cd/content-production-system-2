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

export type NotificationTone = "info" | "success" | "warning" | "error";

const NOTIFICATION_TONES: NotificationTone[] = ["info", "success", "warning", "error"];

function isNotificationTone(value: unknown): value is NotificationTone {
  return typeof value === "string" && NOTIFICATION_TONES.includes(value as NotificationTone);
}

export function resolveNotificationArgs(
  bodyOrTone?: string | NotificationTone,
  toneOrOnClick?: NotificationTone | (() => void),
  onClick?: () => void,
): { body: string; tone: NotificationTone; onClick?: () => void } {
  let body = "";
  let tone: NotificationTone = "info";
  let clickHandler = onClick;

  if (typeof toneOrOnClick === "function") {
    clickHandler = toneOrOnClick;
  } else if (isNotificationTone(toneOrOnClick)) {
    tone = toneOrOnClick;
  }

  if (isNotificationTone(bodyOrTone)) {
    tone = bodyOrTone;
  } else if (typeof bodyOrTone === "string") {
    body = bodyOrTone;
  }

  return { body, tone, onClick: clickHandler };
}

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

function showToast(title: string, body: string, tone: NotificationTone) {
  if (typeof window === "undefined") return;
  const container = getToastContainer();
  const toast = document.createElement("div");
  const toneStyle = {
    info: { border: "#7c3aed", title: "#a78bfa" },
    success: { border: "#16a34a", title: "#4ade80" },
    warning: { border: "#d97706", title: "#fbbf24" },
    error: { border: "#dc2626", title: "#f87171" },
  }[tone];
  toast.style.cssText = `
    background: #1a1a2e; border: 1px solid ${toneStyle.border}; border-radius: 12px;
    padding: 12px 16px; max-width: 320px; color: #e4e4e7;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4); pointer-events: auto;
    animation: toast-slide-in 0.3s ease-out;
    font-family: system-ui, -apple-system, sans-serif;
  `;
  const bodyHtml = body
    ? `<div style="font-size:12px;color:#a1a1aa">${body}</div>`
    : "";
  const titleMargin = body ? "4px" : "0";
  toast.innerHTML = `
    <div style="font-weight:600;font-size:13px;color:${toneStyle.title};margin-bottom:${titleMargin}">${title}</div>
    ${bodyHtml}
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
 * @param bodyOrTone 通知正文，或兼容旧调用方式的通知类型
 * @param toneOrOnClick 通知类型，或点击通知后的回调
 * @param onClick 点击通知后的回调（可选，默认聚焦窗口）
 */
export function sendNotification(
  title: string,
  bodyOrTone?: string | NotificationTone,
  toneOrOnClick?: NotificationTone | (() => void),
  onClick?: () => void,
) {
  if (typeof window === "undefined") return;
  const resolved = resolveNotificationArgs(bodyOrTone, toneOrOnClick, onClick);
  const body = resolved.body;

  // 1. 始终显示应用内 Toast（即使在前台也能看到）
  showToast(title, body, resolved.tone);

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
          body: body || title,
          icon: "/icon.svg",
          tag: `gen-${Date.now()}`,
          silent: false,
        });
        
        notification.onclick = () => {
          window.focus();
          notification.close();
          resolved.onClick?.();
        };
        
        setTimeout(() => notification.close(), 10000);
      } catch (e) {
        console.warn("[Notification] 发送失败:", e);
      }
    }
  }
}
