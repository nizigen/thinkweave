/**
 * Agent 管理页 — 主页面
 * Ref: IMPLEMENTATION_PLAN.md Step 1.2
 * Ref: APP_FLOW.md — 旅程2 Agent管理
 * Ref: FRONTEND_GUIDELINES.md — 组件规范 / 动效规范
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

/* ═══════════ Display constants ═══════════ */

const ROLE_CONFIG: Record<string, { label: string; color: string }> = {
  orchestrator: { label: '编排', color: '#A855F7' },
  manager: { label: '管理', color: '#6366F1' },
  outline: { label: '大纲', color: '#3B82F6' },
  writer: { label: '写作', color: '#10B981' },
  reviewer: { label: '审查', color: '#F59E0B' },
  consistency: { label: '一致性', color: '#EC4899' },
};

const LAYER_CONFIG: Record<number, { label: string; color: string }> = {
  0: { label: 'L0', color: '#A855F7' },
  1: { label: 'L1', color: '#6366F1' },
  2: { label: 'L2', color: '#06B6D4' },
};

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  idle: { label: '空闲', color: '#10B981', icon: <CheckCircleFilled style={{ color: '#10B981' }} /> },
  busy: { label: '忙碌', color: '#3B82F6', icon: <SyncOutlined spin style={{ color: '#3B82F6' }} /> },
  offline: { label: '离线', color: '#6B7280', icon: <MinusCircleOutlined style={{ color: '#6B7280' }} /> },
};

const MODEL_COLORS: Record<string, string> = {
  'gpt-4o': '#10B981',
  'deepseek-v3.2': '#3B82F6',
  'gpt-4o-mini': '#F59E0B',
};

const ROLE_FILTER_OPTIONS = [
  { value: 'orchestrator', label: '编排' },
  { value: 'manager', label: '管理' },
  { value: 'outline', label: '大纲' },
  { value: 'writer', label: '写作' },
  { value: 'reviewer', label: '审查' },
  { value: 'consistency', label: '一致性' },
];

const STATUS_FILTER_OPTIONS = [
  { value: 'idle', label: '空闲' },
  { value: 'busy', label: '忙碌' },
  { value: 'offline', label: '离线' },
];

/* ═══════════ Stats Card ═══════════ */

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
        background: '#111118',
        border: '1px solid #2A2A3E',
        borderRadius: 12,
        padding: '20px 20px 16px',
        flex: 1,
        minWidth: 0,
        cursor: 'default',
        transition: 'border-color 0.2s, box-shadow 0.2s',
      }}
      whileHover={{
        borderColor: color,
        boxShadow: `0 0 20px ${color}12`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text style={{ color: '#94A3B8', fontSize: 13 }}>{title}</Text>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: `${color}14`,
            color,
            fontSize: 16,
          }}
        >
          {icon}
        </div>
      </div>
      <div style={{ fontSize: 32, fontWeight: 700, color: '#F1F5F9', marginTop: 8, lineHeight: 1 }}>
        {count}
      </div>
      <div
        style={{
          marginTop: 12,
          height: 3,
          borderRadius: 2,
          background: '#1E1E2E',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: '60%',
            borderRadius: 2,
            background: `linear-gradient(90deg, ${color}, ${color}66)`,
          }}
        />
      </div>
    </motion.div>
  );
}

/* ═══════════ Main Page ═══════════ */

export default function Agents() {
  const { agents, loading, selectedAgent, fetchAgents, setSelectedAgent } = useAgentStore();
  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  useEffect(() => {
    fetchAgents().catch(() => message.error('加载 Agent 列表失败'));
  }, [fetchAgents]);

  /* ── Filter logic ── */
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

  /* ── Stats ── */
  const stats = useMemo(() => ({
    total: agents.length,
    idle: agents.filter((a) => a.status === 'idle').length,
    busy: agents.filter((a) => a.status === 'busy').length,
    offline: agents.filter((a) => a.status === 'offline').length,
  }), [agents]);

  /* ── Handlers ── */
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

  /* ── Table columns ── */
  const columns: ColumnsType<AgentData> = useMemo(
    () => [
      {
        title: '名称',
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
        title: '角色',
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
        title: '层级',
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
        title: '模型',
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
        title: '状态',
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
        title: '创建时间',
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
          <Tooltip title="查看详情">
            <Button
              type="text"
              size="small"
              style={{ color: '#94A3B8' }}
              onClick={(e) => {
                e.stopPropagation();
                openDetail(record);
              }}
            >
              详情
            </Button>
          </Tooltip>
        ),
      },
    ],
    [openDetail],
  );

  return (
    <div style={{ maxWidth: 1200 }}>
      {/* ── Header ── */}
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
            Agent 管理
          </Title>
          <Text style={{ color: '#94A3B8', fontSize: 14, marginTop: 4, display: 'block' }}>
            管理和监控系统中的所有 Agent 实例
          </Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setModalOpen(true)}
          size="large"
          style={{ borderRadius: 8, fontWeight: 500 }}
        >
          注册新 Agent
        </Button>
      </motion.div>

      {/* ── Stats Cards ── */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
        <StatCard title="全部 Agent" count={stats.total} color="#6366F1" icon={<TeamOutlined />} delay={0} />
        <StatCard title="空闲" count={stats.idle} color="#10B981" icon={<CheckCircleFilled />} delay={0.05} />
        <StatCard title="忙碌" count={stats.busy} color="#3B82F6" icon={<SyncOutlined />} delay={0.1} />
        <StatCard title="离线" count={stats.offline} color="#6B7280" icon={<MinusCircleOutlined />} delay={0.15} />
      </div>

      {/* ── Toolbar ── */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.2 }}
        style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}
      >
        <Input
          placeholder="搜索 Agent..."
          prefix={<SearchOutlined style={{ color: '#475569' }} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 260 }}
          allowClear
        />
        <Select
          placeholder="角色"
          options={ROLE_FILTER_OPTIONS}
          value={roleFilter}
          onChange={setRoleFilter}
          allowClear
          style={{ width: 120 }}
        />
        <Select
          placeholder="状态"
          options={STATUS_FILTER_OPTIONS}
          value={statusFilter}
          onChange={setStatusFilter}
          allowClear
          style={{ width: 120 }}
        />
        <div style={{ flex: 1 }} />
        <Tooltip title="刷新列表">
          <Button
            icon={<ReloadOutlined />}
            onClick={() => fetchAgents().catch(() => message.error('刷新失败'))}
            loading={loading}
          />
        </Tooltip>
      </motion.div>

      {/* ── Table ── */}
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
            showTotal: (total) => `共 ${total} 条`,
            showSizeChanger: false,
          }}
          onRow={(record) => ({
            style: { cursor: 'pointer', transition: 'background 0.2s' },
            onClick: () => openDetail(record),
          })}
          style={{ borderRadius: 12, overflow: 'hidden', border: '1px solid #2A2A3E' }}
          locale={{ emptyText: '暂无 Agent，点击右上角「注册新 Agent」开始' }}
        />
      </motion.div>

      {/* ── Modal & Drawer ── */}
      <CreateAgentModal open={modalOpen} onClose={() => setModalOpen(false)} />
      <AgentDetailDrawer agent={selectedAgent} open={drawerOpen} onClose={closeDrawer} />
    </div>
  );
}
