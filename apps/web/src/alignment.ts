export type AffineTransform = number[][]
export type Point = [number, number]
export type Support = [number, number, number, number] | null

export interface RegistrationTriangle {
  moving: [Point, Point, Point]
  reference: [Point, Point, Point]
  maxResidualPixels?: number
  provenance?: 'structural-feature' | 'structural-flow-patch' | 'structural-flow-neighbor' | 'manual-landmark' | 'approximate-intensity-shape' | 'approximate-structural-flow'
}

export interface LocalRegistration {
  movingToReference?: AffineTransform
  controlPoints?: Array<{ moving: Point; reference: Point; errorPixels: number }>
  triangles?: RegistrationTriangle[]
  overviewTriangles?: RegistrationTriangle[]
}

interface AlignmentViewDelta {
  rotation: number
  zoomScale: number
}

function apply(point: Point, matrix: AffineTransform): Point {
  if (matrix.length !== 2 || matrix.some((row) => row.length !== 3)) throw new Error('Invalid alignment transform')
  return [matrix[0][0] * point[0] + matrix[0][1] * point[1] + matrix[0][2], matrix[1][0] * point[0] + matrix[1][1] * point[1] + matrix[1][2]]
}

function inverse(matrix: AffineTransform): AffineTransform {
  const [[a, b, tx], [c, d, ty]] = matrix
  const determinant = a * d - b * c
  if (Math.abs(determinant) < 1e-12) throw new Error('Alignment transform is singular')
  return [[d / determinant, -b / determinant, (b * ty - d * tx) / determinant], [-c / determinant, a / determinant, (c * tx - a * ty) / determinant]]
}

export function mapComparisonPoint(point: Point, sourceToReference: AffineTransform | null, targetToReference: AffineTransform | null): Point {
  const referencePoint = sourceToReference ? apply(point, sourceToReference) : point
  return targetToReference ? apply(referencePoint, inverse(targetToReference)) : referencePoint
}

function barycentric(point: Point, triangle: [Point, Point, Point]): [number, number, number] | null {
  const [[ax, ay], [bx, by], [cx, cy]] = triangle
  const determinant = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
  if (Math.abs(determinant) < 1e-12) return null
  const first = ((by - cy) * (point[0] - cx) + (cx - bx) * (point[1] - cy)) / determinant
  const second = ((cy - ay) * (point[0] - cx) + (ax - cx) * (point[1] - cy)) / determinant
  const third = 1 - first - second
  return Math.min(first, second, third) >= -1e-7 ? [first, second, third] : null
}

function triangleLinear(source: [Point, Point, Point], target: [Point, Point, Point]): AffineTransform {
  const sourceMatrix = [
    [source[0][0], source[0][1], 1],
    [source[1][0], source[1][1], 1],
    [source[2][0], source[2][1], 1],
  ]
  const determinant = sourceMatrix[0][0] * (sourceMatrix[1][1] - sourceMatrix[2][1])
    - sourceMatrix[0][1] * (sourceMatrix[1][0] - sourceMatrix[2][0])
    + sourceMatrix[1][0] * sourceMatrix[2][1] - sourceMatrix[1][1] * sourceMatrix[2][0]
  if (Math.abs(determinant) < 1e-12) throw new Error('Degenerate registration triangle')
  const solve = (values: number[]) => {
    const [x1, y1] = source[0]; const [x2, y2] = source[1]; const [x3, y3] = source[2]
    const [v1, v2, v3] = values
    return [
      (v1 * (y2 - y3) + v2 * (y3 - y1) + v3 * (y1 - y2)) / determinant,
      (v1 * (x3 - x2) + v2 * (x1 - x3) + v3 * (x2 - x1)) / determinant,
      (v1 * (x2 * y3 - x3 * y2) + v2 * (x3 * y1 - x1 * y3) + v3 * (x1 * y2 - x2 * y1)) / determinant,
    ]
  }
  return [solve(target.map((point) => point[0])), solve(target.map((point) => point[1]))]
}

