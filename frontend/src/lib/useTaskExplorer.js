import { useEffect, useMemo, useState } from 'react'
import { authHeaders, requestJson } from './apiBase'

function sortTasks(items) {
  return [...items].sort((a, b) =>
    String(b.created_at || '').localeCompare(String(a.created_at || ''))
  )
}

export function useTaskExplorer({ withAudit = false } = {}) {
  const [tasks, setTasks] = useState([])
  const [taskId, setTaskId] = useState('')
  const [task, setTask] = useState(null)
  const [audit, setAudit] = useState(null)
  const [listError, setListError] = useState('')
  const [taskError, setTaskError] = useState('')
  const [auditError, setAuditError] = useState('')
  const [listLoading, setListLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    let timer = null

    const load = async () => {
      setListError('')
      try {
        const data = await requestJson('/api/tasks?limit=50', { headers: authHeaders() })
        const nextItems = sortTasks(Array.isArray(data?.items) ? data.items : [])
        if (!cancelled) {
          setTasks(nextItems)
          if (!taskId && nextItems.length) setTaskId(nextItems[0].id)
        }
      } catch (e) {
        if (!cancelled) setListError(String(e))
      } finally {
        if (!cancelled) setListLoading(false)
      }
      if (!cancelled) timer = setTimeout(load, 5000)
    }

    load()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [taskId])

  useEffect(() => {
    if (!taskId) {
      setTask(null)
      return
    }
    let cancelled = false
    let timer = null

    const load = async () => {
      setTaskError('')
      try {
        const data = await requestJson(`/api/tasks/${taskId}`, { headers: authHeaders() })
        if (!cancelled) setTask(data)
      } catch (e) {
        if (!cancelled) setTaskError(String(e))
      }
      if (!cancelled) timer = setTimeout(load, 2500)
    }

    load()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [taskId])

  useEffect(() => {
    if (!withAudit || !taskId) {
      setAudit(null)
      return
    }
    let cancelled = false
    let timer = null

    const load = async () => {
      setAuditError('')
      try {
        const data = await requestJson(`/api/tasks/${taskId}/decomposition-audit`, {
          headers: authHeaders(),
        })
        if (!cancelled) setAudit(data)
      } catch (e) {
        if (!cancelled) {
          setAudit(null)
          setAuditError(String(e))
        }
      }
      if (!cancelled) timer = setTimeout(load, 10000)
    }

    load()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [taskId, withAudit])

  const nodeStatusSummary = useMemo(() => {
    const summary = {}
    const nodes = Array.isArray(task?.nodes) ? task.nodes : []
    for (const node of nodes) {
      const key = node.status || 'unknown'
      summary[key] = (summary[key] || 0) + 1
    }
    return summary
  }, [task])

  return {
    tasks,
    taskId,
    setTaskId,
    task,
    audit,
    listError,
    taskError,
    auditError,
    listLoading,
    nodeStatusSummary,
  }
}

