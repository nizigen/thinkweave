import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { authHeaders, requestJson } from '../lib/apiBase'
import { normalizeDisplayText } from '../lib/text'

const STAGE_ORDER = ['OUTLINE', 'RESEARCH', 'DRAFT', 'REVIEW', 'ASSEMBLY', 'QA']
const ROLE_STAGE_MAP = {
  outline: 'OUTLINE',
  researcher: 'RESEARCH',
  writer: 'DRAFT',
  reviewer: 'REVIEW',
  consistency: 'ASSEMBLY',
  assembler: 'ASSEMBLY',
  qa: 'QA',
}

function stageFromRole(role) {
  return ROLE_STAGE_MAP[String(role || '').toLowerCase()] || 'UNASSIGNED'
}

function stageIndex(stageCode) {
  const idx = STAGE_ORDER.indexOf(stageCode)
  return idx === -1 ? 999 : idx
}

function semanticNodeKey(node) {
  const role = String(node?.agent_role || node?.role || '-').toLowerCase().trim()
  const title = String(node?.title || '').toLowerCase().replace(/\s+/g, ' ').trim()
  return `${role}::${title}`
}

function formatTime(iso) {
  if (!iso) return '-'
  const dt = new Date(iso)
  if (Number.isNaN(dt.getTime())) return '-'
  return dt.toLocaleString()
}

function formatDuration(startIso, endIso) {
  if (!startIso) return '-'
  const start = new Date(startIso).getTime()
  const end = endIso ? new Date(endIso).getTime() : Date.now()
  if (Number.isNaN(start) || Number.isNaN(end)) return '-'
  const sec = Math.max(0, Math.floor((end - start) / 1000))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return `${h}h ${m}m ${s}s`
}

function parseEvidenceRows(markdown) {
  if (!markdown) return []
  return markdown
    .split('\n')
    .filter((line) => line.startsWith('| E'))
    .map((line) => line.split('|').slice(1, -1).map((part) => part.trim()))
    .map((cols) => ({
      evidenceId: cols[0] || '-',
      category: cols[2] || '-',
      priority: cols[3] || '-',
      title: cols[6] || '-',
      url: cols[7] || '',
    }))
}

