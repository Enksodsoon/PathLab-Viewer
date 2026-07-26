import {
  MAX_DRAFT_AGE_MS,
  MAX_DRAFT_BYTES,
  type AnnotationMutation,
} from './types'

const DATABASE_NAME = 'pathlab-annotation-drafts-v1'
const STORE_NAME = 'drafts'

export interface AnnotationDraft {
  schema: 'pathlab-annotation-draft/v1'
  slideId: string
  baseVersion: number
  mutations: AnnotationMutation[]
  snapshot: unknown
  savedAt: number
  dirty: boolean
  byteSize: number
}

export interface DraftStorage {
  list(): Promise<AnnotationDraft[]>
  get(slideId: string): Promise<AnnotationDraft | null>
  put(draft: AnnotationDraft): Promise<void>
  delete(slideId: string): Promise<void>
}

export class DraftCapacityError extends Error {
  constructor() {
    super('Unsaved annotation drafts exceed the five MiB stability limit')
  }
}

function contentBytes(
  draft: Omit<AnnotationDraft, 'byteSize'>,
): number {
  return new TextEncoder().encode(JSON.stringify({
    mutations: draft.mutations,
    snapshot: draft.snapshot,
  })).byteLength
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('IndexedDB request failed'))
  })
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(
      transaction.error ?? new Error('IndexedDB transaction failed'),
    )
    transaction.onabort = () => reject(
      transaction.error ?? new Error('IndexedDB transaction aborted'),
    )
  })
}

export class IndexedDbDraftStorage implements DraftStorage {
  private databasePromise: Promise<IDBDatabase> | null = null

  private database(): Promise<IDBDatabase> {
    this.databasePromise ??= new Promise((resolve, reject) => {
      const request = indexedDB.open(DATABASE_NAME, 1)
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(STORE_NAME)) {
          request.result.createObjectStore(STORE_NAME, { keyPath: 'slideId' })
        }
      }
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error ?? new Error('IndexedDB open failed'))
      request.onblocked = () => reject(new Error('IndexedDB upgrade is blocked'))
    })
    return this.databasePromise
  }

  async list(): Promise<AnnotationDraft[]> {
    const database = await this.database()
    const transaction = database.transaction(STORE_NAME, 'readonly')
    const completion = transactionDone(transaction)
    const result = await requestResult(transaction.objectStore(STORE_NAME).getAll())
    await completion
    return result as AnnotationDraft[]
  }

  async get(slideId: string): Promise<AnnotationDraft | null> {
    const database = await this.database()
    const transaction = database.transaction(STORE_NAME, 'readonly')
    const completion = transactionDone(transaction)
    const result = await requestResult(transaction.objectStore(STORE_NAME).get(slideId))
    await completion
    return (result as AnnotationDraft | undefined) ?? null
  }

  async put(draft: AnnotationDraft): Promise<void> {
    const database = await this.database()
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    const completion = transactionDone(transaction)
    transaction.objectStore(STORE_NAME).put(structuredClone(draft))
    await completion
  }

  async delete(slideId: string): Promise<void> {
    const database = await this.database()
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    const completion = transactionDone(transaction)
    transaction.objectStore(STORE_NAME).delete(slideId)
    await completion
  }
}

export interface AnnotationDraftRepositoryOptions {
  storage?: DraftStorage
  now?: () => number
  maxBytes?: number
  maxAgeMs?: number
}

export class AnnotationDraftRepository {
  private readonly storage: DraftStorage
  private readonly now: () => number
  private readonly maxBytes: number
  private readonly maxAgeMs: number

  constructor(options: AnnotationDraftRepositoryOptions = {}) {
    this.storage = options.storage ?? new IndexedDbDraftStorage()
    this.now = options.now ?? Date.now
    this.maxBytes = options.maxBytes ?? MAX_DRAFT_BYTES
    this.maxAgeMs = options.maxAgeMs ?? MAX_DRAFT_AGE_MS
  }

  async load(slideId: string): Promise<AnnotationDraft | null> {
    return this.storage.get(slideId)
  }

  async save(draft: Omit<AnnotationDraft, 'byteSize'>): Promise<AnnotationDraft> {
    await this.prune()
    const normalized: AnnotationDraft = {
      ...structuredClone(draft),
      byteSize: contentBytes(draft),
    }
    const existing = (await this.storage.list())
      .filter((candidate) => candidate.slideId !== normalized.slideId)
    let total = normalized.byteSize + existing.reduce(
      (sum, candidate) => sum + candidate.byteSize,
      0,
    )
    const evictable = existing
      .filter((candidate) => !candidate.dirty)
      .sort((left, right) => left.savedAt - right.savedAt)
    for (const candidate of evictable) {
      if (total <= this.maxBytes) break
      await this.storage.delete(candidate.slideId)
      total -= candidate.byteSize
    }
    if (total > this.maxBytes) throw new DraftCapacityError()
    await this.storage.put(normalized)
    return normalized
  }

  async prune(): Promise<void> {
    const cutoff = this.now() - this.maxAgeMs
    const drafts = await this.storage.list()
    await Promise.all(
      drafts
        .filter((draft) => !draft.dirty && draft.savedAt < cutoff)
        .map((draft) => this.storage.delete(draft.slideId)),
    )
  }

  async acknowledge(slideId: string): Promise<void> {
    await this.storage.delete(slideId)
  }

  async discard(slideId: string): Promise<void> {
    await this.storage.delete(slideId)
  }
}
