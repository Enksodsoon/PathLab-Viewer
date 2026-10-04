import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { writeFileSync } from 'node:fs'
import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'
import type { RegistrationCandidateManifest, ComparisonSet, SlideRegistration } from '../src/types'

type Point = [number, number]
type RegistrationTriangle = NonNullable<SlideRegistration['triangles']>[number]
type View = { centerX: number; centerY: number; imageZoom: number; rotation: number }
type Application = { sourceSlideId: string; slideId: string; retainedOverview: boolean; regional: boolean; sourceViewport: View; viewport: View }
type Restoration = { slideId: string; requestedViewport: View; actualViewport: View | null }

// Independent barycentric oracle: this does not call the production map lookup.
function inCell(cell: RegistrationTriangle, point: Point, reverse: boolean): Point | null {
  const source = reverse ? cell.reference : cell.moving, target = reverse ? cell.moving : cell.reference
  const [[ax, ay], [bx, by], [cx, cy]] = source
  const denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
  const a = ((by - cy) * (point[0] - cx) + (cx - bx) * (point[1] - cy)) / denominator
  const b = ((cy - ay) * (point[0] - cx) + (ax - cx) * (point[1] - cy)) / denominator
  const c = 1 - a - b
  if (Math.min(a, b, c) < -1e-8) return null
  return [a * target[0][0] + b * target[1][0] + c * target[2][0], a * target[0][1] + b * target[1][1] + c * target[2][1]]
}

