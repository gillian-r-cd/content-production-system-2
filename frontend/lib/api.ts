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
  use_flexible_architecture?: boolean;
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
  version_warning?: string;         // 版本变更警告（更新时返回）
  affected_fields?: string[];       // 受影响的字段名列表
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

  // System Prompts Import/Export
  exportSystemPrompts: (id?: string) => {
    const query = id ? `?id=${id}` : "";
    return fetchAPI<any>(`/api/settings/system-prompts/export${query}`);
  },
  importSystemPrompts: (data: any[]) =>
    fetchAPI<any>("/api/settings/system-prompts/import", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Creator Profiles Import/Export
  exportCreatorProfiles: (id?: string) => {
    const query = id ? `?id=${id}` : "";
    return fetchAPI<any>(`/api/settings/creator-profiles/export${query}`);
  },
  importCreatorProfiles: (data: any[]) =>
    fetchAPI<any>("/api/settings/creator-profiles/import", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Field Templates Import/Export
  exportFieldTemplates: (id?: string) => {
    const query = id ? `?id=${id}` : "";
    return fetchAPI<any>(`/api/settings/field-templates/export${query}`);
  },
  importFieldTemplates: (data: any[]) =>
    fetchAPI<any>("/api/settings/field-templates/import", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Simulators Import/Export
  exportSimulators: (id?: string) => {
    const query = id ? `?id=${id}` : "";
    return fetchAPI<any>(`/api/settings/simulators/export${query}`);
  },
  importSimulators: (data: any[]) =>
    fetchAPI<any>("/api/settings/simulators/import", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Graders
  listGraders: () =>
    fetchAPI<any[]>("/api/graders"),
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
  depth?: number;
  order_index: number;
  content: string;
  status: "pending" | "in_progress" | "completed" | "failed";
  ai_prompt?: string;
  constraints?: FieldConstraints;
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
    constraints: FieldConstraints;
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
  generateStream: async function (blockId: string): Promise<Response> {
    const resp = await fetch(`${API_BASE}/api/blocks/${blockId}/generate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
  console.log(`[AUTO-CHAIN] Generating block ${blockId}...`);
  const resp = await blockAPI.generateStream(blockId);

  if (!resp.ok) {
    console.error(`[AUTO-CHAIN] Generate failed for ${blockId}: ${resp.status}`);
    return false;
  }

  // 读取 SSE 流直到完成
  const reader = resp.body?.getReader();
  const decoder = new TextDecoder();
  let success = false;
  if (reader) {
    let done = false;
    while (!done) {
      const { value, done: streamDone } = await reader.read();
      done = streamDone;
      if (value) {
        const text = decoder.decode(value, { stream: true });
        const lines = text.split("\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.substring(6));
              if (data.done) {
                console.log(`[AUTO-CHAIN] Block ${blockId} completed`);
                success = true;
              }
            } catch {
              // chunk, not JSON
            }
          }
        }
      }
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
  config: Record<string, any>;
  created_at: string;
}

export interface EvalTask {
  id: string;
  eval_run_id: string;
  name: string;
  simulator_type: string;
  interaction_mode: string;
  simulator_config: Record<string, any>;
  persona_config: Record<string, any>;
  target_block_ids: string[];
  grader_config: Record<string, any>;
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
  role_config: Record<string, any>;
  interaction_mode: string;
  input_block_ids: string[];
  persona: Record<string, any>;
  nodes: Array<{ role: string; content: string; turn?: number; phase?: string }>;
  result: Record<string, any>;
  grader_outputs: any[];
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
  roles: Record<string, any>;
}

export const evalAPI = {
  // Config
  getConfig: (): Promise<EvalConfig> => fetchAPI("/api/eval/config"),
  getPersonas: (projectId: string) => fetchAPI("/api/eval/personas/" + projectId),

  // EvalRun CRUD
  listRuns: (projectId: string): Promise<EvalRun[]> => fetchAPI("/api/eval/runs/" + projectId),
  createRun: (data: { project_id: string; name?: string }): Promise<EvalRun> =>
    fetchAPI("/api/eval/runs", { method: "POST", body: JSON.stringify(data) }),
  getRun: (runId: string): Promise<EvalRun> => fetchAPI("/api/eval/run/" + runId),
  updateRun: (runId: string, data: any): Promise<EvalRun> =>
    fetchAPI("/api/eval/run/" + runId, { method: "PUT", body: JSON.stringify(data) }),
  deleteRun: (runId: string) =>
    fetchAPI("/api/eval/run/" + runId, { method: "DELETE" }),

  // EvalTask CRUD
  listTasks: (runId: string): Promise<EvalTask[]> => fetchAPI("/api/eval/run/" + runId + "/tasks"),
  createTask: (runId: string, data: Partial<EvalTask>): Promise<EvalTask> =>
    fetchAPI("/api/eval/run/" + runId + "/tasks", { method: "POST", body: JSON.stringify(data) }),
  updateTask: (taskId: string, data: Partial<EvalTask>): Promise<EvalTask> =>
    fetchAPI("/api/eval/task/" + taskId, { method: "PUT", body: JSON.stringify(data) }),
  deleteTask: (taskId: string) =>
    fetchAPI("/api/eval/task/" + taskId, { method: "DELETE" }),
  batchCreateTasks: (data: { project_id: string; eval_run_id: string; template: string; persona_ids?: string[] }) =>
    fetchAPI("/api/eval/run/" + data.eval_run_id + "/batch-tasks", { method: "POST", body: JSON.stringify(data) }),

  // Execute
  executeRun: (runId: string) =>
    fetchAPI("/api/eval/run/" + runId + "/execute", { method: "POST" }),
  executeTask: (taskId: string): Promise<EvalTrial> =>
    fetchAPI("/api/eval/task/" + taskId + "/execute", { method: "POST" }),

  // Trials
  getTrials: (runId: string): Promise<EvalTrial[]> => fetchAPI("/api/eval/run/" + runId + "/trials"),
  getTrial: (trialId: string): Promise<EvalTrial> => fetchAPI("/api/eval/trial/" + trialId),

  // Diagnosis
  runDiagnosis: (runId: string) =>
    fetchAPI("/api/eval/run/" + runId + "/diagnose", { method: "POST" }),

  // Legacy: full regression in one call
  runEval: (data: any): Promise<EvalRun> =>
    fetchAPI("/api/eval/run", { method: "POST", body: JSON.stringify(data) }),

  // Run a single trial
  runSingleTrial: (data: any): Promise<any> =>
    fetchAPI("/api/eval/trial/run", { method: "POST", body: JSON.stringify(data) }),

  // Generate for ContentBlock
  generateForBlock: (blockId: string) =>
    fetchAPI("/api/eval/generate-for-block/" + blockId, { method: "POST" }),
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
};


// ============== Utilities ==============

/**
 * 解析消息中的 @引用
 * 例如: "请参考 @标题 和 @正文 生成内容" => ["标题", "正文"]
 */
export function parseReferences(message: string): string[] {
  const pattern = /@([^\s@]+)/g;
  const matches: string[] = [];
  let match;
  while ((match = pattern.exec(message)) !== null) {
    matches.push(match[1]);
  }
  return matches;
}
