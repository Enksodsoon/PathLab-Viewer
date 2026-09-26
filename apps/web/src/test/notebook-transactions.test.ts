import { afterEach, expect, it, vi } from 'vitest'

import { saveEntry } from '../classroom/notebook'
import { clearLocalStudy } from '../study/localStore'
import { clearStudyPackDraft } from '../study/authoringStore'

afterEach(() => vi.unstubAllGlobals())

const writes: Array<[string, () => Promise<void>]> = [
  ['notebook', () => saveEntry({ id: 'one', sessionId: 'session', slideId: 'slide', slideName: 'Slide', note: '', createdAt: '' })],
  ['Study context', () => clearLocalStudy('course')],
  ['Study draft', clearStudyPackDraft],
]
it.each(writes)('acknowledges %s writes only after commit and rejects a late abort', async (_name, write) => {
  const requests: Record<string, { result?: unknown; onsuccess?: () => void }> = {}
  function request(name: string, result: unknown) {
    const value = { result, onsuccess: undefined as (() => void) | undefined }
    requests[name] = value
    queueMicrotask(() => value.onsuccess?.())
    return value
  }
  const store = {
    index: () => ({ getAll: () => request('all', []), count: () => request('count', 0) }),
    get: () => request('get', undefined),
    put: () => request('write', 'one'),
    add: () => request('write', 'one'),
    delete: () => request('write', undefined),
  }
  const transaction = {
    objectStore: () => store, error: null,
    oncomplete: undefined as (() => void) | undefined,
    onabort: undefined as (() => void) | undefined,
    onerror: undefined as (() => void) | undefined,
  }
  const database = { transaction: () => transaction, close: vi.fn() }
  vi.stubGlobal('indexedDB', {
    open: () => {
      const value = { result: database, onsuccess: undefined as (() => void) | undefined }
      queueMicrotask(() => value.onsuccess?.())
      return value
    },
  })
  let acknowledged = false
  const saving = write()
  const result = saving.then(() => { acknowledged = true }, (error: unknown) => error)
  await vi.waitFor(() => expect(requests.write).toBeDefined())
  expect(acknowledged).toBe(false)
  transaction.onabort?.()
  expect(await result).toBeInstanceOf(Error)
  expect(database.close).toHaveBeenCalledOnce()
})
