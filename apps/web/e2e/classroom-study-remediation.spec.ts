import { expect, test, type Page } from '@playwright/test'
import { serveSyntheticDzi, visibleSyntheticLandmark } from './fixtures/syntheticDzi'
import { expectForcedColorsFocus } from './fixtures/forcedColors'

test.setTimeout(60_000)
const sizes = [{ width: 320, height: 740 }, { width: 768, height: 1024 }, { width: 740, height: 360 }]
const slide = { id: 'slide', position: 0, displayName: 'Synthetic geometry slide', assetVersion: 'v1', tileSource: '/qa/slide.dzi', width: 256, height: 256, tileSize: 256, format: 'png', folderPath: ['Synthetic'] }
const study = { csrfToken: 'synthetic-study-csrf', pseudonym: 'SYNTHETIC', course: { id: 'qa-course', title: 'Synthetic course', status: 'active', endsAt: null }, pack: { schema: 'pathlab.study-pack/1', title: 'Synthetic pack', slides: [{ viewerSlideId: 'slide', displayName: slide.displayName, tileSource: slide.tileSource }], tasks: [{ id: 'spatial', type: 'spatial', slideId: 'slide', prompt: 'Select a synthetic region', hints: ['Faculty hint'] }, { id: 'choice', type: 'multiple-choice', slideId: 'slide', prompt: 'Choose synthetic answer', options: ['Synthetic A', 'Synthetic B'], hints: [] }] }, progress: [], ai: { eligible: false } }
const classroom = { session: { id: 'qa-session', status: 'active', phase: 'live', publicId: 'qa-public' }, participant: { id: 'qa-participant', alias: 'SYNTHETIC-1' }, csrfToken: 'synthetic-classroom-csrf', stateVersion: 1, presenter: { sequence: 0, slideId: 'slide', viewport: null }, control: { isController: false, requested: false, leaseId: null, controlEpoch: 0, expiresAt: null }, slides: [slide], pendingQuestionIds: [], activePin: null, teacherPointer: null, teachingAnnotations: [] }
async function tiles(page: Page) {
  const tile = await page.evaluate(() => { const canvas = document.createElement('canvas'); canvas.width = 256; canvas.height = 256; const ctx = canvas.getContext('2d')!; ctx.fillStyle = '#eecfc3'; ctx.fillRect(0, 0, 256, 256); ctx.fillStyle = '#995d75'; for (let x = 20; x < 256; x += 40) for (let y = 20; y < 256; y += 40) { ctx.beginPath(); ctx.arc(x, y, 8, 0, 7); ctx.fill() } return canvas.toDataURL('image/png').split(',')[1] })
  await page.route('**/qa/slide.dzi*', (route) => route.fulfill({ contentType: 'application/xml', body: '<Image TileSize="256" Overlap="0" Format="png" xmlns="http://schemas.microsoft.com/deepzoom/2008"><Size Width="256" Height="256"/></Image>' }))
  await page.route('**/qa/slide_files/**', (route) => route.fulfill({ contentType: 'image/png', body: Buffer.from(tile, 'base64') }))
}
async function currentViewerZoom(page: Page) {
  return page.evaluate(async () => {
    const resource = performance.getEntriesByType('resource').find((entry) => /openseadragon\.js/.test(entry.name))
    if (!resource) return null
    const OSD = (await import(resource.name)).default
    let element: Element | null = document.querySelector('.openseadragon-canvas')
    let viewer = element ? OSD.getViewer(element) : null
    while (!viewer && element) { element = element.parentElement; viewer = element ? OSD.getViewer(element) : null }
    return viewer?.viewport.getZoom(true) ?? null
  })
}
async function waitForViewerSettled(page: Page) {
  await expect.poll(() => page.evaluate(async () => {
    const resource = performance.getEntriesByType('resource').find((entry) => /openseadragon\.js/.test(entry.name))
    if (!resource) return false
    const OSD = (await import(resource.name)).default
    let element: Element | null = document.querySelector('.openseadragon-canvas')
    let viewer = element ? OSD.getViewer(element) : null
    while (!viewer && element) { element = element.parentElement; viewer = element ? OSD.getViewer(element) : null }
    if (!viewer) return false
    const size = viewer.viewport.getContainerSize()
    return !viewer.isAnimating() && size.x === viewer.container.clientWidth && size.y === viewer.container.clientHeight
  }), { timeout: 10_000 }).toBe(true)
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
}
async function syntheticLandmarkGeometry(page: Page, source: { x: number; y: number }) {
  return page.evaluate(async (sourcePoint) => {
    const canvas = [...document.querySelectorAll('.openseadragon-canvas canvas')].find((candidate) => candidate.width && candidate.height)!
    const pixels = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height)
    let totalX = 0; let totalY = 0; let count = 0
    for (let y = 0; y < pixels.height; y += 1) for (let x = 0; x < pixels.width; x += 1) {
      const offset = (y * pixels.width + x) * 4
      if (pixels.data[offset] > 220 && pixels.data[offset + 1] < 90 && pixels.data[offset + 2] < 90) { totalX += x; totalY += y; count += 1 }
    }
    const red = { x: totalX / count / canvas.width, y: totalY / count / canvas.height }
    const resource = performance.getEntriesByType('resource').find((entry) => /openseadragon\.js/.test(entry.name))!
    const OSD = (await import(resource.name)).default
    let element: Element | null = document.querySelector('.openseadragon-canvas')
    let viewer = element ? OSD.getViewer(element) : null
    while (!viewer && element) { element = element.parentElement; viewer = element ? OSD.getViewer(element) : null }
    const item = viewer!.world.getItemAt(0)
    const point = new OSD.Point(sourcePoint.x, sourcePoint.y)
    const projection = item.imageToViewerElementCoordinates(point)
    const canvasBounds = viewer!.canvas.getBoundingClientRect()
    const elementBounds = viewer!.element.getBoundingClientRect()
    const containerBounds = viewer!.container.getBoundingClientRect()
    const visible = { x: canvasBounds.left + red.x * canvasBounds.width, y: canvasBounds.top + red.y * canvasBounds.height }
    const toImage = (x: number, y: number) => {
      const image = item.viewportToImageCoordinates(viewer!.viewport.pointFromPixel(new OSD.Point(x, y), true), true)
      return { x: image.x, y: image.y }
    }
    const pagePoint = new OSD.Point(visible.x + scrollX, visible.y + scrollY)
    const windowImage = item.windowToImageCoordinates(pagePoint)
    return {
      source: sourcePoint,
      visible,
      projectionFromViewerElement: { x: elementBounds.left + projection.x, y: elementBounds.top + projection.y },
      projectionFromContainer: { x: containerBounds.left + projection.x, y: containerBounds.top + projection.y },
      projectionFromCanvas: { x: canvasBounds.left + projection.x, y: canvasBounds.top + projection.y },
      visibleToImage: toImage(visible.x - canvasBounds.left, visible.y - canvasBounds.top),
      windowToImage: { x: windowImage.x, y: windowImage.y },
      eventCoordinates: { localX: visible.x - canvasBounds.left, localY: visible.y - canvasBounds.top },
      bounds: {
        viewerElement: { left: elementBounds.left, top: elementBounds.top, width: elementBounds.width, height: elementBounds.height },
        container: { left: containerBounds.left, top: containerBounds.top, width: containerBounds.width, height: containerBounds.height },
        canvas: { left: canvasBounds.left, top: canvasBounds.top, width: canvasBounds.width, height: canvasBounds.height },
        viewport: viewer!.viewport.getContainerSize(),
      },
      camera: { zoom: viewer!.viewport.getZoom(true), animating: viewer!.isAnimating() },
      redPixels: count,
    }
  }, source)
}
async function noOverflow(page: Page) { const result = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth, offenders: [...document.querySelectorAll('*')].filter((el) => el.getBoundingClientRect().right > innerWidth + 1).slice(0, 8).map((el) => ({ tag: el.tagName, class: el.className, right: el.getBoundingClientRect().right })) })); expect(result.scroll, JSON.stringify(result)).toBeLessThanOrEqual(result.width + 1) }
async function contrast(page: Page, selector: string) {
  const colors = await page.locator(selector).first().evaluate((el) => {
    const luminance = (color: string) => { const values = color.match(/[\d.]+/g)!.slice(0, 3).map(Number).map((n) => { const x = n / 255; return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4 }); return values[0] * .2126 + values[1] * .7152 + values[2] * .0722 }
    let surface: Element | null = el
    while (surface && getComputedStyle(surface).backgroundColor === 'rgba(0, 0, 0, 0)') surface = surface.parentElement
    const a = luminance(getComputedStyle(el).color)
    const b = luminance(getComputedStyle(surface ?? document.documentElement).backgroundColor)
    return { foreground: getComputedStyle(el).color, background: getComputedStyle(surface ?? document.documentElement).backgroundColor, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05) }
  })
  expect(colors.ratio).toBeGreaterThanOrEqual(4.5)
  return colors
}
async function denyStorage(page: Page) { await page.addInitScript(() => { for (const method of ['getItem', 'setItem', 'removeItem']) Object.defineProperty(Storage.prototype, method, { configurable: true, value: () => { throw new DOMException('Synthetic storage denial', 'SecurityError') } }) }) }

