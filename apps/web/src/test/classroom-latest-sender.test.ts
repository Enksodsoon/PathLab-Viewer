import { afterEach, describe, expect, it, vi } from 'vitest'

import { createLatestSender } from '../classroom/latestSender'

describe('createLatestSender', () => {
  afterEach(() => vi.useRealTimers())

  it('sends the newest state at a bounded cadence without overlapping requests', async () => {
    vi.useFakeTimers()
    let release: (() => void) | undefined
    const sent: number[] = []
    const sender = createLatestSender(async (value: number) => {
      sent.push(value)
      await new Promise<void>((resolve) => { release = resolve })
    }, 120)

    sender.push(1)
    sender.push(2)
    await vi.advanceTimersByTimeAsync(0)
    expect(sent).toEqual([2])
    sender.push(3)
    sender.push(4)
    await vi.advanceTimersByTimeAsync(500)
    expect(sent).toEqual([2])
    release?.()
    await vi.advanceTimersByTimeAsync(120)
    expect(sent).toEqual([2, 4])
    sender.dispose()
  })
})
