import { expect, test } from '@playwright/test'

test.describe.configure({ mode: 'serial' })
test.setTimeout(90_000)

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', (route) => route.fulfill({
    status: 401,
    contentType: 'application/json',
    body: JSON.stringify({ detail: { code: 'AUTHENTICATION_REQUIRED' } }),
  }))
})

test('persists theme choice and remains usable at every layout boundary', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Administrator sign in' })).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(page.getByRole('radio', { name: 'System' })).toBeChecked()

  await page.locator('label[for="theme-light"]').click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await expect(page.getByRole('radio', { name: 'Light' })).toBeChecked()

  for (const width of [320, 390, 768, 820, 940, 941, 1024, 1584, 1920]) {
    await page.setViewportSize({ width, height: width <= 940 ? 844 : 900 })
    await expect(page.getByRole('heading', { name: 'See the whole picture.' })).toBeVisible()
    const layout = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      headingLines: Array.from(document.querySelectorAll('.auth-story-copy h1 > span'))
        .map((line) => line.getClientRects().length),
    }))
    expect(layout.scrollWidth, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(layout.clientWidth)
    expect(layout.headingLines).toEqual([1, 1])
  }
})

test('keeps recovery immediate, focused, and motion-safe', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/admin')
  await expect(page.locator('.auth-atmosphere')).toHaveAttribute('data-motion', 'reduced', { timeout: 20_000 })

  await page.getByRole('button', { name: 'Recover administrator access' }).click()
  await expect(page.getByRole('heading', { name: 'Recover administrator access' })).toBeFocused()
  await expect(page.getByLabel('Recovery code')).toBeVisible()
  await expect(page.getByLabel('New password', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Confirm new password', { exact: true })).toBeVisible()
  await expect(page.getByText('docker compose -f deploy/compose.yaml exec api pathlab-admin issue-recovery-code --username admin', { exact: true })).toBeVisible()

  const layout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth)
})

test('keeps continuous motion below the long-task threshold', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'chromium', 'One desktop Chromium performance sample is sufficient.')
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Administrator sign in' })).toBeVisible({ timeout: 20_000 })

  const longTasks = await page.evaluate(() => new Promise<number[]>((resolve) => {
    const durations: number[] = []
    const observer = new PerformanceObserver((list) => {
      durations.push(...list.getEntries().map((entry) => entry.duration))
    })
    observer.observe({ type: 'longtask', buffered: false })
    window.setTimeout(() => {
      observer.disconnect()
      resolve(durations)
    }, 10_000)
  }))

  expect(longTasks.filter((duration) => duration > 50)).toEqual([])
})
