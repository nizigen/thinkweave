import { useEffect } from 'react';

import { getTask } from '../api/tasks';
import {
  useMonitorStore,
  type TaskEvent,
} from '../stores/monitorStore';

const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 16000] as const;
const NON_RETRIABLE_CLOSE_CODES = new Set([1008]);

function encodeTokenForProtocol(token: string): string {
  return btoa(token)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

function buildTaskWebSocketUrl(taskId: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/task/${taskId}`;
}

function parseTaskEvent(raw: string): TaskEvent | null {
  try {
    return JSON.parse(raw) as TaskEvent;
  } catch {
    return null;
  }
}

export function useTaskWebSocket(taskId: string | undefined) {
  const connectionState = useMonitorStore((state) => state.connectionState);
  const lastError = useMonitorStore((state) => state.lastError);
  const reconnectAttempt = useMonitorStore((state) => state.reconnectAttempt);

  useEffect(() => {
    if (!taskId) {
      useMonitorStore.getState().reset();
      return undefined;
    }

    useMonitorStore.getState().reset(taskId);

    let isDisposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let attempt = 0;

    const syncTaskSnapshot = async () => {
      try {
        const task = await getTask(taskId);
        if (
          !isDisposed &&
          useMonitorStore.getState().activeTaskId === taskId
        ) {
          useMonitorStore.getState().setTaskSnapshot(task);
        }
      } catch {
        if (!isDisposed) {
          useMonitorStore
            .getState()
            .setConnectionState('error', '任务状态同步失败');
        }
      }
    };

    const clearReconnectTimer = () => {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const scheduleReconnect = () => {
      if (isDisposed) {
        return;
      }
      if (attempt >= RECONNECT_DELAYS_MS.length) {
        useMonitorStore
          .getState()
          .setConnectionState('error', 'WebSocket 重连次数已耗尽');
        return;
      }

      const delay = RECONNECT_DELAYS_MS[attempt];
      attempt += 1;
      useMonitorStore.getState().markReconnectAttempt(attempt);
      useMonitorStore.getState().setConnectionState('disconnected');
      reconnectTimer = window.setTimeout(() => {
        void openSocket();
      }, delay);
    };

    const openSocket = async () => {
      const token = sessionStorage.getItem('task_auth_token')?.trim() ?? '';
      if (!token) {
        useMonitorStore
          .getState()
          .setConnectionState('error', '缺少任务鉴权 token');
        return;
      }

      clearReconnectTimer();
      useMonitorStore.getState().setConnectionState('connecting');

      if (attempt === 0) {
        void syncTaskSnapshot();
      }

      const currentSocket = new WebSocket(buildTaskWebSocketUrl(taskId), [
        'agentic-nexus.auth',
        `auth.${encodeTokenForProtocol(token)}`,
      ]);
      socket = currentSocket;

      currentSocket.onmessage = (event) => {
        if (isDisposed || socket !== currentSocket) {
          return;
        }

        const message = parseTaskEvent(String(event.data));
        if (!message) {
          return;
        }

        if (message.task_id !== taskId) {
          return;
        }

        useMonitorStore.getState().ingestEvent(message);
        if (message.type === 'connected') {
          useMonitorStore.getState().setConnectionState('connected');
          if (attempt > 0) {
            void syncTaskSnapshot();
            attempt = 0;
            useMonitorStore.getState().markReconnectAttempt(0);
          }
        }
      };

      currentSocket.onerror = () => {
        if (!isDisposed && socket === currentSocket) {
          useMonitorStore
            .getState()
            .setConnectionState('error', 'WebSocket 连接错误');
        }
      };

      currentSocket.onclose = (event) => {
        const closeCode = event?.code ?? 1006;
        if (socket === currentSocket) {
          socket = null;
        }
        if (isDisposed) {
          return;
        }
        if (NON_RETRIABLE_CLOSE_CODES.has(closeCode)) {
          useMonitorStore
            .getState()
            .setConnectionState('error', '任务鉴权或访问权限校验失败');
          return;
        }
        scheduleReconnect();
      };
    };

    void openSocket();

    return () => {
      isDisposed = true;
      clearReconnectTimer();
      if (socket) {
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;
        socket.close();
      }
    };
  }, [taskId]);

  return {
    connectionState,
    lastError,
    reconnectAttempt,
  };
}
