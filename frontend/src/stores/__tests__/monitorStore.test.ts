import { beforeEach, describe, expect, it } from 'vitest';

import { useMonitorStore } from '../monitorStore';

describe('monitorStore', () => {
  beforeEach(() => {
    useMonitorStore.getState().reset();
  });

  it('resets connection state and active task', () => {
    useMonitorStore.getState().setConnectionState('connected');
    useMonitorStore.getState().markReconnectAttempt(3);
    useMonitorStore.getState().reset('task-1');

    expect(useMonitorStore.getState().activeTaskId).toBe('task-1');
    expect(useMonitorStore.getState().connectionState).toBe('disconnected');
    expect(useMonitorStore.getState().reconnectAttempt).toBe(0);
  });

  it('keeps only the latest 500 events', () => {
    const { ingestEvent } = useMonitorStore.getState();

    for (let index = 0; index < 520; index += 1) {
      ingestEvent({
        type: 'log',
        task_id: 'task-1',
        node_id: `node-${index}`,
        from_agent: 'writer',
        timestamp: index,
        payload: { index },
      });
    }

    const state = useMonitorStore.getState();
    expect(state.events).toHaveLength(500);
    expect(state.events[0]?.node_id).toBe('node-20');
    expect(state.events.at(-1)?.node_id).toBe('node-519');
  });

  it('ignores events for a different active task', () => {
    useMonitorStore.getState().reset('task-1');
    useMonitorStore.getState().ingestEvent({
      type: 'log',
      task_id: 'task-2',
      node_id: 'node-1',
      from_agent: 'writer',
      timestamp: 1,
      payload: {},
    });

    expect(useMonitorStore.getState().events).toHaveLength(0);
  });

  it('hydrates normalized node map and control state from task snapshot', () => {
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
          status: 'paused',
          preview_cache: {
            'node-1': { content: 'preview body' },
          },
          review_scores: {
            'node-1': { score: 91 },
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
          started_at: '2026-03-24T00:00:00Z',
          finished_at: null,
        },
      ],
    });

    const state = useMonitorStore.getState();
    expect(state.nodesById['node-1']?.status).toBe('running');
    expect(state.controlState?.status).toBe('paused');
    expect(state.chapterPreviewByNodeId['node-1']?.content).toBe('preview body');
    expect(state.reviewScoreByNodeId['node-1']?.score).toBe(91);
  });

  it('clears volatile event caches during snapshot hydration', () => {
    const store = useMonitorStore.getState();
    store.reset('task-1');
    store.setTaskSnapshot({
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

    store.ingestEvent({
      type: 'agent_status',
      task_id: 'task-1',
      node_id: 'node-1',
      from_agent: 'writer',
      timestamp: 1,
      payload: { agent_name: 'writer-1' },
    });
    store.ingestEvent({
      type: 'consistency_result',
      task_id: 'task-1',
      node_id: 'node-1',
      from_agent: 'consistency',
      timestamp: 2,
      payload: { passed: true },
    });

    store.setTaskSnapshot({
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
          preview_cache: {},
          review_scores: {},
        },
      },
      nodes: [
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

    const state = useMonitorStore.getState();
    expect(state.agentStatusByNodeId).toEqual({});
    expect(state.consistencyResultByNodeId).toEqual({});
  });

  it('ingests normalized node and monitor detail events', () => {
    const store = useMonitorStore.getState();
    store.reset('task-1');
    store.setTaskSnapshot({
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
          status: 'pending',
          depends_on: null,
          retry_count: 0,
          started_at: null,
          finished_at: null,
        },
      ],
    });

    store.ingestEvent({
      type: 'node_update',
      task_id: 'task-1',
      node_id: 'node-1',
      from_agent: 'writer',
      timestamp: 1,
      payload: { status: 'running', assigned_agent: 'agent-1' },
    });
    store.ingestEvent({
      type: 'agent_status',
      task_id: 'task-1',
      node_id: 'node-1',
      from_agent: 'writer',
      timestamp: 2,
      payload: { agent_name: 'writer-1' },
    });
    store.ingestEvent({
      type: 'chapter_preview',
      task_id: 'task-1',
      node_id: 'node-1',
      from_agent: 'writer',
      timestamp: 3,
      payload: { content: 'preview body' },
    });
    store.ingestEvent({
      type: 'review_score',
      task_id: 'task-1',
      node_id: 'node-1',
      from_agent: 'reviewer',
      timestamp: 4,
      payload: { score: 89 },
    });
    store.ingestEvent({
      type: 'consistency_result',
      task_id: 'task-1',
      node_id: 'node-1',
      from_agent: 'consistency',
      timestamp: 5,
      payload: { passed: true },
    });
    store.ingestEvent({
      type: 'dag_update',
      task_id: 'task-1',
      node_id: '',
      from_agent: 'scheduler',
      timestamp: 6,
      payload: { control: { status: 'pause_requested' } },
    });
    store.selectNode('node-1');

    const state = useMonitorStore.getState();
    expect(state.nodesById['node-1']?.status).toBe('running');
    expect(state.agentStatusByNodeId['node-1']?.agent_name).toBe('writer-1');
    expect(state.chapterPreviewByNodeId['node-1']?.content).toBe('preview body');
    expect(state.reviewScoreByNodeId['node-1']?.score).toBe(89);
    expect(state.consistencyResultByNodeId['node-1']?.passed).toBe(true);
    expect(state.controlState?.status).toBe('pause_requested');
    expect(state.selectedNodeId).toBe('node-1');
  });
});
