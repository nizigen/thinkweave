import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useMonitorStore } from '../../stores/monitorStore';
import { useTaskWebSocket } from '../useTaskWebSocket';

const { getTaskMock } = vi.hoisted(() => ({
  getTaskMock: vi.fn(),
}));

vi.mock('../../api/tasks', () => ({
  getTask: getTaskMock,
}));

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;

  constructor(
    readonly url: string,
    readonly protocols?: string | string[],
  ) {
    MockWebSocket.instances.push(this);
  }

  close = vi.fn();
}

describe('useTaskWebSocket', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket);
    sessionStorage.clear();
    getTaskMock.mockReset();
    getTaskMock.mockResolvedValue({
      id: 'task-1',
      title: 'Task',
      status: 'running',
      mode: 'report',
      fsm_state: 'writing',
      word_count: 10,
      created_at: '2026-03-24T00:00:00Z',
    });
    useMonitorStore.getState().reset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('opens a websocket with the auth subprotocol pair', () => {
    sessionStorage.setItem('task_auth_token', 'header-token');

    renderHook(() => useTaskWebSocket('task-1'));

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0]?.protocols).toEqual([
      'agentic-nexus.auth',
      'auth.aGVhZGVyLXRva2Vu',
    ]);
  });

  it('does not open a websocket when token is missing', () => {
    renderHook(() => useTaskWebSocket('task-1'));

    expect(MockWebSocket.instances).toHaveLength(0);
    expect(useMonitorStore.getState().connectionState).toBe('error');
  });

  it('marks connected and ingests websocket events', () => {
    sessionStorage.setItem('task_auth_token', 'header-token');
    renderHook(() => useTaskWebSocket('task-1'));

    const socket = MockWebSocket.instances[0];
    act(() => {
      socket?.onmessage?.({
        data: JSON.stringify({
          type: 'connected',
          task_id: 'task-1',
          node_id: '',
          from_agent: '',
          timestamp: 1,
          payload: {},
        }),
      } as MessageEvent<string>);
    });

    expect(useMonitorStore.getState().connectionState).toBe('connected');
    expect(useMonitorStore.getState().events).toHaveLength(1);
  });

  it('reconnects with exponential backoff and resyncs after reconnect success', async () => {
    sessionStorage.setItem('task_auth_token', 'header-token');
    getTaskMock.mockReset();
    getTaskMock
      .mockResolvedValueOnce({
        id: 'task-1',
        title: 'Task',
        status: 'running',
        mode: 'report',
        fsm_state: 'writing',
        word_count: 10,
        created_at: '2026-03-24T00:00:00Z',
        checkpoint_data: {
          control: {
            status: 'active',
            preview_cache: {},
            review_scores: {},
          },
        },
        nodes: [],
      })
      .mockResolvedValueOnce({
        id: 'task-1',
        title: 'Task',
        status: 'running',
        mode: 'report',
        fsm_state: 'writing',
        word_count: 10,
        created_at: '2026-03-24T00:00:00Z',
        checkpoint_data: {
          control: {
            status: 'paused',
            preview_cache: {
              'node-1': { content: 'preview body' },
            },
            review_scores: {
              'node-1': { score: 90 },
            },
          },
        },
        nodes: [
          {
            id: 'node-1',
            task_id: 'task-1',
            title: 'Outline',
            agent_role: 'writer',
            assigned_agent: 'agent-1',
            status: 'paused',
            depends_on: null,
            retry_count: 0,
            started_at: null,
            finished_at: null,
          },
        ],
      });
    renderHook(() => useTaskWebSocket('task-1'));

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(getTaskMock).toHaveBeenCalledTimes(1);

    act(() => {
      MockWebSocket.instances[0]?.onclose?.({} as CloseEvent);
    });

    expect(useMonitorStore.getState().connectionState).toBe('disconnected');
    expect(useMonitorStore.getState().reconnectAttempt).toBe(1);

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(MockWebSocket.instances).toHaveLength(2);

    await act(async () => {
      MockWebSocket.instances[1]?.onmessage?.({
        data: JSON.stringify({
          type: 'connected',
          task_id: 'task-1',
          node_id: '',
          from_agent: '',
          timestamp: 2,
          payload: {},
        }),
      } as MessageEvent<string>);
      await Promise.resolve();
    });

    expect(useMonitorStore.getState().connectionState).toBe('connected');
    expect(useMonitorStore.getState().reconnectAttempt).toBe(0);
    expect(getTaskMock).toHaveBeenCalledTimes(2);
    expect(useMonitorStore.getState().nodesById['node-1']?.status).toBe('paused');
    expect(useMonitorStore.getState().controlState?.status).toBe('paused');
    expect(useMonitorStore.getState().chapterPreviewByNodeId['node-1']?.content).toBe('preview body');
  });

  it('cleans up the socket on unmount', () => {
    sessionStorage.setItem('task_auth_token', 'header-token');
    const { unmount } = renderHook(() => useTaskWebSocket('task-1'));

    const socket = MockWebSocket.instances[0];
    unmount();

    expect(socket?.close).toHaveBeenCalledTimes(1);
  });

  it('ignores stale events from another task id', () => {
    sessionStorage.setItem('task_auth_token', 'header-token');
    renderHook(() => useTaskWebSocket('task-1'));

    const socket = MockWebSocket.instances[0];
    act(() => {
      socket?.onmessage?.({
        data: JSON.stringify({
          type: 'connected',
          task_id: 'task-2',
          node_id: '',
          from_agent: '',
          timestamp: 1,
          payload: {},
        }),
      } as MessageEvent<string>);
    });

    expect(useMonitorStore.getState().events).toHaveLength(0);
    expect(useMonitorStore.getState().connectionState).toBe('connecting');
  });

  it('does not reconnect after a terminal authorization close', () => {
    sessionStorage.setItem('task_auth_token', 'header-token');
    renderHook(() => useTaskWebSocket('task-1'));

    act(() => {
      MockWebSocket.instances[0]?.onclose?.({ code: 1008 } as CloseEvent);
      vi.advanceTimersByTime(20000);
    });

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(useMonitorStore.getState().connectionState).toBe('error');
    expect(useMonitorStore.getState().lastError).toBe(
      '任务鉴权或访问权限校验失败',
    );
  });

  it('ignores stale snapshot responses after task switch', async () => {
    sessionStorage.setItem('task_auth_token', 'header-token');

    let resolveTask1: ((value: Awaited<ReturnType<typeof getTaskMock>>) => void) | null =
      null;
    getTaskMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveTask1 = resolve;
        }),
    );

    const { rerender } = renderHook(
      ({ taskId }) => useTaskWebSocket(taskId),
      { initialProps: { taskId: 'task-1' as string | undefined } },
    );

    getTaskMock.mockResolvedValueOnce({
      id: 'task-2',
      title: 'Task 2',
      status: 'running',
      mode: 'report',
      fsm_state: 'writing',
      word_count: 20,
      created_at: '2026-03-24T00:00:00Z',
    });

    rerender({ taskId: 'task-2' });
    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      resolveTask1?.({
        id: 'task-1',
        title: 'Task 1',
        status: 'running',
        mode: 'report',
        fsm_state: 'writing',
        word_count: 10,
        created_at: '2026-03-24T00:00:00Z',
      });
      await Promise.resolve();
    });

    expect(useMonitorStore.getState().activeTaskId).toBe('task-2');
    expect(useMonitorStore.getState().taskSnapshot?.id).toBe('task-2');
  });
});