function buildDagLayout(nodes) {
  const nodeWidth = 250
  const nodeHeight = 88
  const baseRadius = 240
  const ringGap = 170
  const minArcGap = nodeWidth + 34
  const margin = 220
  const positions = {}

  if (!nodes.length) return { positions, width: 1700, height: 1200 }

  const ids = new Set(nodes.map((n) => n.id))
  const nodeById = {}
  for (const node of nodes) nodeById[node.id] = node

  const parentsById = {}
  const childrenById = {}
  const indegree = {}
  for (const node of nodes) {
    parentsById[node.id] = []
    childrenById[node.id] = []
    indegree[node.id] = 0
  }

  for (const node of nodes) {
    for (const depId of node.depends_on || []) {
      if (!ids.has(depId)) continue
      parentsById[node.id].push(depId)
      childrenById[depId].push(node.id)
      indegree[node.id] += 1
    }
  }

  const queue = Object.keys(indegree)
    .filter((id) => indegree[id] === 0)
    .sort((a, b) => {
      const na = nodeById[a]
      const nb = nodeById[b]
      const ds = stageIndex(na?.stage_code) - stageIndex(nb?.stage_code)
      if (ds !== 0) return ds
      return String(na?.title || a).localeCompare(String(nb?.title || b))
    })

  const rankById = {}
  const topoOrder = []
  for (const id of queue) rankById[id] = 0

  while (queue.length) {
    const curId = queue.shift()
    topoOrder.push(curId)
    const curRank = rankById[curId] ?? 0
    for (const childId of childrenById[curId]) {
      rankById[childId] = Math.max(rankById[childId] ?? 0, curRank + 1)
      indegree[childId] -= 1
      if (indegree[childId] === 0) {
        queue.push(childId)
      }
    }
    queue.sort((a, b) => {
      const ar = rankById[a] ?? 0
      const br = rankById[b] ?? 0
      if (ar !== br) return ar - br
      return String(nodeById[a]?.title || a).localeCompare(String(nodeById[b]?.title || b))
    })
  }

  const placedSet = new Set(topoOrder)
  const maxKnownRank = Math.max(0, ...Object.values(rankById))
  for (const node of nodes) {
    if (placedSet.has(node.id)) continue
    rankById[node.id] = maxKnownRank + 1
    topoOrder.push(node.id)
  }

  // Fallback by stage to avoid collapsing into one single column when runtime deps are sparse.
  for (const node of nodes) {
    const s = stageIndex(node.stage_code)
    if (s >= 0 && s < 900) {
      rankById[node.id] = Math.max(rankById[node.id] ?? 0, s)
    }
  }

  const layerMap = {}
  for (const nodeId of topoOrder) {
    const layer = rankById[nodeId] ?? 0
    if (!layerMap[layer]) layerMap[layer] = []
    layerMap[layer].push(nodeId)
  }

  const orderedLayers = Object.keys(layerMap).map(Number).sort((a, b) => a - b)
  const angleById = {}
  let maxRadius = 0

  for (const layer of orderedLayers) {
    const idsInLayer = layerMap[layer]
    const count = idsInLayer.length
    const dynamicRadius = Math.ceil((count * minArcGap) / (2 * Math.PI))
    let radius = 0
    if (layer === 0) {
      radius = count === 1 ? 0 : Math.max(130, dynamicRadius)
    } else {
      radius = Math.max(baseRadius + (layer - 1) * ringGap, dynamicRadius)
    }
    maxRadius = Math.max(maxRadius, radius)

    if (layer === 0) {
      idsInLayer.sort((a, b) => {
        const na = nodeById[a]
        const nb = nodeById[b]
        const ds = stageIndex(na?.stage_code) - stageIndex(nb?.stage_code)
        if (ds !== 0) return ds
        return String(na?.title || a).localeCompare(String(nb?.title || b))
      })
    } else {
      idsInLayer.sort((a, b) => {
        const pa = parentsById[a] || []
        const pb = parentsById[b] || []
        const aa =
          pa.length > 0
            ? pa.reduce((sum, pid) => sum + (angleById[pid] ?? 0), 0) / pa.length
            : Number.MAX_SAFE_INTEGER / 2
        const ab =
          pb.length > 0
            ? pb.reduce((sum, pid) => sum + (angleById[pid] ?? 0), 0) / pb.length
            : Number.MAX_SAFE_INTEGER / 2
        if (aa !== ab) return aa - ab
        return String(nodeById[a]?.title || a).localeCompare(String(nodeById[b]?.title || b))
      })
    }

    if (count === 1) {
      angleById[idsInLayer[0]] = -Math.PI / 2
    } else {
      const step = (Math.PI * 2) / count
      const offset = -Math.PI / 2 + (layer % 2 === 0 ? step / 2 : 0)
      idsInLayer.forEach((id, idx) => {
        angleById[id] = offset + idx * step
      })
    }
  }

  const centerX = maxRadius + margin
  const centerY = maxRadius + margin
  for (const layer of orderedLayers) {
    const idsInLayer = layerMap[layer]
    const count = idsInLayer.length
    const dynamicRadius = Math.ceil((count * minArcGap) / (2 * Math.PI))
    let radius = 0
    if (layer === 0) {
      radius = count === 1 ? 0 : Math.max(130, dynamicRadius)
    } else {
      radius = Math.max(baseRadius + (layer - 1) * ringGap, dynamicRadius)
    }
    idsInLayer.forEach((id) => {
      const angle = angleById[id] ?? -Math.PI / 2
      const cx = centerX + radius * Math.cos(angle)
      const cy = centerY + radius * Math.sin(angle)
      positions[id] = {
        x: cx - nodeWidth / 2,
        y: cy - nodeHeight / 2,
        width: nodeWidth,
        height: nodeHeight,
        layer,
      }
    })
  }

  const width = Math.max(1900, Math.ceil(centerX * 2 + margin))
  const height = Math.max(1300, Math.ceil(centerY * 2 + margin))
  return { positions, width, height }
}

function buildDagEdges(nodes, nodeMap) {
  const edges = []
  for (const node of nodes) {
    for (const depId of node.depends_on || []) {
      const from = nodeMap[depId]
      if (!from) continue
      const fromIdx = stageIndex(from.stage_code)
      const toIdx = stageIndex(node.stage_code)
      const isTransition = Number.isFinite(fromIdx) && Number.isFinite(toIdx) && toIdx > fromIdx
      edges.push({
        id: `${depId}->${node.id}`,
        fromId: depId,
        toId: node.id,
        kind: isTransition ? 'transition' : 'dependency',
      })
    }
  }
  return edges
}

