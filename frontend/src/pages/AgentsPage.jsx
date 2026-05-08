import { PageHeader } from '../components/PageHeader'
import { SectionCard } from '../components/SectionCard'

const presets = [
  { name: 'Researcher', state: 'active', capability: '信息搜集 / 资料整合' },
  { name: 'Planner', state: 'idle', capability: '结构拆解 / 计划生成' },
  { name: 'Writer', state: 'active', capability: '内容生成 / 结果润色' },
]

export function AgentsPage() {
  return (
    <div className="page-stack">
      <PageHeader title="工作台" subtitle="查看协作 Agent 的状态与角色分工。" />
      <SectionCard title="Agent 列表">
        <ul className="agent-list">
          {presets.map((agent) => (
            <li key={agent.name}>
              <div>
                <strong>{agent.name}</strong>
                <p>{agent.capability}</p>
              </div>
              <span className={`status-pill ${agent.state === 'active' ? 'ok' : ''}`}>
                {agent.state}
              </span>
            </li>
          ))}
        </ul>
      </SectionCard>
    </div>
  )
}
