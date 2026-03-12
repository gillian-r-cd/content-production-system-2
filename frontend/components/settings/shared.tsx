// frontend/components/settings/shared.tsx
// 功能: Settings 页面的共享组件与 locale hook — ImportExportButtons, SingleExportButton, downloadJSON, FormField, TagInput, KeyValueEditor

"use client";

import { useEffect, useRef, useState } from "react";
import { Download, Upload } from "lucide-react";
import { isJaProjectLocale, resolveClientLocale } from "@/lib/project-locale";

export const LOCALE_OPTIONS = [
  { value: "zh-CN", label: "简体中文" },
  { value: "ja-JP", label: "日本語" },
];

export function formatLocaleLabel(locale?: string) {
  return LOCALE_OPTIONS.find((item) => item.value === locale)?.label || locale || "zh-CN";
}

export function LocaleBadge({ locale }: { locale?: string }) {
  return (
    <span className="text-xs bg-emerald-500/10 px-2 py-1 rounded-full text-emerald-400">
      {formatLocaleLabel(locale)}
    </span>
  );
}

export function useSettingsUiLocale() {
  const [locale, setLocale] = useState<"zh-CN" | "ja-JP">(() => resolveClientLocale());

  useEffect(() => {
    const syncLocale = () => {
      setLocale(resolveClientLocale());
    };

    syncLocale();
    window.addEventListener("storage", syncLocale);

    return () => {
      window.removeEventListener("storage", syncLocale);
    };
  }, []);

  return locale;
}

export function useSettingsUiIsJa() {
  return isJaProjectLocale(useSettingsUiLocale());
}

// ============== 导入导出按钮组件 ==============
interface ImportExportButtonsProps {
  onExportAll: () => Promise<void>;
  onExportSingle?: (id: string) => Promise<void>;
  onImport: (data: unknown[]) => Promise<void>;
  typeName: string;  // 如 "内容块模板"
}

export function ImportExportButtons({ onExportAll, onImport, typeName }: ImportExportButtonsProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const isJa = useSettingsUiIsJa();

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setImporting(true);
    try {
      const text = await file.text();
      const json = JSON.parse(text);
      
      // 支持两种格式：直接数组 或 { data: [...] }
      const data = Array.isArray(json) ? json : (json.data || []);
      await onImport(data);
      alert(isJa ? `${typeName} をインポートしました` : `导入${typeName}成功！`);
    } catch (err) {
      console.error("导入失败:", err);
      alert(`${isJa ? "インポートに失敗しました" : "导入失败"}: ${err instanceof Error ? err.message : (isJa ? "ファイル形式エラー" : "文件格式错误")}`);
    } finally {
      setImporting(false);
      // 清空 input 以便重复选择同一文件
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  return (
    <div className="flex items-center gap-2">
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        onChange={handleFileChange}
        className="hidden"
      />
      <button
        onClick={handleImportClick}
        disabled={importing}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors disabled:opacity-50"
      >
        <Upload className="w-4 h-4" />
        {importing ? (isJa ? "インポート中..." : "导入中...") : (isJa ? "インポート" : "导入")}
      </button>
      <button
        onClick={onExportAll}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
      >
        <Download className="w-4 h-4" />
        {isJa ? "すべてエクスポート" : "导出全部"}
      </button>
    </div>
  );
}

// 单个项目导出按钮
export function SingleExportButton({ onExport, title }: { onExport: () => Promise<void>; title?: string }) {
  const [exporting, setExporting] = useState(false);
  const isJa = useSettingsUiIsJa();
  
  const handleClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setExporting(true);
    try {
      await onExport();
    } finally {
      setExporting(false);
    }
  };
  
  return (
    <button
      onClick={handleClick}
      disabled={exporting}
      className="px-2 py-1 text-xs bg-surface-3 hover:bg-surface-4 rounded text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-50"
      title={title || (isJa ? "エクスポート" : "导出")}
    >
      <Download className="w-3.5 h-3.5" />
    </button>
  );
}

// 下载 JSON 文件的工具函数
export function downloadJSON(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ============== 通用表单组件 ==============

export function FormField({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-zinc-300 mb-1.5">{label}</label>
      {children}
      {hint && <p className="text-xs text-zinc-500 mt-1">{hint}</p>}
    </div>
  );
}

export function TagInput({ value, onChange, placeholder }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [input, setInput] = useState("");
  const isJa = useSettingsUiIsJa();
  
  const addTag = () => {
    if (input.trim() && !value.includes(input.trim())) {
      onChange([...value, input.trim()]);
      setInput("");
    }
  };
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addTag();
    }
  };
  
  const removeTag = (tag: string) => {
    onChange(value.filter(v => v !== tag));
  };
  
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {value.map((tag) => (
          <span key={tag} className="inline-flex items-center gap-1 px-2 py-1 bg-brand-600/20 text-brand-400 rounded-lg text-sm">
            {tag}
            <button onClick={() => removeTag(tag)} className="hover:text-red-400">×</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || (isJa ? "入力して Enter で追加..." : "输入后按回车添加...")}
          className="flex-1 px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <button
          type="button"
          onClick={addTag}
          disabled={!input.trim()}
          className="px-3 py-2 bg-brand-600 hover:bg-brand-700 disabled:bg-zinc-700 disabled:cursor-not-allowed text-white rounded-lg text-sm transition-colors"
        >
          {isJa ? "追加" : "添加"}
        </button>
      </div>
      {value.length === 0 && (
        <p className="text-xs text-zinc-500">{isJa ? "入力後に Enter キーを押すか「追加」をクリックしてください" : "输入问题后按 Enter 键或点击「添加」按钮"}</p>
      )}
    </div>
  );
}

export function KeyValueEditor({ value, onChange, keyPlaceholder, valuePlaceholder }: {
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
  keyLabel?: string;
  valueLabel?: string;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
}) {
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const isJa = useSettingsUiIsJa();
  
  const entries = Object.entries(value || {});
  
  const addPair = () => {
    if (newKey.trim() && newValue.trim()) {
      onChange({ ...value, [newKey.trim()]: newValue.trim() });
      setNewKey("");
      setNewValue("");
    }
  };
  
  const removePair = (key: string) => {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { [key]: _, ...rest } = value;
    onChange(rest);
  };
  
  const updateValue = (key: string, newVal: string) => {
    onChange({ ...value, [key]: newVal });
  };
  
  return (
    <div className="space-y-3">
      {entries.map(([k, v]) => (
        <div key={k} className="flex gap-2 items-center">
          <input
            value={k}
            disabled
            className="w-1/3 px-3 py-2 bg-surface-3 border border-surface-3 rounded-lg text-zinc-400 text-sm"
          />
          <input
            value={v}
            onChange={(e) => updateValue(k, e.target.value)}
            className="flex-1 px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <button onClick={() => removePair(k)} className="px-2 py-2 text-red-400 hover:text-red-300">
            ×
          </button>
        </div>
      ))}
      <div className="flex gap-2 items-center pt-2 border-t border-surface-3">
        <input
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
          placeholder={keyPlaceholder || (isJa ? "キー" : "属性名")}
          className="w-1/3 px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <input
          value={newValue}
          onChange={(e) => setNewValue(e.target.value)}
          placeholder={valuePlaceholder || (isJa ? "値" : "属性值")}
          className="flex-1 px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <button onClick={addPair} className="px-3 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm">
          {isJa ? "追加" : "添加"}
        </button>
      </div>
    </div>
  );
}
