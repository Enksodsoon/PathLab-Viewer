export type AffineTransform = number[][]
export type Point = [number, number]
export type Support = [number, number, number, number] | null

export interface LocalRegistration {
  movingToReference?: AffineTransform
  controlPoints?: Array<{ moving: Point; reference: Point; errorPixels: number }>
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

function mapLocal(point: Point, registration: LocalRegistration | null, backwards = false): Point {
  if (!registration?.movingToReference) return point
  const matrix = backwards ? inverse(registration.movingToReference) : registration.movingToReference
  const base = apply(point, matrix)
  const controls = registration.controlPoints ?? []
  if (!controls.length) return base
  const samples = controls.map((control) => {
    const source = backwards ? control.reference : control.moving
    const target = backwards ? control.moving : control.reference
    const predicted = apply(source, matrix)
    return {
      distance: Math.hypot(source[0] - point[0], source[1] - point[1]),
      residual: [target[0] - predicted[0], target[1] - predicted[1]] as Point,
    }
  }).sort((left, right) => left.distance - right.distance).slice(0, 6)
  if (samples[0].distance < 1e-6) return [base[0] + samples[0].residual[0], base[1] + samples[0].residual[1]]
  let total = 0
  let dx = 0
  let dy = 0
  for (const sample of samples) {
    const weight = 1 / Math.max(1, sample.distance * sample.distance)
    total += weight
    dx += weight * sample.residual[0]
    dy += weight * sample.residual[1]
  }
  return [base[0] + dx / total, base[1] + dy / total]
}

export function mapLocalComparisonPoint(
  point: Point,
  source: LocalRegistration | null,
  target: LocalRegistration | null,
): Point {
  return mapLocal(mapLocal(point, source), target, true)
}

export function hasLocalEvidence(registration: LocalRegistration | null): boolean {
  return !registration || (registration.controlPoints?.length ?? 0) >= 4
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
