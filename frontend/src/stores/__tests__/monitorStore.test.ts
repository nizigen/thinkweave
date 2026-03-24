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
});
