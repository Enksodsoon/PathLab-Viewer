export function classroomSlideSource(tileSource: string, sessionId: string): string {
  const separator = tileSource.includes('?') ? '&' : '?'
  return `${tileSource}${separator}classroom=${encodeURIComponent(sessionId)}`
}
