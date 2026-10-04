import { expect, test } from '@playwright/test'

const initial = { id: 'save-qa', revision: 1, status: 'draft', title: 'Synthetic save QA', document: { title: 'Synthetic save QA', items: [], settings: {} } }

test.setTimeout(90_000)

test('pending draft save drains the latest edit at the acknowledged revision and survives reload', async ({ page }) => {
  let saved = initial
  const revisions: string[] = []
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/drafts/save-qa')) {
      if (request.method() === 'PATCH') {
        revisions.push(request.headers()['if-match'])
        if (revisions.length === 1) await pending
        if (request.headers()['if-match'] !== String(saved.revision)) return route.fulfill({ status: 409, json: { detail: { code: 'ASSESSMENT_DRAFT_CONFLICT' } } })
        saved = { ...saved, revision: saved.revision + 1, document: request.postDataJSON().document }
      }
      return route.fulfill({ json: saved })
    }
    if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('/admin/assessments/save-qa')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  const name = page.getByRole('textbox', { name: 'Assessment name', exact: true })
  await name.fill('First edit')
  await expect.poll(() => revisions.length).toBe(1)
  await name.fill('Latest edit')
  // Let the second debounce expire while the first server acknowledgment is held.
  await page.waitForTimeout(1100)
  expect(revisions).toEqual(['1'])
  await expect(page.getByText('Saving…', { exact: true })).toBeVisible()
  release()
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  expect(revisions).toEqual(['1', '2'])
  expect(saved.document.title).toBe('Latest edit')
  await page.reload()
  await expect(name).toHaveValue('Latest edit')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  expect(revisions).toEqual(['1', '2'])
})

test('denied local recovery storage still opens the server draft', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'indexedDB', { configurable: true, get() { throw new DOMException('Synthetic storage denial', 'SecurityError') } })
  })
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/drafts/save-qa')) return route.fulfill({ json: initial })
    if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('/admin/assessments/save-qa')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  await expect(page.getByRole('textbox', { name: 'Assessment name', exact: true })).toHaveValue(initial.document.title)
})
