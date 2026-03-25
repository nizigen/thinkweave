import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMonitorStore } from '../../../stores/monitorStore';
import { DagViewer } from '../DagViewer';

describe('DagViewer', () => {
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
          assigned_agent: 'agent-1',
          status: 'running',
          depends_on: null,
          retry_count: 0,
          started_at: null,
          finished_at: null,
        },
        {
          id: 'node-2',
          task_id: 'task-1',
          title: 'Review',
          agent_role: 'reviewer',
          assigned_agent: null,
          status: 'pending',
          depends_on: ['node-1'],
          retry_count: 0,
          started_at: null,
          finished_at: null,
        },
      ],
    });
  });

  it('renders node labels and status badges', () => {
    render(<DagViewer />);

    expect(screen.getByText('Outline')).toBeInTheDocument();
    expect(screen.getByText('running')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
    expect(screen.getByText('pending')).toBeInTheDocument();
  });

  it('emits node selection through the store', () => {
    const onSelect = vi.fn();

    render(<DagViewer onSelectNode={onSelect} />);

    fireEvent.click(screen.getByRole('button', { name: /outline/i }));

    expect(useMonitorStore.getState().selectedNodeId).toBe('node-1');
    expect(onSelect).toHaveBeenCalledWith('node-1');
  });
});
