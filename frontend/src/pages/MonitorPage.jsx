import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { apiUrl, authHeaders } from '../lib/apiBase'

function stageTag(stageCode) {
  return stageCode || 'UNKNOWN'
}

export function MonitorPage() {
  const { taskId } = useParams()
  const [task, setTask] = useState(null)

  useEffect(() => {
    let canceled = false
    async function load() {
      const resp = await fetch(apiUrl(`/api/tasks/${taskId}`), {
        headers: authHeaders(),
      })
      if (!resp.ok) return
      const data = await resp.json()
      if (!canceled) setTask(data)
    }
    void load()
    const id = setInterval(() => void load(), 1500)
    return () => {
      canceled = true
      clearInterval(id)
    }
  }, [taskId])

  const nodeMap = useMemo(() => {
    const map = {}
    for (const n of task?.nodes || []) map[n.id] = n
    return map
  }, [task])
  const stageProgressText = useMemo(() => {
    const stageProgress = task?.stage_progress || {}
    const entries = Object.entries(stageProgress)
    if (!entries.length) return '-'
    return entries.map(([stage, count]) => `${stage}:${count}`).join(' | ')
  }, [task])

  const nodeSummaryText = useMemo(() => {
    const summary = task?.node_status_summary || {}
    const entries = Object.entries(summary)
    if (!entries.length) return '-'
    return entries.map(([status, count]) => `${status}:${count}`).join(' | ')
  }, [task])

  if (!task) return <section>加载中...</section>

  return (
    <section>
      <h2>任务监控</h2>
      <div className="kpis">
        <div>状态: {task.status}</div>
        <div>FSM: {task.fsm_state}</div>
        <div>字数: {task.word_count}</div>
        <div>错误: {task.error_message || '-'}</div>
        <div>阻塞原因: {task.blocking_reason || '-'}</div>
        <div>节点状态汇总: {nodeSummaryText}</div>
        <div>阶段进度: {stageProgressText}</div>
      </div>

      <h3>DAG 可视化（列表图）</h3>
      <ul className="dag-list">
        {task.nodes.map((node) => (
          <li key={node.id} className={`node node-${node.status}`}>
            <div>
              <strong>{node.title}</strong>
              <span className="tag">{node.agent_role}</span>
              <span className="tag">{stageTag(node.stage_code)}</span>
              <span className="tag">{node.stage_name || '未命名阶段'}</span>
              <span className="tag">{node.status}</span>
            </div>
            <div className="deps">
              depends_on:{' '}
              {(node.depends_on || []).length
                ? (node.depends_on || []).map((id) => nodeMap[id]?.title || id).join(' | ')
                : 'none'}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
