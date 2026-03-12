// frontend/components/settings/logs-section.tsx
// 功能: 调试日志查看和导出
// 主要组件: LogsSection, LogDetailModal, MessageBlock
// 数据结构:
//   prompt_input: JSON 数组 [{role, content, tool_calls?, tool_call_id?, name?}]
//   prompt_output: 纯文本（可能含 [tool_calls] 后缀）

"use client";

import { useState, useMemo, useCallback } from "react";
import { settingsAPI } from "@/lib/api";
import { useSettingsUiIsJa } from "./shared";

// ---- 角色配色与标签 ----
function getRoleConfig(isJa: boolean): Record<string, { label: string; color: string; bg: string }> {
  return {
    system: { label: isJa ? "システムプロンプト" : "System Prompt", color: "text-violet-300", bg: "bg-violet-500/10 border-violet-500/30" },
    human: { label: isJa ? "ユーザーメッセージ" : "用户消息", color: "text-green-300", bg: "bg-green-500/10 border-green-500/30" },
    ai: { label: isJa ? "AI 応答" : "AI 回复", color: "text-amber-300", bg: "bg-amber-500/10 border-amber-500/30" },
    tool: { label: isJa ? "ツール結果" : "工具结果", color: "text-cyan-300", bg: "bg-cyan-500/10 border-cyan-500/30" },
    unknown: { label: isJa ? "不明" : "未知", color: "text-zinc-400", bg: "bg-zinc-500/10 border-zinc-500/30" },
  };
}

interface LogToolCall {
  name?: string;
  [key: string]: unknown;
}

interface PromptMessage {
  role?: string;
  content?: unknown;
  name?: string;
  tool_calls?: LogToolCall[];
}

interface LogItem {
  id: string;
  phase?: string;
  operation?: string;
  model?: string;
  prompt_input?: string;
  prompt_output?: string;
  tokens_in?: number;
  tokens_out?: number;
  duration_ms?: number;
  cost?: number;
  error_message?: string;
  created_at?: string;
}

