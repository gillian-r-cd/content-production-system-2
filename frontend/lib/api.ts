// frontend/lib/api.ts
// 功能: API客户端，封装后端API调用
// 主要函数: fetchAPI, streamAPI
// 数据结构: Project, Field, ChatMessage

export const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

// ============== Types ==============

export interface Project {
  id: string;
  name: string;
  version: number;
  version_note: string;
  creator_profile_id: string | null;
  current_phase: string;
  phase_order: string[];
  phase_status: Record<string, string>;
  /** @deprecated 已废弃，不再由传统流程设置 */
  agent_autonomy?: Record<string, boolean>;
  /** @deprecated P3-2: 已废弃 */
  golden_context?: Record<string, string>;
  use_deep_research: boolean;
  use_flexible_architecture?: boolean;  // [已废弃] 统一为 true
  created_at: string;
  updated_at: string;
}

/** @deprecated P0-1: 统一使用 ContentBlock，此接口仅保留供 FieldCard（经典视图）编译通过 */
export interface Field {
  id: string;
  project_id: string;
  phase: string;
  name: string;
  field_type: string;
  content: string;
  status: string;
  ai_prompt: string;
  pre_questions: string[];
  pre_answers: Record<string, string>;
  dependencies: {
    depends_on: string[];
    dependency_type: string;
  };
  constraints?: Record<string, unknown>;   // 字段生产约束
  need_review: boolean;             // 是否需要人工确认（false = 自动生成）
  template_id: string | null;
  version_warning?: string;         // 版本变更警告（更新时返回）
  affected_fields?: string[];       // 受影响的字段名列表
  created_at: string;
  updated_at: string;
}

export interface CreatorProfile {
  id: string;
  name: string;
  description: string;
  traits: Record<string, unknown>;
  created_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  message_id: string;
  message: string;
  phase: string;
  phase_status: Record<string, string>;
  waiting_for_human: boolean;
}

export interface ChatMessageRecord {
  id: string;
  role: "user" | "assistant";
  content: string;
  original_content: string;
  is_edited: boolean;
  metadata: {
    phase?: string;
    mode?: string;
    tool_used?: string;
    tools_used?: string[];
    skill_used?: string;
    references?: string[];
    is_retry?: boolean;
    suggestion_cards?: Array<{
      id: string;
      target_field: string;
      summary: string;
      reason?: string;
      diff_preview: string;
      edits_count: number;
      group_id?: string;
      group_summary?: string;
      status: string;
    }>;
  };
  created_at: string;
}

export interface Persona {
  source: string;
  name: string;
  background: string;
  story: string;
}

export interface SimulationRecord {
  id: string;
  project_id: string;
  simulator_id: string;
  target_field_ids: string[];
  persona: Persona;
  interaction_log: unknown[];
  feedback: {
    scores: Record<string, number>;
    comments: Record<string, string>;
    overall: string;
    error?: string;
  };
  status: string;
  created_at: string;
}

export interface PersonaFromResearch {
  name: string;
  background: string;
  story: string;
}

// ============== API Functions ==============

