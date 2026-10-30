// 通用格式化工具
export function fmtNum(n) {
  if (n === null || n === undefined || n === '') return '—'
  return Number(n).toLocaleString('zh-CN')
}

export function fmtDate(s) {
  if (!s) return '—'
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return String(s)
  return d.toLocaleString('zh-CN', { hour12: false })
}
