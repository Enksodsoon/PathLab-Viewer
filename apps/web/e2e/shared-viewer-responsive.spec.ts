import { expect, test } from '@playwright/test'
import { serveSyntheticDzi, visibleSyntheticLandmark } from './fixtures/syntheticDzi'
import { expectForcedColorsFocus, focusByTabSequence } from './fixtures/forcedColors'

test.describe.configure({ mode: 'serial', timeout: 120_000 })

const manifest = {
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
      teachingNote: '',
      thumbnailUrl: '/thumb/0',
      tileSource: '/tiles/public-1/slide.dzi',
      scale: null,
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
      scale: null,
    },
  ],
}

const publicSlide = {
  publicId: 'public-1',
  displayName: 'HER2 control',
  state: 'published',
  tileSource: '/tiles/public-1/slide.dzi',
  thumbnailUrl: '/thumb/public-1',
  metadata: {
    width: 24970,
    height: 31087,
    physicalSizeX: 0.5476,
    physicalSizeUnit: 'MICROMETER',
  },
}

const privateSlide = {
  id: 'private-1',
  publicId: '',
  displayName: 'Private teaching slide',
  filename: 'private-slide.ome.tiff',
  sourceBytes: 1048576,
  state: 'ready_private',
  errorCode: null,
  errorMessage: null,
  tileSource: '/tiles/private-1/slide.dzi',
  thumbnailUrl: '/thumb/private-1',
  metadata: {
    width: 2048,
    height: 1024,
    physicalSizeX: 0.5,
    physicalSizeUnit: 'MICROMETER',
  },
  createdAt: '2026-07-26T00:00:00Z',
}

test('keeps held canvas arrows in the current shared slide', async ({ page }) => {
  const canvas = page.locator('.openseadragon-canvas[tabindex="0"]')
  await expect(canvas).toHaveCount(1)
  await canvas.focus()
  await page.keyboard.down('ArrowRight')
  await page.keyboard.down('ArrowRight')
  await page.keyboard.up('ArrowRight')
  await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
  await page.getByRole('heading', { name: 'Colon adenocarcinoma' }).click()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('heading', { name: 'Normal colon' })).toBeVisible()
  await canvas.focus()
  await page.keyboard.down('ArrowLeft')
  await page.keyboard.down('ArrowLeft')
  await page.keyboard.up('ArrowLeft')
  await expect(page.getByRole('heading', { name: 'Normal colon' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Normal colon' })).toBeVisible()
})

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v2/public/folders/share-public', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(manifest),
  }))
  await page.route('**/api/v2/public/collections/share-public', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ ...manifest, targetType: 'collection' }),
  }))
  await page.route('**/api/v1/public/slides/public-1', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(publicSlide),
  }))
  await page.route('**/api/v1/admin/slides/private-1', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(privateSlide),
  }))
  for (const path of ['/tiles/public-1/slide', '/tiles/public-2/slide', '/tiles/private-1/slide']) {
    await serveSyntheticDzi(page, {
      path,
      width: 1024,
      height: 768,
      landmarks: [
        { x: 260, y: 180, color: '#f01e1e', radius: 24 },
        { x: 760, y: 580, color: '#1e59f0', radius: 24 },
      ],
    })
  }
  await page.addInitScript(() => {
    const timers = new Set<number>()
    const originalSetInterval = window.setInterval.bind(window)
    const originalClearInterval = window.clearInterval.bind(window)
    window.setInterval = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) => {
      const id = originalSetInterval(handler, timeout, ...args)
      timers.add(id)
      return id
    }) as typeof window.setInterval
    window.clearInterval = ((id?: number) => {
      if (id !== undefined) timers.delete(id)
      return originalClearInterval(id)
    }) as typeof window.clearInterval
    ;(window as Window & { __viewerCycleIntervals?: Set<number> }).__viewerCycleIntervals = timers
  })
  await page.goto('/f/share-public')
  await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible({ timeout: 15_000 })
})

