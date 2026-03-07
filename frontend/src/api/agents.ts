/**
 * Agent API service layer
 * Endpoints: GET/POST /api/agents, GET/PATCH/DELETE /api/agents/{id}
 * Ref: backend/app/routers/agents.py + backend/app/schemas/agent.py
 */
import apiClient from './client';

export interface AgentCreatePayload {
  name: string;
  role: string;
  layer: number;
  capabilities?: string | null;
  model?: string;
}

export interface AgentData {
  id: string;
  name: string;
  role: string;
  layer: number;
  capabilities: string | null;
  model: string;
  status: string;
  created_at: string;
}

export interface AgentStatusPayload {
  status: 'idle' | 'busy' | 'offline';
}

export const agentApi = {
  list: () =>
    apiClient.get<AgentData[]>('/agents').then((r) => r.data),

  create: (payload: AgentCreatePayload) =>
    apiClient.post<AgentData>('/agents', payload).then((r) => r.data),

  get: (id: string) =>
    apiClient.get<AgentData>(`/agents/${id}`).then((r) => r.data),

  updateStatus: (id: string, payload: AgentStatusPayload) =>
    apiClient.patch<AgentData>(`/agents/${id}/status`, payload).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`/agents/${id}`),
};
