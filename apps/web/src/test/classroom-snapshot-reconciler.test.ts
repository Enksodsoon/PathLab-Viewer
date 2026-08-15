import { describe, expect, it, vi } from 'vitest'

import { createClassroomSnapshotReconciler } from '../classroom/snapshotReconciler'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

describe('classroom snapshot reconciliation', () => {
  it('serializes recovery and skips a response older than the newest required version', async () => {
    const versionFive = deferred<{ stateVersion: number; value: string }>()
    const versionSix = deferred<{ stateVersion: number; value: string }>()
    const load = vi.fn()
      .mockReturnValueOnce(versionFive.promise)
      .mockReturnValueOnce(versionSix.promise)
    const apply = vi.fn()
    const reconciler = createClassroomSnapshotReconciler(load, apply)

    const first = reconciler.request(5)
    const second = reconciler.request(6)
    expect(load).toHaveBeenCalledTimes(1)

    versionFive.resolve({ stateVersion: 5, value: 'stale' })
    await Promise.resolve()
    await Promise.resolve()
    expect(load).toHaveBeenCalledTimes(2)
    expect(apply).not.toHaveBeenCalled()

    versionSix.resolve({ stateVersion: 6, value: 'current' })
    await Promise.all([first, second])
    expect(apply).toHaveBeenCalledTimes(1)
    expect(apply).toHaveBeenCalledWith({ stateVersion: 6, value: 'current' })
  })
})
