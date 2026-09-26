import { expect, test } from './qa-test'
import { readFile } from 'node:fs/promises'
import { signIn, uploadSyntheticSlide, waitForSlideConversion } from '../e2e-live/capacity-helpers'

test('every authored geometry persists; annotation edit, duplicate, trash, restore and export work', async ({ page, isMobile }, testInfo) => {
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  const id = await uploadSyntheticSlide(page, process.env.PATHLAB_E2E_OME!, 'QA annotation lifecycle')
  await waitForSlideConversion(page, id)
  await page.goto(`/admin/preview/${id}`)
  await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toBeVisible()
  if (isMobile) {
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 })
      await expect.poll(() => page.locator('.annotation-commandbar').evaluate((bar) =>
        bar.scrollWidth <= bar.clientWidth + 1)).toBe(true)
    }
  }
  const overlay = page.locator('.annotation-svg-overlay')
  const read = async () => (await (await page.request.get(`/api/v2/admin/annotations/slides/${id}/items?limit=1000`)).json())
  let count = 0
  const touch = isMobile ? await page.context().newCDPSession(page) : null
  for (const [tool, gesture] of [['Point marker', 'point'], ['Rectangle', 'drag'], ['Ellipse', 'drag'],
    ['Ruler', 'drag'], ['Freehand ROI', 'freehand'], ['Polygon', 'path'], ['Polyline', 'path'],
    ['Three-point angle', 'angle'], ['Text callout', 'point']]) {
    await test.step(tool, async () => {
      if (isMobile) {
        const close = page.getByRole('dialog', { name: 'Annotation inspector', exact: true }).getByRole('button', { name: 'Close annotation inspector', exact: true })
        if (await close.isVisible()) await close.click()
      }
      const button = page.getByRole('button', { name: tool, exact: true })
      if (!await button.isVisible()) await page.getByRole('button', { name: 'More annotation tools', exact: true }).click()
      await button.click()
      await expect(page.getByRole('button', { name: 'More annotation tools', exact: true })).toHaveAttribute('aria-expanded', 'false')
      const box = (await overlay.boundingBox())!
      if (!count) await testInfo.attach('gesture-viewport.json', { body: JSON.stringify({ box, viewport: page.viewportSize(), url: page.url() }), contentType: 'application/json' })
      const points = [[box.x + box.width * (isMobile ? .75 : .43), box.y + box.height * .4],
        [box.x + box.width * (isMobile ? .9 : .56), box.y + box.height * .4],
        [box.x + box.width * (isMobile ? .9 : .56), box.y + box.height * .55]]
      expect(await page.evaluate(([x, y]) => Boolean(document.elementFromPoint(x, y)?.closest('.annotation-svg-overlay')), points[0])).toBe(true)
      if (gesture === 'point') {
        if (isMobile) await page.touchscreen.tap(...points[0] as [number, number])
        else await page.mouse.click(...points[0] as [number, number])
      }
      else if (gesture === 'path' || gesture === 'angle') {
        for (const point of points) {
          if (isMobile) await page.touchscreen.tap(...point as [number, number])
          else await page.mouse.click(...point as [number, number])
        }
        if (gesture === 'path') await page.keyboard.press('Enter')
      } else if (touch) {
        await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: points[0][0], y: points[0][1] }] })
        for (const point of [...points.slice(1), ...(gesture === 'freehand' ? [points[0]] : [])]) {
          await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: point[0], y: point[1] }] })
        }
        await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
      } else {
        await page.mouse.move(...points[0] as [number, number])
        await page.mouse.down()
        await page.mouse.move(...points[1] as [number, number], { steps: 8 })
        await page.mouse.move(...points[2] as [number, number], { steps: 8 })
        if (gesture === 'freehand') await page.mouse.move(...points[0] as [number, number], { steps: 8 })
        await page.mouse.up()
      }
      count++
      await expect.poll(async () => (await read()).total).toBe(count)
    })
  }
  await page.reload()
  const geometryTypes = (await read()).items.map((item: { geometry: { type: string } }) => item.geometry.type)
  expect(new Set(geometryTypes)).toEqual(new Set(['point', 'rectangle', 'ellipse', 'polyline', 'polygon', 'angle', 'text']))
  await page.getByRole('button', { name: 'Open annotations', exact: true }).click()
  await page.getByRole('button', { name: /point annotation/ }).click()
  const inspector = page.getByRole(isMobile ? 'dialog' : 'region', { name: 'Annotation inspector', exact: true })
  await inspector.getByLabel('Title', { exact: true }).fill('QA persisted annotation')
  await inspector.getByLabel('Classification', { exact: true }).fill('Synthetic QA')
  await expect.poll(async () => (await read()).items.find((item: { geometry: { type: string } }) => item.geometry.type === 'point')?.metadata.title).toBe('QA persisted annotation')
  await page.getByRole('button', { name: 'Duplicate selected annotations', exact: true }).click()
  await expect.poll(async () => (await read()).total).toBe(count + 1)
  await inspector.getByLabel('Title', { exact: true }).fill('QA trash restore')
  await inspector.getByLabel('Classification', { exact: true }).focus()
  await expect(page.getByRole('status').filter({ hasText: /^Saved$/ })).toBeVisible()
  if (isMobile) await page.screenshot({ path: testInfo.outputPath('annotations-mobile-saved.png') })
  await page.getByRole('button', { name: 'Delete selected annotations', exact: true }).click()
  await expect.poll(async () => (await read()).total).toBe(count)
  await page.getByRole('button', { name: 'Undo', exact: true }).click()
  await expect.poll(async () => (await read()).total).toBe(count + 1)
  await page.getByRole('button', { name: 'Redo', exact: true }).click()
  await expect.poll(async () => (await read()).total).toBe(count)
  await expect(page.getByRole('status').filter({ hasText: /^Saved$/ })).toBeVisible()
  if (isMobile) await inspector.getByRole('button', { name: 'Close annotation inspector', exact: true }).click()
  await page.getByRole('checkbox', { name: 'Trash', exact: true }).check()
  await page.locator('[data-annotation-row]').filter({ hasText: 'QA trash restore' }).click()
  await page.getByRole('button', { name: 'Restore selected annotations', exact: true }).click()
  count++
  await expect.poll(async () => (await read()).total).toBe(count)
  await expect(page.getByRole('status').filter({ hasText: /^Saved$/ })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: 'Open annotations', exact: true }).click()
  await page.locator('[data-annotation-row]').filter({ hasText: 'QA trash restore' }).click()
  await expect(inspector).toBeVisible()
  await page.getByRole('button', { name: 'Show advanced annotation details', exact: true }).click()
  await page.getByRole('button', { name: 'Add annotation layer', exact: true }).click()
  const visibleLayer = page.getByRole('checkbox', { name: 'Show Layer 2', exact: true })
  const lockedLayer = page.getByRole('checkbox', { name: 'Lock Layer 2', exact: true })
  await visibleLayer.click()
  await expect(visibleLayer).not.toBeChecked()
  await lockedLayer.click()
  await expect(lockedLayer).toBeChecked()
  await expect(page.getByRole('button', { name: 'Layer 2', exact: true })).toBeDisabled()
  await lockedLayer.click()
  await expect(lockedLayer).not.toBeChecked()
  await visibleLayer.click()
  await expect(visibleLayer).toBeChecked()
  await page.getByRole('button', { name: 'Move Layer 2 up', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Move Layer 2 up', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Move Layer 2 down', exact: true }).click()
  await page.getByRole('slider', { name: 'Layer 2 opacity', exact: true }).press('ArrowLeft')
  await page.getByRole('button', { name: 'Reload annotations', exact: true }).click()
  await expect(page.locator('.annotation-operation-status')).toHaveText('Annotations reloaded from server')
  await expect(page.getByRole('slider', { name: 'Layer 2 opacity', exact: true })).toHaveValue('0.95')
  let exported = ''
  let geojson = ''
  for (const format of ['PathLab JSON', 'GeoJSON', 'measurements CSV']) {
    const downloading = page.waitForEvent('download')
    await page.getByRole('button', { name: `Export ${format}`, exact: true }).click()
    const download = await downloading
    expect(await download.failure()).toBeNull()
    const file = testInfo.outputPath(download.suggestedFilename())
    await download.saveAs(file)
    if (format === 'PathLab JSON') exported = file
    if (format === 'GeoJSON') geojson = file
    expect((await readFile(file)).length).toBeGreaterThan(10)
  }
  await inspector.locator('input[type="file"]').setInputFiles(exported)
  await page.getByRole('button', { name: 'Confirm annotation import', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('ANNOTATION_IMPORT_ID_CONFLICT')
  expect((await read()).total).toBe(count)
  await page.getByRole('button', { name: 'Retry annotations', exact: true }).click()
  await expect(page.getByRole('alert')).not.toBeVisible()
  await expect(page.locator('.annotation-operation-status')).toHaveText(/^Annotations ready/)
  await page.reload()
  await page.getByRole('button', { name: 'Open annotations', exact: true }).click()
  await page.locator('[data-annotation-row]').filter({ hasText: 'QA persisted annotation' }).click()
  await page.getByRole('button', { name: 'Show advanced annotation details', exact: true }).click()
  await inspector.locator('input[type="file"]').setInputFiles(geojson)
  await page.getByRole('button', { name: 'Confirm annotation import', exact: true }).click()
  await expect.poll(async () => (await read()).total).toBe(count * 2)
  await page.reload()
  await page.getByRole('button', { name: 'Open annotations', exact: true }).click()
  await page.getByRole('searchbox', { name: 'Search annotations', exact: true }).fill('QA persisted annotation')
  await expect(page.getByRole('button', { name: /QA persisted annotation/ }).first()).toBeVisible()
})
