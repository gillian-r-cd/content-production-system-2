// frontend/lib/api.ts
// 功能: API客户端，封装后端API调用
// 主要函数: fetchAPI, streamAPI
// 数据结构: Project, Field, ChatMessage

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

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
  
  create: (data: { name: string; creator_profile_id?: string; use_deep_research?: boolean }) =>
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
  chat: (projectId: string, message: string, currentPhase?: string) =>
    fetchAPI<ChatResponse>("/api/agent/chat", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        message,
        current_phase: currentPhase,
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
  
  // 删除模拟记录
  delete: (id: string) =>
    fetchAPI<any>(`/api/simulations/${id}`, { method: "DELETE" }),
  
  // 获取消费者调研中的人物小传
  getPersonasFromResearch: (projectId: string) =>
    fetchAPI<PersonaFromResearch[]>(`/api/simulations/project/${projectId}/personas`),
};

