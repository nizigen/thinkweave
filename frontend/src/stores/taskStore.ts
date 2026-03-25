import { create } from 'zustand';

export interface Task {
  id: string;
  title: string;
  status: string;
  mode: string;
  fsm_state: string;
  word_count: number;
  created_at: string;
  depth?: string;
  target_words?: number;
  finished_at?: string | null;
  checkpoint_data?: TaskCheckpointData;
  nodes?: TaskNode[];
}

export interface TaskNode {
  id: string;
  task_id: string;
  title: string;
  agent_role: string | null;
  assigned_agent: string | null;
  status: string;
  depends_on: string[] | null;
  retry_count: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface TaskControlSnapshot {
  status: string;
  preview_cache: Record<string, Record<string, unknown>>;
  review_scores: Record<string, Record<string, unknown>>;
  last_command?: {
    type: string;
    node_id?: string;
  };
}

export interface TaskCheckpointData {
  control: TaskControlSnapshot;
  [key: string]: unknown;
}

interface TaskState {
  currentTask: Task | null;
  tasks: Task[];
  setCurrentTask: (task: Task | null) => void;
  setTasks: (tasks: Task[]) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  currentTask: null,
  tasks: [],
  setCurrentTask: (task) => set({ currentTask: task }),
  setTasks: (tasks) => set({ tasks }),
}));
