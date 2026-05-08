import { TaskSelectorBar } from '../components/TaskSelectorBar'
import { normalizeDisplayText } from '../lib/text'
import { useTaskExplorer } from '../lib/useTaskExplorer'

export function DecompositionAuditPage() {
  const {
    tasks,
    taskId,
    setTaskId,
    audit,
    listError,
    taskError,
    auditError,
    listLoading,
  } = useTaskExplorer({ withAudit: true })

  const rows = Array.isArray(audit?.records) ? audit.records : []
  const newest = rows[0] || null
  const latestTrace = newest?.trace || {}
  const repairActions = Array.isArray(latestTrace?.repair_actions)
    ? latestTrace.repair_actions
    : []
  const normalizedNodes = Array.isArray(latestTrace?.normalized_dag?.nodes)
    ? latestTrace.normalized_dag.nodes
    : []

  return (
    <div className="page page-pro-max page-ops">
      <section className="card">
        <header className="card-head">
          <h2>分解审计页</h2>
          <p>查看任务拆解证据链：输入、修复动作、归一化 DAG 与最终节点</p>
        </header>
        <TaskSelectorBar
          tasks={tasks}
          taskId={taskId}
          setTaskId={setTaskId}
          listLoading={listLoading}
          listError={listError}
          taskError={taskError}
          auditError={auditError}
        />
        {newest ? (
          <div className="kpi-grid">
            <div className="kpi-item">
              <span>Audit ID</span>
              <strong>{newest.audit_id || '-'}</strong>
            </div>
            <div className="kpi-item">
              <span>节点数</span>
              <strong>{newest.node_count || 0}</strong>
            </div>
            <div className="kpi-item">
              <span>修复动作数</span>
              <strong>{newest.repair_actions_count || 0}</strong>
            </div>
            <div className="kpi-item">
              <span>校验问题数</span>
              <strong>{newest.validation_issues_count || 0}</strong>
            </div>
          </div>
        ) : (
          <p className="muted">当前任务暂无 decomposition audit 记录。</p>
        )}
      </section>

      <section className="card">
        <header className="card-head">
          <h2>Repair Actions</h2>
          <p>每个动作都表示一次 DAG 结构修正，便于追踪“为什么出现这些节点”</p>
        </header>
        <div className="task-table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>步骤</th>
                <th>变更前节点数</th>
                <th>变更后节点数</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              {repairActions.map((item, idx) => (
                <tr key={`${item.step}-${idx}`}>
                  <td>{item.step || '-'}</td>
                  <td>{item.before_nodes ?? '-'}</td>
                  <td>{item.after_nodes ?? '-'}</td>
                  <td>{item.reason || '-'}</td>
                </tr>
              ))}
              {!repairActions.length ? (
                <tr>
                  <td colSpan={4} className="muted">
                    没有 repair_actions，说明分解结果基本直接通过。
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <header className="card-head">
          <h2>Normalized DAG</h2>
          <p>最终进入执行层的 DAG 归一化视图（不是原始 LLM 草稿）</p>
        </header>
        <div className="task-table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>角色</th>
                <th>标题</th>
                <th>依赖</th>
                <th>路由模式</th>
                <th>能力要求</th>
              </tr>
            </thead>
            <tbody>
              {normalizedNodes.map((node) => (
                <tr key={node.id}>
                  <td>{node.id}</td>
                  <td>{node.role || '-'}</td>
                  <td>{normalizeDisplayText(node.title || '-')}</td>
                  <td>{Array.isArray(node.depends_on) ? node.depends_on.join(', ') : '-'}</td>
                  <td>{node.routing_mode || 'auto'}</td>
                  <td>
                    {Array.isArray(node.required_capabilities)
                      ? node.required_capabilities.join(', ')
                      : '-'}
                  </td>
                </tr>
              ))}
              {!normalizedNodes.length ? (
                <tr>
                  <td colSpan={6} className="muted">
                    当前没有 normalized_dag 数据。
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