test('Study captures a rendered non-square landmark after pan, zoom, and orientation changes', async ({ page }, info) => {
  test.skip(info.project.name !== 'chromium', 'Pixel-based landmark alignment uses one desktop Chromium sample.')
  const servedTiles = await serveSyntheticDzi(page, {
    path: '/qa/non-square',
    width: 1024,
    height: 512,
    landmarks: [{ x: 256, y: 128, color: '#f01e1e', radius: 20 }],
  })
  const geometryStudy = {
    ...study,
    pack: {
      ...study.pack,
      slides: [{ ...study.pack.slides[0], tileSource: '/qa/non-square.dzi' }],
      tasks: [study.pack.tasks[0]],
    },
  }
  let submitted: { x?: number; y?: number } | null = null
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url()).pathname
    if (url.endsWith('/study/session')) return route.fulfill({ status: 401, json: { detail: { code: 'STUDY_SESSION_REQUIRED' } } })
    if (url.endsWith('/study/redeem')) return route.fulfill({ json: geometryStudy })
    if (url.endsWith('/tasks/spatial/submit')) {
      expect(route.request().headers()['x-study-csrf']).toBe('synthetic-study-csrf')
      submitted = route.request().postDataJSON()
      return route.fulfill({ json: { taskId: 'spatial', status: 'completed', correct: true, attemptCount: 1, explanation: 'Synthetic landmark captured', sources: [], hints: [] } })
    }
    return route.fulfill({ json: {} })
  })

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/study')
  await page.getByLabel('One-time invitation code').fill('issued_Ab-cd0123456789CODE')
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Enter Study Mode' }).click()
  await expect(page.getByRole('heading', { name: 'Select a synthetic region' })).toBeVisible()
  await expect(page.locator('.openseadragon-canvas canvas').first()).toBeVisible()
  await expect.poll(() => servedTiles.length).toBeGreaterThan(0)
  await expect.poll(async () => visibleSyntheticLandmark(page)).not.toBeNull()
  const canvas = page.locator('.openseadragon-canvas[tabindex="0"]')
  await canvas.scrollIntoViewIfNeeded()

  await page.getByRole('button', { name: 'Request faculty hint' }).click()
  await page.getByLabel('4: Confident').check()
  let marker = await visibleSyntheticLandmark(page)
  expect(marker).not.toBeNull()
  const zoomBefore = await currentViewerZoom(page)
  await canvas.focus()
  await page.keyboard.press('Equal')
  await expect.poll(() => currentViewerZoom(page)).toBeGreaterThan(zoomBefore!)
  await waitForViewerSettled(page)
  marker = await visibleSyntheticLandmark(page)
  expect(marker).not.toBeNull()
  const geometrySamples = [{ step: 'zoom', geometry: await syntheticLandmarkGeometry(page, { x: 256, y: 128 }) }]

  for (const viewport of [
    { width: 844, height: 390 },
    { width: 768, height: 1024 },
    { width: 740, height: 360 },
  ]) {
    await page.setViewportSize(viewport)
    await waitForViewerSettled(page)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    await expect(page.getByLabel('4: Confident')).toBeChecked()
    await expect(page.getByText(/Hint 1:/)).toBeVisible()
    geometrySamples.push({ step: `resize-${viewport.width}x${viewport.height}`, geometry: await syntheticLandmarkGeometry(page, { x: 256, y: 128 }) })
  }

  await canvas.scrollIntoViewIfNeeded()
  marker = await visibleSyntheticLandmark(page)
  expect(marker).not.toBeNull()
  const canvasBounds = await canvas.boundingBox()
  expect(canvasBounds).not.toBeNull()
  await page.mouse.move(marker!.x, marker!.y)
  await page.mouse.down()
  await page.mouse.move(marker!.x + 24, marker!.y + 12, { steps: 4 })
  await page.mouse.up()
  await waitForViewerSettled(page)
  await expect.poll(async () => {
    const position = await visibleSyntheticLandmark(page)
    return position ? Math.hypot(position.x - marker!.x, position.y - marker!.y) : 0
  }).toBeGreaterThan(4)

  const geometryAfterPan = await syntheticLandmarkGeometry(page, { x: 256, y: 128 })
  geometrySamples.push({ step: 'pan', geometry: geometryAfterPan })
  expect(Math.hypot(geometryAfterPan.visible.x - geometryAfterPan.projectionFromCanvas.x, geometryAfterPan.visible.y - geometryAfterPan.projectionFromCanvas.y)).toBeLessThanOrEqual(1)
  await page.screenshot({ path: info.outputPath('study-marker-before-selection.png') })
  await page.evaluate(() => {
    const resource = performance.getEntriesByType('resource').find((entry) => /openseadragon\.js/.test(entry.name))
    ;(window as Window & { __studyPointProbe?: unknown }).__studyPointProbe = null
    ;(window as Window & { __studyPointProbeReady?: boolean }).__studyPointProbeReady = false
    void (async () => {
      const OSD = (await import(resource!.name)).default
      let viewerElement: Element | null = document.querySelector('.openseadragon-canvas')
      let viewer = viewerElement ? OSD.getViewer(viewerElement) : null
      while (!viewer && viewerElement) { viewerElement = viewerElement.parentElement; viewer = viewerElement ? OSD.getViewer(viewerElement) : null }
      if (!viewer) throw new Error('OpenSeadragon viewer was not attached to the canvas tree')
      viewer.addHandler('canvas-click', (event: {
        position: { x: number; y: number }
        originalEvent: { clientX: number; clientY: number; pageX: number; pageY: number }
      }) => {
        const item = viewer.world.getItemAt(0)
        const fromEvent = item.viewportToImageCoordinates(viewer.viewport.pointFromPixel(event.position, true), true)
        const pagePoint = new OSD.Point(event.originalEvent.pageX, event.originalEvent.pageY)
        const fromWindow = item.windowToImageCoordinates(pagePoint)
        ;(window as Window & { __studyPointProbe?: unknown }).__studyPointProbe = {
          eventPosition: { x: event.position.x, y: event.position.y },
          eventClient: { x: event.originalEvent.clientX, y: event.originalEvent.clientY },
          eventPage: { x: event.originalEvent.pageX, y: event.originalEvent.pageY },
          viewportContainer: viewer.viewport.getContainerSize(),
          imageSize: item.getContentSize(),
          mappedImage: { x: fromEvent.x, y: fromEvent.y },
          windowImage: { x: fromWindow.x, y: fromWindow.y },
          viewerElementBounds: (() => { const r = viewer.element.getBoundingClientRect(); return { left: r.left, top: r.top, width: r.width, height: r.height } })(),
          viewerContainerBounds: (() => { const r = viewer.container.getBoundingClientRect(); return { left: r.left, top: r.top, width: r.width, height: r.height } })(),
          canvasBounds: (() => { const r = viewer.canvas.getBoundingClientRect(); return { left: r.left, top: r.top, width: r.width, height: r.height } })(),
        }
      })
      ;(window as Window & { __studyPointProbeReady?: boolean }).__studyPointProbeReady = true
    })()
  })
  await expect.poll(() => page.evaluate(() => (window as Window & { __studyPointProbeReady?: boolean }).__studyPointProbeReady)).toBe(true)
  await page.mouse.click(geometryAfterPan.projectionFromCanvas.x, geometryAfterPan.projectionFromCanvas.y)
  const pointProbeResult = await page.evaluate(() => (window as Window & { __studyPointProbe?: unknown }).__studyPointProbe)
  console.log('Study landmark transform evidence:', JSON.stringify({ samples: geometrySamples, clickedLandmarkProjection: geometryAfterPan.projectionFromCanvas, event: pointProbeResult }))
  await info.attach('study-canvas-coordinate-probe', { body: JSON.stringify({ samples: geometrySamples, clickedLandmarkProjection: geometryAfterPan.projectionFromCanvas, event: pointProbeResult }), contentType: 'application/json' })
  await expect(page.getByText('Region selected at 0.250, 0.250')).toBeVisible()
  await page.getByRole('button', { name: 'Check answer' }).click()
  await expect(page.getByText('Synthetic landmark captured')).toBeVisible()
  expect(submitted).not.toBeNull()
  console.log('Study submitted landmark coordinate:', JSON.stringify(submitted))
  expect(Math.abs(submitted!.x! - 0.25)).toBeLessThanOrEqual(1 / 1024)
  expect(Math.abs(submitted!.y! - 0.25)).toBeLessThanOrEqual(1 / 512)
  await info.attach('study-nonsquare-landmark', { body: JSON.stringify({ expectedSourcePoint: { x: 256, y: 128 }, submitted, servedTiles: servedTiles.slice(0, 10), viewport: '740x360' }), contentType: 'application/json' })
  await page.screenshot({ path: info.outputPath('study-nonsquare-landmark.png'), fullPage: false })
})

