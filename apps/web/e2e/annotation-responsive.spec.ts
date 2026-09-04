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

const sharedManifest = {
  publicId: 'share-public',
  targetType: 'folder',
  name: 'Public teaching set',
  description: 'De-identified teaching slides',
  expiresAt: null,
  slides: [{
    position: 0,
    displayName: 'Public teaching slide',
    organSite: 'Colon',
    stain: 'H&E',
    diagnosis: 'Teaching',
    tags: [],
    teachingNote: '',
    thumbnailUrl: null,
    tileSource: '/tiles/public-1/slide.dzi',
    scale: null,
  }],
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

const touchPolygon = {
  id: '22222222-2222-4222-8222-222222222222',
  layerId: layer.id,
  geometry: {
    type: 'polygon',
    points: [{ x: 640, y: 320 }, { x: 880, y: 320 }, { x: 760, y: 520 }],
  },
  style: {
    strokeColor: '#ffb400',
    fillColor: '#ffb400',
    strokeWidth: 2,
    opacity: 0.9,
    labelVisible: true,
  },
  metadata: {
    title: 'Touch polygon',
    classification: 'Tumour',
    tags: [],
    notes: '',
  },
  version: 1,
  deletedAt: null,
  createdAt: '2026-07-26T00:00:00Z',
  updatedAt: '2026-07-26T00:00:00Z',
  bounds: { minX: 640, minY: 320, maxX: 880, maxY: 520 },
  measurements: {},
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
  await page.route('**/api/v2/public/folders/share-public', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(sharedManifest),
  }))
  await page.route('**/api/v2/public/collections/share-public', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ ...sharedManifest, targetType: 'collection' }),
  }))
  await page.route('**/api/v2/admin/annotations/slides/private-1/manifest', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      slideId: 'private-1',
      version: 0,
      bounds: { width: 2048, height: 1024 },
      calibration: { x: 0.5, y: 0.75, unit: 'µm' },
      activeCount: 1,
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
    body: JSON.stringify({ items: [touchPolygon], total: 1, nextOffset: null }),
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

test('draws immediately on a virtual Layer 1 and saves layer plus annotation together', async ({
  page,
}) => {
  let savedRequest: {
    ensureLayer?: { id: string; name: string }
    operations: Array<{ type: string; item?: { id: string; layerId: string } }>
  } | null = null
  await page.unroute('**/api/v2/admin/annotations/slides/private-1/manifest')
  await page.unroute('**/api/v2/admin/annotations/slides/private-1/items?**')
  await page.unroute('**/api/v2/admin/annotations/slides/private-1/batch')
  await page.route('**/api/v2/admin/annotations/slides/private-1/manifest', (route) => (
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        slideId: 'private-1',
        version: 0,
        bounds: { width: 2048, height: 1024 },
        calibration: { x: 0.5, y: 0.75, unit: 'µm' },
        activeCount: 0,
        trashedCount: 0,
        layers: [],
        limits: {
          activeAnnotations: 25_000,
          layers: 100,
          verticesPerShape: 8192,
          verticesPerImport: 250_000,
          batchOperations: 50,
        },
      }),
    })
  ))
  await page.route('**/api/v2/admin/annotations/slides/private-1/items?**', (route) => (
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, nextOffset: null }),
    })
  ))
  await page.route('**/api/v2/admin/annotations/slides/private-1/batch', async (route) => {
    const request = route.request().postDataJSON() as {
      mutationId: string
      ensureLayer?: { id: string; name: string }
      operations: Array<{ type: string; item?: { id: string; layerId: string } }>
    }
    savedRequest = request
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        mutationId: request.mutationId,
        version: 1,
        results: request.operations.map((operation) => ({
          id: operation.item?.id,
          operation: operation.type,
          version: 1,
          deleted: false,
        })),
        purged: 0,
      }),
    })
  })

  await page.goto('/admin/preview/private-1')
  await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toBeVisible({
    timeout: 30_000,
  })
  await page.getByRole('button', { name: 'Open annotation inspector' }).click()
  await page.getByRole('button', { name: 'Show advanced annotation details' }).click()
  await expect(page.getByRole('button', { name: 'Layer 1', exact: true })).toBeVisible()
  expect(savedRequest).toBeNull()
  await page.locator('.annotation-inspector').getByRole('button', {
    name: 'Close annotation inspector',
  }).click()

  await page.getByRole('button', { name: 'More annotation tools' }).click()
  await page.getByRole('button', { name: 'Point marker' }).click()
  const overlay = page.locator('.annotation-svg-overlay')
  const overlayBox = await overlay.boundingBox()
  expect(overlayBox).not.toBeNull()
  await overlay.click({
    position: { x: overlayBox!.width / 2, y: overlayBox!.height / 2 },
  })
  await expect(page.locator('.annotation-list-toggle strong')).toHaveText('1')
  await expect.poll(() => savedRequest).not.toBeNull()
  expect(savedRequest!.ensureLayer).toMatchObject({ name: 'Layer 1' })
  expect(savedRequest!.ensureLayer!.id).toBe(savedRequest!.operations[0].item!.layerId)
})

