import { describe, expect, it } from 'vitest'

import { createCompactAnnotationDraft } from '../annotations/drafts'
import { AnnotationSpatialIndex } from '../annotations/spatialIndex'
import { createAnnotationStore } from '../annotations/store'
import {
  MAX_CACHED_ANNOTATIONS,
  MAX_DRAFT_BYTES,
  MAX_MOUNTED_ANNOTATIONS,
  type AnnotationLayer,
  type AnnotationRecord,
} from '../annotations/types'

const layer: AnnotationLayer = {
  id: '11111111-1111-4111-8111-111111111111',
  slideId: 'large-slide',
  name: 'Synthetic',
  sortOrder: 0,
  visible: true,
  locked: false,
  opacity: 1,
  createdAt: '2026-07-26T00:00:00Z',
  updatedAt: '2026-07-26T00:00:00Z',
}

function record(index: number): AnnotationRecord {
  const x = index % 500
  const y = Math.floor(index / 500)
  return {
    id: `annotation-${index}`,
    layerId: layer.id,
    geometry: { type: 'point', x, y },
    style: {
      strokeColor: '#bf3c32',
      fillColor: '#bf3c32',
      strokeWidth: 2,
      opacity: 0.8,
      labelVisible: true,
    },
    metadata: {
      title: `Synthetic ${index}`,
      classification: 'Synthetic',
      tags: [],
      notes: '',
    },
    version: 1,
    deletedAt: null,
    createdAt: '2026-07-26T00:00:00Z',
    updatedAt: '2026-07-26T00:00:00Z',
    bounds: { minX: x, minY: y, maxX: x, maxY: y },
    measurements: {},
  }
}

describe('25,000 annotation stability contract', () => {
  it('keeps rendering and one-record draft work bounded and reports local metrics', () => {
    const heapBefore = process.memoryUsage().heapUsed
    const recordsStarted = performance.now()
    const records = Array.from({ length: 25_000 }, (_, index) => record(index))
    const recordsMs = performance.now() - recordsStarted

    const index = new AnnotationSpatialIndex()
    const indexStarted = performance.now()
    index.load(records)
    const indexMs = performance.now() - indexStarted
    const planStarted = performance.now()
    const plan = index.plan({ minX: 0, minY: 0, maxX: 500, maxY: 50 })
    const planMs = performance.now() - planStarted

    const store = createAnnotationStore({ slideId: 'large-slide' })
    const storeStarted = performance.now()
    store.load({ version: 42, layers: [layer], annotations: records })
    store.update('annotation-1', {
      metadata: {
        ...records[1].metadata,
        title: 'One unsaved local edit',
      },
    })
    const state = store.getState()
    const draft = createCompactAnnotationDraft({
      slideId: state.slideId,
      baseVersion: state.version,
      mutations: state.recoveryMutations,
      savedAt: 100,
    })
    const storeAndDraftMs = performance.now() - storeStarted
    const draftBytes = new TextEncoder().encode(JSON.stringify(draft)).byteLength
    const heapDeltaBytes = process.memoryUsage().heapUsed - heapBefore

    expect(plan.totalVisible).toBe(25_000)
    expect(plan.mounted).toHaveLength(0)
    expect(plan.mounted.length).toBeLessThanOrEqual(MAX_MOUNTED_ANNOTATIONS)
    expect(plan.cached.length).toBeLessThanOrEqual(MAX_CACHED_ANNOTATIONS)
    expect(plan.density.enabled).toBe(true)
    expect(plan.density.cells.length).toBeLessThanOrEqual(1_024)
    expect(draft.mutations).toHaveLength(1)
    expect(draftBytes).toBeLessThan(2_000)
    expect(draftBytes).toBeLessThan(MAX_DRAFT_BYTES)

    if (process.env.PATHLAB_BENCHMARK_METRICS === '1') {
      console.info(JSON.stringify({
        scope: 'machine-local Vitest/jsdom; not browser production load',
        annotations: records.length,
        recordsMs: Number(recordsMs.toFixed(3)),
        spatialIndexMs: Number(indexMs.toFixed(3)),
        renderPlanMs: Number(planMs.toFixed(3)),
        storeAndDraftMs: Number(storeAndDraftMs.toFixed(3)),
        observedHeapDeltaBytes: heapDeltaBytes,
        mounted: plan.mounted.length,
        cached: plan.cached.length,
        densityCells: plan.density.cells.length,
        draftBytes,
      }))
    }
  })
})
