import { Card, Empty, Tag, Typography } from 'antd';

import { useMonitorStore } from '../../stores/monitorStore';

const EVENT_COLORS: Record<string, string> = {
  node_update: 'processing',
  dag_update: 'cyan',
  log: 'default',
  agent_status: 'gold',
  chapter_preview: 'purple',
  review_score: 'success',
  consistency_result: 'warning',
};

function formatTimestamp(timestamp: number) {
  if (!timestamp) {
    return '--';
  }

  const value = timestamp > 1_000_000_000_000 ? timestamp : timestamp * 1000;
  return new Date(value).toLocaleTimeString('zh-CN', {
    hour12: false,
  });
}

export function LogStream() {
  const events = useMonitorStore((state) => state.events);
  const selectedNodeId = useMonitorStore((state) => state.selectedNodeId);

  const visibleEvents = events
    .filter((event) => !selectedNodeId || !event.node_id || event.node_id === selectedNodeId)
    .slice(-25)
    .reverse();

  return (
    <Card title="Log Stream" className="monitor-card monitor-log-card">
      {visibleEvents.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="No monitor events yet"
        />
      ) : (
        <div className="monitor-stack">
          {visibleEvents.map((event, index) => (
            <div
              key={`${event.type}-${event.timestamp}-${event.node_id}-${index}`}
              className="monitor-log-item monitor-list-item"
            >
              <div className="monitor-log-meta">
                <Tag color={EVENT_COLORS[event.type] ?? 'default'}>{event.type}</Tag>
                <Typography.Text type="secondary">
                  {formatTimestamp(event.timestamp)}
                </Typography.Text>
              </div>
              <Typography.Text className="monitor-log-body">
                {event.from_agent || 'system'}
                {event.node_id ? ` / ${event.node_id}` : ''}
              </Typography.Text>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
