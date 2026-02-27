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
  agent_autonomy: Record<string, boolean>;
  golden_context: Record<string, string>;
  use_deep_research: boolean;
  created_at: string;
  updated_at: string;
}

export interface FieldConstraints {
  max_length?: number | null;      // 最大字数
  output_format?: string;           // 输出格式: markdown / plain_text / json / list
  structure?: string | null;        // 结构模板
  example?: string | null;          // 示例输出
}

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
  constraints?: FieldConstraints;   // 字段生产约束
  need_review: boolean;             // 是否需要人工确认（false = 自动生成）
  template_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreatorProfile {
  id: string;
  name: string;
  description: string;
  traits: Record<string, any>;
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
    tool_used?: string;
    skill_used?: string;
    references?: string[];
    is_retry?: boolean;
    suggestion_cards?: any[];
    [key: string]: any;
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
  interaction_log: any[];
  feedback: {
    scores: Record<string, number>;
    comments: Record<string, string>;
    overall: string;
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
      errorMessage = error.detail.map((e: any) => e.msg || e.message || JSON.stringify(e)).join("; ");
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

  exportProject: (id: string, includeVersions: boolean = false) =>
    fetchAPI<any>(`/api/projects/${id}/export${includeVersions ? "?include_versions=true" : ""}`),

  importProject: (data: any, asNew: boolean = true) =>
    fetchAPI<any>("/api/projects/import", {
      method: "POST",
      body: JSON.stringify({ data, as_new: asNew }),
    }),

  search: (projectId: string, query: string, caseSensitive: boolean = false) =>
    fetchAPI<{ results: SearchResult[]; total_matches: number }>(`/api/projects/${projectId}/search`, {
      method: "POST",
      body: JSON.stringify({ query, case_sensitive: caseSensitive }),
    }),

  replace: (projectId: string, query: string, replacement: string, options?: {
    caseSensitive?: boolean;
    targets?: { type: string; id: string; indices?: number[] }[];
  }) =>
    fetchAPI<{ replaced_count: number; affected_items: any[] }>(`/api/projects/${projectId}/replace`, {
      method: "POST",
      body: JSON.stringify({
        query,
        replacement,
        case_sensitive: options?.caseSensitive || false,
        targets: options?.targets,
      }),
    }),
};

// ============== Field API ==============

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
    currentPhase?: string
  ): AsyncGenerator<{ node?: string; content?: string; done?: boolean; error?: string }> {
    const response = await fetch(`${API_BASE}/api/agent/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        message,
        current_phase: currentPhase,
      }),
    });

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) return;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const text = decoder.decode(value);
      const lines = text.split("\n");

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            yield data;
          } catch {
            // Ignore parse errors
          }
        }
      }
    }
  },

  // 获取对话历史
  getHistory: (projectId: string, limit: number = 100) =>
    fetchAPI<ChatMessageRecord[]>(`/api/agent/history/${projectId}?limit=${limit}`),
  
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
    fetchAPI<any>(`/api/agent/message/${messageId}`, { method: "DELETE" }),
  
  // 调用Tool
  callTool: (projectId: string, toolName: string, parameters: Record<string, any> = {}) =>
    fetchAPI<ChatResponse>("/api/agent/tool", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        tool_name: toolName,
        parameters,
      }),
    }),

  // 会话管理
  listConversations: (projectId: string, mode: string = "assistant") =>
    fetchAPI<ConversationRecord[]>(`/api/agent/conversations?project_id=${projectId}&mode=${mode}`),

  createConversation: (data: { project_id: string; mode?: string; title?: string; bootstrap_policy?: string }) =>
    fetchAPI<ConversationRecord>("/api/agent/conversations", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getConversationMessages: (conversationId: string, limit: number = 200) =>
    fetchAPI<ChatMessageRecord[]>(`/api/agent/conversations/${conversationId}/messages?limit=${limit}`),

  // Inline AI 编辑
  inlineEdit: (data: { text: string; operation: string; context?: string; project_id?: string }) =>
    fetchAPI<{ original: string; replacement: string; diff_preview: string }>("/api/agent/inline-edit", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ============== Settings API ==============

export const settingsAPI = {
  // System Prompts
  listSystemPrompts: () =>
    fetchAPI<any[]>("/api/settings/system-prompts"),
  
  updateSystemPrompt: (id: string, data: any) =>
    fetchAPI<any>(`/api/settings/system-prompts/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

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
    fetchAPI<any>(`/api/settings/creator-profiles/${id}`, { method: "DELETE" }),
  
  // Field Templates
  listFieldTemplates: () =>
    fetchAPI<any[]>("/api/settings/field-templates"),
  
  createFieldTemplate: (data: any) =>
    fetchAPI<any>("/api/settings/field-templates", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  
  updateFieldTemplate: (id: string, data: any) =>
    fetchAPI<any>(`/api/settings/field-templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  
  deleteFieldTemplate: (id: string) =>
    fetchAPI<any>(`/api/settings/field-templates/${id}`, { method: "DELETE" }),
  
  // Channels
  listChannels: () =>
    fetchAPI<any[]>("/api/settings/channels"),
  
  createChannel: (data: any) =>
    fetchAPI<any>("/api/settings/channels", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  
  updateChannel: (id: string, data: any) =>
    fetchAPI<any>(`/api/settings/channels/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  
  deleteChannel: (id: string) =>
    fetchAPI<any>(`/api/settings/channels/${id}`, { method: "DELETE" }),
  
  // Simulators
  listSimulators: () =>
    fetchAPI<any[]>("/api/settings/simulators"),
  
  createSimulator: (data: any) =>
    fetchAPI<any>("/api/settings/simulators", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  
  updateSimulator: (id: string, data: any) =>
    fetchAPI<any>(`/api/settings/simulators/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  
  deleteSimulator: (id: string) =>
    fetchAPI<any>(`/api/settings/simulators/${id}`, { method: "DELETE" }),
  
  // Agent Settings
  getAgentSettings: () =>
    fetchAPI<any>("/api/settings/agent"),
  
  updateAgentSettings: (data: any) =>
    fetchAPI<any>("/api/settings/agent", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  
  // Logs
  listLogs: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : "";
    return fetchAPI<any[]>(`/api/settings/logs${query}`);
  },
  
  exportLogs: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : "";
    return fetchAPI<any>(`/api/settings/logs/export${query}`);
  },

  // Eval Prompts
  listEvalPrompts: () =>
    fetchAPI<any[]>("/api/settings/eval-prompts"),

  updateEvalPrompt: (id: string, data: any) =>
    fetchAPI<any>(`/api/settings/eval-prompts/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Eval 预置同步
  syncEvalPresets: () =>
    fetchAPI<{
      imported_graders: number;
      updated_graders: number;
      imported_simulators: number;
      updated_simulators: number;
    }>("/api/settings/eval-presets/sync", {
      method: "POST",
    }),

  // Field Templates 导入/导出
  exportFieldTemplates: (templateId?: string) => {
    const query = templateId ? `?template_id=${templateId}` : "";
    return fetchAPI<any>(`/api/settings/field-templates/export${query}`);
  },
  importFieldTemplates: (data: any) =>
    fetchAPI<any>("/api/settings/field-templates/import", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Creator Profiles 导入/导出
  exportCreatorProfiles: (profileId?: string) => {
    const query = profileId ? `?profile_id=${profileId}` : "";
    return fetchAPI<any>(`/api/settings/creator-profiles/export${query}`);
  },
  importCreatorProfiles: (data: any) =>
    fetchAPI<any>("/api/settings/creator-profiles/import", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Simulators 导入/导出
  exportSimulators: (simulatorId?: string) => {
    const query = simulatorId ? `?simulator_id=${simulatorId}` : "";
    return fetchAPI<any>(`/api/settings/simulators/export${query}`);
  },
  importSimulators: (data: any) =>
    fetchAPI<any>("/api/settings/simulators/import", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // System Prompts 导入/导出
  exportSystemPrompts: (promptId?: string) => {
    const query = promptId ? `?prompt_id=${promptId}` : "";
    return fetchAPI<any>(`/api/settings/system-prompts/export${query}`);
  },
  importSystemPrompts: (data: any) =>
    fetchAPI<any>("/api/settings/system-prompts/import", {
      method: "POST",
      body: JSON.stringify(data),
    }),
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
    fetchAPI<any>(`/api/simulations/${id}`, { method: "DELETE" }),
  
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
  depth: number;
  order_index: number;
  content: string;
  status: "pending" | "in_progress" | "completed" | "failed";
  ai_prompt: string;
  constraints: FieldConstraints;
  pre_questions?: string[];
  pre_answers?: Record<string, string>;
  depends_on: string[];
  special_handler: string | null;
  need_review: boolean;
  auto_generate: boolean;  // 是否自动生成（依赖就绪时自动触发）
  is_collapsed: boolean;
  model_override?: string | null;
  children: ContentBlock[];
  created_at: string | null;
  updated_at: string | null;
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
      need_review?: boolean;
      auto_generate?: boolean;
      model_override?: string | null;
      pre_questions?: string[];
      depends_on?: string[];
      constraints?: Record<string, unknown>;
      [key: string]: unknown;  // 允许模板中的其他自定义字段
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
    constraints?: FieldConstraints;
    depends_on?: string[];
    special_handler?: string | null;
    need_review?: boolean;
    auto_generate?: boolean;
    pre_questions?: string[];
    pre_answers?: Record<string, string>;
    model_override?: string | null;
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
    constraints: FieldConstraints;
    depends_on: string[];
    pre_questions: string[];
    pre_answers: Record<string, string>;
    need_review: boolean;
    auto_generate: boolean;
    is_collapsed: boolean;
    model_override: string | null;
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
  generateStream: (blockId: string, signal?: AbortSignal): Promise<Response> =>
    fetch(`${API_BASE}/api/blocks/${blockId}/generate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal,
    }),

  // 确认内容块（need_review 流程中用户手动确认）
  confirm: (blockId: string) =>
    fetchAPI<ContentBlock>(`/api/blocks/${blockId}/confirm`, {
      method: "POST",
    }),

  // 撤回删除
  undo: (historyId: string) =>
    fetchAPI<any>(`/api/blocks/undo/${historyId}`, {
      method: "POST",
    }),

  // AI 生成提示词
  generatePrompt: (data: { purpose: string; field_name?: string; project_id?: string }) =>
    fetchAPI<{ prompt: string }>("/api/blocks/generate-prompt", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // 应用模板到项目
  applyTemplate: (projectId: string, templateId: string) =>
    fetchAPI<{ message: string; blocks_created: number }>(
      `/api/blocks/project/${projectId}/apply-template?template_id=${templateId}`,
      { method: "POST" }
    ),

  // 复制内容块
  duplicate: (blockId: string) =>
    fetchAPI<ContentBlock>(`/api/blocks/${blockId}/duplicate`, {
      method: "POST",
    }),

  // 迁移传统项目到 content_blocks 架构
  migrateProject: (projectId: string) =>
    fetchAPI<{ message: string; phases_created: number; fields_migrated: number }>(
      `/api/blocks/project/${projectId}/migrate`,
      { method: "POST" }
    ),
};

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

// ============== Grader Types & API ==============

export interface GraderData {
  id: string;
  name: string;
  grader_type: string;
  prompt_template: string;
  dimensions: any[];
  scoring_criteria: Record<string, any>;
  is_preset: boolean;
  project_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export const graderAPI = {
  list: () =>
    fetchAPI<GraderData[]>("/api/graders"),

  get: (id: string) =>
    fetchAPI<GraderData>(`/api/graders/${id}`),

  create: (data: Partial<GraderData>) =>
    fetchAPI<GraderData>("/api/graders", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: string, data: Partial<GraderData>) =>
    fetchAPI<GraderData>(`/api/graders/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    fetchAPI<{ ok: boolean; deleted: string }>(`/api/graders/${id}`, {
      method: "DELETE",
    }),

  listForProject: (projectId: string) =>
    fetchAPI<GraderData[]>(`/api/graders/project/${projectId}`),

  exportAll: (graderId?: string) => {
    const query = graderId ? `?grader_id=${graderId}` : "";
    return fetchAPI<{ type: string; data: any[]; count: number }>(`/api/graders/export/all${query}`);
  },

  importAll: (data: any[]) =>
    fetchAPI<{ message: string; imported: number; updated: number }>("/api/graders/import/all", {
      method: "POST",
      body: JSON.stringify({ data }),
    }),
};

// ============== Eval API ==============

export const evalAPI = {
  // 人物画像
  getPersonas: (projectId: string) =>
    fetchAPI<{ personas: any[] }>(`/api/eval/personas/${projectId}`),

  generatePersona: (projectId: string, avoidNames: string[]) =>
    fetchAPI<{ persona: any }>("/api/eval/personas/generate", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, avoid_names: avoidNames }),
    }),

  // 提示词生成
  generatePrompt: (promptType: string, data: { form_type: string; description: string }) =>
    fetchAPI<{ generated_prompt: string }>("/api/eval/prompts/generate", {
      method: "POST",
      body: JSON.stringify({ prompt_type: promptType, ...data }),
    }),

  // 为内容块生成评估
  generateForBlock: (blockId: string) =>
    fetchAPI<any>(`/api/eval/generate-for-block/${blockId}`, {
      method: "POST",
    }),
};

// ============== Eval V2 API ==============

export interface EvalV2TrialConfig {
  id?: string;
  name: string;
  form_type: string;
  target_block_ids: string[];
  grader_ids: string[];
  grader_weights: Record<string, number>;
  repeat_count: number;
  probe: string;
  form_config: Record<string, any>;
  order_index: number;
}

export interface EvalV2Task {
  id: string;
  project_id: string;
  name: string;
  description: string;
  order_index: number;
  status: string;
  last_error: string;
  content_hash: string;
  last_executed_at: string;
  latest_scores: Record<string, any>;
  latest_overall: number | null;
  latest_batch_id: string;
  progress: Record<string, any>;
  can_stop: boolean;
  can_pause: boolean;
  can_resume: boolean;
  trial_configs: EvalV2TrialConfig[];
}

export const evalV2API = {
  listTasks: (projectId: string) =>
    fetchAPI<{ tasks: EvalV2Task[] }>(`/api/eval/tasks/${projectId}`),

  createTask: (projectId: string, data: Partial<EvalV2Task>) =>
    fetchAPI<EvalV2Task>(`/api/eval/tasks/${projectId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateTask: (taskId: string, data: Partial<EvalV2Task>) =>
    fetchAPI<EvalV2Task>(`/api/eval/task/${taskId}/v2`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteTask: (taskId: string) =>
    fetchAPI<any>(`/api/eval/task/${taskId}`, {
      method: "DELETE",
    }),

  startTask: (taskId: string) =>
    fetchAPI<any>(`/api/eval/task/${taskId}/start`, {
      method: "POST",
    }),

  pauseTask: (taskId: string) =>
    fetchAPI<any>(`/api/eval/task/${taskId}/pause`, {
      method: "POST",
    }),

  resumeTask: (taskId: string) =>
    fetchAPI<any>(`/api/eval/task/${taskId}/resume`, {
      method: "POST",
    }),

  stopTask: (taskId: string) =>
    fetchAPI<any>(`/api/eval/task/${taskId}/stop`, {
      method: "POST",
    }),

  executeAll: (projectId: string) =>
    fetchAPI<any>(`/api/eval/tasks/${projectId}/execute-all`, {
      method: "POST",
    }),

  executionReport: (projectId: string) =>
    fetchAPI<{ executions: any[] }>(`/api/eval/tasks/${projectId}/executions`),

  taskBatch: (taskId: string, batchId: string) =>
    fetchAPI<any>(`/api/eval/task/${taskId}/batch/${batchId}`),

  deleteTaskBatch: (taskId: string, batchId: string) =>
    fetchAPI<any>(`/api/eval/task/${taskId}/batch/${batchId}`, {
      method: "DELETE",
    }),

  batchDeleteExecutions: (projectId: string, items: { task_id: string; batch_id: string }[]) =>
    fetchAPI<any>(`/api/eval/tasks/${projectId}/executions/delete`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),

  getTaskDiagnosis: (taskId: string, batchId?: string) => {
    const query = batchId ? `?batch_id=${batchId}` : "";
    return fetchAPI<{ analysis: any }>(`/api/eval/task/${taskId}/diagnosis${query}`);
  },

  runTaskDiagnosisForBatch: (taskId: string, batchId: string) =>
    fetchAPI<{ analysis: any }>(`/api/eval/task/${taskId}/diagnose`, {
      method: "POST",
      body: JSON.stringify({ batch_id: batchId }),
    }),

  getSuggestionStates: (taskId: string, batchId: string) =>
    fetchAPI<{ states: any[] }>(`/api/eval/task/${taskId}/batch/${batchId}/suggestion-states`),

  markSuggestionApplied: (taskId: string, batchId: string, data: { source: string; suggestion: string; status: string }) =>
    fetchAPI<any>(`/api/eval/task/${taskId}/batch/${batchId}/suggestion-state`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ============== Version API ==============

export interface VersionItem {
  id: string;
  version_number: number;
  content: string;
  source: string;
  source_detail: string | null;
  created_at: string;
}

export const versionAPI = {
  list: (entityId: string) =>
    fetchAPI<{
      entity_id: string;
      entity_name: string;
      entity_type: string;
      current_content: string;
      versions: VersionItem[];
    }>(`/api/versions/${entityId}`),

  rollback: (entityId: string, versionId: string) =>
    fetchAPI<{
      success: boolean;
      entity_id: string;
      restored_version: number;
      message: string;
    }>(`/api/versions/${entityId}/rollback/${versionId}`, {
      method: "POST",
    }),
};

// ============== Memories API ==============

export interface MemoryItemInfo {
  id: string;
  project_id: string | null;
  content: string;
  source_mode: string;
  source_phase: string;
  related_blocks: any[];
  created_at: string;
  updated_at: string;
}

export const memoriesAPI = {
  list: (projectId: string, includeGlobal: boolean = false) =>
    fetchAPI<MemoryItemInfo[]>(`/api/memories/${projectId}${includeGlobal ? "?include_global=true" : ""}`),

  create: (projectId: string, data: { content: string; source_mode?: string; source_phase?: string; related_blocks?: any[] }) =>
    fetchAPI<MemoryItemInfo>(`/api/memories/${projectId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (scope: string, memoryId: string, data: { content?: string; related_blocks?: any[] }) =>
    fetchAPI<MemoryItemInfo>(`/api/memories/${scope}/${memoryId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (scope: string, memoryId: string) =>
    fetchAPI<{ message: string }>(`/api/memories/${scope}/${memoryId}`, {
      method: "DELETE",
    }),
};

// ============== Modes API ==============

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
  list: () =>
    fetchAPI<AgentModeInfo[]>("/api/modes/"),

  get: (modeId: string) =>
    fetchAPI<AgentModeInfo>(`/api/modes/${modeId}`),

  create: (data: Partial<AgentModeInfo>) =>
    fetchAPI<AgentModeInfo>("/api/modes/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (modeId: string, data: Partial<AgentModeInfo>) =>
    fetchAPI<AgentModeInfo>(`/api/modes/${modeId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (modeId: string) =>
    fetchAPI<{ message: string }>(`/api/modes/${modeId}`, {
      method: "DELETE",
    }),
};

// ============== Models API ==============

export interface ModelInfo {
  id: string;
  provider: string;
  name: string;
  tier: string;
}

export const modelsAPI = {
  list: () =>
    fetchAPI<{
      models: ModelInfo[];
      current_default: { main: string; mini: string };
      env_provider: string;
    }>("/api/models/"),
};

// ============== Agent Settings Types ==============

export interface AgentSettingsData {
  tools?: string[];
  skills?: { name: string; description: string; prompt: string }[];
  tool_prompts?: Record<string, string>;
  [key: string]: any;
}

// ============== Conversation Record ==============

export interface ConversationRecord {
  id: string;
  project_id: string;
  mode: string;
  title: string;
  status: string;
  bootstrap_policy: string;
  last_message_at: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

// ============== Search Types ==============

export interface SearchResult {
  type: "field" | "block";
  id: string;
  name: string;
  phase: string;
  parent_id?: string;
  match_count: number;
  snippets: {
    index: number;
    offset: number;
    prefix: string;
    match: string;
    suffix: string;
    line: number;
  }[];
}

// ============== Auto Trigger Chain ==============

/**
 * 前端驱动的自动触发链：
 * 1. 调用 check-auto-triggers 获取满足条件的块 ID
 * 2. 逐个触发流式生成
 * 3. 每个生成完成后递归检查是否有新的可触发块
 */
export async function runAutoTriggerChain(
  projectId: string,
  onUpdate?: () => void,
): Promise<void> {
  try {
    const resp = await fetchAPI<{ eligible_ids: string[] }>(
      `/api/blocks/project/${projectId}/check-auto-triggers`,
      { method: "POST" }
    );
    const ids = resp.eligible_ids || [];
    if (ids.length === 0) return;

    for (const blockId of ids) {
      try {
        const genResp = await blockAPI.generateStream(blockId);
        // 读完流
        const reader = genResp.body?.getReader();
        if (reader) {
          while (true) {
            const { done } = await reader.read();
            if (done) break;
          }
        }
        onUpdate?.();
      } catch (e) {
        console.error(`Auto-trigger generation failed for block ${blockId}:`, e);
      }
    }

    // 递归检查：刚完成的生成可能解锁了新的块
    await runAutoTriggerChain(projectId, onUpdate);
  } catch (e) {
    console.error("Auto-trigger chain failed:", e);
  }
}

// ============== Utilities ==============

/**
 * 解析消息中的 @引用
 * 例如: "请参考 @标题 和 @正文 生成内容" => ["标题", "正文"]
 */
export function parseReferences(message: string, knownNames?: string[]): string[] {
  const matches: string[] = [];

  // 先匹配已知名称（支持含空格的名称）
  if (knownNames && knownNames.length > 0) {
    // 按长度降序排列，优先匹配更长的名称
    const sorted = [...knownNames].sort((a, b) => b.length - a.length);
    for (const name of sorted) {
      if (message.includes(`@${name}`)) {
        matches.push(name);
      }
    }
  }

  // 再用正则匹配简单的 @引用（不含空格）
  const pattern = /@([^\s@]+)/g;
  let match;
  while ((match = pattern.exec(message)) !== null) {
    if (!matches.includes(match[1])) {
      matches.push(match[1]);
    }
  }
  return matches;
}