async function fetchAPI<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    // 处理Pydantic验证错误格式 (detail可能是数组)
    let errorMessage: string;
    if (typeof error.detail === "string") {
      errorMessage = error.detail;
    } else if (Array.isArray(error.detail)) {
      errorMessage = error.detail
        .map((e: unknown) => {
          const item = e as Record<string, unknown>;
          const msg = item.msg;
          if (typeof msg === "string" && msg.trim()) return msg;
          const message = item.message;
          if (typeof message === "string" && message.trim()) return message;
          return JSON.stringify(e);
        })
        .join("; ");
    } else {
      errorMessage = `API error: ${response.status}`;
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

// ============== Project API ==============

export const projectAPI = {
  list: () => fetchAPI<Project[]>("/api/projects/"),
  
  get: (id: string) => fetchAPI<Project>(`/api/projects/${id}`),
  
  create: (data: { 
    name: string; 
    creator_profile_id?: string; 
    use_deep_research?: boolean;
    use_flexible_architecture?: boolean;
    phase_order?: string[];  // [] 表示从零开始
  }) =>
    fetchAPI<Project>("/api/projects/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  
  update: (id: string, data: Partial<Project>) =>
    fetchAPI<Project>(`/api/projects/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  
  delete: (id: string) =>
    fetchAPI<{ message: string }>(`/api/projects/${id}`, { method: "DELETE" }),
  
  createVersion: (id: string, version_note: string) =>
    fetchAPI<Project>(`/api/projects/${id}/versions`, {
      method: "POST",
      body: JSON.stringify({ version_note }),
    }),

  duplicate: (id: string) =>
    fetchAPI<Project>(`/api/projects/${id}/duplicate`, { method: "POST" }),

  exportProject: (id: string, includeLogs: boolean = false) =>
    fetchAPI<Record<string, unknown>>(`/api/projects/${id}/export?include_logs=${includeLogs}`),

  importProject: (data: Record<string, unknown>, matchCreatorProfile: boolean = true) =>
    fetchAPI<{ message: string; project: Project; stats: Record<string, number> }>(
      "/api/projects/import",
      {
        method: "POST",
        body: JSON.stringify({ data, match_creator_profile: matchCreatorProfile }),
      }
    ),

  search: (id: string, query: string, caseSensitive: boolean = false) =>
    fetchAPI<{
      results: SearchResult[];
      total_matches: number;
    }>(`/api/projects/${id}/search`, {
      method: "POST",
      body: JSON.stringify({ query, case_sensitive: caseSensitive }),
    }),

  replace: (
    id: string,
    query: string,
    replacement: string,
    options?: {
      caseSensitive?: boolean;
      targets?: Array<{ type: string; id: string; indices?: number[] }>;
    }
  ) =>
    fetchAPI<{
      replaced_count: number;
      affected_items: Array<{ type: string; id: string; name: string; count: number }>;
    }>(`/api/projects/${id}/replace`, {
      method: "POST",
      body: JSON.stringify({
        query,
        replacement,
        case_sensitive: options?.caseSensitive || false,
        targets: options?.targets || null,
      }),
    }),
};

// ============== Search Types ==============

export interface SearchSnippet {
  index: number;
  offset: number;
  prefix: string;
  match: string;
  suffix: string;
  line: number;
}

export interface SearchResult {
  type: "field" | "block";
  id: string;
  name: string;
  phase: string;
  parent_id?: string;
  match_count: number;
  snippets: SearchSnippet[];
}

// ============== Field API (已废弃 P0-1: 统一使用 blockAPI) ==============

/** @deprecated P0-1: 统一使用 blockAPI */
export const fieldAPI = {
  listByProject: (projectId: string, phase?: string) => {
    const query = phase ? `?phase=${phase}` : "";
    return fetchAPI<Field[]>(`/api/fields/project/${projectId}${query}`);
  },
  
  get: (id: string) => fetchAPI<Field>(`/api/fields/${id}`),
  
  create: (data: Partial<Field>) =>
    fetchAPI<Field>("/api/fields/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  
  update: (id: string, data: Partial<Field>) =>
    fetchAPI<Field>(`/api/fields/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  
  delete: (id: string) =>
    fetchAPI<{ message: string }>(`/api/fields/${id}`, { method: "DELETE" }),
  
  generate: (id: string, pre_answers: Record<string, string> = {}) =>
    fetchAPI<Field>(`/api/fields/${id}/generate`, {
      method: "POST",
      body: JSON.stringify({ pre_answers }),
    }),
};

// ============== Agent API ==============

export const agentAPI = {
  chat: (projectId: string, message: string, options?: { currentPhase?: string; references?: string[] }) =>
    fetchAPI<ChatResponse>("/api/agent/chat", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        message,
        current_phase: options?.currentPhase,
        references: options?.references || [],
      }),
    }),
  
  advance: (projectId: string) =>
    fetchAPI<ChatResponse>("/api/agent/advance", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        message: "继续",
      }),
    }),
  
  stream: async function* (
    projectId: string,
    message: string,
    currentPhase?: string,
    mode?: string
  ): AsyncGenerator<{ node?: string; content?: string; done?: boolean; error?: string }> {
    const { readSSEStream } = await import("@/lib/sse");

    const response = await fetch(`${API_BASE}/api/agent/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        message,
        current_phase: currentPhase,
        mode: mode || "assistant",
      }),
    });

    yield* readSSEStream(response);
  },

  // 获取对话历史
  getHistory: (projectId: string, limit: number = 100, mode?: string) =>
    fetchAPI<ChatMessageRecord[]>(`/api/agent/history/${projectId}?limit=${limit}${mode ? `&mode=${mode}` : ""}`),
  
  // 编辑消息
  editMessage: (messageId: string, content: string) =>
    fetchAPI<ChatMessageRecord>(`/api/agent/message/${messageId}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  
  // 重试/再试一次
  retryMessage: (messageId: string) =>
    fetchAPI<ChatResponse>(`/api/agent/retry/${messageId}`, {
      method: "POST",
    }),
  
  // 删除消息
  deleteMessage: (messageId: string) =>
    fetchAPI<unknown>(`/api/agent/message/${messageId}`, { method: "DELETE" }),
  
  // 调用Tool
  callTool: (projectId: string, toolName: string, parameters: Record<string, unknown> = {}) =>
    fetchAPI<ChatResponse>("/api/agent/tool", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        tool_name: toolName,
        parameters,
      }),
    }),

  // M4: Inline AI 编辑（轻量级 LLM 调用，不经过 Agent Graph）
  inlineEdit: (data: {
    text: string;
    operation: "rewrite" | "expand" | "condense";
    context?: string;
    project_id?: string;
  }) =>
    fetchAPI<{ original: string; replacement: string; diff_preview: string }>(
      "/api/agent/inline-edit",
      { method: "POST", body: JSON.stringify(data) }
    ),
};

// ============== Settings API ==============

export interface SystemPromptItem {
  id: string;
  name: string;
  phase: string;
  content?: string;
}

export interface EvalPromptItem {
  id: string;
  phase: string;
  name?: string;
  description?: string;
  content?: string;
}

export interface FieldTemplateFieldItem {
  name: string;
  type: string;
  ai_prompt: string;
  content?: string;
  pre_questions?: string[];
  depends_on?: string[];
  need_review?: boolean;
  special_handler?: string;
}

export interface FieldTemplateItem {
  id: string;
  name: string;
  description: string;
  category: string;
  fields: FieldTemplateFieldItem[];
}

export interface ChannelItem {
  id: string;
  name: string;
  description?: string;
  platform?: string;
  prompt_template?: string;
}

export interface SimulatorItem {
  id: string;
  name: string;
  description?: string;
  interaction_type: string;
  prompt_template?: string;
  secondary_prompt?: string;
  grader_template?: string;
  evaluation_dimensions?: string[];
  max_turns?: number;
}

export interface AgentSkillItem {
  name: string;
  description: string;
  prompt: string;
}

export interface AgentSettingsData {
  tools?: string[];
  skills?: AgentSkillItem[];
  tool_prompts?: Record<string, string>;
}

