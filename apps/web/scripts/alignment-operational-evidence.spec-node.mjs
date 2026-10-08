import assert from 'node:assert/strict'
import test from 'node:test'
import { boundedPanStroke, previewCandidateProof } from './measure-alignment-operational-ui.mjs'

test('large source-coordinate pans release inside visible canvas and browser', () => {
  const result = boundedPanStroke({ canvas: { x: 640, y: 120, width: 640, height: 600 }, viewport: { width: 1280, height: 720 },
    view: { centerX: 800, centerY: 600, imageZoom: 2, rotation: 0 }, point: [100, 100] })
  assert.ok(result.end[0] < 1280 && result.end[1] < 720)
  assert.ok(result.end[0] > 640 && result.end[1] > 120)
  assert.ok(Math.abs((result.end[0] - result.start[0]) / (result.end[1] - result.start[1]) - 1.4) < 1e-12)
})

test('observed Firefox off-window endpoints become bounded proportional strokes', () => {
  for (const [canvas, oldEnd] of [[{ x: 0, y: 120, width: 639, height: 601 }, [626.8751403541667, 967.3038388333333]],
    [{ x: 640, y: 120, width: 641, height: 601 }, [1515.067694221648, 655.2862078052183]]]) {
    const start = [canvas.x + canvas.width / 2, canvas.y + canvas.height / 2]
    const result = boundedPanStroke({ canvas, viewport: { width: 1280, height: 720 },
      view: { centerX: oldEnd[0] - start[0], centerY: oldEnd[1] - start[1], imageZoom: 1, rotation: 0 }, point: [0, 0] })
    const [left, top, right, bottom] = result.visibleBounds
    assert.ok(result.end[0] > left && result.end[0] < right && result.end[1] > top && result.end[1] < bottom)
  }
})

test('small gestures keep their full pixel displacement', () => {
  const result = boundedPanStroke({ canvas: { x: 0, y: 100, width: 400, height: 500 }, viewport: { width: 400, height: 700 },
    view: { centerX: -12, centerY: -10, imageZoom: 1, rotation: 0 }, point: [0, 0] })
  assert.deepEqual(result.start, [200, 350])
  assert.deepEqual(result.end, [188, 340])
})

test('already-centered source creates no zero-length pointer gesture', () => {
  const values = { canvas: { x: 0, y: 100, width: 400, height: 500 }, viewport: { width: 400, height: 700 },
    view: { centerX: 100, centerY: 200, imageZoom: 2, rotation: 90 }, point: [100, 200] }
  assert.equal(boundedPanStroke(values), null)
  assert.equal(boundedPanStroke({ ...values, point: [100.25, 200.25] }), null)
})

test('rotated partially offscreen pane uses its visible intersection', () => {
  const result = boundedPanStroke({ canvas: { x: -60, y: 200, width: 460, height: 800 }, viewport: { width: 400, height: 700 },
    view: { centerX: 800, centerY: 600, imageZoom: 2, rotation: 90 }, point: [100, 100] })
  assert.deepEqual(result.visibleBounds, [0, 200, 400, 700])
  assert.deepEqual(result.start, [200, 450])
  assert.ok(result.end[0] > 0 && result.end[0] < 400 && result.end[1] > 200 && result.end[1] < 700)
})

test('invalid field and hidden pane refuse a pointer gesture', () => {
  const values = { canvas: { x: 0, y: 0, width: 640, height: 600 }, viewport: { width: 1280, height: 720 },
    view: { centerX: 800, centerY: 600, imageZoom: 2, rotation: 0 }, point: [100, 100] }
  assert.throws(() => boundedPanStroke({ ...values, view: { ...values.view, rotation: NaN } }))
  assert.throws(() => boundedPanStroke({ ...values, canvas: { x: 1300, y: 0, width: 640, height: 600 } }))
})

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
