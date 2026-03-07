/**
 * Agent 详情抽屉
 * Ref: APP_FLOW.md — 旅程2 Agent详情
 * Ref: IMPLEMENTATION_PLAN.md Step 1.2 — Agent详情抽屉
 */
import { useCallback, useState } from 'react';
import {
  Drawer,
  Button,
  Tag,
  Space,
  Descriptions,
  Popconfirm,
  Select,
  message,
  Empty,
  Divider,
  Typography,
} from 'antd';
import {
  DeleteOutlined,
  SwapOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import type { AgentData } from '../../api/agents';
import { useAgentStore } from '../../stores/agentStore';

const { Text, Paragraph } = Typography;

/* ── Display maps ── */
const ROLE_LABELS: Record<string, string> = {
  orchestrator: '编排 (Orchestrator)',
  manager: '管理 (Manager)',
  outline: '大纲 (Outline)',
  writer: '写作 (Writer)',
  reviewer: '审查 (Reviewer)',
  consistency: '一致性 (Consistency)',
};

const LAYER_LABELS: Record<number, string> = {
  0: 'L0 — 编排层',
  1: 'L1 — 管理层',
  2: 'L2 — 执行层',
};

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  idle: { label: '空闲', color: '#10B981' },
  busy: { label: '忙碌', color: '#3B82F6' },
  offline: { label: '离线', color: '#6B7280' },
};

const STATUS_OPTIONS = [
  { value: 'idle', label: '空闲 (Idle)' },
  { value: 'busy', label: '忙碌 (Busy)' },
  { value: 'offline', label: '离线 (Offline)' },
];

interface Props {
  agent: AgentData | null;
  open: boolean;
  onClose: () => void;
}

export default function AgentDetailDrawer({ agent, open, onClose }: Props) {
  const { updateAgentStatus, deleteAgent } = useAgentStore();
  const [statusLoading, setStatusLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const handleStatusChange = useCallback(
    async (newStatus: string) => {
      if (!agent) return;
      setStatusLoading(true);
      try {
        await updateAgentStatus(agent.id, newStatus as 'idle' | 'busy' | 'offline');
        message.success('状态已更新');
      } catch {
        message.error('状态更新失败');
      } finally {
        setStatusLoading(false);
      }
    },
    [agent, updateAgentStatus],
  );

  const handleDelete = useCallback(async () => {
    if (!agent) return;
    setDeleteLoading(true);
    try {
      await deleteAgent(agent.id);
      message.success(`Agent "${agent.name}" 已删除`);
      onClose();
    } catch {
      message.error('删除失败');
    } finally {
      setDeleteLoading(false);
    }
  }, [agent, deleteAgent, onClose]);

  if (!agent) return null;

  const statusCfg = STATUS_CONFIG[agent.status] ?? STATUS_CONFIG.offline;
  const createdAt = new Date(agent.created_at).toLocaleString('zh-CN');

  return (
    <Drawer
      title={null}
      open={open}
      onClose={onClose}
      width={420}
      styles={{
        body: { padding: 0 },
        header: { display: 'none' },
      }}
    >
      {/* Header card */}
      <div
        style={{
          padding: '28px 24px 20px',
          background: 'linear-gradient(135deg, #111118 0%, #1A1A26 100%)',
          borderBottom: '1px solid #2A2A3E',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 20, fontWeight: 600, color: '#F1F5F9' }}>
            {agent.name}
          </Text>
          <Tag
            style={{
              border: 'none',
              background: `${statusCfg.color}18`,
              color: statusCfg.color,
              fontWeight: 500,
            }}
          >
            <span
              style={{
                display: 'inline-block',
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: statusCfg.color,
                marginRight: 6,
                ...(agent.status === 'busy'
                  ? { animation: 'statusPulse 1.5s ease-in-out infinite' }
                  : {}),
              }}
            />
            {statusCfg.label}
          </Tag>
        </div>
        <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 4, display: 'block' }}>
          {ROLE_LABELS[agent.role] ?? agent.role} · {LAYER_LABELS[agent.layer] ?? `L${agent.layer}`}
        </Text>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, color: '#475569', fontSize: 12 }}>
          <ClockCircleOutlined />
          <span>创建于 {createdAt}</span>
        </div>
      </div>

      <div style={{ padding: '20px 24px' }}>
        {/* Basic info */}
        <Descriptions column={1} size="small" labelStyle={{ color: '#94A3B8' }}>
          <Descriptions.Item label="模型">{agent.model}</Descriptions.Item>
          <Descriptions.Item label="层级">{LAYER_LABELS[agent.layer]}</Descriptions.Item>
        </Descriptions>

        {agent.capabilities && (
          <>
            <Divider style={{ margin: '16px 0', borderColor: '#1E1E2E' }} />
            <Text style={{ color: '#94A3B8', fontSize: 12, marginBottom: 8, display: 'block' }}>
              能力描述
            </Text>
            <Paragraph
              style={{
                color: '#F1F5F9',
                background: '#111118',
                padding: '12px 16px',
                borderRadius: 8,
                border: '1px solid #1E1E2E',
                fontSize: 13,
                marginBottom: 0,
              }}
            >
              {agent.capabilities}
            </Paragraph>
          </>
        )}

        {/* Status toggle */}
        <Divider style={{ margin: '20px 0 16px', borderColor: '#1E1E2E' }} />
        <Text style={{ color: '#94A3B8', fontSize: 12, marginBottom: 8, display: 'block' }}>
          切换状态
        </Text>
        <Select
          value={agent.status}
          options={STATUS_OPTIONS}
          onChange={handleStatusChange}
          loading={statusLoading}
          style={{ width: '100%' }}
          suffixIcon={<SwapOutlined />}
        />

        {/* Stats placeholder */}
        <Divider style={{ margin: '20px 0 16px', borderColor: '#1E1E2E' }} />
        <Text style={{ color: '#94A3B8', fontSize: 12, marginBottom: 12, display: 'block' }}>
          执行统计
        </Text>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr',
            gap: 12,
          }}
        >
          {['任务总数', '成功率', '平均耗时'].map((label) => (
            <div
              key={label}
              style={{
                background: '#111118',
                border: '1px solid #1E1E2E',
                borderRadius: 8,
                padding: '12px 8px',
                textAlign: 'center',
              }}
            >
              <div style={{ color: '#475569', fontSize: 11 }}>{label}</div>
              <div style={{ color: '#94A3B8', fontSize: 18, fontWeight: 600, marginTop: 4 }}>--</div>
            </div>
          ))}
        </div>

        {/* History placeholder */}
        <Divider style={{ margin: '20px 0 16px', borderColor: '#1E1E2E' }} />
        <Text style={{ color: '#94A3B8', fontSize: 12, marginBottom: 12, display: 'block' }}>
          历史任务
        </Text>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <Text style={{ color: '#475569', fontSize: 13 }}>
              该 Agent 尚未参与任何任务
            </Text>
          }
        />

        {/* Delete */}
        <Divider style={{ margin: '24px 0 16px', borderColor: '#1E1E2E' }} />
        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
          <Popconfirm
            title={`确认删除 "${agent.name}"？`}
            description="此操作不可逆，Agent 的所有关联数据将被清除"
            onConfirm={handleDelete}
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true, loading: deleteLoading }}
          >
            <Button danger icon={<DeleteOutlined />}>
              删除 Agent
            </Button>
          </Popconfirm>
        </Space>
      </div>
    </Drawer>
  );
}
