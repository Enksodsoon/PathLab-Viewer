import { describe, expect, it } from 'vitest'

import { classroomGuideDelay, classroomReconnectDelay } from '../classroom/reconnect'

describe('classroom reconnect delay', () => {
  it('is deterministic per participant and differs across participants', () => {
    expect(classroomReconnectDelay('participant-a', 0)).toBe(
      classroomReconnectDelay('participant-a', 0),
    )
    expect(classroomReconnectDelay('participant-a', 0)).not.toBe(
      classroomReconnectDelay('participant-b', 0),
    )
  })

  it('spreads the initial retry across 0.5–10 seconds, then caps exponential backoff', () => {
    const initialDelays = Array.from({ length: 256 }, (_, index) => (
      classroomReconnectDelay(`participant-${index}`, 0)
    ))
    expect(Math.min(...initialDelays)).toBeGreaterThanOrEqual(500)
    expect(Math.max(...initialDelays)).toBeLessThanOrEqual(10_000)
    expect(new Set(initialDelays).size).toBeGreaterThan(200)

    const delays = Array.from({ length: 12 }, (_, attempt) => (
      classroomReconnectDelay('participant-a', attempt)
    ))
    expect(delays.slice(1).every((delay, index) => delay >= delays[index])).toBe(true)
    expect(delays.at(-1)).toBeLessThanOrEqual(30_000)
    expect(delays.at(-1)).toBe(delays.at(-2))
  })

  it('deterministically spreads guided slide switches across 0–250 ms', () => {
    const delays = Array.from({ length: 256 }, (_, index) => (
      classroomGuideDelay(`participant-${index}`, 'slide-7')
    ))
    expect(classroomGuideDelay('participant-a', 'slide-7')).toBe(
      classroomGuideDelay('participant-a', 'slide-7'),
    )
    expect(Math.min(...delays)).toBeGreaterThanOrEqual(0)
    expect(Math.max(...delays)).toBeLessThanOrEqual(250)
    expect(new Set(delays).size).toBeGreaterThan(150)
  })
})
