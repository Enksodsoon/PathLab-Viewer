import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'

test('all six authorable question types survive publication, learner save and submission', async ({ page, browser }, testInfo) => {
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  await page.getByRole('button', { name: 'Teaching Studio', exact: true }).click()
  await page.getByRole('button', { name: 'New assessment', exact: true }).click()
  await page.getByRole('button', { name: 'Create assessment', exact: true }).click()
  await page.getByRole('button', { name: 'Upgrade to sections', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Question type for section 1', exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: 'Assessment name', exact: true }).fill('QA all question types')
  const types = ['multiple choice', 'checkboxes', 'rating', 'text response', 'diagnostic field', 'description']
  for (const type of types) {
    const labels: Record<string, string> = { 'multiple choice': 'Multiple choice', checkboxes: 'Checkboxes', rating: 'Rating', 'text response': 'Text response', 'diagnostic field': 'Diagnostic field', description: 'Description' }
    await page.getByRole('combobox', { name: 'Question type for section 1', exact: true }).selectOption({ label: labels[type] })
    await page.getByRole('button', { name: 'Add selected question to section 1', exact: true }).click()
    await page.getByRole('textbox', { name: type === 'description' ? 'Description' : 'Question', exact: true }).last().fill(`QA ${type} prompt`)
    if (['multiple choice', 'checkboxes'].includes(type)) {
      await page.getByRole('textbox', { name: 'Option 1', exact: true }).last().fill('Synthetic A')
      await page.getByRole('textbox', { name: 'Option 2', exact: true }).last().fill('Synthetic B')
      await page.getByLabel('Correct option 1', { exact: true }).last().check()
    }
    await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  }
  await page.reload()
  await expect(page.getByRole('textbox', { name: 'Assessment name', exact: true })).toHaveValue('QA all question types')
  const originalViewport = page.viewportSize()!
  for (const width of [320, 360, 390, 600, 601, 768, 900, 901, 1250, 1251, 1440, 1920]) {
    await page.setViewportSize({ width, height: width === 600 ? 360 : 900 })
    await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), `Assessment overflow at ${width}px`).toBe(true)
    if ([320, 390, 768, 1440].includes(width)) await page.screenshot({ path: testInfo.outputPath(`assessment-${width}.png`) })
  }
  await page.setViewportSize(originalViewport)
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  const publish = page.getByRole('dialog', { name: 'Publish assessment', exact: true })
  await publish.getByRole('combobox', { name: 'Mode', exact: true }).selectOption('formative')
  const publication = page.waitForResponse((response) => response.request().method() === 'POST' && response.url().includes('/publish'))
  await publish.getByRole('button', { name: 'Publish assignment', exact: true }).click()
  const published = await publication
  expect(published.ok(), await published.text()).toBe(true)
  await publish.getByRole('button', { name: 'Open responses', exact: true }).click()
  await expect(publish.getByText('Accepting responses. You can share this link.', { exact: true })).toBeVisible()
  const href = await publish.locator('a[href*="/assessment/"]').last().getAttribute('href')
  const context = await browser.newContext()
  try {
    const student = await context.newPage()
    await student.goto(href!)
    await student.getByRole('button', { name: 'Continue anonymously', exact: true }).click()
    for (const type of types) {
      await expect(student.getByText(`QA ${type} prompt`, { exact: true })).toBeVisible()
      if (type === 'multiple choice') await student.getByRole('radio', { name: 'Synthetic A', exact: true }).check()
      if (type === 'checkboxes') await student.getByRole('checkbox', { name: 'Synthetic A', exact: true }).check()
      if (type === 'rating') await student.getByRole('radio', { name: 'Rating 5', exact: true }).check()
      if (type === 'text response') await student.getByRole('textbox', { name: 'Answer', exact: true }).fill('Synthetic free text')
      if (type === 'diagnostic field') {
        const answerTab = student.getByRole('button', { name: 'Answer', exact: true })
        if (await answerTab.isVisible()) await answerTab.click()
        await student.getByRole('textbox', { name: 'Diagnosis', exact: true }).fill('Synthetic diagnosis')
      }
      if (type !== 'description') {
        await expect(student.getByText(/ · Saved$/)).toBeVisible()
        await student.getByRole('button', { name: 'Mark for review', exact: true }).click()
        await expect(student.getByRole('button', { name: 'Marked for review', exact: true })).toHaveAttribute('aria-pressed', 'true')
        await student.getByRole('button', { name: 'Save & next', exact: true }).click()
      }
    }
    await student.getByRole('button', { name: 'Submit assessment', exact: true }).click()
    await student.getByRole('button', { name: 'Submit assessment', exact: true }).click()
    await expect(student.getByRole('heading', { name: 'Assessment submitted', exact: true })).toBeVisible()
    await student.reload()
    await expect(student.getByRole('heading', { name: 'Assessment submitted', exact: true })).toBeVisible()
  } finally { await context.close() }
  await publish.getByRole('button', { name: 'Close publish settings', exact: true }).click()
  await page.getByRole('tab', { name: 'Responses', exact: true }).click()
  await expect(page.getByText('1 of 1 learners completed', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('1 of 1 learners completed', { exact: true })).toBeVisible()
  await page.getByRole('switch', { name: 'Accepting responses', exact: true }).click()
  await expect(page.getByRole('switch', { name: 'Accepting responses', exact: true })).toHaveAttribute('aria-checked', 'false')
})
