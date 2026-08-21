import type { StudyPackDefinition } from './types'

const DATABASE = 'pathlab-study-authoring-v1'
const STORE = 'drafts'
const MAX_DRAFT_BYTES = 2 * 1024 * 1024

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function operation<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>) {
  const connection = await database()
  return new Promise<T>((resolve, reject) => {
    const transaction = connection.transaction(STORE, mode)
    const request = action(transaction.objectStore(STORE))
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
    transaction.oncomplete = () => connection.close()
    transaction.onerror = () => reject(transaction.error)
  })
}

export async function loadStudyPackDraft(): Promise<StudyPackDefinition | null> {
  return (await operation<StudyPackDefinition | undefined>('readonly', (store) => store.get('current'))) ?? null
}

export async function saveStudyPackDraft(draft: StudyPackDefinition): Promise<void> {
  if (new Blob([JSON.stringify(draft)]).size > MAX_DRAFT_BYTES) throw new Error('Draft exceeds 2 MiB.')
  await operation('readwrite', (store) => store.put(draft, 'current'))
}

export async function clearStudyPackDraft(): Promise<void> {
  await operation('readwrite', (store) => store.delete('current'))
}
