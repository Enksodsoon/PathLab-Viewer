import { expect, test } from '@playwright/test'

const draft = { id: 'dialog-qa', revision: 1, status: 'draft', title: 'Synthetic dialog QA', document: { title: 'Synthetic dialog QA', items: [], settings: {} } }
const navigation = { capabilities: { classroom: false, study: false, assessment: true }, counts: { all: 0, unfiled: 0, shared: 0, processing: 0, failed: 0, trash: 0 }, folders: [], collections: [], savedViews: [], storage: { usedBytes: 0, usableBytes: 1000, effectiveCapacityBytes: 1000 } }

for (const { trigger, label, close } of [
  { trigger: 'Assignment preview', label: 'Learner preview', close: 'Close preview' },
  { trigger: 'Publish', label: 'Publish assessment', close: 'Close publish settings' },
  { trigger: 'Import questions', label: 'Import assessment', close: 'Close import' },
]) {
  for (const viewport of [{ width: 320, height: 568 }, { width: 760, height: 650 }, { width: 844, height: 390 }, { width: 1584, height: 992 }]) {
    test(`${label} at ${viewport.width}x${viewport.height} traps focus, dismisses with Escape and returns to its trigger`, async ({ page }) => {
      let unexpectedWrites = 0
      await page.route('**/api/**', async (route) => {
        const request = route.request()
        const path = new URL(request.url()).pathname
        if (path.endsWith('/preview')) return route.fulfill({ json: { learnerManifest: draft.document, checksum: 'qa' } })
        if (request.method() !== 'GET') { unexpectedWrites++; return route.fulfill({ status: 500, json: { detail: { code: 'UNEXPECTED_QA_WRITE' } } }) }
        if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
        if (path === '/api/v2/admin/library/navigation') return route.fulfill({ json: navigation })
        if (path.endsWith('/drafts/dialog-qa')) return route.fulfill({ json: draft })
        if (path.endsWith('/drafts')) return route.fulfill({ json: { items: [draft], total: 1 } })
        if (path.endsWith('/classes')) return route.fulfill({ json: { items: [] } })
        return route.fulfill({ status: 404, json: { detail: { code: 'QA_ROUTE_NOT_FOUND' } } })
      })
      await page.setViewportSize(viewport)
      await page.goto('/admin/assessments/dialog-qa')
      await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
      const opener = page.getByRole('button', { name: trigger, exact: true })
      await opener.click()
      const dialog = page.getByRole('dialog', { name: label, exact: true })
      const closeButton = dialog.getByRole('button', { name: close, exact: true })
      await expect(dialog).toBeVisible()
      await expect(closeButton).toBeFocused()
      const lastButton = dialog.getByRole('button').last()
      await lastButton.focus()
      await page.keyboard.press('Tab')
      await expect.poll(() => dialog.evaluate(node => node.contains(document.activeElement))).toBe(true)
      await closeButton.focus()
      await page.keyboard.press('Shift+Tab')
      await expect.poll(() => dialog.evaluate(node => node.contains(document.activeElement))).toBe(true)
      await expect.poll(() => dialog.evaluate(node => { const bounds = node.getBoundingClientRect(); return bounds.x >= 0 && bounds.y >= 0 && bounds.right <= innerWidth + 1 && bounds.bottom <= innerHeight + 1 })).toBe(true)
      await page.keyboard.press('Escape')
      await expect(dialog).toHaveCount(0)
      await expect(opener).toBeFocused()
      await opener.click()
      await closeButton.click()
      await expect(dialog).toHaveCount(0)
      await expect(opener).toBeFocused()
      expect(unexpectedWrites).toBe(0)
    })
  }
}

test('disabled publication keeps collection and release expanders reachable by keyboard', async ({ page }) => {
  let saveAttempts = 0
  let publicationAttempts = 0
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() === 'PATCH' && path.endsWith('/drafts/dialog-qa')) {
      saveAttempts++
      return route.fulfill({ status: 503, json: { detail: { code: 'SYNTHETIC_SAVE_FAILURE' } } })
    }
    if (request.method() !== 'GET') {
      publicationAttempts++
      return route.fulfill({ status: 500, json: { detail: { code: 'UNEXPECTED_QA_WRITE' } } })
    }
    if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    if (path === '/api/v2/admin/library/navigation') return route.fulfill({ json: navigation })
    if (path.endsWith('/drafts/dialog-qa')) return route.fulfill({ json: draft })
    if (path.endsWith('/classes')) return route.fulfill({ json: { items: [] } })
    return route.fulfill({ status: 404, json: { detail: { code: 'QA_ROUTE_NOT_FOUND' } } })
  })
  await page.goto('/admin/assessments/dialog-qa')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: 'Assessment name', exact: true }).fill('Unsaved synthetic draft')
  await expect(page.getByText('Changes not saved. Try again.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Publish assessment', exact: true })
  await expect(dialog.getByRole('button', { name: 'Publish assignment', exact: true })).toBeDisabled()
  await dialog.getByRole('button', { name: 'Close publish settings' }).focus()
  await page.keyboard.press('Shift+Tab')
  await expect(dialog.locator('summary').filter({ hasText: 'Learner release' })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(dialog.locator('summary').filter({ hasText: 'Collection settings' })).toBeFocused()
  expect(saveAttempts).toBe(1)
  expect(publicationAttempts).toBe(0)
})
