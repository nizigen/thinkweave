import { Card, Empty, Space, Statistic, Tag, Typography } from 'antd';

import { useMonitorStore } from '../../stores/monitorStore';

export function ChapterPreview() {
  const selectedNodeId = useMonitorStore((state) => state.selectedNodeId);
  const nodesById = useMonitorStore((state) => state.nodesById);
  const chapterPreviewByNodeId = useMonitorStore(
    (state) => state.chapterPreviewByNodeId,
  );
  const reviewScoreByNodeId = useMonitorStore(
    (state) => state.reviewScoreByNodeId,
  );
  const consistencyResultByNodeId = useMonitorStore(
    (state) => state.consistencyResultByNodeId,
  );

  const node = selectedNodeId ? nodesById[selectedNodeId] : null;
  const preview = selectedNodeId ? chapterPreviewByNodeId[selectedNodeId] : null;
  const reviewScore = selectedNodeId ? reviewScoreByNodeId[selectedNodeId] : null;
  const consistency = selectedNodeId
    ? consistencyResultByNodeId[selectedNodeId]
    : null;

  return (
    <Card title="Chapter Preview" className="monitor-card monitor-preview-card">
      {!node ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="Select a node to inspect preview output"
        />
      ) : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div className="monitor-preview-header">
            <div>
              <Typography.Title level={5} style={{ marginBottom: 0 }}>
                {node.title}
              </Typography.Title>
              <Typography.Text type="secondary">
                {node.agent_role ?? 'unknown'} agent
              </Typography.Text>
            </div>
            <Space wrap>
              {typeof reviewScore?.score === 'number' ? (
                <Statistic title="Review Score" value={reviewScore.score as number} />
              ) : null}
              {consistency ? (
                <Tag color="gold">
                  Consistency {String(consistency.status ?? consistency.result ?? 'updated')}
                </Tag>
              ) : null}
            </Space>
          </div>
          <div className="monitor-preview-body">
            {preview?.content ? (
              <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                {String(preview.content)}
              </Typography.Paragraph>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="No preview cached for this node yet"
              />
            )}
          </div>
          {consistency ? (
            <div className="monitor-consistency-panel">
              <Typography.Text strong>Consistency Summary</Typography.Text>
              <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                {String(
                  consistency.summary ??
                    consistency.message ??
                    consistency.result ??
                    'Consistency result received.',
                )}
              </Typography.Paragraph>
            </div>
          ) : null}
        </Space>
      )}
    </Card>
  );
}