function getRectBoundaryPoint(rect, tx, ty) {
  const cx = rect.x + rect.width / 2
  const cy = rect.y + rect.height / 2
  const dx = tx - cx
  const dy = ty - cy
  if (Math.abs(dx) < 1e-6 && Math.abs(dy) < 1e-6) return { x: cx, y: cy }
  const hw = rect.width / 2
  const hh = rect.height / 2
  const sx = Math.abs(dx) > 1e-6 ? hw / Math.abs(dx) : Number.POSITIVE_INFINITY
  const sy = Math.abs(dy) > 1e-6 ? hh / Math.abs(dy) : Number.POSITIVE_INFINITY
  const scale = Math.min(sx, sy)
  return { x: cx + dx * scale, y: cy + dy * scale }
}

function renderReportWithEvidence(text, evidenceMap, onRefClick) {
  if (!text) return '报告尚未生成内容。'
  const markdownWithEvidenceLink = String(text).replace(/\b(E\d+)\b/g, (ref) => {
    if (!evidenceMap[ref]) return ref
    return `[${ref}](evidence://${ref})`
  })

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => {
          const value = String(href || '')
          if (value.startsWith('evidence://')) {
            const evidenceId = value.replace('evidence://', '')
            const row = evidenceMap[evidenceId]
            return (
              <button
                className="evidence-ref"
                onClick={() => onRefClick(evidenceId)}
                title={row?.title || evidenceId}
                type="button"
              >
                {children}
              </button>
            )
          }
          return (
            <a href={value} target="_blank" rel="noreferrer">
              {children}
            </a>
          )
        },
      }}
    >
      {markdownWithEvidenceLink}
    </ReactMarkdown>
  )
}

