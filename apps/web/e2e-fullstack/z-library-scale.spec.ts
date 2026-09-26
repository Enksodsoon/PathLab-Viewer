import { expect, test } from './qa-test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { signIn } from '../e2e-live/capacity-helpers'

test('large synthetic library paginates, survives offline recovery and isolates tab searches', async ({ page, context }) => {
  test.skip(process.env.PATHLAB_E2E_STRESS === '1', 'Stress campaign owns the synthetic size sequence')
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  for (const size of [0, 1, 100, 1000]) {
    execFileSync(process.env.PATHLAB_E2E_PYTHON!,
      [path.resolve('../../scripts/seed_frontend_qa.py'), String(size)], { stdio: 'pipe' })
    const result = await (await page.request.get('/api/v2/admin/library/items?q=Frontend%20QA')).json()
    expect(result.total).toBe(size)
    await page.goto('/admin?q=Frontend%20QA&sort=name_asc')
    if (!size) await expect(page.getByRole('heading', { name: 'No slides here' })).toBeVisible()
    else await expect(page.getByRole('heading', { name: 'Frontend QA 0000', exact: true })).toBeVisible()
  }
  const firstPage = await page.getByRole('heading', { name: /^Frontend QA/ }).allTextContents()
  const paged = page.waitForResponse((response) => response.url().includes('/library/items')
    && new URL(response.url()).searchParams.has('cursor'))
  await page.getByRole('button', { name: 'Next page', exact: true }).click()
  expect((await paged).ok()).toBe(true)
  await expect(page.getByRole('heading', { name: 'Frontend QA 0000', exact: true })).not.toBeVisible()
  const secondPage = await page.getByRole('heading', { name: /^Frontend QA/ }).allTextContents()
  expect(secondPage.length).toBeGreaterThan(0)
  expect(secondPage.some((name) => firstPage.includes(name))).toBe(false)
  await page.getByRole('button', { name: 'Previous page', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Frontend QA 0000', exact: true })).toBeVisible()
  const search = page.getByRole('searchbox', { name: 'Search slides', exact: true })
  await context.setOffline(true)
  try {
    await search.fill('Frontend QA 0999')
    await expect(page.getByRole('alert')).toBeVisible()
  } finally { await context.setOffline(false) }
  await search.fill('Frontend QA 0001')
  await expect(page.getByRole('heading', { name: 'Frontend QA 0001', exact: true })).toBeVisible()
  const other = await context.newPage()
  try {
    await other.goto('/admin?q=Frontend%20QA%200999')
    await expect(other.getByRole('heading', { name: 'Frontend QA 0999', exact: true })).toBeVisible()
    for (const term of ['Frontend QA 0010', 'Frontend QA 0020', 'Frontend QA 0030']) await search.fill(term)
    await expect(page.getByRole('heading', { name: 'Frontend QA 0030', exact: true })).toBeVisible()
    await expect(other.getByRole('heading', { name: 'Frontend QA 0999', exact: true })).toBeVisible()
  } finally { await other.close() }
  await page.getByRole('button', { name: /^Open storage,/ }).click()
  const searched = page.waitForResponse((response) => response.url().includes('/storage')
    && new URL(response.url()).searchParams.get('q') === 'Frontend QA')
  await page.getByRole('searchbox', { name: 'Search stored files', exact: true }).fill('Frontend QA')
  expect((await searched).ok()).toBe(true)
  for (const sort of ['name_asc', 'size_desc', 'updated_desc']) {
    const sorted = page.waitForResponse((response) => response.url().includes('/storage')
      && new URL(response.url()).searchParams.get('sort') === sort)
    await page.getByRole('combobox', { name: 'Sort files', exact: true }).selectOption(sort)
    expect((await sorted).ok()).toBe(true)
    await expect(page.getByRole('combobox', { name: 'Sort files', exact: true })).toHaveValue(sort)
  }
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByText(/^Page 2 of /)).toBeVisible()
  await page.getByRole('button', { name: 'Previous', exact: true }).click()
  await expect(page.getByText(/^Page 1 of /)).toBeVisible()
  await page.getByRole('button', { name: 'Trash', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'No stored files match this view' })).toBeVisible()
})
