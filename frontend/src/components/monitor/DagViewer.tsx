import { Button, Card, Space, Tag, Typography } from 'antd';

import { useMonitorStore } from '../../stores/monitorStore';

const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  ready: 'processing',
  running: 'success',
  paused: 'warning',
  pause_requested: 'gold',
  skipped: 'purple',
  failed: 'error',
  done: 'cyan',
};

interface DagViewerProps {
  onSelectNode?: (nodeId: string) => void;
}

export function DagViewer({ onSelectNode }: DagViewerProps) {
  const orderedNodeIds = useMonitorStore((state) => state.orderedNodeIds);
  const nodesById = useMonitorStore((state) => state.nodesById);
  const selectedNodeId = useMonitorStore((state) => state.selectedNodeId);
  const selectNode = useMonitorStore((state) => state.selectNode);

  return (
    <Card title="DAG Overview" className="monitor-card">
      <Space direction="vertical" size="small" style={{ width: '100%' }}>
        {orderedNodeIds.map((nodeId) => {
          const node = nodesById[nodeId];
          if (!node) {
            return null;
          }

          return (
            <Button
              key={node.id}
              block
              type={selectedNodeId === node.id ? 'primary' : 'default'}
              className={`monitor-node-button monitor-node-${node.status}`}
              onClick={() => {
                selectNode(node.id);
                onSelectNode?.(node.id);
              }}
              style={{ height: 'auto', textAlign: 'left', padding: 12 }}
            >
              <Space
                align="center"
                style={{ width: '100%', justifyContent: 'space-between' }}
              >
                <Space direction="vertical" size={2} style={{ alignItems: 'flex-start' }}>
                  <Typography.Text strong>{node.title}</Typography.Text>
                  <Typography.Text type="secondary">
                    {node.agent_role ?? 'unassigned'}
                    {node.depends_on?.length ? ` / depends on ${node.depends_on.length}` : ''}
                  </Typography.Text>
                </Space>
                <Space wrap size={8}>
                  {node.assigned_agent ? <Tag>{node.assigned_agent}</Tag> : null}
                  <Tag color={STATUS_COLORS[node.status] ?? 'default'}>
                    {node.status}
                  </Tag>
                </Space>
              </Space>
            </Button>
          );
        })}
      </Space>
    </Card>
  );
}
