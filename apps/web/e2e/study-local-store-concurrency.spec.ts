import { expect, test } from '@playwright/test'

test('Study append and cache verification preserve records across two real browser tabs', async ({ page, context }) => {
  const second = await context.newPage()
  await Promise.all([page.goto('/admin'), second.goto('/admin')])
  await page.evaluate(async () => {
    // @ts-expect-error Vite serves this source module for browser storage checks.
    const store = await import('/src/study/localStore.ts')
    await store.clearLocalStudy()
    await store.saveLocalStudy({ courseId: 'synthetic-concurrent', records: [], outbox: Array.from({ length: 200 }, (_, i) => ({ taskId: `pending-${i}`, submission: { selectedOption: i } })), expiresAt: '2099-01-01T00:00:00Z', revoked: false })
  })
  await Promise.all([page, second].map((tab, tabIndex) => tab.evaluate(async (index) => {
    // @ts-expect-error Vite serves this source module for browser storage checks.
    const store = await import('/src/study/localStore.ts')
    await Promise.all(Array.from({ length: 25 }, (_, i) => store.appendLocalRecord('synthetic-concurrent', { taskId: `tab-${index}-${i}`, completedAt: i, completed: true, features: Array(12).fill(0) }, '2099-01-01T00:00:00Z')))
  }, tabIndex)))
  await page.reload()
  const persisted = await page.evaluate(async () => {
    // @ts-expect-error Vite serves this source module for browser storage checks.
    const store = await import('/src/study/localStore.ts')
    const document = await store.loadLocalStudy('synthetic-concurrent')
    return { count: document.records.length, tasks: document.records.map((item: { taskId: string }) => item.taskId).sort(), outbox: document.outbox.length }
  })
  expect(persisted.count).toBe(50)
  expect(persisted.tasks).toEqual([0, 1].flatMap((index) => Array.from({ length: 25 }, (_, i) => `tab-${index}-${i}`)).sort())
  expect(persisted.outbox).toBe(200)

  await Promise.all([
    page.evaluate(async () => {
      // @ts-expect-error Vite serves this source module for browser storage checks.
      const store = await import('/src/study/localStore.ts')
      await Promise.all(Array.from({ length: 25 }, () => store.verifyCachePersistence('synthetic-concurrent')))
    }),
    second.evaluate(async () => {
      // @ts-expect-error Vite serves this source module for browser storage checks.
      const store = await import('/src/study/localStore.ts')
      await Promise.all(Array.from({ length: 250 }, (_, i) => store.appendLocalRecord('synthetic-concurrent', { taskId: `bounded-${i}`, completedAt: i, completed: true, features: Array(12).fill(0) }, '2099-01-01T00:00:00Z')))
    }),
  ])
  const final = await page.evaluate(async () => {
    // @ts-expect-error Vite serves this source module for browser storage checks.
    const store = await import('/src/study/localStore.ts')
    const document = await store.loadLocalStudy('synthetic-concurrent')
    await store.clearLocalStudy()
    return { count: document.records.length, bounded: document.records.filter((item: { taskId: string }) => item.taskId.startsWith('bounded-')).length, outbox: document.outbox.length }
  })
  expect(final).toEqual({ count: 256, bounded: 250, outbox: 200 })
})


test('Study storage resets expired/revoked contexts and rejects aborted append commits', async ({ page }) => {
  await page.goto('/admin')
  const result = await page.evaluate(async () => {
    // @ts-expect-error Vite serves this source module for browser storage checks.
    const store = await import('/src/study/localStore.ts')
    await store.clearLocalStudy()
    const originalRecord = { taskId: 'original', completedAt: 1, completed: true, features: Array(12).fill(0) }
    const document = { courseId: 'synthetic-abort', records: [originalRecord], outbox: [{ taskId: 'pending', submission: { answer: 1 } }], expiresAt: '2099-01-01T00:00:00Z', revoked: false }
    await store.saveLocalStudy(document)
    const put = IDBObjectStore.prototype.put
    IDBObjectStore.prototype.put = function (...args) {
      const request = put.apply(this, args)
      if (this.name === 'course-context') this.transaction.abort()
      return request
    }
    let aborted = false
    try {
      await store.appendLocalRecord(document.courseId, { ...originalRecord, taskId: 'aborted' }, document.expiresAt)
    } catch {
      aborted = true
    } finally {
      IDBObjectStore.prototype.put = put
    }
    const preserved = await store.loadLocalStudy(document.courseId)
    const resets = []
    for (const state of [{ expiresAt: '2000-01-01T00:00:00Z', revoked: false }, { expiresAt: document.expiresAt, revoked: true }]) {
      await store.saveLocalStudy({ ...document, courseId: 'synthetic-reset', ...state })
      await store.appendLocalRecord('synthetic-reset', { ...originalRecord, taskId: 'fresh' }, document.expiresAt)
      const loaded = await store.loadLocalStudy('synthetic-reset')
      resets.push({ tasks: loaded.records.map((item: { taskId: string }) => item.taskId), outbox: loaded.outbox.length, revoked: loaded.revoked, expiresAt: loaded.expiresAt })
    }
    await store.clearLocalStudy()
    return { aborted, preserved: preserved.records.map((item: { taskId: string }) => item.taskId), outbox: preserved.outbox.length, resets }
  })
  expect(result).toEqual({ aborted: true, preserved: ['original'], outbox: 1, resets: Array(2).fill({ tasks: ['fresh'], outbox: 0, revoked: false, expiresAt: '2099-01-01T00:00:00Z' }) })
})
