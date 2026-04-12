/**
 * Agent API service layer
 * Endpoints: GET/POST /api/agents, GET/PATCH/DELETE /api/agents/{id}
 * Ref: backend/app/routers/agents.py + backend/app/schemas/agent.py
 */
import apiClient from './client';

export interface AgentConfigPayload {
  goal?: string;
  backstory?: string;
  description?: string;
  system_message?: string;
  temperature?: number;
  max_tokens?: number;
  max_retries?: number;
  max_tool_iterations?: number;
  fallback_models?: string[];
  skill_allowlist?: string[];
  tool_allowlist?: string[];
  tags?: string[];
}

export interface AgentCreatePayload {
  name: string;
  role: string;
  layer: number;
  capabilities?: string | null;
  model?: string;
  custom_model?: string;
  agent_config?: AgentConfigPayload;
}

export interface AgentData {
  id: string;
  name: string;
  role: string;
  layer: number;
  capabilities: string | null;
  model: string;
  agent_config?: AgentConfigPayload | null;
  status: string;
  created_at: string;
}

export interface AgentStatusPayload {
  status: 'idle' | 'busy' | 'offline';
}

export interface ModelOptionData {
  value: string;
  label: string;
  description: string;
  provider: string;
}

export interface SkillOptionData {
  name: string;
  skill_type: string;
  description: string;
  applicable_roles: string[];
  applicable_modes: string[];
  applicable_stages: string[];
  tools: string[];
  model_preference?: string | null;
  priority: number;
  source_path: string;
}

export interface ToolOptionData {
  name: string;
  description: string;
  server_name: string;
}

export interface RolePresetConfigData {
  skill_allowlist: string[];
  tool_allowlist: string[];
  max_tool_iterations: number;
}

export interface RolePresetData {
  role: string;
  layer: number;
  label: string;
  description: string;
  icon: string;
  default_model: string;
  agent_config: RolePresetConfigData;
}

export const agentApi = {
  list: () =>
    apiClient.get<AgentData[]>('/agents').then((r) => r.data),

  create: (payload: AgentCreatePayload) =>
    apiClient.post<AgentData>('/agents', payload).then((r) => r.data),

  listModelOptions: () =>
    apiClient.get<ModelOptionData[]>('/agents/model-options').then((r) => r.data),

  listRolePresets: () =>
    apiClient.get<RolePresetData[]>('/agents/role-presets').then((r) => r.data),

  listSkillOptions: () =>
    apiClient.get<SkillOptionData[]>('/agents/skills').then((r) => r.data),

  listToolOptions: () =>
    apiClient.get<ToolOptionData[]>('/agents/tool-options').then((r) => r.data),

  get: (id: string) =>
    apiClient.get<AgentData>(`/agents/${id}`).then((r) => r.data),

  updateStatus: (id: string, payload: AgentStatusPayload) =>
    apiClient.patch<AgentData>(`/agents/${id}/status`, payload).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`/agents/${id}`),
};
