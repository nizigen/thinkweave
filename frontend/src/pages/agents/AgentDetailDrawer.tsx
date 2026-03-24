/**
 * Agent 璇︽儏鎶藉眽
 * Ref: APP_FLOW.md 鈥?鏃呯▼2 Agent璇︽儏
 * Ref: IMPLEMENTATION_PLAN.md Step 1.2 鈥?Agent璇︽儏鎶藉眽
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

/* 鈹€鈹€ Display maps 鈹€鈹€ */
const ROLE_LABELS: Record<string, string> = {
  orchestrator: '缂栨帓 (Orchestrator)',
  manager: '绠＄悊 (Manager)',
  outline: '澶х翰 (Outline)',
  writer: '鍐欎綔 (Writer)',
  reviewer: '瀹℃煡 (Reviewer)',
  consistency: '涓€鑷存€?(Consistency)',
};

const LAYER_LABELS: Record<number, string> = {
  0: 'L0 鈥?缂栨帓灞?,
  1: 'L1 鈥?绠＄悊灞?,
  2: 'L2 鈥?鎵ц灞?,
};

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  idle: { label: '绌洪棽', color: '#10B981' },
  busy: { label: '蹇欑', color: '#3B82F6' },
  offline: { label: '绂荤嚎', color: '#6B7280' },
};

const STATUS_OPTIONS = [
  { value: 'idle', label: '绌洪棽 (Idle)' },
  { value: 'busy', label: '蹇欑 (Busy)' },
  { value: 'offline', label: '绂荤嚎 (Offline)' },
];

interface Props {
  agent: AgentData | null;
  open: boolean;
  onClose: () => void;
  allowMutations?: boolean;
}

export default function AgentDetailDrawer({
  agent,
  open,
  onClose,
  allowMutations = true,
}: Props) {
  const { updateAgentStatus, deleteAgent } = useAgentStore();
  const [statusLoading, setStatusLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const handleStatusChange = useCallback(
    async (newStatus: string) => {
      if (!agent) return;
      if (!allowMutations) {
        message.error('Admin permission required');
        return;
      }
      setStatusLoading(true);
      try {
        await updateAgentStatus(agent.id, newStatus as 'idle' | 'busy' | 'offline');
        message.success('鐘舵€佸凡鏇存柊');
      } catch {
        message.error('鐘舵€佹洿鏂板け璐?);
      } finally {
        setStatusLoading(false);
      }
    },
    [agent, updateAgentStatus, allowMutations],
  );

  const handleDelete = useCallback(async () => {
    if (!agent) return;
    if (!allowMutations) {
      message.error('Admin permission required');
      return;
    }
    setDeleteLoading(true);
    try {
      await deleteAgent(agent.id);
      message.success(`Agent "${agent.name}" 宸插垹闄);
      onClose();
    } catch {
      message.error('鍒犻櫎澶辫触');
    } finally {
      setDeleteLoading(false);
    }
  }, [agent, deleteAgent, onClose, allowMutations]);

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
          {ROLE_LABELS[agent.role] ?? agent.role} 路 {LAYER_LABELS[agent.layer] ?? `L${agent.layer}`}
        </Text>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, color: '#475569', fontSize: 12 }}>
          <ClockCircleOutlined />
          <span>鍒涘缓浜?{createdAt}</span>
        </div>
      </div>

      <div style={{ padding: '20px 24px' }}>
        {/* Basic info */}
        <Descriptions column={1} size="small" labelStyle={{ color: '#94A3B8' }}>
          <Descriptions.Item label="妯″瀷">{agent.model}</Descriptions.Item>
          <Descriptions.Item label="灞傜骇">{LAYER_LABELS[agent.layer]}</Descriptions.Item>
        </Descriptions>

        {agent.capabilities && (
          <>
            <Divider style={{ margin: '16px 0', borderColor: '#1E1E2E' }} />
            <Text style={{ color: '#94A3B8', fontSize: 12, marginBottom: 8, display: 'block' }}>
              鑳藉姏鎻忚堪
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
          鍒囨崲鐘舵€?
        </Text>
        <Select
          value={agent.status}
          options={STATUS_OPTIONS}
          onChange={handleStatusChange}
          loading={statusLoading}
          disabled={statusLoading || !allowMutations}
          style={{ width: '100%' }}
          suffixIcon={<SwapOutlined />}
        />

        {/* Stats placeholder */}
        <Divider style={{ margin: '20px 0 16px', borderColor: '#1E1E2E' }} />
        <Text style={{ color: '#94A3B8', fontSize: 12, marginBottom: 12, display: 'block' }}>
          鎵ц缁熻
        </Text>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr',
            gap: 12,
          }}
        >
          {['浠诲姟鎬绘暟', '鎴愬姛鐜?, '骞冲潎鑰楁椂'].map((label) => (
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
          鍘嗗彶浠诲姟
        </Text>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <Text style={{ color: '#475569', fontSize: 13 }}>
              璇?Agent 灏氭湭鍙備笌浠讳綍浠诲姟
            </Text>
          }
        />

        {/* Delete */}
        <Divider style={{ margin: '24px 0 16px', borderColor: '#1E1E2E' }} />
        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
          <Popconfirm
            title={`纭鍒犻櫎 "${agent.name}"锛焋}
            description="姝ゆ搷浣滀笉鍙€嗭紝Agent 鐨勬墍鏈夊叧鑱旀暟鎹皢琚竻闄?
            onConfirm={handleDelete}
            okText="纭鍒犻櫎"
            cancelText="鍙栨秷"
            okButtonProps={{ danger: true, loading: deleteLoading }}`r`n            disabled={!allowMutations}
          >
            <Button danger icon={<DeleteOutlined />} disabled={!allowMutations}>
              鍒犻櫎 Agent
            </Button>
          </Popconfirm>
        </Space>
      </div>
    </Drawer>
  );
}

