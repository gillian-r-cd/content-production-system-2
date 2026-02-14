// frontend/app/page.tsx
// 功能: 首页入口，提供工作台和后台设置的导航

export default function Home() {
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