function mapRegistrationPointUsing(
  point: Point,
  registration: LocalRegistration | null,
  triangles: RegistrationTriangle[] | undefined,
  backwards = false,
): { point: Point; linear: AffineTransform } | null {
  if (!registration?.movingToReference) return { point, linear: [[1, 0, 0], [0, 1, 0]] }
  for (const triangle of triangles ?? []) {
    const source = backwards ? triangle.reference : triangle.moving
    const target = backwards ? triangle.moving : triangle.reference
    const weights = barycentric(point, source)
    if (!weights) continue
    return {
      point: [
        weights[0] * target[0][0] + weights[1] * target[1][0] + weights[2] * target[2][0],
        weights[0] * target[0][1] + weights[1] * target[1][1] + weights[2] * target[2][1],
      ],
      linear: triangleLinear(source, target),
    }
  }
  return null
}

function squaredDistanceToSegment(point: Point, start: Point, end: Point): number {
  const dx = end[0] - start[0]
  const dy = end[1] - start[1]
  const lengthSquared = dx * dx + dy * dy
  if (lengthSquared <= 1e-12) return (point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2
  const projection = Math.max(0, Math.min(1,
    ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / lengthSquared,
  ))
  const x = start[0] + projection * dx
  const y = start[1] + projection * dy
  return (point[0] - x) ** 2 + (point[1] - y) ** 2
}

function mapUsingNearbyOverviewCell(
  point: Point,
  triangles: RegistrationTriangle[],
  backwards: boolean,
): { point: Point; linear: AffineTransform } | null {
  const maximumDistanceSquared = 96 ** 2
  let candidate: RegistrationTriangle | null = null
  let candidateDistanceSquared = Number.POSITIVE_INFINITY
  for (const triangle of triangles) {
    const source = backwards ? triangle.reference : triangle.moving
    const distanceSquared = Math.min(
      squaredDistanceToSegment(point, source[0], source[1]),
      squaredDistanceToSegment(point, source[1], source[2]),
      squaredDistanceToSegment(point, source[2], source[0]),
    )
    if (distanceSquared < candidateDistanceSquared) {
      candidate = triangle
      candidateDistanceSquared = distanceSquared
    }
  }
  if (!candidate || candidateDistanceSquared > maximumDistanceSquared) return null
  const source = backwards ? candidate.reference : candidate.moving
  const target = backwards ? candidate.moving : candidate.reference
  const matrix = triangleLinear(source, target)
  return { point: apply(point, matrix), linear: matrix }
}

export function mapRegistrationPoint(point: Point, registration: LocalRegistration | null, backwards = false): { point: Point; linear: AffineTransform } | null {
  return mapRegistrationPointUsing(point, registration, registration?.triangles, backwards)
}

function mapOverviewRegistrationPoint(point: Point, registration: LocalRegistration | null, backwards = false) {
  if (!registration) return { point, linear: [[1, 0, 0], [0, 1, 0]] as AffineTransform }
  if (registration.overviewTriangles?.length) {
    const mapped = mapRegistrationPointUsing(point, registration, registration.overviewTriangles, backwards)
    if (mapped) return mapped
    return mapUsingNearbyOverviewCell(point, registration.overviewTriangles, backwards)
  }
  if (!registration.movingToReference) return null
  const matrix = backwards ? inverse(registration.movingToReference) : registration.movingToReference
  return { point: apply(point, matrix), linear: matrix }
}

export function mapLocalComparisonPoint(
  point: Point,
  source: LocalRegistration | null,
  target: LocalRegistration | null,
): Point | null {
  const inReference = source ? mapRegistrationPoint(point, source) : { point, linear: [[1, 0, 0], [0, 1, 0]] }
  if (!inReference) return null
  const inTarget = target ? mapRegistrationPoint(inReference.point, target, true) : inReference
  return inTarget?.point ?? null
}

export function hasLocalEvidence(registration: LocalRegistration | null): boolean {
  return !registration || (registration.triangles?.length ?? 0) > 0
}

export function mapOverviewComparisonPoint(
  point: Point,
  source: LocalRegistration | null,
  target: LocalRegistration | null,
): Point | null {
  const inReference = mapOverviewRegistrationPoint(point, source)
  if (!inReference) return null
  return mapOverviewRegistrationPoint(inReference.point, target, true)?.point ?? null
}

export function overviewAlignmentViewDelta(
  point: Point,
  source: LocalRegistration | null,
  target: LocalRegistration | null,
): AlignmentViewDelta | null {
  const sourceMap = mapOverviewRegistrationPoint(point, source)
  if (!sourceMap) return null
  const targetMap = mapOverviewRegistrationPoint(sourceMap.point, target, true)
  if (!targetMap) return null
  return alignmentViewDelta(sourceMap.linear, inverse(targetMap.linear))
}

export function localAlignmentViewDelta(point: Point, source: LocalRegistration | null, target: LocalRegistration | null): AlignmentViewDelta | null {
  const sourceMap = source ? mapRegistrationPoint(point, source) : { point, linear: [[1, 0, 0], [0, 1, 0]] as AffineTransform }
  if (!sourceMap) return null
  const targetMap = target ? mapRegistrationPoint(sourceMap.point, target, true) : { point: sourceMap.point, linear: [[1, 0, 0], [0, 1, 0]] as AffineTransform }
  if (!targetMap) return null
  return alignmentViewDelta(sourceMap.linear, inverse(targetMap.linear))
}

export function withinSupport(point: Point, support: Support): boolean {
  return !support || (point[0] >= support[0] && point[0] <= support[2] && point[1] >= support[1] && point[1] <= support[3])
}

function linearView(matrix: AffineTransform | null) {
  if (!matrix) return { rotation: 0, scale: 1 }
  if (matrix.length !== 2 || matrix.some((row) => row.length !== 3)) throw new Error('Invalid alignment transform')
  const [[a, b], [c, d]] = matrix
  const determinant = a * d - b * c
  if (!Number.isFinite(determinant) || determinant <= 1e-12) throw new Error('Alignment transform cannot orient the viewer')
  return {
    rotation: Math.atan2(c - b, a + d) * 180 / Math.PI,
    scale: Math.sqrt(determinant),
  }
}

export function alignmentViewDelta(
  sourceToReference: AffineTransform | null,
  targetToReference: AffineTransform | null,
): AlignmentViewDelta {
  const source = linearView(sourceToReference)
  const target = linearView(targetToReference)
  return {
    rotation: target.rotation - source.rotation,
    zoomScale: target.scale / source.scale,
  }
}

export function normalizeRotation(degrees: number) {
  return ((degrees % 360) + 360) % 360
}

export function mapSupportBounds(support: Exclude<Support, null>, transform: AffineTransform): Exclude<Support, null> {
  const corners: Point[] = [
    [support[0], support[1]],
    [support[2], support[1]],
    [support[0], support[3]],
    [support[2], support[3]],
  ]
  const mapped = corners.map((point) => apply(point, transform))
  return [
    Math.min(...mapped.map((point) => point[0])),
    Math.min(...mapped.map((point) => point[1])),
    Math.max(...mapped.map((point) => point[0])),
    Math.max(...mapped.map((point) => point[1])),
  ]
}

export function mapComparisonBounds(
  bounds: Exclude<Support, null>,
  sourceToReference: AffineTransform | null,
  targetToReference: AffineTransform | null,
): Exclude<Support, null> {
  const corners: Point[] = [
    [bounds[0], bounds[1]],
    [bounds[2], bounds[1]],
    [bounds[0], bounds[3]],
    [bounds[2], bounds[3]],
  ]
  const mapped = corners.map((point) => mapComparisonPoint(point, sourceToReference, targetToReference))
  return [
    Math.min(...mapped.map((point) => point[0])),
    Math.min(...mapped.map((point) => point[1])),
    Math.max(...mapped.map((point) => point[0])),
    Math.max(...mapped.map((point) => point[1])),
  ]
}

export function intersectSupport(
  left: Exclude<Support, null>,
  right: Exclude<Support, null>,
): Exclude<Support, null> | null {
  const intersection: Exclude<Support, null> = [
    Math.max(left[0], right[0]),
    Math.max(left[1], right[1]),
    Math.min(left[2], right[2]),
    Math.min(left[3], right[3]),
  ]
  return intersection[2] > intersection[0] && intersection[3] > intersection[1] ? intersection : null
}
