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
    body: JSON.stringify({
      items: [
        slide,
        {
          ...slide,
          id: 'slide-2',
          displayName: 'SP-68-7354-C_U129 HER-2_20250501.vsi - SP-68-7354-C_U129 HER-2',
        },
      ],
      nextCursor: null,
      total: 2,
    }),
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

test('keeps per-file processing stages readable on desktop and mobile', async ({ page }) => {
  const processingSlides = [
    {
      ...slide,
      id: 'slide-uploading',
      displayName: 'Uploading source slide',
      state: 'uploading',
    },
    {
      ...slide,
      id: 'slide-validating',
      displayName: 'Validating OME-TIFF slide',
      state: 'validating',
    },
    {
      ...slide,
      id: 'slide-converting',
      displayName: 'Generating viewer tiles',
      state: 'converting',
    },
  ]
  await page.route('**/api/v2/admin/library/items**', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ items: processingSlides, nextCursor: null, total: 3 }),
  }))
  await page.route('**/api/v2/admin/slides/status**', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      items: processingSlides.map((item) => ({
        id: item.id,
        state: item.state,
        errorCode: null,
      })),
    }),
  }))
  await page.goto('/admin?location=processing')

  for (const viewport of [
    { width: 1310, height: 912 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport)
    await expect(page.getByRole('heading', { name: 'Processing' })).toBeVisible()
    await expect(page.getByText('Receiving source file')).toBeVisible()
    await expect(page.getByText('Checking image structure and OME metadata')).toBeVisible()
    await expect(page.locator('.processing-progress > p', {
      hasText: 'Generating viewer tiles',
    })).toBeVisible()
    await expect(page.getByRole('progressbar')).toHaveCount(3)
    await expect.poll(() => page.evaluate(() => (
      document.documentElement.scrollWidth <= document.documentElement.clientWidth
    ))).toBe(true)
  }
})

test('keeps controls readable and non-overlapping across every layout boundary', async ({ page }) => {
  for (const width of [320, 360, 390, 600, 601, 768, 900, 901, 1100, 1101, 1250, 1251, 1439, 1440, 1584, 1920]) {
    await page.setViewportSize({ width, height: width < 600 ? 844 : 900 })
    await expect.poll(() => page.evaluate(() => (
      document.documentElement.scrollWidth <= document.documentElement.clientWidth
    ))).toBe(true)
    await expect(page.getByRole('heading', { name: 'All slides' })).toBeVisible()
    if (width <= 600) {
      const selects = page.locator('.library-command-actions select')
      const boxes = await selects.evaluateAll((elements) => elements.map((element) => {
        const box = element.getBoundingClientRect()
        return { left: box.left, right: box.right, top: box.top, bottom: box.bottom }
      }))
      for (let index = 0; index < boxes.length; index += 1) {
        for (let other = index + 1; other < boxes.length; other += 1) {
          const a = boxes[index]
          const b = boxes[other]
          expect(
            a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top,
            `controls ${index} and ${other} overlap at ${width}px: ${JSON.stringify({ a, b })}`,
          ).toBe(true)
        }
      }
      const libraryLabel = page.getByRole('button', { name: /^library$/i })
      await expect.poll(() => libraryLabel.evaluate((element) => (
        Number.parseFloat(getComputedStyle(element).fontSize)
      ))).toBeGreaterThanOrEqual(11)
    }
  }
})

test('isolates the closed mobile navigator and restores focus after Escape', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const navigator = page.locator('#library-navigator')
  const toggle = page.getByRole('button', { name: 'Open library navigator' })

  await expect(navigator).toBeHidden()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await toggle.click()
  await expect(navigator).toBeVisible()
  await expect(page.locator('main')).toHaveAttribute('inert', '')

  await page.keyboard.press('Escape')

  await expect(navigator).toBeHidden()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(toggle).toBeFocused()
})

test('contains table scrolling without widening the document', async ({ page }) => {
  await page.setViewportSize({ width: 1234, height: 900 })
  await page.goto('/admin?view=table')
  await expect(page.getByRole('table')).toBeVisible()

  const overflow = await page.evaluate(() => ({
    document: {
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    },
    layout: ['.library-shell', '.library-main', '.library-content', '.library-table-wrap']
      .map((selector) => {
        const element = document.querySelector(selector)
        if (!element) return { selector }
        const box = element.getBoundingClientRect()
        return {
          selector,
          clientWidth: element.clientWidth,
          left: box.left,
          overflowX: getComputedStyle(element).overflowX,
          right: box.right,
          scrollWidth: element.scrollWidth,
          width: box.width,
        }
      }),
    offenders: Array.from(document.querySelectorAll('body *'))
      .map((element) => {
        const box = element.getBoundingClientRect()
        const style = getComputedStyle(element)
        return {
          className: typeof element.className === 'string' ? element.className : '',
          clientWidth: element.clientWidth,
          overflowX: style.overflowX,
          right: box.right,
          scrollWidth: element.scrollWidth,
          tagName: element.tagName,
        }
      })
      .filter((element) => (
        element.right > document.documentElement.clientWidth + 1
        || (
          element.scrollWidth > element.clientWidth + 1
          && element.overflowX === 'visible'
        )
      ))
      .slice(0, 12),
  }))
  expect(
    overflow.document.scrollWidth,
    JSON.stringify({ layout: overflow.layout, offenders: overflow.offenders }),
  ).toBeLessThanOrEqual(overflow.document.clientWidth)
  expect(await page.locator('.library-table-wrap').evaluate((element) => (
    element.scrollWidth > element.clientWidth
  ))).toBe(true)
})

