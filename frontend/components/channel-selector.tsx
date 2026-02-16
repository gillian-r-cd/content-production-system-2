// frontend/components/channel-selector.tsx
// 功能: 外延设计渠道选择组件
// 类似 ProposalSelector，但更简单：只有一级渠道列表
// P0-1: 统一使用 blockAPI（已移除 fieldAPI 分支）

"use client";

import { useState, useMemo, useEffect } from "react";
import { blockAPI, agentAPI } from "@/lib/api";
import type { ContentBlock } from "@/lib/api";
import { Check, Plus, Trash2, GripVertical, Send, Pencil, X } from "lucide-react";

// 渠道定义
interface Channel {
  id: string;
  name: string;
  reason: string;
  content_form: string;
  priority: "high" | "medium" | "low";
  selected?: boolean;  // 是否选中
}

// 渠道数据结构
interface ChannelsData {
  channels: Channel[];
  summary?: string;
  error?: string;
}

interface ChannelSelectorProps {
  projectId: string;
  fieldId: string;
  content: string;
  onConfirm: () => void;
  onFieldsCreated?: () => void;
  onSave?: () => void;
}

export function ChannelSelector({
  projectId,
  fieldId,
  content,
  onConfirm,
  onFieldsCreated,
  onSave,
}: ChannelSelectorProps) {
  // 解析渠道数据
  const initialData = useMemo<ChannelsData>(() => {
    try {
      const data = JSON.parse(content);
      // 默认全部选中
      const channels = (data.channels || []).map((ch: Channel) => ({
        ...ch,
        selected: ch.selected !== false,  // 默认选中
      }));
      return { ...data, channels };
    } catch {
      return { channels: [], error: "解析失败" };
    }
  }, [content]);

  const [channelsData, setChannelsData] = useState<ChannelsData>(initialData);
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isCreatingFields, setIsCreatingFields] = useState(false);
  const [editingChannel, setEditingChannel] = useState<string | null>(null);
  const [newChannelName, setNewChannelName] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  
  // Escape 键关闭弹窗
  useEffect(() => {
    if (!showAddModal) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setShowAddModal(false); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [showAddModal]);

  const selectedChannels = channelsData.channels.filter(ch => ch.selected);

  // 切换渠道选中状态
  const toggleChannel = (channelId: string) => {
    if (isConfirmed) return;
    setChannelsData(prev => ({
      ...prev,
      channels: prev.channels.map(ch =>
        ch.id === channelId ? { ...ch, selected: !ch.selected } : ch
      ),
    }));
  };

  // 添加新渠道
  const addChannel = () => {
    if (!newChannelName.trim()) return;
    const newChannel: Channel = {
      id: `custom_${Date.now()}`,
      name: newChannelName.trim(),
      reason: "用户自定义渠道",
      content_form: "待定义",
      priority: "medium",
      selected: true,
    };
    setChannelsData(prev => ({
      ...prev,
      channels: [...prev.channels, newChannel],
    }));
    setNewChannelName("");
    setShowAddModal(false);
  };

  // 删除渠道
  const deleteChannel = (channelId: string) => {
    if (isConfirmed) return;
    setChannelsData(prev => ({
      ...prev,
      channels: prev.channels.filter(ch => ch.id !== channelId),
    }));
  };

  // 更新渠道
  const updateChannel = (channelId: string, updates: Partial<Channel>) => {
    setChannelsData(prev => ({
      ...prev,
      channels: prev.channels.map(ch =>
        ch.id === channelId ? { ...ch, ...updates } : ch
      ),
    }));
  };

  // 保存修改（P0-1: 统一使用 blockAPI）
  const handleSave = async () => {
    setIsSaving(true);
    try {
      await blockAPI.update(fieldId, {
        content: JSON.stringify(channelsData, null, 2),
      });
      onSave?.();
    } catch (err) {
      console.error("保存失败:", err);
      alert("保存失败");
    } finally {
      setIsSaving(false);
    }
  };

  // 查找 produce_outer 阶段的 ContentBlock ID
  const _findProduceOuterParent = async (): Promise<string | null> => {
    try {
      const tree = await blockAPI.getProjectBlocks(projectId);
      const flatten = (blocks: ContentBlock[]): ContentBlock[] =>
        blocks.flatMap(b => [b, ...flatten(b.children || [])]);
      const all = flatten(tree.blocks || []);
      const phase = all.find(b => b.block_type === "phase" && b.special_handler === "produce_outer");
      return phase?.id || null;
    } catch { return null; }
  };

  // 确认并创建内容块
  const handleConfirm = async () => {
    if (selectedChannels.length === 0) {
      alert("请至少选择一个渠道");
      return;
    }

    setIsCreatingFields(true);
    try {
      // 找到 produce_outer 阶段作为父块
      const parentId = await _findProduceOuterParent();

      // 为每个选中的渠道创建一个 ContentBlock
      for (const channel of selectedChannels) {
        await blockAPI.create({
          project_id: projectId,
          parent_id: parentId,
          name: channel.name,
          block_type: "field",
          ai_prompt: `为「${channel.name}」渠道创作内容。
内容形式：${channel.content_form}
渠道特点：${channel.reason}`,
          need_review: true,
        });
      }

      // 保存确认状态
      const confirmedData = {
        ...channelsData,
        confirmed: true,
        confirmed_channels: selectedChannels.map(ch => ch.id),
      };
      await blockAPI.update(fieldId, {
        content: JSON.stringify(confirmedData, null, 2),
        status: "completed",
      });

      setIsConfirmed(true);
      onFieldsCreated?.();
      onConfirm();
    } catch (err) {
      console.error("创建内容块失败:", err);
      alert("创建内容块失败");
    } finally {
      setIsCreatingFields(false);
    }
  };

  const getPriorityIcon = (priority: string) => {
    switch (priority) {
      case "high": return "🔴";
      case "medium": return "🟡";
      default: return "⚪";
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case "high": return "border-red-500/30 bg-red-500/5";
      case "medium": return "border-yellow-500/30 bg-yellow-500/5";
      default: return "border-zinc-600/30 bg-zinc-600/5";
    }
  };

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-200">选择传播渠道</h2>
          <p className="text-sm text-zinc-500 mt-1">
            {channelsData.summary || "选择要使用的渠道，确认后将进入外延生产组"}
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-zinc-500">已选择</span>
          <span className="px-2 py-0.5 bg-brand-600 rounded-full font-medium">
            {selectedChannels.length}
          </span>
          <span className="text-zinc-500">个渠道</span>
        </div>
      </div>

      {/* 渠道列表 */}
      <div className="grid gap-3 md:grid-cols-2">
        {channelsData.channels.map((channel) => (
          <div
            key={channel.id}
            className={`
              relative p-4 rounded-xl border transition-all cursor-pointer
              ${channel.selected 
                ? "border-brand-500/50 bg-brand-500/10" 
                : getPriorityColor(channel.priority)
              }
              ${isConfirmed ? "opacity-70 cursor-default" : "hover:border-brand-500/30"}
            `}
            onClick={() => toggleChannel(channel.id)}
          >
            {/* 选中标记 */}
            <div className={`
              absolute top-3 right-3 w-5 h-5 rounded-full border-2 flex items-center justify-center
              ${channel.selected 
                ? "border-brand-500 bg-brand-500" 
                : "border-zinc-600"
              }
            `}>
              {channel.selected && <Check className="w-3 h-3 text-white" />}
            </div>

            {/* 渠道信息 */}
            <div className="pr-8">
              <div className="flex items-center gap-2 mb-2">
                <span>{getPriorityIcon(channel.priority)}</span>
                {editingChannel === channel.id ? (
                  <input
                    type="text"
                    value={channel.name}
                    onChange={(e) => updateChannel(channel.id, { name: e.target.value })}
                    onBlur={() => setEditingChannel(null)}
                    onKeyDown={(e) => e.key === "Enter" && setEditingChannel(null)}
                    onClick={(e) => e.stopPropagation()}
                    className="bg-transparent border-b border-brand-500 outline-none text-zinc-200 font-medium"
                    autoFocus
                  />
                ) : (
                  <span className="font-medium text-zinc-200">{channel.name}</span>
                )}
              </div>
              <p className="text-sm text-zinc-400 mb-2">{channel.reason}</p>
              <div className="flex items-center gap-2">
                <span className="text-xs px-2 py-0.5 bg-surface-3 rounded text-zinc-400">
                  {channel.content_form}
                </span>
              </div>
            </div>

            {/* 操作按钮 */}
            {!isConfirmed && (
              <div className="absolute bottom-3 right-3 flex gap-1">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditingChannel(channel.id);
                  }}
                  className="p-1 text-zinc-500 hover:text-zinc-300 rounded"
                >
                  <Pencil className="w-3 h-3" />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteChannel(channel.id);
                  }}
                  className="p-1 text-zinc-500 hover:text-red-400 rounded"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            )}
          </div>
        ))}

        {/* 添加渠道按钮 */}
        {!isConfirmed && (
          <button
            onClick={() => setShowAddModal(true)}
            className="p-4 rounded-xl border-2 border-dashed border-zinc-700 hover:border-brand-500/50 
                       flex items-center justify-center gap-2 text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <Plus className="w-5 h-5" />
            <span>添加渠道</span>
          </button>
        )}
      </div>

      {/* 底部操作栏 */}
      <div className="flex items-center justify-between pt-4 border-t border-surface-3">
        {isConfirmed ? (
          <div className="flex items-center gap-2 text-green-400">
            <Check className="w-5 h-5" />
            <span>已确认 {selectedChannels.length} 个渠道，请在左侧查看</span>
          </div>
        ) : (
          <>
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-50"
            >
              {isSaving ? "保存中..." : "保存修改"}
            </button>
            <button
              onClick={handleConfirm}
              disabled={selectedChannels.length === 0 || isCreatingFields}
              className="px-6 py-2.5 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm font-medium
                         flex items-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isCreatingFields ? (
                "创建中..."
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  确认并进入外延生产
                </>
              )}
            </button>
          </>
        )}
      </div>

      {/* 添加渠道弹窗 */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-surface-2 rounded-xl p-6 w-full max-w-md border border-surface-3">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-zinc-200">添加渠道</h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <input
              type="text"
              value={newChannelName}
              onChange={(e) => setNewChannelName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addChannel()}
              placeholder="输入渠道名称，如：小红书、抖音..."
              className="w-full px-4 py-3 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 
                         placeholder:text-zinc-600 focus:outline-none focus:border-brand-500"
              autoFocus
            />
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
              >
                取消
              </button>
              <button
                onClick={addChannel}
                disabled={!newChannelName.trim()}
                className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm disabled:opacity-50"
              >
                添加
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


