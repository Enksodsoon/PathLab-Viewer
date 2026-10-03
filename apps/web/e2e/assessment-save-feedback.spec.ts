import { expect, test } from '@playwright/test'

test('keyboard retry preserves edits and waits for acknowledgment before reporting saved', async ({ page }, testInfo) => {
  if (testInfo.project.name === 'mobile-chromium') await page.setViewportSize({ width: 320, height: 568 })
  let server = { id: 'retry-save-qa', revision: 1, status: 'draft', document: { title: 'Synthetic retry QA', items: [], settings: {} } }
  let attempts = 0
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  const revisions: string[] = []
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/drafts/retry-save-qa')) {
      if (request.method() === 'PATCH') {
        attempts++; revisions.push(request.headers()['if-match'])
        if (attempts === 1) return route.fulfill({ status: 503, json: { detail: { code: 'SYNTHETIC_UNAVAILABLE' } } })
        await pending
        server = { ...server, revision: 2, document: request.postDataJSON().document }
      }
      return route.fulfill({ json: server })
    }
    if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('/admin/assessments/retry-save-qa')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  const name = page.getByRole('textbox', { name: 'Assessment name', exact: true })
  await name.fill('Retained retry edit')
  await expect(page.getByText('Changes not saved. Try again.', { exact: true })).toBeVisible()
  await expect(page.getByText('Conflict: reload or duplicate', { exact: true })).toHaveCount(0)
  const retry = page.getByRole('button', { name: 'Retry save', exact: true })
  const retryBounds = await retry.boundingBox()
  expect(retryBounds).not.toBeNull()
  expect(retryBounds!.x).toBeGreaterThanOrEqual(0)
  expect(retryBounds!.x + retryBounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  await retry.focus(); await page.keyboard.press('Enter')
  await expect(retry).toHaveCount(0)
  await expect(page.locator('.assessment-save-state')).toBeFocused()
  await expect.poll(() => attempts).toBe(2)
  await expect(page.getByText('Saving…', { exact: true })).toBeVisible()
  await expect(page.getByText('All changes saved', { exact: true })).toHaveCount(0)
  await expect(name).toHaveValue('Retained retry edit')
  expect(revisions).toEqual(['1', '1'])
  release()
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  await page.reload()
  await expect(name).toHaveValue('Retained retry edit')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  expect(attempts).toBe(2)
})

for (const [status, message] of [
  [403, 'Changes not saved. You do not have permission to save this draft.'],
  [409, 'Conflict: reload or duplicate'],
] as const) {
  test(`HTTP${status} retains edits and keeps unavailable retry out of the 320px layout`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 })
    let attempts = 0
    await page.route('**/api/**', async route => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (path.endsWith('/drafts/denial-save-qa')) {
        if (request.method() === 'PATCH') {
          attempts++
          return route.fulfill({ status, json: { detail: { code: 'SYNTHETIC_DENIAL' } } })
        }
        return route.fulfill({ json: { id: 'denial-save-qa', status: 'draft', revision: 1, document: { title: 'Synthetic denial QA', items: [], settings: {} } } })
      }
      if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
      return route.fulfill({ status: 404, json: {} })
    })
    await page.goto('/admin/assessments/denial-save-qa')
    await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
    const name = page.getByRole('textbox', { name: 'Assessment name', exact: true })
    await name.fill('Retained denied edit')
    const notice = page.getByText(message, { exact: true })
    await expect(notice).toBeVisible()
    await expect(name).toHaveValue('Retained denied edit')
    await expect(page.getByRole('button', { name: 'Retry save', exact: true })).toHaveCount(0)
    await expect(page.getByText('All changes saved', { exact: true })).toHaveCount(0)
    const bounds = await notice.boundingBox()
    expect(bounds).not.toBeNull()
    expect(bounds!.x).toBeGreaterThanOrEqual(0)
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(320)
    expect(attempts).toBe(1)
  })
}
