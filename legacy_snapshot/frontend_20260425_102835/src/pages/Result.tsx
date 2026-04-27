import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Row,
  Skeleton,
  Statistic,
  Typography,
} from 'antd';
import {
  ClockCircleOutlined,
  FileTextOutlined,
  NodeIndexOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import { getTask } from '../api/tasks';
import type { Task } from '../stores/taskStore';

const { Text } = Typography;

interface TocItem { id: string; level: number; text: string; }

function slugify(text: string): string {
  return text.toLowerCase().replace(/[^\w\u4e00-\u9fa5\s-]/g, '').replace(/\s+/g, '-').slice(0, 60);
}

function parseToc(markdown: string): TocItem[] {
  const counts: Record<string, number> = {};
  return markdown.split('\n').flatMap((line) => {
    const m = line.match(/^(#{1,4})\s+(.+)/);
    if (!m) return [];
    const text = m[2].trim();
    const base = slugify(text);
    counts[base] = (counts[base] ?? 0) + 1;
    const id = counts[base] > 1 ? `${base}-${counts[base]}` : base;
    return [{ id, level: m[1].length, text }];
  });
}

function formatDuration(start: string, end?: string | null): string {
  if (!end) return '-';
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const mins = Math.floor(ms / 60000);
  const secs = Math.floor((ms % 60000) / 1000);
  return mins === 0 ? `${secs}s` : `${mins}m ${secs}s`;
}

function TableOfContents({ items, activeId }: { items: TocItem[]; activeId: string }) {
  if (items.length === 0) return null;
  return (
    <div style={{ position: 'sticky', top: 24, maxHeight: 'calc(100vh - 120px)', overflowY: 'auto', padding: '16px 12px', background: '#111118', border: '1px solid #2A2A3E', borderRadius: 8 }}>
      <Text style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748B', display: 'block', marginBottom: 12 }}>目录</Text>
      {items.map((item) => (
        <div key={item.id} style={{ paddingLeft: (item.level - 1) * 12, marginBottom: 6 }}>
          <a
            href={`#${item.id}`}
            style={{ fontSize: item.level === 1 ? 13 : 12, color: activeId === item.id ? '#818CF8' : '#94A3B8', fontWeight: activeId === item.id ? 600 : 400, textDecoration: 'none', display: 'block', lineHeight: '1.6', transition: 'color 150ms', borderLeft: activeId === item.id ? '2px solid #6366F1' : '2px solid transparent', paddingLeft: 8 }}
            onClick={(e) => { e.preventDefault(); document.getElementById(item.id)?.scrollIntoView({ behavior: 'smooth' }); }}
          >{item.text}</a>
        </div>
      ))}
    </div>
  );
}

function StatsBar({ task }: { task: Task }) {
  const agentCount = useMemo(() => new Set((task.nodes ?? []).map((n) => n.agent_role).filter(Boolean)).size, [task.nodes]);
  const chapterCount = useMemo(() => (task.nodes ?? []).filter((n) => n.agent_role === 'writer').length, [task.nodes]);
  const duration = formatDuration(task.created_at, task.finished_at);
  const cardStyle = { background: '#111118', border: '1px solid #2A2A3E', borderRadius: 8 };
  const bodyStyle = { padding: '16px 20px' };
  const labelStyle = { color: '#94A3B8', fontSize: 12 };
  const valStyle = { color: '#F8FAFC', fontSize: 22 };
  return (
    <Row gutter={16} style={{ marginBottom: 24 }}>
      <Col span={6}><Card style={cardStyle} bodyStyle={bodyStyle}><Statistic title={<Text style={labelStyle}>总字数</Text>} value={task.word_count} prefix={<FileTextOutlined style={{ color: '#6366F1' }} />} valueStyle={valStyle} suffix={<Text style={labelStyle}>字</Text>} /></Card></Col>
      <Col span={6}><Card style={cardStyle} bodyStyle={bodyStyle}><Statistic title={<Text style={labelStyle}>章节数</Text>} value={chapterCount || '-'} prefix={<NodeIndexOutlined style={{ color: '#10B981' }} />} valueStyle={valStyle} /></Card></Col>
      <Col span={6}><Card style={cardStyle} bodyStyle={bodyStyle}><Statistic title={<Text style={labelStyle}>Agent 数</Text>} value={agentCount || '-'} prefix={<TeamOutlined style={{ color: '#3B82F6' }} />} valueStyle={valStyle} /></Card></Col>
      <Col span={6}><Card style={cardStyle} bodyStyle={bodyStyle}><Statistic title={<Text style={labelStyle}>生成耗时</Text>} value={duration} prefix={<ClockCircleOutlined style={{ color: '#F59E0B' }} />} valueStyle={valStyle} /></Card></Col>
    </Row>
  );
}

function MarkdownRenderer({ content }: { content: string }) {
  const idCounters = useRef<Record<string, number>>({});
  useEffect(() => { idCounters.current = {}; }, [content]);

  const makeHeading = (Tag: 'h1' | 'h2' | 'h3', fontSize: number, color: string) =>
    ({ children }: { children?: React.ReactNode }) => {
      const text = String(children);
      const base = slugify(text);
      idCounters.current[base] = (idCounters.current[base] ?? 0) + 1;
      const id = idCounters.current[base] > 1 ? `${base}-${idCounters.current[base]}` : base;
      return <Tag id={id} style={{ fontSize, color, marginTop: 28, marginBottom: 12, borderBottom: Tag === 'h1' ? '1px solid #2A2A3E' : 'none', paddingBottom: Tag === 'h1' ? 8 : 0 }}>{children}</Tag>;
    };

  const components: Components = {
    h1: makeHeading('h1', 24, '#F8FAFC'),
    h2: makeHeading('h2', 20, '#F1F5F9'),
    h3: makeHeading('h3', 17, '#CBD5E1'),
    p: ({ children }) => <p style={{ color: '#CBD5E1', lineHeight: 1.8, marginBottom: 14 }}>{children}</p>,
    code: ({ className, children, ...props }) => {
      const match = /language-(\w+)/.exec(className ?? '');
      if (match) {
        return (
          <pre
            style={{
              background: '#0D0D14',
              color: '#CBD5E1',
              borderRadius: 8,
              fontSize: 13,
              margin: '12px 0',
              border: '1px solid #2A2A3E',
              padding: '12px 14px',
              overflowX: 'auto',
            }}
          >
            <code className={className}>{String(children).replace(/\n$/, '')}</code>
          </pre>
        );
      }
      return <code style={{ background: '#1A1A26', color: '#A5B4FC', padding: '2px 6px', borderRadius: 4, fontSize: '0.875em', fontFamily: "'JetBrains Mono', monospace" }} {...props}>{children}</code>;
    },
    blockquote: ({ children }) => <blockquote style={{ borderLeft: '3px solid #6366F1', paddingLeft: 16, margin: '12px 0', color: '#94A3B8', fontStyle: 'italic' }}>{children}</blockquote>,
    ul: ({ children }) => <ul style={{ color: '#CBD5E1', paddingLeft: 20, marginBottom: 14 }}>{children}</ul>,
    ol: ({ children }) => <ol style={{ color: '#CBD5E1', paddingLeft: 20, marginBottom: 14 }}>{children}</ol>,
    li: ({ children }) => <li style={{ marginBottom: 4, lineHeight: 1.7 }}>{children}</li>,
    table: ({ children }) => <div style={{ overflowX: 'auto', marginBottom: 16 }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14, color: '#CBD5E1' }}>{children}</table></div>,
    th: ({ children }) => <th style={{ background: '#0F0F18', color: '#94A3B8', padding: '8px 12px', border: '1px solid #2A2A3E', textAlign: 'left', fontSize: 12, textTransform: 'uppercase' }}>{children}</th>,
    td: ({ children }) => <td style={{ padding: '8px 12px', border: '1px solid #2A2A3E' }}>{children}</td>,
  };

  return <ReactMarkdown components={components}>{content}</ReactMarkdown>;
}

export default function Result() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeHeadingId, setActiveHeadingId] = useState('');
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!taskId) return;
    setLoading(true);
    getTask(taskId)
      .then(setTask)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load task'))
      .finally(() => setLoading(false));
  }, [taskId]);

  const tocItems = useMemo(() => (task?.output_text ? parseToc(task.output_text) : []), [task?.output_text]);

  useEffect(() => {
    if (!contentRef.current || tocItems.length === 0) return;
    const headings = contentRef.current.querySelectorAll('h1,h2,h3,h4');
    const observer = new IntersectionObserver(
      (entries) => { for (const e of entries) { if (e.isIntersecting) { setActiveHeadingId(e.target.id); break; } } },
      { rootMargin: '-10% 0px -80% 0px' },
    );
    headings.forEach((h) => observer.observe(h));
    return () => observer.disconnect();
  }, [tocItems, task?.output_text]);

  const reviewScores = useMemo<Record<string, number>>(() => {
    const raw = task?.checkpoint_data?.control?.review_scores;
    if (!raw) return {};
    const result: Record<string, number> = {};
    for (const [nodeId, scoreData] of Object.entries(raw)) {
      const s = (scoreData as Record<string, unknown>).score;
      if (typeof s === 'number') result[nodeId] = s;
    }
    return result;
  }, [task?.checkpoint_data]);

  if (loading) return <div style={{ padding: 24 }}><Skeleton active paragraph={{ rows: 8 }} /></div>;

  if (error) return (
    <div style={{ padding: 24 }}>
      <Alert type="error" message="加载失败" description={error}
        action={<Button size="small" onClick={() => navigate(-1)}>返回</Button>} />
    </div>
  );

  if (!task) return null;

  if (!['completed', 'done'].includes(task.status) || !task.output_text) return (
    <div style={{ padding: 24 }}>
      <Alert type="warning" message="任务尚未完成" description={`当前状态：${task.status}（FSM：${task.fsm_state}）`}
        action={<Button size="small" onClick={() => navigate(`/monitor/${task.id}`)}>查看进度</Button>} />
    </div>
  );

  const writerNodes = (task.nodes ?? []).filter((n) => n.agent_role === 'writer');

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, color: '#F8FAFC', marginBottom: 8 }}>{task.title}</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Badge status="success" text={<Text style={{ color: '#10B981' }}>已完成</Text>} />
            <Text style={{ color: '#64748B' }}>·</Text>
            <Text style={{ color: '#94A3B8', fontSize: 13 }}>{task.mode}</Text>
            <Text style={{ color: '#64748B' }}>·</Text>
            <Text style={{ color: '#94A3B8', fontSize: 13 }}>{new Date(task.created_at).toLocaleDateString('zh-CN')}</Text>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          <Button
            icon={<FileTextOutlined />}
            onClick={() => window.open(`/api/export/${task.id}/docx`, '_blank')}
            style={{ background: '#1A1A26', borderColor: '#2A2A3E', color: '#CBD5E1' }}
          >导出 DOCX</Button>
          <Button
            type="primary"
            icon={<FileTextOutlined />}
            onClick={() => window.open(`/api/export/${task.id}/pdf`, '_blank')}
          >导出 PDF</Button>
        </div>
      </div>

      {/* Stats */}
      <StatsBar task={task} />

      {/* Chapter scores */}
      {writerNodes.length > 0 && Object.keys(reviewScores).length > 0 && (
        <div style={{ marginBottom: 20, padding: '12px 16px', background: '#111118', border: '1px solid #2A2A3E', borderRadius: 8 }}>
          <Text style={{ color: '#64748B', fontSize: 12, display: 'block', marginBottom: 10 }}>审查评分</Text>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {writerNodes.map((n) => (
              <div key={n.id} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '6px 10px', background: '#0D0D14', borderRadius: 6, border: '1px solid #2A2A3E', minWidth: 160 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Text style={{ fontSize: 12, color: '#CBD5E1' }}>{n.title}</Text>
                  {reviewScores[n.id] !== undefined && (
                    <span style={{ fontSize: 11, fontWeight: 700, color: reviewScores[n.id] >= 70 ? '#10B981' : '#EF4444', background: reviewScores[n.id] >= 70 ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)', padding: '1px 6px', borderRadius: 4 }}>
                      {reviewScores[n.id]}
                    </span>
                  )}
                </div>
                {n.routing_reason ? (
                  <Text style={{ fontSize: 11, color: '#94A3B8' }}>
                    {`routing: ${n.routing_reason}${n.routing_status ? ` (${n.routing_status})` : ''}`}
                  </Text>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Content area */}
      <Row gutter={24}>
        {tocItems.length > 0 && (
          <Col flex="240px">
            <TableOfContents items={tocItems} activeId={activeHeadingId} />
          </Col>
        )}
        <Col flex="1" style={{ minWidth: 0 }}>
          <div
            ref={contentRef}
            style={{ background: '#111118', border: '1px solid #2A2A3E', borderRadius: 8, padding: '24px 32px' }}
          >
            <MarkdownRenderer content={task.output_text} />
          </div>
        </Col>
      </Row>
    </div>
  );
}
