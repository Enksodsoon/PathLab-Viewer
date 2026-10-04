import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'

type View = { centerX: number; centerY: number; imageZoom: number; rotation: number }
type Application = { slideId: string; approximate: boolean; sourceViewport: View; viewport: View }
type Geometry = { kind: string; sourceSize: number[]; analysisSize: number[]; coordinateFrameSize: number[]; samplingScale: number[]; pyramidDivisor: number; selectedLevel: number }
type Registration = { status: string; engine: string; overviewTriangles: unknown[]; evidence: { phase: string }; engineSettings: { movingGeometry: Geometry; referenceGeometry: Geometry } }

test('alignment large odd DZI preserves foreground sampling frame and real forward/reversed navigation', async ({ page }, testInfo) => {
  let loadedTiles = 0
  page.on('response', response => { if (response.ok() && response.url().includes('/preview/slide_files/')) loadedTiles++ })
  await page.addInitScript(() => {
    Object.assign(window, { alignmentApplications: [] })
    window.addEventListener('pathlab:alignment-applied', event => (window as unknown as { alignmentApplications: unknown[] }).alignmentApplications.push((event as CustomEvent).detail))
  })
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  const fixture = JSON.parse(execFileSync(process.env.PATHLAB_E2E_PYTHON!, [path.resolve('../../scripts/seed_frontend_qa.py'), 'alignment', 'large-odd'], { encoding: 'utf8' })) as { slideIds: string[]; sourceSize: number[] }
  expect(fixture.slideIds).toHaveLength(2)
  expect(fixture.sourceSize).toEqual([5003, 4009])
  const auth = await (await page.request.get('/api/v1/auth/session')).json() as { csrfToken: string }
  const started = performance.now()
  const created = await page.request.post('/api/v1/admin/comparison-sets', { headers: { 'X-CSRF-Token': auth.csrfToken }, data: { name: 'Large odd DZI geometry QA', slideIds: fixture.slideIds, referenceSlideId: fixture.slideIds[0] } })
  expect(created.ok()).toBe(true)
  const { id } = await created.json() as { id: string }
  const endpoint = `/api/v1/admin/comparison-sets/${id}`
  let foreground: Registration | undefined
  await expect.poll(async () => {
    const response = await page.request.get(endpoint)
    expect(response.ok()).toBe(true)
    const current = await response.json() as { members: Array<{ slideId: string; registration?: Registration }> }
    foreground = current.members.find(member => member.slideId === fixture.slideIds[1])?.registration
    return foreground?.status === 'approximate' && foreground.evidence?.phase === 'preview' && foreground.overviewTriangles.length > 0
  }, { timeout: 20_000, intervals: [100, 200, 300] }).toBe(true)
  expect(foreground!.engine).toBe('native-overview-v6')
  for (const geometry of [foreground!.engineSettings.referenceGeometry, foreground!.engineSettings.movingGeometry]) {
    expect(geometry).toMatchObject({ kind: 'dzi-pyramid', sourceSize: [5003, 4009], analysisSize: [626, 502], coordinateFrameSize: [5008, 4016], samplingScale: [8, 8], pyramidDivisor: 8, selectedLevel: 10 })
  }
  await page.goto(`/admin/comparisons/${id}`)
  await expect(page.getByText('Approximate sync', { exact: true })).toBeVisible()
  await expect(page.locator('.comparison-setup-menu')).not.toHaveAttribute('open', '')
  const applications = () => page.evaluate(() => (window as unknown as { alignmentApplications: Application[] }).alignmentApplications)
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(0)
  const browserObservedMilliseconds = performance.now() - started
  expect(browserObservedMilliseconds).toBeLessThanOrEqual(10_000)
  const directions: unknown[] = []
  for (const sourcePane of [0, 1]) {
    const target = fixture.slideIds[1 - sourcePane]
    const before = (await applications()).length
    const canvas = page.locator('.comparison-pane').nth(sourcePane).locator('.openseadragon-canvas').first()
    await canvas.scrollIntoViewIfNeeded()
    const bounds = (await canvas.boundingBox())!, x = bounds.x + bounds.width / 2, y = bounds.y + bounds.height / 2
    await page.mouse.move(x, y); await page.mouse.down()
    await page.mouse.move(x + 4, y + 3, { steps: 4 })
    await page.waitForTimeout(250); await page.mouse.up()
    await expect.poll(async () => (await applications()).slice(before).filter(row => row.slideId === target).length).toBeGreaterThan(0)
    await page.waitForTimeout(150)
    const applied = (await applications()).filter(row => row.slideId === target).at(-1)!
    expect(applied.approximate).toBe(true)
    for (const view of [applied.sourceViewport, applied.viewport]) {
      expect(view.centerX).toBeGreaterThan(0); expect(view.centerX).toBeLessThan(5003)
      expect(view.centerY).toBeGreaterThan(0); expect(view.centerY).toBeLessThan(4009)
      expect(Number.isFinite(view.imageZoom) && view.imageZoom > 0).toBe(true)
    }
    const direction = sourcePane === 0 ? 1 : -1
    // Known synthetic translation is a coarse navigation sanity check, not anatomical error.
    expect(Math.abs(applied.viewport.centerX - applied.sourceViewport.centerX - direction * 16)).toBeLessThan(40)
    expect(Math.abs(applied.viewport.centerY - applied.sourceViewport.centerY - direction * 8)).toBeLessThan(40)
    directions.push({ sourcePane, applied })
  }
  await expect.poll(() => page.locator('.comparison-pane').evaluateAll(elements => elements.filter(element => {
    const canvas = element.querySelector<HTMLCanvasElement>('.openseadragon-canvas canvas'), context = canvas?.getContext('2d')
    if (!canvas || !context || !canvas.width || !canvas.height) return false
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data, colors = new Set<string>()
    for (let i = 0; i < pixels.length; i += 4 * 101) if (pixels[i + 3] && Math.max(pixels[i], pixels[i + 1], pixels[i + 2]) > 30) colors.add(`${pixels[i]},${pixels[i + 1]},${pixels[i + 2]}`)
    return colors.size > 10
  }).length)).toBe(2)
  expect(loadedTiles).toBeGreaterThan(0)
  await expect(page.getByText('Slide tiles could not be loaded.', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Unavailable', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Approximate sync', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('alignment-large-odd-original-pixels.png'), fullPage: true })
  await testInfo.attach('large-odd-foreground-receipt', { body: JSON.stringify({ scope: 'Synthetic original 5003x4009 DZI pixels and actual worker/API/OSD. The 10-second engineering check includes queue, preparation and initial viewport application, excludes fixture construction, and is not production latency or anatomical qualification.', foreground, browserObservedMilliseconds, loadedTiles, directions, advancedOpened: false }), contentType: 'application/json' })
})
