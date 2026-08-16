const INITIAL_RETRY_MIN_MS = 500
const INITIAL_RETRY_SPREAD_MS = 9500
const MAX_BACKOFF_MS = 30_000
const MAX_GUIDE_JITTER_MS = 250

function participantHash(participantId: string): number {
  let value = 2166136261
  for (const character of participantId) {
    value ^= character.charCodeAt(0)
    value = Math.imul(value, 16777619)
  }
  return value >>> 0
}

export function classroomReconnectDelay(participantId: string, attempt: number): number {
  const boundedAttempt = Math.max(0, Math.min(8, Math.floor(attempt)))
  const initialDelay = INITIAL_RETRY_MIN_MS
    + participantHash(participantId) % (INITIAL_RETRY_SPREAD_MS + 1)
  return Math.min(MAX_BACKOFF_MS, initialDelay * (2 ** boundedAttempt))
}

export function classroomGuideDelay(participantId: string, slideId: string): number {
  return participantHash(`${participantId}\u0000${slideId}`) % (MAX_GUIDE_JITTER_MS + 1)
}
