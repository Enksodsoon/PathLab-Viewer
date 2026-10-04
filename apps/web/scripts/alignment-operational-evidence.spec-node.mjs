import assert from 'node:assert/strict'
import test from 'node:test'
import { previewCandidateProof } from './measure-alignment-operational-ui.mjs'

const cells = [{ moving: [[0, 0], [100, 0], [0, 100]], reference: [[10, 20], [110, 20], [10, 120]] }]
const sample = () => ({ sourceSlideId: 'moving', slideId: 'reference',
  sourceViewport: { centerX: 20, centerY: 30 }, viewport: { centerX: 30, centerY: 50 },
  observedAt: 150, frameObservedAt: 180, nonuniformCanvases: 2, retainedOverview: false, regional: false })
const proof = applications => previewCandidateProof({ applications, started: 100,
  cells, sourceId: 'moving', anchorId: 'reference' })

test('Preview clock includes dispatch scheduling and rendered candidate geometry', () => {
  const result = proof([sample()])
  assert.equal(result.seconds, 0.08)
  assert.equal(result.direction, 'candidate-to-anchor')
  assert.deepEqual(result.expected, [30, 50])
  assert.equal(result.centerResidualPixels, 0)
})

test('reversed application requires inverse candidate coordinates', () => {
  const row = sample()
  Object.assign(row, { sourceSlideId: 'reference', slideId: 'moving',
    sourceViewport: row.viewport, viewport: row.sourceViewport })
  assert.equal(proof([row]).direction, 'anchor-to-candidate')
})

test('fallback-only and regional geometry never qualify the Preview clock', () => {
  assert.equal(proof([{ ...sample(), retainedOverview: true }]), null)
  assert.equal(proof([{ ...sample(), regional: true }]), null)
})

test('wrong coordinates, unsupported center and unrelated pair remain null', () => {
  assert.equal(proof([{ ...sample(), viewport: { centerX: 80, centerY: 50 } }]), null)
  assert.equal(proof([{ ...sample(), sourceViewport: { centerX: 900, centerY: 900 } }]), null)
  assert.equal(proof([{ ...sample(), slideId: 'another-reference' }]), null)
})

test('missing original-pixel evidence and invalid observation clocks remain null', () => {
  for (const patch of [{ nonuniformCanvases: undefined }, { nonuniformCanvases: 1 },
    { observedAt: 90 }, { frameObservedAt: 149 }, { frameObservedAt: NaN }]) {
    assert.equal(proof([{ ...sample(), ...patch }]), null)
  }
})

test('selects first own rendered application after a fallback without measuring fallback', () => {
  const later = { ...sample(), observedAt: 200, frameObservedAt: 220 }
  assert.equal(proof([{ ...sample(), retainedOverview: true }, later]).seconds, 0.12)
})
