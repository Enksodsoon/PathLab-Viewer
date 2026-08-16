import { expect, test } from '@playwright/test'

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
  await page.route('**/slide.dzi', (route) => route.fulfill({
    contentType: 'application/xml',
    body: '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" TileSize="512" Overlap="1" Format="jpg"><Size Width="1024" Height="768"/></Image>',
  }))
  await page.goto('/f/share-public')
})

test('keeps the shared viewer usable across desktop and mobile breakpoints', async ({ page }) => {
  test.setTimeout(120_000)
  for (const width of [320, 390, 600, 760, 761, 768, 901, 1024, 1251, 1440, 1584, 1920]) {
    await page.setViewportSize({ width, height: width <= 390 ? 844 : 900 })
    await page.goto('/f/share-public')
    await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
    await expect.poll(() => page.evaluate(() => (
      document.documentElement.scrollWidth <= document.documentElement.clientWidth
    ))).toBe(true)
    await expect(page.getByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
    if (width <= 760) {
      const menu = page.getByRole('button', { name: 'Open slide navigator' })
      await expect(menu).toBeVisible()
      await menu.click()
      const rail = page.getByRole('complementary', { name: 'Shared slides' })
      await expect(rail).toBeVisible()
      await rail.getByRole('button', { name: 'Close slide navigator' }).click()
    }
  }
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
    posterFilter: getComputedStyle(document.querySelector('.viewer-poster')!).filter,
  }))

  await page.getByRole('radio', { name: 'Dark' }).check()
  const darkChrome = await page.evaluate(() => ({
    rootTheme: document.documentElement.dataset.theme,
    shell: getComputedStyle(document.querySelector('.shared-viewer-shell')!).backgroundColor,
    header: getComputedStyle(document.querySelector('.shared-viewer-header')!).backgroundColor,
    rail: getComputedStyle(document.querySelector('.share-slide-rail')!).backgroundColor,
    stage: getComputedStyle(document.querySelector('.shared-viewer-stage')!).backgroundColor,
    posterFilter: getComputedStyle(document.querySelector('.viewer-poster')!).filter,
  }))

  expect(lightChrome.rootTheme).toBe('light')
  expect(darkChrome.rootTheme).toBe('dark')
  expect(lightChrome.shell).not.toBe(darkChrome.shell)
  expect(lightChrome.header).not.toBe(darkChrome.header)
  expect(lightChrome.rail).not.toBe(darkChrome.rail)
  expect(lightChrome.stage).toBe('rgb(9, 8, 7)')
  expect(darkChrome.stage).toBe(lightChrome.stage)
  expect(lightChrome.posterFilter).toBe('none')
  expect(darkChrome.posterFilter).toBe('none')
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
        posterFilter: getComputedStyle(document.querySelector('.viewer-poster')!).filter,
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
        posterFilter: getComputedStyle(document.querySelector('.viewer-poster')!).filter,
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
      expect(light.posterFilter).toBe('none')
      expect(dark.posterFilter).toBe('none')
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
  const routes = [
    { path: '/s/public-1', title: 'HER2 control' },
    { path: '/admin/preview/private-1', title: 'Private teaching slide' },
  ]
  let failedTileRequests = 0

  await page.route('**/slide_files/**', async (route) => {
    failedTileRequests += 1
    await route.fulfill({
      status: 503,
      contentType: 'text/plain',
      body: 'offline tile fixture',
    })
  })
  await page.setViewportSize({ width: 390, height: 844 })

  for (const route of routes) {
    const failuresBeforeNavigation = failedTileRequests
    await page.goto(route.path)
    await expect(page.getByText(route.title, { exact: true })).toBeVisible()
    await expect.poll(() => failedTileRequests).toBeGreaterThanOrEqual(failuresBeforeNavigation + 3)
    await expect(page.getByRole('alert')).toHaveText(/Slide tiles could not be loaded/)
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
