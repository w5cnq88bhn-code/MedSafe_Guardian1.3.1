/** 格式化日期为 YYYY-MM-DD */
export function formatDate(d: Date | string): string {
  const date = typeof d === 'string' ? new Date(d) : d
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** 格式化时间为 HH:MM */
export function formatTime(d: Date | string): string {
  const date = typeof d === 'string' ? new Date(d) : d
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

/** 获取今天日期字符串 */
export function today(): string {
  return formatDate(new Date())
}

/** 获取过去N天的日期数组 */
export function pastDays(n: number): string[] {
  return Array.from({ length: n }, (_, i) => {
    const d = new Date()
    d.setDate(d.getDate() - i)
    return formatDate(d)
  }).reverse()
}
