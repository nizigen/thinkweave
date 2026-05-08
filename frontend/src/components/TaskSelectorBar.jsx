import { normalizeDisplayText } from '../lib/text'

export function TaskSelectorBar({
  tasks,
  taskId,
  setTaskId,
  listLoading,
  listError,
  taskError,
  auditError = '',
}) {
  return (
    <div className="task-picker toolbar-row">
      <label className="toolbar-item">
        <span>选择任务</span>
        <select value={taskId} onChange={(e) => setTaskId(e.target.value)}>
          {!tasks.length ? <option value="">暂无任务</option> : null}
          {tasks.map((item) => (
            <option key={item.id} value={item.id}>
              {normalizeDisplayText(item.title)} ({item.status})
            </option>
          ))}
        </select>
      </label>
      <div className="toolbar-state">
        {listLoading ? <span className="muted">任务列表加载中...</span> : null}
        {listError ? <span className="error">{listError}</span> : null}
        {taskError ? <span className="error">{taskError}</span> : null}
        {auditError ? <span className="error">{auditError}</span> : null}
      </div>
    </div>
  )
}

