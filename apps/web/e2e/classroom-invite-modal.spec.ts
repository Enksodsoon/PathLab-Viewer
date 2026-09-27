import { expect, test } from '@playwright/test'

test('Classroom invitation is modal for keyboard focus and restores its trigger', async ({ page }) => {
  const session = {
    id: 'synthetic-modal', status: 'active', phase: 'preview', publicId: 'synthetic-public',
    joinCode: 'ABC234DEFG', reviewExpiresAt: '2027-01-01T00:00:00Z',
  }
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    let body: unknown = {}
    if (path.endsWith('/auth/session')) body = { csrfToken: 'synthetic-csrf' }
    else if (path.endsWith('/setup/folders')) body = { items: [], nextCursor: null }
    else if (path === '/api/v1/admin/classroom/sessions') body = { sessions: [session] }
    else if (path.endsWith('/participants')) body = { items: [], total: 0, nextCursor: null, rosterVersion: 1 }
    else if (path.endsWith('/synthetic-modal')) body = {
      session, slides: [{ id: 'synthetic-slide', position: 0, displayName: 'Synthetic slide', assetVersion: 'v1', tileSource: '/synthetic.dzi', width: 256, height: 256, tileSize: 256, format: 'png', folderPath: [] }], stateVersion: 1, participantCount: 0, rosterVersion: 1,
      participants: [], pendingQuestions: [], activePins: [], teachingAnnotations: [],
      teacherPointer: null, presenter: { sequence: 0, slideId: null, viewport: null },
      controller: { participantId: null, leaseId: null, controlEpoch: 0, expiresAt: null },
    }
    return route.fulfill({ json: body })
  })
  await page.goto('/admin/classroom')
  await page.getByRole('button', { name: 'Resume classroom ABC234DEFG' }).click()
  const trigger = page.locator('.classroom-join-code')
  await trigger.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Review slides and join class' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Close', exact: true })).toBeFocused()
  // More than the number of dialog controls, including both traversal boundaries.
  for (const key of ['Tab', 'Tab', 'Tab', 'Tab', 'Tab', 'Tab', 'Shift+Tab', 'Shift+Tab']) {
    await page.keyboard.press(key)
    await expect.poll(() => dialog.evaluate((element) => element.contains(document.activeElement) || document.activeElement === document.body)).toBe(true)
  }
  await trigger.evaluate((element) => element.focus())
  await expect(trigger).not.toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(trigger).toBeFocused()
  await trigger.focus()
  await page.keyboard.press('Enter')
  await dialog.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(trigger).toBeFocused()
})
