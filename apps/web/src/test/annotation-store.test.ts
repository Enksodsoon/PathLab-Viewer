import { describe, expect, it, vi } from 'vitest'

import { AnnotationAutosave } from '../annotations/autosave'
import { createAnnotationStore } from '../annotations/store'
import { MAX_BATCH_OPERATIONS } from '../annotations/types'
import type {
  AnnotationLayer,
  AnnotationMutation,
  AnnotationRecord,
} from '../annotations/types'

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

  it('keeps locked layers immutable across create, edit, duplicate, delete, and restore', () => {
    const lockedLayer = { ...layer, locked: true }
    const lockedRecord = structuredClone(annotation)
    const store = createAnnotationStore({
      slideId: 'slide-1',
      idFactory: () => 'locked-copy',
    })
    store.load({ version: 1, layers: [lockedLayer], annotations: [lockedRecord] })

    store.create({
      id: 'locked-create',
      layerId: lockedLayer.id,
      geometry: { type: 'point', x: 5, y: 5 },
      style: lockedRecord.style,
      metadata: lockedRecord.metadata,
    })
    store.update(lockedRecord.id, {
      metadata: { ...lockedRecord.metadata, title: 'Changed' },
    })
    store.delete([lockedRecord.id])

    expect(store.duplicate([lockedRecord.id])).toEqual([])
    expect(store.getState().annotations.has('locked-create')).toBe(false)
    expect(store.getState().annotations.get(lockedRecord.id)).toEqual(lockedRecord)
    expect(store.getState().pendingMutations).toEqual([])

    store.load({
      version: 1,
      layers: [lockedLayer],
      annotations: [{ ...lockedRecord, deletedAt: '2026-07-26T01:00:00Z' }],
    })
    store.restore([lockedRecord.id])
    expect(store.getState().annotations.get(lockedRecord.id)?.deletedAt).not.toBeNull()
    expect(store.getState().pendingMutations).toEqual([])
  })

  it('copies, pastes, duplicates, zooms, and publishes import/export previews', () => {
    const store = createAnnotationStore({
      slideId: 'slide-1',
      idFactory: () => 'a-copy',
    })
    store.load({ version: 1, layers: [layer], annotations: [annotation] })
    expect(store.canPaste()).toBe(false)
    store.select(['a-1'])
    store.copy()
    expect(store.canPaste()).toBe(true)
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
    expect(store.getState().recoveryMutations).toEqual(sent)
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
    expect(store.getState().recoveryMutations).toEqual([])

    store.update('a-1', {
      metadata: { ...annotation.metadata, title: 'Second save' },
    })
    expect(store.peekPendingMutations()[0]).toMatchObject({ version: 2 })
  })

  it('applies brush add and subtract to the selected closed ROI through atomic worker semantics', async () => {
    const worker = {
      run: vi.fn()
        .mockResolvedValueOnce([{
          type: 'polygon',
          points: [
            { x: 0, y: 0 },
            { x: 30, y: 0 },
            { x: 30, y: 30 },
            { x: 0, y: 30 },
          ],
        }])
        .mockResolvedValueOnce([{
          type: 'polygon',
          points: [
            { x: 0, y: 0 },
            { x: 10, y: 0 },
            { x: 10, y: 10 },
            { x: 0, y: 10 },
          ],
        }]),
    }
    const roi: AnnotationRecord = {
      ...annotation,
      geometry: {
        type: 'polygon',
        points: [
          { x: 0, y: 0 },
          { x: 20, y: 0 },
          { x: 20, y: 20 },
          { x: 0, y: 20 },
        ],
      },
      bounds: { minX: 0, minY: 0, maxX: 20, maxY: 20 },
    }
    const brush = {
      type: 'polygon' as const,
      points: [
        { x: 10, y: 10 },
        { x: 30, y: 10 },
        { x: 30, y: 30 },
        { x: 10, y: 30 },
      ],
    }
    const store = createAnnotationStore({
      slideId: 'slide-1',
      booleanClient: worker,
    })
    store.load({ version: 1, layers: [layer], annotations: [roi] })

    await store.brush('add', 'a-1', brush)
    expect(worker.run).toHaveBeenNthCalledWith(1, 'union', [roi.geometry, brush])
    expect(store.getState().annotations.get('a-1')?.bounds).toEqual({
      minX: 0,
      minY: 0,
      maxX: 30,
      maxY: 30,
    })

    const save = store.peekPendingMutations()
    store.beginSave('brush-add', save)
    store.acknowledgeSave({
      mutationId: 'brush-add',
      operations: save,
      result: {
        mutationId: 'brush-add',
        version: 2,
        results: [{ id: 'a-1', operation: 'update', version: 2, deleted: false }],
        purged: 0,
      },
    })
    await store.brush('subtract', 'a-1', brush)
    expect(worker.run).toHaveBeenNthCalledWith(
      2,
      'subtract',
      [expect.objectContaining({ type: 'polygon' }), brush],
    )
    expect(store.getState().annotations.get('a-1')?.bounds).toEqual({
      minX: 0,
      minY: 0,
      maxX: 10,
      maxY: 10,
    })
  })

  it('serializes rapid same-target brush strokes, composes one pending update, and recovers after failure', async () => {
    let releaseFirst!: () => void
    const firstGate = new Promise<void>((resolve) => {
      releaseFirst = resolve
    })
    const added = {
      type: 'polygon' as const,
      points: [
        { x: 0, y: 0 },
        { x: 40, y: 0 },
        { x: 40, y: 40 },
        { x: 0, y: 40 },
      ],
    }
    const subtracted = {
      type: 'polygon' as const,
      points: [
        { x: 5, y: 5 },
        { x: 30, y: 5 },
        { x: 30, y: 30 },
        { x: 5, y: 30 },
      ],
    }
    const recovered = {
      type: 'polygon' as const,
      points: [
        { x: 0, y: 0 },
        { x: 45, y: 0 },
        { x: 45, y: 45 },
        { x: 0, y: 45 },
      ],
    }
    const worker = {
      run: vi.fn()
        .mockImplementationOnce(async () => {
          await firstGate
          return [added]
        })
        .mockImplementationOnce(async (_operation, geometries) => {
          expect(geometries[0]).toEqual(added)
          return [subtracted]
        })
        .mockRejectedValueOnce(new Error('worker unavailable'))
        .mockImplementationOnce(async (_operation, geometries) => {
          expect(geometries[0]).toEqual(subtracted)
          return [recovered]
        }),
    }
    const roi = {
      ...structuredClone(annotation),
      geometry: {
        type: 'polygon' as const,
        points: [
          { x: 0, y: 0 },
          { x: 20, y: 0 },
          { x: 20, y: 20 },
          { x: 0, y: 20 },
        ],
      },
      bounds: { minX: 0, minY: 0, maxX: 20, maxY: 20 },
    }
    const stroke = {
      type: 'polygon' as const,
      points: [
        { x: 10, y: 10 },
        { x: 25, y: 10 },
        { x: 25, y: 25 },
        { x: 10, y: 25 },
      ],
    }
    const store = createAnnotationStore({ slideId: 'slide-1', booleanClient: worker })
    store.load({ version: 1, layers: [layer], annotations: [roi] })

    const first = store.brush('add', roi.id, stroke)
    const second = store.brush('subtract', roi.id, stroke)
    expect(worker.run).toHaveBeenCalledOnce()
    releaseFirst()
    await Promise.all([first, second])

    expect(worker.run).toHaveBeenCalledTimes(2)
    expect(store.peekPendingMutations()).toEqual([
      expect.objectContaining({
        type: 'update',
        id: roi.id,
        geometry: subtracted,
      }),
    ])
    expect(store.getState().pendingMutationBatches).toEqual([{
      atomic: true,
      operations: [
        expect.objectContaining({
          type: 'update',
          id: roi.id,
          geometry: subtracted,
        }),
      ],
    }])
    await expect(store.brush('add', roi.id, stroke)).rejects.toThrow('worker unavailable')
    expect(store.getState().annotations.get(roi.id)?.geometry).toEqual(subtracted)
    expect(store.peekPendingMutations()).toHaveLength(1)

    await expect(store.brush('add', roi.id, stroke)).resolves.toEqual([roi.id])
    expect(store.getState().annotations.get(roi.id)?.geometry).toEqual(recovered)
    expect(store.peekPendingMutations()).toEqual([
      expect.objectContaining({
        type: 'update',
        id: roi.id,
        geometry: recovered,
      }),
    ])
  })

  it('composes rapid multi-fragment brush groups without duplicate targets and retries them whole', async () => {
    let releaseFirst!: () => void
    const firstGate = new Promise<void>((resolve) => {
      releaseFirst = resolve
    })
    const roi = {
      ...structuredClone(annotation),
      id: 'rapid-roi',
      geometry: {
        type: 'polygon' as const,
        points: [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 20 }, { x: 0, y: 20 }],
      },
    }
    const grown = {
      ...roi.geometry,
      points: roi.geometry.points.map((point) => ({ ...point, x: point.x + 1 })),
    }
    const latest = {
      ...roi.geometry,
      points: roi.geometry.points.map((point) => ({ ...point, x: point.x + 2 })),
    }
    const fragmentOne = {
      ...roi.geometry,
      points: roi.geometry.points.map((point) => ({ ...point, x: point.x + 30 })),
    }
    const fragmentTwo = {
      ...roi.geometry,
      points: roi.geometry.points.map((point) => ({ ...point, x: point.x + 60 })),
    }
    const worker = {
      run: vi.fn()
        .mockImplementationOnce(async () => {
          await firstGate
          return [grown, fragmentOne]
        })
        .mockResolvedValueOnce([latest, fragmentTwo]),
    }
    const ids = ['fragment-one', 'fragment-two']
    const store = createAnnotationStore({
      slideId: 'slide-1',
      booleanClient: worker,
      idFactory: () => ids.shift() ?? 'unexpected',
    })
    store.load({ version: 1, layers: [layer], annotations: [roi] })

    const first = store.brush('add', roi.id, roi.geometry)
    const second = store.brush('subtract', roi.id, roi.geometry)
    releaseFirst()
    await Promise.all([first, second])

    const [batch] = store.getState().pendingMutationBatches
    expect(batch.atomic).toBe(true)
    expect(batch.operations).toHaveLength(3)
    expect(batch.operations.map((operation) => (
      operation.type === 'create' ? operation.item.id : operation.id
    ))).toEqual([roi.id, 'fragment-one', 'fragment-two'])
    expect(batch.operations[0]).toMatchObject({ type: 'update', geometry: latest })

    expect(() => store.beginSave('rapid-brush', batch.operations)).not.toThrow()
    expect(store.getState().pendingMutationBatches).toEqual([])
    store.failSave('rapid-brush')
    expect(store.getState().pendingMutationBatches).toEqual([batch])
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

  it('structurally shares unchanged annotation state and cached visibility results', () => {
    const other = {
      ...structuredClone(annotation),
      id: 'a-2',
      metadata: { ...annotation.metadata, title: 'Unchanged finding' },
    }
    const store = createAnnotationStore({ slideId: 'slide-1' })
    store.load({ version: 1, layers: [layer], annotations: [annotation, other] })

    const loaded = store.getState()
    const visible = store.visibleAnnotations()
    expect(store.visibleAnnotations()).toBe(visible)

    store.setTool('select')
    const afterTool = store.getState()
    expect(afterTool.annotations).toBe(loaded.annotations)
    expect(afterTool.annotations.get(other.id)).toBe(loaded.annotations.get(other.id))
    expect(store.visibleAnnotations()).toBe(visible)

    store.select([annotation.id])
    const afterSelection = store.getState()
    expect(afterSelection.annotations).toBe(loaded.annotations)
    expect(store.visibleAnnotations()).toBe(visible)

    store.update(annotation.id, {
      metadata: { ...annotation.metadata, title: 'Changed finding' },
    })
    const afterUpdate = store.getState()
    expect(afterUpdate.annotations).not.toBe(loaded.annotations)
    expect(afterUpdate.annotations.get(other.id)).toBe(loaded.annotations.get(other.id))
    expect(loaded.annotations.get(annotation.id)?.metadata.title).not.toBe('Changed finding')
    expect(store.visibleAnnotations()).not.toBe(visible)
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

  it('rejects a boolean while unrelated work is pending without changing either edit', async () => {
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
    const unrelated = { ...structuredClone(annotation), id: 'other' }
    const booleanClient = { run: vi.fn(async () => [first.geometry]) }
    const store = createAnnotationStore({ slideId: 'slide-1', booleanClient })
    store.load({ version: 1, layers: [layer], annotations: [first, second, unrelated] })
    store.update('other', {
      metadata: { ...unrelated.metadata, title: 'Unsaved unrelated edit' },
    })
    const before = store.getState()
    const pendingBefore = store.peekPendingMutations()

    await expect(store.boolean('split', ['poly-1', 'poly-2'])).rejects.toMatchObject({
      name: 'AnnotationBooleanAtomicityError',
      code: 'ANNOTATION_BOOLEAN_QUEUE_NOT_CLEAN',
    })
    expect(booleanClient.run).not.toHaveBeenCalled()
    expect(store.getState().annotations).toEqual(before.annotations)
    expect(store.peekPendingMutations()).toEqual(pendingBefore)
    expect(store.canUndo()).toBe(true)
  })

  it('rejects an under-8,192-vertex boolean whose complete request exceeds 256 KiB', async () => {
    const first = {
      ...structuredClone(annotation),
      id: 'poly-1',
      geometry: {
        type: 'polygon' as const,
        points: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }],
      },
    }
    const second = { ...structuredClone(first), id: 'poly-2' }
    const largeResult = {
      type: 'polygon' as const,
      points: Array.from({ length: 8_191 }, (_, index) => ({
        x: index + 0.1234567890123456,
        y: index + 0.9876543210987654,
      })),
    }
    const store = createAnnotationStore({
      slideId: 'slide-1',
      booleanClient: { run: vi.fn(async () => [largeResult]) },
    })
    store.load({ version: 1, layers: [layer], annotations: [first, second] })
    const before = store.getState()

    await expect(store.boolean('split', ['poly-1', 'poly-2'])).rejects.toMatchObject({
      name: 'AnnotationBooleanAtomicityError',
      code: 'ANNOTATION_BOOLEAN_REQUEST_TOO_LARGE',
    })
    expect(store.getState().annotations).toEqual(before.annotations)
    expect(store.getState().pendingMutations).toEqual([])
    expect(store.canUndo()).toBe(false)
    expect(store.canRedo()).toBe(false)
  })

  it('sends a valid boolean mutation group as exactly one backend batch', async () => {
    const first = {
      ...structuredClone(annotation),
      id: 'poly-1',
      geometry: {
        type: 'polygon' as const,
        points: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }],
      },
    }
    const second = { ...structuredClone(first), id: 'poly-2' }
    const results = [
      first.geometry,
      {
        ...first.geometry,
        points: first.geometry.points.map((point) => ({ ...point, x: point.x + 20 })),
      },
    ]
    const generatedIds = ['00000000-0000-4000-8000-000000000020']
    const store = createAnnotationStore({
      slideId: 'slide-1',
      booleanClient: { run: vi.fn(async () => results) },
      idFactory: () => generatedIds.shift() ?? 'unexpected',
    })
    store.load({ version: 1, layers: [layer], annotations: [first, second] })
    await store.boolean('split', ['poly-1', 'poly-2'])
    const group = store.peekPendingMutations()
    const save = vi.fn(async (
      mutationId: string,
      _baseVersion: number,
      operations: typeof group,
    ) => ({
      mutationId,
      version: 2,
      results: operations.map((operation) => ({
        id: operation.type === 'create' ? operation.item.id : operation.id,
        operation: operation.type,
        version: 2,
        deleted: operation.type === 'delete',
      })),
      purged: 0,
    }))
    const autosave = new AnnotationAutosave({
      transport: { save },
      baseVersion: 1,
      idFactory: () => '00000000-0000-4000-8000-000000000030',
      ...store.autosaveHooks(),
    })
    for (const operation of group) autosave.enqueue(operation)

    await autosave.flush()

    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0][2]).toEqual(group)
    expect(store.getState().pendingMutations).toEqual([])
    expect(autosave.snapshot()).toMatchObject({ status: 'saved', dirtyCount: 0 })
  })

  it('keeps a multi-fragment brush atomic when unrelated work is already queued', async () => {
    const roi = {
      ...structuredClone(annotation),
      id: 'brush-roi',
      geometry: {
        type: 'polygon' as const,
        points: [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 20 }, { x: 0, y: 20 }],
      },
    }
    const unrelated = { ...structuredClone(annotation), id: 'unrelated' }
    const fragment = {
      ...roi.geometry,
      points: roi.geometry.points.map((point) => ({ ...point, x: point.x + 30 })),
    }
    const generatedIds = ['brush-fragment']
    const store = createAnnotationStore({
      slideId: 'slide-1',
      booleanClient: { run: vi.fn(async () => [roi.geometry, fragment]) },
      idFactory: () => generatedIds.shift() ?? 'unexpected',
    })
    store.load({ version: 1, layers: [layer], annotations: [roi, unrelated] })
    store.update(unrelated.id, {
      metadata: { ...unrelated.metadata, title: 'Queued first' },
    })
    await store.brush('subtract', roi.id, roi.geometry)

    const batches = store.getState().pendingMutationBatches
    expect(batches).toHaveLength(2)
    expect(batches[0]).toMatchObject({
      atomic: false,
      operations: [expect.objectContaining({ type: 'update', id: unrelated.id })],
    })
    expect(batches[1]).toMatchObject({
      atomic: true,
      operations: [
        expect.objectContaining({ type: 'update', id: roi.id }),
        expect.objectContaining({
          type: 'create',
          item: expect.objectContaining({ id: 'brush-fragment' }),
        }),
      ],
    })

    const sent: AnnotationMutation[][] = []
    let version = 1
    const autosave = new AnnotationAutosave({
      baseVersion: 1,
      transport: {
        save: vi.fn(async (
          mutationId: string,
          _baseVersion: number,
          operations: AnnotationMutation[],
        ) => {
          sent.push(structuredClone(operations))
          version += 1
          return {
            mutationId,
            version,
            results: operations.map((operation) => ({
              id: operation.type === 'create' ? operation.item.id : operation.id,
              operation: operation.type,
              version,
              deleted: operation.type === 'delete',
            })),
            purged: 0,
          }
        }),
      },
      ...store.autosaveHooks(),
    })
    autosave.replacePendingBatches(batches)
    await autosave.flush()

    expect(sent).toEqual([
      batches[0].operations,
      batches[1].operations,
    ])
    expect(store.getState().pendingMutations).toEqual([])
  })

  it('rejects brush groups over count and byte limits before changing local state', async () => {
    const roi = {
      ...structuredClone(annotation),
      id: 'brush-roi',
      geometry: {
        type: 'polygon' as const,
        points: [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 20 }, { x: 0, y: 20 }],
      },
    }
    const stroke = structuredClone(roi.geometry)
    const assertRejectedWithoutMutation = async (
      results: Array<typeof roi.geometry>,
      expected: RegExp,
    ) => {
      let nextId = 0
      const store = createAnnotationStore({
        slideId: 'slide-1',
        maxAnnotations: 100,
        booleanClient: { run: vi.fn(async () => results) },
        idFactory: () => `fragment-${nextId++}`,
      })
      store.load({ version: 1, layers: [layer], annotations: [roi] })
      const before = store.getState()
      await expect(store.brush('subtract', roi.id, stroke)).rejects.toThrow(expected)
      expect(store.getState().annotations).toEqual(before.annotations)
      expect(store.getState().pendingMutations).toEqual([])
      expect(store.canUndo()).toBe(false)
    }

    const fiftyOneFragments = Array.from({ length: 51 }, (_, index) => ({
      ...roi.geometry,
      points: roi.geometry.points.map((point) => ({ ...point, x: point.x + index * 30 })),
    }))
    let acceptedId = 0
    const boundaryStore = createAnnotationStore({
      slideId: 'slide-1',
      maxAnnotations: 100,
      booleanClient: {
        run: vi.fn(async () => fiftyOneFragments.slice(0, MAX_BATCH_OPERATIONS)),
      },
      idFactory: () => `accepted-fragment-${acceptedId++}`,
    })
    boundaryStore.load({ version: 1, layers: [layer], annotations: [roi] })
    await expect(boundaryStore.brush('subtract', roi.id, stroke)).resolves.toHaveLength(
      MAX_BATCH_OPERATIONS,
    )
    expect(boundaryStore.getState().pendingMutationBatches).toEqual([{
      atomic: true,
      operations: expect.any(Array),
    }])
    expect(boundaryStore.getState().pendingMutationBatches[0].operations).toHaveLength(
      MAX_BATCH_OPERATIONS,
    )

    await assertRejectedWithoutMutation(fiftyOneFragments, /50|operation|transaction/i)

    const tooManyBytes = [{
      type: 'polygon' as const,
      points: Array.from({ length: 8_191 }, (_, index) => ({
        x: index + 0.1234567890123456,
        y: index + 0.9876543210987654,
      })),
    }]
    await assertRejectedWithoutMutation(tooManyBytes, /256|request|large/i)
  })
})
