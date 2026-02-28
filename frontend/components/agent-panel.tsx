// frontend/components/agent-panel.tsx
// 功能: 右栏AI Agent对话面板
// 主要组件: AgentPanel, MessageBubble, MentionDropdown, ToolSelector
// 支持: @引用、对话历史加载、编辑重发、再试一次、一键复制、Tool调用、流式输出、Markdown渲染、顶部模式切换标签栏、会话历史下拉列表（单删/批量删除）

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { cn, sendNotification, requestNotificationPermission } from "@/lib/utils";
import { agentAPI, parseReferences, API_BASE, modesAPI } from "@/lib/api";
import type { ChatMessageRecord, ContentBlock, AgentModeInfo, ConversationRecord } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { settingsAPI } from "@/lib/api";
import { Square, Clock, Trash2, X, Plus } from "lucide-react";
import { MemoryPanel } from "./memory-panel";
import { SuggestionCard, UndoToast } from "./suggestion-card";
import type { SuggestionCardData, SuggestionStatus, RollbackTarget } from "./suggestion-card";

// 统一的可引用项（兼容 Field 和 ContentBlock）
interface MentionItem {
  id: string;
  name: string;
  label: string;  // 显示在下拉菜单的分类标签（如阶段名或父级名）
  hasContent: boolean;
}

interface AgentPanelProps {
  projectId: string | null;
  currentPhase?: string;  // 当前阶段
  allBlocks?: ContentBlock[];  // 所有内容块
  onContentUpdate?: () => void;  // 当Agent生成内容后刷新
  /** M3: 外部组件注入的消息（如 Eval 诊断→Agent 修改桥接），消费后清空 */
  externalMessage?: string | null;
  onExternalMessageConsumed?: () => void;
}

// 工具名称映射（匹配后端 AGENT_TOOLS 的 tool.name）
const TOOL_NAMES: Record<string, string> = {
  propose_edit: "修改建议",
  rewrite_field: "重写内容块",
  generate_field_content: "生成内容块",
  query_field: "查询内容块",
  read_field: "读取内容块",
  update_field: "覆写内容块",
  manage_architecture: "架构操作",
  advance_to_phase: "推进组",
  run_research: "深度调研",
  manage_persona: "人物管理",
  run_evaluation: "内容评估",
  generate_outline: "大纲生成",
  manage_skill: "技能管理",
  // 旧名称兼容
  deep_research: "深度调研",
  generate_field: "生成内容块",
  evaluate_content: "内容评估",
};

const TOOL_DESCS: Record<string, string> = {
  propose_edit: "向用户展示修改建议和diff预览",
  rewrite_field: "重写整个内容块（全文重写/风格调整）",
  generate_field_content: "为指定内容块生成新内容",
  query_field: "查询内容块状态信息",
  read_field: "读取内容块完整原始内容",
  update_field: "直接用给定内容完整覆写内容块",
  manage_architecture: "添加/删除/移动组和内容块",
  advance_to_phase: "推进项目到下一组",
  run_research: "使用DeepResearch进行网络调研",
  manage_persona: "创建、编辑、选择消费者画像",
  run_evaluation: "对项目内容执行全面质量评估",
  generate_outline: "基于上下文生成内容大纲",
  manage_skill: "管理和应用可复用的AI技能",
};

