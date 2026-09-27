import { expect, test } from '@playwright/test'

import type { LibraryFolder } from '../src/types'

// Each response is a valid tree snapshot; another actor moves B to root, then A under B.
test('Library handles a valid hierarchy change with stale expanded child caches', async ({ page }) => {
  let moved = false
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  const folder = (id: string, parentId: string | null, hasChildren: boolean): LibraryFolder => ({
    id, parentId, name: id, description: '', sortOrder: 0, itemCount: 0,
    childCount: hasChildren ? 1 : 0, hasChildren, trashedAt: null,
    updatedAt: '2026-09-27T00:00:00Z',
  })
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    let body: unknown = {}
    if (url.pathname.endsWith('/navigation')) {
      body = {
        counts: { all: 0, unfiled: 0, shared: 0, processing: 0, failed: 0, trash: 0 },
        folders: [moved ? folder('B', null, true) : folder('A', null, true)],
        folderPath: url.searchParams.get('location') === 'folder:A'
          ? moved ? [folder('B', null, true), folder('A', 'B', false)] : [folder('A', null, true)]
          : [],
        collections: [], savedViews: [],
        storage: { usedBytes: 0, usableBytes: 100000, effectiveCapacityBytes: 100000 },
        capabilities: { classroom: false, study: false },
      }
    } else if (url.pathname.endsWith('/items')) body = { items: [], nextCursor: null, total: 0 }
    else if (url.pathname.endsWith('/A/children')) body = [folder('B', 'A', false)]
    else if (url.pathname.endsWith('/B/children')) body = [folder('A', 'B', false)]
    else if (url.pathname.endsWith('/session')) body = { csrfToken: 'synthetic' }
    else if (url.pathname.endsWith('/status')) body = { items: [] }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.goto('/admin')
  const openNavigator = () => page.getByRole('button', { name: 'Slide library', exact: true }).click()
  await openNavigator()
  await page.getByRole('button', { name: 'Expand A', exact: true }).click()
  await page.getByRole('treeitem', { name: 'A', exact: true }).click()
  moved = true
  await openNavigator()
  await page.getByRole('button', { name: 'All slides 0', exact: true }).click()
  await openNavigator()
  await page.getByRole('button', { name: 'Expand B', exact: true }).click()
  await expect(page.getByRole('treeitem')).toHaveCount(2)
  await expect(page.getByRole('treeitem', { name: 'B', exact: true })).toHaveAttribute('aria-level', '1')
  await expect(page.getByRole('treeitem', { name: 'A', exact: true })).toHaveAttribute('aria-level', '2')
  await page.getByRole('treeitem', { name: 'B', exact: true }).focus()
  await page.keyboard.press('ArrowLeft')
  await expect(page.getByRole('treeitem')).toHaveCount(1)
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('treeitem')).toHaveCount(2)
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('treeitem', { name: 'A', exact: true })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect.poll(() => new URL(page.url()).searchParams.get('location')).toBe('folder:A')
  expect(errors.filter((error) => /Maximum call stack|application render failed/.test(error))).toEqual([])
})
