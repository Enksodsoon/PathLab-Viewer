import { describe, expect, it, vi } from 'vitest'

import { createAnnotationStore } from '../annotations/store'
import type { AnnotationLayer, AnnotationRecord } from '../annotations/types'

const layer: AnnotationLayer = {
  id: 'layer-1',
  slideId: 'slide-1',
  name: 'Diagnostic',
  sortOrder: 0,
  visible: true,
  locked: false,
  opacity: 1,
  createdAt: '2026-07-26T00:00:00Z',
  updatedAt: '2026-07-26T00:00:00Z',
}

const annotation: AnnotationRecord = {
  id: 'a-1',
  layerId: 'layer-1',
  geometry: { type: 'rectangle', x: 10, y: 20, width: 30, height: 40 },
  style: {
    strokeColor: '#c43d3d',
    fillColor: '#c43d3d',
    strokeWidth: 2,
    opacity: 0.35,
    labelVisible: true,
  },
  metadata: { title: 'Tumour', classification: 'Tumour', tags: ['review'], notes: '' },
  version: 1,
  deletedAt: null,
  createdAt: '2026-07-26T00:00:00Z',
  updatedAt: '2026-07-26T00:00:00Z',
  bounds: { minX: 10, minY: 20, maxX: 40, maxY: 60 },
  measurements: {},
}

describe('framework-neutral annotation editing store', () => {
  it('supports tool, selection, layer/filter, bulk editing, delete/restore, and history', () => {
    const store = createAnnotationStore({ slideId: 'slide-1' })
    store.load({ version: 1, layers: [layer], annotations: [annotation] })
    store.setTool('polygon')
    store.select(['a-1'])
    store.bulkUpdate(['a-1'], {
      metadata: { ...annotation.metadata, classification: 'Stroma' },
    })
    expect(store.getState().tool).toBe('polygon')
    expect(store.getState().annotations.get('a-1')?.metadata.classification).toBe('Stroma')

    store.undo()
    expect(store.getState().annotations.get('a-1')?.metadata.classification).toBe('Tumour')
    store.redo()
    expect(store.getState().annotations.get('a-1')?.metadata.classification).toBe('Stroma')

    store.setFilter({ search: 'stroma', layerIds: new Set(['layer-1']) })
    expect(store.visibleAnnotations()).toHaveLength(1)
    store.delete(['a-1'])
    expect(store.visibleAnnotations()).toHaveLength(0)
    store.restore(['a-1'])
    expect(store.visibleAnnotations()).toHaveLength(1)
  })

  it('copies, pastes, duplicates, zooms, and publishes import/export previews', () => {
    const store = createAnnotationStore({
      slideId: 'slide-1',
      idFactory: () => 'a-copy',
    })
    store.load({ version: 1, layers: [layer], annotations: [annotation] })
    store.select(['a-1'])
    store.copy()
    expect(store.paste({ x: 5, y: 5 })).toEqual(['a-copy'])
    expect(store.getState().annotations.get('a-copy')?.geometry).toMatchObject({
      x: 15,
      y: 25,
    })
    expect(store.zoomTarget('a-copy')).toEqual({
      minX: 15,
      minY: 25,
      maxX: 45,
      maxY: 65,
    })
    expect(store.previewImport({
      schema: 'pathlab-annotations/v1',
      slide: { id: 'slide-1', width: 100, height: 100, annotationVersion: 1 },
      layers: [],
      annotations: [],
    }).valid).toBe(true)
    expect(store.exportPathLab().schema).toBe('pathlab-annotations/v1')
  })

  it('attaches and always detaches overlay handlers after failure or disposal', () => {
    const store = createAnnotationStore({ slideId: 'slide-1' })
    const detach = vi.fn()
    const restoreNavigation = vi.fn()

    store.attachOverlay({
      detach,
      restoreNavigation,
      render: vi.fn(() => {
        throw new Error('SVG failure')
      }),
    })
    expect(store.getState().overlayError).toBe('SVG failure')
    expect(detach).toHaveBeenCalledOnce()
    expect(restoreNavigation).toHaveBeenCalledOnce()

    const detachSecond = vi.fn()
    store.attachOverlay({
      detach: detachSecond,
      restoreNavigation,
      render: vi.fn(),
    })
    store.detachOverlay()
    expect(detachSecond).toHaveBeenCalledOnce()
  })

  it('enforces active annotation and layer caps before local state can grow unbounded', () => {
    const store = createAnnotationStore({
      slideId: 'slide-1',
      maxAnnotations: 1,
      maxLayers: 1,
    })
    store.setLayers([layer])
    store.create({
      id: 'first',
      layerId: layer.id,
      geometry: { type: 'point', x: 1, y: 1 },
      style: annotation.style,
      metadata: annotation.metadata,
    })
    expect(() => store.create({
      id: 'second',
      layerId: layer.id,
      geometry: { type: 'point', x: 2, y: 2 },
      style: annotation.style,
      metadata: annotation.metadata,
    })).toThrow(/annotation limit/i)
    expect(() => store.setLayers([layer, { ...layer, id: 'layer-2' }])).toThrow(/layer limit/i)
  })
})
