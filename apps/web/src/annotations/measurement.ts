import type {
  AnnotationCalibration,
  AnnotationGeometry,
  AnnotationPoint,
  MeasurementValues,
} from './types'

export interface AnnotationMeasurement {
  calibrated: boolean
  warning: string | null
  values: MeasurementValues
}

interface CalibrationScale {
  x: number
  y: number
  calibrated: boolean
  warning: string | null
}

function calibrationScale(calibration?: AnnotationCalibration | null): CalibrationScale {
  if (!calibration) {
    return { x: 1, y: 1, calibrated: false, warning: 'Uncalibrated: values are in pixels' }
  }
  const normalizedUnit = calibration.unit.trim().toLowerCase().replace('μ', 'µ')
  const factor = normalizedUnit === 'nm'
    ? 0.001
    : normalizedUnit === 'µm' || normalizedUnit === 'um'
      ? 1
      : normalizedUnit === 'mm'
        ? 1_000
        : null
  if (
    factor === null
    || !Number.isFinite(calibration.x)
    || !Number.isFinite(calibration.y)
    || calibration.x <= 0
    || calibration.y <= 0
  ) {
    return {
      x: 1,
      y: 1,
      calibrated: false,
      warning: `Uncalibrated: unsupported calibration unit "${calibration.unit}"`,
    }
  }
  return {
    x: calibration.x * factor,
    y: calibration.y * factor,
    calibrated: true,
    warning: null,
  }
}

function distance(
  left: AnnotationPoint,
  right: AnnotationPoint,
  scale: CalibrationScale,
): number {
  return Math.hypot((right.x - left.x) * scale.x, (right.y - left.y) * scale.y)
}

function lineLength(points: readonly AnnotationPoint[], scale: CalibrationScale): number {
  let length = 0
  for (let index = 1; index < points.length; index += 1) {
    length += distance(points[index - 1], points[index], scale)
  }
  return length
}

function polygonArea(points: readonly AnnotationPoint[], scale: CalibrationScale): number {
  let twiceArea = 0
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index]
    const next = points[(index + 1) % points.length]
    twiceArea += (current.x * scale.x) * (next.y * scale.y)
      - (next.x * scale.x) * (current.y * scale.y)
  }
  return Math.abs(twiceArea) / 2
}

function angleDegrees(
  points: readonly [AnnotationPoint, AnnotationPoint, AnnotationPoint],
  scale: CalibrationScale,
): number {
  const [start, vertex, end] = points
  const left = {
    x: (start.x - vertex.x) * scale.x,
    y: (start.y - vertex.y) * scale.y,
  }
  const right = {
    x: (end.x - vertex.x) * scale.x,
    y: (end.y - vertex.y) * scale.y,
  }
  const denominator = Math.hypot(left.x, left.y) * Math.hypot(right.x, right.y)
  if (denominator === 0) return 0
  const cosine = Math.max(-1, Math.min(1, (left.x * right.x + left.y * right.y) / denominator))
  return (Math.acos(cosine) * 180) / Math.PI
}

function addLength(values: MeasurementValues, key: 'length' | 'perimeter', micrometres: number): void {
  if (micrometres >= 1_000) {
    values[key] = micrometres / 1_000
    values[`${key}Unit`] = 'mm'
  } else {
    values[key] = micrometres
    values[`${key}Unit`] = 'µm'
  }
}

function addArea(values: MeasurementValues, squareMicrometres: number): void {
  if (squareMicrometres >= 1_000_000) {
    values.area = squareMicrometres / 1_000_000
    values.areaUnit = 'mm²'
  } else {
    values.area = squareMicrometres
    values.areaUnit = 'µm²'
  }
}

function addPixelLength(values: MeasurementValues, key: 'length' | 'perimeter', pixels: number): void {
  values[key] = pixels
  values[`${key}Unit`] = 'px'
}

function addCoordinates(
  values: MeasurementValues,
  point: AnnotationPoint,
  scale: CalibrationScale,
): void {
  if (scale.calibrated) {
    if (point.x * scale.x >= 1_000) {
      values.x = (point.x * scale.x) / 1_000
      values.xUnit = 'mm'
    } else {
      values.x = point.x * scale.x
      values.xUnit = 'µm'
    }
    if (point.y * scale.y >= 1_000) {
      values.y = (point.y * scale.y) / 1_000
      values.yUnit = 'mm'
    } else {
      values.y = point.y * scale.y
      values.yUnit = 'µm'
    }
  } else {
    values.x = point.x
    values.xUnit = 'px'
    values.y = point.y
    values.yUnit = 'px'
  }
}

export function measureGeometry(
  geometry: AnnotationGeometry,
  calibration?: AnnotationCalibration | null,
): AnnotationMeasurement {
  const scale = calibrationScale(calibration)
  const values: MeasurementValues = {}
  const length = (key: 'length' | 'perimeter', value: number) => {
    if (scale.calibrated) addLength(values, key, value)
    else addPixelLength(values, key, value)
  }
  const area = (value: number) => {
    if (scale.calibrated) addArea(values, value)
    else {
      values.area = value
      values.areaUnit = 'px²'
    }
  }

  switch (geometry.type) {
    case 'point':
      addCoordinates(values, geometry, scale)
      values.count = 1
      break
    case 'text':
      addCoordinates(values, geometry, scale)
      break
    case 'polyline':
      length('length', lineLength(geometry.points, scale))
      break
    case 'angle':
      values.angle = angleDegrees(geometry.points, scale)
      values.angleUnit = '°'
      break
    case 'rectangle': {
      const width = geometry.width * scale.x
      const height = geometry.height * scale.y
      length('perimeter', 2 * (width + height))
      area(width * height)
      break
    }
    case 'ellipse': {
      const radiusX = geometry.rx * scale.x
      const radiusY = geometry.ry * scale.y
      const h = ((radiusX - radiusY) ** 2) / ((radiusX + radiusY) ** 2)
      const perimeter = Math.PI * (radiusX + radiusY)
        * (1 + (3 * h) / (10 + Math.sqrt(4 - 3 * h)))
      length('perimeter', perimeter)
      area(Math.PI * radiusX * radiusY)
      break
    }
    case 'polygon':
      length(
        'perimeter',
        lineLength([...geometry.points, geometry.points[0]], scale),
      )
      area(polygonArea(geometry.points, scale))
      break
  }

  return {
    calibrated: scale.calibrated,
    warning: scale.warning,
    values,
  }
}
