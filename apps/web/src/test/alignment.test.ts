import { describe, expect, it } from 'vitest'
import { mapStackPoint } from '../alignment'

import { alignmentViewDelta, continuousAlignmentViewDelta, hasLocalEvidence, intersectSupport, mapComparisonBounds, mapComparisonPoint, mapContinuousComparisonPoint, mapLocalComparisonPoint, mapOverviewComparisonPoint, overviewAlignmentViewDelta, mapSupportBounds, normalizeRotation, withinSupport } from '../alignment'

describe('comparison coordinate mapping', () => {
  it('uses retained Native only after candidate local and own overview, never in strict mode', () => {
    const cell = (size: number, offset: number) => ({ moving: [[0, 0], [size, 0], [0, size]] as [[number, number], [number, number], [number, number]], reference: [[offset, 0], [size + offset, 0], [offset, size]] as [[number, number], [number, number], [number, number]] })
    const registration = { status: 'ready', anchorSlideId: 'fixed', movingToReference: [[1, 0, 10], [0, 1, 0]], triangles: [cell(10, 10)], overviewTriangles: [cell(100, 30)], overviewFallback: { movingToReference: [[1, 0, 40], [0, 1, 0]], overviewTriangles: [cell(200, 40)] }, retainedOverviewFallback: { movingToReference: [[1, 0, 20], [0, 1, 0]], overviewTriangles: [cell(500, 20)] } }
    const members = [{ slideId: 'fixed' }, { slideId: 'moving', registration }]
    expect(mapStackPoint([2, 2], 'moving', 'fixed', 'fixed', members)).toMatchObject({ point: [12, 2], approximate: false })
    expect(mapStackPoint([40, 20], 'moving', 'fixed', 'fixed', members)?.point[0]).toBeCloseTo(70)
    expect(mapStackPoint([120, 30], 'moving', 'fixed', 'fixed', members)?.point[0]).toBeCloseTo(160)
    expect(mapStackPoint([350, 100], 'moving', 'fixed', 'fixed', members)).toMatchObject({ approximate: true, retainedOverview: true })
    expect(mapStackPoint([350, 100], 'moving', 'fixed', 'fixed', members)?.point[0]).toBeCloseTo(370)
    expect(mapStackPoint([370, 100], 'fixed', 'moving', 'fixed', members)?.point[0]).toBeCloseTo(350)
    expect(mapStackPoint([350, 100], 'moving', 'fixed', 'fixed', members, 'strict')).toBeNull()
    expect(mapStackPoint([600, 600], 'moving', 'fixed', 'fixed', members)).toBeNull()
    const regional = [{ sourceSlideId: 'moving', targetSlideId: 'fixed', sourceBounds: [0, 0, 500, 500] as [number, number, number, number], registration: { status: 'approximate', movingToReference: [[1, 0, 80], [0, 1, 0]], triangles: [cell(500, 80)] } }]
    expect(mapStackPoint([350, 100], 'moving', 'fixed', 'fixed', members, 'best', 0, regional)).toMatchObject({ regional: true })
    expect(mapStackPoint([350, 100], 'moving', 'fixed', 'fixed', members, 'best', 0, regional)?.point[0]).toBeCloseTo(430)
  })
  it('prefers bounded regional corrections for displayed siblings without changing their overview maps', () => {
    const cell = { moving: [[100, 100], [300, 100], [100, 300]] as [[number, number], [number, number], [number, number]], reference: [[140, 120], [340, 120], [140, 320]] as [[number, number], [number, number], [number, number]] }
    const members = ['a', 'b'].map(slideId => ({ slideId, registration: { status: 'approximate', anchorSlideId: 'root', movingToReference: [[1, 0, 0], [0, 1, 0]], overviewTriangles: [{ moving: [[0, 0], [1000, 0], [0, 1000]] as typeof cell.moving, reference: [[0, 0], [1000, 0], [0, 1000]] as typeof cell.reference }] } }))
    members.push({ slideId: 'root', registration: null as never })
    const overlays = [{ sourceSlideId: 'a', targetSlideId: 'b', sourceBounds: [100, 100, 200, 200] as [number, number, number, number], registration: { status: 'approximate', movingToReference: [[1, 0, 40], [0, 1, 20]], overviewTriangles: [cell] } }]
    expect(mapStackPoint([150, 150], 'a', 'b', 'root', members, 'best', 0, overlays)?.point).toEqual([190, 170])
    expect(mapStackPoint([190, 170], 'b', 'a', 'root', members, 'best', 0, overlays)?.point).toEqual([150, 150])
    members.push({ ...members[1], slideId: 'c' })
    const composed = mapStackPoint([150, 150], 'a', 'c', 'root', members, 'best', 0, overlays)?.point
    expect(composed?.[0]).toBeCloseTo(190)
    expect(composed?.[1]).toBeCloseTo(170)
    const outside = mapStackPoint([500, 100], 'a', 'b', 'root', members, 'best', 0, overlays)?.point
    expect(outside?.[0]).toBeCloseTo(500)
    expect(outside?.[1]).toBeCloseTo(100)
    expect(mapStackPoint([Number.NaN, 0], 'a', 'b', 'root', members)).toBeNull()
  })
  it('keeps short glass gaps linked as approximate without expanding local support', () => {
    const cell = {
      moving: [[0, 0], [100, 0], [0, 100]] as [[number, number], [number, number], [number, number]],
      reference: [[20, 0], [120, 0], [20, 100]] as [[number, number], [number, number], [number, number]],
    }
    for (const status of ['ready', 'approximate']) {
      const registration = { status, anchorSlideId: 'fixed', movingToReference: [[1, 0, 20], [0, 1, 0]], triangles: status === 'ready' ? [cell] : [], overviewTriangles: [cell] }
      const members = [{ slideId: 'fixed' }, { slideId: 'moving', registration }]
      const mapped = mapStackPoint([110, 25], 'moving', 'fixed', 'fixed', members)
      expect(mapped?.point[0]).toBeCloseTo(130)
      expect(mapped?.point[1]).toBeCloseTo(25)
      expect(mapped?.approximate).toBe(true)
      expect(mapStackPoint(mapped!.point, 'fixed', 'moving', 'fixed', members)?.point[0]).toBeCloseTo(110)
      expect(mapStackPoint([110, 25], 'moving', 'fixed', 'fixed', members, 'strict')).toBeNull()
      expect(mapStackPoint([500, 500], 'moving', 'fixed', 'fixed', members)).toBeNull()
      const overview = mapStackPoint([500, 500], 'moving', 'fixed', 'fixed', members, 'best', 700)
      expect(overview?.point[0]).toBeCloseTo(520)
      expect(overview?.approximate).toBe(true)
      expect(mapStackPoint([500, 500], 'moving', 'fixed', 'fixed', members, 'strict', 700)).toBeNull()
      expect(mapStackPoint([500, 500], 'moving', 'fixed', 'fixed', members, 'best', 100)).toBeNull()
    }
  })

  it('does not use tissue-outline evidence to extrapolate anatomy outside supported cells', () => {
    const registration = {
      status: 'approximate', anchorSlideId: 'fixed',
      movingToReference: [[1, 0, 20], [0, 1, -10]],
      evidence: { source: 'bounded-sparse-overview' },
      overviewTriangles: [{
        moving: [[0, 0], [10, 0], [0, 10]] as [[number, number], [number, number], [number, number]],
        reference: [[20, -10], [30, -10], [20, 0]] as [[number, number], [number, number], [number, number]],
      }],
    }
    const members = [{ slideId: 'fixed' }, { slideId: 'moving', registration }]
    expect(mapStackPoint([200, 300], 'moving', 'fixed', 'fixed', members)).toBeNull()
    expect(mapStackPoint([220, 290], 'fixed', 'moving', 'fixed', members)).toBeNull()
    registration.evidence.source = 'bounded-pyramid-whole-slide-structure'
    expect(mapStackPoint([200, 300], 'moving', 'fixed', 'fixed', members)).toBeNull()
  })
  it('uses a retained coarse mesh only outside the preferred supported cells', () => {
    const cell = (size: number, offset: number) => ({
      moving: [[0, 0], [size, 0], [0, size]] as [[number, number], [number, number], [number, number]],
      reference: [[offset, 0], [size + offset, 0], [offset, size]] as [[number, number], [number, number], [number, number]],
    })
    const registration = {
      status: 'approximate', anchorSlideId: 'fixed',
      movingToReference: [[1, 0, 10], [0, 1, 0]],
      overviewTriangles: [cell(10, 10)],
      overviewFallback: {
        movingToReference: [[1, 0, 20], [0, 1, 0]],
        overviewTriangles: [cell(100, 20)],
      },
    }
    const members = [{slideId: 'fixed'}, {slideId: 'moving', registration}]
    expect(mapStackPoint([2, 2], 'moving', 'fixed', 'fixed', members)?.point).toEqual([12, 2])
    const fallback = mapStackPoint([40, 20], 'moving', 'fixed', 'fixed', members)
    expect(fallback?.point[0]).toBeCloseTo(60, 10)
    expect(fallback?.point[1]).toBeCloseTo(20, 10)
    expect(fallback?.approximate).toBe(true)
    const restored = mapStackPoint([60, 20], 'fixed', 'moving', 'fixed', members)
    expect(restored?.point[0]).toBeCloseTo(40, 10)
    expect(restored?.point[1]).toBeCloseTo(20, 10)
    expect(mapStackPoint([40, 20], 'moving', 'fixed', 'fixed', members, 'strict')).toBeNull()
    expect(mapStackPoint([200, 200], 'moving', 'fixed', 'fixed', members)).toBeNull()
  })
  it('uses an approximate overview outside a manual correction hull', () => {
    const registration = {
      status: 'ready', anchorSlideId: 'fixed', movingToReference: [[1, 0, 5], [0, 1, 0]],
      triangles: [{ moving: [[0, 0], [10, 0], [0, 10]] as [[number, number], [number, number], [number, number]],
        reference: [[5, 0], [15, 0], [5, 10]] as [[number, number], [number, number], [number, number]] }],
      overviewFallback: { movingToReference: [[1, 0, 20], [0, 1, 0]],
        overviewTriangles: [{ moving: [[0, 0], [100, 0], [0, 100]] as [[number, number], [number, number], [number, number]],
          reference: [[20, 0], [120, 0], [20, 100]] as [[number, number], [number, number], [number, number]] }] },
    }
    const members = [{ slideId: 'fixed' }, { slideId: 'moving', registration }]
    expect(mapStackPoint([2, 2], 'moving', 'fixed', 'fixed', members)).toMatchObject({ point: [7, 2], approximate: false })
    const fallback = mapStackPoint([40, 20], 'moving', 'fixed', 'fixed', members)
    expect(fallback?.point[0]).toBeCloseTo(60)
    expect(fallback?.point[1]).toBeCloseTo(20)
    expect(fallback?.approximate).toBe(true)
    expect(mapStackPoint([40, 20], 'moving', 'fixed', 'fixed', members, 'strict')).toBeNull()
  })
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

  it('uses approximate component cells without treating them as anatomical evidence', () => {
    const registration = {
      movingToReference: [[1, 0, 50], [0, 1, 20]],
      overviewTriangles: [{
        moving: [[0, 0], [100, 0], [0, 100]] as [[number, number], [number, number], [number, number]],
        reference: [[12, 8], [110, 5], [15, 112]] as [[number, number], [number, number], [number, number]],
      }],
    }
    const mapped = mapOverviewComparisonPoint([20, 25], registration, null)
    expect(mapped).not.toBeNull()
    expect(mapOverviewComparisonPoint(mapped!, null, registration)?.[0]).toBeCloseTo(20, 10)
    expect(mapOverviewComparisonPoint(mapped!, null, registration)?.[1]).toBeCloseTo(25, 10)
    const delta = overviewAlignmentViewDelta([20, 25], registration, null)
    expect(delta).not.toBeNull()
    expect(hasLocalEvidence(registration)).toBe(false)
    // A small margin keeps panning continuous around sparse component cells.
    const nearby = mapOverviewComparisonPoint([110, 25], registration, null)
    expect(nearby).toEqual([120.55, 30.7])
    expect(mapOverviewComparisonPoint(nearby!, null, registration)?.[0]).toBeCloseTo(110, 10)
    expect(mapOverviewComparisonPoint(nearby!, null, registration)?.[1]).toBeCloseTo(25, 10)
    // The closest component transform continues across surrounding glass. A
    // registration with multiple components must not use an unrelated global affine.
    const distant = mapOverviewComparisonPoint([500, 500], registration, null)
    expect(distant).toEqual([517, 513])
    expect(mapOverviewComparisonPoint(distant!, null, registration)?.[0]).toBeCloseTo(500, 10)
    expect(mapOverviewComparisonPoint(distant!, null, registration)?.[1]).toBeCloseTo(500, 10)
  })

  it('does not extrapolate a validated component map into another fragment', () => {
    const registration = {
      movingToReference: [[0, -2, 1000], [2, 0, 200]],
      triangles: [{
        moving: [[0, 0], [100, 0], [0, 100]] as [[number, number], [number, number], [number, number]],
        reference: [[1000, 200], [1000, 400], [800, 200]] as [[number, number], [number, number], [number, number]],
      }],
    }
    // The point is outside the only local cell. Applying its affine here could
    // jump into a different repeated core, so the map must be unavailable.
    const mapped = mapContinuousComparisonPoint([400, 300], registration, null)
    expect(mapped).toBeNull()
    expect(continuousAlignmentViewDelta([400, 300], registration, null)).toBeNull()

    // A short gap next to the verified cell remains navigable so sparse mesh
    // sampling does not interrupt ordinary panning within one component.
    const adjacent = mapContinuousComparisonPoint([150, 25], registration, null)
    expect(adjacent).toEqual([950, 500])
    expect(mapContinuousComparisonPoint(adjacent!, null, registration)?.[0]).toBeCloseTo(150, 10)
    expect(mapContinuousComparisonPoint(adjacent!, null, registration)?.[1]).toBeCloseTo(25, 10)
  })
})
