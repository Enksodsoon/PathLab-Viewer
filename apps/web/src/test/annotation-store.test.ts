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

  it('coalesces pending edits and reconciles server versions through explicit acknowledgement', () => {
    const store = createAnnotationStore({ slideId: 'slide-1' })
    store.load({ version: 1, layers: [layer], annotations: [annotation] })
    store.update('a-1', { geometry: { type: 'point', x: 4, y: 5 } })
    store.update('a-1', {
      metadata: { ...annotation.metadata, title: 'Latest' },
    })
    expect(store.peekPendingMutations()).toEqual([{
      type: 'update',
      id: 'a-1',
      version: 1,
      geometry: { type: 'point', x: 4, y: 5 },
      metadata: { ...annotation.metadata, title: 'Latest' },
    }])
    const sent = store.peekPendingMutations()
    store.beginSave('m-1', sent)
    expect(store.peekPendingMutations()).toEqual([])
    store.acknowledgeSave({
      mutationId: 'm-1',
      operations: sent,
      result: {
        mutationId: 'm-1',
        version: 2,
        results: [{ id: 'a-1', operation: 'update', version: 2, deleted: false }],
        purged: 0,
      },
    })
    expect(store.getState()).toMatchObject({ version: 2 })
    expect(store.getState().annotations.get('a-1')).toMatchObject({
      version: 2,
      geometry: { type: 'point', x: 4, y: 5 },
      measurements: { x: 4, xUnit: 'px', y: 5, yUnit: 'px', count: 1 },
    })
    expect(store.getState().pendingMutations).toEqual([])

    store.update('a-1', {
      metadata: { ...annotation.metadata, title: 'Second save' },
    })
    expect(store.peekPendingMutations()[0]).toMatchObject({ version: 2 })
  })

  it('reconciles a version-zero create and preserves a newer edit made while create is in flight', () => {
    const store = createAnnotationStore({ slideId: 'slide-1' })
    store.load({ version: 0, layers: [layer], annotations: [] })
    store.create({
      id: 'new-a',
      layerId: layer.id,
      geometry: { type: 'point', x: 1, y: 1 },
      style: annotation.style,
      metadata: annotation.metadata,
    })
    const create = store.peekPendingMutations()
    store.beginSave('create-1', create)
    store.update('new-a', {
      metadata: { ...annotation.metadata, title: 'Edited during save' },
    })
    store.acknowledgeSave({
      mutationId: 'create-1',
      operations: create,
      result: {
        mutationId: 'create-1',
        version: 1,
        results: [{ id: 'new-a', operation: 'create', version: 1, deleted: false }],
        purged: 0,
      },
      records: [{
        ...structuredClone(store.getState().annotations.get('new-a')!),
        version: 1,
        metadata: annotation.metadata,
      }],
    })
    expect(store.getState().annotations.get('new-a')?.version).toBe(1)
    expect(store.getState().annotations.get('new-a')?.metadata.title).toBe('Edited during save')
    expect(store.peekPendingMutations()).toEqual([{
      type: 'update',
      id: 'new-a',
      version: 1,
      metadata: { ...annotation.metadata, title: 'Edited during save' },
    }])
  })

  it('rebases a delete made during create acknowledgement without resurrecting the item', () => {
    const store = createAnnotationStore({ slideId: 'slide-1' })
    store.load({ version: 0, layers: [layer], annotations: [] })
    store.create({
      id: 'new-a',
      layerId: layer.id,
      geometry: { type: 'point', x: 1, y: 1 },
      style: annotation.style,
      metadata: annotation.metadata,
    })
    const create = store.peekPendingMutations()
    store.beginSave('create-1', create)
    store.delete(['new-a'])

    expect(() => store.acknowledgeSave({
      mutationId: 'create-1',
      operations: create,
      result: {
        mutationId: 'create-1',
        version: 1,
        results: [{ id: 'new-a', operation: 'create', version: 1, deleted: false }],
        purged: 0,
      },
    })).not.toThrow()
    expect(store.getState().annotations.has('new-a')).toBe(false)
    expect(store.peekPendingMutations()).toEqual([{
      type: 'delete',
      id: 'new-a',
      version: 1,
    }])
    const deletion = store.peekPendingMutations()
    store.beginSave('delete-1', deletion)
    expect(() => store.acknowledgeSave({
      mutationId: 'delete-1',
      operations: deletion,
      result: {
        mutationId: 'delete-1',
        version: 2,
        results: [{ id: 'new-a', operation: 'delete', version: 2, deleted: true }],
        purged: 0,
      },
    })).not.toThrow()
    expect(store.getState()).toMatchObject({
      version: 2,
      pendingMutations: [],
      autosaveStatus: 'idle',
      overlayError: null,
    })
    expect(store.getState().annotations.has('new-a')).toBe(false)
  })

  it('keeps a newer optimistic restore active when the earlier delete is acknowledged', () => {
    const store = createAnnotationStore({ slideId: 'slide-1' })
    store.load({ version: 1, layers: [layer], annotations: [annotation] })
    store.delete(['a-1'])
    const deletion = store.peekPendingMutations()
    store.beginSave('delete-1', deletion)
    const deletedRecord = structuredClone(store.getState().annotations.get('a-1')!)
    store.restore(['a-1'])

    store.acknowledgeSave({
      mutationId: 'delete-1',
      operations: deletion,
      result: {
        mutationId: 'delete-1',
        version: 2,
        results: [{ id: 'a-1', operation: 'delete', version: 2, deleted: true }],
        purged: 0,
      },
      records: [{ ...deletedRecord, version: 2 }],
    })
    expect(store.getState().annotations.get('a-1')).toMatchObject({
      version: 2,
      deletedAt: null,
    })
    expect(store.peekPendingMutations()).toEqual([{
      type: 'restore',
      id: 'a-1',
      version: 2,
    }])
  })

  it('creates durable undo and redo compensations across acknowledgement boundaries', () => {
    const store = createAnnotationStore({ slideId: 'slide-1' })
    store.load({ version: 1, layers: [layer], annotations: [annotation] })
    store.update('a-1', {
      metadata: { ...annotation.metadata, classification: 'Stroma' },
    })
    const first = store.peekPendingMutations()
    store.beginSave('m-1', first)
    store.acknowledgeSave({
      mutationId: 'm-1',
      operations: first,
      result: {
        mutationId: 'm-1',
        version: 2,
        results: [{ id: 'a-1', operation: 'update', version: 2, deleted: false }],
        purged: 0,
      },
    })

    store.undo()
    expect(store.peekPendingMutations()).toEqual([{
      type: 'update',
      id: 'a-1',
      version: 2,
      metadata: annotation.metadata,
    }])
    const undo = store.peekPendingMutations()
    store.beginSave('m-2', undo)
    store.acknowledgeSave({
      mutationId: 'm-2',
      operations: undo,
      result: {
        mutationId: 'm-2',
        version: 3,
        results: [{ id: 'a-1', operation: 'update', version: 3, deleted: false }],
        purged: 0,
      },
    })
    store.redo()
    expect(store.peekPendingMutations()).toEqual([{
      type: 'update',
      id: 'a-1',
      version: 3,
      metadata: { ...annotation.metadata, classification: 'Stroma' },
    }])
  })

  it('keeps failed batches pending and exposes safe immutable snapshots with change identity', () => {
    const store = createAnnotationStore({ slideId: 'slide-1' })
    store.load({ version: 1, layers: [layer], annotations: [annotation] })
    const stable = store.getState()
    expect(store.getState()).toBe(stable)
    expect(() => stable.annotations.clear()).toThrow(/read-only/i)
    expect(() => stable.selection.add('external')).toThrow(/read-only/i)
    expect(store.getState().annotations).toHaveLength(1)
    expect(store.getState().selection.has('external')).toBe(false)

    store.update('a-1', { geometry: { type: 'point', x: 7, y: 8 } })
    expect(store.getState()).not.toBe(stable)
    const operations = store.peekPendingMutations()
    store.beginSave('failed', operations)
    expect(store.getState().pendingMutations).toEqual([])
    store.failSave('failed')
    expect(store.peekPendingMutations()).toEqual(operations)
  })

  it('enforces the active cap on restore without changing state or pending work', () => {
    const deleted = { ...structuredClone(annotation), id: 'deleted', deletedAt: '2026-07-26' }
    const store = createAnnotationStore({ slideId: 'slide-1', maxAnnotations: 1 })
    store.load({ version: 1, layers: [layer], annotations: [annotation, deleted] })
    expect(() => store.restore(['deleted'])).toThrow(/annotation limit/i)
    expect(store.getState().annotations.get('deleted')?.deletedAt).toBe('2026-07-26')
    expect(store.getState().pendingMutations).toEqual([])
  })

  it('applies multi-fragment booleans atomically and leaves state untouched on preflight failure', async () => {
    const first = {
      ...structuredClone(annotation),
      id: 'poly-1',
      geometry: {
        type: 'polygon' as const,
        points: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }],
      },
    }
    const second = {
      ...structuredClone(first),
      id: 'poly-2',
      geometry: {
        type: 'polygon' as const,
        points: [{ x: 4, y: 0 }, { x: 6, y: 0 }, { x: 6, y: 10 }, { x: 4, y: 10 }],
      },
    }
    const fragments = [
      first.geometry,
      { ...first.geometry, points: first.geometry.points.map((point) => ({ ...point, x: point.x + 20 })) },
      { ...first.geometry, points: first.geometry.points.map((point) => ({ ...point, x: point.x + 40 })) },
    ]
    const booleanClient = { run: vi.fn(async () => fragments) }
    const ids = ['new-1', 'new-2']
    const limited = createAnnotationStore({
      slideId: 'slide-1',
      maxAnnotations: 2,
      booleanClient,
      idFactory: () => ids.shift() ?? 'unexpected',
    })
    limited.load({ version: 1, layers: [layer], annotations: [first, second] })
    const before = limited.getState()
    await expect(limited.boolean('split', ['poly-1', 'poly-2'])).rejects.toThrow(
      /annotation limit/i,
    )
    expect(limited.getState().annotations).toEqual(before.annotations)
    expect(limited.getState().pendingMutations).toEqual([])
  })

  it('rejects oversized boolean results and over-50 mutation transactions atomically', async () => {
    const first = {
      ...structuredClone(annotation),
      id: 'poly-1',
      geometry: {
        type: 'polygon' as const,
        points: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }],
      },
    }
    const second = {
      ...structuredClone(first),
      id: 'poly-2',
      geometry: {
        type: 'polygon' as const,
        points: [{ x: 4, y: 0 }, { x: 6, y: 0 }, { x: 6, y: 10 }, { x: 4, y: 10 }],
      },
    }
    const assertAtomicRejection = async (
      results: Array<typeof first.geometry>,
      message: RegExp,
    ) => {
      let id = 0
      const store = createAnnotationStore({
        slideId: 'slide-1',
        maxAnnotations: 100,
        booleanClient: { run: vi.fn(async () => results) },
        idFactory: () => `generated-${id++}`,
      })
      store.load({ version: 1, layers: [layer], annotations: [first, second] })
      const before = store.getState()

      await expect(store.boolean('split', ['poly-1', 'poly-2'])).rejects.toThrow(message)
      expect(store.getState().annotations).toEqual(before.annotations)
      expect(store.getState().pendingMutations).toEqual([])
      expect(store.canUndo()).toBe(false)
      expect(store.canRedo()).toBe(false)
    }

    const fiftyFragments = Array.from({ length: 50 }, (_, index) => ({
      type: 'polygon' as const,
      points: first.geometry.points.map((point) => ({ ...point, x: point.x + index * 20 })),
    }))
    await assertAtomicRejection(fiftyFragments, /50|operation|transaction/i)

    const oversized = [{
      type: 'polygon' as const,
      points: Array.from({ length: 8_193 }, (_, index) => ({
        x: index % 100,
        y: Math.floor(index / 100),
      })),
    }]
    await assertAtomicRejection(oversized, /8,192|vertices/i)
  })
})