test('Study actual invitation, denied storage, spatial target, keyboard confidence and released feedback', async ({ page }, info) => {
  await denyStorage(page)
  await tiles(page)
  let entered = false
  let failures = 1
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url()).pathname
    if (url.endsWith('/study/session')) return route.fulfill({ status: 401, json: { detail: { code: 'STUDY_SESSION_REQUIRED' } } })
    if (url.endsWith('/study/redeem')) {
      if (route.request().postDataJSON().code !== 'issued_Ab-cd0123456789CODE') return route.fulfill({ status: 403, json: { detail: { code: 'STUDY_INVITATION_INVALID' } } })
      entered = true; return route.fulfill({ json: study })
    }
    if (url.endsWith('/submit')) {
      expect(entered).toBe(true)
      expect(route.request().headers()['x-study-csrf']).toBe('synthetic-study-csrf')
      if (failures-- > 0) return route.fulfill({ status: 503, json: { detail: { code: 'SYNTHETIC_SAVE_FAILURE' } } })
      return route.fulfill({ json: { taskId: 'spatial', status: 'completed', correct: true, attemptCount: 1, explanation: 'Released faculty feedback', sources: [], hints: [] } })
    }
    return route.fulfill({ json: {} })
  })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/study')
  await page.getByLabel('One-time invitation code').fill('wrong-issued-code-0123456')
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Enter Study Mode' }).click()
  await expect(page.getByRole('alert')).toContainText('STUDY_INVITATION_INVALID')
  await page.getByLabel('One-time invitation code').fill('issued_Ab-cd0123456789CODE')
  await page.getByRole('button', { name: 'Enter Study Mode' }).click()
  await expect(page.getByRole('heading', { name: 'Select a synthetic region' })).toBeVisible()
  await expect(page.locator('.openseadragon-canvas canvas').first()).toBeVisible()
  for (const size of sizes) for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.setViewportSize(size)
    if (info.project.name === 'mobile-chromium') await page.getByRole('button', { name: 'Select centre of visible field' }).tap()
    else await page.getByRole('button', { name: 'Select centre of visible field' }).click()
    await expect(page.getByLabel('Your selected region pinned this point')).toBeVisible()
    expect(await page.getByLabel('Your selected region pinned this point').locator('span').evaluate((el) => el.getBoundingClientRect().width)).toBeGreaterThanOrEqual(28)
    await page.getByLabel('4: Confident').focus()
    await page.keyboard.press('Space')
    await expect(page.getByLabel('4: Confident')).toBeChecked()
    await noOverflow(page)
    await info.attach(`study-contrast-${size.width}-${theme}`, { body: JSON.stringify(await contrast(page, '.study-task')), contentType: 'application/json' })
    await page.screenshot({ path: info.outputPath(`study-${size.width}x${size.height}-${theme}.png`), fullPage: true })
  }
  await page.getByRole('button', { name: 'Check answer' }).click()
  await expect(page.getByRole('alert')).toContainText('SYNTHETIC_SAVE_FAILURE')
  await page.getByRole('button', { name: 'Check answer' }).click()
  await expect(page.getByText('Released faculty feedback')).toBeVisible()
  await page.getByRole('button', { name: /Task 2.*Pending/ }).click()
  await expect(page.getByText('Released faculty feedback')).toHaveCount(0)
  await expect(page.getByLabel('Your selected region pinned this point')).toHaveCount(0)
  await page.getByRole('radio', { name: 'Synthetic A', exact: true }).check()
  await expect(page.getByLabel('3: Probable')).toBeChecked()
  const forcedFocus = await expectForcedColorsFocus(page, page.getByRole('button', { name: 'Check answer' }))
  const activeTask = page.locator('[aria-current="step"]')
  await expect(activeTask).toBeVisible()
  const activeTaskOutline = await activeTask.evaluate((element) => {
    const style = getComputedStyle(element)
    return { color: style.outlineColor, style: style.outlineStyle, width: Number.parseFloat(style.outlineWidth) }
  })
  expect(activeTaskOutline.style).not.toBe('none')
  expect(activeTaskOutline.width).toBeGreaterThanOrEqual(2)
  expect(activeTaskOutline.color).not.toBe('rgba(0, 0, 0, 0)')
  await expect(page.getByRole('radio', { name: 'Synthetic A', exact: true })).toBeChecked()
  await info.attach('forced-colors-study', { body: JSON.stringify({ forcedFocus }), contentType: 'application/json' })
})

