/**
 * Agent Zustand store — CRUD actions + state
 * Ref: api/agents.ts
 */
import { create } from 'zustand';
import { agentApi } from '../api/agents';
import type { AgentData, AgentCreatePayload } from '../api/agents';

interface AgentState {
  agents: AgentData[];
  loading: boolean;
  selectedAgent: AgentData | null;

  fetchAgents: () => Promise<void>;
  createAgent: (payload: AgentCreatePayload) => Promise<AgentData>;
  updateAgentStatus: (id: string, status: 'idle' | 'busy' | 'offline') => Promise<void>;
  deleteAgent: (id: string) => Promise<void>;
  setSelectedAgent: (agent: AgentData | null) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: [],
  loading: false,
  selectedAgent: null,

  fetchAgents: async () => {
    set({ loading: true });
    try {
      const agents = await agentApi.list();
      set((s) => ({
        agents,
        loading: false,
        selectedAgent: s.selectedAgent
          ? agents.find((a) => a.id === s.selectedAgent?.id) ?? null
          : null,
      }));
    } catch (err) {
      set({ loading: false });
      throw err instanceof Error ? err : new Error('Failed to fetch agents');
    }
  },

  createAgent: async (payload) => {
    const agent = await agentApi.create(payload);
    set((s) => ({ agents: [...s.agents, agent] }));
    return agent;
  },

  updateAgentStatus: async (id, status) => {
    const updated = await agentApi.updateStatus(id, { status });
    set((s) => ({
      agents: s.agents.map((a) => (a.id === id ? updated : a)),
      selectedAgent: s.selectedAgent?.id === id ? updated : s.selectedAgent,
    }));
  },

  deleteAgent: async (id) => {
    await agentApi.delete(id);
    set((s) => ({
      agents: s.agents.filter((a) => a.id !== id),
      selectedAgent: s.selectedAgent?.id === id ? null : s.selectedAgent,
    }));
  },

  setSelectedAgent: (agent) => set({ selectedAgent: agent }),
}));