test('alignment candidate support retains current overview and direct pane Reset works without Advanced', async ({ page }, testInfo) => {
  let loadedTiles = 0
  page.on('response', response => { if (response.ok() && response.url().includes('/preview/slide_files/')) loadedTiles++ })
  await page.addInitScript(() => {
    Object.assign(window, { alignmentApplications: [], alignmentRestorations: [] })
    window.addEventListener('pathlab:alignment-applied', event => (window as unknown as { alignmentApplications: unknown[] }).alignmentApplications.push((event as CustomEvent).detail))
    window.addEventListener('pathlab:alignment-restored', event => (window as unknown as { alignmentRestorations: unknown[] }).alignmentRestorations.push((event as CustomEvent).detail))
  })
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  const seed = (...args: string[]) => JSON.parse(execFileSync(process.env.PATHLAB_E2E_PYTHON!, [path.resolve('../../scripts/seed_frontend_qa.py'), ...args], { encoding: 'utf8' }))
  const { slideIds } = seed('alignment', 'candidate-pair') as { slideIds: string[] }
  const auth = await (await page.request.get('/api/v1/auth/session')).json() as { csrfToken: string }
  const headers = { 'X-CSRF-Token': auth.csrfToken }
  // Known equivalent cases first, so the final actual metadata edit can invalidate this pair.
  expect((await page.request.post('/api/v2/admin/slides/batch-metadata', { headers, data: { slideIds: slideIds.slice(0, 2), caseId: 'candidate-case-A' } })).ok()).toBe(true)
  const created = await page.request.post('/api/v1/admin/comparison-sets', { headers, data: { name: 'Candidate support QA', slideIds: slideIds.slice(0, 2), referenceSlideId: slideIds[0] } })
  expect(created.ok()).toBe(true)
  const { id } = await created.json() as { id: string }
  const endpoint = `/api/v1/admin/comparison-sets/${id}`
  const getSet = async () => (await (await page.request.get(endpoint)).json()) as ComparisonSet
  let current = await getSet()
  await expect.poll(async () => {
    current = await getSet()
    return current.members[1].nativeOverviewFallback?.overviewTriangles?.length ?? 0
  }, { timeout: 25_000 }).toBeGreaterThan(0)
  // Keep the actual computed Native map before an equivalent legacy refinement can
  // replace its identity. The seed later revalidates live tokens/frame/geometry.
  const nativeCapture = { comparisonSetId: id, setVersion: current.version,
    sourceToken: current.members[1].alignmentSourceVersion, anchorToken: current.members[0].alignmentSourceVersion,
    native: current.members[1].nativeOverviewFallback }
  writeFileSync(path.join(process.env.PATHLAB_DATA_ROOT!, '..', `native-capture-${id}.json`), JSON.stringify(nativeCapture))
  await expect.poll(async () => (await (await page.request.get(`${endpoint}/jobs`)).json() as Array<{ status: string }>).every(job => ['succeeded', 'failed', 'cancelled'].includes(job.status)), { timeout: 25_000 }).toBe(true)
  const postRefinement = await getSet()
  await testInfo.attach('actual-native-before-after-refinement', { body: JSON.stringify({ nativeCapture, postRefinement }), contentType: 'application/json' })
  const fixture = seed('alignment-candidate', id) as { candidateId: string; sourceId: string; anchorId: string; localPoint: Point; nativeOnlyPoint: Point }
  current = await getSet()
  const postOwnMap = { ...postRefinement.members[1].registration }, seedOwnMap = { ...current.members[1].registration }
  delete postOwnMap.overviewFallback; delete seedOwnMap.overviewFallback
  expect(seedOwnMap).toEqual(postOwnMap)
  const manifest = await (await page.request.get(`${endpoint}/candidates`)).json() as RegistrationCandidateManifest
  const candidate = manifest.candidates.find(row => row.id === fixture.candidateId)!
  expect(candidate.currentPair).toBe(true)
  expect(candidate.currentSettings).toBe(true)
  expect(candidate.sourceSnapshotVersion).toBe(current.members[1].alignmentSourceVersion)
  expect(candidate.anchorSnapshotVersion).toBe(current.members[0].alignmentSourceVersion)
  expect(candidate.validationState).toBe('preview_only')
  expect(candidate.benchmarkMeasurements?.qualified).toBe(false)
  const native = current.members[1].nativeOverviewFallback!
  expect(native.engine).toBe('native-overview-v6')
  expect((native.evidence as Record<string, unknown>)?.phase).toBe('preview')
  const canonicalBefore = current.members[1].registration
  const rows = () => page.evaluate(() => (window as unknown as { alignmentApplications: Application[] }).alignmentApplications)
  const restorations = () => page.evaluate(() => (window as unknown as { alignmentRestorations: Restoration[] }).alignmentRestorations)
  const viewFor = async (slideId: string) => {
    const last = (await rows()).findLast(row => row.sourceSlideId === slideId || row.slideId === slideId)!
    expect(last).toBeDefined()
    return last.sourceSlideId === slideId ? last.sourceViewport : last.viewport
  }
  const panTo = async (slideId: string, point: Point) => {
    const view = await viewFor(slideId)
    const index = slideId === fixture.anchorId ? 0 : 1
    const canvas = page.locator('.comparison-pane').nth(index).locator('.openseadragon-canvas').first()
    await canvas.scrollIntoViewIfNeeded()
    const bounds = (await canvas.boundingBox())!, x = bounds.x + bounds.width / 2, y = bounds.y + bounds.height / 2
    const angle = view.rotation * Math.PI / 180, dx = (view.centerX - point[0]) * view.imageZoom, dy = (view.centerY - point[1]) * view.imageZoom
    const before = (await rows()).length
    await page.mouse.move(x, y); await page.mouse.down()
    await page.mouse.move(x + dx * Math.cos(angle) - dy * Math.sin(angle), y + dx * Math.sin(angle) + dy * Math.cos(angle), { steps: 10 })
    await page.waitForTimeout(250); await page.mouse.up(); await page.waitForTimeout(350)
    await expect.poll(async () => (await rows()).length).toBeGreaterThan(before)
  }
  await page.goto(`/admin/comparisons/${id}`)
  await expect.poll(async () => (await rows()).length).toBeGreaterThan(0)
  await expect.poll(() => loadedTiles).toBeGreaterThan(0)
  const resetReceipts: unknown[] = []
  for (const [index, method] of ['pointer', 'keyboard'].entries()) {
    const sourceId = index === 0 ? fixture.anchorId : fixture.sourceId
    const firstCell = native.overviewTriangles![0]
    const triangle = index === 0 ? firstCell.reference : firstCell.moving
    const currentView = await viewFor(sourceId)
    const interiorPoints = [[0.7, 0.2, 0.1], [0.1, 0.2, 0.7]].map(weights => [
      weights.reduce((sum, weight, vertex) => sum + weight * triangle[vertex][0], 0),
      weights.reduce((sum, weight, vertex) => sum + weight * triangle[vertex][1], 0),
    ] as Point)
    interiorPoints.sort((a, b) => Math.hypot(b[0] - currentView.centerX, b[1] - currentView.centerY) - Math.hypot(a[0] - currentView.centerX, a[1] - currentView.centerY))
    await panTo(sourceId, interiorPoints[0])
    const panned = await viewFor(sourceId)
    const button = page.locator('.comparison-pane').nth(index).getByRole('button', { name: /^Reset .* view$/ })
    const bounds = (await button.boundingBox())!
    expect(bounds.width).toBeGreaterThanOrEqual(44); expect(bounds.height).toBeGreaterThanOrEqual(44)
    const selectBounds = (await page.getByLabel(`Slide shown in pane ${index + 1}`).boundingBox())!
    expect(Math.min(bounds.x + bounds.width, selectBounds.x + selectBounds.width) - Math.max(bounds.x, selectBounds.x)).toBeLessThanOrEqual(0)
    const before = (await rows()).length
    if (method === 'keyboard') { await button.focus(); await page.keyboard.press('Enter') }
    else if (testInfo.project.use.hasTouch) await button.tap()
    else await button.click()
    await expect.poll(async () => (await rows()).slice(before).some(row => row.sourceSlideId === sourceId)).toBe(true)
    const resetView = await viewFor(sourceId)
    expect(Math.hypot(resetView.centerX - panned.centerX, resetView.centerY - panned.centerY)).toBeGreaterThan(1)
    await expect(page.locator('.comparison-setup-menu')).not.toHaveAttribute('open', '')
    resetReceipts.push({ method: method === 'pointer' && testInfo.project.use.hasTouch ? 'touch' : method, bounds, panned, resetView, applied: (await rows()).at(-1) })
  }
  const savedViews = await Promise.all([viewFor(fixture.anchorId), viewFor(fixture.sourceId)])
  await page.getByText('Advanced', { exact: true }).click()
  await page.getByText('Registration engine candidates', { exact: true }).click()
  const preview = page.getByRole('button', { name: `Preview ${candidate.engine} for ${current.members[1].displayName}` })
  await expect(preview).toBeEnabled()
  await expect(page.getByRole('button', { name: `Promote ${candidate.engine} for ${current.members[1].displayName}` })).toBeDisabled()
  await preview.click()
  await page.getByText('Advanced', { exact: true }).click()
  await expect(page.getByText('Experimental alignment preview', { exact: true })).toBeVisible()
  const supportReceipts: unknown[] = []
  const assertSupport = async (phase: string, retained: boolean) => {
    const applied = (await rows()).at(-1)!, reverse = applied.sourceSlideId === fixture.anchorId
    const cells = retained ? native.overviewTriangles! : candidate.registration!.triangles!
    const expected = cells.map(cell => inCell(cell, [applied.sourceViewport.centerX, applied.sourceViewport.centerY], reverse)).find(point => point !== null)
    expect(expected, `${phase}: actual source center must lie in independently tested support`).toBeDefined()
    expect(applied.retainedOverview).toBe(retained)
    expect(applied.regional).toBe(false)
    const residual = [Math.abs(applied.viewport.centerX - expected![0]), Math.abs(applied.viewport.centerY - expected![1])]
    expect(Math.max(...residual)).toBeLessThan(0.01)
    await expect(page.locator('.comparison-pane').getByText('Approximate overview', { exact: true })).toHaveCount(retained ? 2 : 0)
    supportReceipts.push({ phase, retained, applied, expected, residual })
  }
  await panTo(fixture.sourceId, fixture.localPoint)
  await assertSupport('own-local-forward', false)
  await panTo(fixture.sourceId, fixture.nativeOnlyPoint)
  await assertSupport('retained-native-forward', true)
  const nativeTarget = native.overviewTriangles!.map(cell => inCell(cell, fixture.nativeOnlyPoint, false)).find(point => point !== null)!
  await panTo(fixture.anchorId, [nativeTarget[0] + 1, nativeTarget[1] + 1])
  await assertSupport('retained-native-reverse', true)
  await expect.poll(() => page.locator('.comparison-pane').evaluateAll(panes => panes.filter(pane => {
    const canvas = pane.querySelector<HTMLCanvasElement>('.openseadragon-canvas canvas'), context = canvas?.getContext('2d')
    if (!canvas || !context || !canvas.width || !canvas.height) return false
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data, colors = new Set<string>()
    for (let i = 0; i < pixels.length; i += 404) if (pixels[i + 3] && pixels[i] > pixels[i + 1] + 15 && pixels[i + 2] > pixels[i + 1] + 15) colors.add(`${pixels[i]},${pixels[i + 1]},${pixels[i + 2]}`)
    return colors.size > 10
  }).length)).toBe(2)
  await page.screenshot({ path: testInfo.outputPath('candidate-retained-overview-original-pixels.png'), fullPage: true })
  const restoreCount = (await restorations()).length
  await page.getByRole('button', { name: 'Restore saved alignment', exact: true }).click()
  await expect(page.getByText('Experimental alignment preview', { exact: true })).toHaveCount(0)
  await expect.poll(async () => (await restorations()).slice(restoreCount).length).toBe(2)
  const restoredFields = (await restorations()).slice(restoreCount)
  for (const [index, id] of [fixture.anchorId, fixture.sourceId].entries()) {
    const restored = restoredFields.find(row => row.slideId === id)!
    expect(restored.actualViewport).not.toBeNull()
    for (const field of ['centerX', 'centerY', 'imageZoom', 'rotation'] as const) {
      expect(Math.abs(restored.requestedViewport[field] - savedViews[index][field])).toBeLessThan(0.01)
      expect(Math.abs(restored.actualViewport![field] - restored.requestedViewport[field])).toBeLessThan(0.01)
    }
  }
  expect((await getSet()).members[1].registration).toEqual(canonicalBefore)
  await page.getByText('Advanced', { exact: true }).click()
  await preview.click()
  await page.getByText('Advanced', { exact: true }).click()
  const oldToken = candidate.sourceSnapshotVersion
  expect((await page.request.post('/api/v2/admin/slides/batch-metadata', { headers, data: { slideIds: [fixture.sourceId], caseId: 'candidate-case-B' } })).ok()).toBe(true)
  const invalidated = await getSet()
  expect(invalidated.version).toBe(current.version)
  expect(invalidated.members[1].alignmentSourceVersion).not.toBe(oldToken)
  expect(invalidated.members[1].nativeOverviewFallback).toBeNull()
  await expect(page.getByText('Experimental alignment preview', { exact: true })).toHaveCount(0)
  await page.getByText('Advanced', { exact: true }).click()
  await expect(preview).toBeDisabled()
  await page.getByText('Advanced', { exact: true }).click()
  await page.screenshot({ path: testInfo.outputPath('candidate-source-invalidated.png'), fullPage: true })
  await testInfo.attach('candidate-reset-receipt', { body: JSON.stringify({ scope: 'Actual worker Native support, original synthetic DZI pixels, real API candidate admission and OSD viewport readback. Partial candidate support is a synthetic UI fixture, not an engine result or anatomical accuracy evidence. Captured actual foreground may be retained by the fixture only after live backend source/frame/geometry/token revalidation, preserving canonical cells/transform. Polling is held by fixture status without creating a registration job.', resetReceipts, supportReceipts, restoredFields, loadedTiles, fixture, candidateId: fixture.candidateId, currentPair: candidate.currentPair, oldToken, freshToken: invalidated.members[1].alignmentSourceVersion, comparisonVersionUnchanged: invalidated.version === current.version }), contentType: 'application/json' })
})
