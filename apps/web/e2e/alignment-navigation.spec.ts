import { expect, test } from '@playwright/test'

const map = {
  status: 'approximate', provenance: 'automatic', anchorSlideId: 'reference',
  movingToReference: [[1, 0, 20], [0, 1, 10]], triangles: [],
  overviewTriangles: [{ moving: [[0, 0], [1000, 0], [0, 750]], reference: [[20, 10], [1020, 10], [20, 760]] }],
}

for (const chain of [false, true]) test(`real OSD automatically positions and navigates ${chain ? 'anchor chains' : 'direct maps'}`, async ({ page }) => {
  let ready = false
  await page.addInitScript(() => {
    const records: unknown[] = []
    Object.assign(window, { alignmentApplications: records })
    window.addEventListener('pathlab:alignment-applied', e => records.push((e as CustomEvent).detail))
  })
  await page.route('**/api/v1/admin/comparison-sets/test**', route => {
    const url = route.request().url()
    const body = url.endsWith('/jobs') ? [] : url.endsWith('/candidates') ? { candidates: [] } : {
      id: 'test', name: 'Synthetic alignment', referenceSlideId: 'reference', version: 1,
      status: ready ? 'partial' : 'running',
      members: (chain ? ['reference', 'moving', 'anchor'] : ['reference', 'moving']).map(slideId => ({
        slideId, displayName: slideId, stain: slideId, tileSource: `/tiles/${slideId}/slide.dzi`,
        metadata: { width: 1024, height: 768, physicalSizeX: 0.25 },
        registration: slideId === 'moving' && ready ? { ...map, anchorSlideId: chain ? 'anchor' : 'reference' }
          : slideId === 'anchor' && ready ? { ...map, status: 'ready', triangles: map.overviewTriangles, overviewTriangles: [] } : null,
      })),
    }
    return route.fulfill({ json: body })
  })
  await page.route('**/tiles/**/slide.dzi', route => route.fulfill({
    contentType: 'application/xml',
    body: '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" TileSize="1024" Overlap="0" Format="png"><Size Width="1024" Height="768"/></Image>',
  }))
  await page.route('**/tiles/**/*_files/**', route => route.fulfill({
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6O4kAAAAASUVORK5CYII=', 'base64'),
  }))
  await page.goto('/admin/comparisons/test')
  await expect(page.getByText('Synthetic alignment')).toBeVisible()
  ready = true
  await expect(page.getByText('Approximate sync')).toBeVisible({ timeout: 10_000 })
  const applications = () => page.evaluate(() => (window as unknown as {
    alignmentApplications: Array<{ sourceViewport: { centerX: number; centerY: number; imageZoom: number }; viewport: { centerX: number; centerY: number; rotation: number; imageZoom: number }; approximate: boolean }>
  }).alignmentApplications)
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(0)
  const verify = async () => {
    const last = (await applications()).at(-1)!
    expect(last.approximate).toBe(true)
    expect(last.viewport.centerX).toBeCloseTo(last.sourceViewport.centerX - (chain ? 40 : 20), 3)
    expect(last.viewport.centerY).toBeCloseTo(last.sourceViewport.centerY - (chain ? 20 : 10), 3)
    expect(last.viewport.imageZoom).toBeCloseTo(last.sourceViewport.imageZoom, 4)
  }
  await verify()
  await page.reload()
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(0)
  await verify()
  const before = (await applications()).length
  const canvas = page.locator('.comparison-pane').first().locator('.openseadragon-canvas').first()
  const bounds = (await canvas.boundingBox())!
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2)
  await page.mouse.down()
  await page.mouse.move(bounds.x + bounds.width / 2 + 20, bounds.y + bounds.height / 2 + 10, { steps: 5 })
  await page.mouse.up()
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(before)
  await verify()
  const beforeZoom = (await applications()).length
  await page.mouse.wheel(0, 200)
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(beforeZoom)
  await verify()
  await page.getByRole('button', { name: /Open rotation controls/ }).first().click()
  await page.getByRole('button', { name: 'Rotate to 90 degrees' }).click()
  await expect.poll(async () => (await applications()).at(-1)?.viewport.rotation).toBe(90)
  await verify()
  const beforeReset = (await applications()).length
  await page.getByRole('button', { name: /Reset view/ }).click()
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(beforeReset)
  await verify()
})
