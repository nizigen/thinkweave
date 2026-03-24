/**
 * Agent 绠＄悊椤?鈥?涓婚〉闈?
 * Ref: IMPLEMENTATION_PLAN.md Step 1.2
 * Ref: APP_FLOW.md 鈥?鏃呯▼2 Agent绠＄悊
 * Ref: FRONTEND_GUIDELINES.md 鈥?缁勪欢瑙勮寖 / 鍔ㄦ晥瑙勮寖
 */
import { useEffect, useState, useMemo, useCallback } from 'react';
import {
  Table,
  Button,
  Input,
  Select,
  Tag,
  Space,
  Typography,
  Tooltip,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  PlusOutlined,
  SearchOutlined,
  ReloadOutlined,
  TeamOutlined,
  CheckCircleFilled,
  SyncOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { useAgentStore } from '../stores/agentStore';
import type { AgentData } from '../api/agents';
import CreateAgentModal from './agents/CreateAgentModal';
import AgentDetailDrawer from './agents/AgentDetailDrawer';

const { Title, Text } = Typography;

/* 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?Display constants 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?*/

const ROLE_CONFIG: Record<string, { label: string; color: string }> = {
  orchestrator: { label: '缂栨帓', color: '#A855F7' },
  manager: { label: '绠＄悊', color: '#6366F1' },
  outline: { label: '澶х翰', color: '#3B82F6' },
  writer: { label: '鍐欎綔', color: '#10B981' },
  reviewer: { label: '瀹℃煡', color: '#F59E0B' },
  consistency: { label: '涓€鑷存€?, color: '#EC4899' },
};

const LAYER_CONFIG: Record<number, { label: string; color: string }> = {
  0: { label: 'L0', color: '#A855F7' },
  1: { label: 'L1', color: '#6366F1' },
  2: { label: 'L2', color: '#06B6D4' },
};

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  idle: { label: '绌洪棽', color: '#10B981', icon: <CheckCircleFilled style={{ color: '#10B981' }} /> },
  busy: { label: '蹇欑', color: '#3B82F6', icon: <SyncOutlined spin style={{ color: '#3B82F6' }} /> },
  offline: { label: '绂荤嚎', color: '#6B7280', icon: <MinusCircleOutlined style={{ color: '#6B7280' }} /> },
};

const MODEL_COLORS: Record<string, string> = {
  'gpt-4o': '#10B981',
  'deepseek-v3.2': '#3B82F6',
  'gpt-4o-mini': '#F59E0B',
};

const ROLE_FILTER_OPTIONS = [
  { value: 'orchestrator', label: '缂栨帓' },
  { value: 'manager', label: '绠＄悊' },
  { value: 'outline', label: '澶х翰' },
  { value: 'writer', label: '鍐欎綔' },
  { value: 'reviewer', label: '瀹℃煡' },
  { value: 'consistency', label: '涓€鑷存€? },
];

const STATUS_FILTER_OPTIONS = [
  { value: 'idle', label: '绌洪棽' },
  { value: 'busy', label: '蹇欑' },
  { value: 'offline', label: '绂荤嚎' },
];

/* 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?Stats Card 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?*/

interface StatCardProps {
  title: string;
  count: number;
  color: string;
  icon: React.ReactNode;
  delay: number;
}

function StatCard({ title, count, color, icon, delay }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay }}
      style={{
        position: 'relative',
        background: 'linear-gradient(135deg, #111118 0%, #0F0F1A 100%)',
        border: '1px solid #2A2A3E',
        borderRadius: 12,
        padding: '20px 20px 16px',
        flex: 1,
        minWidth: 0,
        cursor: 'default',
        transition: 'border-color 0.3s, box-shadow 0.3s',
        overflow: 'hidden',
      }}
      whileHover={{
        borderColor: color,
        boxShadow: `0 0 24px ${color}20, inset 0 1px 0 ${color}15`,
      }}
    >
      {/* 椤堕儴鑹叉潯 */}
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: `linear-gradient(90deg, ${color}00, ${color}60, ${color}00)` }} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text style={{ color: '#CBD5E1', fontSize: 13, fontWeight: 500 }}>{title}</Text>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 10,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: `${color}18`,
            border: `1px solid ${color}25`,
            color,
            fontSize: 17,
          }}
        >
          {icon}
        </div>
      </div>
      <div style={{ fontSize: 36, fontWeight: 700, color: '#F8FAFC', marginTop: 10, lineHeight: 1, letterSpacing: '-0.02em' }}>
        {count}
      </div>
      <div
        style={{
          marginTop: 14,
          height: 3,
          borderRadius: 2,
          background: '#1E1E2E',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: count > 0 ? '60%' : '0%',
            borderRadius: 2,
            background: `linear-gradient(90deg, ${color}, ${color}80)`,
            transition: 'width 0.6s ease',
          }}
        />
      </div>
    </motion.div>
  );
}

