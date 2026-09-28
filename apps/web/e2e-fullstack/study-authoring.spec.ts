import { readFile } from 'node:fs/promises'
import { expect, test } from './qa-test'
import { signIn, uploadSyntheticSlide, waitForSlideConversion } from '../e2e-live/capacity-helpers'

test('author, import, preview and publish a synthetic Study Pack', async ({ page }, testInfo) => {
  const username = process.env.PATHLAB_E2E_USERNAME
  const password = process.env.PATHLAB_E2E_PASSWORD
  const source = process.env.PATHLAB_E2E_OME
  if (!username || !password || !source) throw new Error('Run through the isolated stack launcher')

  const suffix = Date.now().toString(36).toLowerCase()
  const slideName = `QA Study slide ${suffix}`
  const packTitle = `QA Study pack ${suffix}`
  const packKey = `qa-study-${suffix}`
  await signIn(page, username, password)
  const slideId = await uploadSyntheticSlide(page, source, slideName)
  await waitForSlideConversion(page, slideId)
  await page.reload()
  await expect(page.getByRole('heading', { name: slideName, exact: true })).toBeVisible()
  const slideActions = page.getByRole('button', { name: `More actions for ${slideName}`, exact: true })
  await slideActions.scrollIntoViewIfNeeded()
  await slideActions.click()
  const publishAction = page.getByRole('menuitem', { name: 'Publish', exact: true })
  await expect(publishAction).toBeInViewport({ ratio: 1 })
  await publishAction.click()
  const publication = page.getByRole('dialog', { name: 'Confirm deidentification', exact: true })
  await publication.getByRole('checkbox').check()
  const publishResponse = page.waitForResponse((response) => response.request().method() === 'POST'
    && new URL(response.url()).pathname === `/api/v1/admin/slides/${slideId}/publish`)
  await publication.getByRole('button', { name: 'Publish 1 slide', exact: true }).click()
  const published = await publishResponse
  expect(published.ok(), await published.text()).toBe(true)
  await expect(publication).not.toBeVisible()
  const eligibility = await page.evaluate(async (id) => {
    const [slideResponse, authoringResponse] = await Promise.all([
      fetch(`/api/v1/admin/slides/${encodeURIComponent(id)}`),
      fetch('/api/v1/admin/study/authoring/slides'),
    ])
    return {
      slide: { status: slideResponse.status, value: await slideResponse.json() },
      authoring: { status: authoringResponse.status, value: await authoringResponse.json() },
    }
  }, slideId)
  await testInfo.attach('study-slide-eligibility.json', { body: JSON.stringify(eligibility, null, 2), contentType: 'application/json' })
  expect(eligibility.authoring.value.some((item: { id: string }) => item.id === slideId), JSON.stringify(eligibility)).toBe(true)
  await page.goto('/admin/study/packs/new')
  await expect(page.getByRole('heading', { name: 'Author a Study Pack', exact: true })).toBeVisible()
  const slide = page.getByRole('combobox', { name: 'Viewer slide', exact: true })
  await expect(slide.getByRole('option', { name: slideName, exact: true })).toHaveCount(1)
  await slide.selectOption({ label: slideName })

  for (const [label, value] of [
    ['Pack key', packKey], ['Title', packTitle], ['Author', 'Synthetic QA faculty'],
    ['License', 'CC-BY-4.0'], ['Revision', '2026-09-27'],
  ]) await page.getByRole('textbox', { name: label, exact: true }).fill(value)
  await page.getByRole('spinbutton', { name: 'Version', exact: true }).fill('1')
  await page.getByRole('textbox', { name: 'Provenance', exact: true }).fill('Synthetic isolated-stack test fixture.')

  await page.getByRole('textbox', { name: 'Task ID', exact: true }).fill('manual-task')
  await page.getByRole('textbox', { name: 'Prompt', exact: true }).fill('Choose the synthetic reference answer.')
  await page.getByRole('textbox', { name: 'Options, one per line', exact: true }).fill('Reference\nDistractor')
  await page.getByRole('textbox', { name: 'Explicit answer', exact: true }).fill('Reference')
  await page.getByRole('textbox', { name: 'Hints, one per line (maximum 3)', exact: true }).fill('Review the faculty source.\nCompare the example.')
  await page.getByRole('textbox', { name: 'Faculty explanation', exact: true }).fill('This fixture has an explicit faculty answer.')
  await page.getByRole('textbox', { name: 'Source title', exact: true }).fill('Synthetic faculty source')
  await page.getByRole('textbox', { name: 'HTTPS source URL', exact: true }).fill('https://example.edu/pathlab-qa')
  await page.getByRole('button', { name: 'Add task', exact: true }).click()
  await expect(page.getByText('Choose the synthetic reference answer.', { exact: true })).toBeVisible()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export draft', exact: true }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe(`${packKey}-draft.json`)
  const json = await readFile((await download.path())!)
  await page.locator('input[type="file"]').nth(1).setInputFiles({ name: download.suggestedFilename(), mimeType: 'application/json', buffer: json })
  await expect(page.getByText('Choose the synthetic reference answer.', { exact: true })).toBeVisible()

  await page.locator('input[type="file"]').nth(1).setInputFiles({ name: 'invalid.json', mimeType: 'application/json', buffer: Buffer.from('{') })
  await expect(page.getByRole('alert')).toContainText('JSON')
  await page.locator('input[type="file"]').nth(0).setInputFiles({ name: 'invalid.csv', mimeType: 'text/csv', buffer: Buffer.from('id,type\nmissing,spatial') })
  await expect(page.getByRole('alert')).toContainText('CSV column slideId is required.')

  const csv = [
    'id,type,slideId,prompt,options,answerKey,explanation,sourceTitle,sourceUrl',
    `csv-task,multiple-choice,${slideId},Check the second synthetic answer.,Option A|Option B,Option B,The explicit imported key is B.,Imported source,https://example.edu/imported`,
  ].join('\n')
  await page.locator('input[type="file"]').nth(0).setInputFiles({ name: 'valid.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByText('Check the second synthetic answer.', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Edit', exact: true }).first().click()
  await expect(page.getByRole('textbox', { name: 'Task ID', exact: true })).toHaveValue('manual-task')
  await page.getByRole('textbox', { name: 'Prompt', exact: true }).fill('Edited synthetic reference question.')
  await page.getByRole('button', { name: 'Add task', exact: true }).click()
  await expect(page.getByText('Edited synthetic reference question.', { exact: true })).toBeVisible()

  await page.getByRole('combobox', { name: 'Type', exact: true }).selectOption('spatial')
  await page.getByRole('textbox', { name: 'Task ID', exact: true }).fill('spatial-task')
  await page.getByRole('textbox', { name: 'Prompt', exact: true }).fill('Select the synthetic region.')
  for (const [name, value] of [['targetX', '0.25'], ['targetY', '0.25'], ['targetWidth', '0.2'], ['targetHeight', '0.2']]) {
    await page.getByRole('spinbutton', { name, exact: true }).fill(value)
  }
  await page.getByRole('textbox', { name: 'Hints, one per line (maximum 3)', exact: true }).fill('Inspect the field.')
  await page.getByRole('textbox', { name: 'Faculty explanation', exact: true }).fill('The fixture target is normalized to slide coordinates.')
  await page.getByRole('textbox', { name: 'Source title', exact: true }).fill('Synthetic spatial source')
  await page.getByRole('textbox', { name: 'HTTPS source URL', exact: true }).fill('https://example.edu/pathlab-spatial-qa')
  await page.getByRole('button', { name: 'Add task', exact: true }).click()
  await expect(page.getByText('Select the synthetic region.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start mandatory preview (3)', exact: true })).toBeEnabled()

  const completeExportPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export draft', exact: true }).click()
  const completeExport = await completeExportPromise
  const completeJson = await readFile((await completeExport.path())!)
  const exportedDraft = JSON.parse(completeJson.toString('utf8')) as { tasks: Array<{ id: string; tolerance?: number }> }
  expect(exportedDraft.tasks.find((task) => task.id === 'spatial-task')?.tolerance).toBe(0.06)
  await page.getByRole('button', { name: 'Delete draft', exact: true }).click()
  await expect(page.getByText('Local authoring draft deleted.', { exact: true })).toBeVisible()
  const jsonInput = page.locator('input[type="file"]').nth(1)
  await jsonInput.setInputFiles({ name: completeExport.suggestedFilename(), mimeType: 'application/json', buffer: completeJson })
  await expect(page.getByRole('button', { name: 'Start mandatory preview (3)', exact: true })).toBeEnabled()

  const validation = page.waitForResponse((response) => response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/admin/study/packs/validate')
  await page.getByRole('button', { name: 'Start mandatory preview (3)', exact: true }).click()
  const validationResponse = await validation
  await testInfo.attach('study-pack-validation.json', {
    body: JSON.stringify({ status: validationResponse.status(), response: await validationResponse.json(), request: validationResponse.request().postDataJSON() }, null, 2),
    contentType: 'application/json',
  })
  await expect(page.getByRole('heading', { name: 'Task 1 of 3', exact: true })).toBeVisible()
  const authorViewport = page.viewportSize()!
  const responsiveGeometry: Array<{ width: number; viewport: number; client: number; scroll: number }> = []
  for (const width of [320, 360, 390, 600, 601, 768, 900, 901, 1250, 1251, 1440, 1920]) {
    await page.setViewportSize({ width, height: 844 })
    const geometry = await page.evaluate(() => ({ viewport: window.innerWidth, client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }))
    responsiveGeometry.push({ width, ...geometry })
    expect(geometry.scroll, `Study Pack author preview overflow at ${width}px: ${JSON.stringify(geometry)}`).toBeLessThanOrEqual(geometry.client + 1)
    await expect(page.getByRole('button', { name: 'Next', exact: true })).toBeVisible()
  }
  await testInfo.attach('study-author-responsive-geometry.json', { body: JSON.stringify(responsiveGeometry, null, 2), contentType: 'application/json' })
  await page.setViewportSize(authorViewport)
  await expect(page.getByRole('button', { name: 'Previous', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Task 2 of 3', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Task 3 of 3', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Next', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Previous', exact: true }).click()
  await page.getByRole('button', { name: 'Previous', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Task 1 of 3', exact: true })).toBeVisible()
  await expect(page.getByText('All bounded local-AI cards', { exact: true })).toBeVisible()
  await page.getByRole('checkbox', { name: /I reviewed every task/ }).check()
  await page.getByRole('button', { name: 'Attest and publish immutable version', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Study Coach', exact: true })).toBeVisible()
  const packSelector = page.getByRole('combobox', { name: 'Study Pack', exact: true })
  await expect(packSelector.getByRole('option', { name: `${packTitle} · v1`, exact: true })).toHaveCount(1)
  await page.reload()
  await expect(packSelector.getByRole('option', { name: `${packTitle} · v1`, exact: true })).toHaveCount(1)
})
