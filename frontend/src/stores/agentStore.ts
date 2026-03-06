import { create } from 'zustand';

export interface Agent {
  id: string;
  name: string;
  role: string;
  layer: number;
  status: string;
  model_name: string;
}

interface AgentState {
  agents: Agent[];
  setAgents: (agents: Agent[]) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: [],
  setAgents: (agents) => set({ agents }),
}));
