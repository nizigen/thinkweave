import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { SectionCard } from '../components/SectionCard'
import { apiUrl, authHeaders } from '../lib/apiBase'

function stageTag(stageCode) {
  return stageCode || 'UNKNOWN'
}

export function MonitorPage() {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const [task, setTask] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let canceled = false
    async function load() {
      try {
        const resp = await fetch(apiUrl(`/api/tasks/${taskId}`), {
          headers: authHeaders(),
        })
        if (!resp.ok) {
          setError(`加载失败: ${resp.status}`)
          return
        }
        const data = await resp.json()
        if (!canceled) setTask(data)
      } catch (e) {
        if (!canceled) setError(String(e))
      }
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

  if (error) {
    return (
      <SectionCard>
        <EmptyState
          title="任务加载失败"
          description={error}
          action={
            <button className="btn btn-primary" type="button" onClick={() => navigate('/history')}>
              返回历史记录
            </button>
          }
        />
      </SectionCard>
    )
  }

  if (!task) return <SectionCard><p className="muted-text">加载中...</p></SectionCard>

  return (
    <div className="page-stack">
      <PageHeader
        title="任务详情"
        subtitle="实时查看 DAG 节点状态、执行进度与异常。"
        actions={
          <button className="btn btn-ghost" type="button" onClick={() => navigate(-1)}>
            返回上一页
          </button>
        }
      />

      <div className="kpi-grid">
        <SectionCard><p className="muted-label">状态</p><p className="kpi-value">{task.status}</p></SectionCard>
        <SectionCard><p className="muted-label">FSM</p><p className="kpi-value">{task.fsm_state}</p></SectionCard>
        <SectionCard><p className="muted-label">字数</p><p className="kpi-value">{task.word_count}</p></SectionCard>
        <SectionCard><p className="muted-label">阻塞原因</p><p className="small-text">{task.blocking_reason || '-'}</p></SectionCard>
      </div>

      <SectionCard title="执行摘要">
        <p className="small-text">节点状态汇总: {nodeSummaryText}</p>
        <p className="small-text">阶段进度: {stageProgressText}</p>
        <p className="small-text">错误: {task.error_message || '-'}</p>
      </SectionCard>

      <SectionCard title="节点列表">
        <ul className="dag-list">
          {task.nodes?.map((node) => (
            <li key={node.id} className={`node node-${node.status}`}>
              <div className="card-title-row">
                <strong>{node.title}</strong>
                <span className="status-pill">{node.status}</span>
              </div>
              <div className="tag-row">
                <span className="soft-tag">{node.agent_role}</span>
                <span className="soft-tag">{stageTag(node.stage_code)}</span>
                <span className="soft-tag">{node.stage_name || '未命名阶段'}</span>
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
      </SectionCard>
    </div>
  )
}