test('keeps the shared viewer usable across desktop and mobile breakpoints', async ({ page }) => {
  test.setTimeout(120_000)
  for (const width of [320, 390, 600, 760, 761, 768, 901, 1024, 1251, 1440, 1584, 1920]) {
    await page.setViewportSize({ width, height: width <= 390 ? 844 : 900 })
    await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
    await expect.poll(() => page.evaluate(() => (
      document.documentElement.scrollWidth <= document.documentElement.clientWidth
    ))).toBe(true)
    await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
    if (width <= 760) {
      const menu = page.getByRole('button', { name: 'Open slide navigator' })
      await expect(menu).toBeVisible()
      await menu.click()
      const rail = page.getByRole('dialog', { name: 'Shared slides' })
      await expect(rail).toBeVisible()
      await rail.getByRole('button', { name: 'Close slide navigator' }).click()
    }
  }
})

test('keeps shared viewer controls visible across the canonical viewport and breakpoint matrix', async ({ page }, info) => {
  const viewports = [
    { width: 320, height: 568 }, { width: 390, height: 844 },
    { width: 568, height: 320 }, { width: 667, height: 375 },
    { width: 768, height: 1024 }, { width: 1024, height: 768 },
    { width: 1280, height: 720 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 },
    { width: 2560, height: 1440 }, { width: 3440, height: 1440 }, { width: 3840, height: 2160 },
    { width: 759, height: 480 }, { width: 760, height: 480 }, { width: 761, height: 480 },
  ]
  const evidence: Array<Record<string, unknown>> = []

  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
    const mobile = viewport.width <= 760
    const control = mobile
      ? page.getByRole('button', { name: 'Open slide navigator' })
      : page.getByRole('button', { name: 'Zoom in' })
    await expect(control).toBeVisible()
    if (mobile) await expect(page.locator('#shared-slide-rail')).toHaveAttribute('inert', '')

    await focusByTabSequence(page, control, mobile ? 'Open slide navigator' : 'Zoom in')
    await expect(control).toBeFocused()

    const layout = await page.evaluate(() => {
      const control = document.activeElement as HTMLElement
      const rect = control.getBoundingClientRect()
      const style = getComputedStyle(control)
      return {
        viewport: { width: innerWidth, height: innerHeight },
        document: { clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth },
        control: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height },
        focus: { focusVisible: control.matches(':focus-visible'), outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth },
      }
    })
    expect(layout.document.scrollWidth, `document overflow at ${viewport.width}x${viewport.height}`).toBeLessThanOrEqual(layout.document.clientWidth)
    expect(layout.control.left).toBeGreaterThanOrEqual(0)
    expect(layout.control.top).toBeGreaterThanOrEqual(0)
    expect(layout.control.right).toBeLessThanOrEqual(viewport.width + 1)
    expect(layout.control.bottom).toBeLessThanOrEqual(viewport.height + 1)
    expect(layout.focus.focusVisible).toBe(true)
    expect(layout.focus.outlineStyle).not.toBe('none')
    expect(Number.parseFloat(layout.focus.outlineWidth)).toBeGreaterThan(0)
    if (mobile) {
      expect(layout.control.width).toBeGreaterThanOrEqual(44)
      expect(layout.control.height).toBeGreaterThanOrEqual(44)
    }
    evidence.push(layout)
  }

  await info.attach('shared-viewer-canonical-viewport-matrix', { body: JSON.stringify(evidence), contentType: 'application/json' })
})

