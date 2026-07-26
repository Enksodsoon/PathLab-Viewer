import { describe, expect, it } from 'vitest'

import {
  AnnotationDraftRepository,
  DraftCapacityError,
  type AnnotationDraft,
  type DraftStorage,
} from '../annotations/drafts'

class MemoryDraftStorage implements DraftStorage {
  readonly records = new Map<string, AnnotationDraft>()

  async list(): Promise<AnnotationDraft[]> {
    return [...this.records.values()]
  }

  async put(draft: AnnotationDraft): Promise<void> {
    this.records.set(draft.slideId, structuredClone(draft))
  }

  async delete(slideId: string): Promise<void> {
    this.records.delete(slideId)
  }

  async get(slideId: string): Promise<AnnotationDraft | null> {
    return structuredClone(this.records.get(slideId) ?? null)
  }
}

const draft = (
  slideId: string,
  savedAt: number,
  dirty: boolean,
  payload = 'small',
): Omit<AnnotationDraft, 'byteSize'> => ({
  schema: 'pathlab-annotation-draft/v1',
  slideId,
  baseVersion: 1,
  mutations: [],
  snapshot: payload,
  savedAt,
  dirty,
})

describe('durable annotation drafts', () => {
  it('preserves dirty drafts beyond seven days until acknowledgement or discard', async () => {
    const storage = new MemoryDraftStorage()
    const now = Date.UTC(2026, 6, 26)
    const repository = new AnnotationDraftRepository({ storage, now: () => now })
    await repository.save(draft('dirty', now - 10 * 86_400_000, true))
    await repository.save(draft('clean', now - 10 * 86_400_000, false))

    await repository.prune()
    expect(await repository.load('dirty')).not.toBeNull()
    expect(await repository.load('clean')).toBeNull()
    await repository.acknowledge('dirty')
    expect(await repository.load('dirty')).toBeNull()

    await repository.save(draft('discard', now, true))
    await repository.discard('discard')
    expect(await repository.load('discard')).toBeNull()
  })

  it('enforces a total five MiB budget by evicting clean oldest data, never dirty data', async () => {
    const storage = new MemoryDraftStorage()
    const repository = new AnnotationDraftRepository({
      storage,
      now: () => 10_000,
      maxBytes: 1_000,
    })
    await repository.save(draft('clean', 1, false, 'x'.repeat(300)))
    await repository.save(draft('dirty', 2, true, 'y'.repeat(300)))
    await repository.save(draft('new', 3, true, 'z'.repeat(300)))

    expect(await repository.load('clean')).toBeNull()
    expect(await repository.load('dirty')).not.toBeNull()
    expect(await repository.load('new')).not.toBeNull()
    await expect(repository.save(draft('overflow', 4, true, 'q'.repeat(900))))
      .rejects.toBeInstanceOf(DraftCapacityError)
    expect(await repository.load('dirty')).not.toBeNull()
  })

  it('counts every persisted draft field, including byteSize metadata, against capacity', async () => {
    const storage = new MemoryDraftStorage()
    const repository = new AnnotationDraftRepository({ storage, maxBytes: 10_000 })
    const saved = await repository.save(draft('all-fields', 123, true, 'payload'))
    expect(saved.byteSize).toBe(
      new TextEncoder().encode(JSON.stringify(saved)).byteLength,
    )
  })

  it('serializes concurrent repositories before making a shared capacity decision', async () => {
    const storage = new MemoryDraftStorage()
    const first = new AnnotationDraftRepository({ storage, maxBytes: 500 })
    const second = new AnnotationDraftRepository({ storage, maxBytes: 500 })

    const results = await Promise.allSettled([
      first.save(draft('first', 1, true, 'x'.repeat(250))),
      second.save(draft('second', 2, true, 'y'.repeat(250))),
    ])

    expect(results.filter((result) => result.status === 'fulfilled')).toHaveLength(1)
    expect(results.filter((result) => result.status === 'rejected')).toHaveLength(1)
    expect(storage.records).toHaveLength(1)
  })
})