test('Classroom full stage, native tray, P and Alt-click anchored questions with retry', async ({ page }, info) => {
  await tiles(page)
  await page.addInitScript(() => { window.EventSource = class { addEventListener() {} close() {} } as unknown as typeof EventSource })
  let questions = 0
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url()).pathname
    if (url.endsWith('/sessions/qa-session')) return route.fulfill({ json: classroom })
    if (url.endsWith('/questions')) {
      const body = route.request().postDataJSON()
      expect(body.csrfToken).toBe('synthetic-classroom-csrf')
      expect(body.x).toBeGreaterThanOrEqual(0); expect(body.x).toBeLessThanOrEqual(1)
      questions += 1
      return route.fulfill({ status: questions === 1 ? 503 : 200, json: questions === 1 ? { detail: { code: 'SYNTHETIC_QUESTION_FAILURE' } } : {} })
    }
    return route.fulfill({ json: {} })
  })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/classroom/qa-session')
  const canvas = page.locator('.openseadragon-canvas canvas').first()
  await expect(canvas).toBeVisible()
  for (const size of sizes) for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.setViewportSize(size)
    const tray = page.locator('.classroom-activity-tray')
    const summary = tray.locator('summary')
    await summary.click()
    await expect(tray).not.toHaveAttribute('open')
    const width = await page.locator('.classroom-viewer').evaluate((el) => el.getBoundingClientRect().width)
    expect(width).toBeGreaterThan(size.width - 2)
    await page.keyboard.press('p')
    await expect(page.getByLabel('Question at this point')).toBeFocused()
    await page.getByLabel('Question at this point').fill('Synthetic pinned question')
    await expect.poll(async () => page.locator('.classroom-question-composer').evaluate((el) => { const r = el.getBoundingClientRect(); return r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight })).toBe(true)
    await info.attach(`classroom-contrast-${size.width}-${theme}`, { body: JSON.stringify(await contrast(page, '.classroom-question-composer')), contentType: 'application/json' })
    await page.screenshot({ path: info.outputPath(`classroom-${size.width}x${size.height}-${theme}.png`), fullPage: true })
    await noOverflow(page)
    await page.getByRole('button', { name: 'Cancel', exact: true }).click()
    await summary.click()
    if (info.project.name === 'mobile-chromium') await page.getByRole('button', { name: 'Ask at visible centre (P)' }).tap()
    else await page.getByRole('button', { name: 'Ask at visible centre (P)' }).click()
    await expect(page.getByLabel('Question at this point')).toBeVisible()
    await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  }
  await page.setViewportSize({ width: 1024, height: 768 })
  await page.locator('.classroom-activity-tray summary').click()
  await page.locator('.openseadragon-canvas').first().click({ position: { x: 250, y: 200 }, modifiers: ['Alt'] })
  await page.getByLabel('Question at this point').fill('Retain this failed question')
  await page.keyboard.press('Control+Enter')
  await page.locator('.classroom-activity-tray summary').click()
  await expect(page.locator('.classroom-message')).toContainText('Question could not be sent')
  await expect(page.getByLabel('Question at this point')).toHaveValue('Retain this failed question')
  await page.getByLabel('Question at this point').focus()
  await page.keyboard.press('Meta+Enter')
  await expect(page.getByLabel('Question at this point')).toHaveCount(0)
  await expect(page.locator('.classroom-message')).toContainText('Question sent to the teacher')
  await page.keyboard.press('p')
  const forcedFocus = await expectForcedColorsFocus(page, page.getByLabel('Question at this point'))
  await expect(page.getByLabel('Question at this point')).toBeVisible()
  await info.attach('forced-colors-classroom', { body: JSON.stringify({ forcedFocus }), contentType: 'application/json' })
})

