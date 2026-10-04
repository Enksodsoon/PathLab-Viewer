import { expect, test } from '@playwright/test'

for (const target of ['folder', 'collection'] as const) {
  for (const viewport of [{ width: 320, height: 740 }, { width: 768, height: 1024 }, { width: 900, height: 420 }, { width: 1584, height: 992 }]) {
    test(`${target} unavailable return preserves authentication at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport)
      await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: viewport.width >= 900 ? 'dark' : 'light' })
      let reads = 0
      await page.route('**/api/**', async (route) => {
        const publicRead = /\/api\/v2\/public\/(folders|collections)\//.test(route.request().url())
        if (publicRead) reads += 1
        await route.fulfill({ status: publicRead ? 404 : 401, contentType: 'application/json', body: JSON.stringify({ detail: { code: publicRead ? 'NOT_FOUND' : 'AUTHENTICATION_REQUIRED' } }) })
      })
      const path = `${target === 'folder' ? '/f/' : '/c/'}unavailable-qa`
      await page.goto(path)
      await expect(page.getByRole('heading', { name: 'This shared library is unavailable' })).toBeVisible()
      const initialReads = reads
      await page.getByRole('button', { name: 'Try again' }).click()
      await expect.poll(() => reads).toBe(initialReads + 1)
      await expect(page.getByRole('heading', { name: 'This shared library is unavailable' })).toBeVisible()
      const exit = page.getByRole('link', { name: 'Go to library' })
      await expect(exit).toBeVisible()
      const box = await exit.boundingBox()
      expect(box).not.toBeNull()
      expect(box!.height).toBeGreaterThanOrEqual(44)
      expect(box!.x).toBeGreaterThanOrEqual(0)
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width)
      await exit.focus()
      await expect(exit).toBeFocused()
      await page.keyboard.press('Enter')
      await expect(page).toHaveURL(/\/admin$/)
      await expect(page.getByRole('heading', { name: 'Administrator sign in' })).toBeVisible()
      await page.reload()
      await expect(page.getByRole('heading', { name: 'Administrator sign in' })).toBeVisible()
    })
  }
}