function renderMemorySummary(summary) {
  const text = normalizeDisplayText(String(summary || '').trim())
  if (!text) return '-'
  return (
    <div className="memory-summary-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  )
}

export function MonitorPage() {
  const navigate = useNavigate()
  const { taskId: routeTaskId } = useParams()
  const [tasks, setTasks] = useState([])
  const [agents, setAgents] = useState([])
  const [taskId, setTaskId] = useState(routeTaskId || '')
  const [task, setTask] = useState(null)
  const [audit, setAudit] = useState(null)
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [focusedEvidenceId, setFocusedEvidenceId] = useState('')
  const [error, setError] = useState('')
  const [lastRefreshAt, setLastRefreshAt] = useState(0)
  const evidenceRowRefs = useRef({})

  useEffect(() => {
    setTaskId(routeTaskId || '')
  }, [routeTaskId])

  useEffect(() => {
    let cancelled = false
    let timer = null
    const loadTasks = async () => {
      try {
        const [taskData, agentData] = await Promise.all([
          requestJson('/api/tasks', { headers: authHeaders() }),
          requestJson('/api/agents', { headers: authHeaders() }),
        ])
        const nextItems = Array.isArray(taskData?.items) ? taskData.items : []
        if (!cancelled) {
          setTasks(nextItems)
          setAgents(Array.isArray(agentData) ? agentData : [])
          if (!taskId && nextItems.length) {
            const nextId = nextItems[0].id
            setTaskId(nextId)
            navigate(`/monitor/${nextId}`, { replace: true })
          }
        }
      } catch (e) {
        if (!cancelled) setError(String(e))
      }
      if (!cancelled) timer = setTimeout(loadTasks, 4000)
    }
    loadTasks()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [navigate, taskId])

  useEffect(() => {
    if (!taskId) return
    let cancelled = false
    let taskTimer = null
    let auditTimer = null
    const loadTask = async () => {
      setError('')
      try {
        const data = await requestJson(`/api/tasks/${taskId}`, { headers: authHeaders() })
        if (!cancelled) {
          setTask(data)
          setLastRefreshAt(Date.now())
        }
      } catch (e) {
        if (!cancelled) setError(String(e))
      }
      if (!cancelled) taskTimer = setTimeout(loadTask, 2000)
    }
    const loadAudit = async () => {
      try {
        const data = await requestJson(`/api/tasks/${taskId}/decomposition-audit`, {
          headers: authHeaders(),
        })
        if (!cancelled) setAudit(data)
      } catch {
        if (!cancelled) setAudit(null)
      }
      if (!cancelled) auditTimer = setTimeout(loadAudit, 10000)
    }
    loadTask()
    loadAudit()
    return () => {
      cancelled = true
      if (taskTimer) clearTimeout(taskTimer)
      if (auditTimer) clearTimeout(auditTimer)
    }
  }, [taskId])

  const canonicalNodes = useMemo(() => {
    const runtimeNodes = Array.isArray(task?.nodes) ? task.nodes : []
    const plannedNodes = Array.isArray(audit?.normalized_dag?.nodes)
      ? audit.normalized_dag.nodes
      : []
    const runtimeMap = {}
    for (const node of runtimeNodes) runtimeMap[node.id] = node
    const runtimeSemanticMap = {}
    for (const node of runtimeNodes) {
      const key = semanticNodeKey(node)
      if (!runtimeSemanticMap[key]) runtimeSemanticMap[key] = node
    }

    const nodes = []
    const usedRuntimeIds = new Set()
    for (const planned of plannedNodes) {
      const runtimeById = runtimeMap[planned.id] || null
      const runtimeBySemantic = runtimeSemanticMap[semanticNodeKey(planned)] || null
      const runtime = runtimeById || runtimeBySemantic || {}
      const plannedDeps = Array.isArray(planned.depends_on) ? planned.depends_on : []
      const runtimeDeps = Array.isArray(runtime.depends_on) ? runtime.depends_on : []
      const mergedDeps = Array.from(new Set([...plannedDeps, ...runtimeDeps]))
      nodes.push({
        id: planned.id,
        title: runtime.title || planned.title || planned.id,
        stage_code: runtime.stage_code || stageFromRole(runtime.agent_role || planned.role),
        agent_role: runtime.agent_role || planned.role || '-',
        status: runtime.status || 'planned',
        depends_on: mergedDeps,
        assigned_agent: runtime.assigned_agent || '',
        started_at: runtime.started_at || null,
        finished_at: runtime.finished_at || null,
        routing_mode: runtime.routing_mode || planned.routing_mode || null,
        required_capabilities:
          runtime.required_capabilities || planned.required_capabilities || [],
      })
      if (runtime?.id) usedRuntimeIds.add(runtime.id)
    }
    for (const runtime of runtimeNodes) {
      if (usedRuntimeIds.has(runtime.id)) continue
      nodes.push(runtime)
    }
    return nodes
  }, [task, audit])

  const groupedNodes = useMemo(() => {
    const groups = {}
    for (const node of canonicalNodes) {
      const code = node.stage_code || 'UNKNOWN'
      if (!groups[code]) groups[code] = []
      groups[code].push(node)
    }
    return Object.entries(groups).sort(([a], [b]) => {
      const ai = STAGE_ORDER.indexOf(a)
      const bi = STAGE_ORDER.indexOf(b)
      if (ai === -1 && bi === -1) return a.localeCompare(b)
      if (ai === -1) return 1
      if (bi === -1) return -1
      return ai - bi
    })
  }, [canonicalNodes])

  const nodeMap = useMemo(() => {
    const map = {}
    for (const node of canonicalNodes) map[node.id] = node
    return map
  }, [canonicalNodes])

  const agentMap = useMemo(() => {
    const map = {}
    for (const agent of agents) map[agent.id] = agent
    return map
  }, [agents])

  const stageProgressText = useMemo(() => {
    const stageProgress = task?.stage_progress || {}
    const entries = Object.entries(stageProgress)
    if (!entries.length) return '-'
    return entries.map(([stage, count]) => `${stage}:${count}`).join(' | ')
  }, [task])

  const nodeSummaryText = useMemo(() => {
    const summary = {}
    for (const node of canonicalNodes) {
      const key = node.status || 'unknown'
      summary[key] = (summary[key] || 0) + 1
    }
    const entries = Object.entries(summary)
    if (!entries.length) return '-'
    return entries.map(([status, count]) => `${status}:${count}`).join(' | ')
  }, [canonicalNodes])

  const dagLayout = useMemo(() => buildDagLayout(canonicalNodes), [canonicalNodes])
  const dagEdges = useMemo(() => buildDagEdges(canonicalNodes, nodeMap), [canonicalNodes, nodeMap])

  useEffect(() => {
    if (!canonicalNodes.length) return
    if (!selectedNodeId || !canonicalNodes.some((n) => n.id === selectedNodeId)) {
      setSelectedNodeId(canonicalNodes[0].id)
    }
  }, [canonicalNodes, selectedNodeId])

  const selectedNode = canonicalNodes.find((node) => node.id === selectedNodeId) || null
  const evidencePool = task?.checkpoint_data?.evidence_pool || null
  const evidenceRows = parseEvidenceRows(evidencePool?.markdown || '')
  const evidenceMap = useMemo(() => {
    const map = {}
    for (const row of evidenceRows) map[row.evidenceId] = row
    return map
  }, [evidenceRows])

  const transitionLogs = useMemo(() => {
    const logs = task?.checkpoint_data?.transition_logs || []
    return [...logs].sort((a, b) =>
      String(a?.created_at || '').localeCompare(String(b?.created_at || ''))
    )
  }, [task])

  const nodeDone = canonicalNodes.filter((node) =>
    ['done', 'completed'].includes(String(node.status || '').toLowerCase())
  ).length
  const nodeTotal = canonicalNodes.length
  const nodePercent = nodeTotal ? Math.round((nodeDone / nodeTotal) * 100) : 0
  const wordPercent =
    task?.target_words > 0
      ? Math.round(((task?.word_count || 0) / task.target_words) * 100)
      : 0

  const ganttRows = useMemo(() => {
    const rows = canonicalNodes
      .filter((n) => n.started_at)
      .map((node) => {
        const start = new Date(node.started_at).getTime()
        const end = node.finished_at ? new Date(node.finished_at).getTime() : Date.now()
        return {
          node,
          start,
          end: Number.isNaN(end) ? start : Math.max(start, end),
        }
      })
      .filter((r) => !Number.isNaN(r.start))
      .sort((a, b) => a.start - b.start)
    if (!rows.length) return { rows: [], rangeStart: 0, rangeEnd: 0 }
    const rangeStart = Math.min(...rows.map((r) => r.start))
    const rangeEnd = Math.max(...rows.map((r) => r.end))
    return { rows, rangeStart, rangeEnd: Math.max(rangeStart + 1, rangeEnd) }
  }, [canonicalNodes])

  const memorySummary = useMemo(() => {
    const outputText = String(task?.output_text || '')
    const cited = outputText.match(/E\d+/g) || []
    const citedUnique = new Set(cited)
    const categories = new Map()
    let highPriorityCount = 0
    for (const row of evidenceRows) {
      const category = String(row.category || '-')
      categories.set(category, (categories.get(category) || 0) + 1)
      if (/high|critical|p0|p1|高|紧急/i.test(String(row.priority || ''))) {
        highPriorityCount += 1
      }
    }
    return {
      evidenceCount: evidenceRows.length,
      citedCount: cited.length,
      citedUniqueCount: citedUnique.size,
      highPriorityCount,
      categoryText: Array.from(categories.entries())
        .slice(0, 6)
        .map(([name, count]) => `${name}:${count}`)
        .join(' · '),
      transitionCount: transitionLogs.length,
    }
  }, [evidenceRows, task?.output_text, transitionLogs.length])

  const memoryWritesByNode = useMemo(() => {
    const raw = task?.checkpoint_data?.control?.memory_writes
    if (!raw || typeof raw !== 'object') return []
    return Object.entries(raw)
      .map(([nodeId, rows]) => {
        const node = nodeMap[nodeId] || null
        const safeRows = Array.isArray(rows) ? rows : []
        return {
          nodeId,
          node,
          rows: safeRows.map((row) => ({
            at: row?.at || '',
            role: row?.role || node?.agent_role || '-',
            title: row?.title || node?.title || '-',
            summary: row?.summary || '',
            chars: Number(row?.chars || 0),
            depth: row?.depth || '',
            chapterIndex: row?.chapter_index,
            chapterTitle: row?.chapter_title || '',
          })),
        }
      })
      .filter((entry) => entry.rows.length > 0)
  }, [task, nodeMap])

  const memoryWriteRows = useMemo(() => {
    const rows = []
    for (const group of memoryWritesByNode) {
      for (const row of group.rows) {
        rows.push({
          ...row,
          nodeId: group.nodeId,
          nodeTitle: group.node?.title || '',
        })
      }
    }
    return rows.sort((a, b) => String(b.at || '').localeCompare(String(a.at || '')))
  }, [memoryWritesByNode])

  function focusEvidence(evidenceId) {
    setFocusedEvidenceId(evidenceId)
    const el = evidenceRowRefs.current[evidenceId]
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  if (!task) {
    return (
      <section className="card">
        <h2>监控中心</h2>
        <p className="muted">等待任务数据...</p>
      </section>
    )
  }

  return (
    <div className="page page-monitor page-pro-max">
      <section className="card monitor-card">
        <header className="card-head">
          <h2>任务监控中心</h2>
          <p>最后刷新: {lastRefreshAt ? new Date(lastRefreshAt).toLocaleTimeString() : '-'}</p>
        </header>

        <div className="module-scroll-x">
          <div className="module-width-lg">
            <div className="task-picker">
              <label>
                <span>选择任务</span>
                <select
                  value={taskId}
                  onChange={(e) => {
                    const next = e.target.value
                    setTaskId(next)
                    navigate(`/monitor/${next}`)
                  }}
                >
                  {tasks.map((item) => (
                    <option value={item.id} key={item.id}>
                      {normalizeDisplayText(item.title)} ({item.status})
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="kpi-grid">
              <div className="kpi-item">
                <span>状态</span>
                <strong>{task.status}</strong>
              </div>
              <div className="kpi-item">
                <span>FSM</span>
                <strong>{task.fsm_state || '-'}</strong>
              </div>
              <div className="kpi-item">
                <span>节点进度</span>
                <strong>
                  {nodeDone}/{nodeTotal} ({nodePercent}%)
                </strong>
              </div>
              <div className="kpi-item">
                <span>字数进度</span>
                <strong>
                  {task.word_count}/{task.target_words} ({wordPercent}%)
                </strong>
              </div>
              <div className="kpi-item">
                <span>运行时长</span>
                <strong>{formatDuration(task.created_at, task.finished_at)}</strong>
              </div>
              <div className="kpi-item">
                <span>阶段计数</span>
                <strong>{stageProgressText}</strong>
              </div>
            </div>
          </div>
        </div>
        <p className="hint">节点状态汇总: {nodeSummaryText}</p>
        {task.error_message ? <p className="error">错误: {task.error_message}</p> : null}
        {task.blocking_reason ? <p className="hint">阻塞原因: {task.blocking_reason}</p> : null}
        {error ? <p className="error">{error}</p> : null}
      </section>

      <section className="card monitor-card">
        <header className="card-head">
          <h2>DAG 可视连线图</h2>
          <p>经典 DAG 视图（实线=状态迁移，虚线=其他依赖）</p>
        </header>
        <div className="module-scroll-x">
          <div className="module-width-xl">
            <div className="dag-canvas-scroll">
              <div className="dag-canvas" style={{ width: dagLayout.width, height: dagLayout.height }}>
                <svg className="dag-canvas-svg" width={dagLayout.width} height={dagLayout.height}>
                  <defs>
                    <marker
                      id="dag-arrow-solid"
                      viewBox="0 0 10 10"
                      refX="9"
                      refY="5"
                      markerWidth="7"
                      markerHeight="7"
                      orient="auto"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" className="dag-arrow-solid" />
                    </marker>
                    <marker
                      id="dag-arrow-dashed"
                      viewBox="0 0 10 10"
                      refX="9"
                      refY="5"
                      markerWidth="7"
                      markerHeight="7"
                      orient="auto"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" className="dag-arrow-dashed" />
                    </marker>
                  </defs>

                  {dagEdges.map((edge) => {
                    const from = dagLayout.positions[edge.fromId]
                    const to = dagLayout.positions[edge.toId]
                    if (!from || !to) return null
                    const fromCenterX = from.x + from.width / 2
                    const fromCenterY = from.y + from.height / 2
                    const toCenterX = to.x + to.width / 2
                    const toCenterY = to.y + to.height / 2
                    const start = getRectBoundaryPoint(from, toCenterX, toCenterY)
                    const end = getRectBoundaryPoint(to, fromCenterX, fromCenterY)
                    const dx = end.x - start.x
                    const dy = end.y - start.y
                    const dist = Math.max(1, Math.hypot(dx, dy))
                    const nx = -dy / dist
                    const ny = dx / dist
                    const curve = Math.min(86, Math.max(22, dist * 0.12))
                    const mx = (start.x + end.x) / 2 + nx * curve
                    const my = (start.y + end.y) / 2 + ny * curve
                    const d = `M ${start.x} ${start.y} Q ${mx} ${my}, ${end.x} ${end.y}`
                    const isTransition = edge.kind === 'transition'
                    return (
                      <path
                        key={edge.id}
                        className={`dag-edge ${isTransition ? 'dag-edge-solid' : 'dag-edge-dashed'}`}
                        d={d}
                        markerEnd={`url(#${isTransition ? 'dag-arrow-solid' : 'dag-arrow-dashed'})`}
                      />
                    )
                  })}
                </svg>

                {canonicalNodes.map((node) => {
                  const pos = dagLayout.positions[node.id]
                  if (!pos) return null
                  return (
                    <button
                      key={node.id}
                      className={`dag-canvas-node status-${node.status} ${
                        selectedNodeId === node.id ? 'selected' : ''
                      }`}
                      onClick={() => setSelectedNodeId(node.id)}
                      style={{ left: pos.x, top: pos.y, width: pos.width, height: pos.height }}
                      title={`${normalizeDisplayText(node.title)} | ${node.stage_code || '-'} | ${node.status}`}
                      type="button"
                    >
                      <strong>{normalizeDisplayText(node.title)}</strong>
                      <small>
                        {node.stage_code || '-'} · {node.agent_role} · {node.status}
                      </small>
                      <small>
                        执行代理:{' '}
                        {node.assigned_agent
                          ? agentMap[node.assigned_agent]?.name || node.assigned_agent
                          : '未分配'}
                      </small>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="card monitor-card">
        <header className="card-head">
          <h2>DAG 节点墙</h2>
          <p>按 Stage 分组，固定展示全量节点（共 {canonicalNodes.length} 个）</p>
        </header>
        <div className="module-scroll-x">
          <div className="module-width-xl">
            <div className="dag-stage-grid">
              {groupedNodes.map(([stage, nodes]) => (
                <div className="stage-column" key={stage}>
                  <h3>{stage}</h3>
                  <div className="node-grid">
                    {nodes.map((node) => (
                      <article
                        key={node.id}
                        className={`dag-node status-${node.status} ${
                          selectedNodeId === node.id ? 'selected' : ''
                        }`}
                        onClick={() => setSelectedNodeId(node.id)}
                      >
                        <strong>{normalizeDisplayText(node.title)}</strong>
                        <div className="node-tags">
                          <span className="tag">{node.agent_role}</span>
                          <span className="tag">{node.status}</span>
                          <span className="tag">
                            {node.assigned_agent
                              ? `@${agentMap[node.assigned_agent]?.name || node.assigned_agent}`
                              : '@未分配'}
                          </span>
                        </div>
                        <small>依赖: {(node.depends_on || []).length || '无'}</small>
                      </article>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {selectedNode ? (
              <div className="node-detail">
                <h3>节点详情</h3>
                <div className="detail-grid">
                  <div className="detail-line">
                    <span>标题</span>
                    <strong>{normalizeDisplayText(selectedNode.title)}</strong>
                  </div>
                  <div className="detail-line">
                    <span>角色</span>
                    <strong>{selectedNode.agent_role}</strong>
                  </div>
                  <div className="detail-line">
                    <span>状态</span>
                    <strong>{selectedNode.status}</strong>
                  </div>
                  <div className="detail-line">
                    <span>执行代理</span>
                    <strong>
                      {selectedNode.assigned_agent
                        ? `${selectedNode.assigned_agent} (${agentMap[selectedNode.assigned_agent]?.name || '未知'})`
                        : '未分配'}
                    </strong>
                  </div>
                  <div className="detail-line">
                    <span>开始时间</span>
                    <strong>{formatTime(selectedNode.started_at)}</strong>
                  </div>
                  <div className="detail-line">
                    <span>结束时间</span>
                    <strong>{formatTime(selectedNode.finished_at)}</strong>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <section className="card monitor-card">
        <header className="card-head">
          <h2>节点执行甘特图</h2>
          <p>固定展示已启动节点（共 {ganttRows.rows.length} 个）</p>
        </header>
        <div className="module-scroll-x">
          <div className="module-width-lg">
            <div className="gantt-wrap">
              {ganttRows.rows.map((row) => {
                const duration = ganttRows.rangeEnd - ganttRows.rangeStart
                const leftPct = ((row.start - ganttRows.rangeStart) / duration) * 100
                const widthPct = ((row.end - row.start) / duration) * 100
                return (
                  <div className="gantt-row" key={row.node.id}>
                    <div className="gantt-label">
                      <strong>{normalizeDisplayText(row.node.title)}</strong>
                      <small>
                        {row.node.stage_code} · {row.node.status}
                      </small>
                    </div>
                    <div className="gantt-track">
                      <div
                        className={`gantt-bar status-${row.node.status}`}
                        style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 1.4)}%` }}
                        title={`${formatTime(row.node.started_at)} ~ ${formatTime(row.node.finished_at)}`}
                      />
                    </div>
                  </div>
                )
              })}
              {!ganttRows.rows.length ? <p className="muted">当前没有可展示的执行时序节点。</p> : null}
            </div>
          </div>
        </div>
      </section>

      <section className="card monitor-card">
        <header className="card-head">
          <h2>阶段迁移时间线</h2>
          <p>checkpoint_data.transition_logs</p>
        </header>
        <div className="module-scroll-x">
          <div className="module-width-lg">
            <ol className="timeline-list">
              {transitionLogs.map((log, idx) => (
                <li className="timeline-item" key={`${log.created_at}-${idx}`}>
                  <div className="timeline-left">
                    <strong>
                      {log.from_state || '-'} → {log.to_state || '-'}
                    </strong>
                    <small>{formatTime(log.created_at)}</small>
                  </div>
                  <div className="timeline-right">
                    <span>{log.reason || '-'}</span>
                    <span>{log.metadata?.node_role || '-'}</span>
                    <span>{log.created_by || '-'}</span>
                  </div>
                </li>
              ))}
              {!transitionLogs.length ? <li className="muted">暂无阶段迁移日志</li> : null}
            </ol>
          </div>
        </div>
      </section>

      <section className="card monitor-card">
        <header className="card-head">
          <h2>记忆层</h2>
          <p>SessionMemory / KnowledgeGraph / 节点写入明细</p>
        </header>
        <div className="module-scroll-x">
          <div className="module-width-lg">
            <p className="memory-explain">
              当前任务记忆由两层协同：SessionMemory 负责单任务去重与短期上下文拼接，KnowledgeGraph
              负责跨任务的长期知识沉淀；证据池条目会在章节写作与一致性校验阶段反复被引用。
            </p>
            <div className="memory-grid">
              <article className="memory-block">
                <h3>记忆链路说明</h3>
                <ul className="memory-list">
                  <li>写作前先检索已有证据，优先复用高置信信息，减少重复生成。</li>
                  <li>章节输出时写入引用编号（E1/E2...），便于后续追溯来源。</li>
                  <li>一致性阶段按证据反查关键论断，发现冲突后触发修复。</li>
                </ul>
              </article>
              <article className="memory-block">
                <h3>本任务记忆快照</h3>
                <ul className="memory-list">
                  <li>节点写入条数: {memoryWriteRows.length}</li>
                  <li>有写入的节点数: {memoryWritesByNode.length}</li>
                  <li>证据条目数: {memorySummary.evidenceCount}</li>
                  <li>高优先级证据: {memorySummary.highPriorityCount}</li>
                  <li>报告引用次数: {memorySummary.citedCount}</li>
                  <li>去重后引用证据: {memorySummary.citedUniqueCount}</li>
                  <li>阶段迁移日志: {memorySummary.transitionCount}</li>
                  <li>类别分布: {memorySummary.categoryText || '暂无分类信息'}</li>
                </ul>
              </article>
            </div>

            <div className="evidence-table-wrap">
              <table className="task-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>节点</th>
                    <th>角色</th>
                    <th>写入摘要</th>
                  </tr>
                </thead>
                <tbody>
                  {memoryWriteRows.slice(0, 50).map((row, idx) => (
                    <tr key={`${row.nodeId}-${row.at}-${idx}`}>
                      <td>{formatTime(row.at)}</td>
                      <td>{normalizeDisplayText(row.nodeTitle || row.title || '-')}</td>
                      <td>{row.role || '-'}</td>
                      <td className="memory-summary-cell">{renderMemorySummary(row.summary)}</td>
                    </tr>
                  ))}
                  {!memoryWriteRows.length ? (
                    <tr>
                      <td colSpan={4} className="muted">
                        暂无节点记忆写入明细（后端将在节点落库后写入此处）
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <section className="card monitor-card">
        <header className="card-head">
          <h2>证据池</h2>
          <p>evidence_pool 快照与引用跳转</p>
        </header>
        <div className="module-scroll-x">
          <div className="module-width-lg">

            <div className="evidence-table-wrap">
              <table className="task-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Category</th>
                    <th>Priority</th>
                    <th>Title</th>
                  </tr>
                </thead>
                <tbody>
                  {evidenceRows.slice(0, 20).map((row) => (
                    <tr
                      key={row.evidenceId}
                      className={focusedEvidenceId === row.evidenceId ? 'evidence-row-active' : ''}
                      ref={(el) => {
                        if (el) evidenceRowRefs.current[row.evidenceId] = el
                      }}
                    >
                      <td>{row.evidenceId}</td>
                      <td>{row.category}</td>
                      <td>{row.priority}</td>
                      <td>
                        {row.url ? (
                          <a href={row.url} target="_blank" rel="noreferrer">
                            {normalizeDisplayText(row.title)}
                          </a>
                        ) : (
                          normalizeDisplayText(row.title)
                        )}
                      </td>
                    </tr>
                  ))}
                  {!evidenceRows.length ? (
                    <tr>
                      <td colSpan={4} className="muted">
                        暂无证据池快照
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <section className="card monitor-card">
        <header className="card-head">
          <h2>报告实时预览</h2>
          <p>自动轮询 output_text（点击 E 编号跳转证据）</p>
        </header>
        <div className="module-scroll-x">
          <div className="module-width-md">
            <article className="report-box">
              {renderReportWithEvidence(task.output_text, evidenceMap, focusEvidence)}
            </article>
          </div>
        </div>
      </section>
    </div>
  )
}
