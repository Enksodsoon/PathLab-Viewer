import {
  difference,
  intersection,
  union,
  type MultiPolygon,
  type Polygon,
  type Ring,
} from 'polygon-clipping'

import type { PolygonBooleanOperation, PolygonGeometry } from './types'

function toPolygon(geometry: PolygonGeometry): Polygon {
  const ring: Ring = geometry.points.map(({ x, y }) => [x, y])
  if (ring.length < 3) throw new RangeError('Boolean polygons require at least three vertices')
  const [firstX, firstY] = ring[0]
  const [lastX, lastY] = ring[ring.length - 1]
  if (firstX !== lastX || firstY !== lastY) ring.push([firstX, firstY])
  return [ring]
}

function signedArea(points: readonly [number, number][]): number {
  let area = 0
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index]
    const next = points[(index + 1) % points.length]
    area += current[0] * next[1] - next[0] * current[1]
  }
  return area / 2
}

function normalizeRing(ring: Ring): Array<[number, number]> {
  const open = ring.slice(0, -1) as Array<[number, number]>
  if (open.length < 3) return []
  if (signedArea(open) < 0) open.reverse()
  let startIndex = 0
  for (let index = 1; index < open.length; index += 1) {
    if (
      open[index][1] < open[startIndex][1]
      || (open[index][1] === open[startIndex][1] && open[index][0] < open[startIndex][0])
    ) {
      startIndex = index
    }
  }
  return [...open.slice(startIndex), ...open.slice(0, startIndex)]
}

function stitchHoles(polygon: Polygon): Array<[number, number]> {
  let result = normalizeRing(polygon[0])
  for (const rawHole of polygon.slice(1)) {
    const hole = normalizeRing(rawHole).reverse()
    if (hole.length === 0) continue
    let holeIndex = 0
    for (let index = 1; index < hole.length; index += 1) {
      if (
        hole[index][0] > hole[holeIndex][0]
        || (hole[index][0] === hole[holeIndex][0] && hole[index][1] < hole[holeIndex][1])
      ) {
        holeIndex = index
      }
    }
    const orderedHole = [...hole.slice(holeIndex), ...hole.slice(0, holeIndex)]
    let outerIndex = 0
    let nearest = Number.POSITIVE_INFINITY
    for (let index = 0; index < result.length; index += 1) {
      const distance = Math.hypot(
        result[index][0] - orderedHole[0][0],
        result[index][1] - orderedHole[0][1],
      )
      if (distance < nearest) {
        nearest = distance
        outerIndex = index
      }
    }
    result = [
      ...result.slice(0, outerIndex + 1),
      orderedHole[0],
      ...orderedHole.slice(1),
      orderedHole[0],
      result[outerIndex],
      ...result.slice(outerIndex + 1),
    ]
  }
  return result
}

function fromMultiPolygon(value: MultiPolygon): PolygonGeometry[] {
  return value
    .map(stitchHoles)
    .filter((points) => points.length >= 3)
    .map((points) => ({
      type: 'polygon' as const,
      points: points.map(([x, y]) => ({ x, y })),
    }))
}

export function executePolygonBoolean(
  operation: PolygonBooleanOperation,
  geometries: readonly PolygonGeometry[],
): PolygonGeometry[] {
  if (geometries.length === 0) return []
  const polygons = structuredClone(geometries).map(toPolygon)
  let result: MultiPolygon
  switch (operation) {
    case 'union':
      result = union(polygons[0], ...polygons.slice(1))
      break
    case 'intersection':
      result = intersection(polygons[0], ...polygons.slice(1))
      break
    case 'subtract':
    case 'split':
      result = difference(polygons[0], ...polygons.slice(1))
      break
  }
  return fromMultiPolygon(result)
}
