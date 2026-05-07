import { useEffect, useMemo, useState } from 'react'
import { authHeaders, requestJson } from '../lib/apiBase'

function splitCsv(value) {
  return String(value || '')
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean)
}

export function AgentsPage() {
  const [items, setItems] = useState([])
  const [skills, setSkills] = useState([])
  const [modelOptions, setModelOptions] = useState([])
  const [rolePresets, setRolePresets] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [health, setHealth] = useState(null)
  const [healthError, setHealthError] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [createMessage, setCreateMessage] = useState('')
  const [deleteMessage, setDeleteMessage] = useState('')
  const [statusMessage, setStatusMessage] = useState('')

  const [form, setForm] = useState({
    name: '',
    role: 'writer',
    layer: 2,
    capabilities: '',
    model: 'deepseek-v3.2',
    custom_model: '',
    goal: '',
    backstory: '',
    description: '',
    system_message: '',
    temperature: 0.3,
    max_tokens: 2000,
    max_retries: 3,
    fallback_models_text: '',
    skill_allowlist: [],
    tags_text: '',
  })

  useEffect(() => {
    let cancelled = false
    let timer = null

    const loadAgents = async () => {
      setError('')
      setLoading(true)
      try {
        const data = await requestJson('/api/agents', { headers: authHeaders() })
        if (!cancelled) {
          const list = Array.isArray(data) ? data : []
          setItems(list)
          if (!selectedId && list.length) {
            setSelectedId(list[0].id)
          }
        }
      } catch (e) {
        if (!cancelled) setError(String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
      if (!cancelled) timer = setTimeout(loadAgents, 2500)
    }

    const loadMeta = async () => {
      try {
        const [skillData, modelData, presetData] = await Promise.all([
          requestJson('/api/agents/skills', { headers: authHeaders() }),
          requestJson('/api/agents/model-options', { headers: authHeaders() }),
          requestJson('/api/agents/role-presets', { headers: authHeaders() }),
        ])
        if (cancelled) return
        setSkills(Array.isArray(skillData) ? skillData : [])
        setModelOptions(Array.isArray(modelData) ? modelData : [])
        setRolePresets(Array.isArray(presetData) ? presetData : [])
      } catch {
        // 这些元数据接口不阻塞主流程
      }
    }

    loadAgents()
    loadMeta()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [selectedId])

  useEffect(() => {
    if (!selectedId) return
    let cancelled = false
    let timer = null

    const loadHealth = async () => {
      setHealthError('')
      try {
        const data = await requestJson(`/api/agents/${selectedId}/health`, {
          headers: authHeaders(),
        })
        if (!cancelled) setHealth(data)
      } catch (e) {
        if (!cancelled) setHealthError(String(e))
      }
      if (!cancelled) timer = setTimeout(loadHealth, 2500)
    }

    loadHealth()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [selectedId])

  const selected = items.find((agent) => agent.id === selectedId) || null

  const rolePresetMap = useMemo(() => {
    const m = {}
    for (const preset of rolePresets) m[preset.role] = preset
    return m
  }, [rolePresets])

  const agentsByLayer = useMemo(() => {
    const map = new Map([
      [0, []],
      [1, []],
      [2, []],
    ])
    for (const agent of items) {
      const layer = Number.isFinite(Number(agent.layer)) ? Number(agent.layer) : 2
      if (!map.has(layer)) map.set(layer, [])
      map.get(layer).push(agent)
    }
    for (const layerAgents of map.values()) {
      layerAgents.sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')))
    }
    return Array.from(map.entries()).sort((a, b) => a[0] - b[0])
  }, [items])

  function applyPreset(role) {
    const preset = rolePresetMap[role]
    if (!preset) return
    setForm((prev) => ({
      ...prev,
      role,
      layer: preset.layer ?? prev.layer,
      model: preset.default_model || prev.model,
      skill_allowlist: preset.agent_config?.skill_allowlist || prev.skill_allowlist,
    }))
  }

  function toggleListValue(field, value) {
    setForm((prev) => {
      const cur = new Set(prev[field] || [])
      if (cur.has(value)) cur.delete(value)
      else cur.add(value)
      return { ...prev, [field]: Array.from(cur) }
    })
  }

  async function createAgent() {
    setCreateMessage('')
    setSaving(true)
    try {
      const tags = splitCsv(form.tags_text)
      const payload = {
        name: form.name.trim(),
        role: form.role,
        layer: Number(form.layer),
        capabilities: form.capabilities.trim() || null,
        model: form.model || null,
        custom_model: form.custom_model.trim() || null,
        agent_config: {
          goal: form.goal.trim() || null,
          backstory: form.backstory.trim() || null,
          description: form.description.trim() || null,
          system_message: form.system_message.trim() || null,
          temperature: Number(form.temperature),
          max_tokens: Number(form.max_tokens),
          max_retries: Number(form.max_retries),
          fallback_models: splitCsv(form.fallback_models_text),
          skill_allowlist: form.skill_allowlist,
          tags,
        },
      }
      const created = await requestJson('/api/agents', {
        method: 'POST',
        headers: authHeaders({ 'content-type': 'application/json' }),
        body: JSON.stringify(payload),
      })
      setCreateMessage(`已创建: ${created.name}`)
      setSelectedId(created.id)
      setForm((prev) => ({ ...prev, name: '', capabilities: '', custom_model: '' }))
    } catch (e) {
      setCreateMessage(String(e))
    } finally {
      setSaving(false)
    }
  }

  async function deleteSelected() {
    if (!selectedId) return
    const ok = window.confirm('确认删除当前 Agent？')
    if (!ok) return
    setDeleteMessage('')
    try {
      await requestJson(`/api/agents/${selectedId}`, {
        method: 'DELETE',
        headers: authHeaders(),
      })
      setDeleteMessage('删除成功')
      setSelectedId('')
    } catch (e) {
      setDeleteMessage(String(e))
    }
  }

  async function setStatus(status) {
    if (!selectedId) return
    setStatusMessage('')
    try {
      await requestJson(`/api/agents/${selectedId}/status`, {
        method: 'PATCH',
        headers: authHeaders({ 'content-type': 'application/json' }),
        body: JSON.stringify({ status }),
      })
      setStatusMessage(`状态已更新为 ${status}`)
    } catch (e) {
      setStatusMessage(String(e))
    }
  }

  return (
    <div className="page page-agents page-pro-max">
      <section className="card card-create-agent">
        <header className="card-head">
          <h2>Agent 管理台</h2>
          <p>支持创建/查看/删除 Agent，按 L0/L1/L2 分层展示运行中的编排体系</p>
        </header>
        {loading ? <p className="muted">加载中...</p> : null}
        {error ? <p className="error">{error}</p> : null}

        <div className="layer-grid">
          {agentsByLayer.map(([layer, layerAgents]) => (
            <section className="layer-column" key={`layer-${layer}`}>
              <h3>
                L{layer}{' '}
                {layer === 0
                  ? '编排层（Orchestrator）'
                  : layer === 1
                    ? '管理层（Manager）'
                    : '执行层（Workers）'}
              </h3>
              <p className="muted layer-desc">
                {layer === 0
                  ? '负责任务分解、DAG 构建和全局调度。'
                  : layer === 1
                    ? '负责资源协调、策略收敛和子任务分配。'
                    : '负责大纲、调研、写作、审查、一致性等执行任务。'}
              </p>
              <div className="agent-grid">
                {layerAgents.map((agent) => (
                  <article
                    key={agent.id}
                    className={`agent-card ${selectedId === agent.id ? 'selected' : ''}`}
                    onClick={() => setSelectedId(agent.id)}
                  >
                    <h3>{agent.name || '未命名-agent'}</h3>
                    <p>{agent.role || '-'}</p>
                    <div className="agent-meta">
                      <span>L{agent.layer ?? '-'}</span>
                      <span>{agent.model || '-'}</span>
                      <span className={`status-pill status-${agent.status || 'unknown'}`}>
                        {agent.status || '未知'}
                      </span>
                    </div>
                  </article>
                ))}
                {!layerAgents.length ? <p className="muted">当前层暂无 Agent</p> : null}
              </div>
            </section>
          ))}
          {!items.length && !loading ? <p className="muted">暂无 Agent 数据</p> : null}
        </div>
      </section>

      <section className="card card-agent-detail">
        <header className="card-head">
          <h2>Agent 详情</h2>
          <p>健康信息 + 删除/状态操作 + 当前 agent_config 原文</p>
        </header>
        {!selected ? <p className="muted">请选择一个 Agent</p> : null}
        {selected ? (
          <div className="detail-grid">
            <div className="detail-line">
              <span>ID</span>
              <strong>{selected.id}</strong>
            </div>
            <div className="detail-line">
              <span>能力说明</span>
              <strong>{selected.capabilities || '-'}</strong>
            </div>
            <div className="detail-line">
              <span>状态</span>
              <strong>{selected.status || '-'}</strong>
            </div>
            {health ? (
              <>
                <div className="detail-line">
                  <span>运行态</span>
                  <strong>{health.runtime_status || '-'}</strong>
                </div>
                <div className="detail-line">
                  <span>心跳延迟</span>
                  <strong>{Math.round(health.heartbeat_age_seconds || 0)}s</strong>
                </div>
                <div className="detail-line">
                  <span>错误次数</span>
                  <strong>{health.error_count ?? 0}</strong>
                </div>
              </>
            ) : null}
            {healthError ? <p className="error">{healthError}</p> : null}

            <div className="actions">
              <button className="btn btn-ghost" onClick={() => setStatus('idle')}>
                设为空闲（idle）
              </button>
              <button className="btn btn-ghost" onClick={() => setStatus('busy')}>
                设为忙碌（busy）
              </button>
              <button className="btn btn-ghost" onClick={() => setStatus('offline')}>
                设为离线（offline）
              </button>
              <button className="btn" onClick={deleteSelected}>
                删除 Agent
              </button>
            </div>
            {statusMessage ? <p className="hint">{statusMessage}</p> : null}
            {deleteMessage ? <p className="hint">{deleteMessage}</p> : null}
            <pre className="json-box">
              {JSON.stringify(selected.agent_config || {}, null, 2)}
            </pre>
          </div>
        ) : null}
      </section>

      <section className="card card-agent-editor">
        <header className="card-head">
          <h2>创建 Agent</h2>
          <p>支持技能白名单和层级化角色模板</p>
        </header>

        <div className="detail-grid">
          <div className="detail-line">
            <span>配置说明</span>
            <strong>Skill 白名单控制 agent 可调用技能，统一通过技能约束执行。</strong>
          </div>
          <div className="detail-line">
            <span>回退模型</span>
            <strong>逗号分隔，主模型失败时按顺序降级，示例：`gpt-5.2,deepseek-v3.2`。</strong>
          </div>
        </div>

        <div className="form-grid">
          <label>
            <span>名称</span>
            <input
              value={form.name}
              onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="agent-name"
            />
          </label>
          <label>
            <span>角色</span>
            <select
              value={form.role}
              onChange={(e) => {
                const role = e.target.value
                applyPreset(role)
              }}
            >
              {[...new Set(['writer', 'reviewer', 'researcher', ...rolePresets.map((r) => r.role)])].map((role) => (
                <option value={role} key={role}>
                  {rolePresetMap[role]?.label ? `${rolePresetMap[role].label} (${role})` : role}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>层级</span>
            <select
              value={form.layer}
              onChange={(e) => setForm((p) => ({ ...p, layer: Number(e.target.value || 0) }))}
            >
              <option value={0}>L0 - 编排层</option>
              <option value={1}>L1 - 管理层</option>
              <option value={2}>L2 - 执行层</option>
            </select>
          </label>
          <label>
            <span>模型</span>
            <select
              value={form.model}
              onChange={(e) => setForm((p) => ({ ...p, model: e.target.value }))}
            >
              {modelOptions.length
                ? modelOptions.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))
                : ['deepseek-v3.2'].map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
            </select>
          </label>

          <label>
            <span>能力说明</span>
            <input
              value={form.capabilities}
              onChange={(e) => setForm((p) => ({ ...p, capabilities: e.target.value }))}
              placeholder="例如：长文写作 / 审校 / 检索"
            />
          </label>
          <label>
            <span>自定义模型</span>
            <input
              value={form.custom_model}
              onChange={(e) => setForm((p) => ({ ...p, custom_model: e.target.value }))}
              placeholder="可选，不填则使用上面的模型"
            />
          </label>

          <label className="field-full">
            <span>目标（goal）</span>
            <input
              value={form.goal}
              onChange={(e) => setForm((p) => ({ ...p, goal: e.target.value }))}
            />
          </label>
          <label className="field-full">
            <span>背景设定（backstory）</span>
            <input
              value={form.backstory}
              onChange={(e) => setForm((p) => ({ ...p, backstory: e.target.value }))}
            />
          </label>
          <label className="field-full">
            <span>职责描述（description）</span>
            <input
              value={form.description}
              onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
            />
          </label>
          <label className="field-full">
            <span>系统提示词（system_message）</span>
            <input
              value={form.system_message}
              onChange={(e) => setForm((p) => ({ ...p, system_message: e.target.value }))}
            />
          </label>

          <label>
            <span>采样温度（temperature）</span>
            <input
              type="number"
              step="0.1"
              min="0"
              max="2"
              value={form.temperature}
              onChange={(e) =>
                setForm((p) => ({ ...p, temperature: Number(e.target.value || 0) }))
              }
            />
          </label>
          <label>
            <span>最大输出 Token</span>
            <input
              type="number"
              value={form.max_tokens}
              onChange={(e) =>
                setForm((p) => ({ ...p, max_tokens: Number(e.target.value || 0) }))
              }
            />
          </label>
          <label>
            <span>最大重试次数</span>
            <input
              type="number"
              value={form.max_retries}
              onChange={(e) =>
                setForm((p) => ({ ...p, max_retries: Number(e.target.value || 0) }))
              }
            />
          </label>

          <label className="field-full">
            <span>回退模型（逗号分隔）</span>
            <input
              value={form.fallback_models_text}
              onChange={(e) =>
                setForm((p) => ({ ...p, fallback_models_text: e.target.value }))
              }
              placeholder="gpt-5.2,deepseek-v3.2"
            />
          </label>
          <label className="field-full">
            <span>标签（逗号分隔）</span>
            <input
              value={form.tags_text}
              onChange={(e) => setForm((p) => ({ ...p, tags_text: e.target.value }))}
              placeholder="team:a,region:cn"
            />
          </label>
        </div>

        <div className="allowlist-grid">
          <div>
            <h3>技能白名单（Skills）</h3>
            <div className="chips">
              {skills.map((s) => (
                <label key={s.name} className="chip">
                  <input
                    type="checkbox"
                    checked={form.skill_allowlist.includes(s.name)}
                    onChange={() => toggleListValue('skill_allowlist', s.name)}
                  />
                  <span>{s.name}</span>
                </label>
              ))}
              {!skills.length ? <span className="muted">暂无技能选项</span> : null}
            </div>
          </div>
        </div>

        <div className="actions">
          <button
            className="btn btn-primary"
            disabled={saving || form.name.trim().length < 2}
            onClick={createAgent}
          >
            {saving ? '创建中...' : '创建 Agent'}
          </button>
          {createMessage ? <span className="hint">{createMessage}</span> : null}
        </div>
      </section>
    </div>
  )
}
