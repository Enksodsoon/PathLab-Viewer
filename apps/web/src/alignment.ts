export type AffineTransform = number[][]
export type Point = [number, number]
export type Support = [number, number, number, number] | null

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

export function withinSupport(point: Point, support: Support): boolean {
  return !support || (point[0] >= support[0] && point[0] <= support[2] && point[1] >= support[1] && point[1] <= support[3])
}
