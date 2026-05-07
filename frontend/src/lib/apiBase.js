function normalizeBase(rawBase) {
  if (!rawBase) return ''
  const trimmed = String(rawBase).trim()
  if (!trimmed) return ''
  return trimmed.replace(/\/+$/, '')
}

function resolveDefaultApiBase() {
  const explicit = normalizeBase(import.meta.env.VITE_API_BASE)
  if (explicit) return explicit
  if (typeof window === 'undefined') return ''

  const { protocol, hostname, port } = window.location
  const isLocalHost = hostname === 'localhost' || hostname === '127.0.0.1'
  if (!isLocalHost) return ''

  // Vite dev/preview ports: auto-wire frontend -> backend for local runs.
  if (port === '5173' || port === '4173') {
    return `${protocol}//${hostname}:18080`
  }
  return ''
}

function resolveDefaultToken() {
  const fromEnv = String(import.meta.env.VITE_TASK_AUTH_TOKEN || '').trim()
  if (fromEnv) return fromEnv
  if (typeof window === 'undefined') return ''

  const isLocalHost =
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1'
  if (isLocalHost) {
    return 'local-dev-admin-token'
  }
  return ''
}

export const API_BASE = resolveDefaultApiBase()

export function apiUrl(path) {
  if (!path.startsWith('/')) return `${API_BASE}/${path}`
  return `${API_BASE}${path}`
}

export function authHeaders(extra = {}) {
  const headers = { ...extra }
  const token =
    sessionStorage.getItem('task_auth_token')?.trim() ||
    resolveDefaultToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  return headers
}

export async function requestJson(path, options = {}) {
  const response = await fetch(apiUrl(path), options)
  if (!response.ok) {
    let detail = ''
    try {
      const body = await response.json()
      detail = body?.detail ? ` - ${body.detail}` : ''
    } catch {
      detail = ''
    }
    throw new Error(`HTTP ${response.status}${detail}`)
  }
  return response.json()
}
