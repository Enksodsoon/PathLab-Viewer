import { expect, test } from '@playwright/test'
import path from 'node:path'

const fixtureRoot = process.env.PATHLAB_SCREENSHOT_DZI_ROOT

test.skip(!fixtureRoot, 'PATHLAB_SCREENSHOT_DZI_ROOT must point to a current non-PHI DZI')

test('captures the visible tissue canvas without DOM overlays or network upload', async ({ page }) => {
  const requests: Array<{ method: string; url: string }> = []
  page.on('request', (request) => requests.push({ method: request.method(), url: request.url() }))

  await page.route('**/api/v1/public/slides/classroom-spike', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      publicId: 'classroom-spike',
      displayName: 'Synthetic non-PHI tissue',
      state: 'published',
      tileSource: '/tiles/classroom-spike/v1/slide.dzi',
      thumbnailUrl: null,
      metadata: { width: 2048, height: 1536 },
    }),
  }))
  await page.route('**/tiles/classroom-spike/v1/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname
    const relative = pathname.split('/tiles/classroom-spike/v1/')[1]
    await route.fulfill({ path: path.join(fixtureRoot!, ...relative.split('/')) })
  })

  await page.goto('/s/classroom-spike')
  const canvas = page.locator('.openseadragon-canvas canvas').first()
  await expect(canvas).toBeVisible()
  await page.waitForFunction(() => {
    const candidates = [...document.querySelectorAll<HTMLCanvasElement>('.openseadragon-canvas canvas')]
    return candidates.some((candidate) => candidate.width >= 900 && candidate.height >= 500)
  })

  await page.locator('.openseadragon-canvas').first().evaluate((host) => {
    const overlay = document.createElement('div')
    overlay.dataset.screenshotExclusionProbe = 'true'
    Object.assign(overlay.style, {
      position: 'absolute',
      inset: '30% 40%',
      background: 'rgb(255, 0, 0)',
      zIndex: '999',
    })
    host.append(overlay)
  })

  const evidence = await page.locator('.openseadragon-canvas canvas').evaluateAll(async (canvases) => {
    const canvas = canvases
      .map((candidate) => candidate as HTMLCanvasElement)
      .sort((left, right) => right.width * right.height - left.width * left.height)[0]
    const { captureVisibleTissue } = await import('/src/classroom/screenshot.ts')
    const capture = await captureVisibleTissue(canvas)
    const decoded = document.createElement('canvas')
    decoded.width = capture.width
    decoded.height = capture.height
    const bitmap = await createImageBitmap(capture.blob)
    decoded.getContext('2d')?.drawImage(bitmap, 0, 0)
    bitmap.close()
    const context = decoded.getContext('2d', { willReadFrequently: true })
    if (!context) throw new Error('Visible OpenSeadragon canvas is unreadable')
    const pixels = context.getImageData(0, 0, decoded.width, decoded.height).data
    let colored = 0
    let pureRed = 0
    for (let offset = 0; offset < pixels.length; offset += 4 * 127) {
      const red = pixels[offset]
      const green = pixels[offset + 1]
      const blue = pixels[offset + 2]
      const alpha = pixels[offset + 3]
      if (alpha && (red !== green || green !== blue)) colored += 1
      if (red === 255 && green === 0 && blue === 0 && alpha === 255) pureRed += 1
    }
    return {
      width: capture.width,
      height: capture.height,
      bytes: capture.blob.size,
      colored,
      pureRed,
    }
  })

  expect(evidence.width).toBeLessThanOrEqual(1600)
  expect(evidence.height).toBeLessThanOrEqual(1200)
  expect(evidence.bytes).toBeGreaterThan(1_000)
  expect(evidence.bytes).toBeLessThanOrEqual(2 * 1024 * 1024)
  expect(evidence.colored).toBeGreaterThan(100)
  expect(evidence.pureRed).toBe(0)
  expect(requests.some((request) => (
    request.method !== 'GET' && /api\/.*(?:screenshot|notebook|capture)/i.test(request.url)
  ))).toBe(false)
})