// ---- 单条 Message 展示块 ----
function MessageBlock({ msg, index, defaultOpen, isJa }: { msg: PromptMessage; index: number; defaultOpen: boolean; isJa: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const role = msg.role || "unknown";
  const roleConfig = getRoleConfig(isJa);
  const config = roleConfig[role] || roleConfig.unknown;
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
              🔧 {msg.tool_calls.map((tc) => String(tc.name || "")).join(", ")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-600">{charCount.toLocaleString()} {isJa ? "文字" : "字符"}</span>
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
function parsePromptInput(raw: string, isJa: boolean): { parsed: PromptMessage[] | null; rawText: string } {
  if (!raw) return { parsed: null, rawText: isJa ? "なし" : "无" };
  try {
    const arr: unknown = JSON.parse(raw);
    if (Array.isArray(arr) && arr.length > 0 && typeof (arr[0] as PromptMessage)?.role === "string") {
      return { parsed: arr as PromptMessage[], rawText: raw };
    }
  } catch {
    // 旧格式或解析失败 — 显示原始文本
  }
  return { parsed: null, rawText: raw };
}

// ---- 日志详情弹窗 ----
function LogDetailModal({ log, onClose, isJa }: { log: LogItem; onClose: () => void; isJa: boolean }) {
  const { parsed: messages, rawText } = useMemo(() => parsePromptInput(log.prompt_input || "", isJa), [isJa, log.prompt_input]);
  const [showRawInput, setShowRawInput] = useState(false);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-surface-1 border border-surface-3 rounded-xl overflow-hidden">
        {/* 头部 */}
        <div className="flex-shrink-0 flex justify-between items-center px-6 py-4 border-b border-surface-3">
          <div>
            <h3 className="text-lg font-medium text-zinc-100">{isJa ? "ログ詳細" : "日志详情"}</h3>
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
                {isJa ? "入力 (Messages) — LLM が実際に受け取った全情報" : "输入 (Messages) — 大模型实际收到的全部信息"}
              </h4>
              {messages && (
                <button
                  onClick={() => setShowRawInput(!showRawInput)}
                  className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
                >
                  {showRawInput ? (isJa ? "構造表示" : "分层展示") : (isJa ? "生 JSON" : "原始 JSON")}
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
                {messages.map((msg, idx: number) => (
                  <MessageBlock
                    key={idx}
                    msg={msg}
                    index={idx}
                    defaultOpen={msg.role === "human" || messages.length <= 3}
                    isJa={isJa}
                  />
                ))}
              </div>
            )}
          </div>

          {/* 输出 (Response) */}
          <div>
            <h4 className="text-sm font-medium text-zinc-400 mb-3">{isJa ? "出力 (Response)" : "输出 (Response)"}</h4>
            <pre className="p-4 bg-surface-2 rounded-lg text-sm text-zinc-300 whitespace-pre-wrap overflow-auto max-h-[60vh] leading-relaxed">
              {log.prompt_output || (isJa ? "なし" : "无")}
            </pre>
          </div>

          {/* 错误信息（如果有） */}
          {log.error_message && (
            <div>
              <h4 className="text-sm font-medium text-red-400 mb-3">{isJa ? "エラー情報" : "错误信息"}</h4>
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

// ---- 下载工具函数 ----

/** 将单条日志格式化为可读 JSON 对象 */
function formatLogForDownload(log: LogItem) {
  // 尝试解析 prompt_input 为结构化数据
  let parsedInput: unknown = log.prompt_input;
  if (log.prompt_input) {
    try {
      parsedInput = JSON.parse(log.prompt_input);
    } catch {
      // 保持原始字符串
    }
  }

  return {
    id: log.id,
    created_at: log.created_at,
    phase: log.phase,
    operation: log.operation,
    model: log.model,
    tokens_in: log.tokens_in || 0,
    tokens_out: log.tokens_out || 0,
    total_tokens: (log.tokens_in || 0) + (log.tokens_out || 0),
    duration_ms: log.duration_ms || 0,
    cost: log.cost || 0,
    status: log.error_message ? "failed" : "success",
    error_message: log.error_message || null,
    prompt_input: parsedInput,
    prompt_output: log.prompt_output || null,
  };
}

/** 触发浏览器下载 JSON 文件 */
function downloadJSON(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---- 主组件 ----
export function LogsSection({ logs, onRefresh }: { logs: LogItem[]; onRefresh?: () => void }) {
  const isJa = useSettingsUiIsJa();
  const [selectedLog, setSelectedLog] = useState<LogItem | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // 全选/反选
  const allSelected = logs.length > 0 && selectedIds.size === logs.length;
  const someSelected = selectedIds.size > 0 && selectedIds.size < logs.length;

  const toggleSelectAll = useCallback(() => {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(logs.map((l) => l.id)));
    }
  }, [allSelected, logs]);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await onRefresh?.();
    setSelectedIds(new Set()); // 刷新后清除选中
    setIsRefreshing(false);
  };

  const handleExport = useCallback(async (format: "json" | "csv") => {
    try {
      const data = await settingsAPI.exportLogs();
      if (format === "json") {
        downloadJSON(data, `logs_${new Date().toISOString().split("T")[0]}.json`);
      }
    } catch {
      alert(isJa ? "エクスポートに失敗しました" : "导出失败");
    }
  }, [isJa]);

  // 单项下载
  const handleDownloadSingle = useCallback((log: LogItem) => {
    const data = formatLogForDownload(log);
    const ts = (log.created_at || "").replace(/[:.]/g, "-").slice(0, 19);
    const op = log.operation || "log";
    downloadJSON(data, `log_${op}_${ts}.json`);
  }, []);

  // 批量下载选中项
  const handleDownloadSelected = useCallback(() => {
    if (selectedIds.size === 0) return;
    const selectedLogs = logs.filter((l) => selectedIds.has(l.id));
    const data = {
      exported_at: new Date().toISOString(),
      count: selectedLogs.length,
      total_cost: selectedLogs.reduce((sum, l) => sum + (l.cost || 0), 0),
      total_tokens: selectedLogs.reduce((sum, l) => sum + (l.tokens_in || 0) + (l.tokens_out || 0), 0),
      logs: selectedLogs.map(formatLogForDownload),
    };
    downloadJSON(data, `logs_batch_${selectedLogs.length}${isJa ? "items" : "条"}_${new Date().toISOString().split("T")[0]}.json`);
  }, [isJa, logs, selectedIds]);

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">{isJa ? "デバッグログ" : "调试日志"}</h2>
          <p className="text-sm text-zinc-500 mt-1">{isJa ? "各 AI 呼び出しの詳細情報を確認できます" : "查看每次 AI 调用的详细信息"}</p>
        </div>
        <div className="flex gap-2 items-center">
          {/* 批量下载按钮 — 仅选中时显示 */}
          {selectedIds.size > 0 && (
            <button
              onClick={handleDownloadSelected}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-white transition-colors text-sm"
            >
              {isJa ? `⬇ 選択項目をダウンロード (${selectedIds.size})` : `⬇ 下载选中 (${selectedIds.size})`}
            </button>
          )}
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:bg-zinc-600 rounded-lg text-white transition-colors"
          >
            {isRefreshing ? (isJa ? "⏳ 更新中..." : "⏳ 刷新中...") : (isJa ? "🔄 更新" : "🔄 刷新")}
          </button>
          <button onClick={() => handleExport("json")} className="px-4 py-2 bg-surface-3 hover:bg-surface-4 rounded-lg">
            {isJa ? "JSON をエクスポート" : "导出 JSON"}
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-3">
              <th className="py-3 px-2 w-8">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(el) => { if (el) el.indeterminate = someSelected; }}
                  onChange={toggleSelectAll}
                  className="rounded border-zinc-600 bg-surface-2 text-brand-500 focus:ring-brand-500 cursor-pointer"
                />
              </th>
              <th className="text-left py-3 px-3 text-zinc-500">{isJa ? "時間" : "时间"}</th>
              <th className="text-left py-3 px-3 text-zinc-500">{isJa ? "段階" : "组"}</th>
              <th className="text-left py-3 px-3 text-zinc-500">{isJa ? "操作" : "操作"}</th>
              <th className="text-left py-3 px-3 text-zinc-500">{isJa ? "モデル" : "模型"}</th>
              <th className="text-right py-3 px-3 text-zinc-500">Tokens</th>
              <th className="text-right py-3 px-3 text-zinc-500">{isJa ? "所要時間" : "耗时"}</th>
              <th className="text-right py-3 px-3 text-zinc-500">{isJa ? "コスト" : "成本"}</th>
              <th className="py-3 px-3"></th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-12 text-center text-zinc-500">{isJa ? "ログ記録はまだありません" : "暂无日志记录"}</td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id} className={`border-b border-surface-3/50 hover:bg-surface-2 ${selectedIds.has(log.id) ? "bg-brand-600/5" : ""}`}>
                  <td className="py-3 px-2">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(log.id)}
                      onChange={() => toggleSelect(log.id)}
                      className="rounded border-zinc-600 bg-surface-2 text-brand-500 focus:ring-brand-500 cursor-pointer"
                    />
                  </td>
                  <td className="py-3 px-3 text-zinc-400">{log.created_at?.slice(0, 19)}</td>
                  <td className="py-3 px-3 text-zinc-300">{log.phase}</td>
                  <td className="py-3 px-3 text-zinc-300">{log.operation}</td>
                  <td className="py-3 px-3 text-zinc-400 text-xs">{log.model}</td>
                  <td className="py-3 px-3 text-right text-zinc-400">{(log.tokens_in || 0) + (log.tokens_out || 0)}</td>
                  <td className="py-3 px-3 text-right text-zinc-400">{log.duration_ms}ms</td>
                  <td className="py-3 px-3 text-right text-green-400">${(log.cost || 0).toFixed(4)}</td>
                  <td className="py-3 px-3 flex items-center gap-2">
                    <button
                      onClick={() => handleDownloadSingle(log)}
                      className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                      title={isJa ? "このログをダウンロード" : "下载此条日志"}
                    >
                      ⬇
                    </button>
                    <button onClick={() => setSelectedLog(log)} className="text-xs text-brand-400 hover:text-brand-300">
                      {isJa ? "詳細" : "详情"}
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
        <LogDetailModal log={selectedLog} onClose={() => setSelectedLog(null)} isJa={isJa} />
      )}
    </div>
  );
}
