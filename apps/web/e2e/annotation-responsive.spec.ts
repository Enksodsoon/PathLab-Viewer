import { expect, test, type Page } from '@playwright/test'

test.describe.configure({ mode: 'serial', timeout: 120_000 })

const privateSlide = {
  id: 'private-1',
  publicId: '',
  displayName: 'Private annotation slide',
  filename: 'private-slide.ome.tiff',
  sourceBytes: 1_048_576,
  state: 'ready_private',
  errorCode: null,
  errorMessage: null,
  tileSource: '/tiles/private-1/slide.dzi',
  thumbnailUrl: null,
  metadata: {
    width: 2048,
    height: 1024,
    physicalSizeX: 0.5,
    physicalSizeY: 0.75,
    physicalSizeUnit: 'MICROMETER',
  },
  annotationsEnabled: true,
  annotationVersion: 0,
  createdAt: '2026-07-26T00:00:00Z',
}

const publicSlide = {
  publicId: 'public-1',
  displayName: 'Public teaching slide',
  state: 'published',
  tileSource: '/tiles/public-1/slide.dzi',
  thumbnailUrl: null,
  metadata: {
    width: 2048,
    height: 1024,
    physicalSizeX: 0.5,
    physicalSizeUnit: 'MICROMETER',
  },
}

const layer = {
  id: '11111111-1111-4111-8111-111111111111',
  slideId: 'private-1',
  name: 'Findings',
  sortOrder: 0,
  visible: true,
  locked: false,
  opacity: 1,
  createdAt: '2026-07-26T00:00:00Z',
  updatedAt: '2026-07-26T00:00:00Z',
}

async function mockSlides(page: Page) {
  await page.route('**/api/v1/admin/slides/private-1', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(privateSlide),
  }))
  await page.route('**/api/v1/public/slides/public-1', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(publicSlide),
  }))
  await page.route('**/api/v2/admin/annotations/slides/private-1/manifest', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      slideId: 'private-1',
      version: 0,
      bounds: { width: 2048, height: 1024 },
      calibration: { x: 0.5, y: 0.75, unit: 'µm' },
      activeCount: 0,
      trashedCount: 0,
      layers: [layer],
      limits: {
        activeAnnotations: 25_000,
        layers: 100,
        verticesPerShape: 8192,
        verticesPerImport: 250_000,
        batchOperations: 50,
      },
    }),
  }))
  await page.route('**/api/v2/admin/annotations/slides/private-1/items?**', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ items: [], total: 0, nextOffset: null }),
  }))
  await page.route('**/api/v2/admin/annotations/slides/private-1/batch', async (route) => {
    const request = route.request().postDataJSON() as {
      mutationId: string
      operations: Array<{ type: string; id?: string; item?: { id: string } }>
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        mutationId: request.mutationId,
        version: 1,
        results: request.operations.map((operation) => ({
          id: operation.item?.id ?? operation.id,
          operation: operation.type,
          version: 1,
          deleted: operation.type === 'delete',
        })),
        purged: 0,
      }),
    })
  })
  await page.route('**/tiles/**/slide.dzi', (route) => route.fulfill({
    contentType: 'application/xml',
    body: '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" TileSize="512" Overlap="1" Format="jpg"><Size Width="2048" Height="1024"/></Image>',
  }))
  await page.route('**/tiles/**/*_files/**', (route) => route.fulfill({
    status: 404,
    body: '',
  }))
}

test.beforeEach(async ({ page }) => {
  await mockSlides(page)
})

test('keeps the full private Canvas Focus workspace usable on desktop', async ({ page }) => {
  await page.setViewportSize({ width: 1584, height: 992 })
  await page.goto('/admin/preview/private-1')

  await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toBeVisible({
    timeout: 30_000,
  })
  await expect(page.getByRole('region', { name: 'Annotation inspector' })).toBeVisible()
  await expect(page.getByRole('searchbox', { name: 'Search annotations' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Point marker' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Findings', exact: true })).toBeVisible()
  await expect.poll(() => page.evaluate(() => (
    document.documentElement.scrollWidth <= document.documentElement.clientWidth
  ))).toBe(true)

  for (const name of ['Pan', 'Point marker', 'Save annotations', 'Close annotation inspector']) {
    const box = await page.getByRole('button', { name }).first().boundingBox()
    expect(box?.width).toBeGreaterThanOrEqual(44)
    expect(box?.height).toBeGreaterThanOrEqual(44)
  }

  await page.getByRole('button', { name: 'Point marker' }).click()
  await expect(page.getByRole('button', { name: 'Point marker' })).toHaveAttribute('aria-pressed', 'true')
  const overlay = page.locator('.annotation-svg-overlay')
  await expect(overlay).toBeAttached()
  await overlay.click({ position: { x: 720, y: 420 } })
  await expect(page.getByRole('button', { name: /point annotation/i })).toBeVisible()

  await page.keyboard.press('Control+s')
  await expect(page.locator('.annotation-save-status')).toHaveText(/Saved|No changes/)
})