test('checks image geometry and overflow separately at DPR 1, 2, and 3', async ({ page, browser }, info) => {
  test.skip(info.project.name !== 'chromium', 'Device pixel ratio is checked in desktop Chromium contexts.')
  const origin = new URL(page.url()).origin
  const samples: Array<Record<string, unknown>> = []

  for (const deviceScaleFactor of [1, 2, 3]) {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 720 },
      deviceScaleFactor,
    })
    try {
      const dprPage = await context.newPage()
      await dprPage.route('**/api/v2/public/folders/share-public', (route) => route.fulfill({ json: manifest }))
      await dprPage.route('**/api/v1/public/slides/public-1', (route) => route.fulfill({ json: publicSlide }))
      await serveSyntheticDzi(dprPage, {
        path: '/tiles/public-1/slide',
        width: 512,
        height: 384,
        landmarks: [{ x: 128, y: 96, color: '#f01e1e', radius: 22 }],
      })
      await dprPage.goto(`${origin}/f/share-public`)
      await expect(dprPage.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
      await expect.poll(() => visibleSyntheticLandmark(dprPage)).not.toBeNull()

      const landmark = await visibleSyntheticLandmark(dprPage)
      expect(landmark).not.toBeNull()
      const geometry = await dprPage.evaluate(async (visible) => {
        const resource = performance.getEntriesByType('resource').find((entry) => /openseadragon\.js/.test(entry.name))
        if (!resource) throw new Error('OpenSeadragon module was not loaded')
        const OSD = (await import(resource.name)).default
        let host: Element | null = document.querySelector('.openseadragon-canvas')
        let viewer = host ? OSD.getViewer(host) : null
        while (!viewer && host) { host = host.parentElement; viewer = host ? OSD.getViewer(host) : null }
        if (!viewer) throw new Error('OpenSeadragon viewer was not attached')
        const item = viewer.world.getItemAt(0)
        const viewerBounds = viewer.element.getBoundingClientRect()
        const local = new OSD.Point(visible.x - viewerBounds.left, visible.y - viewerBounds.top)
        const imagePoint = item.viewportToImageCoordinates(viewer.viewport.pointFromPixel(local, true), true)
        const expected = new OSD.Point(128, 96)
        const projected = item.imageToViewerElementCoordinates(expected)
        return {
          dpr: window.devicePixelRatio,
          viewport: { width: innerWidth, height: innerHeight },
          document: { width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth },
          image: item.getContentSize(),
          captured: { x: imagePoint.x, y: imagePoint.y },
          projected: { x: viewerBounds.left + projected.x, y: viewerBounds.top + projected.y },
          visible,
        }
      }, landmark!)

      expect(geometry.dpr).toBe(deviceScaleFactor)
      expect(geometry.document.scrollWidth).toBeLessThanOrEqual(geometry.document.width)
      expect(Math.abs(geometry.visible.x - geometry.projected.x)).toBeLessThanOrEqual(1)
      expect(Math.abs(geometry.visible.y - geometry.projected.y)).toBeLessThanOrEqual(1)
      expect(Math.abs(geometry.captured.x - 128)).toBeLessThanOrEqual(1)
      expect(Math.abs(geometry.captured.y - 96)).toBeLessThanOrEqual(1)
      samples.push(geometry)
    } finally {
      await context.close()
    }
  }

  const reference = samples[0] as { captured: { x: number; y: number } }
  for (const sample of samples.slice(1) as Array<{ captured: { x: number; y: number } }>) {
    expect(Math.abs(sample.captured.x - reference.captured.x)).toBeLessThanOrEqual(1)
    expect(Math.abs(sample.captured.y - reference.captured.y)).toBeLessThanOrEqual(1)
  }
  await info.attach('shared-viewer-dpr-geometry', { body: JSON.stringify(samples), contentType: 'application/json' })
})

