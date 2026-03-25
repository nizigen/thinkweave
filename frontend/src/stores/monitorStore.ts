import { create } from 'zustand';

import type { Task, TaskControlSnapshot, TaskNode } from './taskStore';

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

function emptyControlState(): TaskControlSnapshot {
  return {
    status: 'active',
    preview_cache: {},
    review_scores: {},
  };
}

function normalizeControlState(task: Task | null): TaskControlSnapshot {
  const control = task?.checkpoint_data?.control;
  if (!control) {
    return emptyControlState();
  }
  return {
    status: control.status ?? 'active',
    preview_cache: control.preview_cache ?? {},
    review_scores: control.review_scores ?? {},
    last_command: control.last_command,
  };
}

function indexNodes(nodes: TaskNode[] | undefined): Record<string, TaskNode> {
  return Object.fromEntries((nodes ?? []).map((node) => [node.id, node]));
}

interface MonitorState {
  activeTaskId: string | null;
  connectionState: MonitorConnectionState;
  lastError: string | null;
  reconnectAttempt: number;
  lastEventAt: number | null;
  taskSnapshot: Task | null;
  nodesById: Record<string, TaskNode>;
  orderedNodeIds: string[];
  agentStatusByNodeId: Record<string, Record<string, unknown>>;
  chapterPreviewByNodeId: Record<string, Record<string, unknown>>;
  reviewScoreByNodeId: Record<string, Record<string, unknown>>;
  consistencyResultByNodeId: Record<string, Record<string, unknown>>;
  controlState: TaskControlSnapshot | null;
  selectedNodeId: string | null;
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
  selectNode: (nodeId: string | null) => void;
}

export const useMonitorStore = create<MonitorState>((set) => ({
  activeTaskId: null,
  connectionState: 'disconnected',
  lastError: null,
  reconnectAttempt: 0,
  lastEventAt: null,
  taskSnapshot: null,
  nodesById: {},
  orderedNodeIds: [],
  agentStatusByNodeId: {},
  chapterPreviewByNodeId: {},
  reviewScoreByNodeId: {},
  consistencyResultByNodeId: {},
  controlState: null,
  selectedNodeId: null,
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
      nodesById: {},
      orderedNodeIds: [],
      agentStatusByNodeId: {},
      chapterPreviewByNodeId: {},
      reviewScoreByNodeId: {},
      consistencyResultByNodeId: {},
      controlState: null,
      selectedNodeId: null,
      events: [],
    }),
  setConnectionState: (state, error = null) =>
    set({
      connectionState: state,
      lastError: error,
    }),
  setTaskSnapshot: (task) =>
    set((state) => {
      const nodesById = indexNodes(task?.nodes);
      const orderedNodeIds = (task?.nodes ?? []).map((node) => node.id);
      const controlState = normalizeControlState(task);
      const selectedNodeId =
        state.selectedNodeId && nodesById[state.selectedNodeId]
          ? state.selectedNodeId
          : null;

      return {
        taskSnapshot: task,
        nodesById,
        orderedNodeIds,
        agentStatusByNodeId: {},
        controlState,
        chapterPreviewByNodeId: { ...controlState.preview_cache },
        reviewScoreByNodeId: { ...controlState.review_scores },
        consistencyResultByNodeId: {},
        selectedNodeId,
      };
    }),
  markReconnectAttempt: (count) => set({ reconnectAttempt: count }),
  selectNode: (nodeId) => set({ selectedNodeId: nodeId }),
  ingestEvent: (event) =>
    set((state) => {
      if (state.activeTaskId && event.task_id !== state.activeTaskId) {
        return state;
      }

      const nextEvents = [...state.events, event].slice(-MAX_RETAINED_EVENTS);
      const nextState: Partial<MonitorState> = {
        events: nextEvents,
        lastEventAt: Date.now(),
        connectionState:
          event.type === 'connected' ? 'connected' : state.connectionState,
      };

      if (event.type === 'node_update' && event.node_id) {
        const previousNode = state.nodesById[event.node_id];
        if (previousNode) {
          nextState.nodesById = {
            ...state.nodesById,
            [event.node_id]: {
              ...previousNode,
              ...event.payload,
            } as TaskNode,
          };
        }
      }

      if (event.type === 'agent_status' && event.node_id) {
        nextState.agentStatusByNodeId = {
          ...state.agentStatusByNodeId,
          [event.node_id]: event.payload,
        };
      }

      if (event.type === 'chapter_preview' && event.node_id) {
        nextState.chapterPreviewByNodeId = {
          ...state.chapterPreviewByNodeId,
          [event.node_id]: event.payload,
        };
      }

      if (event.type === 'review_score' && event.node_id) {
        nextState.reviewScoreByNodeId = {
          ...state.reviewScoreByNodeId,
          [event.node_id]: event.payload,
        };
      }

      if (event.type === 'consistency_result' && event.node_id) {
        nextState.consistencyResultByNodeId = {
          ...state.consistencyResultByNodeId,
          [event.node_id]: event.payload,
        };
      }

      if (event.type === 'dag_update' && event.payload.control) {
        const controlPayload = event.payload.control as Partial<TaskControlSnapshot>;
        nextState.controlState = {
          ...(state.controlState ?? emptyControlState()),
          ...controlPayload,
          preview_cache:
            controlPayload.preview_cache ?? state.controlState?.preview_cache ?? {},
          review_scores:
            controlPayload.review_scores ?? state.controlState?.review_scores ?? {},
        };
      }

      return {
        ...nextState,
      };
    }),
}));
