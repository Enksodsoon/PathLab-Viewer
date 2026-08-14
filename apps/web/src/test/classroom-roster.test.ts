import { afterEach, describe, expect, it, vi } from 'vitest'

import { teacherParticipants } from '../classroom/api'
import { createRosterReconciler } from '../classroom/roster'

describe('teacher classroom roster', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('requests searchable keyset pages of at most 100 participants', async () => {
    const response = {
      items: [], total: 0, nextCursor: null, rosterVersion: 8,
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(response), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await expect(teacherParticipants('session/one', {
      after: 'AMBER-00000001', limit: 100, q: ' renal ',
    })).resolves.toEqual(response)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/classroom/sessions/session%2Fone/participants?after=AMBER-00000001&limit=100&q=renal',
      { credentials: 'same-origin', cache: 'no-store' },
    )
  })

  it('coalesces roster-changed bursts to at most one reconciliation per second', async () => {
    vi.useFakeTimers()
    const reconcile = vi.fn(async () => undefined)
    const scheduler = createRosterReconciler(reconcile)

    scheduler.notify(2)
    scheduler.notify(3)
    scheduler.notify(4)
    await vi.advanceTimersByTimeAsync(0)
    expect(reconcile).toHaveBeenCalledTimes(1)
    expect(reconcile).toHaveBeenLastCalledWith(4)

    scheduler.notify(5)
    await vi.advanceTimersByTimeAsync(999)
    expect(reconcile).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(reconcile).toHaveBeenCalledTimes(2)
    expect(reconcile).toHaveBeenLastCalledWith(5)

    scheduler.dispose()
  })
})
