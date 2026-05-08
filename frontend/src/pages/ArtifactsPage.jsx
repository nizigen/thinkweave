import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { TaskSelectorBar } from '../components/TaskSelectorBar'
import { normalizeDisplayText } from '../lib/text'
import { useTaskExplorer } from '../lib/useTaskExplorer'
import { parseEvidenceRows } from '../lib/taskViewUtils'

export function ArtifactsPage() {
  const {
    tasks,
    taskId,
    setTaskId,
    task,
    listError,
    taskError,
    listLoading,
  } = useTaskExplorer()

  const checkpoint = task?.checkpoint_data || {}
  const evidencePool = checkpoint?.evidence_pool || {}
  const evidenceRows = parseEvidenceRows(evidencePool?.markdown || '')
  const reportText = String(task?.output_text || '').trim()
  const hasReport = reportText.length > 0

  return (
    <div className="page page-pro-max page-ops">
      <section className="card">
        <header className="card-head">
          <h2>产物中心</h2>
          <p>查看任务报告正文、证据池条目、来源分布，作为交付验收入口</p>
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
            <span>任务状态</span>
            <strong>{task?.status || '-'}</strong>
          </div>
          <div className="kpi-item">
            <span>报告字数</span>
            <strong>{task?.word_count || 0}</strong>
          </div>
          <div className="kpi-item">
            <span>证据条目</span>
            <strong>{evidenceRows.length}</strong>
          </div>
        </div>
      </section>

      <section className="card">
        <header className="card-head">
          <h2>报告正文</h2>
          <p>渲染 `output_text`，用于快速检查结构完整性与可读性</p>
        </header>
        {hasReport ? (
          <div className="report-box">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{reportText}</ReactMarkdown>
          </div>
        ) : (
          <p className="muted">当前任务暂无报告正文输出。</p>
        )}
      </section>

      <section className="card">
        <header className="card-head">
          <h2>证据池</h2>
          <p>基于 `checkpoint_data.evidence_pool.markdown` 解析</p>
        </header>
        <div className="task-table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>类别</th>
                <th>优先级</th>
                <th>标题</th>
                <th>来源</th>
              </tr>
            </thead>
            <tbody>
              {evidenceRows.map((row) => (
                <tr key={row.evidenceId}>
                  <td>{row.evidenceId}</td>
                  <td>{row.category}</td>
                  <td>{row.priority}</td>
                  <td>{normalizeDisplayText(row.title)}</td>
                  <td>
                    {row.url ? (
                      <a href={row.url} target="_blank" rel="noreferrer">
                        {row.source || 'link'}
                      </a>
                    ) : (
                      row.source
                    )}
                  </td>
                </tr>
              ))}
              {!evidenceRows.length ? (
                <tr>
                  <td colSpan={5} className="muted">
                    当前任务证据池为空
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

