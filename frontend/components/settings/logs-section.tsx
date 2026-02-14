// frontend/components/settings/logs-section.tsx
// 功能: 调试日志查看和导出

"use client";

import { useState } from "react";
import { settingsAPI } from "@/lib/api";

export function LogsSection({ logs, onRefresh }: { logs: any[]; onRefresh?: () => void }) {
  const [selectedLog, setSelectedLog] = useState<any>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await onRefresh?.();
    setIsRefreshing(false);
  };

  const handleExport = async (format: "json" | "csv") => {
    try {
      const data = await settingsAPI.exportLogs();
      if (format === "json") {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `logs_${new Date().toISOString().split("T")[0]}.json`;
        a.click();
      }
    } catch (err) {
      alert("导出失败");
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">调试日志</h2>
          <p className="text-sm text-zinc-500 mt-1">查看每次 AI 调用的详细信息</p>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={handleRefresh} 
            disabled={isRefreshing}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:bg-zinc-600 rounded-lg text-white transition-colors"
          >
            {isRefreshing ? "⏳ 刷新中..." : "🔄 刷新"}
          </button>
          <button onClick={() => handleExport("json")} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">
            导出 JSON
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-3">
              <th className="text-left py-3 px-3 text-zinc-500">时间</th>
              <th className="text-left py-3 px-3 text-zinc-500">组</th>
              <th className="text-left py-3 px-3 text-zinc-500">操作</th>
              <th className="text-left py-3 px-3 text-zinc-500">模型</th>
              <th className="text-right py-3 px-3 text-zinc-500">Tokens</th>
              <th className="text-right py-3 px-3 text-zinc-500">耗时</th>
              <th className="text-right py-3 px-3 text-zinc-500">成本</th>
              <th className="py-3 px-3"></th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-zinc-500">暂无日志记录</td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id} className="border-b border-surface-3/50 hover:bg-surface-2">
                  <td className="py-3 px-3 text-zinc-400">{log.created_at?.slice(0, 19)}</td>
                  <td className="py-3 px-3 text-zinc-300">{log.phase}</td>
                  <td className="py-3 px-3 text-zinc-300">{log.operation}</td>
                  <td className="py-3 px-3 text-zinc-400 text-xs">{log.model}</td>
                  <td className="py-3 px-3 text-right text-zinc-400">{(log.tokens_in || 0) + (log.tokens_out || 0)}</td>
                  <td className="py-3 px-3 text-right text-zinc-400">{log.duration_ms}ms</td>
                  <td className="py-3 px-3 text-right text-green-400">${(log.cost || 0).toFixed(4)}</td>
                  <td className="py-3 px-3">
                    <button onClick={() => setSelectedLog(log)} className="text-xs text-brand-400 hover:text-brand-300">
                      详情
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 日志详情弹窗 */}
      {selectedLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSelectedLog(null)} />
          <div className="relative w-full max-w-3xl max-h-[80vh] overflow-auto bg-surface-1 border border-surface-3 rounded-xl p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-medium text-zinc-100">日志详情</h3>
              <button onClick={() => setSelectedLog(null)} className="text-zinc-400 hover:text-zinc-200">✕</button>
            </div>
            <div className="space-y-4">
              <div>
                <h4 className="text-sm text-zinc-500 mb-2">输入 (Prompt)</h4>
                <pre className="p-4 bg-surface-2 rounded-lg text-sm text-zinc-300 whitespace-pre-wrap overflow-auto max-h-60">
                  {selectedLog.prompt_input || "无"}
                </pre>
              </div>
              <div>
                <h4 className="text-sm text-zinc-500 mb-2">输出 (Response)</h4>
                <pre className="p-4 bg-surface-2 rounded-lg text-sm text-zinc-300 whitespace-pre-wrap overflow-auto max-h-60">
                  {selectedLog.prompt_output || "无"}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
