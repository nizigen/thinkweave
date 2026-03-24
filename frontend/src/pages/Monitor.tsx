import { useParams } from 'react-router-dom';
import { Alert, Space, Tag, Typography } from 'antd';

import { useTaskWebSocket } from '../hooks/useTaskWebSocket';

const { Title } = Typography;

export default function Monitor() {
  const { taskId } = useParams<{ taskId: string }>();
  const { connectionState, reconnectAttempt, lastError } = useTaskWebSocket(taskId);

  return (
    <Space direction="vertical" size="middle">
      <Title level={3}>编排监控 — 任务 {taskId}</Title>
      <Tag color={connectionState === 'connected' ? 'success' : 'processing'}>
        连接状态：{connectionState}
      </Tag>
      <Typography.Text>重连次数：{reconnectAttempt}</Typography.Text>
      {lastError ? <Alert type="error" showIcon message={lastError} /> : null}
    </Space>
  );
}
