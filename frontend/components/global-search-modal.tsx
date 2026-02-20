// frontend/components/global-search-modal.tsx
// 功能: 全局搜索替换模态框
// 支持: 跨字段搜索、定位、单个/全部替换

"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Search, Replace, X, ChevronDown, ChevronRight, CaseSensitive, ArrowRight } from "lucide-react";
import { projectAPI } from "@/lib/api";
import type { SearchResult } from "@/lib/api";

interface GlobalSearchModalProps {
  projectId: string;
  open: boolean;
  onClose: () => void;
  onNavigateToField?: (fieldId: string, fieldType: "field" | "block") => void;
  onContentUpdate?: () => void;
}

export function GlobalSearchModal({
  projectId,
  open,
  onClose,
  onNavigateToField,
  onContentUpdate,
}: GlobalSearchModalProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [replaceText, setReplaceText] = useState("");
  const [showReplace, setShowReplace] = useState(false);
  const [caseSensitive, setCaseSensitive] = useState(false);
  
  // Escape 键关闭
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [totalMatches, setTotalMatches] = useState(0);
  const [isSearching, setIsSearching] = useState(false);
  const [isReplacing, setIsReplacing] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // 自动聚焦搜索框
  useEffect(() => {
    if (open && searchInputRef.current) {
      setTimeout(() => searchInputRef.current?.focus(), 100);
    }
  }, [open]);

  // 实时搜索（防抖）
  const doSearch = useCallback(async (query: string) => {
    if (!query.trim()) {
      setResults([]);
      setTotalMatches(0);
      return;
    }
    setIsSearching(true);
    try {
      const data = await projectAPI.search(projectId, query, caseSensitive);
      setResults(data.results);
      setTotalMatches(data.total_matches);
      // 默认展开所有结果
      setExpandedItems(new Set(data.results.map(r => r.id)));
    } catch (e) {
      console.error("Search failed:", e);
    } finally {
      setIsSearching(false);
    }
  }, [projectId, caseSensitive]);

  // 搜索防抖
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    searchTimeoutRef.current = setTimeout(() => {
      doSearch(searchQuery);
    }, 300);
    return () => {
      if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    };
  }, [searchQuery, caseSensitive, doSearch]);

  // 替换单个匹配
  const handleReplaceSingle = async (result: SearchResult, snippetIndex: number) => {
    if (!replaceText && replaceText !== "") return;
    setIsReplacing(true);
    try {
      const data = await projectAPI.replace(projectId, searchQuery, replaceText, {
        caseSensitive,
        targets: [{ type: result.type, id: result.id, indices: [snippetIndex] }],
      });
      setToast({ message: `已替换 ${data.replaced_count} 处`, type: "success" });
      // 重新搜索
      await doSearch(searchQuery);
      onContentUpdate?.();
    } catch (e) {
      setToast({ message: `替换失败: ${e}`, type: "error" });
    } finally {
      setIsReplacing(false);
    }
  };

  // 替换某个内容块/块中的所有匹配
  const handleReplaceInItem = async (result: SearchResult) => {
    setIsReplacing(true);
    try {
      const data = await projectAPI.replace(projectId, searchQuery, replaceText, {
        caseSensitive,
        targets: [{ type: result.type, id: result.id }],
      });
      setToast({ message: `已替换 ${data.replaced_count} 处`, type: "success" });
      await doSearch(searchQuery);
      onContentUpdate?.();
    } catch (e) {
      setToast({ message: `替换失败: ${e}`, type: "error" });
    } finally {
      setIsReplacing(false);
    }
  };

  // 全局替换所有
  const handleReplaceAll = async () => {
    if (!searchQuery.trim()) return;
    const confirmMsg = `确定要将所有 ${totalMatches} 处「${searchQuery}」替换为「${replaceText}」吗？此操作会保存版本记录。`;
    if (!confirm(confirmMsg)) return;

    setIsReplacing(true);
    try {
      const data = await projectAPI.replace(projectId, searchQuery, replaceText, {
        caseSensitive,
      });
      setToast({
        message: `已替换 ${data.replaced_count} 处（涉及 ${data.affected_items.length} 个内容块）`,
        type: "success",
      });
      await doSearch(searchQuery);
      onContentUpdate?.();
    } catch (e) {
      setToast({ message: `替换失败: ${e}`, type: "error" });
    } finally {
      setIsReplacing(false);
    }
  };

  // 切换展开/折叠
  const toggleExpand = (id: string) => {
    setExpandedItems(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // 键盘快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    if (open) {
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    }
  }, [open, onClose]);

  // Toast 自动消失
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-16">
      {/* 背景遮罩 */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* 搜索面板 */}
      <div className="relative w-[640px] max-h-[70vh] bg-surface-2 border border-surface-4 rounded-xl shadow-2xl flex flex-col">
        {/* 头部：搜索 + 替换输入 */}
        <div className="p-4 border-b border-surface-4">
          <div className="flex items-center gap-2">
            <Search size={16} className="text-zinc-400 shrink-0" />
            <input
              ref={searchInputRef}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索项目中的所有内容..."
              className="flex-1 bg-transparent text-zinc-200 text-sm outline-none placeholder:text-zinc-500"
            />
            <button
              onClick={() => setCaseSensitive(!caseSensitive)}
              title="区分大小写"
              className={`p-1 rounded transition-colors ${
                caseSensitive
                  ? "bg-brand-600 text-white"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-surface-3"
              }`}
            >
              <CaseSensitive size={16} />
            </button>
            <button
              onClick={() => setShowReplace(!showReplace)}
              title="替换"
              className={`p-1 rounded transition-colors ${
                showReplace
                  ? "bg-brand-600 text-white"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-surface-3"
              }`}
            >
              <Replace size={16} />
            </button>
            <button onClick={onClose} className="p-1 text-zinc-500 hover:text-zinc-300">
              <X size={16} />
            </button>
          </div>

          {/* 替换输入框 */}
          {showReplace && (
            <div className="flex items-center gap-2 mt-3">
              <ArrowRight size={16} className="text-zinc-500 shrink-0" />
              <input
                value={replaceText}
                onChange={(e) => setReplaceText(e.target.value)}
                placeholder="替换为..."
                className="flex-1 bg-surface-3 text-zinc-200 text-sm outline-none rounded px-2 py-1.5 placeholder:text-zinc-500"
              />
              <button
                onClick={handleReplaceAll}
                disabled={isReplacing || !searchQuery.trim() || totalMatches === 0}
                className="px-3 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              >
                全部替换 ({totalMatches})
              </button>
            </div>
          )}

          {/* 搜索统计 */}
          {searchQuery.trim() && (
            <div className="mt-2 text-xs text-zinc-500">
              {isSearching
                ? "正在搜索..."
                : `找到 ${totalMatches} 个匹配，分布在 ${results.length} 个内容块中`}
            </div>
          )}
        </div>

        {/* 搜索结果列表 */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {results.length === 0 && searchQuery.trim() && !isSearching ? (
            <div className="p-8 text-center text-zinc-500 text-sm">
              没有找到匹配的内容
            </div>
          ) : (
            results.map((result) => (
              <div key={result.id} className="border-b border-surface-4 last:border-b-0">
                {/* 字段/块标题 */}
                <div
                  className="flex items-center justify-between px-4 py-2 hover:bg-surface-3 cursor-pointer"
                  onClick={() => toggleExpand(result.id)}
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    {expandedItems.has(result.id) ? (
                      <ChevronDown size={14} className="text-zinc-500 shrink-0" />
                    ) : (
                      <ChevronRight size={14} className="text-zinc-500 shrink-0" />
                    )}
                    <span className={`text-xs px-1.5 py-0.5 rounded shrink-0 ${
                      result.type === "field"
                        ? "bg-blue-900/50 text-blue-400"
                        : "bg-purple-900/50 text-purple-400"
                    }`}>
                      {result.type === "field" ? "内容块" : "内容块"}
                    </span>
                    <span className="text-sm text-zinc-200 truncate font-medium">{result.name}</span>
                    {result.phase && (
                      <span className="text-xs text-zinc-500">({result.phase})</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-zinc-500">{result.match_count} 个匹配</span>
                    {showReplace && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleReplaceInItem(result);
                        }}
                        disabled={isReplacing}
                        className="px-2 py-0.5 text-xs bg-orange-600/80 hover:bg-orange-600 text-white rounded disabled:opacity-50"
                        title={`替换此内容块中的所有匹配`}
                      >
                        替换全部
                      </button>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onNavigateToField?.(result.id, result.type);
                      }}
                      className="px-2 py-0.5 text-xs bg-brand-600/80 hover:bg-brand-600 text-white rounded"
                      title="定位到此内容块"
                    >
                      定位
                    </button>
                  </div>
                </div>

                {/* 匹配片段 */}
                {expandedItems.has(result.id) && (
                  <div className="px-4 pb-2">
                    {result.snippets.map((snippet) => (
                      <div
                        key={snippet.index}
                        className="flex items-start gap-2 py-1.5 pl-6 group hover:bg-surface-3/50 rounded"
                      >
                        <span className="text-xs text-zinc-600 shrink-0 mt-0.5 w-8 text-right">
                          L{snippet.line}
                        </span>
                        <div className="flex-1 text-sm text-zinc-400 break-all min-w-0">
                          <span>{snippet.prefix}</span>
                          <mark className="bg-yellow-500/30 text-yellow-200 px-0.5 rounded">
                            {snippet.match}
                          </mark>
                          <span>{snippet.suffix}</span>
                        </div>
                        {showReplace && (
                          <button
                            onClick={() => handleReplaceSingle(result, snippet.index)}
                            disabled={isReplacing}
                            className="px-1.5 py-0.5 text-xs text-zinc-400 hover:text-white hover:bg-orange-600 rounded opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-50 shrink-0"
                            title="替换此处"
                          >
                            替换
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Toast */}
        {toast && (
          <div className={`absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded-lg text-sm shadow-lg ${
            toast.type === "success" ? "bg-green-600 text-white" : "bg-red-600 text-white"
          }`}>
            {toast.message}
          </div>
        )}
      </div>
    </div>
  );
}