test('Assessment practice survives denied reads and writes without promising persistence', async ({ page }, info) => {
  await denyStorage(page)
  const definition = { title: 'Synthetic practice', settings: {}, items: [{ id: 'one', type: 'multiple-choice', prompt: 'Synthetic practice question', points: '1', required: true, options: [{ id: 'a', label: 'Synthetic answer' }], answerKey: { optionIds: ['a'] } }] }
  await page.route('**/api/**', (route) => route.fulfill({ json: route.request().url().includes('/practice/') ? { publicId: 'qa-practice', storage: 'browser-local', definition, assets: {} } : { publicId: 'qa-practice', mode: 'practice', status: 'open', durationSeconds: 0, closesAt: null, assets: {}, manifest: definition } }))
  await page.emulateMedia({ reducedMotion: 'reduce' })
  for (const size of sizes) for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.setViewportSize(size)
    await page.goto('/assessment/qa-practice')
    await page.getByLabel('Synthetic answer').check()
    await expect(page.getByLabel('Synthetic answer')).toBeChecked()
    await expect(page.getByRole('alert')).toContainText('only in memory for this tab and will be lost on reload')
    await expect(page.getByText('Stored only in this browser')).toHaveCount(0)
    await noOverflow(page)
    await info.attach(`practice-contrast-${size.width}-${theme}`, { body: JSON.stringify(await contrast(page, '.assessment-student-main')), contentType: 'application/json' })
    await page.screenshot({ path: info.outputPath(`practice-${size.width}x${size.height}-${theme}.png`), fullPage: true })
  }
  const forcedFocus = await expectForcedColorsFocus(page, page.getByLabel('Synthetic answer'))
  await expect(page.getByLabel('Synthetic answer')).toBeChecked()
  await info.attach('forced-colors-assessment', { body: JSON.stringify({ forcedFocus }), contentType: 'application/json' })
})

