import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { SectionCard } from '../components/SectionCard'
import { apiUrl, authHeaders } from '../lib/apiBase'

export function HistoryPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [keyword, setKeyword] = useState('')

  useEffect(() => {
    let canceled = false
    async function load() {
      try {
        const resp = await fetch(apiUrl('/api/tasks'), {
          headers: authHeaders(),
        })
        if (!resp.ok) {
          setError(`加载失败: ${resp.status}`)
          return
        }
        const data = await resp.json()
        if (!canceled) setItems(data.items || [])
      } catch (e) {
        if (!canceled) setError(String(e))
      } finally {
        if (!canceled) setLoading(false)
      }
    }
    void load()
    const id = setInterval(() => void load(), 3000)
    return () => {
      canceled = true
      clearInterval(id)
    }
  }, [])

  const filtered = useMemo(() => {
    const lower = keyword.trim().toLowerCase()
    return items.filter((item) => !lower || item.title.toLowerCase().includes(lower))
  }, [items, keyword])

  return (
    <div className="page-stack">
      <PageHeader title="历史记录" subtitle="查看全部任务，继续追踪执行与产出。" />
      <SectionCard>
        <div className="toolbar-row">
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="按标题搜索"
            aria-label="按标题搜索"
          />
          <button className="btn btn-ghost" type="button" onClick={() => navigate('/')}>
            新建任务
          </button>
        </div>
      </SectionCard>

      <SectionCard title="任务列表">
        {loading ? <p className="muted-text">加载中...</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
        {!loading && !filtered.length ? (
          <EmptyState
            title="暂无历史任务"
            description="可以先创建一个任务，随后在这里查看进度与详情。"
            action={
              <button className="btn btn-primary" type="button" onClick={() => navigate('/')}>
                去创建
              </button>
            }
          />
        ) : null}

        {filtered.length ? (
          <ul className="task-list">
            {filtered.map((task) => (
              <li key={task.id}>
                <button
                  type="button"
                  className="list-link"
                  onClick={() => navigate(`/monitor/${task.id}`)}
                >
                  <span className="title-wrap">{task.title}</span>
                  <span className="status-pill">{task.status}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </SectionCard>
    </div>
  )
}
