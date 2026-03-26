/**
 * 大纲确认页
 * Ref: IMPLEMENTATION_PLAN.md Step 6.4
 * Ref: APP_FLOW.md 大纲编辑页
 * Ref: FRONTEND_GUIDELINES.md 组件规范
 */
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Button,
  Typography,
  Space,
  Spin,
  Alert,
  message,
} from 'antd';
import {
  CheckOutlined,
  EditOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import apiClient from '../api/client';

const { Title, Text, Paragraph } = Typography;

interface OutlineData {
  task_id: string;
  content: string;
  version: number;
  confirmed: boolean;
}

export default function Outline() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [outline, setOutline] = useState<OutlineData | null>(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) return;
    setLoading(true);
    apiClient.get<OutlineData>(`/tasks/${taskId}/outline`)
      .then((r) => {
        setOutline(r.data);
        setContent(r.data.content);
      })
      .catch(() => setError('无法加载大纲，请稍后重试'))
      .finally(() => setLoading(false));
  }, [taskId]);

  const handleConfirm = async () => {
    if (!taskId) return;
    setConfirming(true);
    try {
      await apiClient.post(`/tasks/${taskId}/outline/confirm`, { content });
      message.success('大纲已确认，进入写作阶段');
      navigate(`/monitor/${taskId}`);
    } catch {
      message.error('确认失败，请重试');
    } finally {
      setConfirming(false);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (error || !outline) {
    return (
      <div style={{ padding: 24 }}>
        <Alert type="error" message={error ?? '大纲不存在'} />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      style={{ maxWidth: 800, margin: '0 auto', padding: 24 }}
    >
      {/* 顶部色条 */}
      <div style={{
        height: 2,
        background: 'linear-gradient(90deg, #6366F100, #6366F160, #6366F100)',
        marginBottom: 24,
        borderRadius: 1,
      }} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ color: '#F8FAFC', margin: 0 }}>确认大纲</Title>
          <Text style={{ color: '#94A3B8' }}>审阅并编辑章节结构，确认后进入写作阶段</Text>
        </div>
        <Space>
          <Button
            type="primary"
            icon={<CheckOutlined />}
            loading={confirming}
            onClick={handleConfirm}
            size="large"
            style={{
              background: '#6366F1',
              borderColor: '#6366F1',
              boxShadow: '0 2px 12px rgba(99,102,241,0.35)',
            }}
          >
            确认大纲
          </Button>
          <Button
            icon={<ArrowRightOutlined />}
            onClick={() => navigate(`/monitor/${taskId}`)}
            style={{ borderColor: '#2A2A3E', color: '#94A3B8' }}
          >
            跳过
          </Button>
        </Space>
      </div>

      {/* 编辑区 */}
      <div style={{
        background: '#111118',
        border: '1px solid #2A2A3E',
        borderRadius: 8,
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '10px 16px',
          background: '#0D0D14',
          borderBottom: '1px solid #1A1A26',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          <EditOutlined style={{ color: '#6366F1' }} />
          <Text style={{ color: '#CBD5E1', fontSize: 13 }}>Markdown 编辑器 — 版本 {outline.version}</Text>
        </div>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          style={{
            width: '100%',
            minHeight: 480,
            background: '#111118',
            color: '#F1F5F9',
            border: 'none',
            outline: 'none',
            padding: '16px 20px',
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            fontSize: 14,
            lineHeight: 1.7,
            resize: 'vertical',
            boxSizing: 'border-box',
          }}
          placeholder="# 文档标题\n\n## 第一章 概述\n\n## 第二章 主体\n"
          spellCheck={false}
        />
      </div>

      <Paragraph style={{ color: '#64748B', fontSize: 12, marginTop: 12 }}>
        提示：使用 # 标记一级标题，## 标记二级标题。确认后大纲将固定，写作 Agent 按此结构并行生成内容。
      </Paragraph>
    </motion.div>
  );
}
