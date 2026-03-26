/**
 * 历史任务页
 * Ref: IMPLEMENTATION_PLAN.md Step 6.3
 * Ref: APP_FLOW.md 旅程5 历史任务
 * Ref: FRONTEND_GUIDELINES.md 组件规范 / 颜色系统
 */
import { useEffect, useState, useCallback } from 'react';
import {
  Table,
  Button,
  Input,
  Select,
  Space,
  Typography,
  Tag,
  Popconfirm,
  message,
  DatePicker,
} from 'antd';
import type { ColumnsType, TableRowSelection } from 'antd/es/table/interface';
import {
  SearchOutlined,
  DeleteOutlined,
  ReloadOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { listTasks, batchDeleteTasks } from '../api/tasks';
import type { Task } from '../stores/taskStore';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  completed: { label: '已完成', color: '#10B981' },
  running:   { label: '执行中', color: '#3B82F6' },
  failed:    { label: '失败',   color: '#EF4444' },
  pending:   { label: '待执行', color: '#6B7280' },
  paused:    { label: '已暂停', color: '#F59E0B' },
};

const MODE_CONFIG: Record<string, { label: string; color: string }> = {
  report:  { label: '技术报告', color: '#6366F1' },
  novel:   { label: '小说',     color: '#EC4899' },
  custom:  { label: '自定义',   color: '#06B6D4' },
};

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function History() {
  const navigate = useNavigate();
  const [tasks, setTasks]         = useState<Task[]>([]);
  const [total, setTotal]         = useState(0);
  const [page, setPage]           = useState(1);
  const [loading, setLoading]     = useState(false);
  const [search, setSearch]       = useState('');
  const [statusFilter, setStatus] = useState<string | undefined>();
  const [modeFilter, setMode]     = useState<string | undefined>();
  const [selected, setSelected]   = useState<string[]>([]);
  const [deleting, setDeleting]   = useState(false);

  const fetchTasks = useCallback(async (pg = page) => {
    setLoading(true);
    try {
      const result = await listTasks({
        offset: (pg - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        search: search || undefined,
        status: statusFilter,
        mode: modeFilter,
      });
      setTasks(result.items);
      setTotal(result.total);
    } catch {
      message.error('加载任务列表失败');
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter, modeFilter]);

  useEffect(() => { fetchTasks(page); }, [page, statusFilter, modeFilter]);

  const handleSearch = () => { setPage(1); fetchTasks(1); };

  const handleDelete = async () => {
    if (!selected.length) return;
    setDeleting(true);
    try {
      const { deleted_count } = await batchDeleteTasks(selected);
      message.success(`已删除 ${deleted_count} 个任务`);
      setSelected([]);
      fetchTasks(1);
    } catch {
      message.error('删除失败，请重试');
    } finally {
      setDeleting(false);
    }
  };

  const rowSelection: TableRowSelection<Task> = {
    selectedRowKeys: selected,
    onChange: (keys) => setSelected(keys as string[]),
  };

  const columns: ColumnsType<Task> = [
    {
      title: '任务标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (text: string, record: Task) => (
        <Button
          type="link"
          style={{ padding: 0, color: '#F1F5F9', fontWeight: 500 }}
          onClick={() => navigate(`/result/${record.id}`)}
          icon={<FileTextOutlined style={{ color: '#6366F1' }} />}
        >
          {text}
        </Button>
      ),
    },
    {
      title: '模式',
      dataIndex: 'mode',
      key: 'mode',
      width: 110,
      render: (mode: string) => {
        const cfg = MODE_CONFIG[mode] ?? { label: mode, color: '#94A3B8' };
        return <Tag color={cfg.color} style={{ borderRadius: 4 }}>{cfg.label}</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const cfg = STATUS_CONFIG[status] ?? { label: status, color: '#94A3B8' };
        return (
          <Tag
            style={{
              borderRadius: 4,
              background: `${cfg.color}20`,
              border: `1px solid ${cfg.color}60`,
              color: cfg.color,
            }}
          >
            {cfg.label}
          </Tag>
        );
      },
    },
    {
      title: '字数',
      dataIndex: 'word_count',
      key: 'word_count',
      width: 90,
      render: (n: number) => (
        <Text style={{ color: '#CBD5E1', fontSize: 13 }}>
          {n ? `${(n / 1000).toFixed(1)}k` : '—'}
        </Text>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (ts: string) => (
        <Text style={{ color: '#94A3B8', fontSize: 13 }}>
          {new Date(ts).toLocaleString('zh-CN', { hour12: false })}
        </Text>
      ),
    },
    {
      title: '完成时间',
      dataIndex: 'finished_at',
      key: 'finished_at',
      width: 160,
      render: (ts: string | null) =>
        ts ? (
          <Text style={{ color: '#94A3B8', fontSize: 13 }}>
            {new Date(ts).toLocaleString('zh-CN', { hour12: false })}
          </Text>
        ) : (
          <Text style={{ color: '#475569', fontSize: 13 }}>—</Text>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: unknown, record: Task) => (
        <Button
          size="small"
          type="link"
          style={{ color: '#6366F1' }}
          onClick={() => navigate(`/result/${record.id}`)}
        >
          查看
        </Button>
      ),
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      style={{ padding: 24 }}
    >
      {/* 顶部色条 */}
      <div style={{
        height: 2,
        background: 'linear-gradient(90deg, #6366F100, #6366F160, #6366F100)',
        marginBottom: 24,
        borderRadius: 1,
      }} />

      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 20 }}>
        <Title level={3} style={{ margin: 0, color: '#F8FAFC' }}>历史任务</Title>
        <Text style={{ marginLeft: 12, color: '#94A3B8', fontSize: 13 }}>
          共 {total} 条记录
        </Text>
      </div>

      {/* 过滤栏 */}
      <div style={{
        display: 'flex',
        gap: 12,
        marginBottom: 16,
        flexWrap: 'wrap',
        alignItems: 'center',
      }}>
        <Input
          placeholder="搜索任务标题…"
          prefix={<SearchOutlined style={{ color: '#64748B' }} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onPressEnter={handleSearch}
          style={{ width: 240, background: '#0D0D14', borderColor: '#2A2A3E' }}
          allowClear
        />
        <Select
          placeholder="状态筛选"
          allowClear
          style={{ width: 140 }}
          value={statusFilter}
          onChange={(v) => { setStatus(v); setPage(1); }}
          options={Object.entries(STATUS_CONFIG).map(([k, v]) => ({ value: k, label: v.label }))}
        />
        <Select
          placeholder="模式筛选"
          allowClear
          style={{ width: 140 }}
          value={modeFilter}
          onChange={(v) => { setMode(v); setPage(1); }}
          options={Object.entries(MODE_CONFIG).map(([k, v]) => ({ value: k, label: v.label }))}
        />
        <Button
          icon={<SearchOutlined />}
          onClick={handleSearch}
          style={{ background: '#6366F1', borderColor: '#6366F1', color: '#fff' }}
        >
          搜索
        </Button>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => fetchTasks(page)}
          style={{ borderColor: '#2A2A3E', color: '#CBD5E1' }}
        />
        {selected.length > 0 && (
          <Popconfirm
            title={`确认删除选中的 ${selected.length} 个任务？`}
            onConfirm={handleDelete}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button
              danger
              icon={<DeleteOutlined />}
              loading={deleting}
            >
              删除 ({selected.length})
            </Button>
          </Popconfirm>
        )}
      </div>

      {/* 任务表格 */}
      <Table<Task>
        rowKey="id"
        dataSource={tasks}
        columns={columns}
        loading={loading}
        rowSelection={rowSelection}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showSizeChanger: false,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p) => setPage(p),
          style: { marginTop: 16 },
        }}
        onRow={(record) => ({
          onClick: () => navigate(`/result/${record.id}`),
          style: { cursor: 'pointer' },
        })}
        style={{
          background: '#111118',
          borderRadius: 8,
          border: '1px solid #2A2A3E',
        }}
        locale={{ emptyText: '暂无历史任务' }}
      />
    </motion.div>
  );
}
