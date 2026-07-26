import type {
  AngleGeometry,
  AnnotationBounds,
  AnnotationGeometry,
  AnnotationPoint,
  AnnotationRecord,
  AnnotationTool,
  PolygonGeometry,
} from './types'
import { MAX_VERTICES_PER_SHAPE } from './types'

function clone<T>(value: T): T {
  return structuredClone(value)
}

function finitePoint(point: AnnotationPoint): AnnotationPoint {
  if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) {
    throw new TypeError('Annotation coordinates must be finite')
  }
  return { x: point.x, y: point.y }
}

function requirePoints(points: readonly AnnotationPoint[], minimum: number): AnnotationPoint[] {
  if (points.length < minimum) throw new RangeError(`At least ${minimum} points are required`)
  if (points.length > MAX_VERTICES_PER_SHAPE) {
    throw new RangeError('Annotation shapes cannot exceed 8,192 vertices')
  }
  return points.map(finitePoint)
}

export function geometryVertexCount(geometry: AnnotationGeometry): number {
  switch (geometry.type) {
    case 'angle':
    case 'polyline':
    case 'polygon':
      return geometry.points.length
    case 'rectangle':
      return 4
    case 'ellipse':
      return 64
    case 'point':
    case 'text':
      return 1
  }
}

export function createGeometryForTool(
  tool: AnnotationTool,
  points: readonly AnnotationPoint[],
  options: { text?: string } = {},
): AnnotationGeometry | null {
  switch (tool) {
    case 'hand':
    case 'select':
    case 'marquee':
      return null
    case 'point': {
      const point = requirePoints(points, 1)[0]
      return { type: 'point', ...point }
    }
    case 'ruler':
    case 'polyline':
      return { type: 'polyline', points: requirePoints(points, 2) }
    case 'angle': {
      const anglePoints = requirePoints(points, 3).slice(0, 3)
      return { type: 'angle', points: anglePoints as AngleGeometry['points'] }
    }
    case 'rectangle': {
      const [start, end] = requirePoints(points, 2)
      const width = Math.abs(end.x - start.x)
      const height = Math.abs(end.y - start.y)
      if (width === 0 || height === 0) throw new RangeError('Rectangle must have positive area')
      return {
        type: 'rectangle',
        x: Math.min(start.x, end.x),
        y: Math.min(start.y, end.y),
        width,
        height,
      }
    }
    case 'ellipse': {
      const [start, end] = requirePoints(points, 2)
      const rx = Math.abs(end.x - start.x) / 2
      const ry = Math.abs(end.y - start.y) / 2
      if (rx === 0 || ry === 0) throw new RangeError('Ellipse must have positive area')
      return {
        type: 'ellipse',
        cx: (start.x + end.x) / 2,
        cy: (start.y + end.y) / 2,
        rx,
        ry,
      }
    }
    case 'polygon':
    case 'freehand':
    case 'brush-add':
    case 'brush-subtract':
      return { type: 'polygon', points: requirePoints(points, 3) }
    case 'text': {
      const point = requirePoints(points, 1)[0]
      const text = options.text?.trim()
      if (!text) throw new RangeError('Text is required')
      return { type: 'text', ...point, text }
    }
  }
}

export function geometryBounds(geometry: AnnotationGeometry): AnnotationBounds {
  switch (geometry.type) {
    case 'point':
    case 'text':
      return { minX: geometry.x, minY: geometry.y, maxX: geometry.x, maxY: geometry.y }
    case 'rectangle':
      return {
        minX: geometry.x,
        minY: geometry.y,
        maxX: geometry.x + geometry.width,
        maxY: geometry.y + geometry.height,
      }
    case 'ellipse':
      return {
        minX: geometry.cx - geometry.rx,
        minY: geometry.cy - geometry.ry,
        maxX: geometry.cx + geometry.rx,
        maxY: geometry.cy + geometry.ry,
      }
    case 'angle':
    case 'polyline':
    case 'polygon': {
      const xs = geometry.points.map((point) => point.x)
      const ys = geometry.points.map((point) => point.y)
      return {
        minX: Math.min(...xs),
        minY: Math.min(...ys),
        maxX: Math.max(...xs),
        maxY: Math.max(...ys),
      }
    }
  }
}