test('uses a bottom tool dock and focus-restoring inspector sheet at 760px and below', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/preview/private-1')

  const toolbar = page.getByRole('toolbar', { name: 'Annotation tools' })
  await expect(toolbar).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('dialog', { name: 'Annotation inspector' })).toHaveCount(0)

  const toolbarBox = await toolbar.boundingBox()
  expect(toolbarBox).not.toBeNull()
  expect(toolbarBox!.y + toolbarBox!.height).toBeGreaterThan(780)
  const pointBox = await page.getByRole('button', { name: 'Point marker' }).boundingBox()
  expect(pointBox?.width).toBeGreaterThanOrEqual(44)
  expect(pointBox?.height).toBeGreaterThanOrEqual(44)

  const openInspector = page.getByRole('button', { name: 'Open annotation inspector' })
  await openInspector.click()
  const sheet = page.getByRole('dialog', { name: 'Annotation inspector' })
  await expect(sheet).toBeVisible()
  await expect(sheet).toHaveAttribute('aria-modal', 'true')
  const sheetBox = await sheet.boundingBox()
  expect(sheetBox?.y).toBeGreaterThan(200)
  const undersizedTargets = await page.locator('.annotation-workspace').evaluate((workspace) => {
    const targets = [...workspace.querySelectorAll<HTMLElement>(
      'button, input, select, textarea',
    )]
    const measured = new Set<HTMLElement>()
    return targets.flatMap((element) => {
      const style = getComputedStyle(element)
      if (style.display === 'none' || style.visibility === 'hidden') return []
      const target = element.matches('input[type="checkbox"], input[type="color"]')
        ? element.closest<HTMLElement>('label') ?? element
        : element
      if (measured.has(target)) return []
      measured.add(target)
      const box = target.getBoundingClientRect()
      // Fractional device-pixel conversion can report a declared 44 CSS px target
      // as 43.99 in Chromium/WebKit, so compare with a half-pixel layout tolerance.
      if (box.width >= 43.5 && box.height >= 43.5) return []
      return [{
        label: element.getAttribute('aria-label') ?? element.textContent?.trim() ?? element.tagName,
        width: Math.round(box.width),
        height: Math.round(box.height),
      }]
    })
  })
  expect(undersizedTargets).toEqual([])
  await sheet.getByRole('button', { name: 'Close annotation inspector' }).click()
  await expect(sheet).toHaveCount(0)
  await expect(openInspector).toBeFocused()

  await page.getByRole('button', { name: 'Point marker' }).click()
  const overlay = page.locator('.annotation-svg-overlay')
  await expect(overlay).toBeAttached()
  await overlay.dispatchEvent('pointerdown', {
    clientX: 180,
    clientY: 360,
    pointerId: 7,
    pointerType: 'touch',
  })
  await expect(page.getByRole('button', { name: /point annotation/i })).toBeVisible()
  await expect.poll(() => page.evaluate(() => (
    document.documentElement.scrollWidth <= document.documentElement.clientWidth
  ))).toBe(true)
})

test('tracks light and dark application themes without filtering the pathology canvas', async ({ page }) => {
  await page.goto('/admin/preview/private-1')
  await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toBeVisible({
    timeout: 30_000,
  })
  const inspector = page.locator('.annotation-inspector')
  if (await inspector.count() === 0) {
    await page.getByRole('button', { name: 'Open annotation inspector' }).click()
  }
  await expect(inspector).toBeVisible()

  await page.getByRole('radio', { name: 'Light' }).check()
  const light = await page.evaluate(() => ({
    panel: getComputedStyle(document.querySelector('.annotation-inspector')!).backgroundColor,
    stageFilter: getComputedStyle(document.querySelector('.viewer-stage')!).filter,
  }))
  await page.getByRole('radio', { name: 'Dark' }).check()
  const dark = await page.evaluate(() => ({
    panel: getComputedStyle(document.querySelector('.annotation-inspector')!).backgroundColor,
    stageFilter: getComputedStyle(document.querySelector('.viewer-stage')!).filter,
  }))

  expect(light.panel).not.toBe(dark.panel)
  expect(light.stageFilter).toBe('none')
  expect(dark.stageFilter).toBe('none')
})

test('keeps the public route free of annotation UI, APIs, payload fields, and lazy modules', async ({ page }) => {
  const requests: string[] = []
  page.on('request', (request) => requests.push(request.url()))
  await page.goto('/s/public-1')

  await expect(page.getByText('Public teaching slide', { exact: true })).toBeVisible()
  await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toHaveCount(0)
  await expect(page.getByText('Annotations', { exact: true })).toHaveCount(0)

  expect(requests.some((url) => url.includes('/api/v2/admin/annotations/'))).toBe(false)
  expect(requests.some((url) => url.includes('/src/annotations/'))).toBe(false)
  expect(Object.keys(publicSlide)).not.toContain('annotationsEnabled')
  expect(Object.keys(publicSlide)).not.toContain('annotationVersion')
})
