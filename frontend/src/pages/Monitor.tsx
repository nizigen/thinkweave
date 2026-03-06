import { useParams } from 'react-router-dom';
import { Typography } from 'antd';

const { Title } = Typography;

export default function Monitor() {
  const { taskId } = useParams<{ taskId: string }>();
  return <Title level={3}>编排监控 — 任务 {taskId}</Title>;
}