test('native OSD pinned question sends from pointer button and keyboard', async ({ page }, info) => {
  await tiles(page)
  await page.addInitScript(() => { window.EventSource = class { addEventListener() {} close() {} } as unknown as typeof EventSource })
  const questions: Array<Record<string, unknown>> = []
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/sessions/qa-session')) return route.fulfill({ json: classroom })
    if (path.endsWith('/questions')) { questions.push(route.request().postDataJSON()); return route.fulfill({ status: 200, json: {} }) }
    return route.fulfill({ json: {} })
  })
  await page.goto('/classroom/qa-session')
  await expect(page.locator('.openseadragon-canvas canvas').first()).toBeVisible()
  await page.getByRole('button', { name: 'Ask at visible centre (P)' }).click()
  await page.getByLabel('Question at this point').fill('Synthetic pointer question')
  if (info.project.name === 'mobile-chromium') await page.getByRole('button', { name: 'Send question', exact: true }).tap()
  else await page.getByRole('button', { name: 'Send question', exact: true }).click()
  await expect.poll(() => questions.length).toBe(1)
  await expect(page.getByLabel('Question at this point')).toHaveCount(0)
  await page.getByRole('button', { name: 'Ask at visible centre (P)' }).click()
  await page.getByLabel('Question at this point').fill('Synthetic keyboard question')
  await page.keyboard.press('Control+Enter')
  await expect.poll(() => questions.length).toBe(2)
  await expect(page.getByLabel('Question at this point')).toHaveCount(0)
  await info.attach('question-requests', { body: JSON.stringify(questions), contentType: 'application/json' })
})

