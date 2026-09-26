export interface ClassroomStreamCursor {
  hubEpoch: string
  eventSequence: number
  stateVersion: number
  needsSnapshot?: boolean
}

export type ClassroomStreamDecision = 'apply' | 'ignore' | 'resync'

export function createClassroomStreamCursor(stateVersion: number): ClassroomStreamCursor {
  return { hubEpoch: '', eventSequence: 0, stateVersion }
}

export function noteClassroomSnapshot(
  cursor: ClassroomStreamCursor,
  stateVersion: number,
): void {
  cursor.stateVersion = stateVersion
  delete cursor.needsSnapshot
}

export function applyClassroomStreamEvent(
  cursor: ClassroomStreamCursor,
  eventType: string,
  payload: Record<string, unknown>,
  options: { coalescible?: boolean; terminal?: boolean } = {},
): ClassroomStreamDecision {
  const hubEpoch = typeof payload.hubEpoch === 'string' ? payload.hubEpoch : ''
  const eventSequence = typeof payload.eventSequence === 'number'
    && Number.isSafeInteger(payload.eventSequence)
    && payload.eventSequence >= 0
    ? payload.eventSequence
    : -1
  const resync = (): ClassroomStreamDecision => {
    cursor.needsSnapshot = true
    return 'resync'
  }
  if (!hubEpoch || eventSequence < 0) return resync()

  if (eventType === 'stream-ready') {
    const stateVersion = typeof payload.stateVersion === 'number'
      && Number.isSafeInteger(payload.stateVersion)
      && payload.stateVersion >= 0
      ? payload.stateVersion
      : -1
    cursor.hubEpoch = hubEpoch
    cursor.eventSequence = eventSequence
    return stateVersion === cursor.stateVersion && !cursor.needsSnapshot ? 'apply' : resync()
  }

  if (hubEpoch === cursor.hubEpoch && eventSequence <= cursor.eventSequence) return 'ignore'

  const hasGap = hubEpoch !== cursor.hubEpoch
    || (!options.coalescible && eventSequence !== cursor.eventSequence + 1)
  cursor.hubEpoch = hubEpoch
  cursor.eventSequence = eventSequence

  if (typeof payload.stateVersion === 'number' && Number.isSafeInteger(payload.stateVersion)) {
    if (options.terminal && payload.stateVersion >= cursor.stateVersion) {
      cursor.stateVersion = payload.stateVersion
      delete cursor.needsSnapshot
      return 'apply'
    }
    if (hasGap || cursor.needsSnapshot) return resync()
    if (payload.stateVersion !== cursor.stateVersion) return resync()
  }
  if (hasGap || cursor.needsSnapshot) return resync()
  return 'apply'
}

export function createClassroomEphemeralBuffer() {
  // ponytail: two latest fields; add an explicit field if the protocol gains another.
  const latest = new Map<string, () => void>()
  return {
    hold(type: string, replay: () => void): boolean {
      const field = type === 'presenter' ? 'presenter'
        : type === 'pointer' || type === 'pointer-removed' ? 'pointer' : null
      if (!field) return false
      latest.delete(field)
      latest.set(field, replay)
      return true
    },
    drain(): void {
      const callbacks = [...latest.values()]
      latest.clear()
      for (const replay of callbacks) replay()
    },
    clear(): void { latest.clear() },
  }
}
