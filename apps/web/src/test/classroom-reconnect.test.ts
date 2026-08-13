import { describe, expect, it } from 'vitest'

import { classroomReconnectDelay } from '../classroom/reconnect'

describe('classroom reconnect delay', () => {
  it('is deterministic per participant and differs across participants', () => {
    expect(classroomReconnectDelay('participant-a', 0)).toBe(
      classroomReconnectDelay('participant-a', 0),
    )
    expect(classroomReconnectDelay('participant-a', 0)).not.toBe(
      classroomReconnectDelay('participant-b', 0),
    )
  })

  it('backs off within a bounded five-second window', () => {
    const delays = Array.from({ length: 10 }, (_, attempt) => (
      classroomReconnectDelay('participant-a', attempt)
    ))
    expect(Math.min(...delays)).toBeGreaterThanOrEqual(500)
    expect(Math.max(...delays)).toBeLessThanOrEqual(5000)
    expect(delays[3]).toBe(delays[9])
  })
})
