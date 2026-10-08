import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'

type Point = [number, number]
type Matrix = [number, number, number, number, number, number]
type View = { centerX: number; centerY: number; imageZoom: number; rotation: number; visibleBounds?: number[] }
type Application = { slideId: string; sourceViewport: View; viewport: View }
const apply = (m: Matrix, p: Point): Point => [m[0] * p[0] + m[1] * p[1] + m[2], m[3] * p[0] + m[4] * p[1] + m[5]]
const inverse = (m: Matrix): Matrix => {
  const det = m[0] * m[4] - m[1] * m[3]
  return [m[4] / det, -m[1] / det, (m[1] * m[5] - m[4] * m[2]) / det,
    -m[3] / det, m[0] / det, (m[3] * m[2] - m[0] * m[5]) / det]
}
const rootMaps: Matrix[] = [[1, 0, 0, 0, 1, 0], [1, 0, 20, 0, 1, -10], [0, -1, 550, 1, 0, -50], [1, 0, 5, 0, 1, -5]]
const calibration: Point[] = [[0.25, 0.5], [0.25, 0.5], [0.5, 1.5], [0.125, 0.5]]
const effective = (mpp: Point, rotation: number) => Math.hypot(Math.cos(rotation * Math.PI / 180) * mpp[0], Math.sin(rotation * Math.PI / 180) * mpp[1])
const normalize = (angle: number) => ((angle % 360) + 360) % 360

