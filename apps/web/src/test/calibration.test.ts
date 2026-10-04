import { expect, it } from 'vitest'
import { horizontalMicronsPerPixel, normalizedMicronsPerPixel } from '../calibration'

it.each([
  ['um', 0.25], ['µm', 0.25], ['μm', 0.25], ['UnitsLength.MICROMETER', 0.25],
  ['micrometres', 0.25], ['nanometers', 250], ['mm', 0.00025],
  ['cm', 0.000025], ['m', 0.00000025],
])('normalizes declared %s units without guessing', (physicalSizeUnit, value) => {
  const calibration = normalizedMicronsPerPixel({ width: 100, height: 100, physicalSizeX: value, physicalSizeY: value * 2, physicalSizeUnit })!
  expect(calibration[0]).toBeCloseTo(0.25)
  expect(calibration[1]).toBeCloseTo(0.5)
})

it('uses declared per-axis units and fails closed on an unknown overriding unit', () => {
  const metadata = { width: 100, height: 100, physicalSizeX: 250, physicalSizeY: 0.0005, physicalSizeXUnit: 'nm', physicalSizeYUnit: 'mm', physicalSizeUnit: 'um' }
  expect(normalizedMicronsPerPixel(metadata)).toEqual([0.25, 0.5])
  expect(normalizedMicronsPerPixel({ ...metadata, physicalSizeXUnit: 'pixels' })).toBeNull()
  expect(normalizedMicronsPerPixel({ ...metadata, physicalSizeX: 0.25, physicalSizeXUnit: null })).toEqual([0.25, 0.5])
})

it.each([undefined, null, '', 'unknown'])('rejects missing or unknown unit %s', physicalSizeUnit => {
  expect(normalizedMicronsPerPixel({ width: 100, height: 100, physicalSizeX: 0.25, physicalSizeY: 0.5, physicalSizeUnit })).toBeNull()
})

it.each([NaN, Infinity, 0, -1, null, undefined])('rejects invalid physical size %s', physicalSizeY => {
  expect(normalizedMicronsPerPixel({ width: 100, height: 100, physicalSizeX: 0.25, physicalSizeY, physicalSizeUnit: 'um' })).toBeNull()
})

it('reports horizontal physical length at arbitrary and right-angle rotations', () => {
  expect(horizontalMicronsPerPixel([0.25, 0.5], 90)).toBeCloseTo(0.5)
  expect(horizontalMicronsPerPixel([0.25, 0.5], 180)).toBeCloseTo(0.25)
  expect(horizontalMicronsPerPixel([0.25, 0.5], 45)).toBeCloseTo(Math.sqrt((0.25 ** 2 + 0.5 ** 2) / 2))
})
