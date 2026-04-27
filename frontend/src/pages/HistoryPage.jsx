import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiUrl, authHeaders } from '../lib/apiBase'

export function HistoryPage() {
  const [items, setItems] = useState([])

  useEffect(() => {
    let canceled = false
    async function load() {
      const resp = await fetch(apiUrl('/api/tasks'), {
        headers: authHeaders(),
      })
      const data = await resp.json()
      if (!canceled) {
        setItems(data.items || [])
      }
    }
    void load()
    const id = setInterval(() => void load(), 2000)
    return () => {
      canceled = true
      clearInterval(id)
    }
  }, [])

  return (
    <section>
      <h2>历史任务</h2>
      <ul className="task-list">
        {items.map((task) => (
          <li key={task.id}>
            <strong>{task.title}</strong>
            <span>{task.status}</span>
            <Link to={`/monitor/${task.id}`}>查看监控</Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
