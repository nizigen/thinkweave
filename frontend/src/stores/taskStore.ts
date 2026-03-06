import { create } from 'zustand';

export interface Task {
  id: string;
  title: string;
  status: string;
  mode: string;
  fsm_state: string;
  word_count: number;
  created_at: string;
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