test('alignment ordered pane matrix verifies all displayed pairs and both navigation directions with declared units', async ({ page }, testInfo) => {
  test.setTimeout(240_000)
  let loadedTiles = 0
  page.on('response', response => { if (response.ok() && response.url().includes('/preview/slide_files/')) loadedTiles++ })
  await page.addInitScript(() => {
    Object.assign(window, { alignmentApplications: [] })
    window.addEventListener('pathlab:alignment-applied', event => (window as unknown as { alignmentApplications: unknown[] }).alignmentApplications.push((event as CustomEvent).detail))
  })
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  const { slideIds } = JSON.parse(execFileSync(process.env.PATHLAB_E2E_PYTHON!, [path.resolve('../../scripts/seed_frontend_qa.py'), 'alignment'], { encoding: 'utf8' })) as { slideIds: string[] }
  const slides = await Promise.all(slideIds.slice(0, 4).map(async id => {
    const response = await page.request.get(`/api/v1/admin/slides/${id}`)
    expect(response.ok()).toBe(true)
    return response.json()
  }))
  const ids = slides.map(slide => slide.id as string)
  const rootCells: Point[][] = [[[280, 230], [320, 230], [280, 270]], [[320, 230], [320, 270], [280, 270]]]
  const metadata = [
    { physicalSizeX: 0.25, physicalSizeY: 0.5, physicalSizeUnit: 'um' },
    { physicalSizeX: 250, physicalSizeY: 500, physicalSizeUnit: 'UnitsLength.NANOMETER' },
    { physicalSizeX: 500, physicalSizeY: 0.0015, physicalSizeXUnit: 'nm', physicalSizeYUnit: 'mm' },
    { physicalSizeX: 0.125, physicalSizeY: 0.5, physicalSizeUnit: 'micrometres' },
  ]
  // Mathematical maps, independent of anatomical inference. Pixels remain real seeded derivatives.
  const members = slides.map((slide, index) => {
    const anchor = index === 3 ? 1 : 0
    return { ...slide, slideId: ids[index], stain: `Geometry ${index}`, metadata: { width: 640, height: 480, ...metadata[index] }, registration: index === 0 ? null : {
      status: 'ready', provenance: 'automatic', anchorSlideId: ids[anchor],
      movingToReference: index === 3 ? [[1, 0, -15], [0, 1, 5]] : [rootMaps[index].slice(0, 3), rootMaps[index].slice(3)],
      overviewTriangles: rootCells.map(cell => ({ moving: cell.map(point => apply(inverse(rootMaps[index]), point)), reference: cell.map(point => apply(inverse(rootMaps[anchor]), point)) })),
      triangles: rootCells.map(cell => ({ moving: cell.map(point => apply(inverse(rootMaps[index]), point)), reference: cell.map(point => apply(inverse(rootMaps[anchor]), point)) })),
    } }
  })
  await page.route('**/api/v1/admin/comparison-sets/pane-matrix**', route => route.fulfill({ json: route.request().url().endsWith('/jobs') ? [] : { id: 'pane-matrix', name: 'Ordered geometry QA', status: 'ready', version: 1, referenceSlideId: ids[0], members } }))
  const applications = () => page.evaluate(() => (window as unknown as { alignmentApplications: Application[] }).alignmentApplications)
  const clear = () => page.evaluate(() => { (window as unknown as { alignmentApplications: unknown[] }).alignmentApplications = [] })
  const receipts: unknown[] = []
  const unsupported: unknown[] = []
  const scaleLabelBounds: unknown[] = []
  try {
  for (let left = 0; left < 4; left++) for (let right = 0; right < 4; right++) {
    if (left === right) continue
    await page.goto('/admin/comparisons/pane-matrix')
    // Select through real pane controls, temporarily using an unused member for a swap.
    const desired = [ids[left], ids[right]]
    for (let pane = 0; pane < 2; pane++) {
      const other = 1 - pane
      if (await page.getByLabel(`Slide shown in pane ${other + 1}`).inputValue() === desired[pane]) {
        const current = await page.getByLabel(`Slide shown in pane ${pane + 1}`).inputValue()
        const spare = ids.find(id => id !== desired[pane] && id !== current)!
        await page.getByLabel(`Slide shown in pane ${other + 1}`).selectOption(spare)
      }
      await page.getByLabel(`Slide shown in pane ${pane + 1}`).selectOption(desired[pane])
    }
    await page.getByText('Advanced', { exact: true }).click()
    await page.getByRole('button', { name: 'Reset view', exact: true }).click()
    await page.getByText('Advanced', { exact: true }).click()
    await expect.poll(async () => (await applications()).length).toBeGreaterThan(0)
    for (let sourcePane = 0; sourcePane < 2; sourcePane++) {
      const sourceIndex = sourcePane === 0 ? left : right, targetIndex = sourcePane === 0 ? right : left
      const pane = page.locator('.comparison-pane').nth(sourcePane)
      const scaleLabel = pane.locator('.comparison-relative-scale')
      if (await scaleLabel.count()) {
        const labelBounds = (await scaleLabel.boundingBox())!, paneBounds = (await pane.boundingBox())!
        const rotationBounds = (await pane.getByRole('button', { name: /^Open rotation controls/ }).boundingBox())!
        expect(labelBounds.x).toBeGreaterThanOrEqual(paneBounds.x)
        expect(labelBounds.x + labelBounds.width).toBeLessThanOrEqual(paneBounds.x + paneBounds.width)
        expect(labelBounds.y).toBeGreaterThanOrEqual(paneBounds.y)
        expect(labelBounds.y + labelBounds.height).toBeLessThanOrEqual(rotationBounds.y)
        scaleLabelBounds.push({ displayed: [left, right], sourcePane, labelBounds, rotationBounds, withinPane: true, controlsClear: true })
      }
      await pane.getByRole('button', { name: /^Open rotation controls/ }).click()
      await pane.getByRole('button', { name: 'Rotate to 90 degrees', exact: true }).click()
      await pane.getByRole('button', { name: /^Open rotation controls/ }).click()
      const canvas = pane.locator('.openseadragon-canvas').first()
      await canvas.scrollIntoViewIfNeeded()
      const bounds = (await canvas.boundingBox())!, x = bounds.x + bounds.width / 2, y = bounds.y + bounds.height / 2
      await clear()
      await page.mouse.move(x, y)
      await page.mouse.down()
      await page.mouse.move(x + 4, y + 3, { steps: 4 })
      await page.waitForTimeout(250)
      await page.mouse.up()
      await expect.poll(async () => (await applications()).filter(row => row.slideId === ids[targetIndex]).length).toBeGreaterThan(0)
      await page.waitForTimeout(150)
      const pan = (await applications()).filter(row => row.slideId === ids[targetIndex]).at(-1)!
      await clear()
      await page.mouse.move(x, y)
      await page.mouse.wheel(0, pan.sourceViewport.imageZoom >= 1.5 ? 120 : -120)
      await expect.poll(async () => (await applications()).filter(row => row.slideId === ids[targetIndex]).length).toBeGreaterThan(0)
      await page.waitForTimeout(600)
      const zoom = (await applications()).filter(row => row.slideId === ids[targetIndex]).at(-1)!
      expect(zoom.sourceViewport.imageZoom).not.toBeCloseTo(pan.sourceViewport.imageZoom, 3)
      for (const [action, row] of [['pan', pan], ['zoom', zoom]] as const) {
        const root = apply(rootMaps[sourceIndex], [row.sourceViewport.centerX, row.sourceViewport.centerY])
        const expected = apply(inverse(rootMaps[targetIndex]), root)
        const sourceAngle = Math.atan2(rootMaps[sourceIndex][3], rootMaps[sourceIndex][0]) * 180 / Math.PI
        const targetAngle = Math.atan2(rootMaps[targetIndex][3], rootMaps[targetIndex][0]) * 180 / Math.PI
        const rotation = normalize(row.sourceViewport.rotation + targetAngle - sourceAngle)
        expect(Math.abs(row.viewport.centerX - expected[0])).toBeLessThan(0.1)
        expect(Math.abs(row.viewport.centerY - expected[1])).toBeLessThan(0.1)
        expect(normalize(row.viewport.rotation)).toBeCloseTo(rotation, 5)
        expect(row.viewport.imageZoom).toBeCloseTo(row.sourceViewport.imageZoom * effective(calibration[targetIndex], rotation) / effective(calibration[sourceIndex], row.sourceViewport.rotation), 5)
        expect(row.sourceViewport.visibleBounds).toHaveLength(4)
        receipts.push({ displayed: [left, right], sourcePane, source: sourceIndex, target: targetIndex, action, root, expected, actual: row.viewport, sourceViewport: row.sourceViewport })
      }
    }
    await expect.poll(() => page.locator('.comparison-pane').evaluateAll(elements => elements.filter(element => {
      const canvas = element.querySelector<HTMLCanvasElement>('.openseadragon-canvas canvas')
      if (!canvas) return false
      const context = canvas.getContext('2d')
      if (!context || !canvas.width || !canvas.height) return false
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data, colors = new Set<string>()
      for (let i = 0; i < pixels.length; i += 4 * 101) if (pixels[i + 3] && Math.max(pixels[i], pixels[i + 1], pixels[i + 2]) > 30) colors.add(`${pixels[i]},${pixels[i + 1]},${pixels[i + 2]}`)
      return colors.size > 10
    }).length)).toBe(2)
    if (left === 1 && right === 3) await testInfo.attach('hidden-root-chain-original-pixels', { body: await page.screenshot(), contentType: 'image/png' })
    const outsidePane = page.locator('.comparison-pane').first()
    const outsideCanvas = outsidePane.locator('.openseadragon-canvas').first()
    await outsideCanvas.scrollIntoViewIfNeeded()
    const outsideBounds = (await outsideCanvas.boundingBox())!
    const ox = outsideBounds.x + outsideBounds.width / 2, oy = outsideBounds.y + outsideBounds.height / 2
    await page.mouse.move(ox, oy)
    await page.mouse.wheel(0, 1200)
    await page.waitForTimeout(400)
    await page.mouse.down()
    await page.mouse.move(ox + 500, oy + 400, { steps: 8 })
    await page.waitForTimeout(250)
    await page.mouse.up()
    // The wide field may still contain supported cells; zoom into the displaced field
    // so the visible-radius fallback cannot legitimately reach those cells.
    await page.mouse.move(ox, oy)
    await page.mouse.wheel(0, -1200)
    await expect(page.locator('.comparison-alignment-context summary').filter({ hasText: 'Some panes are outside mapped tissue' })).toBeVisible()
    await expect(page.locator('.comparison-pane').nth(1).getByText('Unavailable', { exact: true })).toBeVisible()
    const stopped = (await applications()).length
    await page.waitForTimeout(300)
    expect((await applications()).length).toBe(stopped)
    unsupported.push({ displayed: [left, right], sourcePane: 0, targetPane: 1, targetSuspended: true, applicationCountStable: true, visibleUnsupportedField: true, lastSupportedSourceViewport: (await applications()).at(-1)?.sourceViewport })
  }
  expect(receipts).toHaveLength(48)
  expect(loadedTiles).toBeGreaterThan(0)
  } finally {
  await testInfo.attach('ordered-pane-matrix', { body: JSON.stringify({ scope: 'Mathematical fixture navigation only; no anatomical accuracy or real-world combination qualification.', displayedPairs: 12, sourceDirections: 24, supportedActions: receipts, unsupportedFields: unsupported, scaleLabelBounds, lastApplications: (await applications()).slice(-4), loadedTiles }, null, 2), contentType: 'application/json' })
  }
})
