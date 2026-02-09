// frontend/components/layout/workspace-layout.tsx
// 功能: 工作台三栏布局，支持左右侧栏折叠/展开 + 拖拽调整宽度
// 主要组件: WorkspaceLayout
// 数据结构:
//   - leftWidth / rightWidth: 侧栏像素宽度（持久化到 localStorage）
//   - leftCollapsed / rightCollapsed: 折叠状态（持久化到 localStorage）

"use client";

import { ReactNode, useState, useRef, useCallback, useEffect } from "react";
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen } from "lucide-react";

// ── 常量 ──────────────────────────────────────────
const LS_KEY = "workspace-layout";

const LEFT_DEFAULT = 256;   // w-64
const LEFT_MIN = 180;
const LEFT_MAX = 420;

const RIGHT_DEFAULT = 384;  // w-96
const RIGHT_MIN = 280;
const RIGHT_MAX = 620;

const COLLAPSED_WIDTH = 0;  // 折叠后宽度

// ── 持久化 helpers ────────────────────────────────
interface LayoutState {
  lw: number;
  rw: number;
  lc: boolean;
  rc: boolean;
}

function loadState(): LayoutState {
  if (typeof window === "undefined") {
    return { lw: LEFT_DEFAULT, rw: RIGHT_DEFAULT, lc: false, rc: false };
  }
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { lw: LEFT_DEFAULT, rw: RIGHT_DEFAULT, lc: false, rc: false };
}

function saveState(s: LayoutState) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(s));
  } catch { /* ignore */ }
}

// ── 组件 ──────────────────────────────────────────
interface WorkspaceLayoutProps {
  leftPanel: ReactNode;
  centerPanel: ReactNode;
  rightPanel: ReactNode;
}

export function WorkspaceLayout({
  leftPanel,
  centerPanel,
  rightPanel,
}: WorkspaceLayoutProps) {
  // --- 状态 ---
  const [leftWidth, setLeftWidth] = useState(LEFT_DEFAULT);
  const [rightWidth, setRightWidth] = useState(RIGHT_DEFAULT);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  // 首次从 localStorage 恢复
  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    const s = loadState();
    setLeftWidth(s.lw);
    setRightWidth(s.rw);
    setLeftCollapsed(s.lc);
    setRightCollapsed(s.rc);
  }, []);

  // 持久化（debounced）
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!initialized.current) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      saveState({ lw: leftWidth, rw: rightWidth, lc: leftCollapsed, rc: rightCollapsed });
    }, 300);
  }, [leftWidth, rightWidth, leftCollapsed, rightCollapsed]);

  // --- 拖拽 ---
  const dragging = useRef<"left" | "right" | null>(null);
  const startX = useRef(0);
  const startW = useRef(0);

  const onMouseMove = useCallback((e: MouseEvent) => {
    if (!dragging.current) return;
    const delta = e.clientX - startX.current;
    if (dragging.current === "left") {
      const newW = Math.max(LEFT_MIN, Math.min(LEFT_MAX, startW.current + delta));
      setLeftWidth(newW);
    } else {
      // 右栏：鼠标往左 → 变宽
      const newW = Math.max(RIGHT_MIN, Math.min(RIGHT_MAX, startW.current - delta));
      setRightWidth(newW);
    }
  }, []);

  const onMouseUp = useCallback(() => {
    dragging.current = null;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
  }, [onMouseMove]);

  const startDrag = useCallback(
    (side: "left" | "right", e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = side;
      startX.current = e.clientX;
      startW.current = side === "left" ? leftWidth : rightWidth;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("mouseup", onMouseUp);
    },
    [leftWidth, rightWidth, onMouseMove, onMouseUp],
  );

  // --- 折叠切换 ---
  const toggleLeft = useCallback(() => setLeftCollapsed((c) => !c), []);
  const toggleRight = useCallback(() => setRightCollapsed((c) => !c), []);

  // 实际渲染宽度
  const lw = leftCollapsed ? COLLAPSED_WIDTH : leftWidth;
  const rw = rightCollapsed ? COLLAPSED_WIDTH : rightWidth;

  return (
    <div className="flex h-screen bg-surface-0 overflow-hidden">
      {/* ── 左栏 ── */}
      <aside
        className="flex-shrink-0 border-r border-surface-3 bg-surface-1 overflow-hidden transition-[width] duration-200 ease-in-out"
        style={{ width: lw }}
      >
        {!leftCollapsed && (
          <div className="h-full overflow-y-auto">{leftPanel}</div>
        )}
      </aside>

      {/* ── 左侧拖拽手柄 + 折叠按钮 ── */}
      <div className="relative flex-shrink-0 z-10">
        {/* 拖拽区域 */}
        {!leftCollapsed && (
          <div
            className="resize-handle"
            onMouseDown={(e) => startDrag("left", e)}
          />
        )}
        {/* 折叠/展开按钮 */}
        <button
          onClick={toggleLeft}
          className="collapse-btn collapse-btn-left"
          title={leftCollapsed ? "展开左栏" : "收起左栏"}
        >
          {leftCollapsed ? (
            <PanelLeftOpen className="w-3.5 h-3.5" />
          ) : (
            <PanelLeftClose className="w-3.5 h-3.5" />
          )}
        </button>
      </div>

      {/* ── 中栏 ── */}
      <main className="flex-1 overflow-y-auto bg-surface-0 min-w-0">
        {centerPanel}
      </main>

      {/* ── 右侧拖拽手柄 + 折叠按钮 ── */}
      <div className="relative flex-shrink-0 z-10">
        {!rightCollapsed && (
          <div
            className="resize-handle"
            onMouseDown={(e) => startDrag("right", e)}
          />
        )}
        <button
          onClick={toggleRight}
          className="collapse-btn collapse-btn-right"
          title={rightCollapsed ? "展开右栏" : "收起右栏"}
        >
          {rightCollapsed ? (
            <PanelRightOpen className="w-3.5 h-3.5" />
          ) : (
            <PanelRightClose className="w-3.5 h-3.5" />
          )}
        </button>
      </div>

      {/* ── 右栏 ── */}
      <aside
        className="flex-shrink-0 border-l border-surface-3 bg-surface-1 flex flex-col overflow-hidden transition-[width] duration-200 ease-in-out"
        style={{ width: rw }}
      >
        {!rightCollapsed && (
          <div className="h-full flex flex-col overflow-hidden">{rightPanel}</div>
        )}
      </aside>
    </div>
  );
}