test('uses designed filter, checkbox, and compact table thumbnail controls', async ({ page }) => {
  await page.goto('/admin?view=table')
  await page.getByRole('button', { name: 'Filters' }).click()

  const closeStyle = await page.getByRole('button', { name: 'Close filters' }).evaluate((element) => {
    const style = getComputedStyle(element)
    return {
      color: style.color,
      background: style.backgroundColor,
      width: style.width,
      height: style.height,
    }
  })
  expect(closeStyle.color).not.toBe('rgb(255, 255, 255)')
  expect(closeStyle.background).toBe('rgb(20, 18, 16)')
  expect(closeStyle.width).toBe('34px')
  expect(closeStyle.height).toBe('34px')

  const selectVisible = page.getByRole('checkbox', { name: 'Select visible' })
  await expect(selectVisible).toHaveCSS('appearance', 'none')
  await selectVisible.click()
  await expect(selectVisible).toBeChecked()
  await expect(selectVisible).toHaveCSS('background-color', 'rgb(240, 111, 91)')

  const thumbnail = page.locator('.table-mini-thumb').first()
  const thumbnailBounds = await thumbnail.boundingBox()
  expect(thumbnailBounds?.width).toBeGreaterThanOrEqual(60)
  expect(thumbnailBounds?.height).toBeGreaterThanOrEqual(40)
  await expect(thumbnail.locator('.thumbnail-fallback span')).toBeHidden()
})

test('wraps long slide names within mobile cards', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const heading = page.getByRole('heading', {
    name: 'SP-68-7354-C_U129 HER-2_20250501.vsi - SP-68-7354-C_U129 HER-2',
  })
  await expect(heading).toBeVisible()

  const style = await heading.evaluate((element) => {
    const computed = getComputedStyle(element)
    return {
      lineClamp: computed.getPropertyValue('-webkit-line-clamp'),
      whiteSpace: computed.whiteSpace,
    }
  })
  expect(style.whiteSpace).not.toBe('nowrap')
  expect(style.lineClamp).toBe('2')

  const card = heading.locator('xpath=ancestor::article')
  const [headingBox, cardBox] = await Promise.all([heading.boundingBox(), card.boundingBox()])
  expect(headingBox).not.toBeNull()
  expect(cardBox).not.toBeNull()
  expect((headingBox?.x ?? 0) + (headingBox?.width ?? 0)).toBeLessThanOrEqual(
    (cardBox?.x ?? 0) + (cardBox?.width ?? 0),
  )
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

test('keeps the shared viewer navigable on desktop and mobile', async ({ page }) => {
  await page.route('**/api/v2/public/folders/share-public', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
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
          teachingNote: 'Safe note',
          thumbnailUrl: '/thumb/0',
          tileSource: '/tiles/public-1/slide.dzi',
          scale: 0.5,
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
          scale: 0.5,
        },
      ],
    }),
  }))
  await page.route('**/thumb/**', (route) => route.fulfill({ status: 404 }))
  await page.route('**/tiles/**', (route) => route.fulfill({ status: 404 }))

  await page.goto('/f/share-public')
  await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible({
    timeout: 10_000,
  })
  await page.getByRole('button', { name: 'Next slide' }).click()
  await expect(page.getByRole('heading', { name: 'Normal colon' })).toBeVisible()

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('button', { name: 'Open slide navigator' })).toBeVisible()
  await page.getByRole('button', { name: 'Open slide navigator' }).click()
  await expect(page.getByRole('searchbox', { name: 'Search shared slides' })).toBeVisible()
  expect(await page.evaluate(() => (
    document.documentElement.scrollWidth <= document.documentElement.clientWidth
  ))).toBe(true)
})

test('keeps folder sharing controls contained on mobile', async ({ page }) => {
  await page.goto('/admin?location=folder:folder-organs')
  await page.setViewportSize({ width: 390, height: 844 })
  const share = page.getByRole('button', { name: 'Share', exact: true })
  await expect(share).toBeVisible()
  for (const control of [share, page.getByRole('button', { name: 'Upload', exact: true })]) {
    const box = await control.boundingBox()
    expect(box).not.toBeNull()
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(390)
  }
  expect(await page.evaluate(() => (
    document.documentElement.scrollWidth <= document.documentElement.clientWidth
  ))).toBe(true)
  await share.click()
  await expect(page.getByRole('dialog', { name: 'Share Organ systems' })).toBeVisible()
})
