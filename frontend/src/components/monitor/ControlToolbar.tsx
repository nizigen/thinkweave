import { Button, Card, Space } from 'antd';

import { useMonitorStore } from '../../stores/monitorStore';

interface ControlToolbarProps {
  onPause: () => void;
  onResume: () => void;
  onSkip: () => void;
  onRetry: () => void;
  busyAction?: 'pause' | 'resume' | 'skip' | 'retry' | null;
}

export function ControlToolbar({
  onPause,
  onResume,
  onSkip,
  onRetry,
  busyAction = null,
}: ControlToolbarProps) {
  const selectedNodeId = useMonitorStore((state) => state.selectedNodeId);
  const nodesById = useMonitorStore((state) => state.nodesById);
  const controlState = useMonitorStore((state) => state.controlState);

  const selectedNode = selectedNodeId ? nodesById[selectedNodeId] : null;
  const controlStatus = controlState?.status ?? 'active';

  const canPause = controlStatus === 'active';
  const canResume = controlStatus === 'paused';
  const canSkip = Boolean(
    selectedNode && ['pending', 'ready', 'running'].includes(selectedNode.status),
  );
  const canRetry = Boolean(
    selectedNode && ['failed', 'skipped'].includes(selectedNode.status),
  );

  return (
    <Card title="Controls" className="monitor-card">
      <Space wrap>
        <Button onClick={onPause} disabled={!canPause} loading={busyAction === 'pause'}>
          Pause
        </Button>
        <Button
          onClick={onResume}
          disabled={!canResume}
          loading={busyAction === 'resume'}
        >
          Resume
        </Button>
        <Button onClick={onSkip} disabled={!canSkip} loading={busyAction === 'skip'}>
          Skip
        </Button>
        <Button onClick={onRetry} disabled={!canRetry} loading={busyAction === 'retry'}>
          Retry
        </Button>
      </Space>
    </Card>
  );
}
