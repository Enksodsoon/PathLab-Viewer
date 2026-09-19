import { describe, expect, it } from 'vitest'

import { mapComparisonPoint, withinSupport } from '../alignment'

describe('comparison coordinate mapping', () => {
  it('maps bidirectionally through reference coordinates', () => {
    const movingToReference = [[1, 0, 20], [0, 1, -10]]
    expect(mapComparisonPoint([100, 80], movingToReference, null)).toEqual([120, 70])
    expect(mapComparisonPoint([120, 70], null, movingToReference)).toEqual([100, 80])
  })

  it('rejects points outside a registration support region', () => {
    expect(withinSupport([25, 25], [0, 0, 50, 50])).toBe(true)
    expect(withinSupport([55, 25], [0, 0, 50, 50])).toBe(false)
    expect(withinSupport([55, 25], null)).toBe(true)
  })
})
