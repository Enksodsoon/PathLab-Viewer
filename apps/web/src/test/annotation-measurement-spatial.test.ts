import { describe, expect, it } from 'vitest'

import { measureGeometry } from '../annotations/measurement'
import { AnnotationSpatialIndex } from '../annotations/spatialIndex'
import type { AnnotationRecord } from '../annotations/types'

function record(index: number): AnnotationRecord {
  const x = index % 100
  const y = Math.floor(index / 100)
  return {
    id: `annotation-${index}`,
    layerId: 'layer-1',
    geometry: { type: 'point', x, y },
    style: {
      strokeColor: '#c43d3d',
      fillColor: '#c43d3d',
      strokeWidth: 2,
      opacity: 0.35,
      labelVisible: true,
    },
    metadata: { title: `A${index}`, classification: '', tags: [], notes: '' },
    version: 1,
    deletedAt: null,
    createdAt: '2026-07-26T00:00:00Z',
    updatedAt: '2026-07-26T00:00:00Z',
    bounds: { minX: x, minY: y, maxX: x, maxY: y },
    measurements: {},
  }
}

describe('calibrated annotation measurements', () => {
  it('uses anisotropic nm calibration and reports human-scale micrometres', () => {
    const result = measureGeometry(
      { type: 'polyline', points: [{ x: 0, y: 0 }, { x: 2, y: 1 }] },
      { x: 500, y: 1_000, unit: 'nm' },
    )
    expect(result.calibrated).toBe(true)
    expect(result.values.length).toBeCloseTo(Math.sqrt(2), 8)
    expect(result.values.lengthUnit).toBe('µm')
    expect(result.warning).toBeNull()
  })

  it('converts area to mm squared and keeps angles dimensionless', () => {
    const area = measureGeometry(
      { type: 'rectangle', x: 0, y: 0, width: 2, height: 3 },
      { x: 1, y: 1, unit: 'mm' },
    )
    expect(area.values.area).toBe(6)
    expect(area.values.areaUnit).toBe('mm²')

    const angle = measureGeometry({
      type: 'angle',
      points: [{ x: 1, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 1 }],
    })
    expect(angle.values.angle).toBe(90)
    expect(angle.values.angleUnit).toBe('°')
  })

  it('makes missing and unknown calibration explicitly uncalibrated', () => {
    for (const calibration of [null, { x: 1, y: 1, unit: 'inch' }]) {
      const result = measureGeometry(
        { type: 'polyline', points: [{ x: 0, y: 0 }, { x: 3, y: 4 }] },
        calibration,
      )
      expect(result.calibrated).toBe(false)
      expect(result.values.length).toBe(5)
      expect(result.values.lengthUnit).toBe('px')
      expect(result.warning).toMatch(/uncalibrated/i)
    }
  })
})

describe('bounded spatial rendering plan', () => {
  it('mounts at most 2,000, caches at most 5,000, and supplies density fallback', () => {
    const index = new AnnotationSpatialIndex()
    index.load(Array.from({ length: 6_000 }, (_, itemIndex) => record(itemIndex)))

    const plan = index.plan({ minX: 0, minY: 0, maxX: 100, maxY: 100 })
    expect(plan.mounted).toHaveLength(0)
    expect(plan.cached.length).toBeLessThanOrEqual(5_000)
    expect(plan.totalVisible).toBe(6_000)
    expect(plan.density.enabled).toBe(true)
    expect(plan.density.cells.length).toBeGreaterThan(0)
    expect(plan.prompt).toMatch(/zoom/i)
  })

  it('updates and removes indexed annotations without a full rebuild', () => {
    const index = new AnnotationSpatialIndex()
    index.load([record(1), record(2)])
    const moved = record(1)
    moved.bounds = { minX: 500, minY: 500, maxX: 500, maxY: 500 }
    moved.geometry = { type: 'point', x: 500, y: 500 }
    index.upsert(moved)
    index.remove('annotation-2')

    expect(index.query({ minX: 0, minY: 0, maxX: 10, maxY: 10 })).toEqual([])
    expect(index.query({ minX: 499, minY: 499, maxX: 501, maxY: 501 }))
      .toHaveLength(1)
  })
})
