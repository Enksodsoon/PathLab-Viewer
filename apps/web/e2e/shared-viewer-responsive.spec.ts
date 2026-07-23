import { expect, test } from '@playwright/test'

const manifest = {
  publicId: 'share-public',
  targetType: 'folder',
  name: 'GI teaching set',
  description: 'Safe teaching slides',
  expiresAt: null,
  slides: [
    {
      position: 0,
      displayName: 'Colon adenocarcinoma',
      organSite: 'Colon',
      stain: 'H&E',
      diagnosis: 'Adenocarcinoma',
      tags: ['Teaching'],
      teachingNote: '',
      thumbnailUrl: '/thumb/0',
      tileSource: '/tiles/public-1/slide.dzi',
      scale: null,
    },
    {
      position: 1,
      displayName: 'Normal colon',
      organSite: 'Colon',
      stain: 'H&E',
      diagnosis: 'Normal',
      tags: [],
      teachingNote: '',
      thumbnailUrl: '/thumb/1',
      tileSource: '/tiles/public-2/slide.dzi',
      scale: null,
    },
  ],
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v2/public/folders/share-public', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(manifest),
  }))
  await page.route('**/slide.dzi', (route) => route.fulfill({
    contentType: 'application/xml',
    body: '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" TileSize="512" Overlap="1" Format="jpg"><Size Width="1024" Height="768"/></Image>',
  }))
  await page.goto('/f/share-public')
  await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
})

test('keeps the shared viewer usable across desktop and mobile breakpoints', async ({ page }) => {
  for (const width of [320, 390, 760, 761, 1024, 1584]) {
    await page.setViewportSize({ width, height: width <= 390 ? 844 : 900 })
    await expect.poll(() => page.evaluate(() => (
      document.documentElement.scrollWidth <= document.documentElement.clientWidth
    ))).toBe(true)
    await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
    if (width <= 760) {
      const menu = page.getByRole('button', { name: 'Open slide navigator' })
      await expect(menu).toBeVisible()
      await menu.click()
      const rail = page.getByRole('complementary', { name: 'Shared slides' })
      await expect(rail).toBeVisible()
      await rail.getByRole('button', { name: 'Close slide navigator' }).click()
    }
  }
})

test('switches slides without replacing the public route', async ({ page }) => {
  await page.getByRole('button', { name: 'Next slide' }).click()
  await expect(page.getByRole('heading', { name: 'Normal colon' })).toBeVisible()
  await expect(page).toHaveURL(/\/f\/share-public$/)
})
