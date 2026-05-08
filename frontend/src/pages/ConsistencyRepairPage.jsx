import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { TaskSelectorBar } from '../components/TaskSelectorBar'
import { normalizeDisplayText } from '../lib/text'
import { useTaskExplorer } from '../lib/useTaskExplorer'
import { formatTime } from '../lib/taskViewUtils'

function isRepairNodeTitle(title) {
  const text = String(title || '')
  return (
    text.includes('一致性定向修复') ||
    text.includes('一致性修复审查') ||
    text.includes('一致性复核') ||
    text.includes('自动补写轮次')
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

export function ConsistencyRepairPage() {
  const {
    tasks,
    taskId,
    setTaskId,
    task,
    listError,
    taskError,
    listLoading,
  } = useTaskExplorer()

  const nodes = Array.isArray(task?.nodes) ? task.nodes : []
  const checkpoint = task?.checkpoint_data || {}
  const budget = checkpoint?.consistency_repair_budget || null
  const softFailures = Array.isArray(checkpoint?.consistency_soft_failures)
    ? checkpoint.consistency_soft_failures
    : []
  const repairNodes = nodes.filter((node) => isRepairNodeTitle(node.title))
  const consistencyNodes = nodes.filter((node) => String(node.agent_role || '').toLowerCase() === 'consistency')

  const memoryWrites = useMemo(() => {
    const raw = checkpoint?.control?.memory_writes
    if (!raw || typeof raw !== 'object') return []
    const rows = []
    for (const [nodeId, items] of Object.entries(raw)) {
      if (!Array.isArray(items)) continue
      for (const row of items) {
        rows.push({
          nodeId,
          role: row?.role || '-',
          title: row?.title || '-',
          summary: row?.summary || '-',
          at: row?.at || '',
        })
      }
    }
    return rows
      .filter((row) => ['writer', 'consistency'].includes(String(row.role || '').toLowerCase()))
      .sort((a, b) => String(b.at || '').localeCompare(String(a.at || '')))
      .slice(0, 20)
  }, [checkpoint])

  return (
    <div className="page page-pro-max page-ops">
      <section className="card">
        <header className="card-head">
          <h2>一致性修复页</h2>
          <p>展示 consistency 的修复预算、软失败事件、修复波次节点和相关记忆写入</p>
        </header>
        <TaskSelectorBar
          tasks={tasks}
          taskId={taskId}
          setTaskId={setTaskId}
          listLoading={listLoading}
          listError={listError}
          taskError={taskError}
        />
        <div className="kpi-grid">
          <div className="kpi-item">
            <span>Consistency 节点</span>
            <strong>{consistencyNodes.length}</strong>
          </div>
          <div className="kpi-item">
            <span>修复波次节点</span>
            <strong>{repairNodes.length}</strong>
          </div>
          <div className="kpi-item">
            <span>软失败事件</span>
            <strong>{softFailures.length}</strong>
          </div>
        </div>
        <pre className="json-box">{JSON.stringify(budget || {}, null, 2)}</pre>
      </section>

      <section className="card">
        <header className="card-head">
          <h2>修复波次节点</h2>
          <p>如果 consistency 判定不过关，系统会注入这些节点完成定向修复与复核</p>
        </header>
        <div className="task-table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>角色</th>
                <th>标题</th>
                <th>状态</th>
                <th>依赖数</th>
              </tr>
            </thead>
            <tbody>
              {repairNodes.map((node) => (
                <tr key={node.id}>
                  <td>{node.agent_role || '-'}</td>
                  <td>{normalizeDisplayText(node.title || '-')}</td>
                  <td>{node.status || '-'}</td>
                  <td>{Array.isArray(node.depends_on) ? node.depends_on.length : 0}</td>
                </tr>
              ))}
              {!repairNodes.length ? (
                <tr>
                  <td colSpan={4} className="muted">
                    当前任务还没有触发一致性修复波次
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <header className="card-head">
          <h2>Writer/Consistency 记忆写入</h2>
          <p>用于检查修复轮次是否把关键上下文写回记忆层</p>
        </header>
        <div className="task-table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>角色</th>
                <th>节点标题</th>
                <th>摘要</th>
              </tr>
            </thead>
            <tbody>
              {memoryWrites.map((row, idx) => (
                <tr key={`${row.nodeId}-${idx}`}>
                  <td>{formatTime(row.at)}</td>
                  <td>{row.role}</td>
                  <td>{normalizeDisplayText(row.title)}</td>
                  <td className="memory-summary-cell">{renderMemorySummary(row.summary)}</td>
                </tr>
              ))}
              {!memoryWrites.length ? (
                <tr>
                  <td colSpan={4} className="muted">
                    当前没有 writer/consistency 的记忆写入记录
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
