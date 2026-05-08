import { useEffect, useMemo, useState } from 'react'
import { apiUrl, authHeaders, requestJson } from '../lib/apiBase'
import { summaryTextMap } from '../lib/taskViewUtils'

function countBy(rows, keyFn) {
  const map = {}
  for (const row of rows) {
    const key = keyFn(row) || 'unknown'
    map[key] = (map[key] || 0) + 1
  }
  return map
}

export function RuntimeHealthPage() {
  const [health, setHealth] = useState(null)
  const [agents, setAgents] = useState([])
  const [tasks, setTasks] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    let timer = null
    const load = async () => {
      setError('')
      try {
        const [h, a, t] = await Promise.all([
          fetch(apiUrl('/health')).then((r) =>
            r.ok ? r.json() : Promise.resolve({ status: 'down' })
          ),
          requestJson('/api/agents', { headers: authHeaders() }),
          requestJson('/api/tasks?limit=100', { headers: authHeaders() }),
        ])
        if (!cancelled) {
          setHealth(h)
          setAgents(Array.isArray(a) ? a : [])
          setTasks(Array.isArray(t?.items) ? t.items : [])
        }
      } catch (e) {
        if (!cancelled) setError(String(e))
      }
      if (!cancelled) timer = setTimeout(load, 5000)
    }
    load()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [])

  const agentRoleSummary = useMemo(
    () => countBy(agents, (a) => a.role),
    [agents]
  )
  const agentStatusSummary = useMemo(
    () => countBy(agents, (a) => a.status),
    [agents]
  )
  const taskStatusSummary = useMemo(
    () => countBy(tasks, (t) => t.status),
    [tasks]
  )

  return (
    <div className="page page-pro-max page-ops">
      <section className="card">
        <header className="card-head">
          <h2>系统健康页</h2>
          <p>运行态总览：服务健康、Agent 分布、任务队列状态</p>
        </header>
        {error ? <p className="error">{error}</p> : null}
        <div className="kpi-grid">
          <div className="kpi-item">
            <span>Backend Health</span>
            <strong>{health?.status || 'unknown'}</strong>
          </div>
          <div className="kpi-item">
            <span>Agents</span>
            <strong>{agents.length}</strong>
          </div>
          <div className="kpi-item">
            <span>Tasks</span>
            <strong>{tasks.length}</strong>
          </div>
          <div className="kpi-item">
            <span>Agent Status</span>
            <strong>{summaryTextMap(agentStatusSummary)}</strong>
          </div>
          <div className="kpi-item">
            <span>Agent Roles</span>
            <strong>{summaryTextMap(agentRoleSummary)}</strong>
          </div>
          <div className="kpi-item">
            <span>Task Status</span>
            <strong>{summaryTextMap(taskStatusSummary)}</strong>
          </div>
        </div>
      </section>

      <section className="card">
        <header className="card-head">
          <h2>Agent 状态矩阵</h2>
          <p>快速识别角色是否短缺、离线是否异常</p>
        </header>
        <div className="task-table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>角色</th>
                <th>层级</th>
                <th>状态</th>
                <th>模型</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.id}>
                  <td>{agent.name || '-'}</td>
                  <td>{agent.role || '-'}</td>
                  <td>L{agent.layer ?? '-'}</td>
                  <td>
                    <span className={`status-dot status-${agent.status}`} />
                    {agent.status}
                  </td>
                  <td>{agent.model || '-'}</td>
                </tr>
              ))}
              {!agents.length ? (
                <tr>
                  <td colSpan={5} className="muted">
                    暂无 agent 数据
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <header className="card-head">
          <h2>最近任务队列</h2>
          <p>快速识别 pending 卡住或 failed 激增</p>
        </header>
        <div className="task-table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>标题</th>
                <th>状态</th>
                <th>FSM</th>
                <th>字数</th>
                <th>深度</th>
              </tr>
            </thead>
            <tbody>
              {tasks.slice(0, 30).map((task) => (
                <tr key={task.id}>
                  <td>{task.title || '-'}</td>
                  <td>
                    <span className={`status-dot status-${task.status}`} />
                    {task.status}
                  </td>
                  <td>{task.fsm_state || '-'}</td>
                  <td>{task.word_count || 0}</td>
                  <td>{task.depth || '-'}</td>
                </tr>
              ))}
              {!tasks.length ? (
                <tr>
                  <td colSpan={5} className="muted">
                    暂无任务数据
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
