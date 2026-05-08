import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { SectionCard } from '../components/SectionCard'
import { apiUrl, authHeaders } from '../lib/apiBase'

function summarize(items) {
  const total = items.length
  const running = items.filter((t) => t.status === 'running').length
  const done = items.filter((t) => t.status === 'done').length
  const blocked = items.filter((t) => t.status === 'blocked').length
  return [
    { label: '总记录', value: total },
    { label: '进行中', value: running },
    { label: '已完成', value: done },
    { label: '阻塞', value: blocked },
  ]
}

export function HomePage() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [depth, setDepth] = useState('standard')
  const [mode, setMode] = useState('report')
  const [targetWords, setTargetWords] = useState(10000)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [items, setItems] = useState([])

  useEffect(() => {
    let canceled = false
    async function load() {
      const resp = await fetch(apiUrl('/api/tasks'), { headers: authHeaders() })
      if (!resp.ok) return
      const data = await resp.json()
      if (!canceled) setItems(data.items || [])
    }
    void load()
    return () => {
      canceled = true
    }
  }, [])

  const kpis = useMemo(() => summarize(items), [items])
  const recent = useMemo(() => items.slice(0, 3), [items])

  async function createTask() {
    setError('')
    setLoading(true)
    try {
      const resp = await fetch(apiUrl('/api/tasks'), {
        method: 'POST',
        headers: authHeaders({ 'content-type': 'application/json' }),
        body: JSON.stringify({ title, depth, mode, target_words: targetWords }),
      })
      if (!resp.ok) {
        setError(`创建失败: ${resp.status}`)
        return
      }
      const data = await resp.json()
      navigate(`/monitor/${data.id}`)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="总览"
        subtitle="管理你的内容生产与记录流，查看进度并快速继续。"
      />

      <div className="kpi-grid">
        {kpis.map((item) => (
          <SectionCard key={item.label}>
            <p className="muted-label">{item.label}</p>
            <p className="kpi-value">{item.value}</p>
          </SectionCard>
        ))}
      </div>

      <div className="two-col-grid">
        <SectionCard title="新建记录任务">
          <div className="form-grid">
            <label htmlFor="task-title">标题</label>
            <input
              id="task-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="输入主题标题"
            />

            <label htmlFor="task-mode">模式</label>
            <select id="task-mode" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="report">report</option>
              <option value="novel">novel</option>
              <option value="custom">custom</option>
            </select>

            <label htmlFor="task-depth">深度</label>
            <select id="task-depth" value={depth} onChange={(e) => setDepth(e.target.value)}>
              <option value="quick">quick</option>
              <option value="standard">standard</option>
              <option value="deep">deep</option>
            </select>

            <label htmlFor="task-words">目标字数</label>
            <input
              id="task-words"
              type="number"
              min="100"
              value={targetWords}
              onChange={(e) => setTargetWords(Number(e.target.value || 0))}
            />
          </div>
          <div className="button-row">
            <button
              type="button"
              onClick={createTask}
              disabled={loading || title.trim().length < 6}
              className="btn btn-primary"
            >
              {loading ? '创建中...' : '开始生成'}
            </button>
          </div>
          {error ? <p className="error-text">{error}</p> : null}
        </SectionCard>

        <SectionCard
          title="继续进行"
          extra={
            <button className="btn btn-ghost" type="button" onClick={() => navigate('/history')}>
              查看全部
            </button>
          }
        >
          {recent.length ? (
            <ul className="simple-list">
              {recent.map((task) => (
                <li key={task.id}>
                  <button
                    type="button"
                    className="list-link"
                    onClick={() => navigate(`/monitor/${task.id}`)}
                  >
                    <span>{task.title}</span>
                    <span className="status-pill">{task.status}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="暂无记录" description="新建一个任务后会出现在这里。" />
          )}
        </SectionCard>
      </div>
    </div>
  )
}
