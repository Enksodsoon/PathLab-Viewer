import type { SlideMetadata } from './types'

const factors: Record<string, number> = {
  um: 1, micrometer: 1, micrometre: 1, micron: 1,
  nm: 0.001, nanometer: 0.001, nanometre: 0.001,
  mm: 1000, millimeter: 1000, millimetre: 1000,
  cm: 10000, centimeter: 10000, centimetre: 10000,
  m: 1000000, meter: 1000000, metre: 1000000,
}

/** Physical navigation requires explicitly calibrated, finite positive image axes. */
export function normalizedMicronsPerPixel(metadata?: SlideMetadata | null): [number, number] | null {
  if (!metadata) return null
  const values: number[] = []
  for (const axis of ['X', 'Y'] as const) {
    const key = `physicalSize${axis}Unit` as const
    const declared = metadata[key] ?? metadata.physicalSizeUnit
    if (typeof declared !== 'string') return null
    const unit = declared.trim().toLowerCase().split('.').at(-1)!.replace(/[µμ]/g, 'u').replace(/s$/, '')
    const value = metadata[`physicalSize${axis}`]
    const normalized = typeof value === 'number' ? value * factors[unit] : NaN
    if (!Number.isFinite(normalized) || normalized <= 0) return null
    values.push(normalized)
  }
  return [values[0], values[1]]
}

/** Micrometres along a horizontal screen pixel before image zoom, without warping pixels. */
export function horizontalMicronsPerPixel(calibration: [number, number], rotation: number): number {
  const radians = rotation * Math.PI / 180
  return Math.hypot(Math.cos(radians) * calibration[0], Math.sin(radians) * calibration[1])
}