test('emulates 200% and 400% root-font enlargement independently from browser zoom', async ({ page }, info) => {
  await page.setViewportSize({ width: 320, height: 568 })
  const samples: Array<Record<string, unknown>> = []

  for (const multiplier of [2, 4]) {
    await page.evaluate((scale) => { document.documentElement.style.fontSize = `${scale * 100}%` }, multiplier)
    const textSize = await page.evaluate(() => Number.parseFloat(getComputedStyle(document.body).fontSize))
    expect(textSize).toBeGreaterThanOrEqual(16 * multiplier)
    await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
    const control = page.getByRole('button', { name: 'Open slide navigator' })
    await expect(control).toBeVisible()
    await control.focus()
    await expect(control).toBeFocused()
    const layout = await page.evaluate(() => {
      const element = document.activeElement as HTMLElement
      const box = element.getBoundingClientRect()
      return {
        rootFontSize: getComputedStyle(document.documentElement).fontSize,
        bodyFontSize: getComputedStyle(document.body).fontSize,
        viewport: { width: innerWidth, height: innerHeight },
        document: { width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth },
        control: { left: box.left, top: box.top, right: box.right, bottom: box.bottom },
      }
    })
    expect(layout.document.scrollWidth).toBeLessThanOrEqual(layout.document.width)
    expect(layout.control.left).toBeGreaterThanOrEqual(0)
    expect(layout.control.right).toBeLessThanOrEqual(layout.viewport.width + 1)
    samples.push(layout)
  }

  await info.attach('shared-viewer-root-font-enlargement', { body: JSON.stringify(samples), contentType: 'application/json' })
})

