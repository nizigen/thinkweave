import { useEffect, useMemo, useState } from 'react'
import { TaskSelectorBar } from '../components/TaskSelectorBar'
import { authHeaders, requestJson } from '../lib/apiBase'
import { normalizeDisplayText } from '../lib/text'
import { useTaskExplorer } from '../lib/useTaskExplorer'
import { summaryTextMap } from '../lib/taskViewUtils'

export function RoutingDebugPage() {
  const {
    tasks,
    taskId,
    setTaskId,
    task,
    listError,
    taskError,
    listLoading,
  } = useTaskExplorer()
  const [agents, setAgents] = useState([])
  const [agentError, setAgentError] = useState('')

  useEffect(() => {
    let cancelled = false
    let timer = null
    const load = async () => {
      setAgentError('')
      try {
        const data = await requestJson('/api/agents', { headers: authHeaders() })
        if (!cancelled) setAgents(Array.isArray(data) ? data : [])
      } catch (e) {
        if (!cancelled) setAgentError(String(e))
      }
      if (!cancelled) timer = setTimeout(load, 5000)
    }
    load()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [])

  const agentMap = useMemo(() => {
    const map = {}
    for (const a of agents) map[a.id] = a
    return map
  }, [agents])
  const nodes = Array.isArray(task?.nodes) ? task.nodes : []

  const routingReasonSummary = useMemo(() => {
    const summary = {}
    for (const node of nodes) {
      const key = node.routing_reason || 'none'
      summary[key] = (summary[key] || 0) + 1
    }
    return summary
  }, [nodes])

  const pendingMatchRows = nodes.filter((n) => n.routing_status === 'pending_match')

  return (
    <div className="page page-pro-max page-ops">
      <section className="card">
        <header className="card-head">
          <h2>路由决策页</h2>
          <p>查看每个节点为什么分给某个 agent，定位 skill/capability/fallback 是否符合预期</p>
        </header>
        <TaskSelectorBar
          tasks={tasks}
          taskId={taskId}
          setTaskId={setTaskId}
          listLoading={listLoading}
          listError={listError}
          taskError={taskError}
        />
        {agentError ? <p className="error">{agentError}</p> : null}
        <div className="kpi-grid">
          <div className="kpi-item">
            <span>路由原因分布</span>
            <strong>{summaryTextMap(routingReasonSummary)}</strong>
          </div>
          <div className="kpi-item">
            <span>待匹配节点</span>
            <strong>{pendingMatchRows.length}</strong>
          </div>
          <div className="kpi-item">
            <span>Agent 总数</span>
            <strong>{agents.length}</strong>
          </div>
        </div>
      </section>

      <section className="card">
        <header className="card-head">
          <h2>节点路由明细</h2>
          <p>含 `routing_mode / required_capabilities / assigned agent skill_allowlist`</p>
        </header>
        <div className="task-table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>角色</th>
                <th>标题</th>
                <th>路由模式</th>
                <th>原因</th>
                <th>状态</th>
                <th>能力要求</th>
                <th>分配 Agent</th>
                <th>Agent Skills</th>
              </tr>
            </thead>
            <tbody>
              {nodes.map((node) => {
                const agent = agentMap[node.assigned_agent] || null
                const skillList = Array.isArray(agent?.agent_config?.skill_allowlist)
                  ? agent.agent_config.skill_allowlist
                  : []
                return (
                  <tr key={node.id}>
                    <td>{node.agent_role || '-'}</td>
                    <td>{normalizeDisplayText(node.title || '-')}</td>
                    <td>{node.routing_mode || 'auto'}</td>
                    <td>{node.routing_reason || '-'}</td>
                    <td>{node.routing_status || '-'}</td>
                    <td>
                      {Array.isArray(node.required_capabilities)
                        ? node.required_capabilities.join(', ')
                        : '-'}
                    </td>
                    <td>{agent ? `${agent.name} (${agent.role})` : node.assigned_agent || '-'}</td>
                    <td>{skillList.length ? skillList.join(', ') : '-'}</td>
                  </tr>
                )
              })}
              {!nodes.length ? (
                <tr>
                  <td colSpan={8} className="muted">
                    当前任务暂无节点，无法展示路由信息
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

