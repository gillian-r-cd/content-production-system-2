// frontend/components/agent-panel.tsx
// 功能: 右栏AI Agent对话面板
// 主要组件: AgentPanel, MessageBubble, MentionDropdown, ToolSelector
// 支持: @引用、对话历史加载、编辑重发、再试一次、一键复制、Tool调用

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { cn, PHASE_NAMES } from "@/lib/utils";
import { agentAPI } from "@/lib/api";
import type { Field, ChatMessageRecord } from "@/lib/api";

interface AgentPanelProps {
  projectId: string | null;
  fields?: Field[];
  onSendMessage?: (message: string) => Promise<string>;
  onContentUpdate?: () => void;  // 当Agent生成内容后刷新
  isLoading?: boolean;
}

// 可用的Tool列表
const AVAILABLE_TOOLS = [
  { id: "deep_research", name: "深度调研", desc: "使用DeepResearch进行网络调研" },
  { id: "generate_field", name: "生成字段", desc: "根据上下文生成指定字段内容" },
  { id: "simulate_consumer", name: "消费者模拟", desc: "模拟消费者体验内容" },
  { id: "evaluate_content", name: "内容评估", desc: "评估内容质量" },
];

export function AgentPanel({
  projectId,
  fields = [],
  onSendMessage,
  onContentUpdate,
  isLoading = false,
}: AgentPanelProps) {
  const [messages, setMessages] = useState<ChatMessageRecord[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showMentions, setShowMentions] = useState(false);
  const [showTools, setShowTools] = useState(false);
  const [mentionFilter, setMentionFilter] = useState("");
  const [mentionIndex, setMentionIndex] = useState(0);
  const [cursorPosition, setCursorPosition] = useState(0);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const mentionStartPos = useRef<number>(-1);

  const completedFields = fields.filter((f) => f.status === "completed");
  const filteredFields = completedFields.filter((f) =>
    f.name.toLowerCase().includes(mentionFilter.toLowerCase()) ||
    f.phase.toLowerCase().includes(mentionFilter.toLowerCase())
  );

  // 加载对话历史
  useEffect(() => {
    if (projectId) {
      loadHistory();
    } else {
      setMessages([]);
    }
  }, [projectId]);

  // 自动滚动
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadHistory = async () => {
    if (!projectId) return;
    try {
      const history = await agentAPI.getHistory(projectId);
      setMessages(history);
    } catch (err) {
      console.error("加载对话历史失败:", err);
    }
  };

  const insertMention = useCallback((field: Field) => {
    const beforeMention = input.slice(0, mentionStartPos.current);
    const afterMention = input.slice(cursorPosition);
    const newInput = `${beforeMention}@${field.name}${afterMention}`;
    setInput(newInput);
    setShowMentions(false);
    setMentionFilter("");
    mentionStartPos.current = -1;
    setTimeout(() => inputRef.current?.focus(), 0);
  }, [input, cursorPosition]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    const selectionStart = e.target.selectionStart || 0;
    setInput(value);
    setCursorPosition(selectionStart);

    const lastAtPos = value.lastIndexOf("@", selectionStart - 1);
    if (lastAtPos !== -1) {
      const textAfterAt = value.slice(lastAtPos + 1, selectionStart);
      if (!textAfterAt.includes(" ")) {
        mentionStartPos.current = lastAtPos;
        setMentionFilter(textAfterAt);
        setShowMentions(true);
        setMentionIndex(0);
        return;
      }
    }
    setShowMentions(false);
    setMentionFilter("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (showMentions && filteredFields.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionIndex((prev) => (prev + 1) % filteredFields.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionIndex((prev) => (prev - 1 + filteredFields.length) % filteredFields.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertMention(filteredFields[mentionIndex]);
        return;
      }
      if (e.key === "Escape") {
        setShowMentions(false);
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey && !showMentions) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = async () => {
    if (!input.trim() || !projectId || sending) return;

    const userMessage = input.trim();
    setInput("");
    setSending(true);
    setShowMentions(false);

    // 立即显示用户消息（乐观更新）
    const tempUserMsg: ChatMessageRecord = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: userMessage,
      original_content: userMessage,
      is_edited: false,
      metadata: {},
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    try {
      const response = await agentAPI.chat(projectId, userMessage);
      // 重新加载完整历史（包含真实的消息ID和Agent响应）
      await loadHistory();
      
      // 通知父组件刷新内容和进度
      if (onContentUpdate) {
        onContentUpdate();
      }
    } catch (error) {
      console.error("发送失败:", error);
      // 移除临时消息，显示错误
      setMessages((prev) => prev.filter((m) => m.id !== tempUserMsg.id));
    } finally {
      setSending(false);
    }
  };

  const handleRetry = async (messageId: string) => {
    if (!projectId) return;
    setSending(true);
    try {
      await agentAPI.retryMessage(messageId);
      await loadHistory();
    } catch (err) {
      console.error("重试失败:", err);
    } finally {
      setSending(false);
    }
  };

  const handleEdit = (message: ChatMessageRecord) => {
    setEditingMessageId(message.id);
    setEditContent(message.content);
  };

  const handleSaveEdit = async () => {
    if (!editingMessageId || !projectId || sending) return;

    setSending(true);  // 添加loading状态
    setEditingMessageId(null);  // 立即关闭编辑框
    
    try {
      await agentAPI.editMessage(editingMessageId, editContent);
      // 编辑后重新发送
      const response = await agentAPI.chat(projectId, editContent);
      await loadHistory();
      
      // 通知父组件刷新
      if (onContentUpdate) {
        onContentUpdate();
      }
    } catch (err) {
      console.error("编辑失败:", err);
    } finally {
      setSending(false);
      setEditContent("");
    }
  };

  const handleCopy = async (content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      // 可以添加toast提示
    } catch (err) {
      console.error("复制失败:", err);
    }
  };

  const handleToolCall = async (toolId: string) => {
    if (!projectId) return;
    setShowTools(false);
    setSending(true);

    try {
      await agentAPI.callTool(projectId, toolId, {});
      await loadHistory();
    } catch (err) {
      console.error("Tool调用失败:", err);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* 头部 */}
      <div className="px-4 py-3 border-b border-surface-3">
        <h2 className="font-semibold text-zinc-100">AI Agent</h2>
        <p className="text-xs text-zinc-500">
          {projectId ? "与 Agent 对话推进内容生产" : "请先选择项目"}
        </p>
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-zinc-500 py-8">
            <p>开始对话吧！</p>
            <p className="text-sm mt-2">
              你可以说 "开始" 来启动内容生产流程
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            isEditing={editingMessageId === msg.id}
            editContent={editContent}
            onEditContentChange={setEditContent}
            onEdit={() => handleEdit(msg)}
            onSaveEdit={handleSaveEdit}
            onCancelEdit={() => setEditingMessageId(null)}
            onRetry={() => handleRetry(msg.id)}
            onCopy={() => handleCopy(msg.content)}
          />
        ))}

        {sending && (
          <div className="flex items-center gap-2 text-zinc-500">
            <div className="w-2 h-2 bg-brand-500 rounded-full animate-pulse" />
            <span className="text-sm">Agent 正在思考...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 输入区 */}
      <div className="p-4 border-t border-surface-3">
        <div className="relative">
          {/* @引用下拉菜单 */}
          {showMentions && filteredFields.length > 0 && (
            <div className="absolute bottom-full left-0 right-0 mb-1 bg-surface-2 border border-surface-3 rounded-lg shadow-xl max-h-48 overflow-y-auto z-10">
              <div className="p-2 text-xs text-zinc-500 border-b border-surface-3">
                选择要引用的字段
              </div>
              {filteredFields.map((field, idx) => (
                <button
                  key={field.id}
                  onClick={() => insertMention(field)}
                  className={cn(
                    "w-full px-3 py-2 text-left hover:bg-surface-3 flex items-center gap-2",
                    idx === mentionIndex && "bg-surface-3"
                  )}
                >
                  <span className="text-xs text-zinc-500">{PHASE_NAMES[field.phase] || field.phase}</span>
                  <span className="text-sm text-zinc-200">{field.name}</span>
                </button>
              ))}
            </div>
          )}

          {/* Tool选择下拉 */}
          {showTools && (
            <div className="absolute bottom-full left-0 right-0 mb-1 bg-surface-2 border border-surface-3 rounded-lg shadow-xl z-10">
              <div className="p-2 text-xs text-zinc-500 border-b border-surface-3">
                选择要调用的工具
              </div>
              {AVAILABLE_TOOLS.map((tool) => (
                <button
                  key={tool.id}
                  onClick={() => handleToolCall(tool.id)}
                  className="w-full px-3 py-2 text-left hover:bg-surface-3"
                >
                  <div className="text-sm text-zinc-200">{tool.name}</div>
                  <div className="text-xs text-zinc-500">{tool.desc}</div>
                </button>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder={projectId ? "输入消息... 使用 @ 引用字段" : "请先选择项目"}
              disabled={!projectId || sending}
              className="flex-1 px-4 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
            />
            <button
              onClick={handleSend}
              disabled={!projectId || !input.trim() || sending}
              className="px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:bg-surface-3 disabled:cursor-not-allowed rounded-lg transition-colors"
            >
              发送
            </button>
          </div>
        </div>

        {/* 快捷操作 */}
        <div className="flex gap-2 mt-2 flex-wrap">
          <QuickAction label="继续" onClick={() => setInput("继续")} disabled={!projectId || sending} />
          <QuickAction label="开始调研" onClick={() => setInput("开始消费者调研")} disabled={!projectId || sending} />
          <QuickAction label="评估" onClick={() => setInput("评估当前内容")} disabled={!projectId || sending} />
          <button
            onClick={() => setShowTools(!showTools)}
            disabled={!projectId || sending}
            className="px-2 py-1 text-xs text-brand-400 hover:text-brand-300 hover:bg-surface-3 disabled:opacity-50 rounded transition-colors flex items-center gap-1"
          >
            🔧 调用工具
          </button>
        </div>
      </div>
    </div>
  );
}

interface MessageBubbleProps {
  message: ChatMessageRecord;
  isEditing: boolean;
  editContent: string;
  onEditContentChange: (content: string) => void;
  onEdit: () => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onRetry: () => void;
  onCopy: () => void;
}

function MessageBubble({
  message,
  isEditing,
  editContent,
  onEditContentChange,
  onEdit,
  onSaveEdit,
  onCancelEdit,
  onRetry,
  onCopy,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [showActions, setShowActions] = useState(false);

  const renderContent = (content: string) => {
    const parts = content.split(/(@[\u4e00-\u9fffa-zA-Z0-9_]+)/g);
    return parts.map((part, i) => {
      if (part.startsWith("@")) {
        return <span key={i} className="text-brand-400 font-medium">{part}</span>;
      }
      return part;
    });
  };

  return (
    <div
      className={cn("flex group", isUser ? "justify-end" : "justify-start")}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      <div className="relative max-w-[85%]">
        {/* 消息气泡 */}
        <div
          className={cn(
            "px-4 py-2 rounded-2xl",
            isUser
              ? "bg-brand-600 text-white rounded-br-md"
              : "bg-surface-3 text-zinc-200 rounded-bl-md"
          )}
        >
          {isEditing ? (
            <div className="space-y-2">
              <textarea
                value={editContent}
                onChange={(e) => onEditContentChange(e.target.value)}
                className="w-full bg-surface-1 text-zinc-200 rounded p-2 text-sm min-h-[60px]"
              />
              <div className="flex gap-2">
                <button onClick={onSaveEdit} className="px-2 py-1 text-xs bg-brand-600 rounded">
                  保存并重发
                </button>
                <button onClick={onCancelEdit} className="px-2 py-1 text-xs bg-surface-4 rounded">
                  取消
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="whitespace-pre-wrap text-sm">
                {renderContent(message.content)}
              </div>
              {message.is_edited && (
                <span className="text-xs opacity-50 ml-1">(已编辑)</span>
              )}
              {message.metadata?.tool_used && (
                <span className="text-xs opacity-70 block mt-1">
                  🔧 {message.metadata.tool_used}
                </span>
              )}
            </>
          )}
        </div>

        {/* 操作按钮 */}
        {showActions && !isEditing && (
          <div
            className={cn(
              "absolute top-0 flex gap-1 bg-surface-2 rounded-lg shadow-lg p-1 z-10",
              isUser ? "left-0 -translate-x-full -ml-2" : "right-0 translate-x-full ml-2"
            )}
          >
            <ActionButton icon="📋" title="复制" onClick={onCopy} />
            {isUser && <ActionButton icon="✏️" title="编辑重发" onClick={onEdit} />}
            {!isUser && <ActionButton icon="🔄" title="再试一次" onClick={onRetry} />}
          </div>
        )}
      </div>
    </div>
  );
}

function ActionButton({ icon, title, onClick }: { icon: string; title: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="w-6 h-6 flex items-center justify-center text-xs hover:bg-surface-3 rounded transition-colors"
    >
      {icon}
    </button>
  );
}

function QuickAction({ label, onClick, disabled }: { label: string; onClick: () => void; disabled: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 disabled:opacity-50 disabled:cursor-not-allowed rounded transition-colors"
    >
      {label}
    </button>
  );
}