export function AgentPanel({
  projectId,
  currentPhase,
  allBlocks = [],
  onContentUpdate,
  externalMessage,
  onExternalMessageConsumed,
}: AgentPanelProps) {
  const [messages, setMessages] = useState<ChatMessageRecord[]>([]);
  const [conversations, setConversations] = useState<ConversationRecord[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showMentions, setShowMentions] = useState(false);
  const [showTools, setShowTools] = useState(false);
  const [chatMode, setChatMode] = useState<string>("assistant");
  const [availableModes, setAvailableModes] = useState<AgentModeInfo[]>([]);
  const [mentionFilter, setMentionFilter] = useState("");
  const [mentionIndex, setMentionIndex] = useState(0);
  const [cursorPosition, setCursorPosition] = useState(0);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [availableTools, setAvailableTools] = useState<{ id: string; name: string; desc: string }[]>([]);
  const [showMemoryPanel, setShowMemoryPanel] = useState(false);
  const [showConversationList, setShowConversationList] = useState(false);
  const [selectedConvIds, setSelectedConvIds] = useState<Set<string>>(new Set());
  const conversationListRef = useRef<HTMLDivElement>(null);
  const [suggestions, setSuggestions] = useState<SuggestionCardData[]>([]);
  // M6 T6.7: UndoToast 队列（FIFO）— 连续接受多张卡片时依次显示撤回 toast
  const [undoQueue, setUndoQueue] = useState<{
    entityId: string;
    versionId: string;
    targetField: string;
    suggestionId: string;
    /** Group 全部撤回用: 多个 rollback 目标 */
    rollbackTargets?: RollbackTarget[];
  }[]>([]);
  // Suggestion 生命周期事件队列: accept/reject/undo 事件在此积累，下次发送消息时序列化注入
  const pendingEventsRef = useRef<string[]>([]);
  // M6 T6.3: suggestionsRef 镜像 suggestions state，供 useCallback 闭包读取最新值
  const suggestionsRef = useRef<SuggestionCardData[]>(suggestions);
  useEffect(() => { suggestionsRef.current = suggestions; }, [suggestions]);
  // M6 T6.5: 追问源卡片 ID，新卡片到达后标记旧卡片为 superseded
  // M7: 赋值时机从"点击追问时"改为"发送时"（由 T7.4 控制）
  const followUpSourceRef = useRef<string | null>(null);
  // M7 T7.1: 追问目标（UI 驱动），非空时输入框上方显示追问标签
  const [followUpTarget, setFollowUpTarget] = useState<{
    cardId: string;
    targetField: string;
    summary: string;
    groupId?: string;
  } | null>(null);

  // 加载可用 Agent 模式
  useEffect(() => {
    modesAPI.list().then((modes: AgentModeInfo[]) => {
      setAvailableModes(modes);
      // 如果当前模式不在列表中，重置为第一个
      if (modes.length > 0 && !modes.find((m: AgentModeInfo) => m.name === chatMode)) {
        setChatMode(modes[0].name);
      }
    }).catch(() => {
      console.error("Failed to load agent modes");
      // Fallback: 保持默认 assistant 模式
    });
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const mentionStartPos = useRef<number>(-1);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 构建统一的可引用项列表（兼容传统字段和灵活架构内容块）
  const mentionItems: MentionItem[] = (() => {
    const seen = new Set<string>(); // 用于去重
    
    if (allBlocks.length > 0) {
      // P0-1: 统一从 allBlocks (ContentBlock) 提取可引用项
      // 注意：allBlocks 是扁平数组，不应递归 children（会重复）
      const items: MentionItem[] = [];
      
      // 构建 ID→名称映射用于显示父级标签
      const blockById = new Map<string, ContentBlock>();
      for (const block of allBlocks) {
        blockById.set(block.id, block);
      }
      
      for (const block of allBlocks) {
        // 选所有 field 类型（不要求必须有内容）
        if (block.block_type === "field") {
          if (seen.has(block.id)) continue;
          seen.add(block.id);
          
          const parentBlock = block.parent_id ? blockById.get(block.parent_id) : null;
          items.push({
            id: block.id,
            name: block.name,
            label: parentBlock?.name || "内容块",
            hasContent: !!(block.content && block.content.trim()),
          });
          
          // 如果是 design_inner 类型的内容块，提取方案供单独引用
          if (block.special_handler === "design_inner") {
            try {
              const parsed = JSON.parse(block.content);
              const proposals = parsed?.proposals;
              if (Array.isArray(proposals)) {
                proposals.forEach((p: { id?: string | number; name?: string }, i: number) => {
                  if (p && p.name) {
                    const pName = `方案${i + 1}:${p.name}`;
                    if (!seen.has(pName)) {
                      seen.add(pName);
                      items.push({
                        id: `proposal_${p.id || i}`,
                        name: pName,
                        label: "内涵设计",
                        hasContent: true,
                      });
                    }
                  }
                });
              }
            } catch { /* not JSON, skip */ }
          }
        }
      }
      return items;
    }
    // P0-1: 传统 ProjectField 分支已移除，统一使用 ContentBlock
    return [];
  })();

  const filteredMentionItems = mentionItems.filter((item) =>
    item.name.toLowerCase().includes(mentionFilter.toLowerCase()) ||
    item.label.toLowerCase().includes(mentionFilter.toLowerCase())
  );

  const loadConversations = useCallback(async () => {
    if (!projectId) return;
    try {
      const rows = await agentAPI.listConversations(projectId, chatMode);
      setConversations(rows);
      if (rows.length === 0) {
        const created = await agentAPI.createConversation({
          project_id: projectId,
          mode: chatMode,
        });
        setConversations([created]);
        setActiveConversationId(created.id);
        return;
      }
      if (!activeConversationId || !rows.some((c) => c.id === activeConversationId)) {
        setActiveConversationId(rows[0].id);
      }
    } catch (err) {
      console.error("加载会话列表失败:", err);
    }
  }, [projectId, chatMode, activeConversationId]);

  const loadHistory = useCallback(async () => {
    if (!projectId || !activeConversationId) return;
    try {
      const history = await agentAPI.getConversationMessages(activeConversationId, 200);
      setMessages(history);

      // 从 message_metadata.suggestion_cards 恢复卡片状态（持久化 → 刷新后不丢失）
      const restoredCards: SuggestionCardData[] = [];
      for (const msg of history) {
        const cards = msg.metadata?.suggestion_cards;
        if (cards && Array.isArray(cards)) {
          for (const c of cards) {
            restoredCards.push({
              id: c.id,
              target_field: c.target_field,
              summary: c.summary || "",
              reason: c.reason,
              diff_preview: c.diff_preview || "",
              edits_count: c.edits_count || 0,
              group_id: c.group_id,
              group_summary: c.group_summary,
              status: (c.status || "pending") as SuggestionStatus,
              messageId: msg.id,
              mode: msg.metadata?.mode || "assistant",
            });
          }
        }
      }
      setSuggestions(restoredCards);
    } catch (err) {
      console.error("加载对话历史失败:", err);
    }
  }, [projectId, activeConversationId]);

  // 按 mode 加载会话列表
  useEffect(() => {
    if (projectId) {
      setMessages([]);
      setSuggestions([]);
      loadConversations();
    } else {
      setConversations([]);
      setActiveConversationId(null);
      setMessages([]);
    }
  }, [projectId, chatMode, loadConversations]);

  // 会话切换后加载消息
  useEffect(() => {
    if (projectId && activeConversationId) {
      loadHistory();
    }
  }, [projectId, activeConversationId, loadHistory]);

  // 加载工具列表（从后台 Agent 设置）
  useEffect(() => {
    // 旧工具名 → 新工具名映射（兼容已保存的旧配置）
    const TOOL_ID_MIGRATION: Record<string, string> = {
      deep_research: "run_research",
      generate_field: "generate_field_content",
      evaluate_content: "run_evaluation",
    };

    const loadTools = async () => {
      try {
        const settings = await settingsAPI.getAgentSettings();
        const seen = new Set<string>();
        const tools = (settings.tools || [])
          .map((rawId: string) => TOOL_ID_MIGRATION[rawId] || rawId)  // 迁移旧名称
          .filter((id: string) => { if (seen.has(id)) return false; seen.add(id); return true; })  // 去重
          .map((toolId: string) => ({
            id: toolId,
            name: TOOL_NAMES[toolId] || toolId,
            desc: TOOL_DESCS[toolId] || "工具",
          }));
        setAvailableTools(tools);
      } catch (err) {
        console.error("加载工具列表失败:", err);
        setAvailableTools([
          { id: "propose_edit", name: "修改建议", desc: "向用户展示修改建议和diff预览" },
          { id: "rewrite_field", name: "重写内容块", desc: "重写整个内容块（全文重写/风格调整）" },
          { id: "generate_field_content", name: "生成内容块", desc: "为指定内容块生成新内容" },
          { id: "query_field", name: "查询内容块", desc: "查询内容块状态信息" },
          { id: "read_field", name: "读取内容块", desc: "读取内容块完整原始内容" },
          { id: "update_field", name: "覆写内容块", desc: "直接用给定内容完整覆写内容块" },
          { id: "manage_architecture", name: "架构操作", desc: "添加/删除/移动组和内容块" },
          { id: "advance_to_phase", name: "推进组", desc: "推进项目到下一组" },
          { id: "run_research", name: "深度调研", desc: "使用DeepResearch进行网络调研" },
          { id: "manage_persona", name: "人物管理", desc: "创建、编辑、选择消费者画像" },
          { id: "run_evaluation", name: "内容评估", desc: "对项目内容执行全面质量评估" },
          { id: "generate_outline", name: "大纲生成", desc: "基于上下文生成内容大纲" },
          { id: "manage_skill", name: "技能管理", desc: "管理和应用可复用的AI技能" },
        ]);
      }
    };
    loadTools();
  }, []);

  // 自动滚动
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(timer);
  }, [toast]);

  // M3: 外部组件注入消息（如 Eval 诊断→Agent 修改）— 消费后通知父组件清空
  useEffect(() => {
    if (externalMessage && !sending) {
      handleSend(externalMessage);
      onExternalMessageConsumed?.();
    }
  }, [externalMessage]); // eslint-disable-line react-hooks/exhaustive-deps

  const insertMention = useCallback((item: MentionItem) => {
    const beforeMention = input.slice(0, mentionStartPos.current);
    const afterMention = input.slice(cursorPosition);
    const mentionText = `@${item.name} `;  // 末尾加空格，方便继续输入
    const newInput = `${beforeMention}${mentionText}${afterMention}`;
    const newCursorPos = beforeMention.length + mentionText.length;
    setInput(newInput);
    setShowMentions(false);
    setMentionFilter("");
    mentionStartPos.current = -1;
    // 聚焦并把光标移到插入文字之后
    setTimeout(() => {
      const el = inputRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(newCursorPos, newCursorPos);
      }
    }, 0);
  }, [input, cursorPosition]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    const selectionStart = e.target.selectionStart || 0;
    setInput(value);
    setCursorPosition(selectionStart);

    // 自动调整 textarea 高度
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";  // 最大约6行

    const lastAtPos = value.lastIndexOf("@", selectionStart - 1);
    if (lastAtPos !== -1) {
      const textAfterAt = value.slice(lastAtPos + 1, selectionStart);
      // 支持含空格的字段名：如果输入含空格，检查是否有已知字段名以此开头
      // 例如输入 "@Eval t" 时，"Eval test" 以 "Eval t" 开头 → 保持下拉显示
      const hasNewline = textAfterAt.includes("\n");
      const hasSpace = textAfterAt.includes(" ");
      const keepOpen = !hasNewline && (
        !hasSpace ||
        mentionItems.some((item) =>
          item.name.toLowerCase().startsWith(textAfterAt.toLowerCase())
        )
      );
      if (keepOpen) {
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
    if (showMentions && filteredMentionItems.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionIndex((prev) => (prev + 1) % filteredMentionItems.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionIndex((prev) => (prev - 1 + filteredMentionItems.length) % filteredMentionItems.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertMention(filteredMentionItems[mentionIndex]);
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

  const handleSend = async (overrideMessage?: string) => {
    const messageToSend = overrideMessage || input.trim();
    if (!messageToSend || !projectId || !activeConversationId || sending) return;
    // 首次发送时请求通知权限（需在用户交互中触发）
    requestNotificationPermission();

    const userMessage = messageToSend;
    
    // 提取 @ 引用的字段名（传入已知字段名以支持含空格的名称）
    const knownNames = mentionItems.map((item) => item.name);
    const references = parseReferences(userMessage, knownNames);
    console.log("[AgentPanel] 发送消息，引用内容块:", references);
    
    setInput("");
    setSending(true);
    setShowMentions(false);
    // 重置 textarea 高度
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
    }

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

    // 创建 AbortController 用于停止生成
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      // 构建请求体（含追问上下文注入）
      const requestBody: Record<string, unknown> = {
        project_id: projectId,
        message: userMessage,
        references,
        current_phase: currentPhase || undefined,
        mode: chatMode,
        conversation_id: activeConversationId,
      };

      // M7 T7.4: 追问上下文注入 — 发送时生成，而非点击追问时
      if (followUpTarget) {
        if (followUpTarget.groupId) {
          // Group 追问：上下文包含整组信息
          const groupCards = suggestionsRef.current.filter((s) => s.group_id === followUpTarget.groupId);
          const cardSummaries = groupCards.map((c) => `「${c.target_field}」: ${c.summary}`).join("; ");
          pendingEventsRef.current.push(
            `[用户正在对修改建议组 (${groupCards.length} 项: ${cardSummaries}) 进行追问，组摘要: ${followUpTarget.summary}]`
          );
        } else {
          // 单 Card 追问
          pendingEventsRef.current.push(
            `[用户正在对「${followUpTarget.targetField}」的修改建议 #${followUpTarget.cardId.slice(0, 8)} 进行追问，原建议摘要: ${followUpTarget.summary}]`
          );
        }
        // M7: ref 赋值从点击时延迟到发送时，确保 SSE supersede 匹配的 ref 始终对应最近一次发送
        followUpSourceRef.current = followUpTarget.cardId;
        setFollowUpTarget(null);  // 清空 UI 标签
      }

      // Suggestion 生命周期上下文注入（Layer 3）
      if (pendingEventsRef.current.length > 0) {
        requestBody.followup_context = pendingEventsRef.current.join("\n");
        pendingEventsRef.current = []; // 发送后清空
      }

      // 使用流式 API（传递 current_phase 确保后端使用正确的阶段）
      const response = await fetch(`${API_BASE}/api/agent/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
        signal: abortController.signal,
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
      const cardSummaries: string[] = [];  // M6 T6.6: 累积卡片摘要
      
      // 产出类型路由（内容应显示在中间区，聊天区只显示简短确认）
      // 后端使用的阶段名称（兼容旧 route 事件）
      const PRODUCE_ROUTES = ["intent", "research", "design_inner", "produce_inner", 
                               "design_outer", "produce_outer", "evaluate",
                               "generate_field", "rewrite"];

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
                // 记录路由类型（后端兼容事件，首个 tool 触发）
                currentRoute = data.target;
                console.log("[AgentPanel] Route:", currentRoute);
                
                // 显示当前正在执行的操作
                const routeStatusNames: Record<string, string> = {
                  "intent": "🔍 正在分析意图...",
                  "research": "📊 正在进行消费者调研...",
                  "design_inner": "✏️ 正在设计内涵方案...",
                  "produce_inner": "📝 正在生产内涵内容...",
                  "design_outer": "🎨 正在设计外延方案...",
                  "produce_outer": "🖼️ 正在生产外延内容...",
                  "evaluate": "📋 正在执行评估...",
                  "generate_field": "⚙️ 正在生成内容块...",
                  "rewrite": "✏️ 正在重写内容...",
                  "suggest": "✏️ 正在生成修改建议...",
                  "generic_research": "🔍 正在进行深度调研...",
                  "advance_phase": "⏭️ 正在推进组...",
                  "query": "🔎 正在查询内容块...",
                  "chat": "💬 正在思考...",
                };
                const statusText = routeStatusNames[currentRoute] || `⏳ 正在处理 [${currentRoute}]...`;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === tempAiMsg.id ? { ...m, content: statusText } : m
                  )
                );
              } else if (data.type === "tool_start") {
                // 工具开始执行（LangGraph 新事件）
                const toolName = TOOL_NAMES[data.tool] || data.tool;
                console.log("[AgentPanel] Tool start:", data.tool);
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === tempAiMsg.id
                      ? { ...m, content: `🔧 正在使用 ${toolName}...` }
                      : m
                  )
                );
              } else if (data.type === "tool_progress") {
                // 工具内部 LLM 生成进度
                const toolName = TOOL_NAMES[data.tool] || data.tool;
                const chars = data.chars || 0;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === tempAiMsg.id
                      ? { ...m, content: `🔧 ${toolName} 生成中... (${chars} 字)` }
                      : m
                  )
                );
              } else if (data.type === "tool_end") {
                // 工具完成（LangGraph 新事件）
                console.log("[AgentPanel] Tool end:", data.tool, "field_updated:", data.field_updated);
                if (data.field_updated && onContentUpdate) {
                  onContentUpdate();
                }
                // 更新 AI 气泡：显示工具完成摘要（不再停留在"正在使用XXX"）
                const toolName = TOOL_NAMES[data.tool] || data.tool;
                const summary = data.output ? data.output.slice(0, 200) : "";
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === tempAiMsg.id
                      ? { ...m, content: `✅ ${toolName} 完成。${summary ? "\n" + summary : ""}` }
                      : m
                  )
                );
              } else if (data.type === "suggestion_card") {
                // Suggestion Card（propose_edit 工具输出）— 关联到当前 AI 消息
                console.log("[AgentPanel] Suggestion card:", data.id, data.target_field, "→ msg:", tempAiMsg.id, "mode:", chatMode);
                const newCard: SuggestionCardData = {
                  id: data.id,
                  target_field: data.target_field,
                  summary: data.summary || "",
                  reason: data.reason,
                  diff_preview: data.diff_preview || "",
                  edits_count: data.edits_count || 0,
                  group_id: data.group_id,
                  group_summary: data.group_summary,
                  status: "pending",
                  messageId: tempAiMsg.id,  // 关联到产生此卡片的 AI 消息
                  mode: chatMode,           // 记录产生此卡片的 Agent 模式（M1.5 mode 隔离）
                };

                // M6 T6.5: 追问→superseded 闭环
                // 如果有追问源卡片且新卡片目标字段相同，标记旧卡片为 superseded
                const sourceCardId = followUpSourceRef.current;
                if (sourceCardId) {
                  const sourceCard = suggestionsRef.current.find((s) => s.id === sourceCardId);
                  if (sourceCard && sourceCard.target_field === data.target_field) {
                    setSuggestions((prev) =>
                      prev.map((s) => s.id === sourceCardId ? { ...s, status: "superseded" as SuggestionStatus } : s)
                    );
                    // 持久化 superseded 状态（fire-and-forget）
                    if (projectId) {
                      fetch(`${API_BASE}/api/agent/confirm-suggestion`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                          project_id: projectId,
                          suggestion_id: sourceCardId,
                          action: "supersede",  // 使用正确的 action，后端映射为 "superseded" 状态
                        }),
                      }).catch(() => {});
                    }
                  }
                  followUpSourceRef.current = null;  // 消费后清空
                }

                setSuggestions((prev) => [...prev, newCard]);
                // M6 T6.6: 累积卡片摘要（不覆盖之前的）
                cardSummaries.push(data.summary || data.target_field);
                const summaryText = cardSummaries.map((s, i) => `${i + 1}. **${s}**`).join("\n");
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === tempAiMsg.id
                      ? { ...m, content: `✏️ 修改建议已生成：\n${summaryText}` }
                      : m
                  )
                );
              } else if (data.type === "token") {
                // 逐 token 更新（LLM 思考/回复内容）
                fullContent += data.content;
                
                // 只有非产出模式才实时显示内容
                if (!PRODUCE_ROUTES.includes(currentRoute)) {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === tempAiMsg.id ? { ...m, content: fullContent } : m
                    )
                  );
                }
              } else if (data.type === "user_saved") {
                // 后端返回用户消息的真实 ID，更新临时 ID
                if (data.message_id) {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === tempUserMsg.id ? { ...m, id: data.message_id } : m
                    )
                  );
                }
              } else if (data.type === "done") {
                // 流式完成
                const actualRoute = data.route || currentRoute;
                const isProducing = data.is_producing || PRODUCE_ROUTES.includes(actualRoute);
                
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id !== tempAiMsg.id) return m;
                    // 优先用流式累积的 fullContent；如果为空，保留气泡中已有的内容（如工具完成摘要）
                    let finalContent = fullContent || m.content || "";
                    if (isProducing && (!finalContent || finalContent.includes("已生成【】"))) {
                      finalContent = "✅ 内容已生成，请在左侧工作台查看和编辑。";
                    }
                    return { ...m, id: data.message_id, content: finalContent };
                  })
                );
                // 同步更新关联的 SuggestionCard 的 messageId（temp → 真实 ID）
                if (data.message_id && data.message_id !== tempAiMsg.id) {
                  setSuggestions((prev) =>
                    prev.map((s) => s.messageId === tempAiMsg.id ? { ...s, messageId: data.message_id } : s)
                  );
                }
                if (data.conversation_id) {
                  setActiveConversationId(data.conversation_id);
                }
                // M7 T7.5: 流结束后清空 followUpSourceRef（AI 回复纯文字没有新卡片时避免残留）
                followUpSourceRef.current = null;
                sendNotification(
                  isProducing ? "内容生成完成" : "Agent 回复完成",
                  isProducing ? "内容已生成完毕，点击查看" : "Agent 已完成回复，点击查看"
                );
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
            } catch {
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
      // 如果是用户主动中断，不显示错误
      if (error instanceof DOMException && error.name === "AbortError") {
        console.log("[AgentPanel] 用户停止了生成");
        setMessages((prev) =>
          prev.map((m) =>
            m.id === tempAiMsg.id && !m.content
              ? { ...m, content: "⏹️ 已停止生成" }
              : m.id === tempAiMsg.id && m.content === "⏳ 正在生成内容..."
              ? { ...m, content: "⏹️ 已停止生成" }
              : m
          )
        );
      } else {
        console.error("发送失败:", error);
        // 更新临时 AI 消息显示错误
        setMessages((prev) =>
          prev.map((m) =>
            m.id === tempAiMsg.id
              ? { ...m, content: `❌ 发送失败: ${error}` }
              : m
          )
        );
      }
    } finally {
      setSending(false);
      abortControllerRef.current = null;
    }
  };

  // 停止生成
  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  };

  const handleRetry = async (messageId: string) => {
    if (!projectId) return;
    setSending(true);
    try {
      await agentAPI.retryMessage(messageId);
      // 清除 undoQueue: loadHistory 会重建 suggestions，旧的 undo toast 不再有效
      setUndoQueue([]);
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
    if (!editingMessageId || !projectId || !activeConversationId || sending) return;

    setSending(true);
    setEditingMessageId(null);
    
    // 提取 @ 引用（传入已知字段名以支持含空格的名称）
    const knownNames = mentionItems.map((item) => item.name);
    const references = parseReferences(editContent, knownNames);
    const editedContent = editContent;
    setEditContent("");
    
    try {
      // 1. 先更新编辑的消息（可能失败，如果 ID 是临时的则跳过）
      try {
        await agentAPI.editMessage(editingMessageId, editedContent);
      } catch (editErr) {
        console.warn("[handleSaveEdit] 编辑消息失败（可能是临时ID），继续重新发送:", editErr);
      }
      
      // 2. 删除该消息之后的所有消息（从UI中移除），并更新编辑消息
      const editedMsgIndex = messages.findIndex(m => m.id === editingMessageId);
      if (editedMsgIndex !== -1) {
        // M6 T6.8: 收集被截断消息的 ID，用于清理关联的 suggestion cards
        const removedMsgIds = new Set(messages.slice(editedMsgIndex + 1).map(m => m.id));
        setMessages(prev => {
          const updated = prev.slice(0, editedMsgIndex);
          const editedMsg = { ...prev[editedMsgIndex], content: editedContent, is_edited: true };
          return [...updated, editedMsg];
        });
        // M6 T6.8: 移除被截断消息关联的 suggestion cards（避免孤儿卡片）
        if (removedMsgIds.size > 0) {
          setSuggestions((prev) => prev.filter((s) => !s.messageId || !removedMsgIds.has(s.messageId)));
          // 同步清理 undoQueue 中被移除卡片相关的 toast
          setUndoQueue((prev) => prev.filter((t) => {
            const card = suggestionsRef.current.find((s) => s.id === t.suggestionId);
            return !card || !card.messageId || !removedMsgIds.has(card.messageId);
          }));
        }
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
      
      // 4. 使用流式 API 重新发送（包含 current_phase + Layer 3 事件）
      const editRequestBody: Record<string, unknown> = {
        project_id: projectId,
        message: editedContent,
        references,
        current_phase: currentPhase || undefined,
        mode: chatMode,
        conversation_id: activeConversationId,
      };
      // M7 T7.4: 追问上下文注入（与 handleSend 对齐）
      if (followUpTarget) {
        if (followUpTarget.groupId) {
          const groupCards = suggestionsRef.current.filter((s) => s.group_id === followUpTarget.groupId);
          const cardSummaries = groupCards.map((c) => `「${c.target_field}」: ${c.summary}`).join("; ");
          pendingEventsRef.current.push(
            `[用户正在对修改建议组 (${groupCards.length} 项: ${cardSummaries}) 进行追问，组摘要: ${followUpTarget.summary}]`
          );
        } else {
          pendingEventsRef.current.push(
            `[用户正在对「${followUpTarget.targetField}」的修改建议 #${followUpTarget.cardId.slice(0, 8)} 进行追问，原建议摘要: ${followUpTarget.summary}]`
          );
        }
        followUpSourceRef.current = followUpTarget.cardId;
        setFollowUpTarget(null);
      }
      // Layer 3: 注入积累的 Suggestion 生命周期事件
      if (pendingEventsRef.current.length > 0) {
        editRequestBody.followup_context = pendingEventsRef.current.join("\n");
        pendingEventsRef.current = [];
      }
      const response = await fetch(`${API_BASE}/api/agent/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editRequestBody),
      });

      if (!response.ok) throw new Error(`Stream failed: ${response.status}`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No reader");

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let currentRoute = "";
      const cardSummaries: string[] = [];  // M6 T6.6b: 累积卡片摘要（与 handleSend 对齐）

      const PRODUCE_ROUTES = ["intent", "research", "design_inner", "produce_inner", 
                               "design_outer", "produce_outer", "evaluate",
                               "generate_field", "rewrite"];

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
              if (data.type === "user_saved") {
                // 更新编辑消息的 ID 为后端真实 ID
                if (data.message_id) {
                  setMessages(prev =>
                    prev.map(m => m.id === editingMessageId ? { ...m, id: data.message_id } : m)
                  );
                }
              } else if (data.type === "route") {
                currentRoute = data.target;
                const routeStatusNames: Record<string, string> = {
                  "intent": "🔍 正在分析意图...",
                  "research": "📊 正在进行消费者调研...",
                  "generate_field": "⚙️ 正在生成内容块...",
                  "rewrite": "✏️ 正在重写内容...",
                  "suggest": "✏️ 正在生成修改建议...",
                  "evaluate": "📋 正在执行评估...",
                  "advance_phase": "⏭️ 正在推进组...",
                  "chat": "💬 正在思考...",
                };
                const statusText = routeStatusNames[currentRoute] || `⏳ 正在处理...`;
                setMessages(prev =>
                  prev.map(m => m.id === tempAiMsg.id ? { ...m, content: statusText } : m)
                );
              } else if (data.type === "tool_start") {
                const toolName = TOOL_NAMES[data.tool] || data.tool;
                setMessages(prev =>
                  prev.map(m => m.id === tempAiMsg.id ? { ...m, content: `🔧 正在使用 ${toolName}...` } : m)
                );
              } else if (data.type === "tool_progress") {
                const toolName = TOOL_NAMES[data.tool] || data.tool;
                const chars = data.chars || 0;
                setMessages(prev =>
                  prev.map(m => m.id === tempAiMsg.id
                    ? { ...m, content: `🔧 ${toolName} 生成中... (${chars} 字)` }
                    : m)
                );
              } else if (data.type === "tool_end") {
                if (data.field_updated && onContentUpdate) {
                  onContentUpdate();
                }
                const tn = TOOL_NAMES[data.tool] || data.tool;
                const sm = data.output ? data.output.slice(0, 200) : "";
                setMessages(prev =>
                  prev.map(m => m.id === tempAiMsg.id ? { ...m, content: `✅ ${tn} 完成。${sm ? "\n" + sm : ""}` } : m)
                );
              } else if (data.type === "suggestion_card") {
                console.log("[AgentPanel] Suggestion card (edit):", data.id, data.target_field, "→ msg:", tempAiMsg.id, "mode:", chatMode);
                const newCard: SuggestionCardData = {
                  id: data.id,
                  target_field: data.target_field,
                  summary: data.summary || "",
                  reason: data.reason,
                  diff_preview: data.diff_preview || "",
                  edits_count: data.edits_count || 0,
                  group_id: data.group_id,
                  group_summary: data.group_summary,
                  status: "pending",
                  messageId: tempAiMsg.id,  // 关联到产生此卡片的 AI 消息
                  mode: chatMode,           // 记录产生此卡片的 Agent 模式（M1.5 mode 隔离）
                };

                // M7: supersede 逻辑（与 handleSend 对齐）
                const sourceCardId = followUpSourceRef.current;
                if (sourceCardId) {
                  const sourceCard = suggestionsRef.current.find((s) => s.id === sourceCardId);
                  if (sourceCard && sourceCard.target_field === data.target_field) {
                    setSuggestions((prev) =>
                      prev.map((s) => s.id === sourceCardId ? { ...s, status: "superseded" as SuggestionStatus } : s)
                    );
                    if (projectId) {
                      fetch(`${API_BASE}/api/agent/confirm-suggestion`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                          project_id: projectId,
                          suggestion_id: sourceCardId,
                          action: "supersede",
                        }),
                      }).catch(() => {});
                    }
                  }
                  followUpSourceRef.current = null;
                }

                setSuggestions((prev) => [...prev, newCard]);
                // M6 T6.6b: 累积卡片摘要（与 handleSend 对齐）
                cardSummaries.push(data.summary || data.target_field);
                const summaryText = cardSummaries.map((s, i) => `${i + 1}. **${s}**`).join("\n");
                setMessages(prev =>
                  prev.map(m => m.id === tempAiMsg.id
                    ? { ...m, content: `✏️ 修改建议已生成：\n${summaryText}` }
                    : m)
                );
              } else if (data.type === "token") {
                fullContent += data.content;
                if (!PRODUCE_ROUTES.includes(currentRoute)) {
                  setMessages(prev =>
                    prev.map(m => m.id === tempAiMsg.id ? { ...m, content: fullContent } : m)
                  );
                }
              } else if (data.type === "done") {
                const actualRoute = data.route || currentRoute;
                const isProducing = data.is_producing || PRODUCE_ROUTES.includes(actualRoute);
                
                setMessages(prev =>
                  prev.map(m => {
                    if (m.id !== tempAiMsg.id) return m;
                    let fc = fullContent || m.content || "";
                    if (isProducing && !fc) fc = "✅ 内容已生成，请在左侧工作台查看和编辑。";
                    return { ...m, id: data.message_id, content: fc };
                  })
                );
                // 同步更新关联的 SuggestionCard 的 messageId（temp → 真实 ID）
                if (data.message_id && data.message_id !== tempAiMsg.id) {
                  setSuggestions((prev) =>
                    prev.map((s) => s.messageId === tempAiMsg.id ? { ...s, messageId: data.message_id } : s)
                  );
                }
                // M7 T7.5: 流结束后清空 followUpSourceRef
                followUpSourceRef.current = null;
              }
            } catch {}
          }
        }
      }
      
      // 通知父组件刷新
      if (onContentUpdate) {
        onContentUpdate();
      }
    } catch (err) {
      console.error("编辑重发失败:", err);
      // 重新加载历史以恢复
      await loadHistory();
    } finally {
      setSending(false);
    }
  };

  const handleCopy = async (content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setToast({ message: "已复制到剪贴板", type: "success" });
    } catch (err) {
      console.error("复制失败:", err);
      setToast({ message: "复制失败", type: "error" });
    }
  };

  // ── Suggestion Card 回调 ──

  const handleSuggestionStatusChange = useCallback((
    suggestionId: string,
    status: SuggestionStatus,
    undoInfo?: { entity_id: string; version_id: string },
  ) => {
    setSuggestions((prev) =>
      prev.map((s) => s.id === suggestionId ? { ...s, status, entity_id: undoInfo?.entity_id, version_id: undoInfo?.version_id } : s)
    );
    // M6 T6.3: 从 ref 读取最新 suggestions（避免闭包捕获过期值）
    const card = suggestionsRef.current.find((s) => s.id === suggestionId);
    const fieldName = card?.target_field || "unknown";
    if (status === "accepted") {
      pendingEventsRef.current.push(`[用户已接受对「${fieldName}」的修改建议 #${suggestionId.slice(0, 8)}，内容已更新]`);
    } else if (status === "rejected") {
      pendingEventsRef.current.push(`[用户已拒绝对「${fieldName}」的修改建议 #${suggestionId.slice(0, 8)}，内容未变更]`);
    }
    // 接受时显示 Undo Toast（仅当 version_id 有效时才可撤回）
    // M6 T6.7: 追加到 undoQueue（FIFO），避免覆盖前一张的 undo 机会
    if (status === "accepted" && undoInfo && undoInfo.version_id) {
      setUndoQueue((prev) => [...prev, {
        entityId: undoInfo.entity_id,
        versionId: undoInfo.version_id,
        targetField: card?.target_field || "",
        suggestionId,
      }]);
    }
  }, []);  // M6: 不再依赖 suggestions（从 ref 读取）

  const handleSuggestionFollowUp = useCallback((card: SuggestionCardData) => {
    // M7 T7.3: 只设置 followUpTarget，其余逻辑（ref 赋值、事件注入）延迟到发送时（T7.4）
    setFollowUpTarget({
      cardId: card.id,
      targetField: card.target_field,
      summary: card.summary,
      groupId: card.group_id,
    });
    inputRef.current?.focus();
  }, []);

  const handleUndoComplete = useCallback((suggestionId: string) => {
    // M6 T6.3: 从 ref 读取 suggestions（避免闭包捕获过期值）
    const currentSuggestions = suggestionsRef.current;
    // 推入撤回事件（Layer 3）
    // suggestionId 可能是单 card_id 或 group_id
    const card = currentSuggestions.find((s) => s.id === suggestionId);
    if (card) {
      // 单 card 撤回
      const fieldName = card.target_field || "unknown";
      pendingEventsRef.current.push(`[用户已撤回对「${fieldName}」的修改 #${suggestionId.slice(0, 8)}，内容已回滚到修改前版本]`);
      setSuggestions((prev) =>
        prev.map((s) => s.id === suggestionId ? { ...s, status: "undone" as SuggestionStatus } : s)
      );
    } else {
      // 可能是 group_id — 撤回整组
      const groupCards = currentSuggestions.filter((s) => s.group_id === suggestionId && s.status === "accepted");
      if (groupCards.length > 0) {
        const fieldNames = groupCards.map((c) => `「${c.target_field}」`).join("、");
        pendingEventsRef.current.push(`[用户已撤回对 ${fieldNames} 的${groupCards.length}项关联修改，内容已回滚到修改前版本]`);
        const groupCardIds = new Set(groupCards.map((c) => c.id));
        setSuggestions((prev) =>
          prev.map((s) => groupCardIds.has(s.id) ? { ...s, status: "undone" as SuggestionStatus } : s)
        );
      }
    }
    // M6 T6.7: 从队列移除当前 toast（shift 到下一个）
    setUndoQueue((prev) => prev.filter((t) => t.suggestionId !== suggestionId));
    if (onContentUpdate) onContentUpdate();

    // M6 T6.4: 持久化撤回状态到后端（前端 rollback 已完成，此处仅更新 metadata）
    if (projectId) {
      fetch(`${API_BASE}/api/agent/confirm-suggestion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          suggestion_id: suggestionId,
          action: "undo",
        }),
      }).catch((err) => {
        // 不阻断 UX：rollback 本身已完成，状态持久化失败仅 warn
        console.warn("[handleUndoComplete] undo 状态持久化失败:", err);
      });
    }
  }, [onContentUpdate, projectId]);  // M6: 不再依赖 suggestions（从 ref 读取）

  const handleToolCall = async (toolId: string) => {
    if (!projectId) return;
    setShowTools(false);

    // 把工具 ID 翻译为自然语言指令，通过 Agent 流式对话发送
    // 这样 Agent 有上下文、有流式进度，比直接调 /tool 好得多
    const TOOL_INSTRUCTIONS: Record<string, string> = {
      propose_edit: "请帮我看看当前内容有什么可以改进的，用修改建议卡片展示。",
      rewrite_field: "请帮我重写内容块。",
      generate_field_content: "请帮我生成当前内容块的内容。",
      query_field: "请查询当前内容块的状态。",
      read_field: "请读取当前内容块的内容。",
      update_field: "请帮我覆写内容块。",
      manage_architecture: "请帮我管理项目结构。",
      advance_to_phase: "请推进到下一个组。",
      run_research: "请帮我进行深度调研。",
      manage_persona: "请列出当前项目的消费者画像。",
      run_evaluation: "请对当前项目内容进行全面质量评估。",
      generate_outline: "请帮我生成内容大纲。",
      manage_skill: "请列出可用的AI技能。",
    };

    const instruction = TOOL_INSTRUCTIONS[toolId] || `请执行工具：${TOOL_NAMES[toolId] || toolId}`;
    // 直接调用 handleSend 并传入指令（不依赖 input state，避免异步竞态）
    await handleSend(instruction);
  };

  const handleCreateConversation = async () => {
    if (!projectId || sending) return;
    try {
      const conv = await agentAPI.createConversation({
        project_id: projectId,
        mode: chatMode,
      });
      setConversations((prev) => [conv, ...prev]);
      setActiveConversationId(conv.id);
      setMessages([]);
      setSuggestions([]);
    } catch (err) {
      console.error("创建会话失败:", err);
    }
  };

  // ---- 会话删除 ----
  const handleDeleteConversation = async (convId: string) => {
    try {
      await agentAPI.deleteConversation(convId);
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      setSelectedConvIds((prev) => { const next = new Set(prev); next.delete(convId); return next; });
      // 如果删除的是当前激活的会话，自动切换
      if (activeConversationId === convId) {
        const remaining = conversations.filter((c) => c.id !== convId);
        if (remaining.length > 0) {
          setActiveConversationId(remaining[0].id);
        } else {
          // 全部删完了，创建一个新的
          setActiveConversationId(null);
          setMessages([]);
          setSuggestions([]);
        }
      }
    } catch (err) {
      console.error("删除会话失败:", err);
    }
  };

  const handleBatchDeleteConversations = async () => {
    if (selectedConvIds.size === 0) return;
    const ids = Array.from(selectedConvIds);
    try {
      await agentAPI.batchDeleteConversations(ids);
      setConversations((prev) => prev.filter((c) => !selectedConvIds.has(c.id)));
      // 如果当前会话被删了，切换
      if (activeConversationId && selectedConvIds.has(activeConversationId)) {
        const remaining = conversations.filter((c) => !selectedConvIds.has(c.id));
        if (remaining.length > 0) {
          setActiveConversationId(remaining[0].id);
        } else {
          setActiveConversationId(null);
          setMessages([]);
          setSuggestions([]);
        }
      }
      setSelectedConvIds(new Set());
    } catch (err) {
      console.error("批量删除会话失败:", err);
    }
  };

  const toggleConvSelection = (convId: string) => {
    setSelectedConvIds((prev) => {
      const next = new Set(prev);
      if (next.has(convId)) { next.delete(convId); } else { next.add(convId); }
      return next;
    });
  };

  // 点击外部关闭会话列表
  useEffect(() => {
    if (!showConversationList) return;
    const handler = (e: MouseEvent) => {
      if (conversationListRef.current && !conversationListRef.current.contains(e.target as Node)) {
        setShowConversationList(false);
        setSelectedConvIds(new Set());
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showConversationList]);

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

      {/* 记忆面板（覆盖整个 Agent 面板区域） */}
      {showMemoryPanel && projectId && (
        <MemoryPanel
          projectId={projectId}
          onClose={() => setShowMemoryPanel(false)}
        />
      )}

      {/* 头部 + 模式切换（记忆面板隐藏时显示） */}
      {!showMemoryPanel && (
      <div className="border-b border-surface-3">
        <div className="px-4 pt-3 pb-2 flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-zinc-100">AI Agent</h2>
            <p className="text-xs text-zinc-500">
              {projectId ? "与 Agent 对话推进内容生产" : "请先选择项目"}
            </p>
          </div>
          {projectId && (
            <button
              onClick={() => setShowMemoryPanel(true)}
              title="查看项目记忆"
              className="text-zinc-500 hover:text-zinc-300 text-lg px-2 py-1 rounded hover:bg-surface-2 transition"
            >
              🧠
            </button>
          )}
        </div>
        {/* 模式切换标签栏 + 会话历史时钟 icon */}
        <div className="px-3 flex items-center gap-1 overflow-x-auto relative">
          <div className="flex gap-1 flex-1 overflow-x-auto">
            {availableModes.length > 0 ? (
              availableModes.map((mode) => (
                <button
                  key={mode.name}
                  onClick={() => setChatMode(mode.name)}
                  title={mode.description}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-t-lg transition-all whitespace-nowrap border-b-2",
                    chatMode === mode.name
                      ? "border-brand-500 text-brand-300 bg-brand-500/10"
                      : "border-transparent text-zinc-500 hover:text-zinc-300 hover:bg-surface-2"
                  )}
                >
                  <span className="text-base leading-none">{mode.icon}</span>
                  <span>{mode.display_name}</span>
                </button>
              ))
            ) : (
              <button
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-t-lg border-b-2 border-brand-500 text-brand-300 bg-brand-500/10"
              >
                <span className="text-base leading-none">🛠️</span>
                <span>助手</span>
              </button>
            )}
          </div>
          {/* 新建会话 + 会话历史 icon */}
          <div className="flex items-center gap-1 shrink-0 pb-1">
            <button
              onClick={handleCreateConversation}
              disabled={!projectId || sending}
              title="新建会话"
              className="p-1.5 rounded text-zinc-500 hover:text-zinc-300 hover:bg-surface-2 disabled:opacity-50 transition"
            >
              <Plus size={14} />
            </button>
            <button
              onClick={() => { setShowConversationList((v) => !v); setSelectedConvIds(new Set()); }}
              title="会话历史"
              className={cn(
                "p-1.5 rounded transition",
                showConversationList
                  ? "text-brand-300 bg-brand-500/10"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-surface-2"
              )}
            >
              <Clock size={14} />
            </button>
          </div>
          {/* 会话历史下拉列表 */}
          {showConversationList && (
            <div
              ref={conversationListRef}
              className="absolute top-full right-0 mt-1 w-64 z-50 bg-surface-1 border border-surface-3 rounded-lg shadow-xl"
            >
              {/* 列表头 */}
              <div className="flex items-center justify-between px-3 py-2 border-b border-surface-3">
                <span className="text-xs font-medium text-zinc-400">会话历史</span>
                <div className="flex items-center gap-1">
                  {selectedConvIds.size > 0 && (
                    <button
                      onClick={handleBatchDeleteConversations}
                      title={`删除选中的 ${selectedConvIds.size} 个会话`}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20 transition"
                    >
                      <Trash2 size={11} />
                      <span>删除({selectedConvIds.size})</span>
                    </button>
                  )}
                  <button
                    onClick={() => { setShowConversationList(false); setSelectedConvIds(new Set()); }}
                    className="p-1 rounded text-zinc-500 hover:text-zinc-300 hover:bg-surface-2 transition"
                  >
                    <X size={12} />
                  </button>
                </div>
              </div>
              {/* 会话列表 */}
              <div className="max-h-60 overflow-y-auto p-1.5 space-y-0.5">
                {conversations.length === 0 ? (
                  <div className="text-center text-zinc-500 text-xs py-4">暂无会话</div>
                ) : (
                  conversations.map((conv) => (
                    <div
                      key={conv.id}
                      className={cn(
                        "group flex items-center gap-1.5 px-2 py-1.5 rounded text-xs transition",
                        activeConversationId === conv.id
                          ? "bg-brand-500/10 text-brand-300"
                          : "text-zinc-400 hover:bg-surface-2"
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={selectedConvIds.has(conv.id)}
                        onChange={() => toggleConvSelection(conv.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="shrink-0 accent-brand-500"
                      />
                      <button
                        onClick={() => { setActiveConversationId(conv.id); setShowConversationList(false); setSelectedConvIds(new Set()); }}
                        className="flex-1 text-left truncate min-w-0"
                      >
                        {conv.title || "新会话"}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteConversation(conv.id); }}
                        title="删除此会话"
                        className="shrink-0 p-0.5 rounded text-zinc-600 hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      )}

      {!showMemoryPanel && (
      <>
      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-zinc-500 py-8">
            <p>开始对话吧！</p>
            <p className="text-sm mt-2">
              你可以说 &quot;开始&quot; 来启动内容生产流程
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id}>
            <MessageBubble
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
            {/* 此消息关联的 Suggestion Cards — inline 渲染在消息正下方 */}
            {/* 按 mode 隔离：只渲染当前模式产生的卡片（M1.5 修复跨模式泄漏） */}
            {suggestions
              .filter((card) => card.messageId === msg.id && (!card.mode || card.mode === chatMode))
              .map((card) => (
                <div key={card.id} className="mt-2">
                  <SuggestionCard
                    data={card}
                    projectId={projectId || ""}
                    onStatusChange={handleSuggestionStatusChange}
                    onFollowUp={handleSuggestionFollowUp}
                    onContentUpdate={onContentUpdate}
                  />
                </div>
              ))}
          </div>
        ))}

        {/* 无关联消息的 Suggestion Cards（兜底：当前 mode 的、messageId 无法匹配的卡片） */}
        {/* M1.5: 增加 mode 过滤，避免切换模式时其他 mode 的卡片从兜底区泄漏 */}
        {suggestions
          .filter(
            (card) =>
              (!card.mode || card.mode === chatMode) &&
              (!card.messageId || !messages.some((m) => m.id === card.messageId))
          )
          .map((card) => (
            <div key={card.id} className="mt-2">
              <SuggestionCard
                data={card}
                projectId={projectId || ""}
                onStatusChange={handleSuggestionStatusChange}
                onFollowUp={handleSuggestionFollowUp}
                onContentUpdate={onContentUpdate}
              />
            </div>
          ))}

        {sending && (
          <div className="flex items-center gap-2 text-zinc-500">
            <div className="w-2 h-2 bg-brand-500 rounded-full animate-pulse" />
            <span className="text-sm">Agent 正在思考...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Undo Toast — M6 T6.7: 队列模式，显示队首 toast + 剩余数量 */}
      {undoQueue.length > 0 && (() => {
        const current = undoQueue[0];
        return (
          <div className="px-4 py-2 border-t border-surface-3">
            <UndoToast
              key={current.suggestionId}  /* key 确保切换时重新挂载、重置计时 */
              entityId={current.entityId}
              versionId={current.versionId}
              targetField={current.targetField}
              onUndo={() => handleUndoComplete(current.suggestionId)}
              onExpire={() => setUndoQueue((prev) => prev.slice(1))}
              rollbackTargets={current.rollbackTargets}
            />
            {undoQueue.length > 1 && (
              <div className="text-xs text-zinc-500 mt-1 text-center">
                还有 {undoQueue.length - 1} 项修改可撤回
              </div>
            )}
          </div>
        );
      })()}

      {/* 输入区 */}
      <div className="p-4 border-t border-surface-3">
        <div className="relative">
          {/* @引用下拉菜单 */}
          {showMentions && filteredMentionItems.length > 0 && (
            <div className="absolute bottom-full left-0 right-0 mb-1 bg-surface-2 border border-surface-3 rounded-lg shadow-xl max-h-48 overflow-y-auto z-10">
              <div className="p-2 text-xs text-zinc-500 border-b border-surface-3">
                选择要引用的内容块（{filteredMentionItems.length} 个可用）
              </div>
              {filteredMentionItems.map((item, idx) => (
                <button
                  key={`${item.id}-${idx}`}
                  onClick={() => insertMention(item)}
                  className={cn(
                    "w-full px-3 py-2 text-left hover:bg-surface-3 flex items-center gap-2",
                    idx === mentionIndex && "bg-surface-3"
                  )}
                >
                  <span className="text-xs text-zinc-500">{item.label}</span>
                  <span className="text-sm text-zinc-200">{item.name}</span>
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

          {/* M7 T7.2: 追问标签条 — 与输入框视觉一体 */}
          {followUpTarget && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-surface-3 border border-surface-3 border-b-0 rounded-t-lg text-sm">
              <span className="text-zinc-400">💬 追问：</span>
              <span className="text-zinc-200 truncate">
                「{followUpTarget.targetField}」{followUpTarget.summary}
              </span>
              <button
                onClick={() => setFollowUpTarget(null)}
                className="ml-auto text-zinc-500 hover:text-zinc-300 shrink-0 px-1"
                title="取消追问"
              >
                ✕
              </button>
            </div>
          )}

          <div className="flex gap-2 items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder={projectId ? `输入消息... 使用 @ 引用内容块${mentionItems.length > 0 ? ` (${mentionItems.length}个可用)` : ""}` : "请先选择项目"}
              disabled={!projectId || !activeConversationId || sending}
              rows={1}
              className={cn(
                "flex-1 px-4 py-2 bg-surface-2 border border-surface-3 text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50 resize-none overflow-hidden",
                followUpTarget ? "rounded-b-lg rounded-t-none" : "rounded-lg"
              )}
              style={{ minHeight: "40px", maxHeight: "160px" }}
            />
            {sending ? (
              <button
                onClick={handleStopGeneration}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors text-white flex items-center gap-1.5"
                title="停止生成"
              >
                <Square className="w-4 h-4" />
                停止
              </button>
            ) : (
              <button
                onClick={() => handleSend()}
                disabled={!projectId || !activeConversationId || !input.trim()}
                className="px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:bg-surface-3 disabled:cursor-not-allowed rounded-lg transition-colors"
              >
                发送
              </button>
            )}
          </div>
        </div>

        {/* 快捷操作 */}
        <div className="flex gap-2 mt-2 flex-wrap items-center">
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
      </>
      )}
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
        return <span key={`ref-${i}`} className="text-brand-300 font-medium">{part}</span>;
      }
      return <span key={`txt-${i}`}>{part}</span>;
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
        rehypePlugins={[rehypeRaw]}
        components={{
          // 修订标记样式（<del>/<ins> 由 edit_engine 生成）
          del: ({ children }) => <del className="bg-red-900/30 text-red-300 line-through">{children}</del>,
          ins: ({ children }) => <ins className="bg-green-900/30 text-green-300 no-underline">{children}</ins>,
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
              {message.metadata?.tools_used && Array.isArray(message.metadata.tools_used) && message.metadata.tools_used.length > 0 && (
                <span className="text-xs opacity-70 block mt-1">
                  🔧 {message.metadata.tools_used.map((t: string) => TOOL_NAMES[t] || t).join(", ")}
                </span>
              )}
              {/* 旧格式兼容 */}
              {message.metadata?.tool_used && !message.metadata?.tools_used && (
                <span className="text-xs opacity-70 block mt-1">
                  🔧 {TOOL_NAMES[message.metadata.tool_used] || message.metadata.tool_used}
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
