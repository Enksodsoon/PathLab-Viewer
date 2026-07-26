import { expect, test, type Locator, type Page } from '@playwright/test'

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

async function expectMinimumTouchTarget(targets: Locator, label: string) {
  const boxes = await targets.evaluateAll((elements) => elements.map((element) => {
    const box = element.getBoundingClientRect()
    return { height: box.height, width: box.width }
  }))
  expect(boxes.length, `${label} should expose at least one target`).toBeGreaterThan(0)
  for (const [index, box] of boxes.entries()) {
    expect(box.height, `${label} target ${index} height`).toBeGreaterThanOrEqual(44)
    expect(box.width, `${label} target ${index} width`).toBeGreaterThanOrEqual(44)
  }
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
    const searchBox = await page.locator('.library-search').boundingBox()
    expect(searchBox?.height, `search control expanded vertically at ${width}px`).toBeLessThanOrEqual(56)
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
      const libraryLabel = page.getByRole('button', { name: /^all slides$/i })
      await expect.poll(() => libraryLabel.evaluate((element) => (
        Number.parseFloat(getComputedStyle(element).fontSize)
      ))).toBeGreaterThanOrEqual(11)
    }
  }
})

test('uses the Canvas Focus shell at every approved responsive width', async ({ page }) => {
  for (const width of [320, 390, 600, 768, 901, 1251, 1440, 1920]) {
    await page.setViewportSize({ width, height: width <= 600 ? 844 : 960 })
    await expect(page.getByRole('heading', { name: 'All slides' })).toBeVisible()

    const layout = await page.evaluate(() => {
      const shell = document.querySelector<HTMLElement>('.library-shell')
      const rail = document.querySelector<HTMLElement>('.library-app-rail')
      const main = document.querySelector<HTMLElement>('.library-main')
      const navigator = document.querySelector<HTMLElement>('.library-navigator-wrap')
      if (!shell || !rail || !main || !navigator) throw new Error('Canvas Focus regions missing')
      const shellStyle = getComputedStyle(shell)
      const railStyle = getComputedStyle(rail)
      const mainBox = main.getBoundingClientRect()
      return {
        columns: shellStyle.gridTemplateColumns.split(' ').filter(Boolean).length,
        documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        mainRight: mainBox.right,
        mainWidth: mainBox.width,
        navigatorPosition: getComputedStyle(navigator).position,
        railBottom: railStyle.bottom,
        railPosition: railStyle.position,
        railWidth: rail.getBoundingClientRect().width,
      }
    })

    expect(layout.documentFits).toBe(true)
    expect(layout.navigatorPosition).toBe('fixed')
    expect(layout.columns).toBe(width <= 600 ? 1 : 2)
    expect(layout.mainRight).toBeLessThanOrEqual(width + 1)
    expect(layout.mainWidth).toBeLessThanOrEqual(1560)
    if (width <= 600) {
      expect(layout.railPosition).toBe('fixed')
      expect(layout.railBottom).toBe('0px')
      expect(layout.railWidth).toBeCloseTo(width, 0)
    } else {
      expect(layout.railWidth).toBeLessThanOrEqual(72)
    }
  }
})

test('keeps every rail destination reachable on short desktop viewports', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 600 })
  const rail = page.getByRole('complementary', { name: 'Product navigation' })
  const requiredDestinations = [
    'All slides',
    'Open library navigator',
    'Upload',
    'Processing',
    'Failed',
    'Trash',
    'Account',
    'Sign out',
  ]

  await expect(rail).toHaveCSS('overflow-y', 'auto')
  const railMetrics = await rail.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }))
  expect(railMetrics.scrollHeight).toBeGreaterThan(railMetrics.clientHeight)

  for (const name of requiredDestinations) {
    const target = rail.getByRole('button', { name, exact: true })
    await expect(target).toHaveCount(1)
    await target.scrollIntoViewIfNeeded()
    const [railBox, targetBox] = await Promise.all([
      rail.boundingBox(),
      target.boundingBox(),
    ])
    expect(railBox).not.toBeNull()
    expect(targetBox).not.toBeNull()
    expect(targetBox!.y).toBeGreaterThanOrEqual(railBox!.y - 1)
    expect(targetBox!.y + targetBox!.height).toBeLessThanOrEqual(
      railBox!.y + railBox!.height + 1,
    )
  }
})