test('teacher expiry input is submitted after normal browser fill and Prepare click', async ({ page }, info) => {
  await page.addInitScript(() => sessionStorage.setItem('pathlab-csrf', 'synthetic-csrf'))
  const requests: Array<{ reviewExpiresAt: string }> = []
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/session')) return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    if (path.endsWith('/setup/folders')) return route.fulfill({ json: { items: [{ id: 'folder', name: 'Synthetic class', folderPath: ['Synthetic class'], depth: 0, hasChildren: false, readyCount: 1, blockedCount: 0, tooManySlides: false }], nextCursor: null } })
    if (path.endsWith('/readiness')) return route.fulfill({ json: { folderId: 'folder', ready: [{ id: 'slide', displayName: 'Synthetic', folderPath: [] }], blocked: [], tooManySlides: false } })
    if (path.endsWith('/sessions') && route.request().method() === 'POST') { requests.push(route.request().postDataJSON()); return route.fulfill({ status: 503, json: { detail: { code: 'SYNTHETIC_STOP_AFTER_REQUEST' } } }) }
    return route.fulfill({ json: { sessions: [] } })
  })
  await page.goto('/admin/classroom')
  await page.getByRole('radio', { name: /Synthetic class/ }).check()
  const chosen = await page.evaluate(() => { const date = new Date(Date.now() + 86400000); const pad = (value: number) => String(value).padStart(2, '0'); const local = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`; return { local, iso: new Date(local).toISOString() } })
  await page.getByLabel('Review access expires').fill(chosen.local)
  await page.getByRole('button', { name: 'Prepare classroom with 1 slide', exact: true }).click()
  await expect.poll(() => requests.length).toBe(1)
  expect(requests[0].reviewExpiresAt).toBe(chosen.iso)
  await info.attach('expiry-request', { body: JSON.stringify({ chosen, requests }), contentType: 'application/json' })
})
