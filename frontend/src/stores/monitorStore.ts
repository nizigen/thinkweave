import { create } from 'zustand';

import type { Task } from './taskStore';

export type MonitorConnectionState =
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'error';

export interface TaskEvent {
  type: string;
  task_id: string;
  node_id: string;
  from_agent: string;
  timestamp: number;
  payload: Record<string, unknown>;
}

const MAX_RETAINED_EVENTS = 500;

interface MonitorState {
  activeTaskId: string | null;
  connectionState: MonitorConnectionState;
  lastError: string | null;
  reconnectAttempt: number;
  lastEventAt: number | null;
  taskSnapshot: Task | null;
  events: TaskEvent[];
  maxRetainedEvents: number;
  reset: (taskId?: string) => void;
  setConnectionState: (
    state: MonitorConnectionState,
    error?: string | null,
  ) => void;
  setTaskSnapshot: (task: Task | null) => void;
  markReconnectAttempt: (count: number) => void;
  ingestEvent: (event: TaskEvent) => void;
}

export const useMonitorStore = create<MonitorState>((set) => ({
  activeTaskId: null,
  connectionState: 'disconnected',
  lastError: null,
  reconnectAttempt: 0,
  lastEventAt: null,
  taskSnapshot: null,
  events: [],
  maxRetainedEvents: MAX_RETAINED_EVENTS,
  reset: (taskId) =>
    set({
      activeTaskId: taskId ?? null,
      connectionState: 'disconnected',
      lastError: null,
      reconnectAttempt: 0,
      lastEventAt: null,
      taskSnapshot: null,
      events: [],
    }),
  setConnectionState: (state, error = null) =>
    set({
      connectionState: state,
      lastError: error,
    }),
  setTaskSnapshot: (task) => set({ taskSnapshot: task }),
  markReconnectAttempt: (count) => set({ reconnectAttempt: count }),
  ingestEvent: (event) =>
    set((state) => {
      if (state.activeTaskId && event.task_id !== state.activeTaskId) {
        return state;
      }

      const nextEvents = [...state.events, event].slice(-MAX_RETAINED_EVENTS);
      return {
        events: nextEvents,
        lastEventAt: Date.now(),
        connectionState:
          event.type === 'connected' ? 'connected' : state.connectionState,
      };
    }),
}));
