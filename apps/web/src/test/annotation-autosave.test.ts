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
})