test('keeps the mobile slide drawer modal, keyboard-contained, and restores focus across resize', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const trigger = page.getByRole('button', { name: 'Open slide navigator' })
  const stage = page.locator('.shared-viewer-stage')
  await expect(trigger).toBeVisible()
  await expect(page.locator('#shared-slide-rail')).toHaveAttribute('inert', '')
  await trigger.focus()
  await page.keyboard.press('Enter')

  const drawer = page.getByRole('dialog', { name: 'Shared slides' })
  await expect(drawer).toBeVisible()
  await expect(page.getByRole('button', { name: 'Close slide navigator' })).toBeFocused()
  await expect(stage).toHaveAttribute('inert', '')
  await expect(drawer.getByRole('searchbox', { name: 'Search shared slides' })).toBeVisible()

  await page.keyboard.press('Shift+Tab')
  await expect(drawer.getByRole('button', { name: /Normal colon/ })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(drawer.getByRole('button', { name: 'Close slide navigator' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(drawer).toHaveCount(0)
  await expect(trigger).toBeFocused()

  await trigger.click()
  await expect(page.getByRole('dialog', { name: 'Shared slides' })).toBeVisible()
  await page.setViewportSize({ width: 761, height: 480 })
  await expect(trigger).toBeHidden()
  await expect(page.locator('.shared-viewer-header h1')).toBeFocused()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('moves focus to the navigator trigger when a focused desktop rail is hidden', async ({ page }) => {
  await page.setViewportSize({ width: 761, height: 480 })
  const search = page.getByRole('searchbox', { name: 'Search shared slides' })
  await search.focus()
  await expect(search).toBeFocused()

  await page.setViewportSize({ width: 760, height: 480 })
  await expect(page.locator('#shared-slide-rail')).toHaveAttribute('inert', '')
  await expect(page.getByRole('button', { name: 'Open slide navigator' })).toBeFocused()
})

test('keeps shared slide selection and drawer focus visible in forced colors', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ forcedColors: 'active' })
  const trigger = page.getByRole('button', { name: 'Open slide navigator' })
  await focusByTabSequence(page, trigger, 'Open slide navigator')
  await page.keyboard.press('Enter')
  const drawer = page.getByRole('dialog', { name: 'Shared slides' })
  await expect(drawer).toBeVisible()
  const focus = await expectForcedColorsFocus(
    page,
    drawer.getByRole('button', { name: 'Close slide navigator' }),
    { alreadyFocused: true },
  )
  const dialog = await drawer.evaluate((element) => ({
    color: getComputedStyle(element).color,
    background: getComputedStyle(element).backgroundColor,
    borderColor: getComputedStyle(element).borderTopColor,
    borderWidth: getComputedStyle(element).borderTopWidth,
  }))
  expect(Number.parseFloat(dialog.borderWidth)).toBeGreaterThanOrEqual(2)
  const controlBorders = await page.locator('.shared-viewer-tools button, .share-menu, .share-rail-heading button').evaluateAll((elements) =>
    elements.map((element) => {
      const style = getComputedStyle(element)
      return { borderStyle: style.borderTopStyle, borderWidth: style.borderTopWidth }
    }),
  )
  expect(controlBorders.length).toBeGreaterThan(0)
  for (const border of controlBorders) {
    expect(border.borderStyle).not.toBe('none')
    expect(Number.parseFloat(border.borderWidth)).toBeGreaterThanOrEqual(1)
  }
  await expect(page.getByRole('button', { name: /Colon adenocarcinoma/ })).toHaveAttribute('aria-current', 'page')
  await info.attach('forced-colors-shared-viewer', { body: JSON.stringify({ focus, dialog }), contentType: 'application/json' })
})

test('keeps one viewer, stable handlers and bounded caches through 20 viewport cycles', async ({ page }, info) => {
  test.skip(info.project.name !== 'chromium', 'Viewer lifecycle instrumentation uses Chromium performance APIs.')
  test.setTimeout(90_000)
  await page.setViewportSize({ width: 1440, height: 900 })
  await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()

  const snapshot = async () => page.evaluate(async () => {
    const resource = performance.getEntriesByType('resource').find((entry) => /openseadragon\.js/.test(entry.name))!
    const OSD = (await import(resource.name)).default
    const host = document.querySelector('.openseadragon-container')?.parentElement
    const viewer = host ? OSD.getViewer(host) : null
    if (!viewer) return null
    const globals = window as Window & { __viewerCycleInstance?: unknown; __viewerCycleIntervals?: Set<number> }
    if (!globals.__viewerCycleInstance) globals.__viewerCycleInstance = viewer
    const cache = (viewer as typeof viewer & { tileCache: { _maxCacheItemCount: number; numTilesLoaded(): number; numCachesLoaded(): number } }).tileCache
    const loader = viewer.imageLoader as typeof viewer.imageLoader & { jobsInProgress: number; jobQueue: unknown[] }
    return {
      sameViewer: globals.__viewerCycleInstance === viewer,
      registeredViewers: (OSD as typeof OSD & { _viewers: Map<Element, unknown> })._viewers.size,
      viewerNodes: document.querySelectorAll('.openseadragon-container').length,
      canvasNodes: document.querySelectorAll('.openseadragon-canvas').length,
      openHandlers: viewer.numberOfHandlers('open'),
      tileHandlers: viewer.numberOfHandlers('tile-loaded'),
      animationHandlers: viewer.numberOfHandlers('animation-finish'),
      failureHandlers: viewer.numberOfHandlers('tile-load-failed'),
      activeIntervals: globals.__viewerCycleIntervals?.size ?? -1,
      cacheLimit: cache._maxCacheItemCount,
      cachedTiles: cache.numTilesLoaded(),
      cachedObjects: cache.numCachesLoaded(),
      queueLength: loader.jobQueue.length,
      jobsInProgress: loader.jobsInProgress,
      viewerLoadQueue: (viewer as typeof viewer & { _loadQueue: unknown[] })._loadQueue.length,
      container: { width: viewer.container.clientWidth, height: viewer.container.clientHeight },
      viewport: viewer.viewport.getContainerSize(),
      animating: viewer.isAnimating(),
      memoryBytes: (performance as Performance & { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize ?? null,
    }
  })
  const initial = await snapshot()
  expect(initial).not.toBeNull()
  expect(initial?.viewerNodes).toBeGreaterThanOrEqual(1)
  expect(initial?.registeredViewers).toBeGreaterThanOrEqual(1)
  await expect.poll(() => snapshot()).toMatchObject({ queueLength: 0, jobsInProgress: 0, viewerLoadQueue: 0, animating: false })
  const baseline = await snapshot()
  expect(baseline?.cacheLimit).toBe(100)

  const sizes = [{ width: 390, height: 844 }, { width: 1440, height: 900 }]
  for (let cycle = 0; cycle < 20; cycle += 1) {
    const size = sizes[cycle % 2]
    await page.setViewportSize(size)
    await expect.poll(async () => {
      const state = await snapshot()
      return state && !state.animating && state.container.width === state.viewport.x && state.container.height === state.viewport.y
    }, { timeout: 10_000 }).toBe(true)
    await expect(page.locator('.openseadragon-container')).toHaveCount(baseline!.viewerNodes)
    await expect(page.locator('.openseadragon-canvas')).toHaveCount(baseline!.canvasNodes)
  }
  await expect.poll(() => snapshot()).toMatchObject({ queueLength: 0, jobsInProgress: 0, viewerLoadQueue: 0, animating: false })
  const final = await snapshot()
  expect(final?.sameViewer).toBe(true)
  expect(final?.viewerNodes).toBe(baseline?.viewerNodes)
  expect(final?.registeredViewers).toBe(baseline?.registeredViewers)
  expect(final?.canvasNodes).toBe(baseline?.canvasNodes)
  expect(final?.cacheLimit).toBe(100)
  expect(final?.activeIntervals).toBe(baseline?.activeIntervals)
  expect(final?.openHandlers).toBe(baseline?.openHandlers)
  expect(final?.tileHandlers).toBe(baseline?.tileHandlers)
  expect(final?.animationHandlers).toBe(baseline?.animationHandlers)
  expect(final?.failureHandlers).toBe(baseline?.failureHandlers)
  expect(final?.cachedObjects).toBeLessThanOrEqual(200)
  const evidence = { initial, baseline, final, alternatingViewports: 20, note: 'Cache object and memory counts are diagnostic; the configured image cache limit is asserted.' }
  console.log('Viewer resize-cycle evidence:', JSON.stringify(evidence))
  await info.attach('viewer-resize-cycle', { body: JSON.stringify(evidence), contentType: 'application/json' })
})

test('switches slides without replacing the public route', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
  await page.getByRole('button', { name: 'Next slide' }).click()
  await expect(page.getByRole('heading', { name: 'Normal colon' })).toBeVisible()
  await expect(page).toHaveURL(/\/f\/share-public$/)
})

test('switches complete viewer chrome themes without filtering pathology imagery', async ({ page }) => {
  const themeControl = page.getByRole('group', { name: 'Theme preference' })
  await expect(themeControl).toBeVisible()

  await page.getByRole('radio', { name: 'Light' }).check()
  const lightChrome = await page.evaluate(() => ({
    rootTheme: document.documentElement.dataset.theme,
    shell: getComputedStyle(document.querySelector('.shared-viewer-shell')!).backgroundColor,
    header: getComputedStyle(document.querySelector('.shared-viewer-header')!).backgroundColor,
    rail: getComputedStyle(document.querySelector('.share-slide-rail')!).backgroundColor,
    stage: getComputedStyle(document.querySelector('.shared-viewer-stage')!).backgroundColor,
    imageSurfaceFilter: getComputedStyle(document.querySelector('.viewer-poster, .openseadragon-canvas')!).filter,
  }))

  await page.getByRole('radio', { name: 'Dark' }).check()
  const darkChrome = await page.evaluate(() => ({
    rootTheme: document.documentElement.dataset.theme,
    shell: getComputedStyle(document.querySelector('.shared-viewer-shell')!).backgroundColor,
    header: getComputedStyle(document.querySelector('.shared-viewer-header')!).backgroundColor,
    rail: getComputedStyle(document.querySelector('.share-slide-rail')!).backgroundColor,
    stage: getComputedStyle(document.querySelector('.shared-viewer-stage')!).backgroundColor,
    imageSurfaceFilter: getComputedStyle(document.querySelector('.viewer-poster, .openseadragon-canvas')!).filter,
  }))

  expect(lightChrome.rootTheme).toBe('light')
  expect(darkChrome.rootTheme).toBe('dark')
  expect(lightChrome.shell).not.toBe(darkChrome.shell)
  expect(lightChrome.header).not.toBe(darkChrome.header)
  expect(lightChrome.rail).not.toBe(darkChrome.rail)
  expect(lightChrome.stage).toBe('rgb(9, 8, 7)')
  expect(darkChrome.stage).toBe(lightChrome.stage)
  expect(lightChrome.imageSurfaceFilter).toBe('none')
  expect(darkChrome.imageSurfaceFilter).toBe('none')
})

test('keeps collection routes usable at desktop and mobile sizes', async ({ page }) => {
  await page.goto('/c/share-public')
  await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()

  for (const width of [390, 1024]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await expect.poll(() => page.evaluate(() => (
      document.documentElement.scrollWidth <= document.documentElement.clientWidth
    ))).toBe(true)
    await expect(page.getByRole('group', { name: 'Theme preference' })).toBeVisible()
  }
  await expect(page).toHaveURL(/\/c\/share-public$/)
})

test('keeps private and individual public imagery invariant across themes and widths', async ({ page }) => {
  test.setTimeout(120_000)

  const routes = [
    { path: '/s/public-1', title: 'HER2 control' },
    { path: '/admin/preview/private-1', title: 'Private teaching slide' },
  ]

  for (const route of routes) {
    for (const width of [390, 1584]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 992 })
      await page.goto(route.path)
      await expect(page.getByText(route.title, { exact: true })).toBeVisible()
      await expect(page.getByRole('group', { name: 'Theme preference' })).toBeVisible()

      await page.getByRole('radio', { name: 'Light' }).check()
      const light = await page.evaluate(() => ({
        theme: document.documentElement.dataset.theme,
        header: getComputedStyle(document.querySelector('.viewer-header')!).backgroundColor,
        stage: getComputedStyle(document.querySelector('.viewer-stage')!).backgroundColor,
        stageFilter: getComputedStyle(document.querySelector('.viewer-stage')!).filter,
        surface: getComputedStyle(document.querySelector('.osd-surface')!).backgroundColor,
        surfaceFilter: getComputedStyle(document.querySelector('.osd-surface')!).filter,
        imageFilters: [...document.querySelectorAll('.viewer-poster, .openseadragon-canvas canvas')].map((element) => getComputedStyle(element).filter),
        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      }))

      await page.getByRole('radio', { name: 'Dark' }).check()
      const dark = await page.evaluate(() => ({
        theme: document.documentElement.dataset.theme,
        header: getComputedStyle(document.querySelector('.viewer-header')!).backgroundColor,
        stage: getComputedStyle(document.querySelector('.viewer-stage')!).backgroundColor,
        stageFilter: getComputedStyle(document.querySelector('.viewer-stage')!).filter,
        surface: getComputedStyle(document.querySelector('.osd-surface')!).backgroundColor,
        surfaceFilter: getComputedStyle(document.querySelector('.osd-surface')!).filter,
        imageFilters: [...document.querySelectorAll('.viewer-poster, .openseadragon-canvas canvas')].map((element) => getComputedStyle(element).filter),
        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      }))

      expect(light.theme).toBe('light')
      expect(dark.theme).toBe('dark')
      expect(light.header).not.toBe(dark.header)
      expect(light.stage).toBe('rgb(9, 8, 7)')
      expect(dark.stage).toBe(light.stage)
      expect(light.surface).toBe(light.stage)
      expect(dark.surface).toBe(light.stage)
      expect(light.stageFilter).toBe('none')
      expect(dark.stageFilter).toBe('none')
      expect(light.surfaceFilter).toBe('none')
      expect(dark.surfaceFilter).toBe('none')
      expect(light.imageFilters.every((filter) => filter === 'none')).toBe(true)
      expect(dark.imageFilters.every((filter) => filter === 'none')).toBe(true)
      expect(light.overflow).toBe(false)
      expect(dark.overflow).toBe(false)
      await expect(page).toHaveURL(new RegExp(`${route.path}$`))
      await expect(page.getByRole('button', { name: 'Zoom in' })).toBeVisible()
      await expect(page.getByRole('combobox', { name: 'Loading mode' })).toBeVisible()

      if (width === 390) {
        for (const name of ['Zoom in', 'Zoom out', 'Home view', 'Fullscreen']) {
          const box = await page.getByRole('button', { name }).boundingBox()
          expect(box?.width).toBeGreaterThanOrEqual(44)
          expect(box?.height).toBeGreaterThanOrEqual(44)
        }
        const loadingMode = await page.getByRole('combobox', { name: 'Loading mode' }).boundingBox()
        expect(loadingMode?.height).toBeGreaterThanOrEqual(44)
      }
    }
  }
})

test('keeps mobile offline status clear of the loading control', async ({ page }) => {
  test.setTimeout(60_000)
  const routes = [
    { path: '/s/public-1', title: 'HER2 control', tileId: 'public-1' },
    { path: '/admin/preview/private-1', title: 'Private teaching slide', tileId: 'private-1' },
  ]
  const failedTileUrls = new Set<string>()

  await page.unroute('**/slide.dzi')
  await page.route('**/slide.dzi', (route) => route.fulfill({
    contentType: 'application/xml',
    body: '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" TileSize="128" Overlap="1" Format="jpg"><Size Width="1024" Height="768"/></Image>',
  }))
  await page.route('**/slide_files/**', async (route) => {
    failedTileUrls.add(route.request().url())
    await route.abort()
  })
  await page.goto('about:blank')
  failedTileUrls.clear()
  await page.setViewportSize({ width: 390, height: 844 })

  for (const route of routes) {
    await page.goto(route.path)
    await expect(page.getByText(route.title, { exact: true })).toBeVisible()
    await expect.poll(() => [...failedTileUrls].filter((url) => (
      new URL(url).pathname.startsWith(`/tiles/${route.tileId}/slide_files/`)
    )).length, { timeout: 10_000 }).toBeGreaterThanOrEqual(3)
    await expect(page.getByRole('alert')).toHaveText(/Slide tiles could not be loaded/, { timeout: 10_000 })
    await page.evaluate(() => window.dispatchEvent(new Event('offline')))

    const loadingMode = page.locator('.viewer-loading-mode')
    const connectionStatus = page.getByRole('status')
    await expect(connectionStatus).toHaveText(/Offline/)

    const [loadingBox, statusBox] = await Promise.all([
      loadingMode.boundingBox(),
      connectionStatus.boundingBox(),
    ])
    if (!loadingBox || !statusBox) throw new Error(`Missing viewer overlay geometry on ${route.path}`)

    const rectanglesIntersect = (
      loadingBox.x < statusBox.x + statusBox.width
      && loadingBox.x + loadingBox.width > statusBox.x
      && loadingBox.y < statusBox.y + statusBox.height
      && loadingBox.y + loadingBox.height > statusBox.y
    )

    expect(loadingBox.y + loadingBox.height).toBeLessThanOrEqual(statusBox.y)
    expect(rectanglesIntersect).toBe(false)
    expect(statusBox.x).toBeGreaterThanOrEqual(0)
    expect(statusBox.y).toBeGreaterThanOrEqual(0)
    expect(statusBox.x + statusBox.width).toBeLessThanOrEqual(390)
    expect(statusBox.y + statusBox.height).toBeLessThanOrEqual(844)
  }
})


test('starts a newly selected shared slide at its native rotation', async ({ page }) => {
  const rotation = page.getByRole('button', { name: /Open rotation controls/ })
  await rotation.click()
  await page.getByRole('button', { name: 'Rotate to 90 degrees' }).click()
  await expect(rotation).toHaveAccessibleName('Open rotation controls. Current rotation 90 degrees')
  await page.getByRole('button', { name: 'Next slide' }).click()
  await expect(page.getByRole('heading', { name: 'Normal colon' })).toBeVisible()
  const actualRotation = await page.evaluate(async () => {
    const resource = performance.getEntriesByType('resource').find((entry) => entry.name.includes('/openseadragon.js'))!
    const { default: OpenSeadragon } = await import(resource.name)
    return OpenSeadragon.getViewer(document.querySelector('.openseadragon-container')!.parentElement).viewport.getRotation()
  })
  expect(actualRotation).toBe(0)
  await expect(rotation).toHaveAccessibleName('Open rotation controls. Current rotation 0 degrees')
})
