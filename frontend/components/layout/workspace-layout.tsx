// frontend/components/layout/workspace-layout.tsx
// 功能: 工作台三栏布局
// 主要组件: WorkspaceLayout

"use client";

import { ReactNode } from "react";

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
  return (
    <div className="flex h-screen bg-surface-0">
      {/* 左栏：项目进度 */}
      <aside className="w-64 flex-shrink-0 border-r border-surface-3 bg-surface-1 overflow-y-auto">
        {leftPanel}
      </aside>

      {/* 中栏：内容展示区 */}
      <main className="flex-1 overflow-y-auto bg-surface-0">
        {centerPanel}
      </main>

      {/* 右栏：AI Agent */}
      <aside className="w-96 flex-shrink-0 border-l border-surface-3 bg-surface-1 flex flex-col">
        {rightPanel}
      </aside>
    </div>
  );
}


