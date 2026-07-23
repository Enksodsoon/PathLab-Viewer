import { expect, test, type Page } from '@playwright/test'

const navigation = {
  counts: { all: 2, unfiled: 0, shared: 0, processing: 0, failed: 0, trash: 0 },
  folders: [{
    id: 'folder-organs',
    parentId: null,
    name: 'Organ systems',
    description: '',
    sortOrder: 0,
    itemCount: 2,
    childCount: 0,
    hasChildren: false,
    trashedAt: null,
    updatedAt: '2026-07-23T00:00:00Z',
  }],
  collections: [{
    id: 'collection-core',
    name: 'Core Curriculum',
    description: '',
    sortOrder: 0,
    itemCount: 2,
    updatedAt: '2026-07-23T00:00:00Z',
  }],
  savedViews: [],
}

const slide = {
  id: 'slide-1',
  publicId: 'public-1',
  displayName: 'Colon adenocarcinoma',
  description: '',
  folderId: 'folder-organs',
  caseId: 'GI-2026-014',
  organSite: 'Colon',
  stain: 'H&E',
  diagnosis: 'Adenocarcinoma',
  course: 'Core pathology',
  tags: ['Teaching'],
  teachingNote: '',
  sourceBytes: 3_420_000_000,
  derivativeBytes: 100,
  state: 'ready_private',
  errorCode: null,
  createdAt: '2026-07-23T00:00:00Z',
  updatedAt: '2026-07-23T00:00:00Z',
  trashedAt: null,
  thumbnailUrl: null,
}

async function mockLibrary(page: Page) {
  await page.route('**/api/v2/admin/library/navigation', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(navigation),
  }))
  await page.route('**/api/v2/admin/library/items**', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ items: [slide, { ...slide, id: 'slide-2', displayName: 'Lung H&E' }], nextCursor: null, total: 2 }),
  }))
  await page.route('**/api/v2/admin/slides/slide-1', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      ...slide,
      filename: 'colon.ome.tiff',
      adminNotes: 'Private note',
      metadata: null,
    }),
  }))
}

test.beforeEach(async ({ page }) => {
  await mockLibrary(page)
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'All slides' })).toBeVisible()
})

test('keeps the library contained across representative window widths', async ({ page }) => {
  for (const width of [320, 360, 390, 600, 768, 900, 1024, 1280, 1584, 1920]) {
    await page.setViewportSize({ width, height: width < 600 ? 844 : 900 })
    await expect.poll(() => page.evaluate(() => (
      document.documentElement.scrollWidth <= document.documentElement.clientWidth
    ))).toBe(true)
    await expect(page.getByRole('heading', { name: 'All slides' })).toBeVisible()
  }
})

test('exposes functional creation, card, and mobile account controls', async ({ page }) => {
  await page.getByRole('button', { name: 'Create' }).click()
  await expect(page.getByRole('menuitem', { name: 'New collection' })).toBeVisible()
  await page.getByRole('button', { name: 'Create' }).click()

  await page.getByRole('button', { name: /more actions for colon adenocarcinoma/i }).click()
  await page.getByRole('menuitem', { name: 'Edit details' }).click()
  await expect(page.getByRole('heading', { name: 'Edit slide details' })).toBeVisible()
  await page.getByRole('button', { name: /close edit slide details/i }).click()

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('button', { name: 'Account' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
})
