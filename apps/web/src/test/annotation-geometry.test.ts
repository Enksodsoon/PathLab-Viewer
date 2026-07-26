import { describe, expect, it, vi } from 'vitest'

import {
  BooleanOperationTimeoutError,
  createBooleanWorkerClient,
  executePolygonBoolean,
} from '../annotations/boolean'
import {
  createGeometryForTool,
  duplicateAnnotation,
  editVertex,
  moveGeometry,
  resizeGeometry,
} from '../annotations/geometry'
import type { AnnotationRecord, PolygonGeometry } from '../annotations/types'

const polygon = (points: Array<[number, number]>): PolygonGeometry => ({
  type: 'polygon',
  points: points.map(([x, y]) => ({ x, y })),
})

describe('annotation geometry tools', () => {
  it('creates every approved drawing geometry in source-image pixels', () => {
    expect(createGeometryForTool('point', [{ x: 12, y: 18 }])).toEqual({
      type: 'point',
      x: 12,
      y: 18,
    })
    expect(createGeometryForTool('ruler', [{ x: 1, y: 2 }, { x: 5, y: 8 }])?.type)
      .toBe('polyline')
    expect(createGeometryForTool('polyline', [{ x: 1, y: 2 }, { x: 5, y: 8 }])?.type)
      .toBe('polyline')
    expect(createGeometryForTool('angle', [
      { x: 1, y: 2 },
      { x: 5, y: 8 },
      { x: 9, y: 4 },
    ])?.type).toBe('angle')
    expect(createGeometryForTool('rectangle', [{ x: 8, y: 9 }, { x: 2, y: 3 }])).toEqual({
      type: 'rectangle',
      x: 2,
      y: 3,
      width: 6,
      height: 6,
    })
    expect(createGeometryForTool('ellipse', [{ x: 2, y: 3 }, { x: 8, y: 9 }])).toEqual({
      type: 'ellipse',
      cx: 5,
      cy: 6,
      rx: 3,
      ry: 3,
    })
    for (const tool of ['polygon', 'freehand', 'brush-add', 'brush-subtract'] as const) {
      expect(createGeometryForTool(tool, [
        { x: 2, y: 3 },
        { x: 8, y: 3 },
        { x: 8, y: 9 },
      ])?.type).toBe('polygon')
    }
    expect(createGeometryForTool('text', [{ x: 4, y: 6 }], { text: 'Callout' })).toEqual({
      type: 'text',
      x: 4,
      y: 6,
      text: 'Callout',
    })
    expect(createGeometryForTool('hand', [])).toBeNull()
    expect(createGeometryForTool('select', [])).toBeNull()
    expect(createGeometryForTool('marquee', [])).toBeNull()
  })

  it('rejects non-finite coordinates and shapes above 8,192 vertices client-side', () => {
    expect(() => createGeometryForTool('point', [{ x: Number.NaN, y: 1 }])).toThrow(
      /finite/i,
    )
    expect(() => createGeometryForTool(
      'polygon',
      Array.from({ length: 8_193 }, (_, index) => ({ x: index, y: index % 2 })),
    )).toThrow(/8,192/)
  })

  it('moves, resizes, edits vertices, and duplicates without mutating source records', () => {
    const source: AnnotationRecord = {
      id: '00000000-0000-4000-8000-000000000001',
      layerId: '00000000-0000-4000-8000-000000000010',
      geometry: polygon([[1, 1], [5, 1], [5, 5]]),
      style: {
        strokeColor: '#c43d3d',
        fillColor: '#c43d3d',
        strokeWidth: 2,
        opacity: 0.35,
        labelVisible: true,
      },
      metadata: { title: 'A', classification: '', tags: [], notes: '' },
      version: 1,
      deletedAt: null,
      createdAt: '2026-07-26T00:00:00Z',
      updatedAt: '2026-07-26T00:00:00Z',
      bounds: { minX: 1, minY: 1, maxX: 5, maxY: 5 },
      measurements: {},
    }
    const before = structuredClone(source)

    expect(moveGeometry(source.geometry, 3, -1)).toMatchObject({
      points: [{ x: 4, y: 0 }, { x: 8, y: 0 }, { x: 8, y: 4 }],
    })
    expect(resizeGeometry(source.geometry, { minX: 1, minY: 1, maxX: 9, maxY: 9 }))
      .toMatchObject({ points: [{ x: 1, y: 1 }, { x: 9, y: 1 }, { x: 9, y: 9 }] })
    expect(editVertex(source.geometry, 1, { x: 7, y: 2 })).toMatchObject({
      points: [{ x: 1, y: 1 }, { x: 7, y: 2 }, { x: 5, y: 5 }],
    })
    const copy = duplicateAnnotation(
      source,
      '00000000-0000-4000-8000-000000000002',
      { x: 10, y: 20 },
    )
    expect(copy.id).not.toBe(source.id)
    expect(copy.version).toBe(0)
    expect(copy.geometry).toMatchObject({
      points: [{ x: 11, y: 21 }, { x: 15, y: 21 }, { x: 15, y: 25 }],
    })
    expect(source).toEqual(before)
  })
})

describe('bounded polygon booleans', () => {
  it('performs union, subtraction, intersection, and split without mutating inputs', () => {
    const left = polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    const right = polygon([[5, 0], [15, 0], [15, 10], [5, 10]])
    const before = structuredClone([left, right])

    expect(executePolygonBoolean('union', [left, right])).toHaveLength(1)
    expect(executePolygonBoolean('intersection', [left, right])).toEqual([
      polygon([[5, 0], [10, 0], [10, 10], [5, 10]]),
    ])
    expect(executePolygonBoolean('subtract', [left, right])).toHaveLength(1)
    expect(executePolygonBoolean('split', [left, right]).length).toBeGreaterThanOrEqual(1)
    expect([left, right]).toEqual(before)
  })

  it('terminates a stalled worker at two seconds and leaves source geometry untouched', async () => {
    vi.useFakeTimers()
    const terminate = vi.fn()
    const source = polygon([[0, 0], [10, 0], [10, 10]])
    const before = structuredClone(source)
    const client = createBooleanWorkerClient(() => ({
      postMessage: vi.fn(),
      terminate,
      onmessage: null,
      onerror: null,
    }))

    const pending = client.run('union', [source])
    const rejection = expect(pending).rejects.toBeInstanceOf(BooleanOperationTimeoutError)
    await vi.advanceTimersByTimeAsync(2_000)
    await rejection
    expect(terminate).toHaveBeenCalledOnce()
    expect(source).toEqual(before)
    vi.useRealTimers()
  })
})
