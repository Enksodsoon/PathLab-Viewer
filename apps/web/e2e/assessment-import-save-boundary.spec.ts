import { expect, test } from '@playwright/test'

test('import waits for save acknowledgment and preserves the title after reload', async ({ page }) => {
  test.setTimeout(90_000)
  const question = { id: 'source-q', type: 'short-answer', prompt: 'Synthetic import question', points: '1', required: true }
  let server = { id: 'import-qa', status: 'draft', revision: 1, title: 'Original title', document: { title: 'Original title', items: [] as typeof question[], settings: {} } }
  let imports = 0
  let patchStarted = false
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/drafts/import-qa/import-questions')) {
      imports++
      expect(request.postDataJSON().expectedRevision).toBe(2)
      server = { ...server, revision: 3, document: { ...server.document, items: [question] } }
      return route.fulfill({ json: server })
    }
    if (path.endsWith('/drafts/import-qa')) {
      if (request.method() === 'PATCH') {
        expect(request.headers()['if-match']).toBe('1')
        patchStarted = true
        await pending
        server = { ...server, revision: 2, document: request.postDataJSON().document }
      }
      return route.fulfill({ json: server })
    }
    if (path.endsWith('/drafts')) return route.fulfill({ json: { items: [{ ...server, id: 'source-qa', title: 'Source', document: { ...server.document, items: [question] } }] } })
    if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('/admin/assessments/import-qa')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible({ timeout: 45_000 })
  const name = page.getByRole('textbox', { name: 'Assessment name', exact: true })
  await name.fill('Locally edited title')
  await page.getByRole('button', { name: 'Import questions', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Import assessment' })
  await dialog.getByRole('combobox', { name: 'Source assessment' }).selectOption('source-qa')
  await dialog.getByRole('button', { name: 'Select all shown' }).click()
  const submit = dialog.getByRole('button', { name: 'Import selected (1)' })
  await expect.poll(() => patchStarted).toBe(true)
  await expect(submit).toBeDisabled()
  await expect(dialog.getByText('Save your changes before importing questions.')).toBeVisible()
  expect(imports).toBe(0)
  release()
  await expect(submit).toBeEnabled()
  await submit.click()
  await expect(dialog).toHaveCount(0)
  await expect(name).toHaveValue('Locally edited title')
  await expect(page.getByRole('group', { name: 'Question 1' })).toBeVisible()
  await page.reload()
  await expect(name).toHaveValue('Locally edited title')
  await expect(page.getByRole('group', { name: 'Question 1' })).toBeVisible()
  expect(imports).toBe(1)
})
