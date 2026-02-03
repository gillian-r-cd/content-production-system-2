// frontend/app/page.tsx
// 功能: 首页，重定向到内容生产界面

import { redirect } from "next/navigation";

export default function Home() {
  // TODO: 实现项目选择页面
  // 暂时显示欢迎信息
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-brand-400 to-brand-600 bg-clip-text text-transparent">
          内容生产系统
        </h1>
        <p className="text-zinc-400 mb-8">
          AI Agent 驱动的商业内容生产平台
        </p>
        <div className="flex gap-4 justify-center">
          <a
            href="/workspace"
            className="px-6 py-3 bg-brand-600 hover:bg-brand-700 rounded-lg font-medium transition-colors"
          >
            进入工作台
          </a>
          <a
            href="/settings"
            className="px-6 py-3 bg-surface-3 hover:bg-surface-4 rounded-lg font-medium transition-colors"
          >
            后台设置
          </a>
        </div>
      </div>
    </main>
  );
}

