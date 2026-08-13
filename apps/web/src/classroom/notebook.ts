export interface NotebookEntry {
  id: string
  sessionId: string
  slideId: string
  slideName: string
  note: string
  createdAt: string
  image?: Blob
  viewport?: { x: number; y: number; zoom: number }
  hasDrawing?: boolean
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
    const coordinate = entry.viewport
      ? `<span>Field ${Math.round(entry.viewport.x * 100)}%, ${Math.round(entry.viewport.y * 100)}% · zoom ${entry.viewport.zoom.toFixed(2)}</span>`
      : ''
    const drawing = entry.hasDrawing ? '<span>Private drawing included</span>' : ''
    return `<article><header><div><p>PathLab field note</p><h2>${escapeHtml(entry.slideName)}</h2></div><time>${escapeHtml(entry.createdAt)}</time></header>${image}<div class="entry-meta">${coordinate}${drawing}</div>${entry.note ? `<p class="note">${escapeHtml(entry.note)}</p>` : ''}</article>`
  }))
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>${escapeHtml(title)}</title><style>:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#211f1b;background:#f4f1ea}*{box-sizing:border-box}body{max-width:980px;margin:0 auto;padding:clamp(22px,5vw,64px);background:#f4f1ea}body>header{margin-bottom:clamp(34px,7vw,72px)}body>header p,article header p{margin:0 0 8px;color:#c75f4d;font-size:12px;font-weight:750;letter-spacing:.12em;text-transform:uppercase}h1,h2{margin:0;font-family:ui-serif,Georgia,serif;font-weight:500;line-height:1.02}h1{font-size:clamp(42px,8vw,76px)}body>header>span{display:block;margin-top:14px;color:#69645c}main{display:grid;gap:28px}article{overflow:hidden;border:1px solid #d9d3c8;border-radius:18px;background:#fffdfa;box-shadow:0 16px 44px rgb(44 38 30 / 8%);break-inside:avoid}article>header{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;padding:22px 24px}h2{font-size:clamp(26px,5vw,38px)}time{color:#777168;font-size:12px}img{display:block;width:100%;height:auto;max-height:70vh;object-fit:contain;background:#090909}.entry-meta{display:flex;flex-wrap:wrap;gap:8px;padding:16px 24px 0}.entry-meta span{padding:6px 9px;border-radius:999px;color:#5d574f;background:#f1ede6;font-size:12px}.note{margin:0;padding:18px 24px 26px;font:17px/1.65 ui-serif,Georgia,serif;white-space:pre-wrap}@media(max-width:560px){body{padding:18px}article>header{display:block}time{display:block;margin-top:10px}.entry-meta,.note,article>header{padding-left:18px;padding-right:18px}}@media print{:root,body{background:#fff}body{max-width:none;padding:0}body>header{margin-bottom:30px}article{border-color:#bbb;box-shadow:none;page-break-inside:avoid}main{gap:20px}}</style></head><body><header><p>Private learning record</p><h1>${escapeHtml(title)}</h1><span>${entries.length} ${entries.length === 1 ? 'field note' : 'field notes'} · created on this device</span></header><main>${sections.join('')}</main></body></html>`
}

export async function exportNotebook(title: string, entries: NotebookEntry[]): Promise<Blob> {
  return new Blob([await notebookHtml(title, entries)], { type: 'text/html;charset=utf-8' })
}

export async function notebookFile(title: string, entries: NotebookEntry[]): Promise<File> {
  return new File(
    [await exportNotebook(title, entries)],
    'pathlab-classroom-notebook.html',
    { type: 'text/html;charset=utf-8' },
  )
}
