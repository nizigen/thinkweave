import { Card, Progress, Space, Tag, Typography } from 'antd';

import { useMonitorStore } from '../../stores/monitorStore';

const FSM_PERCENT: Record<string, number> = {
  pending: 10,
  planning: 20,
  decomposing: 30,
  writing: 65,
  reviewing: 85,
  finalizing: 95,
  completed: 100,
};

const CONTROL_COLORS: Record<string, string> = {
  active: 'success',
  pause_requested: 'gold',
  paused: 'warning',
};

export function FsmProgress() {
  const taskSnapshot = useMonitorStore((state) => state.taskSnapshot);
  const controlState = useMonitorStore((state) => state.controlState);
  const selectedNodeId = useMonitorStore((state) => state.selectedNodeId);

  const fsmState = taskSnapshot?.fsm_state ?? 'pending';
  const percent = FSM_PERCENT[fsmState] ?? 0;

  return (
    <Card title="FSM Progress" className="monitor-card monitor-progress-card">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Typography.Title level={4} style={{ marginBottom: 4 }}>
            {taskSnapshot?.title ?? 'Task Monitor'}
          </Typography.Title>
          <Typography.Text type="secondary">
            FSM state: {fsmState}
          </Typography.Text>
        </div>
        <Progress percent={percent} strokeColor="#3b82f6" trailColor="#1f2937" />
        <Space wrap>
          <Tag color="blue">Task {taskSnapshot?.status ?? 'unknown'}</Tag>
          <Tag color={CONTROL_COLORS[controlState?.status ?? 'active'] ?? 'default'}>
            Control {controlState?.status ?? 'active'}
          </Tag>
          <Tag color={selectedNodeId ? 'purple' : 'default'}>
            {selectedNodeId ? `Node ${selectedNodeId}` : 'No node selected'}
          </Tag>
        </Space>
      </Space>
    </Card>
  );
}
