import { useParams } from 'react-router-dom';
import { Typography } from 'antd';

const { Title } = Typography;

export default function Outline() {
  const { taskId } = useParams<{ taskId: string }>();
  return <Title level={3}>大纲编辑 — 任务 {taskId}</Title>;
}
