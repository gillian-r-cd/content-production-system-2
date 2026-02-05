// frontend/components/agent-panel.tsx
// 功能: 右栏AI Agent对话面板
// 主要组件: AgentPanel, MessageBubble, MentionDropdown, ToolSelector
// 支持: @引用、对话历史加载、编辑重发、再试一次、一键复制、Tool调用、流式输出、Markdown渲染

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { cn, PHASE_NAMES } from "@/lib/utils";
import { agentAPI, parseReferences, API_BASE } from "@/lib/api";
import type { Field, ChatMessageRecord } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { settingsAPI } from "@/lib/api";

interface AgentPanelProps {
  projectId: string | null;
  fields?: Field[];
  onSendMessage?: (message: string) => Promise<string>;
  onContentUpdate?: () => void;  // 当Agent生成内容后刷新
  isLoading?: boolean;
}

// 工具名称映射
const TOOL_NAMES: Record<string, string> = {
  deep_research: "深度调研",
  generate_field: "生成字段",
  simulate_consumer: "消费者模拟",
  evaluate_content: "内容评估",
  architecture_writer: "架构操作",
  outline_generator: "大纲生成",
  persona_manager: "人物管理",
  skill_manager: "技能管理",
};

const TOOL_DESCS: Record<string, string> = {
  deep_research: "使用DeepResearch进行网络调研",
  generate_field: "根据上下文生成指定字段内容",
  simulate_consumer: "模拟消费者体验内容",
  evaluate_content: "评估内容质量",
  architecture_writer: "添加/删除/移动阶段和字段",
  outline_generator: "基于上下文生成内容大纲",
  persona_manager: "创建、编辑、选择消费者画像",
  skill_manager: "管理和应用可复用的AI技能",
};

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
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [availableTools, setAvailableTools] = useState<{ id: string; name: string; desc: string }[]>([]);

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

  // 加载工具列表（从后台 Agent 设置）
  useEffect(() => {
    const loadTools = async () => {
      try {
        const settings = await settingsAPI.getAgentSettings();
        const tools = (settings.tools || []).map((toolId: string) => ({
          id: toolId,
          name: TOOL_NAMES[toolId] || toolId,
          desc: TOOL_DESCS[toolId] || "工具",
        }));
        setAvailableTools(tools);
      } catch (err) {
        console.error("加载工具列表失败:", err);
        // 使用默认工具列表
        setAvailableTools([
          { id: "deep_research", name: "深度调研", desc: "使用DeepResearch进行网络调研" },
          { id: "generate_field", name: "生成字段", desc: "根据上下文生成指定字段内容" },
          { id: "simulate_consumer", name: "消费者模拟", desc: "模拟消费者体验内容" },
          { id: "evaluate_content", name: "内容评估", desc: "评估内容质量" },
        ]);
      }
    };
    loadTools();
  }, []);

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
    
    // 提取 @ 引用的字段名
    const references = parseReferences(userMessage);
    console.log("[AgentPanel] 发送消息，引用字段:", references);
    
    setInput("");
    setSending(true);
    setShowMentions(false);

    // 立即显示用户消息（乐观更新）
    const tempUserMsg: ChatMessageRecord = {
      id: `temp-user-${Date.now()}`,
      role: "user",
      content: userMessage,
      original_content: userMessage,
      is_edited: false,
      metadata: { references },
      created_at: new Date().toISOString(),
    };
    
    // 创建一个临时的 AI 回复消息（用于流式更新）
    const tempAiMsg: ChatMessageRecord = {
      id: `temp-ai-${Date.now()}`,
      role: "assistant",
      content: "",
      original_content: "",
      is_edited: false,
      metadata: {},
      created_at: new Date().toISOString(),
    };
    
    setMessages((prev) => [...prev, tempUserMsg, tempAiMsg]);

    try {
      // 使用流式 API
      const response = await fetch(`${API_BASE}/api/agent/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          message: userMessage,
          references,
        }),
      });

      if (!response.ok) {
        throw new Error(`Stream failed: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No reader");

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let currentRoute = "";  // 跟踪当前路由
      
      // 产出类型路由（内容应显示在中间区，聊天区只显示简短确认）
      const PRODUCE_ROUTES = ["intent_produce", "research", "design_inner", "produce_inner", 
                               "design_outer", "produce_outer", "simulate", "evaluate"];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.type === "route") {
                // 记录路由类型
                currentRoute = data.target;
                console.log("[AgentPanel] Route:", currentRoute);
                
                // 如果是产出模式，显示"生成中..."
                if (PRODUCE_ROUTES.includes(currentRoute)) {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === tempAiMsg.id ? { ...m, content: "⏳ 正在生成内容..." } : m
                    )
                  );
                }
              } else if (data.type === "token") {
                // 逐 token 更新
                fullContent += data.content;
                
                // 只有非产出模式才实时显示内容
                if (!PRODUCE_ROUTES.includes(currentRoute)) {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === tempAiMsg.id ? { ...m, content: fullContent } : m
                    )
                  );
                }
              } else if (data.type === "content") {
                // 一次性内容（非流式场景）
                fullContent = data.content;
                
                if (!PRODUCE_ROUTES.includes(currentRoute)) {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === tempAiMsg.id ? { ...m, content: fullContent } : m
                    )
                  );
                }
              } else if (data.type === "done") {
                // 流式完成
                const routeNames: Record<string, string> = {
                  "intent_produce": "意图分析",
                  "research": "消费者调研",
                  "design_inner": "内涵设计",
                  "produce_inner": "内涵生产",
                  "design_outer": "外延设计",
                  "produce_outer": "外延生产",
                  "simulate": "消费者模拟",
                  "evaluate": "评估报告",
                };
                
                // 产出模式：显示简短确认消息
                if (PRODUCE_ROUTES.includes(currentRoute)) {
                  const routeName = routeNames[currentRoute] || currentRoute;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === tempAiMsg.id
                        ? { ...m, id: data.message_id, content: `✅ 已生成【${routeName}】，请在左侧工作台查看和编辑。` }
                        : m
                    )
                  );
                } else {
                  // 对话模式：保持完整内容
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === tempAiMsg.id ? { ...m, id: data.message_id } : m
                    )
                  );
                }
              } else if (data.type === "error") {
                console.error("Stream error:", data.error);
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === tempAiMsg.id
                      ? { ...m, content: `❌ 错误: ${data.error}` }
                      : m
                  )
                );
              }
            } catch (e) {
              // JSON 解析失败，忽略
            }
          }
        }
      }
      
      // 通知父组件刷新内容和进度（特别是产出模式需要刷新中间区）
      if (onContentUpdate) {
        onContentUpdate();
      }
    } catch (error) {
      console.error("发送失败:", error);
      // 更新临时 AI 消息显示错误
      setMessages((prev) =>
        prev.map((m) =>
          m.id === tempAiMsg.id
            ? { ...m, content: `❌ 发送失败: ${error}` }
            : m
        )
      );
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

    setSending(true);
    setEditingMessageId(null);
    
    // 提取 @ 引用
    const references = parseReferences(editContent);
    const editedContent = editContent;
    setEditContent("");
    
    try {
      // 1. 先更新编辑的消息
      await agentAPI.editMessage(editingMessageId, editedContent);
      
      // 2. 删除该消息之后的所有消息（从UI中移除）
      const editedMsgIndex = messages.findIndex(m => m.id === editingMessageId);
      if (editedMsgIndex !== -1) {
        // 保留编辑的消息及之前的，移除之后的
        setMessages(prev => {
          const updated = prev.slice(0, editedMsgIndex);
          // 更新编辑的消息内容
          const editedMsg = { ...prev[editedMsgIndex], content: editedContent, is_edited: true };
          return [...updated, editedMsg];
        });
      }
      
      // 3. 创建临时 AI 回复
      const tempAiMsg: ChatMessageRecord = {
        id: `temp-ai-${Date.now()}`,
        role: "assistant",
        content: "",
        original_content: "",
        is_edited: false,
        metadata: {},
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, tempAiMsg]);
      
      // 4. 使用流式 API 重新发送
      const response = await fetch(`${API_BASE}/api/agent/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          message: editedContent,
          references,
        }),
      });

      if (!response.ok) throw new Error(`Stream failed: ${response.status}`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No reader");

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === "token") {
                fullContent += data.content;
                setMessages(prev =>
                  prev.map(m => m.id === tempAiMsg.id ? { ...m, content: fullContent } : m)
                );
              } else if (data.type === "content") {
                fullContent = data.content;
                setMessages(prev =>
                  prev.map(m => m.id === tempAiMsg.id ? { ...m, content: fullContent } : m)
                );
              } else if (data.type === "done") {
                setMessages(prev =>
                  prev.map(m => m.id === tempAiMsg.id ? { ...m, id: data.message_id } : m)
                );
              }
            } catch (e) {}
          }
        }
      }
      
      // 通知父组件刷新
      if (onContentUpdate) {
        onContentUpdate();
      }
    } catch (err) {
      console.error("编辑失败:", err);
      // 重新加载历史以恢复
      await loadHistory();
    } finally {
      setSending(false);
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
    <div className="flex flex-col h-full relative">
      {/* Toast 通知 */}
      {toast && (
        <div
          className={cn(
            "absolute top-2 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg shadow-lg transition-all duration-300",
            toast.type === "success"
              ? "bg-green-600/90 text-white"
              : "bg-red-600/90 text-white"
          )}
        >
          <div className="flex items-center gap-2">
            <span>{toast.type === "success" ? "✓" : "✕"}</span>
            <span className="text-sm">{toast.message}</span>
          </div>
        </div>
      )}

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
              {availableTools.map((tool) => (
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

  // 渲染用户消息（高亮 @ 引用）
  const renderUserContent = (content: string) => {
    const parts = content.split(/(@[\u4e00-\u9fffa-zA-Z0-9_]+)/g);
    return parts.map((part, i) => {
      if (part.startsWith("@")) {
        return <span key={i} className="text-brand-300 font-medium">{part}</span>;
      }
      return part;
    });
  };

  // 渲染 AI 消息（Markdown 渲染）
  const renderAiContent = (content: string) => {
    if (!content) {
      return <span className="text-zinc-500 animate-pulse">▌</span>;
    }
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // 自定义各种 Markdown 元素的样式
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          h1: ({ children }) => <h1 className="text-lg font-bold mb-2">{children}</h1>,
          h2: ({ children }) => <h2 className="text-base font-bold mb-2">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-bold mb-1">{children}</h3>,
          ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-1">{children}</ol>,
          li: ({ children }) => <li className="ml-2">{children}</li>,
          code: ({ className, children, ...props }) => {
            const isInline = !className;
            return isInline ? (
              <code className="bg-surface-1 px-1 py-0.5 rounded text-brand-400 text-xs" {...props}>
                {children}
              </code>
            ) : (
              <code className="block bg-surface-1 p-2 rounded text-xs overflow-x-auto my-2" {...props}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => <pre className="bg-surface-1 rounded overflow-x-auto">{children}</pre>,
          strong: ({ children }) => <strong className="font-bold text-zinc-100">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand-400 hover:underline">
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-brand-500 pl-3 my-2 text-zinc-400 italic">
              {children}
            </blockquote>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    );
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
              <div className="text-sm">
                {isUser ? renderUserContent(message.content) : renderAiContent(message.content)}
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
