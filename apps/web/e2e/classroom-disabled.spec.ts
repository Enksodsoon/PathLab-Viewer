import { expect, test } from '@playwright/test'

test('disabled ordinary admin entry loads no classroom request or page bundle', async ({ page }) => {
  const requests: string[] = []
  page.on('request', (request) => requests.push(request.url()))
  await page.route('**/api/**', (route) => route.fulfill({
    status: 401,
    contentType: 'application/json',
    body: JSON.stringify({ detail: { code: 'AUTH_REQUIRED' } }),
  }))

  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible()

  const resources = await page.evaluate(() => performance.getEntriesByType('resource')
    .map((entry) => entry.name))
  expect(resources.some((url) => /Classroom(?:Teacher|Student)Page/i.test(url))).toBe(false)
  expect(requests.some((url) => /\/api\/.*classroom/i.test(url))).toBe(false)
})
