import { expect, it } from 'vitest'
import * as alignment from '../alignment'

const members = [
  { slideId: 'ref', registration: null },
  { slideId: 'a', registration: { status: 'approximate', anchorSlideId: 'ref', movingToReference: [[1, 0, 10], [0, 1, 0]] } },
  { slideId: 'b', registration: { status: 'approximate', anchorSlideId: 'a', movingToReference: [[2, 0, 0], [0, 2, 0]] } },
  { slideId: 'missing', registration: null },
]

it('maps a two-edge anchor chain in both directions, retaining approximate provenance', () => {
  const mapped = alignment.mapStackPoint([50, 20], 'ref', 'b', 'ref', members)
  expect(mapped?.point).toEqual([20, 10])
  expect(mapped?.zoomScale).toBe(2)
  expect(mapped?.approximate).toBe(true)
  expect(alignment.mapStackPoint([20, 10], 'b', 'ref', 'ref', members)?.point).toEqual([50, 20])
})

it('never interprets a missing registration as an identity map', () => {
  expect(alignment.mapStackPoint([50, 20], 'ref', 'missing', 'ref', members)).toBeNull()
})

it('rejects cyclic anchors and refuses approximate edges in strict mode', () => {
  expect(alignment.mapStackPoint([50, 20], 'ref', 'b', 'ref', members, 'strict')).toBeNull()
  const cyclic = members.map(m => m.slideId === 'a' ? { ...m, registration: { ...m.registration!, anchorSlideId: 'b' } } : m)
  expect(alignment.mapStackPoint([50, 20], 'ref', 'b', 'ref', cyclic)).toBeNull()
})
