export interface VersionedClassroomSnapshot {
  stateVersion: number
}

export interface ClassroomSnapshotReconciler {
  request: (minimumVersion?: number) => Promise<void>
  dispose: () => void
}

export function createClassroomSnapshotReconciler<T extends VersionedClassroomSnapshot>(
  load: () => Promise<T>,
  apply: (snapshot: T) => void,
): ClassroomSnapshotReconciler {
  let inFlight: Promise<void> | null = null
  let requiredVersion = 0
  let pending = false
  let disposed = false

  const request = (minimumVersion = 0): Promise<void> => {
    if (disposed) return Promise.resolve()
    requiredVersion = Math.max(requiredVersion, minimumVersion)
    pending = true
    if (inFlight) return inFlight

    const run = async () => {
      let staleResponses = 0
      while (!disposed && pending) {
        pending = false
        const targetVersion = requiredVersion
        const snapshot = await load()
        if (disposed) return
        const latestRequiredVersion = Math.max(targetVersion, requiredVersion)
        if (snapshot.stateVersion < latestRequiredVersion) {
          staleResponses += 1
          if (staleResponses >= 3) {
            throw new Error('Classroom snapshot did not reach the required version')
          }
          pending = true
          continue
        }
        staleResponses = 0
        apply(snapshot)
        if (requiredVersion <= snapshot.stateVersion) requiredVersion = 0
      }
    }
    inFlight = run().finally(() => { inFlight = null })
    return inFlight
  }

  return {
    request,
    dispose() {
      disposed = true
      pending = false
    },
  }
}
