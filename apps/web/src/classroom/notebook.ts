export interface NotebookEntry {
  id: string
  sessionId: string
  slideId: string
  slideName: string
  note: string
  createdAt: string
  image?: Blob
}

export interface StorageCapability {
  indexedDb: boolean
  usage?: number
  quota?: number
  persisted?: boolean
}

const DATABASE_NAME = 'pathlab-classroom-notebook'
const STORE_NAME = 'entries'
const SCHEMA_VERSION = 1
export const MAX_NOTEBOOK_ENTRIES = 100

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!('indexedDB' in window)) {
      reject(new Error('Private notebook storage is unavailable in this browser'))
      return
    }
    const request = indexedDB.open(DATABASE_NAME, SCHEMA_VERSION)
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        const store = database.createObjectStore(STORE_NAME, { keyPath: 'id' })
        store.createIndex('sessionId', 'sessionId')
      }
    }
    request.onerror = () => reject(request.error ?? new Error('Notebook storage failed'))
    request.onsuccess = () => resolve(request.result)
  })
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('Notebook storage failed'))
  })
}

export async function storageCapability(): Promise<StorageCapability> {
  if (!('indexedDB' in window)) return { indexedDb: false }
  const estimate: StorageEstimate = await navigator.storage?.estimate?.().catch(() => ({})) ?? {}
  const persisted = await navigator.storage?.persist?.().catch(() => false)
  return {
    indexedDb: true,
    usage: estimate.usage,
    quota: estimate.quota,
    persisted,
  }
}

export async function listEntries(sessionId: string): Promise<NotebookEntry[]> {
  const database = await openDatabase()
  try {
    const transaction = database.transaction(STORE_NAME, 'readonly')
    const values = await requestResult(
      transaction.objectStore(STORE_NAME).index('sessionId').getAll(sessionId),
    ) as NotebookEntry[]
    return values.sort((left, right) => left.createdAt.localeCompare(right.createdAt))
  } finally {
    database.close()
  }
}

export async function saveEntry(entry: NotebookEntry): Promise<void> {
  const existing = await listEntries(entry.sessionId)
  if (existing.length >= MAX_NOTEBOOK_ENTRIES) {
    throw new Error(`Notebook limit reached (${MAX_NOTEBOOK_ENTRIES} entries)`)
  }
  const database = await openDatabase()
  try {
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    await requestResult(transaction.objectStore(STORE_NAME).add(entry))
  } catch (error) {
    if (error instanceof DOMException && error.name === 'QuotaExceededError') {
      throw new Error('Browser storage is full. Export the notebook before adding more images.')
    }
    throw error
  } finally {
    database.close()
  }
}

export async function deleteSessionEntries(sessionId: string): Promise<void> {
  const database = await openDatabase()
  try {
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    const index = transaction.objectStore(STORE_NAME).index('sessionId')
    await new Promise<void>((resolve, reject) => {
      const cursor = index.openKeyCursor(IDBKeyRange.only(sessionId))
      cursor.onerror = () => reject(cursor.error ?? new Error('Notebook deletion failed'))
      cursor.onsuccess = () => {
        const current = cursor.result
        if (!current) {
          resolve()
          return
        }
        transaction.objectStore(STORE_NAME).delete(current.primaryKey)
        current.continue()
      }
    })
  } finally {
    database.close()
  }
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character] ?? character)
}

function blobDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error ?? new Error('Notebook export failed'))
    reader.onload = () => resolve(String(reader.result))
    reader.readAsDataURL(blob)
  })
}

export async function notebookHtml(
  title: string,
  entries: NotebookEntry[],
): Promise<string> {
  const sections = await Promise.all(entries.map(async (entry) => {
    const image = entry.image
      ? `<img alt="Captured tissue field" src="${await blobDataUrl(entry.image)}">`
      : ''
    return `<article><h2>${escapeHtml(entry.slideName)}</h2><time>${escapeHtml(entry.createdAt)}</time>${image}<p>${escapeHtml(entry.note)}</p></article>`
  }))
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>${escapeHtml(title)}</title><style>body{font:16px system-ui;max-width:900px;margin:auto;padding:32px;color:#17211d}article{border-top:1px solid #cad3ce;padding:24px 0}img{display:block;max-width:100%;height:auto;margin:12px 0;object-fit:contain}time{color:#53615a}p{white-space:pre-wrap}</style></head><body><h1>${escapeHtml(title)}</h1>${sections.join('')}</body></html>`
}

export async function exportNotebook(title: string, entries: NotebookEntry[]): Promise<Blob> {
  return new Blob([await notebookHtml(title, entries)], { type: 'text/html;charset=utf-8' })
}
