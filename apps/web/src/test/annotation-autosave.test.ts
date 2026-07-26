import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AnnotationAutosave,
  type AnnotationAutosaveTransport,
} from '../annotations/autosave'
import { AnnotationApiError } from '../annotations/api'
import type { AnnotationMutation } from '../annotations/types'

const mutation = (index: number): AnnotationMutation => ({
  type: 'delete',
  id: `annotation-${index}`,
  version: 1,
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

afterEach(() => {
  vi.useRealTimers()
})

describe('annotation autosave', () => {
  it('debounces 750 ms, sends batches of 50, and flushes all queued operations', async () => {
    vi.useFakeTimers()
    const sent: AnnotationMutation[][] = []
    let version = 3
    const transport: AnnotationAutosaveTransport = {
      save: vi.fn(async (_mutationId, baseVersion, operations) => {
        expect(baseVersion).toBe(version)
        sent.push(operations)
        version += 1
        return { mutationId: 'server-mutation', version, results: [], purged: 0 }
      }),
    }
    const autosave = new AnnotationAutosave({
      transport,
      baseVersion: 3,
      idFactory: () => 'client-mutation',
    })
    for (let index = 0; index < 105; index += 1) autosave.enqueue(mutation(index))

    await vi.advanceTimersByTimeAsync(749)
    expect(transport.save).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    await autosave.flush()

    expect(sent.map((batch) => batch.length)).toEqual([50, 50, 5])
    expect(autosave.snapshot()).toMatchObject({
      status: 'saved',
      dirtyCount: 0,
      version: 6,
    })
  })

  it('backs off after a network failure without claiming a save', async () => {
    vi.useFakeTimers()
    const save = vi.fn()
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce({
        mutationId: 'm',
        version: 2,
        results: [],
        purged: 0,
      })
    const autosave = new AnnotationAutosave({
      transport: { save },
      baseVersion: 1,
      retryDelaysMs: [1_000],
    })
    autosave.enqueue(mutation(1))

    await vi.advanceTimersByTimeAsync(750)
    expect(autosave.snapshot().status).toBe('retrying')
    expect(autosave.snapshot().dirtyCount).toBe(1)
    await vi.advanceTimersByTimeAsync(999)
    expect(save).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    await autosave.flush()
    expect(autosave.snapshot().status).toBe('saved')
  })

  it('stops on 409 and exposes reload or save-as-duplicate conflict choices', async () => {
    vi.useFakeTimers()
    const onReload = vi.fn(async () => 9)
    const onDuplicate = vi.fn(async (items: readonly AnnotationMutation[]) => {
      expect(items).toHaveLength(1)
      return 10
    })
    const autosave = new AnnotationAutosave({
      transport: {
        save: vi.fn(async () => {
          throw new AnnotationApiError(409, 'ANNOTATION_CONFLICT', { currentVersion: 9 })
        }),
      },
      baseVersion: 1,
      onReload,
      onSaveAsDuplicate: onDuplicate,
    })
    autosave.enqueue(mutation(1))
    await vi.advanceTimersByTimeAsync(750)

    expect(autosave.snapshot()).toMatchObject({
      status: 'conflict',
      conflict: { currentVersion: 9, choices: ['reload', 'save-as-duplicate'] },
      dirtyCount: 1,
    })
    await autosave.resolveConflict('save-as-duplicate')
    expect(onDuplicate).toHaveBeenCalledOnce()
    expect(autosave.snapshot()).toMatchObject({ status: 'saved', version: 10, dirtyCount: 0 })
  })

  it('coalesces rapid same-target edits into one valid backend operation', async () => {
    vi.useFakeTimers()
    const save = vi.fn(async (
      mutationId: string,
      _baseVersion: number,
      operations: AnnotationMutation[],
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
    const autosave = new AnnotationAutosave({ transport: { save }, baseVersion: 1 })
    autosave.enqueue({
      type: 'update',
      id: 'a-1',
      version: 1,
      geometry: { type: 'point', x: 1, y: 1 },
    })
    autosave.enqueue({
      type: 'update',
      id: 'a-1',
      version: 1,
      metadata: { title: 'Latest', classification: '', tags: [], notes: '' },
    })
    autosave.enqueue({
      type: 'update',
      id: 'a-1',
      version: 1,
      geometry: { type: 'point', x: 9, y: 9 },
    })

    await autosave.flush()
    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0][2]).toEqual([{
      type: 'update',
      id: 'a-1',
      version: 1,
      geometry: { type: 'point', x: 9, y: 9 },
      metadata: { title: 'Latest', classification: '', tags: [], notes: '' },
    }])
  })

  it('reduces a dependent restore-update-delete chain to no backend operation', async () => {
    const save = vi.fn()
    const autosave = new AnnotationAutosave({ transport: { save }, baseVersion: 1 })
    autosave.enqueue({ type: 'restore', id: 'a-1', version: 1 })
    autosave.enqueue({
      type: 'update',
      id: 'a-1',
      version: 1,
      metadata: { title: 'Transient', classification: '', tags: [], notes: '' },
    })
    autosave.enqueue({ type: 'delete', id: 'a-1', version: 1 })

    await autosave.flush()
    expect(save).not.toHaveBeenCalled()
    expect(autosave.snapshot()).toMatchObject({ status: 'idle', dirtyCount: 0 })
  })

  it('isolates replacement operations from an older in-flight acknowledgement', async () => {
    vi.useFakeTimers()
    const first = deferred<{
      mutationId: string
      version: number
      results: []
      purged: number
    }>()
    const calls: AnnotationMutation[][] = []
    const save = vi.fn(async (
      mutationId: string,
      _baseVersion: number,
      operations: AnnotationMutation[],
    ) => {
      calls.push(structuredClone(operations))
      if (calls.length === 1) return first.promise
      return { mutationId, version: 3, results: [], purged: 0 }
    })
    const autosave = new AnnotationAutosave({ transport: { save }, baseVersion: 1 })
    autosave.enqueue(mutation(1))
    await vi.advanceTimersByTimeAsync(750)
    expect(save).toHaveBeenCalledOnce()

    autosave.replacePending([mutation(2)])
    first.resolve({ mutationId: 'first', version: 2, results: [], purged: 0 })
    await autosave.flush()

    expect(calls).toEqual([[mutation(1)], [mutation(2)]])
    expect(autosave.snapshot()).toMatchObject({ dirtyCount: 0, version: 3 })
  })

  it('counts the complete request envelope and rejects a single oversized operation locally', async () => {
    const save = vi.fn()
    const autosave = new AnnotationAutosave({
      transport: { save },
      baseVersion: 1,
      idFactory: () => '00000000-0000-4000-8000-000000000001',
    })
    autosave.enqueue({
      type: 'update',
      id: 'a-1',
      version: 1,
      metadata: {
        title: '',
        classification: '',
        tags: [],
        notes: 'x'.repeat(256 * 1024),
      },
    })

    await autosave.flush()
    expect(save).not.toHaveBeenCalled()
    expect(autosave.snapshot()).toMatchObject({
      status: 'error',
      dirtyCount: 1,
      error: 'ANNOTATION_REQUEST_TOO_LARGE',
    })
  })

  it('publishes start and atomic acknowledgement hooks without clearing before success', async () => {
    const pending = deferred<{
      mutationId: string
      version: number
      results: []
      purged: number
    }>()
    const starts = vi.fn()
    const acknowledgements = vi.fn()
    const autosave = new AnnotationAutosave({
      transport: { save: vi.fn(() => pending.promise) },
      baseVersion: 1,
      idFactory: () => 'stable-mutation-id',
      onBatchStart: starts,
      onAcknowledged: acknowledgements,
    })
    autosave.enqueue(mutation(1))
    const flushing = autosave.flush()
    expect(starts).toHaveBeenCalledWith({
      mutationId: 'stable-mutation-id',
      operations: [mutation(1)],
    })
    expect(autosave.snapshot().dirtyCount).toBe(1)
    pending.resolve({
      mutationId: 'stable-mutation-id',
      version: 2,
      results: [],
      purged: 0,
    })
    await flushing
    expect(acknowledgements).toHaveBeenCalledOnce()
    expect(autosave.snapshot().dirtyCount).toBe(0)
  })
})
