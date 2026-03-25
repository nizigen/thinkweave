import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMonitorStore } from '../../../stores/monitorStore';
import Monitor from '../../../pages/Monitor';
import type { Task } from '../../../stores/taskStore';

const { pauseTaskMock, resumeTaskMock, retryTaskNodeMock, skipTaskNodeMock } =
  vi.hoisted(() => ({
    pauseTaskMock: vi.fn(),
    resumeTaskMock: vi.fn(),
    retryTaskNodeMock: vi.fn(),
    skipTaskNodeMock: vi.fn(),
  }));

vi.mock('../../../api/tasks', () => ({
  pauseTask: pauseTaskMock,
  resumeTask: resumeTaskMock,
  retryTaskNode: retryTaskNodeMock,
  skipTaskNode: skipTaskNodeMock,
}));

vi.mock('../../../hooks/useTaskWebSocket', () => ({
  useTaskWebSocket: () => ({
    connectionState: 'connected',
    reconnectAttempt: 0,
    lastError: null,
  }),
}));

describe('Monitor page', () => {
  beforeEach(() => {
    pauseTaskMock.mockReset();
    resumeTaskMock.mockReset();
    retryTaskNodeMock.mockReset();
    skipTaskNodeMock.mockReset();
    useMonitorStore.getState().reset('task-1');
    useMonitorStore.getState().setTaskSnapshot({
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
          preview_cache: {
            'node-1': { content: 'preview body' },
          },
          review_scores: {
            'node-1': { score: 93 },
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
          status: 'running',
          depends_on: null,
          retry_count: 0,
          started_at: null,
          finished_at: null,
        },
      ],
    });
    useMonitorStore.getState().selectNode('node-1');
  });

  it('renders the full control tower sections', () => {
    render(
      <MemoryRouter initialEntries={['/monitor/task-1']}>
        <Routes>
          <Route path="/monitor/:taskId" element={<Monitor />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText(/control tower/i)).toBeInTheDocument();
    expect(screen.getByText(/dag overview/i)).toBeInTheDocument();
    expect(screen.getByText(/controls/i)).toBeInTheDocument();
    expect(screen.getByText(/agent activity/i)).toBeInTheDocument();
    expect(screen.getByText(/log stream/i)).toBeInTheDocument();
    expect(screen.getByText(/chapter preview/i)).toBeInTheDocument();
  });

  it('drops stale control responses after unmount and task switch', async () => {
    let resolvePause: ((value: Task) => void) | null = null;

    pauseTaskMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolvePause = resolve as typeof resolvePause;
        }),
    );

    const { unmount } = render(
      <MemoryRouter initialEntries={['/monitor/task-1']}>
        <Routes>
          <Route path="/monitor/:taskId" element={<Monitor />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: /pause/i }));
    unmount();

    useMonitorStore.getState().reset('task-2');
    useMonitorStore.getState().setTaskSnapshot({
      id: 'task-2',
      title: 'Task 2',
      status: 'running',
      mode: 'report',
      fsm_state: 'reviewing',
      word_count: 20,
      created_at: '2026-03-24T00:00:00Z',
      checkpoint_data: {
        control: {
          status: 'active',
          preview_cache: {},
          review_scores: {},
        },
      },
      nodes: [],
    });

    await act(async () => {
      resolvePause?.({
        id: 'task-1',
        title: 'Task',
        status: 'paused',
        mode: 'report',
        fsm_state: 'writing',
        word_count: 10,
        created_at: '2026-03-24T00:00:00Z',
        checkpoint_data: {
          control: {
            status: 'pause_requested',
            preview_cache: {},
            review_scores: {},
          },
        },
        nodes: [],
      });
      await Promise.resolve();
    });

    expect(useMonitorStore.getState().activeTaskId).toBe('task-2');
    expect(useMonitorStore.getState().taskSnapshot?.id).toBe('task-2');
    expect(useMonitorStore.getState().taskSnapshot?.fsm_state).toBe('reviewing');
  });
});
