const ROSTER_RECONCILE_INTERVAL_MS = 1000

export interface RosterReconciler {
  notify: (rosterVersion: number) => void
  dispose: () => void
}

export function createRosterReconciler(
  reconcile: (rosterVersion: number) => Promise<void>,
): RosterReconciler {
  let timer: number | null = null
  let pendingVersion: number | null = null
  let lastStartedAt = Number.NEGATIVE_INFINITY
  let disposed = false

  const schedule = () => {
    if (disposed || timer !== null || pendingVersion === null) return
    const delay = Math.max(0, ROSTER_RECONCILE_INTERVAL_MS - (Date.now() - lastStartedAt))
    timer = window.setTimeout(() => {
      timer = null
      if (disposed || pendingVersion === null) return
      const version = pendingVersion
      pendingVersion = null
      lastStartedAt = Date.now()
      void reconcile(version).finally(schedule)
    }, delay)
  }

  return {
    notify(rosterVersion) {
      if (disposed || !Number.isSafeInteger(rosterVersion) || rosterVersion < 0) return
      pendingVersion = Math.max(pendingVersion ?? rosterVersion, rosterVersion)
      schedule()
    },
    dispose() {
      disposed = true
      pendingVersion = null
      if (timer !== null) window.clearTimeout(timer)
      timer = null
    },
  }
}
