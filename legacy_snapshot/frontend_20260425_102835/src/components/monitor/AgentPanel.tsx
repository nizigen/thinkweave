import { Card, Empty, Space, Tag, Typography } from 'antd';

import { useMonitorStore } from '../../stores/monitorStore';

export function AgentPanel() {
  const selectedNodeId = useMonitorStore((state) => state.selectedNodeId);
  const nodesById = useMonitorStore((state) => state.nodesById);
  const agentStatusByNodeId = useMonitorStore((state) => state.agentStatusByNodeId);
  const orderedNodeIds = useMonitorStore((state) => state.orderedNodeIds);

  const entries = orderedNodeIds
    .map((nodeId) => {
      const node = nodesById[nodeId];
      if (!node) {
        return null;
      }
      return {
        node,
        status: agentStatusByNodeId[nodeId] ?? null,
      };
    })
    .filter((entry) => entry !== null)
    .filter((entry) => !selectedNodeId || entry.node.id === selectedNodeId);

  return (
    <Card title="Agent Activity" className="monitor-card">
      {entries.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No agent activity yet" />
      ) : (
        <div className="monitor-stack">
          {entries.map((entry) => (
            <div key={entry.node.id} className="monitor-list-item">
              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                <Space wrap>
                  <Typography.Text strong>{entry.node.title}</Typography.Text>
                  <Tag color={entry.node.status === 'running' ? 'success' : 'default'}>
                    {entry.node.status}
                  </Tag>
                </Space>
                <Typography.Text type="secondary">
                  {String(
                    entry.status?.agent_name ??
                      entry.node.assigned_agent ??
                      entry.node.agent_role ??
                      'unassigned',
                  )}
                </Typography.Text>
                {entry.status ? (
                  <Typography.Text>
                    {String(entry.status.message ?? entry.status.status ?? 'heartbeat')}
                  </Typography.Text>
                ) : null}
                {entry.node.routing_reason ? (
                  <Typography.Text type="secondary">
                    {`routing: ${entry.node.routing_reason} (${entry.node.routing_status ?? 'unknown'})`}
                  </Typography.Text>
                ) : null}
              </Space>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
