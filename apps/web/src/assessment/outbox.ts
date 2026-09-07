export interface AssessmentOutboxEntry {
  id: string
  publicId: string
  attemptId: string
  itemId: string
  revision: number
  response: Record<string, unknown>
  createdAt: number
}

const DB_NAME = 'pathlab-assessment-outbox-v1'
const STORE = 'responses'

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(STORE)) {
        const store = database.createObjectStore(STORE, { keyPath: 'id' })
        store.createIndex('attempt', 'attemptId')
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export async function enqueueAssessmentResponse(entry: AssessmentOutboxEntry): Promise<void> {
  const database = await openDatabase()
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE, 'readwrite')
    transaction.objectStore(STORE).put(entry)
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error)
  })
  database.close()
}

export async function listAssessmentOutbox(attemptId: string): Promise<AssessmentOutboxEntry[]> {
  const database = await openDatabase()
  const entries = await new Promise<AssessmentOutboxEntry[]>((resolve, reject) => {
    const request = database.transaction(STORE).objectStore(STORE).index('attempt').getAll(attemptId)
    request.onsuccess = () => resolve(request.result as AssessmentOutboxEntry[])
    request.onerror = () => reject(request.error)
  })
  database.close()
  return entries.sort((left, right) => left.createdAt - right.createdAt)
}

export async function removeAssessmentOutbox(ids: string[]): Promise<void> {
  if (ids.length === 0) return
  const database = await openDatabase()
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE, 'readwrite')
    const store = transaction.objectStore(STORE)
    ids.forEach((id) => store.delete(id))
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error)
  })
  database.close()
}
