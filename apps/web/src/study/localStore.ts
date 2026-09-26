import type { LocalStudyRecord } from './types'

const DATABASE = 'pathlab-study-local-v1'
const STORE = 'course-context'
const MAX_RECORDS = 256
const MAX_OUTBOX = 200

type LocalDocument = {
  courseId: string
  records: LocalStudyRecord[]
  outbox: Array<{ taskId: string; submission: Record<string, string | number> }>
  expiresAt: string | null
  revoked: boolean
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function transaction<T>(
  mode: IDBTransactionMode,
  operation: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const database = await openDatabase()
  return new Promise<T>((resolve, reject) => {
    const tx = database.transaction(STORE, mode)
    const request = operation(tx.objectStore(STORE))
    request.onerror = () => reject(request.error)
    tx.oncomplete = () => resolve(request.result)
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error ?? new Error('Study transaction aborted'))
  }).finally(() => database.close())
}

async function readAndUpdateLocalStudy(
  courseId: string,
  update?: (document: LocalDocument) => LocalDocument,
): Promise<LocalDocument> {
  const database = await openDatabase()
  return new Promise<LocalDocument>((resolve, reject) => {
    // Readwrite transactions on this store serialize across connections/tabs.
    const tx = database.transaction(STORE, 'readwrite')
    const store = tx.objectStore(STORE)
    const request = store.get(courseId)
    let result: LocalDocument
    request.onsuccess = () => {
      try {
        const stored = request.result as LocalDocument | undefined
        const expired = stored?.expiresAt && Date.parse(stored.expiresAt) <= Date.now()
        const invalid = !stored || expired || stored.revoked
        const current: LocalDocument = invalid
          ? { courseId, records: [], outbox: [], expiresAt: null, revoked: false }
          : stored
        const next = update ? update(current) : current
        result = { ...next, records: next.records.slice(-MAX_RECORDS), outbox: next.outbox.slice(-MAX_OUTBOX) }
        if (update) store.put(result, courseId)
        else if (stored && invalid) store.delete(courseId)
      } catch (error) {
        tx.abort()
        reject(error)
      }
    }
    request.onerror = () => reject(request.error)
    tx.oncomplete = () => resolve(result)
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error ?? new Error('Study transaction aborted'))
  }).finally(() => database.close())
}

export async function loadLocalStudy(courseId: string): Promise<LocalDocument> {
  return readAndUpdateLocalStudy(courseId)
}

export async function saveLocalStudy(document: LocalDocument): Promise<void> {
  const bounded: LocalDocument = {
    ...document,
    records: document.records.slice(-MAX_RECORDS),
    outbox: document.outbox.slice(-MAX_OUTBOX),
  }
  await transaction('readwrite', (store) => store.put(bounded, document.courseId))
}

export async function appendLocalRecord(
  courseId: string,
  record: LocalStudyRecord,
  expiresAt: string | null,
): Promise<LocalStudyRecord[]> {
  const document = await readAndUpdateLocalStudy(courseId, (current) => ({
    ...current, expiresAt, records: [...current.records, record],
  }))
  return document.records
}

export async function clearLocalStudy(courseId?: string): Promise<void> {
  if (courseId) {
    await transaction('readwrite', (store) => store.delete(courseId))
    return
  }
  await transaction('readwrite', (store) => store.clear())
}

export async function verifyCachePersistence(courseId: string): Promise<boolean> {
  const existing = await readAndUpdateLocalStudy(courseId, (current) => current)
  const loaded = await loadLocalStudy(courseId)
  return loaded.courseId === courseId && loaded.records.length >= existing.records.length
}
