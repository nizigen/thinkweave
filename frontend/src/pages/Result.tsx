import { useParams } from 'react-router-dom';
import { Typography } from 'antd';

const { Title } = Typography;

export default function Result() {
  const { taskId } = useParams<{ taskId: string }>();
  return <Title level={3}>结果展示 — 任务 {taskId}</Title>;
}
