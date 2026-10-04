import type { AssessmentDraft } from './types'

const DATABASE = 'pathlab-assessment'
const STORE = 'drafts'

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: 'id' })
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export async function cacheAssessmentDraft(draft: AssessmentDraft): Promise<void> {
  const database = await openDatabase()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE, 'readwrite')
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error)
      transaction.onabort = () => reject(transaction.error ?? new DOMException('Local recovery transaction aborted', 'AbortError'))
      transaction.objectStore(STORE).put(draft)
    })
  } finally {
    database.close()
  }
}

export async function readCachedAssessmentDraft(id: string): Promise<AssessmentDraft | null> {
  const database = await openDatabase()
  try {
    const value = await new Promise<AssessmentDraft | undefined>((resolve, reject) => {
      const transaction = database.transaction(STORE)
      let result: AssessmentDraft | undefined
      transaction.oncomplete = () => resolve(result)
      transaction.onerror = () => reject(transaction.error)
      transaction.onabort = () => reject(transaction.error ?? new DOMException('Local recovery transaction aborted', 'AbortError'))
      const request = transaction.objectStore(STORE).get(id)
      request.onsuccess = () => { result = request.result as AssessmentDraft | undefined }
    })
    return value ?? null
  } finally {
    database.close()
  }
}
