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
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE, 'readwrite')
    transaction.objectStore(STORE).put(draft)
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error)
  })
  database.close()
}

export async function readCachedAssessmentDraft(id: string): Promise<AssessmentDraft | null> {
  const database = await openDatabase()
  const value = await new Promise<AssessmentDraft | undefined>((resolve, reject) => {
    const request = database.transaction(STORE).objectStore(STORE).get(id)
    request.onsuccess = () => resolve(request.result as AssessmentDraft | undefined)
    request.onerror = () => reject(request.error)
  })
  database.close()
  return value ?? null
}
