// frontend/components/settings/logs-section.tsx
// 功能: 调试日志查看和导出
// 主要组件: LogsSection, LogDetailModal, MessageBlock
// 数据结构:
//   prompt_input: JSON 数组 [{role, content, tool_calls?, tool_call_id?, name?}]
//   prompt_output: 纯文本（可能含 [tool_calls] 后缀）

"use client";

import { useState, useMemo } from "react";
import { settingsAPI } from "@/lib/api";

// ---- 角色配色与标签 ----
const ROLE_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  system: { label: "System Prompt", color: "text-violet-300", bg: "bg-violet-500/10 border-violet-500/30" },
  human: { label: "用户消息", color: "text-green-300", bg: "bg-green-500/10 border-green-500/30" },
  ai: { label: "AI 回复", color: "text-amber-300", bg: "bg-amber-500/10 border-amber-500/30" },
  tool: { label: "工具结果", color: "text-cyan-300", bg: "bg-cyan-500/10 border-cyan-500/30" },
  unknown: { label: "未知", color: "text-zinc-400", bg: "bg-zinc-500/10 border-zinc-500/30" },
};

// ---- 单条 Message 展示块 ----
function MessageBlock({ msg, index, defaultOpen }: { msg: any; index: number; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const role = msg.role || "unknown";
  const config = ROLE_CONFIG[role] || ROLE_CONFIG.unknown;
  const content = typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content, null, 2);
  const charCount = content.length;

  return (
    <div className={`border rounded-lg overflow-hidden ${config.bg}`}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2 text-left hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium ${config.color}`}>
            #{index + 1} {config.label}
          </span>
          {msg.name && (
            <span className="text-xs text-zinc-500">({msg.name})</span>
          )}
          {msg.tool_calls && msg.tool_calls.length > 0 && (
            <span className="text-xs text-cyan-400">
              🔧 {msg.tool_calls.map((tc: any) => tc.name).join(", ")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-600">{charCount.toLocaleString()} 字符</span>
          <span className="text-zinc-500 text-xs">{open ? "▼" : "▶"}</span>
        </div>
      </button>
      {open && (
        <div className="border-t border-white/10">
          <pre className="p-4 text-sm text-zinc-300 whitespace-pre-wrap overflow-auto max-h-[60vh] leading-relaxed">
            {content}
          </pre>
          {msg.tool_calls && msg.tool_calls.length > 0 && (
            <div className="px-4 pb-3 border-t border-white/10 pt-2">
              <p className="text-xs text-cyan-400 mb-1">Tool Calls:</p>
              <pre className="text-xs text-zinc-400 whitespace-pre-wrap">
                {JSON.stringify(msg.tool_calls, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---- 解析 prompt_input ----
function parsePromptInput(raw: string): { parsed: any[] | null; rawText: string } {
  if (!raw) return { parsed: null, rawText: "无" };
  try {
    const arr = JSON.parse(raw);
    if (Array.isArray(arr) && arr.length > 0 && arr[0].role) {
      return { parsed: arr, rawText: raw };
    }
  } catch {
    // 旧格式或解析失败 — 显示原始文本
  }
  return { parsed: null, rawText: raw };
}

// ---- 日志详情弹窗 ----
function LogDetailModal({ log, onClose }: { log: any; onClose: () => void }) {
  const { parsed: messages, rawText } = useMemo(() => parsePromptInput(log.prompt_input), [log.prompt_input]);
  const [showRawInput, setShowRawInput] = useState(false);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-surface-1 border border-surface-3 rounded-xl overflow-hidden">
        {/* 头部 */}
        <div className="flex-shrink-0 flex justify-between items-center px-6 py-4 border-b border-surface-3">
          <div>
            <h3 className="text-lg font-medium text-zinc-100">日志详情</h3>
            <div className="flex gap-4 mt-1 text-xs text-zinc-500">
              <span>{log.operation}</span>
              <span>{log.model}</span>
              <span>Tokens: {(log.tokens_in || 0) + (log.tokens_out || 0)}</span>
              <span>{log.duration_ms}ms</span>
              <span>${(log.cost || 0).toFixed(4)}</span>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-200 text-xl">✕</button>
        </div>

        {/* 内容区域（可滚动） */}
        <div className="flex-1 overflow-auto p-6 space-y-6">
          {/* 输入 (Messages) */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-zinc-400">
                输入 (Messages) — 大模型实际收到的全部信息
              </h4>
              {messages && (
                <button
                  onClick={() => setShowRawInput(!showRawInput)}
                  className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
                >
                  {showRawInput ? "分层展示" : "原始 JSON"}
                </button>
              )}
            </div>

            {showRawInput || !messages ? (
              // 原始文本视图
              <pre className="p-4 bg-surface-2 rounded-lg text-sm text-zinc-300 whitespace-pre-wrap overflow-auto max-h-[60vh] leading-relaxed">
                {messages ? JSON.stringify(messages, null, 2) : rawText}
              </pre>
            ) : (
              // 分层消息视图
              <div className="space-y-2">
                {messages.map((msg: any, idx: number) => (
                  <MessageBlock
                    key={idx}
                    msg={msg}
                    index={idx}
                    defaultOpen={msg.role === "human" || messages.length <= 3}
                  />
                ))}
              </div>
            )}
          </div>

          {/* 输出 (Response) */}
          <div>
            <h4 className="text-sm font-medium text-zinc-400 mb-3">输出 (Response)</h4>
            <pre className="p-4 bg-surface-2 rounded-lg text-sm text-zinc-300 whitespace-pre-wrap overflow-auto max-h-[60vh] leading-relaxed">
              {log.prompt_output || "无"}
            </pre>
          </div>

          {/* 错误信息（如果有） */}
          {log.error_message && (
            <div>
              <h4 className="text-sm font-medium text-red-400 mb-3">错误信息</h4>
              <pre className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-300 whitespace-pre-wrap overflow-auto">
                {log.error_message}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---- 主组件 ----
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
        <LogDetailModal log={selectedLog} onClose={() => setSelectedLog(null)} />
      )}
    </div>
  );
}