/* 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?Main Page 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?*/

export default function Agents() {
  const canManageAgents = import.meta.env.VITE_AGENT_ADMIN === 'true';
  const { agents, loading, selectedAgent, fetchAgents, setSelectedAgent } = useAgentStore();
  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  useEffect(() => {
    fetchAgents().catch(() => message.error('鍔犺浇 Agent 鍒楄〃澶辫触'));
  }, [fetchAgents]);

  /* 鈹€鈹€ Filter logic 鈹€鈹€ */
  const filtered = useMemo(() => {
    let list = agents;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (a) => a.name.toLowerCase().includes(q) || a.role.toLowerCase().includes(q),
      );
    }
    if (roleFilter) list = list.filter((a) => a.role === roleFilter);
    if (statusFilter) list = list.filter((a) => a.status === statusFilter);
    return list;
  }, [agents, search, roleFilter, statusFilter]);

  /* 鈹€鈹€ Stats 鈹€鈹€ */
  const stats = useMemo(() => ({
    total: agents.length,
    idle: agents.filter((a) => a.status === 'idle').length,
    busy: agents.filter((a) => a.status === 'busy').length,
    offline: agents.filter((a) => a.status === 'offline').length,
  }), [agents]);

  /* 鈹€鈹€ Handlers 鈹€鈹€ */
  const openDetail = useCallback(
    (agent: AgentData) => {
      setSelectedAgent(agent);
      setDrawerOpen(true);
    },
    [setSelectedAgent],
  );

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    setSelectedAgent(null);
  }, [setSelectedAgent]);

  /* 鈹€鈹€ Table columns 鈹€鈹€ */
  const columns: ColumnsType<AgentData> = useMemo(
    () => [
      {
        title: '鍚嶇О',
        dataIndex: 'name',
        key: 'name',
        render: (name: string, record: AgentData) => (
          <Space>
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: ROLE_CONFIG[record.role]?.color ?? '#6B7280',
                flexShrink: 0,
              }}
            />
            <Text
              style={{ color: '#F1F5F9', fontWeight: 500, cursor: 'pointer' }}
              onClick={(e) => {
                e.stopPropagation();
                openDetail(record);
              }}
            >
              {name}
            </Text>
          </Space>
        ),
      },
      {
        title: '瑙掕壊',
        dataIndex: 'role',
        key: 'role',
        width: 110,
        render: (role: string) => {
          const cfg = ROLE_CONFIG[role] ?? { label: role, color: '#6B7280' };
          return (
            <Tag
              style={{
                border: 'none',
                background: `${cfg.color}18`,
                color: cfg.color,
                fontWeight: 500,
                borderRadius: 6,
              }}
            >
              {cfg.label}
            </Tag>
          );
        },
      },
      {
        title: '灞傜骇',
        dataIndex: 'layer',
        key: 'layer',
        width: 80,
        render: (layer: number) => {
          const cfg = LAYER_CONFIG[layer] ?? { label: `L${layer}`, color: '#6B7280' };
          return (
            <Tag
              style={{
                border: `1px solid ${cfg.color}44`,
                background: 'transparent',
                color: cfg.color,
                fontWeight: 600,
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                fontSize: 12,
                borderRadius: 4,
              }}
            >
              {cfg.label}
            </Tag>
          );
        },
      },
      {
        title: '妯″瀷',
        dataIndex: 'model',
        key: 'model',
        width: 140,
        render: (model: string) => {
          const color = MODEL_COLORS[model] ?? '#94A3B8';
          return (
            <Text style={{ color, fontSize: 13, fontFamily: "'JetBrains Mono', monospace" }}>
              {model}
            </Text>
          );
        },
      },
      {
        title: '鐘舵€?,
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (status: string) => {
          const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.offline;
          return (
            <Space size={6}>
              {cfg.icon}
              <Text style={{ color: cfg.color, fontSize: 13 }}>{cfg.label}</Text>
            </Space>
          );
        },
      },
      {
        title: '鍒涘缓鏃堕棿',
        dataIndex: 'created_at',
        key: 'created_at',
        width: 160,
        render: (t: string) => (
          <Text style={{ color: '#94A3B8', fontSize: 13 }}>
            {new Date(t).toLocaleDateString('zh-CN')}
          </Text>
        ),
      },
      {
        title: '',
        key: 'actions',
        width: 60,
        render: (_: unknown, record: AgentData) => (
          <Tooltip title="鏌ョ湅璇︽儏">
            <Button
              type="text"
              size="small"
              style={{ color: '#94A3B8' }}
              onClick={(e) => {
                e.stopPropagation();
                openDetail(record);
              }}
            >
              璇︽儏
            </Button>
          </Tooltip>
        ),
      },
    ],
    [openDetail],
  );

  return (
    <div style={{ maxWidth: 1200 }}>
      {/* 鈹€鈹€ Header 鈹€鈹€ */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: 24,
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0, color: '#F1F5F9' }}>
            Agent 绠＄悊
          </Title>
          <Text style={{ color: '#94A3B8', fontSize: 14, marginTop: 4, display: 'block' }}>
            绠＄悊鍜岀洃鎺х郴缁熶腑鐨勬墍鏈?Agent 瀹炰緥
          </Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => { if (!canManageAgents) { message.error('Admin permission required'); return; } setModalOpen(true); }}
          size="large"
          disabled={!canManageAgents}
          style={{ borderRadius: 8, fontWeight: 500 }}
        >
          娉ㄥ唽鏂?Agent
        </Button>
      </motion.div>

      {/* 鈹€鈹€ Stats Cards 鈹€鈹€ */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
        <StatCard title="鍏ㄩ儴 Agent" count={stats.total} color="#6366F1" icon={<TeamOutlined />} delay={0} />
        <StatCard title="绌洪棽" count={stats.idle} color="#10B981" icon={<CheckCircleFilled />} delay={0.05} />
        <StatCard title="蹇欑" count={stats.busy} color="#3B82F6" icon={<SyncOutlined />} delay={0.1} />
        <StatCard title="绂荤嚎" count={stats.offline} color="#6B7280" icon={<MinusCircleOutlined />} delay={0.15} />
      </div>

      {/* 鈹€鈹€ Toolbar 鈹€鈹€ */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.2 }}
        style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}
      >
        <Input
          placeholder="鎼滅储 Agent..."
          prefix={<SearchOutlined style={{ color: '#475569' }} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 260 }}
          allowClear
        />
        <Select
          placeholder="瑙掕壊"
          options={ROLE_FILTER_OPTIONS}
          value={roleFilter}
          onChange={setRoleFilter}
          allowClear
          style={{ width: 120 }}
        />
        <Select
          placeholder="鐘舵€?
          options={STATUS_FILTER_OPTIONS}
          value={statusFilter}
          onChange={setStatusFilter}
          allowClear
          style={{ width: 120 }}
        />
        <div style={{ flex: 1 }} />
        <Tooltip title="鍒锋柊鍒楄〃">
          <Button
            icon={<ReloadOutlined />}
            onClick={() => fetchAgents().catch(() => message.error('鍒锋柊澶辫触'))}
            loading={loading}
          />
        </Tooltip>
      </motion.div>

      {/* 鈹€鈹€ Table 鈹€鈹€ */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.25 }}
      >
        <Table<AgentData>
          columns={columns}
          dataSource={filtered}
          rowKey="id"
          loading={loading}
          pagination={{
            pageSize: 10,
            showTotal: (total) => `鍏?${total} 鏉,
            showSizeChanger: false,
          }}
          onRow={(record) => ({
            style: { cursor: 'pointer', transition: 'background 0.2s' },
            onClick: () => openDetail(record),
          })}
          style={{
            borderRadius: 12,
            overflow: 'hidden',
            border: '1px solid #2A2A3E',
            boxShadow: '0 4px 16px rgba(0, 0, 0, 0.2)',
          }}
          locale={{ emptyText: '鏆傛棤 Agent锛岀偣鍑诲彸涓婅銆屾敞鍐屾柊 Agent銆嶅紑濮? }}
        />
      </motion.div>

      {/* 鈹€鈹€ Modal & Drawer 鈹€鈹€ */}
      <CreateAgentModal open={modalOpen} onClose={() => setModalOpen(false)} allowMutations={canManageAgents} />
      <AgentDetailDrawer agent={selectedAgent} open={drawerOpen} onClose={closeDrawer} allowMutations={canManageAgents} />
    </div>
  );
}


