import { describe, expect, it } from 'vitest'

import { toApiDateTime, toLocalDateTimeInput } from '../assessment/dateTime'

describe('assessment date and time parameters', () => {
  it('round-trips an API instant through a datetime-local field without timezone drift', () => {
    const instant = '2026-12-18T03:00:00.000Z'
    expect(toApiDateTime(toLocalDateTimeInput(instant))).toBe(instant)
  })

  it('keeps optional dates empty', () => {
    expect(toLocalDateTimeInput(null)).toBe('')
    expect(toApiDateTime('')).toBeNull()
  })
})
