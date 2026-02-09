// frontend/components/version-history.tsx
// 功能: 版本历史面板组件（支持查看历史版本和回滚）

"use client";

import { useState, useEffect } from "react";
import { versionAPI } from "@/lib/api";
import type { VersionItem } from "@/lib/api";
import { History, RotateCcw, X, ChevronDown, ChevronUp, Eye } from "lucide-react";

const SOURCE_LABELS: Record<string, string> = {
  user_edit: "手动编辑",
  ai_generate: "AI 生成",
  ai_regenerate: "AI 重新生成",
  ai_regenerate_stream: "AI 流式重新生成",
  ai_generate_stream_interrupted: "AI 生成(中断)",
  agent_modify: "Agent 修改",
  agent_produce: "Agent 生成",
  rollback_snapshot: "回滚前快照",
  manual: "手动保存",
};

interface VersionHistoryProps {
  entityId: string;
  entityName: string;
  onRollback?: () => void;  // 回滚成功后刷新
  onClose: () => void;
}

export function VersionHistoryPanel({ entityId, entityName, onRollback, onClose }: VersionHistoryProps) {
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedVersion, setExpandedVersion] = useState<string | null>(null);
  const [rollingBack, setRollingBack] = useState<string | null>(null);

  useEffect(() => {
    loadVersions();
  }, [entityId]);

  const loadVersions = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await versionAPI.list(entityId);
      setVersions(data.versions);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载版本历史失败");
    } finally {
      setLoading(false);
    }
  };

  const handleRollback = async (versionId: string, versionNumber: number) => {
    if (!confirm(`确定要回滚到版本 v${versionNumber} 吗？当前内容会被保存为新版本后覆盖。`)) return;
    
    setRollingBack(versionId);
    try {
      await versionAPI.rollback(entityId, versionId);
      onRollback?.();
      onClose();
    } catch (err) {
      alert("回滚失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setRollingBack(null);
    }
  };

  const formatTime = (iso: string) => {
    if (!iso) return "";
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    
    if (diff < 60000) return "刚刚";
    if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`;
    
    return d.toLocaleString("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-surface-2 border border-surface-3 rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-3">
          <div className="flex items-center gap-2">
            <History className="w-5 h-5 text-brand-400" />
            <h3 className="text-lg font-medium text-zinc-100">
              版本历史 - {entityName}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <span className="text-zinc-400 animate-pulse">加载版本历史...</span>
            </div>
          ) : error ? (
            <div className="text-center py-8 text-red-400">{error}</div>
          ) : versions.length === 0 ? (
            <div className="text-center py-12 text-zinc-500">
              暂无版本历史记录
            </div>
          ) : (
            <div className="space-y-2">
              {versions.map((v) => (
                <div
                  key={v.id}
                  className="border border-surface-3 rounded-lg overflow-hidden hover:border-surface-4 transition-colors"
                >
                  {/* Version header */}
                  <div className="flex items-center justify-between px-4 py-3 bg-surface-1">
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-mono font-medium text-brand-400">
                        v{v.version_number}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-surface-3 text-zinc-400">
                        {SOURCE_LABELS[v.source] || v.source}
                      </span>
                      <span className="text-xs text-zinc-500">
                        {formatTime(v.created_at)}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* Preview toggle */}
                      <button
                        onClick={() => setExpandedVersion(expandedVersion === v.id ? null : v.id)}
                        className="flex items-center gap-1 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded transition-colors"
                        title="预览内容"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        {expandedVersion === v.id ? (
                          <ChevronUp className="w-3 h-3" />
                        ) : (
                          <ChevronDown className="w-3 h-3" />
                        )}
                      </button>
                      {/* Rollback button */}
                      <button
                        onClick={() => handleRollback(v.id, v.version_number)}
                        disabled={rollingBack === v.id}
                        className="flex items-center gap-1 px-2.5 py-1 text-xs bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-500/30 rounded transition-colors disabled:opacity-50"
                        title={`回滚到版本 v${v.version_number}`}
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        {rollingBack === v.id ? "回滚中..." : "回滚"}
                      </button>
                    </div>
                  </div>

                  {/* Expanded content preview */}
                  {expandedVersion === v.id && (
                    <div className="px-4 py-3 border-t border-surface-3 bg-surface-0">
                      <pre className="text-xs text-zinc-300 whitespace-pre-wrap max-h-64 overflow-y-auto font-mono leading-relaxed">
                        {v.content.length > 2000
                          ? v.content.slice(0, 2000) + "\n\n... (内容过长已截断)"
                          : v.content}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-surface-3 text-xs text-zinc-500">
          共 {versions.length} 个历史版本 · 回滚会自动保存当前内容为新版本
        </div>
      </div>
    </div>
  );
}


// ============== 小按钮（嵌入到FieldCard/ContentBlockCard的工具栏中）==============

interface VersionHistoryButtonProps {
  entityId: string;
  entityName: string;
  onRollback?: () => void;
}

export function VersionHistoryButton({ entityId, entityName, onRollback }: VersionHistoryButtonProps) {
  const [showPanel, setShowPanel] = useState(false);

  return (
    <>
      <button
        onClick={() => setShowPanel(true)}
        className="flex items-center gap-1 px-2.5 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 border border-surface-3 rounded-lg transition-colors"
        title="查看版本历史"
      >
        <History className="w-3.5 h-3.5" />
        版本
      </button>

      {showPanel && (
        <VersionHistoryPanel
          entityId={entityId}
          entityName={entityName}
          onRollback={onRollback}
          onClose={() => setShowPanel(false)}
        />
      )}
    </>
  );
}
