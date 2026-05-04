import { useEffect, useState } from 'react'
import { apiUrl, authHeaders } from '../lib/apiBase'

export function AgentsPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError('')
      try {
        const resp = await fetch(apiUrl('/api/agents'), {
          headers: authHeaders(),
        })
        if (!resp.ok) {
          setError(`加载失败: ${resp.status}`)
          return
        }
        const data = await resp.json()
        if (!cancelled) {
          setItems(Array.isArray(data) ? data : [])
        }
      } catch (e) {
        if (!cancelled) {
          setError(String(e))
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section>
      <h2>Agent 管理</h2>
      {loading ? <p>加载中...</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {!loading && !error ? (
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>角色</th>
              <th>层级</th>
              <th>模型</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {items.map((agent) => (
              <tr key={agent.id}>
                <td>{agent.name || '-'}</td>
                <td>{agent.role || '-'}</td>
                <td>{agent.layer ?? '-'}</td>
                <td>{agent.model || '-'}</td>
                <td>{agent.status || '-'}</td>
              </tr>
            ))}
            {items.length === 0 ? (
              <tr>
                <td colSpan={5}>暂无 agent</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      ) : null}
    </section>
  )
}
