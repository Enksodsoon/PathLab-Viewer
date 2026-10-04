import { expect, test } from '@playwright/test'

for (const operation of ['write', 'read'] as const) {
  test(`local recovery rejects a ${operation} transaction aborted after request success`, async ({ page }) => {
    await page.route('**/api/**', route => route.fulfill({ status: 404, json: {} }))
    await page.goto('/')
    const result = await page.evaluate(async operation => {
      const modulePath = '/src/assessment/draftCache.ts'
      const { cacheAssessmentDraft, readCachedAssessmentDraft } = await import(modulePath)
      const draft = { id: 'synthetic-transaction-abort', revision: 1, doc: { title: 'Committed control', items: [], settings: {} } }
      await cacheAssessmentDraft(draft)
      const events: string[] = []
      let closes = 0
      const originalClose = IDBDatabase.prototype.close
      IDBDatabase.prototype.close = function () { closes++; return originalClose.call(this) }
      const method = operation === 'write' ? 'put' : 'get'
      const original = IDBObjectStore.prototype[method]
      // Real IndexedDB rollback, injected after a successful request and before commit.
      IDBObjectStore.prototype[method] = function (...args: Parameters<typeof original>) {
        const request = original.apply(this, args)
        request.addEventListener('success', () => { events.push('request success'); this.transaction.abort() })
        this.transaction.addEventListener('abort', () => events.push('transaction abort'))
        return request
      }
      try {
        const work = operation === 'write'
          ? cacheAssessmentDraft({ ...draft, doc: { ...draft.doc, title: 'Rolled back edit' } })
          : readCachedAssessmentDraft(draft.id)
        const outcome = await Promise.race([
          work.then(() => 'resolved', (error: DOMException) => error.name),
          new Promise<string>(resolve => setTimeout(() => resolve('pending'), 1000)),
        ])
        IDBObjectStore.prototype[method] = original
        const operationCloses = closes
        const persisted = await readCachedAssessmentDraft(draft.id)
        return { outcome, events, operationCloses, title: persisted?.doc.title }
      } finally {
        IDBObjectStore.prototype[method] = original
        IDBDatabase.prototype.close = originalClose
      }
    }, operation)
    expect(result.events).toEqual(['request success', 'transaction abort'])
    expect(result.outcome).toBe('AbortError')
    expect(result.operationCloses).toBe(1)
    expect(result.title).toBe('Committed control')
  })
}

test('aborted recovery write warns while server acknowledgment remains successful', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(() => {
    const original = IDBObjectStore.prototype.put
    IDBObjectStore.prototype.put = function (...args) {
      const request = original.apply(this, args)
      request.addEventListener('success', () => this.transaction.abort())
      return request
    }
  })
  let saves = 0
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/drafts/abort-write-qa')) {
      if (request.method() === 'PATCH') saves++
      const document = request.method() === 'PATCH' ? request.postDataJSON().document : { title: 'Synthetic abort QA', items: [], settings: {} }
      return route.fulfill({ json: { id: 'abort-write-qa', status: 'draft', revision: request.method() === 'PATCH' ? 2 : 1, document } })
    }
    if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('/admin/assessments/abort-write-qa')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  await page.getByRole('textbox', { name: 'Assessment name', exact: true }).fill('Server acknowledged despite local abort')
  await expect(page.getByText('Local recovery unavailable. Keep this tab open until changes are saved.', { exact: true })).toBeVisible()
  await expect.poll(() => saves).toBe(1)
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})
