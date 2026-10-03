import { expect, test } from '@playwright/test'

test('denied local recovery writes do not produce unhandled errors during a successful server save', async ({ page }) => {
  test.setTimeout(90_000)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(() => {
    Object.defineProperty(window, 'indexedDB', { configurable: true, get() { throw new DOMException('Synthetic recovery denied', 'SecurityError') } })
  })
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/drafts/write-denial-qa')) {
      const document = request.method() === 'PATCH' ? request.postDataJSON().document : { title: 'Synthetic write denial', items: [], settings: {} }
      return route.fulfill({ json: { id: 'write-denial-qa', status: 'draft', revision: request.method() === 'PATCH' ? 2 : 1, document } })
    }
    if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('/admin/assessments/write-denial-qa')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  await page.getByRole('textbox', { name: 'Assessment name', exact: true }).fill('Server acknowledged edit')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  await expect(page.getByText('Local recovery unavailable. Keep this tab open until changes are saved.', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('failed save retains equal-revision local edits across reload and resaves when the server recovers', async ({ page }) => {
  test.setTimeout(90_000)
  const initial = { id: 'local-recovery-qa', revision: 1, status: 'draft', title: 'Synthetic recovery QA', document: { title: 'Synthetic recovery QA', items: [], settings: {} } }
  let server = initial
  let saves = 0
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  const revisions: string[] = []
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/drafts/local-recovery-qa')) {
      if (request.method() === 'PATCH') {
        saves++
        revisions.push(request.headers()['if-match'])
        if (saves === 1) return route.fulfill({ status: 503, json: { detail: { code: 'SYNTHETIC_UNAVAILABLE' } } })
        await pending
        server = { ...server, revision: 2, document: request.postDataJSON().document }
      }
      return route.fulfill({ json: server })
    }
    if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('/admin/assessments/local-recovery-qa')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  const name = page.getByRole('textbox', { name: 'Assessment name', exact: true })
  await name.fill('Locally retained edit')
  await expect(page.getByText('Conflict: reload or duplicate', { exact: true })).toBeVisible()
  await expect.poll(() => page.evaluate(() => new Promise<string | null>((resolve, reject) => {
    const open = indexedDB.open('pathlab-assessment', 1)
    open.onerror = () => reject(open.error)
    open.onsuccess = () => {
      const database = open.result
      const read = database.transaction('drafts').objectStore('drafts').get('local-recovery-qa')
      read.onerror = () => { database.close(); reject(read.error) }
      read.onsuccess = () => { database.close(); resolve(read.result?.document.title ?? null) }
    }
  }))).toBe('Locally retained edit')
  await page.reload()
  await expect(name).toHaveValue('Locally retained edit')
  await expect.poll(() => saves).toBe(2)
  expect(revisions).toEqual(['1', '1'])
  await expect(page.getByText('Saving…', { exact: true })).toBeVisible()
  release()
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  expect(server.document.title).toBe('Locally retained edit')
  await page.reload()
  await expect(name).toHaveValue('Locally retained edit')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  expect(saves).toBe(2)
})
