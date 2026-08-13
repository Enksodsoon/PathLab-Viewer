const BASE_RETRY_MS = 500
const MAX_BACKOFF_MS = 4000
const MAX_JITTER_MS = 1000

function participantHash(participantId: string): number {
  let value = 2166136261
  for (const character of participantId) {
    value ^= character.charCodeAt(0)
    value = Math.imul(value, 16777619)
  }
  return value >>> 0
}

export function classroomReconnectDelay(participantId: string, attempt: number): number {
  const boundedAttempt = Math.max(0, Math.min(3, Math.floor(attempt)))
  const backoff = Math.min(MAX_BACKOFF_MS, BASE_RETRY_MS * (2 ** boundedAttempt))
  const jitter = participantHash(participantId) % (MAX_JITTER_MS + 1)
  return Math.min(MAX_BACKOFF_MS + MAX_JITTER_MS, backoff + jitter)
}