export function moveGeometry(
  geometry: AnnotationGeometry,
  deltaX: number,
  deltaY: number,
): AnnotationGeometry {
  if (!Number.isFinite(deltaX) || !Number.isFinite(deltaY)) {
    throw new TypeError('Move offsets must be finite')
  }
  switch (geometry.type) {
    case 'point':
      return { ...geometry, x: geometry.x + deltaX, y: geometry.y + deltaY }
    case 'text':
      return { ...geometry, x: geometry.x + deltaX, y: geometry.y + deltaY }
    case 'rectangle':
      return { ...geometry, x: geometry.x + deltaX, y: geometry.y + deltaY }
    case 'ellipse':
      return { ...geometry, cx: geometry.cx + deltaX, cy: geometry.cy + deltaY }
    case 'angle':
      return {
        ...geometry,
        points: geometry.points.map((point) => ({
          x: point.x + deltaX,
          y: point.y + deltaY,
        })) as AngleGeometry['points'],
      }
    case 'polyline':
    case 'polygon':
      return {
        ...geometry,
        points: geometry.points.map((point) => ({
          x: point.x + deltaX,
          y: point.y + deltaY,
        })),
      }
  }
}

function mapPointToBounds(
  point: AnnotationPoint,
  source: AnnotationBounds,
  target: AnnotationBounds,
): AnnotationPoint {
  const sourceWidth = source.maxX - source.minX
  const sourceHeight = source.maxY - source.minY
  const targetWidth = target.maxX - target.minX
  const targetHeight = target.maxY - target.minY
  return {
    x: sourceWidth === 0
      ? target.minX
      : target.minX + ((point.x - source.minX) / sourceWidth) * targetWidth,
    y: sourceHeight === 0
      ? target.minY
      : target.minY + ((point.y - source.minY) / sourceHeight) * targetHeight,
  }
}

export function resizeGeometry(
  geometry: AnnotationGeometry,
  bounds: AnnotationBounds,
): AnnotationGeometry {
  if (bounds.maxX <= bounds.minX || bounds.maxY <= bounds.minY) {
    throw new RangeError('Resize bounds must have positive area')
  }
  const source = geometryBounds(geometry)
  switch (geometry.type) {
    case 'point':
      return { ...geometry, x: bounds.minX, y: bounds.minY }
    case 'text':
      return { ...geometry, x: bounds.minX, y: bounds.minY }
    case 'rectangle':
      return {
        ...geometry,
        x: bounds.minX,
        y: bounds.minY,
        width: bounds.maxX - bounds.minX,
        height: bounds.maxY - bounds.minY,
      }
    case 'ellipse':
      return {
        ...geometry,
        cx: (bounds.minX + bounds.maxX) / 2,
        cy: (bounds.minY + bounds.maxY) / 2,
        rx: (bounds.maxX - bounds.minX) / 2,
        ry: (bounds.maxY - bounds.minY) / 2,
      }
    case 'angle':
      return {
        ...geometry,
        points: geometry.points.map(
          (point) => mapPointToBounds(point, source, bounds),
        ) as AngleGeometry['points'],
      }
    case 'polyline':
    case 'polygon':
      return {
        ...geometry,
        points: geometry.points.map((point) => mapPointToBounds(point, source, bounds)),
      }
  }
}

export function editVertex(
  geometry: AnnotationGeometry,
  index: number,
  point: AnnotationPoint,
): AnnotationGeometry {
  if (!('points' in geometry)) throw new TypeError(`${geometry.type} has no editable vertices`)
  if (!Number.isInteger(index) || index < 0 || index >= geometry.points.length) {
    throw new RangeError('Vertex index is outside the geometry')
  }
  const points = geometry.points.map((candidate, candidateIndex) => (
    candidateIndex === index ? finitePoint(point) : { ...candidate }
  ))
  if (geometry.type === 'angle') {
    return { ...geometry, points: points as AngleGeometry['points'] }
  }
  return { ...geometry, points }
}

export function duplicateAnnotation(
  source: AnnotationRecord,
  id: string,
  offset: AnnotationPoint = { x: 12, y: 12 },
): AnnotationRecord {
  const geometry = moveGeometry(source.geometry, offset.x, offset.y)
  return {
    ...clone(source),
    id,
    geometry,
    bounds: geometryBounds(geometry),
    version: 0,
    deletedAt: null,
  }
}

export function asPolygon(geometry: AnnotationGeometry, segments = 64): PolygonGeometry {
  switch (geometry.type) {
    case 'polygon':
      return clone(geometry)
    case 'rectangle':
      return {
        type: 'polygon',
        points: [
          { x: geometry.x, y: geometry.y },
          { x: geometry.x + geometry.width, y: geometry.y },
          { x: geometry.x + geometry.width, y: geometry.y + geometry.height },
          { x: geometry.x, y: geometry.y + geometry.height },
        ],
      }
    case 'ellipse':
      return {
        type: 'polygon',
        points: Array.from({ length: Math.max(12, segments) }, (_, index) => {
          const angle = (index / Math.max(12, segments)) * Math.PI * 2
          return {
            x: geometry.cx + Math.cos(angle) * geometry.rx,
            y: geometry.cy + Math.sin(angle) * geometry.ry,
          }
        }),
      }
    default:
      throw new TypeError(`${geometry.type} cannot be converted to a closed ROI`)
  }
}