export interface SettingsLogItem {
  id: string;
  [key: string]: unknown;
}

export const settingsAPI = {
  // System Prompts
  listSystemPrompts: () =>
    fetchAPI<SystemPromptItem[]>("/api/settings/system-prompts"),
  
  updateSystemPrompt: (id: string, data: unknown) =>
    fetchAPI<unknown>(`/api/settings/system-prompts/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  listEvalPrompts: () =>
    fetchAPI<EvalPromptItem[]>("/api/settings/eval-prompts"),
  updateEvalPrompt: (id: string, data: unknown) =>
    fetchAPI<unknown>(`/api/settings/eval-prompts/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  syncEvalPresets: () =>
    fetchAPI<{
      imported_graders: number;
      updated_graders: number;
      imported_simulators: number;
      updated_simulators: number;
    }>("/api/settings/eval-presets/sync", { method: "POST" }),

  // Creator Profiles
  listCreatorProfiles: () =>
    fetchAPI<CreatorProfile[]>("/api/settings/creator-profiles"),
  
  createCreatorProfile: (data: Partial<CreatorProfile>) =>
    fetchAPI<CreatorProfile>("/api/settings/creator-profiles", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  
  updateCreatorProfile: (id: string, data: Partial<CreatorProfile>) =>
    fetchAPI<CreatorProfile>(`/api/settings/creator-profiles/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  
  deleteCreatorProfile: (id: string) =>
    fetchAPI<unknown>(`/api/settings/creator-profiles/${id}`, { method: "DELETE" }),
  
  // Field Templates
  listFieldTemplates: () =>
    fetchAPI<FieldTemplateItem[]>("/api/settings/field-templates"),
  
  createFieldTemplate: (data: unknown) =>
    fetchAPI<unknown>("/api/settings/field-templates", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  
  updateFieldTemplate: (id: string, data: unknown) =>
    fetchAPI<unknown>(`/api/settings/field-templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  
  deleteFieldTemplate: (id: string) =>
    fetchAPI<unknown>(`/api/settings/field-templates/${id}`, { method: "DELETE" }),
  
  // Channels
  listChannels: () =>
    fetchAPI<ChannelItem[]>("/api/settings/channels"),
  
  createChannel: (data: unknown) =>
    fetchAPI<unknown>("/api/settings/channels", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  
  updateChannel: (id: string, data: unknown) =>
    fetchAPI<unknown>(`/api/settings/channels/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  
  deleteChannel: (id: string) =>
    fetchAPI<unknown>(`/api/settings/channels/${id}`, { method: "DELETE" }),
  
  // Simulators
  listSimulators: () =>
    fetchAPI<SimulatorItem[]>("/api/settings/simulators"),
  
  createSimulator: (data: unknown) =>
    fetchAPI<unknown>("/api/settings/simulators", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  
  updateSimulator: (id: string, data: unknown) =>
    fetchAPI<unknown>(`/api/settings/simulators/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  
  deleteSimulator: (id: string) =>
    fetchAPI<unknown>(`/api/settings/simulators/${id}`, { method: "DELETE" }),
  
  // Agent Settings
  getAgentSettings: () =>
    fetchAPI<AgentSettingsData>("/api/settings/agent"),
  
  updateAgentSettings: (data: unknown) =>
    fetchAPI<unknown>("/api/settings/agent", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  
  // Logs
  listLogs: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : "";
    return fetchAPI<SettingsLogItem[]>(`/api/settings/logs${query}`);
  },
  
  exportLogs: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : "";
    return fetchAPI<unknown>(`/api/settings/logs/export${query}`);
  },

  // System Prompts Import/Export
  exportSystemPrompts: (id?: string) => {
    const query = id ? `?id=${id}` : "";
    return fetchAPI<unknown>(`/api/settings/system-prompts/export${query}`);
  },
  importSystemPrompts: (data: unknown[]) =>
    fetchAPI<unknown>("/api/settings/system-prompts/import", {
      method: "POST",
      body: JSON.stringify({ data }),
    }),

  // Creator Profiles Import/Export
  exportCreatorProfiles: (id?: string) => {
    const query = id ? `?id=${id}` : "";
    return fetchAPI<unknown>(`/api/settings/creator-profiles/export${query}`);
  },
  importCreatorProfiles: (data: unknown[]) =>
    fetchAPI<unknown>("/api/settings/creator-profiles/import", {
      method: "POST",
      body: JSON.stringify({ data }),
    }),

  // Field Templates Import/Export
  exportFieldTemplates: (id?: string) => {
    const query = id ? `?id=${id}` : "";
    return fetchAPI<unknown>(`/api/settings/field-templates/export${query}`);
  },
  importFieldTemplates: (data: unknown[]) =>
    fetchAPI<unknown>("/api/settings/field-templates/import", {
      method: "POST",
      body: JSON.stringify({ data }),
    }),

  // Simulators Import/Export
  exportSimulators: (id?: string) => {
    const query = id ? `?id=${id}` : "";
    return fetchAPI<unknown>(`/api/settings/simulators/export${query}`);
  },
  importSimulators: (data: unknown[]) =>
    fetchAPI<unknown>("/api/settings/simulators/import", {
      method: "POST",
      body: JSON.stringify({ data }),
    }),

  // Graders
  listGraders: () =>
    fetchAPI<GraderData[]>("/api/graders"),
};

// ============== Simulation API ==============

export const simulationAPI = {
  // 获取项目的模拟记录列表
  list: (projectId: string) =>
    fetchAPI<SimulationRecord[]>(`/api/simulations/project/${projectId}`),
  
  // 获取模拟记录详情
  get: (id: string) =>
    fetchAPI<SimulationRecord>(`/api/simulations/${id}`),
  
  // 创建模拟记录
  create: (data: {
    project_id: string;
    simulator_id: string;
    target_field_ids: string[];
    persona: Persona;
  }) =>
    fetchAPI<SimulationRecord>("/api/simulations/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  
  // 运行模拟（启动模拟任务）
  run: (id: string) =>
    fetchAPI<SimulationRecord>(`/api/simulations/${id}/run`, { method: "POST" }),
  
  // 删除模拟记录
  delete: (id: string) =>
    fetchAPI<unknown>(`/api/simulations/${id}`, { method: "DELETE" }),
  
  // 获取消费者调研中的人物小传
  getPersonasFromResearch: (projectId: string) =>
    fetchAPI<PersonaFromResearch[]>(`/api/simulations/project/${projectId}/personas`),
};

// ============== Content Block Types (新架构) ==============

export interface ContentBlock {
  id: string;
  project_id: string;
  parent_id: string | null;
  name: string;
  block_type: "phase" | "field" | "proposal" | "group";
  depth?: number;
  order_index: number;
  content: string;
  status: "pending" | "in_progress" | "completed" | "failed";
  ai_prompt?: string;
  constraints?: Record<string, unknown>;
  depends_on?: string[];
  special_handler: string | null;
  pre_questions?: string[];
  pre_answers?: Record<string, string>;
  need_review?: boolean;
  is_collapsed?: boolean;
  children: ContentBlock[];
  created_at: string | null;
  updated_at: string | null;
  // 版本警告（当修改影响下游内容块时）
  version_warning?: string | null;
  affected_blocks?: string[] | null;
}

export interface BlockTree {
  project_id: string;
  blocks: ContentBlock[];
  total_count: number;
}

export interface PhaseTemplate {
  id: string;
  name: string;
  description: string;
  phases: Array<{
    name: string;
    block_type: string;
    special_handler: string | null;
    order_index: number;
    default_fields: Array<{
      name: string;
      block_type: string;
      ai_prompt?: string;
      content?: string;
      pre_questions?: string[];
      depends_on?: string[];
      constraints?: Record<string, unknown>;
      need_review?: boolean;
    }>;
  }>;
  is_default: boolean;
  is_system: boolean;
  created_at: string | null;
  updated_at: string | null;
}

// ============== Content Block API (新架构) ==============

export const blockAPI = {
  // 获取项目的所有内容块（树形结构）
  getProjectBlocks: (projectId: string) =>
    fetchAPI<BlockTree>(`/api/blocks/project/${projectId}`),

  // 获取单个内容块
  get: (blockId: string, includeChildren = false) =>
    fetchAPI<ContentBlock>(`/api/blocks/${blockId}?include_children=${includeChildren}`),

  // 创建内容块
  create: (data: {
    project_id: string;
    parent_id?: string | null;
    name: string;
    block_type?: string;
    content?: string;
    ai_prompt?: string;
    constraints?: Record<string, unknown>;
    depends_on?: string[];
    special_handler?: string | null;
    pre_questions?: string[];
    pre_answers?: Record<string, string>;
    need_review?: boolean;
    order_index?: number;
  }) =>
    fetchAPI<ContentBlock>("/api/blocks/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // 更新内容块
  update: (blockId: string, data: Partial<{
    name: string;
    content: string;
    status: string;
    ai_prompt: string;
    constraints: Record<string, unknown>;
    depends_on: string[];
    pre_questions: string[];
    pre_answers: Record<string, string>;
    need_review: boolean;
    is_collapsed: boolean;
  }>) =>
    fetchAPI<ContentBlock>(`/api/blocks/${blockId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // 删除内容块
  delete: (blockId: string) =>
    fetchAPI<{ message: string }>(`/api/blocks/${blockId}`, {
      method: "DELETE",
    }),

  // 深拷贝内容块（含所有子块）
  duplicate: (blockId: string) =>
    fetchAPI<ContentBlock>(`/api/blocks/${blockId}/duplicate`, {
      method: "POST",
    }),

  // 移动内容块
  move: (blockId: string, data: {
    new_parent_id: string | null;
    new_order_index: number;
  }) =>
    fetchAPI<ContentBlock>(`/api/blocks/${blockId}/move`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // 生成内容块内容
  generate: (blockId: string) =>
    fetchAPI<{
      block_id: string;
      content: string;
      status: string;
      tokens_in: number;
      tokens_out: number;
      cost: number;
    }>(`/api/blocks/${blockId}/generate`, {
      method: "POST",
    }),

  // 流式生成内容块内容（返回原始 Response 用于 SSE 读取）
  generateStream: async function (blockId: string, signal?: AbortSignal): Promise<Response> {
    const resp = await fetch(`${API_BASE}/api/blocks/${blockId}/generate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal,
    });
    return resp;
  },

  // 应用模板到项目
  applyTemplate: (projectId: string, templateId: string) =>
    fetchAPI<{ message: string; blocks_created: number }>(
      `/api/blocks/project/${projectId}/apply-template?template_id=${templateId}`,
      { method: "POST" }
    ),

  // 迁移传统项目到 content_blocks 架构
  migrateProject: (projectId: string) =>
    fetchAPI<{ message: string; phases_created: number; fields_migrated: number }>(
      `/api/blocks/project/${projectId}/migrate`,
      { method: "POST" }
    ),

  // 检查可自动触发的块（只返回 ID 列表，不做生成）
  checkAutoTriggers: (projectId: string) =>
    fetchAPI<{ eligible_ids: string[] }>(
      `/api/blocks/project/${projectId}/check-auto-triggers`,
      { method: "POST" }
    ),

  // 用户手动确认内容块 → 状态变为 completed
  confirm: (blockId: string) =>
    fetchAPI<ContentBlock>(`/api/blocks/${blockId}/confirm`, {
      method: "POST",
    }),

  // 撤销操作
  undo: (historyId: string) =>
    fetchAPI<{ message: string }>(`/api/blocks/undo/${historyId}`, {
      method: "POST",
    }),

  // AI 生成提示词
  generatePrompt: (data: { purpose: string; field_name?: string; project_id?: string }) =>
    fetchAPI<{ prompt: string; model: string; tokens_used: number }>(
      "/api/blocks/generate-prompt",
      {
        method: "POST",
        body: JSON.stringify(data),
      }
    ),
};

/**
 * 前端驱动的自动触发链：
 * 1. 调用 check-auto-triggers 获取可触发的块 ID
 * 2. 对所有 eligible 块 **并行** 调用 generateStream 进行生成
 * 3. 全部完成后递归检查是否解锁了新的下游块
 * 
 * 去重机制：全局锁防止多个调用方同时启动链条（如 progress-panel +
 * content-block-editor + content-block-card 都会在 onUpdate 时触发）。
 * 
 * @param projectId 项目 ID
 * @param onBlockUpdate 每次有块状态变化时的回调（刷新 UI）
 * @param maxDepth 最大递归深度（防止无限循环），默认 10
 */

// ===== 全局去重锁（按 projectId）=====
const _autoChainLocks = new Map<string, boolean>();

export async function runAutoTriggerChain(
  projectId: string,
  onBlockUpdate?: () => void,
  maxDepth: number = 10,
): Promise<string[]> {
  if (maxDepth <= 0) return [];

  // 去重：如果已经有一个链正在运行，跳过
  if (_autoChainLocks.get(projectId)) {
    console.log(`[AUTO-CHAIN] Already running for project ${projectId}, skipping`);
    return [];
  }
  _autoChainLocks.set(projectId, true);

  try {
    return await _runAutoTriggerChainInner(projectId, onBlockUpdate, maxDepth);
  } finally {
    _autoChainLocks.set(projectId, false);
  }
}

async function _runAutoTriggerChainInner(
  projectId: string,
  onBlockUpdate?: () => void,
  maxDepth: number = 10,
): Promise<string[]> {
  if (maxDepth <= 0) return [];

  const result = await blockAPI.checkAutoTriggers(projectId);
  const eligibleIds = result.eligible_ids || [];
  if (eligibleIds.length === 0) return [];

  console.log(`[AUTO-CHAIN] Found ${eligibleIds.length} eligible blocks, generating in PARALLEL...`);

  // ===== 关键改动：并行生成所有 eligible 块 =====
  const promises = eligibleIds.map((blockId) => _generateSingleBlock(blockId));
  const results = await Promise.allSettled(promises);

  const allTriggered: string[] = [];
  for (let i = 0; i < results.length; i++) {
    const r = results[i];
    if (r.status === "fulfilled" && r.value) {
      allTriggered.push(eligibleIds[i]);
    } else if (r.status === "rejected") {
      console.error(`[AUTO-CHAIN] Error generating block ${eligibleIds[i]}:`, r.reason);
    }
  }

  // 所有并行块完成后刷新一次 UI
  if (allTriggered.length > 0) {
    onBlockUpdate?.();
  }

  // 递归：刚完成的块可能解锁了新的下游块
  if (allTriggered.length > 0) {
    const moreTriggered = await _runAutoTriggerChainInner(projectId, onBlockUpdate, maxDepth - 1);
    allTriggered.push(...moreTriggered);
  }

  return allTriggered;
}

/** 生成单个块并读完 SSE 流，返回是否成功 */
async function _generateSingleBlock(blockId: string): Promise<boolean> {
  const { readSSEStream } = await import("@/lib/sse");

  console.log(`[AUTO-CHAIN] Generating block ${blockId}...`);
  const resp = await blockAPI.generateStream(blockId);

  if (!resp.ok) {
    console.error(`[AUTO-CHAIN] Generate failed for ${blockId}: ${resp.status}`);
    return false;
  }

  let success = false;
  for await (const data of readSSEStream(resp)) {
    if (data.done) {
      console.log(`[AUTO-CHAIN] Block ${blockId} completed`);
      success = true;
    }
  }
  return success;
}

// ============== Phase Template API (新架构) ==============

export const phaseTemplateAPI = {
  // 获取所有模板
  list: () =>
    fetchAPI<PhaseTemplate[]>("/api/phase-templates/"),

  // 获取单个模板
  get: (templateId: string) =>
    fetchAPI<PhaseTemplate>(`/api/phase-templates/${templateId}`),

  // 创建模板
  create: (data: {
    name: string;
    description?: string;
    phases: PhaseTemplate["phases"];
  }) =>
    fetchAPI<PhaseTemplate>("/api/phase-templates/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // 更新模板
  update: (templateId: string, data: Partial<{
    name: string;
    description: string;
    phases: PhaseTemplate["phases"];
  }>) =>
    fetchAPI<PhaseTemplate>(`/api/phase-templates/${templateId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // 删除模板
  delete: (templateId: string) =>
    fetchAPI<{ message: string }>(`/api/phase-templates/${templateId}`, {
      method: "DELETE",
    }),

  // 复制模板
  duplicate: (templateId: string, newName?: string) =>
    fetchAPI<PhaseTemplate>(
      `/api/phase-templates/${templateId}/duplicate${newName ? `?new_name=${encodeURIComponent(newName)}` : ""}`,
      { method: "POST" }
    ),
};

// ============== Eval V2 API ==============

export interface EvalRun {
  id: string;
  project_id: string;
  name: string;
  status: string;
  summary: string;
  overall_score: number | null;
  role_scores: Record<string, number>;
  trial_count: number;
  content_block_id: string | null;
  config: Record<string, unknown>;
  created_at: string;
}

export interface EvalTask {
  id: string;
  eval_run_id: string;
  name: string;
  simulator_type: string;
  interaction_mode: string;
  simulator_config: Record<string, unknown>;
  persona_config: Record<string, unknown>;
  target_block_ids: string[];
  grader_config: Record<string, unknown>;
  order_index: number;
  status: string;
  error: string;
  created_at: string;
}

export interface LLMCall {
  step: string;
  input: { system_prompt: string; user_message: string };
  output: string;
  tokens_in: number;
  tokens_out: number;
  cost: number;
  duration_ms: number;
  timestamp: string;
}

export interface EvalTrial {
  id: string;
  eval_run_id: string;
  eval_task_id: string | null;
  role: string;
  role_config: Record<string, unknown>;
  interaction_mode: string;
  input_block_ids: string[];
  persona: Record<string, unknown>;
  nodes: Array<{ role: string; content: string; turn?: number; phase?: string }>;
  result: Record<string, unknown>;
  grader_outputs: unknown[];
  llm_calls: LLMCall[];
  overall_score: number | null;
  status: string;
  error: string;
  tokens_in: number;
  tokens_out: number;
  cost: number;
  created_at: string;
}

// Eval config types (from /api/eval/config)
export interface SimulatorTypeInfo {
  name: string;
  icon: string;
  description: string;
  default_interaction: string;
  default_dimensions: string[];
  system_prompt: string;
}

export interface EvalConfig {
  simulator_types: Record<string, SimulatorTypeInfo>;
  interaction_modes: Record<string, { name: string; description: string }>;
  grader_types: Record<string, { name: string; description: string }>;
  roles: Record<string, unknown>;
}

export const evalAPI = {
  // Config
  getConfig: (): Promise<EvalConfig> => fetchAPI("/api/eval/config"),
  getPersonas: (projectId: string) => fetchAPI("/api/eval/personas/" + projectId),
  generatePersona: (projectId: string, avoidNames: string[] = []) =>
    fetchAPI<{ persona: { name: string; prompt: string } }>("/api/eval/personas/generate", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, avoid_names: avoidNames }),
    }),
  generatePrompt: (promptType: string, context: Record<string, unknown> = {}) =>
    fetchAPI<{ generated_prompt: string }>("/api/eval/prompts/generate", {
      method: "POST",
      body: JSON.stringify({ prompt_type: promptType, context }),
    }),

  // Generate for ContentBlock
  generateForBlock: (blockId: string) =>
    fetchAPI("/api/eval/generate-for-block/" + blockId, { method: "POST" }),
};

// ============== Eval V2 (Task 容器 + TrialConfig) API ==============

export interface EvalV2TrialConfig {
  id?: string;
  name: string;
  form_type: "assessment" | "review" | "experience" | "scenario";
  target_block_ids: string[];
  grader_ids: string[];
  grader_weights?: Record<string, number>;
  repeat_count: number;
  probe?: string;
  form_config?: Record<string, unknown>;
  order_index?: number;
}

export interface EvalV2Task {
  id: string;
  project_id: string;
  name: string;
  description: string;
  order_index: number;
  status: string;
  content_hash: string;
  last_executed_at: string;
  latest_scores: Record<string, unknown>;
  latest_overall: number | null;
  latest_batch_id: string;
  progress?: {
    total: number;
    completed: number;
    percent: number;
    is_running: boolean;
    is_paused?: boolean;
    pause_requested?: boolean;
    stop_requested: boolean;
    batch_id?: string;
  };
  can_stop?: boolean;
  trial_configs: EvalV2TrialConfig[];
}

export interface EvalV2ExecutionRow {
  task_id: string;
  batch_id: string;
  task_name: string;
  overall?: number | null;
  status?: string;
  trial_count?: number | null;
  executed_at?: string;
}

export interface EvalV2TrialDetail {
  id: string;
  trial_config_name?: string;
  form_type: string;
  repeat_index: number;
  overall_score?: number | null;
  status?: string;
  llm_calls?: Array<{
    step?: string;
    tokens_in?: number;
    tokens_out?: number;
    cost?: number;
    input?: { system_prompt?: string; user_message?: string };
    output?: unknown;
  }>;
  dimension_scores?: Record<string, number | null | undefined>;
  overall_comment?: string;
  score_evidence?: Array<{
    grader_name?: string;
    dimension?: string;
    score?: number | string | null;
    evidence?: string;
  }>;
  grader_results?: Array<{ grader_name?: string; feedback?: string }>;
  improvement_suggestions?: string[];
  process?: Array<{
    type?: string;
    stage?: string;
    role?: string;
    content?: string;
    block_id?: string;
    block_title?: string;
    data?: unknown;
  }>;
}

export interface EvalV2TaskBatchDetail {
  trials?: EvalV2TrialDetail[];
}

export interface EvalV2DiagnosisResponse {
  analysis?: {
    patterns?: Array<{ title?: string; frequency?: string }>;
    suggestions?: Array<{ title?: string; detail?: string }>;
  } | null;
}

export const evalV2API = {
  listTasks: (projectId: string) =>
    fetchAPI<{ tasks: EvalV2Task[] }>(`/api/eval/tasks/${projectId}`),
  createTask: (projectId: string, data: {
    name: string;
    description?: string;
    order_index?: number;
    trial_configs: EvalV2TrialConfig[];
  }) =>
    fetchAPI<EvalV2Task>(`/api/eval/tasks/${projectId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateTask: (taskId: string, data: {
    name?: string;
    description?: string;
    order_index?: number;
    trial_configs?: EvalV2TrialConfig[];
  }) =>
    fetchAPI<EvalV2Task>(`/api/eval/task/${taskId}/v2`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteTask: (taskId: string) =>
    fetchAPI<{ message: string }>(`/api/eval/task/${taskId}`, { method: "DELETE" }),
  executeTask: (taskId: string) =>
    fetchAPI<{ message?: string }>(`/api/eval/task/${taskId}/execute`, { method: "POST" }),
  startTask: (taskId: string) =>
    fetchAPI<{ message?: string }>(`/api/eval/task/${taskId}/start`, { method: "POST" }),
  stopTask: (taskId: string) =>
    fetchAPI<{ message?: string }>(`/api/eval/task/${taskId}/stop`, { method: "POST" }),
  pauseTask: (taskId: string) =>
    fetchAPI<{ message?: string }>(`/api/eval/task/${taskId}/pause`, { method: "POST" }),
  resumeTask: (taskId: string) =>
    fetchAPI<{ message?: string }>(`/api/eval/task/${taskId}/resume`, { method: "POST" }),
  executeAll: (projectId: string) =>
    fetchAPI<{ message?: string }>(`/api/eval/tasks/${projectId}/execute-all`, { method: "POST" }),
  taskTrials: (taskId: string) =>
    fetchAPI<{ trials: EvalV2TrialDetail[] }>(`/api/eval/task/${taskId}/trials`),
  taskLatest: (taskId: string) =>
    fetchAPI<unknown>(`/api/eval/task/${taskId}/latest`),
  taskReport: (projectId: string) =>
    fetchAPI<{ tasks: unknown[] }>(`/api/eval/tasks/${projectId}/report`),
  executionReport: (projectId: string) =>
    fetchAPI<{ executions: EvalV2ExecutionRow[] }>(`/api/eval/tasks/${projectId}/executions`),
  runTaskDiagnosis: (taskId: string) =>
    fetchAPI<EvalV2DiagnosisResponse>(`/api/eval/task/${taskId}/diagnose`, { method: "POST" }),
  runTaskDiagnosisForBatch: (taskId: string, batchId: string) =>
    fetchAPI<EvalV2DiagnosisResponse>(`/api/eval/task/${taskId}/diagnose?batch_id=${encodeURIComponent(batchId)}`, { method: "POST" }),
  getTaskDiagnosis: (taskId: string, batchId?: string) =>
    fetchAPI<EvalV2DiagnosisResponse>(`/api/eval/task/${taskId}/diagnosis${batchId ? `?batch_id=${encodeURIComponent(batchId)}` : ""}`),
  taskBatch: (taskId: string, batchId: string) =>
    fetchAPI<EvalV2TaskBatchDetail>(`/api/eval/task/${taskId}/batch/${batchId}`),
  deleteTaskBatch: (taskId: string, batchId: string) =>
    fetchAPI<unknown>(`/api/eval/task/${taskId}/batch/${batchId}`, { method: "DELETE" }),
  batchDeleteExecutions: (projectId: string, items: Array<{ task_id: string; batch_id: string }>) =>
    fetchAPI<unknown>(`/api/eval/tasks/${projectId}/executions/delete`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
  getSuggestionStates: (taskId: string, batchId: string) =>
    fetchAPI<{ states: Array<{ source: string; suggestion: string; suggestion_hash: string; status: string }> }>(
      `/api/eval/task/${taskId}/batch/${batchId}/suggestion-states`
    ),
  markSuggestionApplied: (taskId: string, batchId: string, payload: { source: string; suggestion: string; status?: string }) =>
    fetchAPI<unknown>(`/api/eval/task/${taskId}/batch/${batchId}/suggestion-state`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  providerTest: () =>
    fetchAPI<unknown>("/api/eval/provider/test", { method: "POST" }),
};


// ============== Grader (评分器) ==============

export interface GraderData {
  id: string;
  name: string;
  grader_type: string;      // "content_only" | "content_and_process"
  prompt_template: string;
  dimensions: string[];
  scoring_criteria: Record<string, string>;
  is_preset: boolean;
  project_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export const graderAPI = {
  list: (): Promise<GraderData[]> => fetchAPI("/api/graders"),
  listForProject: (projectId: string): Promise<GraderData[]> =>
    fetchAPI(`/api/graders/project/${projectId}`),
  get: (graderId: string): Promise<GraderData> =>
    fetchAPI(`/api/graders/${graderId}`),
  create: (data: Partial<GraderData>): Promise<GraderData> =>
    fetchAPI("/api/graders", { method: "POST", body: JSON.stringify(data) }),
  update: (graderId: string, data: Partial<GraderData>): Promise<GraderData> =>
    fetchAPI(`/api/graders/${graderId}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (graderId: string) =>
    fetchAPI(`/api/graders/${graderId}`, { method: "DELETE" }),
  getTypes: () => fetchAPI("/api/graders/types"),
  exportAll: (id?: string) => {
    const query = id ? `?grader_id=${id}` : "";
    return fetchAPI<unknown>(`/api/graders/export/all${query}`);
  },
  importAll: (data: unknown[]) =>
    fetchAPI<unknown>("/api/graders/import/all", {
      method: "POST",
      body: JSON.stringify({ data }),
    }),
};


// ============== Version History API ==============

export interface VersionItem {
  id: string;
  version_number: number;
  content: string;
  source: string;
  source_detail: string | null;
  created_at: string;
}

export interface VersionListResponse {
  entity_id: string;
  entity_name: string;
  entity_type: string;
  current_content: string;
  versions: VersionItem[];
}

export interface RollbackResponse {
  success: boolean;
  entity_id: string;
  restored_version: number;
  message: string;
}

export const versionAPI = {
  list: (entityId: string) =>
    fetchAPI<VersionListResponse>(`/api/versions/${entityId}`),

  rollback: (entityId: string, versionId: string) =>
    fetchAPI<RollbackResponse>(`/api/versions/${entityId}/rollback/${versionId}`, {
      method: "POST",
    }),
};


// ============== Agent Mode Types & API ==============

export interface AgentModeInfo {
  id: string;
  name: string;
  display_name: string;
  description: string;
  system_prompt: string;
  icon: string;
  is_system: boolean;
  sort_order: number;
}

export const modesAPI = {
  list: () => fetchAPI<AgentModeInfo[]>("/api/modes/"),
  get: (id: string) => fetchAPI<AgentModeInfo>(`/api/modes/${id}`),
  create: (data: {
    name: string;
    display_name: string;
    description: string;
    system_prompt: string;
    icon: string;
    sort_order?: number;
  }) =>
    fetchAPI<AgentModeInfo>("/api/modes/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<AgentModeInfo>) =>
    fetchAPI<AgentModeInfo>(`/api/modes/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    fetchAPI<{ message: string }>(`/api/modes/${id}`, { method: "DELETE" }),
};

// ============== Memory Types & API ==============

export interface MemoryItemInfo {
  id: string;
  project_id: string;
  content: string;
  source_mode: string;
  source_phase: string;
  related_blocks: string[];
  created_at: string;
  updated_at: string;
}

export const memoriesAPI = {
  list: (projectId: string, includeGlobal: boolean = true) =>
    fetchAPI<MemoryItemInfo[]>(`/api/memories/${projectId}${includeGlobal ? "?include_global=true" : ""}`),

  get: (projectId: string, memoryId: string) =>
    fetchAPI<MemoryItemInfo>(`/api/memories/${projectId}/${memoryId}`),

  create: (projectId: string, data: {
    content: string;
    source_mode?: string;
    source_phase?: string;
    related_blocks?: string[];
  }) =>
    fetchAPI<MemoryItemInfo>(`/api/memories/${projectId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (projectId: string, memoryId: string, data: {
    content?: string;
    related_blocks?: string[];
  }) =>
    fetchAPI<MemoryItemInfo>(`/api/memories/${projectId}/${memoryId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (projectId: string, memoryId: string) =>
    fetchAPI<{ message: string }>(`/api/memories/${projectId}/${memoryId}`, {
      method: "DELETE",
    }),
};

// ============== Utilities ==============

/**
 * 解析消息中的 @引用，支持含空格的内容块名
 *
 * 策略：优先按已知字段名贪婪匹配（最长优先），兼容未知名称的基础正则
 *
 * 例如:
 *   knownFieldNames = ["Eval test", "逐字稿1", "逐字稿2"]
 *   parseReferences("参考 @Eval test 修改 @逐字稿2", knownFieldNames)
 *   => ["Eval test", "逐字稿2"]  （保持在原文中出现的顺序）
 */
export function parseReferences(message: string, knownFieldNames?: string[]): string[] {
  if (!knownFieldNames || knownFieldNames.length === 0) {
    // 无已知字段名时回退到简单正则（不支持空格）
    const pattern = /@([^\s@]+)/g;
    const matches: string[] = [];
    let match;
    while ((match = pattern.exec(message)) !== null) {
      matches.push(match[1]);
    }
    return matches;
  }

  // 按长度降序排列，确保最长名称优先匹配（如 "Eval test" 优先于 "Eval"）
  const sorted = [...knownFieldNames].sort((a, b) => b.length - a.length);
  const found: { name: string; index: number }[] = [];
  const usedRanges: [number, number][] = [];

  for (let i = 0; i < message.length; i++) {
    if (message[i] !== "@") continue;
    // 跳过已被更长匹配覆盖的位置
    if (usedRanges.some(([s, e]) => i >= s && i < e)) continue;

    const afterAt = message.slice(i + 1);

    // 尝试匹配已知字段名（最长优先）
    let matched = false;
    for (const name of sorted) {
      if (afterAt.startsWith(name)) {
        // 检查边界：名称后应是空白、标点、另一个@、或字符串结尾
        const charAfter = afterAt[name.length];
        if (!charAfter || /[\s，。！？、：；""''（）@\n]/.test(charAfter)) {
          found.push({ name, index: i });
          usedRanges.push([i, i + 1 + name.length]);
          matched = true;
          break;
        }
      }
    }

    // 未匹配已知名称时回退到简单正则（至空白/@停止）
    if (!matched) {
      const fallback = afterAt.match(/^([^\s@]+)/);
      if (fallback) {
        found.push({ name: fallback[1], index: i });
        usedRanges.push([i, i + 1 + fallback[1].length]);
      }
    }
  }

  // 按在原文中的出现顺序返回
  found.sort((a, b) => a.index - b.index);
  return found.map((m) => m.name);
}
