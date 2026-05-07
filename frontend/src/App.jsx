import { NavLink, Navigate, Route, Routes } from 'react-router-dom'

import { AgentsPage } from './pages/AgentsPage'
import { HomePage } from './pages/HomePage'
import { MonitorPage } from './pages/MonitorPage'

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
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
