import { Link, Route, Routes } from 'react-router-dom'

import { AgentsPage } from './pages/AgentsPage'
import { HistoryPage } from './pages/HistoryPage'
import { HomePage } from './pages/HomePage'
import { MonitorPage } from './pages/MonitorPage'

export function App() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>ThinkWeave</h1>
        <nav>
          <Link to="/">任务创建</Link>
          <Link to="/agents">Agent 管理</Link>
          <Link to="/history">历史任务</Link>
        </nav>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/monitor/:taskId" element={<MonitorPage />} />
        </Routes>
      </main>
    </div>
  )
}
