import { expect, test } from '@playwright/test'

test('a committed save with a lost response drains newer edits at the recovered revision and survives reload', async ({ page }, testInfo) => {
  if (testInfo.project.name === 'mobile-chromium') await page.setViewportSize({ width: 320, height: 568 })
  let server = { id: 'lost-ack-qa', revision: 1, status: 'draft', document: { title: 'Synthetic lost acknowledgment QA', items: [], settings: {} } }
  const revisions: string[] = []
  let loseResponse!: () => void
  const pending = new Promise<void>(resolve => { loseResponse = resolve })
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/drafts/lost-ack-qa')) {
      if (request.method() === 'PATCH') {
        const revision = request.headers()['if-match']
        revisions.push(revision)
        if (Number(revision) !== server.revision) return route.fulfill({ status: 409, json: { detail: { code: 'ASSESSMENT_DRAFT_CONFLICT' } } })
        server = { ...server, revision: server.revision + 1, document: request.postDataJSON().document }
        if (revisions.length === 1) {
          await pending
          return route.abort('connectionreset')
        }
      }
      return route.fulfill({ json: server })
    }
    if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('/admin/assessments/lost-ack-qa')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  const name = page.getByRole('textbox', { name: 'Assessment name', exact: true })
  await name.fill('Committed first edit')
  await expect.poll(() => revisions).toEqual(['1'])
  await name.fill('Newer retained edit')
  await expect(page.getByText('All changes saved', { exact: true })).toHaveCount(0)
  loseResponse()
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  expect(revisions).toEqual(['1', '2'])
  expect(server.revision).toBe(3)
  expect(server.document.title).toBe('Newer retained edit')
  await page.reload()
  await expect(name).toHaveValue('Newer retained edit')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  expect(revisions).toEqual(['1', '2'])
})

test('an uncertain save cannot acknowledge or overwrite a different server document', async ({ page }) => {
  let server = { id: 'different-ack-qa', revision: 1, status: 'draft', document: { title: 'Synthetic competing writer QA', items: [], settings: {} } }
  let attempts = 0
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/drafts/different-ack-qa')) {
      if (request.method() === 'PATCH') {
        attempts++
        if (attempts === 1) {
          server = { ...server, revision: 2, document: { ...server.document, title: 'Another writer committed' } }
          return route.abort('connectionreset')
        }
        return route.fulfill({ status: 409, json: { detail: { code: 'ASSESSMENT_DRAFT_CONFLICT' } } })
      }
      return route.fulfill({ json: server })
    }
    if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('/admin/assessments/different-ack-qa')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  const name = page.getByRole('textbox', { name: 'Assessment name', exact: true })
  await name.fill('Local edit kept in this tab')
  await expect(page.getByText('Changes not saved. Try again.', { exact: true })).toBeVisible()
  await expect(name).toHaveValue('Local edit kept in this tab')
  await page.getByRole('button', { name: 'Retry save', exact: true }).click()
  await expect(page.getByText('Conflict: reload or duplicate', { exact: true })).toBeVisible()
  await expect(name).toHaveValue('Local edit kept in this tab')
  await expect(page.getByText('All changes saved', { exact: true })).toHaveCount(0)
  expect(attempts).toBe(2)
  expect(server.document.title).toBe('Another writer committed')
})

test('a denied mutation followed by failed session refresh cannot be reported as a recovered save', async ({ page }) => {
  let reads = 0
  let denied = false
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/drafts/session-ack-qa')) {
      if (request.method() === 'PATCH') {
        denied = true
        return route.fulfill({ status: 403, json: { detail: { code: 'CSRF_INVALID' } } })
      }
      reads++
      return route.fulfill({ json: { id: 'session-ack-qa', revision: denied ? 2 : 1, status: 'draft', document: { title: denied ? 'Denied edit' : 'Synthetic session QA', items: [], settings: {} } } })
    }
    if (path === '/api/v1/auth/session') return route.fulfill({ status: 503, json: { detail: { code: 'SYNTHETIC_REFRESH_UNAVAILABLE' } } })
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('/admin/assessments/session-ack-qa')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  const initialReads = reads
  const name = page.getByRole('textbox', { name: 'Assessment name', exact: true })
  await name.fill('Denied edit')
  await expect(page.getByText('Changes not saved. Try again.', { exact: true })).toBeVisible()
  await expect(name).toHaveValue('Denied edit')
  await expect(page.getByText('All changes saved', { exact: true })).toHaveCount(0)
  expect(denied).toBe(true)
  expect(reads).toBe(initialReads)
})