test('keeps the full private Canvas Focus workspace usable on desktop', async ({ page }) => {
  await page.setViewportSize({ width: 1584, height: 992 })
  await page.goto('/admin/preview/private-1')

  await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toBeVisible({
    timeout: 30_000,
  })
  await expect(page.getByRole('region', { name: 'Annotation inspector' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Open annotations' }).click()
  await expect(page.getByRole('searchbox', { name: 'Search annotations' })).toBeVisible()
  await page.getByRole('button', { name: 'Open annotation inspector' }).click()
  await page.getByRole('button', { name: 'Show advanced annotation details' }).click()
  await page.getByRole('button', { name: 'More annotation tools' }).click()
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
  await expect(page.locator('.annotation-data-cue')).toContainText('POINT')
  const overlay = page.locator('.annotation-svg-overlay')
  await expect(overlay).toBeAttached()
  await overlay.click({ position: { x: 720, y: 420 } })
  await expect(page.getByRole('button', { name: /point annotation/i })).toBeVisible()

  await page.getByRole('button', { name: 'Rectangle' }).click()
  await page.keyboard.down('Space')
  await expect(page.locator('.annotation-operation-status')).toHaveText(
    'Pan active; release Space to continue Rectangle',
  )
  await expect(overlay).toHaveCSS('pointer-events', 'none')
  await page.keyboard.up('Space')
  await expect(page.locator('.annotation-operation-status')).toHaveText('Rectangle active')
  await expect(overlay).toHaveCSS('pointer-events', 'auto')
  await overlay.dispatchEvent('pointerdown', {
    clientX: 420,
    clientY: 300,
    pointerId: 11,
    pointerType: 'mouse',
  })
  await overlay.dispatchEvent('pointermove', {
    clientX: 620,
    clientY: 440,
    pointerId: 11,
    pointerType: 'mouse',
  })
  await expect(page.locator('rect.annotation-draft-shape')).toBeVisible()
  await expect(page.locator('.annotation-draft-measurement')).toContainText('px')
  await overlay.dispatchEvent('pointerup', {
    clientX: 620,
    clientY: 440,
    pointerId: 11,
    pointerType: 'mouse',
  })
  await expect(page.locator('.annotation-draft-shape')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /rectangle annotation/i })).toBeVisible()

  await page.keyboard.press('Control+s')
  await expect(page.locator('.annotation-save-status')).toHaveText(/Saved|No changes/)
})

test('shows selected annotations moving with the pointer before release', async ({ page }) => {
  await page.setViewportSize({ width: 1584, height: 992 })
  await page.goto('/admin/preview/private-1')
  await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toBeVisible({
    timeout: 30_000,
  })
  await page.getByRole('button', { name: 'Select', exact: true }).click()
  await page.getByRole('button', { name: 'Open annotations' }).click()
  await page.getByRole('button', { name: /Touch polygon/ }).click()

  const overlay = page.locator('.annotation-svg-overlay')
  const shape = page.locator(
    `[data-annotation-id="${touchPolygon.id}"] > polygon`,
  )
  const before = await shape.boundingBox()
  expect(before).not.toBeNull()
  const startX = before!.x + before!.width / 2
  const startY = before!.y + before!.height / 2

  await shape.hover({
    position: { x: before!.width / 2, y: before!.height / 2 },
  })
  await page.mouse.down()
  await page.mouse.move(startX + 36, startY + 24, { steps: 4 })

  await expect(overlay).toHaveClass(/is-moving-annotation/)
  const previewTranslation = await page.locator('.annotation-move-preview').evaluate((node) => {
    const matrix = new DOMMatrixReadOnly(getComputedStyle(node).transform)
    return { x: matrix.m41, y: matrix.m42 }
  })
  expect(Math.abs(previewTranslation.x - 36)).toBeLessThanOrEqual(0.1)
  expect(Math.abs(previewTranslation.y - 24)).toBeLessThanOrEqual(0.1)
  const during = await shape.boundingBox()
  expect(Math.abs(during!.x - (before!.x + 36))).toBeLessThanOrEqual(3)
  expect(Math.abs(during!.y - (before!.y + 24))).toBeLessThanOrEqual(3)

  await page.mouse.up()
  await expect(overlay).not.toHaveClass(/is-moving-annotation/)
  await expect(page.locator('.annotation-move-preview')).toHaveCount(0)
})

test('resolves a single ROI and previews calibrated ruler and angle measurements', async ({ page }) => {
  await page.setViewportSize({ width: 1584, height: 992 })
  await page.goto('/admin/preview/private-1')
  await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toBeVisible({
    timeout: 30_000,
  })
  const overlay = page.locator('.annotation-svg-overlay')

  await page.getByRole('button', { name: 'More annotation tools' }).click()
  await expect(page.getByRole('button', { name: 'Erase from selected ROI' }))
    .toHaveAttribute('aria-disabled', 'false')

  await page.getByRole('button', { name: 'Ruler' }).click()
  await overlay.dispatchEvent('pointerdown', {
    clientX: 300,
    clientY: 400,
    pointerId: 21,
    pointerType: 'mouse',
  })
  await overlay.dispatchEvent('pointermove', {
    clientX: 400,
    clientY: 400,
    pointerId: 21,
    pointerType: 'mouse',
  })
  const liveMeasurement = page.locator('.annotation-draft-measurement')
  await expect(liveMeasurement).toHaveText(/^\d+(?:\.\d+)? µm$/)
  const shorterLength = Number((await liveMeasurement.textContent())!.split(' ')[0])
  await overlay.dispatchEvent('pointermove', {
    clientX: 500,
    clientY: 400,
    pointerId: 21,
    pointerType: 'mouse',
  })
  await expect.poll(async () => (
    Number((await liveMeasurement.textContent())!.split(' ')[0])
  )).toBeGreaterThan(shorterLength)
  await overlay.dispatchEvent('pointercancel', {
    clientX: 500,
    clientY: 400,
    pointerId: 21,
    pointerType: 'mouse',
  })

  await page.getByRole('button', { name: 'More annotation tools' }).click()
  await page.getByRole('button', { name: 'Three-point angle' }).click()
  for (const [clientX, clientY, pointerId] of [[300, 400, 22], [400, 400, 23]]) {
    await overlay.dispatchEvent('pointerdown', {
      clientX,
      clientY,
      pointerId,
      pointerType: 'mouse',
    })
    await overlay.dispatchEvent('pointerup', {
      clientX,
      clientY,
      pointerId,
      pointerType: 'mouse',
    })
  }
  await overlay.dispatchEvent('pointermove', {
    clientX: 400,
    clientY: 500,
    pointerId: 24,
    pointerType: 'mouse',
  })
  await expect(page.locator('.annotation-draft-measurement')).toHaveText('90°')
  await overlay.dispatchEvent('pointerdown', {
    clientX: 400,
    clientY: 500,
    pointerId: 24,
    pointerType: 'mouse',
  })
  await overlay.dispatchEvent('pointerup', {
    clientX: 400,
    clientY: 500,
    pointerId: 24,
    pointerType: 'mouse',
  })
  await expect(page.locator('.annotation-draft-measurement')).toHaveCount(0)
  await expect(page.locator('[data-annotation-label="measurement"]')).toHaveText('90°')
})

test('keeps desktop panels compact, separated, and lets the annotation list move', async ({ page }) => {
  await page.setViewportSize({ width: 1134, height: 824 })
  await page.goto('/admin/preview/private-1')
  await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toBeVisible({
    timeout: 30_000,
  })
  await page.getByRole('button', { name: 'Open annotations' }).click()
  await page.getByRole('button', { name: 'Open annotation inspector' }).click()
  await page.getByRole('button', { name: 'More annotation tools' }).click()

  const commandbar = page.locator('.annotation-commandbar')
  const moreTools = page.locator('.annotation-more-tools')
  const commandBounds = await commandbar.boundingBox()
  const moreBounds = await moreTools.boundingBox()
  expect(commandBounds).not.toBeNull()
  expect(moreBounds).not.toBeNull()
  const panelsOverlap = !(
    moreBounds!.x + moreBounds!.width <= commandBounds!.x
    || commandBounds!.x + commandBounds!.width <= moreBounds!.x
    || moreBounds!.y + moreBounds!.height <= commandBounds!.y
    || commandBounds!.y + commandBounds!.height <= moreBounds!.y
  )
  expect(panelsOverlap).toBe(false)

  const inspector = page.locator('.annotation-inspector')
  const compactInspector = await inspector.boundingBox()
  expect(compactInspector?.height).toBeLessThan(430)

  const list = page.locator('.annotation-list')
  const moveHandle = page.getByRole('button', { name: 'Move annotation list' })
  const before = await list.boundingBox()
  const handleBounds = await moveHandle.boundingBox()
  expect(before).not.toBeNull()
  expect(handleBounds).not.toBeNull()
  await page.mouse.move(
    handleBounds!.x + handleBounds!.width / 2,
    handleBounds!.y + handleBounds!.height / 2,
  )
  await page.mouse.down()
  await page.mouse.move(
    handleBounds!.x + handleBounds!.width / 2 + 260,
    handleBounds!.y + handleBounds!.height / 2 - 180,
    { steps: 5 },
  )
  await page.mouse.up()
  const after = await list.boundingBox()
  expect(after!.x).toBeGreaterThan(before!.x + 200)
  expect(after!.y).toBeLessThan(before!.y - 120)
  await expect(list).not.toHaveAttribute('data-dragging')

  await page.getByRole('button', { name: 'Show advanced annotation details' }).click()
  const expandedInspector = await inspector.boundingBox()
  expect(expandedInspector!.height).toBeGreaterThan(compactInspector!.height)
  await expect(page.getByRole('button', { name: 'Hide advanced annotation details' }))
    .toHaveAttribute('aria-expanded', 'true')
})

test('presents selected annotation actions with clear progressive disclosure', async ({ page }) => {
  await page.setViewportSize({ width: 1134, height: 824 })
  await page.goto('/admin/preview/private-1')
  await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toBeVisible({
    timeout: 30_000,
  })
  await page.getByRole('button', { name: 'Open annotations' }).click()
  await page.getByRole('button', { name: /Touch polygon/ }).click()

  const inspector = page.getByRole('region', { name: 'Annotation inspector' })
  await expect(inspector).toBeVisible()
  await expect(inspector.locator('.annotation-selection-summary')).toContainText('Touch polygon')
  await expect(inspector.locator('.annotation-selection-summary')).toContainText('polygon · Findings')
  await expect(page.getByRole('button', { name: 'Zoom to selected annotation' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Duplicate selected annotations' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Delete selected annotations' })).toBeVisible()
  await expect(page.getByLabel('Boolean operations')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Restore selected annotations' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Show advanced annotation details' }))
    .toHaveAttribute('aria-expanded', 'false')
  await expect(inspector.getByRole('heading', { name: 'Annotation details' })).toBeVisible()

  await page.getByRole('button', { name: 'Show advanced annotation details' }).click()
  for (const heading of [
    'Metadata',
    'Appearance',
    'Layers',
    'Geometry & measurements',
    'Data & history',
  ]) {
    await expect(inspector.getByRole('heading', { name: heading })).toBeVisible()
  }
  await expect(page.getByRole('button', { name: 'Import annotations' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Export PathLab JSON' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Browse annotation revisions' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reload annotations' })).toBeVisible()
  const overflowingControls = await inspector.evaluate((element) => {
    const boundary = element.getBoundingClientRect()
    return [...element.querySelectorAll<HTMLElement>('*')].flatMap((candidate) => {
      const box = candidate.getBoundingClientRect()
      if (
        candidate.classList.contains('visually-hidden')
        || box.width === 0
        || box.height === 0
        || box.right <= boundary.right + 0.5
      ) return []
      return [{
        className: candidate.className,
        overflow: Math.round((box.right - boundary.right) * 10) / 10,
        tag: candidate.tagName,
      }]
    })
  })
  expect(overflowingControls).toEqual([])

  await page.getByRole('button', { name: 'Copy selected annotations' }).click()
  await expect(page.getByRole('button', { name: 'Paste annotations' })).toBeEnabled()

  await page.getByRole('button', { name: 'Duplicate selected annotations' }).click()
  await expect(page.locator('.annotation-list-toggle strong')).toHaveText('2')
  const annotationRows = page.getByRole('button', { name: /Touch polygon/ })
  await annotationRows.nth(1).click({ modifiers: ['Shift'] })
  await expect(page.getByLabel('Boolean operations')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Intersect', exact: true })).toBeVisible()
  await annotationRows.first().click()
  await page.getByRole('button', { name: 'Delete selected annotations' }).click()
  await expect(page.locator('.annotation-list-toggle strong')).toHaveText('1')
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
  await page.getByRole('button', { name: 'More annotation tools' }).click()
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
  await expect(overlay).toBeVisible()
  const persisted = page.waitForResponse((response) => (
    response.request().method() === 'POST'
    && response.url().includes('/api/v2/admin/annotations/slides/private-1/batch')
    && response.ok()
  ))
  // Use Playwright's complete pointer sequence. A synthetic pointerdown can be
  // dropped by Firefox before React commits the annotation and persistence effect.
  await overlay.click({ position: { x: 180, y: 360 } })
  await persisted
  await page.getByRole('button', { name: 'Open annotations' }).click()
  await expect(page.getByRole('button', { name: /point annotation/i })).toBeVisible()
  await expect.poll(() => page.evaluate(() => (
    document.documentElement.scrollWidth <= document.documentElement.clientWidth
  ))).toBe(true)
})

test('edits a polygon vertex through a 44px touch handle on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/preview/private-1')
  await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toBeVisible({
    timeout: 30_000,
  })

  await page.getByRole('button', { name: 'Open annotations' }).click()
  await page.getByRole('button', { name: 'Select', exact: true }).click()
  await page.getByRole('button', { name: /Touch polygon/ }).click()
  await page.getByRole('dialog', { name: 'Annotation inspector' })
    .getByRole('button', { name: 'Close annotation inspector' })
    .click()
  await expect(page.getByRole('dialog', { name: 'Annotation inspector' })).not.toBeVisible()
  const handle = page.locator(
    '[data-annotation-handle="vertex"][data-vertex-index="0"]',
  )
  await expect(handle).toHaveAttribute('role', 'button', { timeout: 15_000 })
  await expect(handle).toHaveAttribute('aria-label', 'Move vertex 1 of Touch polygon')
  const handleBox = await handle.boundingBox()
  expect(handleBox?.width).toBeGreaterThanOrEqual(43.5)
  expect(handleBox?.height).toBeGreaterThanOrEqual(43.5)
  const glyph = handle.locator('.annotation-canvas-handle-glyph')
  const initialX = Number(await glyph.getAttribute('cx'))
  const overlay = page.locator('.annotation-svg-overlay')
  const pointer = {
    pointerId: 17,
    pointerType: 'touch',
    clientX: handleBox!.x + handleBox!.width / 2,
    clientY: handleBox!.y + handleBox!.height / 2,
  }
  await handle.dispatchEvent('pointerdown', pointer)
  await overlay.dispatchEvent('pointermove', {
    ...pointer,
    clientX: pointer.clientX + 28,
    clientY: pointer.clientY + 18,
  })
  await overlay.dispatchEvent('pointerup', {
    ...pointer,
    clientX: pointer.clientX + 28,
    clientY: pointer.clientY + 18,
  })

  await expect.poll(async () => Number(await glyph.getAttribute('cx')))
    .toBeGreaterThan(initialX)
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

for (const publicRoute of [
  { path: '/s/public-1', apiPath: '/api/v1/public/slides/public-1' },
  { path: '/f/share-public', apiPath: '/api/v2/public/folders/share-public' },
  { path: '/c/share-public', apiPath: '/api/v2/public/collections/share-public' },
]) {
  test(`keeps ${publicRoute.path} free of annotation UI, APIs, payload fields, and lazy modules`, async ({ page }) => {
    const requests: string[] = []
    page.on('request', (request) => requests.push(request.url()))
    const publicResponse = page.waitForResponse((response) => (
      response.url().includes(publicRoute.apiPath)
    ))

    await page.goto(publicRoute.path)
    const payload = await (await publicResponse).json() as unknown

    await expect(page.getByText('Public teaching slide', { exact: true }).first()).toBeVisible()
    await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toHaveCount(0)
    await expect(page.getByText('Annotations', { exact: true })).toHaveCount(0)

    expect(requests.some((url) => url.includes('/api/v2/admin/annotations/'))).toBe(false)
    expect(requests.some((url) => url.includes('/src/annotations/'))).toBe(false)
    expect(requests.some((url) => url.includes('AnnotationWorkspace'))).toBe(false)
    expect(requests.some((url) => url.includes('boolean.worker'))).toBe(false)
    expect(JSON.stringify(payload)).not.toContain('"annotationsEnabled"')
    expect(JSON.stringify(payload)).not.toContain('"annotationVersion"')
  })
}
