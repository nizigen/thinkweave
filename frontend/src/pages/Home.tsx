/**
 * 任务创建页
 * Ref: IMPLEMENTATION_PLAN.md Step 6.4
 * Ref: APP_FLOW.md 旅程1 任务创建
 * Ref: FRONTEND_GUIDELINES.md 组件规范 / 颜色系统
 */
import { useState } from 'react';
import {
  Form,
  Input,
  Select,
  InputNumber,
  Button,
  Typography,
  Card,
  Space,
  message,
} from 'antd';
import {
  SendOutlined,
  FileTextOutlined,
  BookOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { Task } from '../stores/taskStore';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

interface CreateTaskPayload {
  title: string;
  mode: string;
  depth: string;
  target_words: number;
  draft_text?: string;
}

const MODE_OPTIONS = [
  { value: 'report',  label: '技术报告', icon: <FileTextOutlined />, desc: '结构化技术文档，含引言、方法、结论' },
  { value: 'novel',   label: '小说',     icon: <BookOutlined />,     desc: '叙事性长篇创意写作，含章节结构' },
  { value: 'custom',  label: '自定义',   icon: <SettingOutlined />,  desc: '根据描述自由生成，灵活定制' },
];

const DEPTH_OPTIONS = [
  { value: 'quick',    label: '快速',  words: '~3,000 字',  desc: '快速生成，适合概览' },
  { value: 'standard', label: '标准',  words: '~10,000 字', desc: '均衡质量与速度' },
  { value: 'deep',     label: '深入',  words: '~20,000 字', desc: '深度研究，高质量输出' },
];

const DEFAULT_WORDS: Record<string, number> = {
  quick: 3000,
  standard: 10000,
  deep: 20000,
};

export default function Home() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState('report');
  const [depth, setDepth] = useState('standard');

  const handleDepthChange = (val: string) => {
    setDepth(val);
    form.setFieldValue('target_words', DEFAULT_WORDS[val] ?? 10000);
  };

  const handleSubmit = async (values: CreateTaskPayload) => {
    setLoading(true);
    // 请求浏览器通知权限
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
    try {
      const resp = await apiClient.post<Task>('/tasks', values);
      const task = resp.data;
      message.success('任务创建成功，正在跳转监控页…');
      navigate(`/monitor/${task.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      message.error(typeof detail === 'string' ? detail : '创建失败，请检查参数后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}
    >
      {/* 顶部色条 */}
      <div style={{
        height: 2,
        background: 'linear-gradient(90deg, #6366F100, #6366F160, #6366F100)',
        marginBottom: 28,
        borderRadius: 1,
      }} />

      <Title level={3} style={{ color: '#F8FAFC', marginBottom: 4 }}>新建生成任务</Title>
      <Paragraph style={{ color: '#94A3B8', marginBottom: 28 }}>
        描述你的主题，AI 将自动规划章节结构并并行生成内容。
      </Paragraph>

      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{ mode: 'report', depth: 'standard', target_words: 10000 }}
      >
        {/* 标题 */}
        <Form.Item
          name="title"
          label={<Text style={{ color: '#CBD5E1' }}>主题 / 标题</Text>}
          rules={[{ required: true, min: 6, message: '请输入至少 6 个字符的主题' }]}
        >
          <TextArea
            rows={2}
            placeholder="例如：2025年量子计算技术发展报告"
            style={{ background: '#0D0D14', borderColor: '#2A2A3E', color: '#F1F5F9', resize: 'none' }}
            maxLength={500}
            showCount
          />
        </Form.Item>

        {/* 模式选择 */}
        <Form.Item
          name="mode"
          label={<Text style={{ color: '#CBD5E1' }}>生成模式</Text>}
        >
          <div style={{ display: 'flex', gap: 12 }}>
            {MODE_OPTIONS.map((opt) => (
              <Card
                key={opt.value}
                onClick={() => { setMode(opt.value); form.setFieldValue('mode', opt.value); }}
                style={{
                  flex: 1,
                  cursor: 'pointer',
                  background: mode === opt.value ? '#1F1F2E' : '#111118',
                  border: `1px solid ${mode === opt.value ? '#6366F1' : '#2A2A3E'}`,
                  borderRadius: 8,
                  transition: 'all 0.15s',
                  boxShadow: mode === opt.value ? '0 0 12px rgba(99,102,241,0.2)' : 'none',
                }}
                bodyStyle={{ padding: '12px 14px' }}
              >
                <Space direction="vertical" size={2}>
                  <Space style={{ color: mode === opt.value ? '#818CF8' : '#94A3B8' }}>
                    {opt.icon}
                    <Text style={{ color: mode === opt.value ? '#F1F5F9' : '#CBD5E1', fontWeight: 500 }}>
                      {opt.label}
                    </Text>
                  </Space>
                  <Text style={{ color: '#64748B', fontSize: 12 }}>{opt.desc}</Text>
                </Space>
              </Card>
            ))}
          </div>
        </Form.Item>

        {/* 深度选择 */}
        <Form.Item
          name="depth"
          label={<Text style={{ color: '#CBD5E1' }}>研究深度</Text>}
        >
          <div style={{ display: 'flex', gap: 12 }}>
            {DEPTH_OPTIONS.map((opt) => (
              <Card
                key={opt.value}
                onClick={() => handleDepthChange(opt.value)}
                style={{
                  flex: 1,
                  cursor: 'pointer',
                  background: depth === opt.value ? '#1F1F2E' : '#111118',
                  border: `1px solid ${depth === opt.value ? '#6366F1' : '#2A2A3E'}`,
                  borderRadius: 8,
                  transition: 'all 0.15s',
                }}
                bodyStyle={{ padding: '12px 14px' }}
              >
                <Space direction="vertical" size={2}>
                  <Text style={{ color: depth === opt.value ? '#F1F5F9' : '#CBD5E1', fontWeight: 500 }}>
                    {opt.label}
                    <Text style={{ color: '#6366F1', marginLeft: 6, fontSize: 12 }}>{opt.words}</Text>
                  </Text>
                  <Text style={{ color: '#64748B', fontSize: 12 }}>{opt.desc}</Text>
                </Space>
              </Card>
            ))}
          </div>
        </Form.Item>

        {/* 目标字数 */}
        <Form.Item
          name="target_words"
          label={<Text style={{ color: '#CBD5E1' }}>目标字数</Text>}
        >
          <InputNumber
            min={500}
            max={200000}
            step={500}
            style={{ width: '100%', background: '#0D0D14', borderColor: '#2A2A3E' }}
            formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
            parser={(v) => Number((v ?? '').replace(/,/g, '')) as 500}
          />
        </Form.Item>

        {/* 草稿（可选） */}
        <Form.Item
          name="draft_text"
          label={
            <Space>
              <Text style={{ color: '#CBD5E1' }}>草稿内容</Text>
              <Text style={{ color: '#64748B', fontSize: 12 }}>（可选）粘贴已有内容从 PRE_REVIEW 阶段续写</Text>
            </Space>
          }
        >
          <TextArea
            rows={4}
            placeholder="粘贴已有草稿文本…"
            style={{ background: '#0D0D14', borderColor: '#2A2A3E', color: '#F1F5F9', resize: 'vertical' }}
            maxLength={200000}
          />
        </Form.Item>

        <Form.Item style={{ marginTop: 8 }}>
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            icon={<SendOutlined />}
            size="large"
            style={{
              width: '100%',
              height: 48,
              background: '#6366F1',
              borderColor: '#6366F1',
              fontSize: 16,
              fontWeight: 600,
              boxShadow: '0 2px 12px rgba(99,102,241,0.35)',
            }}
          >
            {loading ? '正在创建任务…' : '开始生成'}
          </Button>
        </Form.Item>
      </Form>
    </motion.div>
  );
}
