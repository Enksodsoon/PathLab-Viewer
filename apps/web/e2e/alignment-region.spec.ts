import { expect, test } from '@playwright/test'

test('real OSD adjusts a displayed sibling region while refinement runs, previews and saves it', async ({ page }) => {
  const triangle = { moving: [[6000, 6000], [9000, 6000], [6000, 9000]], reference: [[6000, 6000], [9000, 6000], [6000, 9000]] }
  const makeSet = () => ({ id: 'region-test', name: 'Region navigation fixture', referenceSlideId: 'root', version: 1, status: 'running', regionalCorrections: [] as unknown[], members: ['root', 'a', 'b'].map(slideId => ({ slideId, displayName: slideId, stain: slideId, tileSource: `/tiles/${slideId}/slide.dzi`, metadata: { width: 10000, height: 10000, physicalSizeX: 0.25 }, registration: slideId === 'root' ? null : { status: 'approximate', provenance: 'automatic', anchorSlideId: 'root', movingToReference: [[1, 0, 0], [0, 1, 0]], triangles: [], overviewTriangles: [triangle] } })) })
  let saved = makeSet()
  const requests: Array<{ operation: string; version: number; regionId?: string; sourceSlideId: string; targetSlideId: string; sourceBounds: number[]; movingPoints: number[][]; referencePoints: number[][] }> = []
  await page.addInitScript(() => {
    sessionStorage.setItem('pathlab-comparison-view:admin:region-test', JSON.stringify(['a', 'b']))
    const records: unknown[] = []
    Object.assign(window, { alignmentApplications: records })
    window.addEventListener('pathlab:alignment-applied', event => records.push((event as CustomEvent).detail))
  })
  await page.route('**/api/v1/auth/session', route => route.fulfill({ json: { csrfToken: 'fixture' } }))
  await page.route('**/api/v1/admin/comparison-sets/region-test**', route => {
    const url = route.request().url()
    if (url.endsWith('/region-corrections')) {
      const payload = route.request().postDataJSON(); requests.push(payload)
      const [x, y, width, height] = payload.sourceBounds
      const dx = payload.referencePoints[0][0] - payload.movingPoints[0][0]
      const dy = payload.referencePoints[0][1] - payload.movingPoints[0][1]
      const moving = [[x, y], [x + width, y], [x, y + height]]
      const reference = moving.map(([px, py]) => [px + dx, py + dy])
      const overlay = { id: 'revision-1', regionId: 'region-1', sourceSlideId: payload.sourceSlideId, targetSlideId: payload.targetSlideId, sourceBounds: payload.sourceBounds, sourceVersion: 'a-v1', targetVersion: 'b-v1', createdAt: new Date().toISOString(), registration: { status: 'approximate', provenance: 'manual-region', movingToReference: [[1, 0, dx], [0, 1, dy]], triangles: [{ moving, reference }], overviewTriangles: [{ moving, reference }] } }
      const result = { ...saved, regionalCorrections: [overlay] }
      if (payload.operation === 'save') { result.version = 2; result.status = 'ready'; saved = result }
      return route.fulfill({ json: result })
    }
    return route.fulfill({ json: url.endsWith('/jobs') ? [] : url.endsWith('/candidates') ? { candidates: [] } : saved })
  })
  await page.route('**/tiles/**/slide.dzi', route => route.fulfill({ contentType: 'application/xml', body: '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" TileSize="1024" Overlap="0" Format="png"><Size Width="10000" Height="10000"/></Image>' }))
  await page.route('**/tiles/**/*_files/**', route => route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6O4kAAAAASUVORK5CYII=', 'base64') }))
  await page.goto('/admin/comparisons/region-test')
  const applications = () => page.evaluate(() => (window as unknown as { alignmentApplications: Array<{ sourceViewport: { centerX: number; centerY: number }; viewport: { centerX: number; centerY: number }; approximate: boolean }> }).alignmentApplications)
  await expect.poll(async () => (await applications()).at(-1)?.sourceViewport.centerX).toBeGreaterThan(6000)
  await expect(page.getByRole('button', { name: 'Adjust region' })).toBeEnabled()
  await page.getByRole('button', { name: 'Adjust region' }).click()
  await expect(page.getByLabel('Correction reference slide')).toHaveValue('b')
  await expect(page.getByText('Captured region (pixels):', { exact: false })).toBeVisible()
  const canvas = page.locator('.comparison-pane').first().locator('.openseadragon-canvas').first()
  const box = (await canvas.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 30, box.y + box.height / 2 + 10, { steps: 5 })
  await page.mouse.up()
  await page.getByRole('button', { name: 'Record point pair' }).click()
  await expect(page.getByRole('button', { name: 'Preview correction' })).toBeEnabled()
  const before = (await applications()).length
  await page.getByRole('button', { name: 'Preview correction' }).click()
  await expect(page.getByText('Unsaved correction preview', { exact: true })).toBeVisible()
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(before)
  const last = (await applications()).at(-1)!
  const request = requests[0]
  expect(last.viewport.centerX).toBeCloseTo(last.sourceViewport.centerX - (request.referencePoints[0][0] - request.movingPoints[0][0]), 3)
  expect(last.approximate).toBe(true)
  await page.waitForTimeout(2200)
  await expect(page.getByText('Unsaved correction preview', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Save correction' }).click()
  await expect(page.getByText('Region correction saved.', { exact: false })).toBeVisible()
  expect(requests[1]).toMatchObject({ operation: 'save', version: 1, regionId: 'region-1' })
  await page.reload()
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(0)
  await page.getByText('Advanced', { exact: true }).click()
  await expect(page.getByRole('region', { name: 'Active pane inspector' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeVisible()
})
