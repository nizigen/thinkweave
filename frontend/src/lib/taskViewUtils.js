export function formatTime(iso) {
  if (!iso) return '-'
  const dt = new Date(iso)
  if (Number.isNaN(dt.getTime())) return '-'
  return dt.toLocaleString()
}

export function formatDuration(startIso, endIso) {
  if (!startIso) return '-'
  const start = new Date(startIso).getTime()
  const end = endIso ? new Date(endIso).getTime() : Date.now()
  if (Number.isNaN(start) || Number.isNaN(end)) return '-'
  const sec = Math.max(0, Math.floor((end - start) / 1000))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return `${h}h ${m}m ${s}s`
}

export function parseEvidenceRows(markdown) {
  if (!markdown) return []
  return String(markdown)
    .split('\n')
    .filter((line) => line.startsWith('| E'))
    .map((line) => line.split('|').slice(1, -1).map((part) => part.trim()))
    .map((cols) => ({
      evidenceId: cols[0] || '-',
      source: cols[1] || '-',
      category: cols[2] || '-',
      priority: cols[3] || '-',
      title: cols[6] || '-',
      url: cols[7] || '',
    }))
}

export function summaryTextMap(obj) {
  const entries = Object.entries(obj || {})
  if (!entries.length) return '-'
  return entries.map(([k, v]) => `${k}:${v}`).join(' | ')
}

