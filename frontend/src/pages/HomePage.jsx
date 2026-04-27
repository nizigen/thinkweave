import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiUrl, authHeaders } from '../lib/apiBase'

export function HomePage() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [depth, setDepth] = useState('standard')
  const [mode, setMode] = useState('report')
  const [targetWords, setTargetWords] = useState(10000)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function createTask() {
    setError('')
    setLoading(true)
    try {
      const resp = await fetch(apiUrl('/api/tasks'), {
        method: 'POST',
        headers: authHeaders({ 'content-type': 'application/json' }),
        body: JSON.stringify({ title, depth, mode, target_words: targetWords }),
      })
      if (!resp.ok) {
        setError(`创建失败: ${resp.status}`)
        return
      }
      const data = await resp.json()
      navigate(`/monitor/${data.id}`)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section>
      <h2>新建任务</h2>
      <label>标题</label>
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="输入主题标题" />

      <label>模式</label>
      <select value={mode} onChange={(e) => setMode(e.target.value)}>
        <option value="report">report</option>
        <option value="novel">novel</option>
        <option value="custom">custom</option>
      </select>

      <label>深度</label>
      <select value={depth} onChange={(e) => setDepth(e.target.value)}>
        <option value="quick">quick</option>
        <option value="standard">standard</option>
        <option value="deep">deep</option>
      </select>

      <label>目标字数</label>
      <input type="number" value={targetWords} onChange={(e) => setTargetWords(Number(e.target.value || 0))} />

      <button onClick={createTask} disabled={loading || title.length < 6}>
        {loading ? '创建中...' : '开始生成'}
      </button>
      {error ? <p className="error">{error}</p> : null}
    </section>
  )
}
