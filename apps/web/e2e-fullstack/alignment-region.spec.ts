import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'
import { mapStackPoint, type Point } from '../src/alignment'
import type { ComparisonSet } from '../src/types'

type Application = { sourceSlideId: string; slideId: string; regional: boolean; approximate: boolean; sourceViewport: { centerX: number; centerY: number; imageZoom: number; rotation: number }; viewport: { centerX: number; centerY: number; imageZoom: number; rotation: number } }

test('alignment region correction uses real tissue, hidden-reference panes, revision save and two-point cancel', async ({ page }, testInfo) => {
  let loadedTiles = 0
  page.on('response', response => { if (response.ok() && response.url().includes('/preview/slide_files/')) loadedTiles += 1 })
  await page.addInitScript(() => {
    Object.assign(window, { alignmentApplications: [] })
    window.addEventListener('pathlab:alignment-applied', event => (window as unknown as { alignmentApplications: unknown[] }).alignmentApplications.push((event as CustomEvent).detail))
  })
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  const { slideIds } = JSON.parse(execFileSync(process.env.PATHLAB_E2E_PYTHON!, [path.resolve('../../scripts/seed_frontend_qa.py'), 'alignment'], { encoding: 'utf8' })) as { slideIds: string[] }
  const auth = await (await page.request.get('/api/v1/auth/session')).json() as { csrfToken: string }
  const created = await page.request.post('/api/v1/admin/comparison-sets', { headers: { 'X-CSRF-Token': auth.csrfToken }, data: { name: 'Region correction QA', slideIds: slideIds.slice(0, 3), referenceSlideId: slideIds[0] } })
  expect(created.ok()).toBe(true)
  const { id } = await created.json() as { id: string }
  const endpoint = `/api/v1/admin/comparison-sets/${id}`
  await expect.poll(async () => {
    const current = await (await page.request.get(endpoint)).json()
    return current.members.filter((member: { registration?: { status: string } }) => ['ready', 'approximate'].includes(member.registration?.status ?? '')).length
  }, { timeout: 25_000 }).toBe(2)
  await page.evaluate(({ id, panes }) => sessionStorage.setItem(`pathlab-comparison-view:admin:${id}`, JSON.stringify(panes)), { id, panes: slideIds.slice(1, 3) })
  await page.goto(`/admin/comparisons/${id}`)
  await expect(page.getByLabel('Slide shown in pane 1')).toHaveValue(slideIds[1])
  await expect(page.getByLabel('Slide shown in pane 2')).toHaveValue(slideIds[2])
  await expect(page.locator('.comparison-setup-menu')).not.toHaveAttribute('open', '')
  const currentSet = await (await page.request.get(endpoint)).json()
  const slidesButton = page.getByRole('button', { name: 'Slides', exact: true })
  await slidesButton.focus(); await page.keyboard.press('Enter')
  await expect(slidesButton).toHaveAttribute('aria-expanded', 'true')
  await page.locator('#comparison-slides button').filter({ hasText: currentSet.members[0].displayName }).click()
  await expect(page.getByLabel('Slide shown in pane 1')).toHaveValue(slideIds[0])
  await page.locator('#comparison-slides button').filter({ hasText: currentSet.members[1].displayName }).click()
  await expect(page.getByLabel('Slide shown in pane 1')).toHaveValue(slideIds[1])
  await slidesButton.focus(); await page.keyboard.press('Enter')
  await expect(slidesButton).toHaveAttribute('aria-expanded', 'false')
  await page.getByRole('button', { name: 'Views linked' }).focus(); await page.keyboard.press('Enter')
  await expect(page.getByRole('button', { name: 'Views independent' })).toHaveAttribute('aria-pressed', 'false')
  await page.getByRole('button', { name: 'Views independent' }).focus(); await page.keyboard.press('Enter')
  await expect(page.getByRole('button', { name: 'Views linked' })).toHaveAttribute('aria-pressed', 'true')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  await expect(page.getByLabel('Loading mode', { exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Slide shown in pane 1')).toHaveCSS('appearance', 'none')
  await expect(page.getByLabel('Slide shown in pane 1')).toHaveCSS('background-color', 'rgb(45, 43, 39)')
  await expect(page.getByLabel('Slide shown in pane 1')).toHaveCSS('color', 'rgb(255, 255, 255)')
  const applications = () => page.evaluate(() => (window as unknown as { alignmentApplications: Application[] }).alignmentApplications)
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(0)
  const last = (await applications()).at(-1)!
  expect(last.sourceViewport.centerX).toBeGreaterThan(60)
  expect(last.sourceViewport.centerX).toBeLessThan(570)
  await expect.poll(() => loadedTiles).toBeGreaterThan(0)
  await expect(page.getByText('Slide tiles could not be loaded.', { exact: true })).toHaveCount(0)
  const driveToInterior = async () => {
    const current = (await applications()).at(-1)!.sourceViewport
    const before = (await applications()).length
    const canvas = page.locator('.comparison-pane').first().locator('.openseadragon-canvas').first()
    await canvas.scrollIntoViewIfNeeded()
    const bounds = (await canvas.boundingBox())!
    const x = bounds.x + bounds.width / 2, y = bounds.y + bounds.height / 2
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.mouse.move(x + (current.centerX - 250) * current.imageZoom, y + (current.centerY - 200) * current.imageZoom, { steps: 5 })
    // End a deliberate pan without an inertial flick across the tissue edge.
    await page.waitForTimeout(250)
    await page.mouse.up()
    await expect.poll(async () => (await applications()).length).toBeGreaterThan(before)
    await page.waitForTimeout(350)
    const field = (await applications()).at(-1)!.sourceViewport
    expect(field.centerX).toBeGreaterThan(180)
    expect(field.centerX).toBeLessThan(330)
    expect(field.centerY).toBeGreaterThan(120)
    expect(field.centerY).toBeLessThan(300)
  }
  const manualPathReceipts: unknown[] = []
  const assertManualPath = async (set: ComparisonSet, phase: string, minimumApplications = 0) => {
    await expect.poll(async () => { const rows = await applications(); return rows.length > minimumApplications && rows.at(-1)?.regional }).toBe(true)
    const applied = (await applications()).at(-1)!, region = set.regionalCorrections![0]
    expect([region.sourceSlideId, region.targetSlideId]).toContain(applied.sourceSlideId)
    const [[a, b, tx], [c, d, ty]] = region.registration.movingToReference!
    const x = applied.sourceViewport.centerX, y = applied.sourceViewport.centerY
    const forward = applied.sourceSlideId === region.sourceSlideId, determinant = a * d - b * c
    const expected = forward ? [a * x + b * y + tx, c * x + d * y + ty] : [(d * (x - tx) - b * (y - ty)) / determinant, (-c * (x - tx) + a * (y - ty)) / determinant]
    expect(applied.slideId).toBe(forward ? region.targetSlideId : region.sourceSlideId)
    const sourcePoint = forward ? [x, y] : expected, [left, top, width, height] = region.sourceBounds
    expect(sourcePoint[0]).toBeGreaterThanOrEqual(left); expect(sourcePoint[0]).toBeLessThanOrEqual(left + width)
    expect(sourcePoint[1]).toBeGreaterThanOrEqual(top); expect(sourcePoint[1]).toBeLessThanOrEqual(top + height)
    const residual = [Math.abs(applied.viewport.centerX - expected[0]), Math.abs(applied.viewport.centerY - expected[1])]
    expect(Math.max(...residual)).toBeLessThan(0.01)
    expect(applied.approximate).toBe(true)
    for (const pane of await page.locator('.comparison-pane').all()) {
      const label = pane.getByText('Manually adjusted approximation', { exact: true })
      await expect(label).toBeVisible()
      const labelBounds = (await label.boundingBox())!, paneBounds = (await pane.boundingBox())!, headerBounds = (await pane.locator('header').boundingBox())!
      expect(labelBounds.x).toBeGreaterThanOrEqual(paneBounds.x)
      expect(labelBounds.x + labelBounds.width).toBeLessThanOrEqual(paneBounds.x + paneBounds.width)
      expect(labelBounds.y).toBeGreaterThanOrEqual(headerBounds.y + headerBounds.height)
    }
    await expect(page.locator('.comparison-setup-menu')).not.toHaveAttribute('open', '')
    manualPathReceipts.push({ phase, applied, expected, residual, supportedCapturedRegion: true, bothManualLabelsVisible: true, labelsClearOfControls: true })
  }
  const panSourceTo = async (sourceId: string, point: Point) => {
    const rows = await applications(), last = rows.findLast(row => row.sourceSlideId === sourceId || row.slideId === sourceId)!
    const view = last.sourceSlideId === sourceId ? last.sourceViewport : last.viewport
    const selects = await page.getByLabel(/Slide shown in pane/).all(), paneIndex = (await Promise.all(selects.map(select => select.inputValue()))).indexOf(sourceId)
    expect(paneIndex).toBeGreaterThanOrEqual(0)
    const canvas = page.locator('.comparison-pane').nth(paneIndex).locator('.openseadragon-canvas').first()
    await canvas.scrollIntoViewIfNeeded()
    const bounds = (await canvas.boundingBox())!, x = bounds.x + bounds.width / 2, y = bounds.y + bounds.height / 2
    const radians = view.rotation * Math.PI / 180, dx = (view.centerX - point[0]) * view.imageZoom, dy = (view.centerY - point[1]) * view.imageZoom
    await page.mouse.move(x, y); await page.mouse.down()
    await page.mouse.move(x + dx * Math.cos(radians) - dy * Math.sin(radians), y + dx * Math.sin(radians) + dy * Math.cos(radians), { steps: 8 })
    await page.waitForTimeout(250); await page.mouse.up(); await page.waitForTimeout(350)
    await expect.poll(async () => (await applications()).length).toBeGreaterThan(rows.length)
  }
  await driveToInterior()
  // Assert rendered original pixels as well as successful tile responses.
  await expect.poll(() => page.locator('.comparison-pane').first().locator('.openseadragon-canvas canvas').first().evaluate(element => {
    const canvas = element as HTMLCanvasElement
    const context = canvas.getContext('2d')
    if (!context || !canvas.width || !canvas.height) return 0
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
    let tissuePixels = 0
    for (let index = 0; index < pixels.length; index += 128) {
      if (pixels[index + 3] > 0 && pixels[index] > pixels[index + 1] + 15 && pixels[index + 2] > pixels[index + 1] + 15 && pixels[index + 1] < 220) tissuePixels += 1
    }
    return tissuePixels
  })).toBeGreaterThan(100)
  await page.screenshot({ path: testInfo.outputPath('alignment-light.png'), fullPage: true })
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'))
  await page.screenshot({ path: testInfo.outputPath('alignment-dark.png'), fullPage: true })
  for (const control of await page.locator('.comparison-view-controls button').all()) {
    const bounds = (await control.boundingBox())!
    expect(bounds.height).toBeGreaterThanOrEqual(44)
  }
  await page.getByRole('button', { name: 'Adjust region' }).click()
  await expect(page.getByLabel('Correction reference slide')).toHaveValue(slideIds[2])
  await page.getByRole('button', { name: 'Record point pair' }).click()
  let previewFailureInjected = false
  await page.route(`**${endpoint}/region-corrections`, async route => {
    if (!previewFailureInjected && route.request().method() === 'POST' && route.request().postDataJSON().operation === 'preview') {
      previewFailureInjected = true
      await route.fulfill({ status: 503, json: { detail: { code: 'QA_TRANSIENT_PREVIEW_FAILURE' } } })
    } else await route.continue()
  })
  await page.getByRole('button', { name: 'Preview correction' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByText('1 point pairs', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Preview correction' })).toBeEnabled()
  const beforeOnePreview = (await applications()).length
  const previewResponse = page.waitForResponse(response => response.url().endsWith('/region-corrections') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Preview correction' }).click()
  const preview = await previewResponse
  expect(preview.ok(), await preview.text()).toBe(true)
  const previewSet = await preview.json()
  expect(previewSet.regionalCorrections).toHaveLength(1)
  expect(previewSet.regionalCorrections[0].registration.status).toBe('approximate')
  expect(previewSet.regionalCorrections[0].basisVersion).toEqual(expect.any(String))
  await expect(page.getByText('Unsaved correction preview', { exact: true })).toBeVisible()
  await assertManualPath(previewSet, 'one-point-preview', beforeOnePreview)
  await page.screenshot({ path: testInfo.outputPath('alignment-region-preview.png'), fullPage: true })
  const beforeOneSave = (await applications()).length
  const saveResponse = page.waitForResponse(response => response.url().endsWith('/region-corrections') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save correction' }).click()
  const savedResponse = await saveResponse
  expect(savedResponse.ok(), await savedResponse.text()).toBe(true)
  expect(savedResponse.request().postDataJSON()).toMatchObject({ sourceVersion: previewSet.regionalCorrections[0].sourceVersion, targetVersion: previewSet.regionalCorrections[0].targetVersion, basisVersion: previewSet.regionalCorrections[0].basisVersion })
  const savedSet = await savedResponse.json()
  expect(savedSet.version).toBe(previewSet.version + 1)
  expect(savedSet.regionalCorrections[0].regionId).toBe(previewSet.regionalCorrections[0].regionId)
  await expect(page.getByText('Region correction saved.', { exact: false })).toBeVisible()
  await assertManualPath(savedSet, 'one-point-save', beforeOneSave)
  await page.reload()
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(0)
  await assertManualPath(savedSet, 'one-point-reload')
  await driveToInterior()
  await page.getByRole('button', { name: 'Adjust region' }).click()
  const recordTwoPoints = async () => {
  await page.getByRole('button', { name: 'Record point pair' }).click()
  for (const pane of await page.locator('.comparison-pane').all()) {
    const canvas = pane.locator('.openseadragon-canvas').first()
    await canvas.scrollIntoViewIfNeeded()
    const bounds = (await canvas.boundingBox())!
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2)
    await page.mouse.down()
    await page.mouse.move(bounds.x + bounds.width / 2 - 40, bounds.y + bounds.height / 2 - 25, { steps: 5 })
    await page.waitForTimeout(250)
    await page.mouse.up()
    await page.waitForTimeout(350)
  }
  await page.getByRole('button', { name: 'Record point pair' }).click()
  await expect(page.getByRole('button', { name: 'Record point pair' })).toBeDisabled()
  }
  await recordTwoPoints()
  const twoPointResponse = page.waitForResponse(response => response.url().endsWith('/region-corrections') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Preview correction' }).click()
  const twoPoint = await twoPointResponse
  expect(twoPoint.ok(), await twoPoint.text()).toBe(true)
  expect(twoPoint.request().postDataJSON().movingPoints).toHaveLength(2)
  await assertManualPath(await twoPoint.json(), 'two-point-preview-before-cancel')
  await page.getByRole('button', { name: 'Cancel correction' }).click()
  const afterCancel = await (await page.request.get(endpoint)).json()
  expect(afterCancel.version).toBe(savedSet.version)
  expect(afterCancel.regionalCorrections).toHaveLength(1)
  await assertManualPath(afterCancel, 'cancel-restored-saved-region')
  await page.getByRole('button', { name: 'Adjust region' }).click()
  await recordTwoPoints()
  const secondPreviewResponse = page.waitForResponse(response => response.url().endsWith('/region-corrections') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Preview correction' }).click()
  const secondPreview = await secondPreviewResponse
  expect(secondPreview.ok(), await secondPreview.text()).toBe(true)
  await assertManualPath(await secondPreview.json(), 'two-point-preview-before-save')
  const secondSaveResponse = page.waitForResponse(response => response.url().endsWith('/region-corrections') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save correction' }).click()
  const secondSave = await secondSaveResponse
  expect(secondSave.ok(), await secondSave.text()).toBe(true)
  const twiceSaved = await secondSave.json()
  expect(twiceSaved.version).toBe(savedSet.version + 1)
  expect(twiceSaved.regionalCorrections).toHaveLength(2)
  expect(secondSave.request().postDataJSON().movingPoints).toHaveLength(2)
  await assertManualPath(twiceSaved, 'two-point-save')
  await page.reload()
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(0)
  const reloadedSet = await (await page.request.get(endpoint)).json()
  expect(reloadedSet.version).toBe(twiceSaved.version)
  expect(reloadedSet.regionalCorrections).toHaveLength(2)
  await assertManualPath(reloadedSet, 'two-point-reload')
  await expect(page.locator('.comparison-setup-menu')).not.toHaveAttribute('open', '')
  await page.screenshot({ path: testInfo.outputPath('alignment-two-point-saved.png'), fullPage: true })
  const sourceId = reloadedSet.regionalCorrections[0].sourceSlideId
  const outsideCandidates: Point[] = []
  for (let y = 60; y <= 400; y += 20) for (let x = 60; x <= 560; x += 20) {
    const outsideEveryRegion = reloadedSet.regionalCorrections.every((region: NonNullable<ComparisonSet['regionalCorrections']>[number]) => { const [left, top, width, height] = region.sourceBounds; return x < left || y < top || x > left + width || y > top + height })
    if (outsideEveryRegion && mapStackPoint([x, y], sourceId, reloadedSet.regionalCorrections[0].targetSlideId, reloadedSet.referenceSlideId, reloadedSet.members, 'best', 0)) outsideCandidates.push([x, y])
  }
  expect(outsideCandidates.length).toBeGreaterThan(0)
  const current = (await applications()).at(-1)!, sourceView = current.sourceSlideId === sourceId ? current.sourceViewport : current.viewport
  outsideCandidates.sort((a, b) => Math.hypot(a[0] - sourceView.centerX, a[1] - sourceView.centerY) - Math.hypot(b[0] - sourceView.centerX, b[1] - sourceView.centerY))
  await panSourceTo(sourceId, outsideCandidates[0])
  const outsideApplied = (await applications()).at(-1)!
  expect(outsideApplied.sourceSlideId).toBe(sourceId); expect(outsideApplied.regional).toBe(false)
  await expect(page.getByText('Manually adjusted approximation', { exact: true })).toHaveCount(0)
  await expect(page.locator('.comparison-pane').filter({ has: page.getByText('Approximate sync', { exact: true }) })).toHaveCount(2)
  await page.screenshot({ path: testInfo.outputPath('alignment-outside-region-overview.png'), fullPage: true })
  manualPathReceipts.push({ phase: 'outside-all-regions-overview', applied: outsideApplied, manualLabelsAbsent: true })
  const movingCell = reloadedSet.regionalCorrections[0].registration.triangles[0].moving as Point[]
  await panSourceTo(sourceId, [movingCell.reduce((sum, point) => sum + point[0], 0) / 3, movingCell.reduce((sum, point) => sum + point[1], 0) / 3])
  await assertManualPath(reloadedSet, 'returned-to-supported-region')
  await testInfo.attach('manual-path-receipt', { body: JSON.stringify({ scope: 'Actual regional API affine and independent forward/inverse affine oracle against real OSD readback; synthetic navigation only.', coordinateTolerancePixels: 0.01, observations: manualPathReceipts }), contentType: 'application/json' })
  await testInfo.attach('guided-correction-receipt' , { body: JSON.stringify({ scope: 'Disposable synthetic tissue derivative, actual OSD and backend region API; no anatomical qualification.', loadedTiles, hiddenReference: true, slidesKeyboardSelection: true, syncKeyboardRoundtrip: true, advancedOpenedDuringGuidedCorrection: false, onePointSavedReloaded: true, twoPointPreviewCancelled: true, twoPointSavedReloaded: true, injectedTransientPreviewFailureRetainedPoints: previewFailureInjected, assertionRetries: testInfo.retry }), contentType: 'application/json' })
  await page.getByText('Advanced', { exact: true }).click()
  await expect(page.getByRole('region', { name: 'Active pane inspector' })).toBeVisible()
  await page.getByText('Display', { exact: true }).click()
  await expect(page.getByLabel('Tile detail')).toBeVisible()
  await page.getByLabel('Tile detail').selectOption('full')
  await page.getByLabel('Tile detail').selectOption('data-saver')
  expect(await page.evaluate(() => localStorage.getItem('pathlab-viewer-loading-mode:v1'))).toBe('data-saver')
  await page.screenshot({ path: testInfo.outputPath('alignment-inspector.png'), fullPage: true })
  await page.reload()
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(0)
  await page.getByText('Advanced', { exact: true }).click()
  await page.getByText('Display', { exact: true }).click()
  await expect(page.getByLabel('Tile detail')).toHaveValue('data-saver')
  await expect(page.getByLabel('Loading mode', { exact: true })).toHaveCount(0)
})
