import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { TaskSelectorBar } from '../components/TaskSelectorBar'
import { normalizeDisplayText } from '../lib/text'
import { useTaskExplorer } from '../lib/useTaskExplorer'
import { formatDuration, formatTime, summaryTextMap } from '../lib/taskViewUtils'

export function TaskDetailPage() {
  const {
    tasks,
    taskId,
    setTaskId,
    task,
    listError,
    taskError,
    listLoading,
    nodeStatusSummary,
  } = useTaskExplorer()

  const nodes = Array.isArray(task?.nodes) ? task.nodes : []
  const roleSummary = useMemo(() => {
    const summary = {}
    for (const node of nodes) {
      const key = node.agent_role || 'unknown'
      summary[key] = (summary[key] || 0) + 1
    }
    return summary
  }, [nodes])

  return (
    <div className="page page-pro-max page-ops">
      <section className="card">
        <header className="card-head">
          <h2>任务详情页</h2>
          <p>任务基础信息、节点全量清单、执行时序与路由结果</p>
        </header>
        <TaskSelectorBar
          tasks={tasks}
          taskId={taskId}
          setTaskId={setTaskId}
          listLoading={listLoading}
          listError={listError}
          taskError={taskError}
        />
        {task ? (
          <div className="kpi-grid">
            <div className="kpi-item">
              <span>任务状态</span>
              <strong>{task.status}</strong>
            </div>
            <div className="kpi-item">
              <span>FSM</span>
              <strong>{task.fsm_state || '-'}</strong>
            </div>
            <div className="kpi-item">
              <span>字数</span>
              <strong>
                {task.word_count || 0}/{task.target_words || 0}
              </strong>
            </div>
            <div className="kpi-item">
              <span>节点状态</span>
              <strong>{summaryTextMap(nodeStatusSummary)}</strong>
            </div>
            <div className="kpi-item">
              <span>角色构成</span>
              <strong>{summaryTextMap(roleSummary)}</strong>
            </div>
            <div className="kpi-item">
              <span>创建时间</span>
              <strong>{formatTime(task.created_at)}</strong>
            </div>
          </div>
        ) : null}
        {task ? (
          <div className="ops-link-row">
            <Link className="btn btn-ghost" to={`/monitor/${task.id}`}>
              打开监控中心
            </Link>
            <Link className="btn btn-ghost" to="/ops/decomposition">
              分解审计
            </Link>
            <Link className="btn btn-ghost" to="/ops/routing">
              路由决策
            </Link>
            <Link className="btn btn-ghost" to="/ops/consistency">
              一致性修复
            </Link>
            <Link className="btn btn-ghost" to="/ops/artifacts">
              产物中心
            </Link>
          </div>
        ) : null}
      </section>

      <section className="card">
        <header className="card-head">
          <h2>节点清单</h2>
          <p>默认按角色和标题排序，便于快速检查是否缺章、错章或路由异常</p>
        </header>
        <div className="task-table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>角色</th>
                <th>节点标题</th>
                <th>状态</th>
                <th>路由</th>
                <th>依赖数</th>
                <th>开始/结束</th>
                <th>耗时</th>
              </tr>
            </thead>
            <tbody>
              {[...nodes]
                .sort((a, b) => {
                  const rs = String(a.agent_role || '').localeCompare(String(b.agent_role || ''))
                  if (rs !== 0) return rs
                  return String(a.title || '').localeCompare(String(b.title || ''))
                })
                .map((node) => (
                  <tr key={node.id}>
                    <td>{node.agent_role || '-'}</td>
                    <td>{normalizeDisplayText(node.title || '-')}</td>
                    <td>
                      <span className={`status-dot status-${node.status}`} />
                      {node.status}
                    </td>
                    <td>{node.routing_reason || node.routing_status || '-'}</td>
                    <td>{Array.isArray(node.depends_on) ? node.depends_on.length : 0}</td>
                    <td>
                      {formatTime(node.started_at)} / {formatTime(node.finished_at)}
                    </td>
                    <td>{formatDuration(node.started_at, node.finished_at)}</td>
                  </tr>
                ))}
              {!nodes.length ? (
                <tr>
                  <td colSpan={7} className="muted">
                    当前任务还没有节点数据
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

