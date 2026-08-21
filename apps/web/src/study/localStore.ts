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
  return new Promise((resolve, reject) => {
    const tx = database.transaction(STORE, mode)
    const request = operation(tx.objectStore(STORE))
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
    tx.oncomplete = () => database.close()
    tx.onerror = () => reject(tx.error)
  })
}

export async function loadLocalStudy(courseId: string): Promise<LocalDocument> {
  const stored = await transaction<LocalDocument | undefined>('readonly', (store) => store.get(courseId))
  const expired = stored?.expiresAt && Date.parse(stored.expiresAt) <= Date.now()
  if (!stored || expired || stored.revoked) {
    if (stored) await clearLocalStudy(courseId)
    return { courseId, records: [], outbox: [], expiresAt: null, revoked: false }
  }
  return {
    ...stored,
    records: stored.records.slice(-MAX_RECORDS),
    outbox: stored.outbox.slice(-MAX_OUTBOX),
  }
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
  const document = await loadLocalStudy(courseId)
  const records = [...document.records, record].slice(-MAX_RECORDS)
  await saveLocalStudy({ ...document, expiresAt, records })
  return records
}

export async function clearLocalStudy(courseId?: string): Promise<void> {
  if (courseId) {
    await transaction('readwrite', (store) => store.delete(courseId))
    return
  }
  await transaction('readwrite', (store) => store.clear())
}

export async function verifyCachePersistence(courseId: string): Promise<boolean> {
  const existing = await loadLocalStudy(courseId)
  await saveLocalStudy(existing)
  const loaded = await loadLocalStudy(courseId)
  return loaded.courseId === courseId && loaded.records.length === existing.records.length
}
