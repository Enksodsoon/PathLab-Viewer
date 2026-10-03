import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'

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
  await expect(page.getByLabel('Loading mode', { exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Slide shown in pane 1')).toHaveCSS('appearance', 'none')
  await expect(page.getByLabel('Slide shown in pane 1')).toHaveCSS('background-color', 'rgb(45, 43, 39)')
  await expect(page.getByLabel('Slide shown in pane 1')).toHaveCSS('color', 'rgb(255, 255, 255)')
  const applications = () => page.evaluate(() => (window as unknown as { alignmentApplications: Array<{ slideId: string; sourceViewport: { centerX: number; centerY: number; imageZoom: number }; viewport: { centerX: number; centerY: number }; approximate: boolean }> }).alignmentApplications)
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
  const previewResponse = page.waitForResponse(response => response.url().endsWith('/region-corrections') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Preview correction' }).click()
  const preview = await previewResponse
  expect(preview.ok(), await preview.text()).toBe(true)
  const previewSet = await preview.json()
  expect(previewSet.regionalCorrections).toHaveLength(1)
  expect(previewSet.regionalCorrections[0].registration.status).toBe('approximate')
  await expect(page.getByText('Unsaved correction preview', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('alignment-region-preview.png'), fullPage: true })
  const saveResponse = page.waitForResponse(response => response.url().endsWith('/region-corrections') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save correction' }).click()
  const savedResponse = await saveResponse
  expect(savedResponse.ok(), await savedResponse.text()).toBe(true)
  expect(savedResponse.request().postDataJSON()).toMatchObject({ sourceVersion: previewSet.regionalCorrections[0].sourceVersion, targetVersion: previewSet.regionalCorrections[0].targetVersion })
  const savedSet = await savedResponse.json()
  expect(savedSet.version).toBe(previewSet.version + 1)
  expect(savedSet.regionalCorrections[0].regionId).toBe(previewSet.regionalCorrections[0].regionId)
  await expect(page.getByText('Region correction saved.', { exact: false })).toBeVisible()
  await page.reload()
  await expect.poll(async () => (await applications()).length).toBeGreaterThan(0)
  await driveToInterior()
  await page.getByRole('button', { name: 'Adjust region' }).click()
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
  const twoPointResponse = page.waitForResponse(response => response.url().endsWith('/region-corrections') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Preview correction' }).click()
  const twoPoint = await twoPointResponse
  expect(twoPoint.ok(), await twoPoint.text()).toBe(true)
  expect(twoPoint.request().postDataJSON().movingPoints).toHaveLength(2)
  await page.getByRole('button', { name: 'Cancel correction' }).click()
  const afterCancel = await (await page.request.get(endpoint)).json()
  expect(afterCancel.version).toBe(savedSet.version)
  expect(afterCancel.regionalCorrections).toHaveLength(1)
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
