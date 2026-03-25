import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMonitorStore } from '../../../stores/monitorStore';
import { ControlToolbar } from '../ControlToolbar';

describe('ControlToolbar', () => {
  const noop = vi.fn();

  beforeEach(() => {
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
          preview_cache: {},
          review_scores: {},
        },
      },
      nodes: [
        {
          id: 'node-1',
          task_id: 'task-1',
          title: 'Outline',
          agent_role: 'writer',
          assigned_agent: null,
          status: 'running',
          depends_on: null,
          retry_count: 0,
          started_at: null,
          finished_at: null,
        },
      ],
    });
  });

  it('disables node-level actions when no node is selected', () => {
    render(
      <ControlToolbar
        onPause={noop}
        onResume={noop}
        onSkip={noop}
        onRetry={noop}
      />,
    );

    expect(screen.getByRole('button', { name: /pause/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /resume/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /skip/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /retry/i })).toBeDisabled();
  });

  it('enables matching controls for the selected node and paused task state', () => {
    useMonitorStore.getState().selectNode('node-1');
    useMonitorStore.getState().ingestEvent({
      type: 'dag_update',
      task_id: 'task-1',
      node_id: '',
      from_agent: 'scheduler',
      timestamp: 1,
      payload: { control: { status: 'paused' } },
    });

    render(
      <ControlToolbar
        onPause={noop}
        onResume={noop}
        onSkip={noop}
        onRetry={noop}
      />,
    );

    expect(screen.getByRole('button', { name: /pause/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /resume/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /skip/i })).toBeEnabled();
  });
});
