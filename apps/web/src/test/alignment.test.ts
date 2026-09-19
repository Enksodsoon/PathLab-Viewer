import { describe, expect, it } from 'vitest'

import { alignmentViewDelta, hasLocalEvidence, intersectSupport, mapComparisonBounds, mapComparisonPoint, mapLocalComparisonPoint, mapSupportBounds, normalizeRotation, withinSupport } from '../alignment'

describe('comparison coordinate mapping', () => {
  it('maps bidirectionally through reference coordinates', () => {
    const movingToReference = [[1, 0, 20], [0, 1, -10]]
    expect(mapComparisonPoint([100, 80], movingToReference, null)).toEqual([120, 70])
    expect(mapComparisonPoint([120, 70], null, movingToReference)).toEqual([100, 80])
  })

  it('derives bidirectional viewer rotation and scale from affine registration', () => {
    const movingToReference = [[0.8459608705, 0.4885494475, -2975], [-0.4885885636, 0.845341361, 1935]]
    const moving = alignmentViewDelta(null, movingToReference)
    const reference = alignmentViewDelta(movingToReference, null)

    expect(moving.rotation).toBeCloseTo(-30, 1)
    expect(moving.zoomScale).toBeCloseTo(0.977, 2)
    expect(reference.rotation).toBeCloseTo(30, 1)
    expect(reference.zoomScale).toBeCloseTo(1 / 0.977, 2)
    expect(normalizeRotation(-30)).toBe(330)
  })

  it('finds the common reference-space area covered by a rotated slide', () => {
    const transform = [[0, -1, 100], [1, 0, 20]]
    expect(mapSupportBounds([10, 20, 40, 60], transform)).toEqual([40, 30, 80, 60])
    expect(intersectSupport([0, 0, 70, 70], [40, 30, 80, 60])).toEqual([40, 30, 70, 60])
    expect(intersectSupport([0, 0, 10, 10], [20, 20, 30, 30])).toBeNull()
    expect(mapComparisonBounds([40, 30, 80, 60], null, transform)).toEqual([10, 20, 40, 60])
  })

  it('rejects points outside a registration support region', () => {
    expect(withinSupport([25, 25], [0, 0, 50, 50])).toBe(true)
    expect(withinSupport([55, 25], [0, 0, 50, 50])).toBe(false)
    expect(withinSupport([55, 25], null)).toBe(true)
  })

  it('uses the same accepted triangle for exact forward and reverse navigation', () => {
    const registration = {
      movingToReference: [[1, 0, 10], [0, 1, 0]],
      controlPoints: [
        { moving: [0, 0] as [number, number], reference: [12, 1] as [number, number], errorPixels: 1 },
        { moving: [100, 0] as [number, number], reference: [108, -1] as [number, number], errorPixels: 1 },
        { moving: [0, 100] as [number, number], reference: [14, 99] as [number, number], errorPixels: 1 },
        { moving: [100, 100] as [number, number], reference: [106, 101] as [number, number], errorPixels: 1 },
      ],
      triangles: [{
        moving: [[0, 0], [100, 0], [0, 100]] as [[number, number], [number, number], [number, number]],
        reference: [[12, 1], [108, -1], [14, 99]] as [[number, number], [number, number], [number, number]],
      }],
    }
    const mapped = mapLocalComparisonPoint([25, 20], registration, null)
    expect(mapped).not.toBeNull()
    expect(mapLocalComparisonPoint(mapped!, null, registration)?.[0]).toBeCloseTo(25, 10)
    expect(mapLocalComparisonPoint(mapped!, null, registration)?.[1]).toBeCloseTo(20, 10)
    expect(mapLocalComparisonPoint([100, 100], registration, null)).toBeNull()
    expect(hasLocalEvidence(registration)).toBe(true)
    expect(hasLocalEvidence({ movingToReference: registration.movingToReference })).toBe(false)
  })
})
