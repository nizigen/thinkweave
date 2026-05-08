import { NavLink, Navigate, Route, Routes } from 'react-router-dom'

import { AgentsPage } from './pages/AgentsPage'
import { ArtifactsPage } from './pages/ArtifactsPage'
import { ConsistencyRepairPage } from './pages/ConsistencyRepairPage'
import { DecompositionAuditPage } from './pages/DecompositionAuditPage'
import { HomePage } from './pages/HomePage'
import { MonitorPage } from './pages/MonitorPage'
import { RoutingDebugPage } from './pages/RoutingDebugPage'
import { RuntimeHealthPage } from './pages/RuntimeHealthPage'
import { TaskDetailPage } from './pages/TaskDetailPage'

export function App() {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand">
          <h1>ThinkWeave</h1>
          <p>Hierarchical Agent Control Room</p>
        </div>
        <nav className="main-nav">
          <NavLink to="/" end>
            主页
          </NavLink>
          <NavLink to="/agents">Agent 管理</NavLink>
          <NavLink to="/monitor">监控中心</NavLink>
          <NavLink to="/ops/task-detail">任务详情</NavLink>
          <NavLink to="/ops/decomposition">分解审计</NavLink>
          <NavLink to="/ops/routing">路由决策</NavLink>
          <NavLink to="/ops/consistency">一致性修复</NavLink>
          <NavLink to="/ops/artifacts">产物中心</NavLink>
          <NavLink to="/ops/runtime">系统健康</NavLink>
        </nav>

        <div className="sidebar-foot">
          <p>Realtime DAG + Memory Monitor</p>
          <small>Redis Streams / FSM / Cognee</small>
        </div>
      </aside>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/monitor" element={<MonitorPage />} />
          <Route path="/monitor/:taskId" element={<MonitorPage />} />
          <Route path="/ops/task-detail" element={<TaskDetailPage />} />
          <Route path="/ops/decomposition" element={<DecompositionAuditPage />} />
          <Route path="/ops/routing" element={<RoutingDebugPage />} />
          <Route path="/ops/consistency" element={<ConsistencyRepairPage />} />
          <Route path="/ops/artifacts" element={<ArtifactsPage />} />
          <Route path="/ops/runtime" element={<RuntimeHealthPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