test('keeps representative mobile controls at least 44 pixels in both axes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })

  await expectMinimumTouchTarget(
    page.locator('.library-breadcrumb-row > button:visible'),
    'breadcrumb',
  )

  await page.getByRole('button', { name: 'Filters' }).click()
  await expectMinimumTouchTarget(
    page.getByRole('button', { name: 'Close filters' }),
    'filter close',
  )
  await expectMinimumTouchTarget(
    page.getByRole('button', { name: 'Clear filters' }),
    'clear filters',
  )
  await page.getByRole('button', { name: 'Close filters' }).click()

  await page.getByRole('button', {
    name: 'More actions for Colon adenocarcinoma',
  }).click()
  await expectMinimumTouchTarget(page.getByRole('menuitem'), 'slide menu')
  await page.keyboard.press('Escape')

  await page.getByRole('checkbox', {
    name: 'Select Colon adenocarcinoma',
  }).check()
  await expectMinimumTouchTarget(
    page.getByRole('toolbar', { name: 'Selection actions' }).getByRole('button'),
    'selection action',
  )
})

test('keeps nested mobile breadcrumb links at least 44 pixels in both axes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin?location=folder:folder-organs')
  await expect(page.getByRole('heading', { name: 'Organ systems' })).toBeVisible()

  const breadcrumb = page.getByRole('navigation', { name: 'Breadcrumb' })
  await expectMinimumTouchTarget(
    breadcrumb.getByRole('button', { name: 'All slides' }),
    'nested breadcrumb',
  )
})

test('keeps the details inspector out of the content grid', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 })
  const mainBefore = await page.locator('.library-main').boundingBox()

  await page.getByRole('button', {
    name: /open details for colon adenocarcinoma/i,
  }).click()
  const inspector = page.getByRole('complementary', { name: 'Slide details' })
  await expect(inspector).toBeVisible()
  await expect(inspector).toHaveAttribute('data-overlay', 'inspector')

  const [mainAfter, inspectorPosition] = await Promise.all([
    page.locator('.library-main').boundingBox(),
    inspector.evaluate((element) => getComputedStyle(element).position),
  ])
  expect(mainAfter).toEqual(mainBefore)
  expect(inspectorPosition).toBe('fixed')
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
  await page.setViewportSize({ width: 901, height: 900 })
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

  const semanticColors = await page.evaluate(() => {
    const probe = document.createElement('span')
    probe.style.backgroundColor = 'var(--surface-elevated)'
    probe.style.color = 'var(--primary)'
    document.body.append(probe)
    const style = getComputedStyle(probe)
    const colors = {
      primary: style.color,
      surfaceElevated: style.backgroundColor,
    }
    probe.remove()
    return colors
  })
  const closeStyle = await page.getByRole('button', { name: 'Close filters' }).evaluate((element) => {
    const style = getComputedStyle(element)
    return {
      color: style.color,
      background: style.backgroundColor,
      width: style.width,
      height: style.height,
    }
  })
  expect(closeStyle.color).not.toBe('rgba(0, 0, 0, 0)')
  expect(closeStyle.background).toBe(semanticColors.surfaceElevated)
  const minimumCloseSize = (page.viewportSize()?.width ?? 0) <= 600 ? 44 : 40
  expect(Number.parseFloat(closeStyle.width)).toBeGreaterThanOrEqual(minimumCloseSize)
  expect(Number.parseFloat(closeStyle.height)).toBeGreaterThanOrEqual(minimumCloseSize)

  const selectVisible = page.getByRole('checkbox', { name: 'Select visible' })
  await expect(selectVisible).toHaveCSS('appearance', 'none')
  await selectVisible.click()
  await expect(selectVisible).toBeChecked()
  await expect(selectVisible).toHaveCSS('background-color', semanticColors.primary)

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
  for (const control of [share, page.locator('.library-upload-button')]) {
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
