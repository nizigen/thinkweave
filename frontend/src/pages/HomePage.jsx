import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE, authHeaders, requestJson } from '../lib/apiBase'

export function HomePage() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('二次元行业盈利方式调研')
  const [depth, setDepth] = useState('standard')
  const [mode, setMode] = useState('report')
  const [targetWords, setTargetWords] = useState(10000)
  const [taskToken, setTaskToken] = useState(
    sessionStorage.getItem('task_auth_token') || 'local-dev-admin-token'
  )
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadingTasks, setLoadingTasks] = useState(true)
  const [error, setError] = useState('')
  const [taskError, setTaskError] = useState('')

  useEffect(() => {
    let cancelled = false
    let timer = null

    const load = async () => {
      setLoadingTasks(true)
      setTaskError('')
      try {
        const data = await requestJson('/api/tasks', { headers: authHeaders() })
        if (!cancelled) {
          setItems(Array.isArray(data?.items) ? data.items : [])
        }
      } catch (e) {
        if (!cancelled) setTaskError(String(e))
      } finally {
        if (!cancelled) setLoadingTasks(false)
      }
      if (!cancelled) {
        timer = setTimeout(load, 4000)
      }
    }

    load()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [])

  const statusSummary = useMemo(() => {
    const summary = {}
    for (const task of items) {
      const key = task.status || 'unknown'
      summary[key] = (summary[key] || 0) + 1
    }
    return summary
  }, [items])

  async function createTask() {
    setError('')
    setLoading(true)
    try {
      const cleanToken = taskToken.trim()
      if (cleanToken) {
        sessionStorage.setItem('task_auth_token', cleanToken)
      } else {
        sessionStorage.removeItem('task_auth_token')
      }

      const data = await requestJson('/api/tasks', {
        method: 'POST',
        headers: authHeaders({ 'content-type': 'application/json' }),
        body: JSON.stringify({
          title,
          depth,
          mode,
          target_words: targetWords,
        }),
      })
      navigate(`/monitor/${data.id}`)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page page-home page-pro-max">
      <section className="card card-create">
        <header className="card-head">
          <h2>任务启动台</h2>
          <p>创建新任务并进入实时监控</p>
        </header>

        <div className="form-grid">
          <label>
            <span>标题</span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="输入主题标题"
            />
          </label>

          <label>
            <span>模式</span>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="report">report</option>
              <option value="novel">novel</option>
              <option value="custom">custom</option>
            </select>
          </label>

          <label>
            <span>深度</span>
            <select value={depth} onChange={(e) => setDepth(e.target.value)}>
              <option value="quick">quick</option>
              <option value="standard">standard</option>
              <option value="deep">deep</option>
            </select>
          </label>

          <label>
            <span>目标字数</span>
            <input
              type="number"
              min={500}
              value={targetWords}
              onChange={(e) => setTargetWords(Number(e.target.value || 0))}
            />
          </label>

          <label className="field-full">
            <span>任务 Token</span>
            <input
              value={taskToken}
              onChange={(e) => setTaskToken(e.target.value)}
              placeholder="local-dev-admin-token"
            />
          </label>
        </div>

        <div className="actions">
          <button
            className="btn btn-primary"
            onClick={createTask}
            disabled={loading || title.trim().length < 6}
          >
            {loading ? '创建中...' : '开始生成并进入监控'}
          </button>
          <span className="hint">API Base: {API_BASE || '(same-origin)'}</span>
        </div>
        {error ? <p className="error">{error}</p> : null}
      </section>

      <section className="card card-summary">
        <header className="card-head">
          <h2>运行概览</h2>
          <p>最近 20 个任务实时状态</p>
        </header>
        {loadingTasks ? <p className="muted">加载中...</p> : null}
        {taskError ? <p className="error">{taskError}</p> : null}

        <div className="kpi-grid">
          <div className="kpi-item">
            <span>Total</span>
            <strong>{items.length}</strong>
          </div>
          {Object.entries(statusSummary).map(([status, count]) => (
            <div className="kpi-item" key={status}>
              <span>{status}</span>
              <strong>{count}</strong>
            </div>
          ))}
        </div>

        <div className="task-table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>标题</th>
                <th>状态</th>
                <th>FSM</th>
                <th>字数</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((task) => (
                <tr key={task.id}>
                  <td>{task.title}</td>
                  <td>
                    <span className={`status-dot status-${task.status}`} />
                    {task.status}
                  </td>
                  <td>{task.fsm_state || '-'}</td>
                  <td>{task.word_count || 0}</td>
                  <td>
                    <button
                      className="btn btn-ghost"
                      onClick={() => navigate(`/monitor/${task.id}`)}
                    >
                      打开监控
                    </button>
                  </td>
                </tr>
              ))}
              {!items.length && !loadingTasks ? (
                <tr>
                  <td colSpan={5} className="muted">
                    暂无任务
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
