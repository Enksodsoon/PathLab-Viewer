import { expect, test } from './qa-test'
import { execFileSync } from 'node:child_process'
import { writeFile } from 'node:fs/promises'
import path from 'node:path'
import { signIn } from '../e2e-live/capacity-helpers'

test('large synthetic library paginates, survives offline recovery and isolates tab searches', async ({ page, context }, testInfo) => {
  test.setTimeout(900_000)
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
    if (size === 1000) {
      const explorer = await context.newPage()
      const menuEvidence: Array<{ label: string; items: string[] }> = []
      const menuStarted = Date.now()
      const retainProgress = async (phase: string) => {
        const directory = process.env.PATHLAB_E2E_REPORT_DIR
        if (!directory) return
        await writeFile(path.join(directory, 'library-scale-progress.json'), JSON.stringify({
          fixture: 'Frontend QA metadata-only', phase, expectedMenus: 1000,
          checkedMenus: menuEvidence.length, elapsedMs: Date.now() - menuStarted,
          lastCheckedMenu: menuEvidence.at(-1)?.label ?? null,
        }, null, 2))
      }
      try {
        await explorer.goto('/admin?q=Frontend%20QA&sort=name_asc')
        await expect(explorer.getByRole('heading', { name: 'Frontend QA 0000', exact: true })).toBeVisible()
        while (true) {
          const actions = explorer.locator('button[aria-label^="More actions for Frontend QA"]')
          const count = await actions.count()
          expect(count).toBeGreaterThan(0)
          await retainProgress('checking page')
          for (let index = 0; index < count; index += 1) {
            const trigger = actions.nth(index)
            const label = await trigger.getAttribute('aria-label')
            if (!label) throw new Error('Synthetic slide action menu has no accessible name')
            await trigger.click()
            const menu = explorer.getByRole('menu').last()
            await expect(menu).toBeVisible()
            const items = (await menu.getByRole('menuitem').allTextContents())
              .map((item) => item.trim().replace(/\s+/g, ' ')).sort()
            expect(items).toEqual([
              'Add to collection', 'Details', 'Edit details', 'Move', 'Move to Trash', 'Retry conversion',
            ])
            await explorer.keyboard.press('Escape')
            await expect(menu).toBeHidden()
            menuEvidence.push({ label, items })
          }
          await retainProgress('page checked')
          const next = explorer.getByRole('button', { name: 'Next page', exact: true })
          if (!(await next.count()) || !(await next.isEnabled())) break
          const responsePromise = explorer.waitForResponse((response) => {
            const url = new URL(response.url())
            return url.pathname.endsWith('/api/v2/admin/library/items') && url.searchParams.has('cursor')
          })
          await next.click()
          const response = await responsePromise
          expect(response.ok()).toBe(true)
          const { items } = await response.json() as { items: Array<{ displayName: string }> }
          await expect(actions).toHaveCount(items.length)
          await expect(actions.first()).toHaveAttribute('aria-label', `More actions for ${items[0].displayName}`)
        }
      } finally { await explorer.close() }
      expect(menuEvidence).toHaveLength(1000)
      await retainProgress('all1000 menus checked')
      await testInfo.attach('all-synthetic-slide-menus.json', {
        body: JSON.stringify({ fixture: 'Frontend QA metadata-only', count: menuEvidence.length, menus: menuEvidence }, null, 2),
        contentType: 'application/json',
      })
    }
  }
  const sortControl = page.getByRole('combobox', { name: 'Sort slides', exact: true })
  for (const sort of ['updated_asc', 'created_desc', 'created_asc', 'name_asc', 'name_desc', 'updated_desc']) {
    const responsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return url.pathname.endsWith('/api/v2/admin/library/items')
        && (url.searchParams.get('sort') ?? 'updated_desc') === sort
    })
    await sortControl.selectOption(sort)
    const response = await responsePromise
    expect(response.ok()).toBe(true)
    const { items } = await response.json() as { items: Array<{
      id: string
      displayName: string
      createdAt: string
      updatedAt: string
    }> }

    const descending = sort.endsWith('_desc')
    const value = (item: typeof items[number]) => sort.startsWith('updated')
      ? Date.parse(item.updatedAt)
      : sort.startsWith('created')
        ? Date.parse(item.createdAt)
        : item.displayName
    const expectedIds = [...items].sort((left, right) => {
      const leftValue = value(left)
      const rightValue = value(right)
      const valueOrder = leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0
      const idOrder = left.id < right.id ? -1 : left.id > right.id ? 1 : 0
      return (valueOrder || idOrder) * (descending ? -1 : 1)
    }).map((item) => item.id)
    expect(items.map((item) => item.id)).toEqual(expectedIds)
    await expect(sortControl).toHaveValue(sort)
    await expect(page.locator('.library-slide-card .card-content-heading h3'))
      .toHaveText(items.map((item) => item.displayName))
  }
  await sortControl.selectOption('name_asc')
  await expect(sortControl).toHaveValue('name_asc')

  const firstPage = await page.getByRole('heading', { name: /^Frontend QA/ }).allTextContents()
  const paged = page.waitForResponse((response) => response.url().includes('/library/items')
    && new URL(response.url()).searchParams.has('cursor'))
  const nextPage = page.getByRole('button', { name: 'Next page', exact: true })
  await nextPage.scrollIntoViewIfNeeded()
  await expect(nextPage).toBeInViewport({ ratio: 1 })
  await nextPage.click()
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
