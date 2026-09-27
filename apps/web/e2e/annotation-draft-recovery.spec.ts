import { expect, test } from '@playwright/test'

test('annotation draft storage retries a failed native IndexedDB open on the same instance', async ({ page }) => {
  await page.goto('/admin')
  const result = await page.evaluate(async () => {
    // @ts-expect-error Vite serves this source module for browser storage checks.
    const { IndexedDbDraftStorage } = await import('/src/annotations/drafts.ts')
    const nativeOpen = indexedDB.open.bind(indexedDB)
    let opens = 0
    indexedDB.open = (...args: Parameters<IDBFactory['open']>) => {
      const request = nativeOpen(...args)
      opens += 1
      if (opens === 1) {
        request.addEventListener('upgradeneeded', () => {
          queueMicrotask(() => request.transaction?.abort())
        })
      }
      return request
    }
    try {
      const storage = new IndexedDbDraftStorage()
      let firstError = ''
      try { await storage.list() } catch (error) {
        firstError = error instanceof DOMException ? error.name : String(error)
      }
      const recovered = await storage.list()
      const retryOpens = opens
      // Release the healthy connection before testing the blocked-open lifecycle.
      ;(await storage.databasePromise).close()
      let lateSuccess: Promise<void> = Promise.resolve()
      indexedDB.open = (...args: Parameters<IDBFactory['open']>) => {
        const request = nativeOpen(...args)
        lateSuccess = new Promise((resolve) => {
          request.addEventListener('success', () => queueMicrotask(resolve))
        })
        // Version1 cannot naturally upgrade an older persisted version. Inject only
        // its blocked notification; the later successful connection is native IDB.
        queueMicrotask(() => request.dispatchEvent(new Event('blocked')))
        return request
      }
      const blocked = new IndexedDbDraftStorage()
      let blockedError = ''
      try { await blocked.list() } catch (error) {
        blockedError = error instanceof Error ? error.message : String(error)
      }
      await lateSuccess
      await new Promise<void>((resolve, reject) => {
        const deletion = indexedDB.deleteDatabase('pathlab-annotation-drafts-v1')
        deletion.onsuccess = () => resolve()
        deletion.onerror = () => reject(deletion.error)
        deletion.onblocked = () => reject(new Error('Late successful connection leaked'))
      })
      return { firstError, opens: retryOpens, recovered, blockedError }
    } finally {
      indexedDB.open = nativeOpen
    }
  })
  expect(result).toEqual({
    firstError: 'AbortError', opens: 2, recovered: [],
    blockedError: 'IndexedDB upgrade is blocked',
  })
})
