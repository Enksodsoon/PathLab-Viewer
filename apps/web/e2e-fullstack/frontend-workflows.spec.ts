import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'

test.beforeEach(async ({ page }) => {
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
})

test('creation commands persist folders, collections and saved searches', async ({ page }) => {
  for (const kind of ['folder', 'collection', 'saved view']) {
    await test.step(`create and reload ${kind}`, async () => {
      await page.getByRole('button', { name: 'Create', exact: true }).click()
      await page.getByRole('menuitem', { name: `New ${kind}`, exact: true }).click()
      const dialog = page.getByRole('dialog', { name: `New ${kind}`, exact: true })
      const name = `QA persistent ${kind}`
      await dialog.getByLabel('Name', { exact: true }).fill(name)
      if (kind !== 'saved view') await dialog.getByLabel('Description', { exact: true }).fill('Synthetic QA only')
      await dialog.getByRole('button', { name: 'Create', exact: true }).click()
      await expect(dialog).not.toBeVisible()
      await page.reload()
      await page.getByRole('button', { name: 'Slide library', exact: true }).click()
      await expect(page.locator('#library-navigator').getByText(name, { exact: true }).first()).toBeVisible()
      await page.keyboard.press('Escape')
    })
  }
})

test('rapid resubmission creates only one folder', async ({ page }) => {
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await page.getByRole('menuitem', { name: 'New folder', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'New folder', exact: true })
  await dialog.getByLabel('Name', { exact: true }).fill('QA single submission')
  let release!: () => void
  const gate = new Promise<void>((resolve) => { release = resolve })
  let posts = 0
  await page.route('**/api/v2/admin/folders', async (route) => {
    if (route.request().method() === 'POST') { posts++; await gate }
    await route.continue()
  })
  try {
    await dialog.getByRole('button', { name: 'Create', exact: true }).click()
    await expect.poll(() => posts).toBe(1)
    await expect(dialog.getByRole('button', { name: 'Create', exact: true })).toBeDisabled()
    await dialog.getByLabel('Name', { exact: true }).press('Enter')
    // Hold the real response while testing a second user submission.
    await page.waitForTimeout(250)
    expect(posts).toBe(1)
  } finally { release() }
  await expect(dialog).not.toBeVisible()
  await page.reload()
  const navigation = await page.request.get('/api/v2/admin/library/navigation')
  const data = await navigation.json()
  expect(data.folders.filter((folder: { name: string }) => folder.name === 'QA single submission')).toHaveLength(1)
})

test('themes, layouts and search survive reload on real backend', async ({ page }) => {
  for (const mode of ['Light', 'Dark', 'System']) {
    await page.getByRole('radio', { name: mode, exact: true }).check()
    await page.reload()
    await expect(page.getByRole('radio', { name: mode, exact: true })).toBeChecked()
  }
  for (const view of ['List', 'Table', 'Grid']) {
    const compact = page.getByRole('combobox', { name: 'View slides', exact: true })
    const mobile = await compact.isVisible()
    if (mobile) await compact.selectOption(view.toLowerCase())
    else await page.getByRole('button', { name: `${view} view`, exact: true }).click()
    await page.reload()
    if (mobile) await expect(compact).toHaveValue(view.toLowerCase())
    else await expect(page.getByRole('button', { name: `${view} view`, exact: true })).toHaveAttribute('aria-pressed', 'true')
  }
  const search = page.getByRole('searchbox', { name: 'Search slides', exact: true })
  await search.fill('QA-no-matching-slide-☃')
  await expect(page).toHaveURL(/q=QA-no-matching-slide/)
  await expect(page.getByRole('heading', { name: 'No slides here' })).toBeVisible()
  await page.reload()
  await expect(search).toHaveValue('QA-no-matching-slide-☃')
  await search.fill('')
  for (const value of ['updated_asc', 'created_desc', 'created_asc', 'name_asc', 'name_desc', 'updated_desc']) {
    await page.getByRole('combobox', { name: 'Sort slides', exact: true }).selectOption(value)
    await expect(page.getByRole('combobox', { name: 'Sort slides', exact: true })).toHaveValue(value)
  }
})

test('failed creation keeps the form usable and retry persists exactly once', async ({ page }) => {
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await page.getByRole('menuitem', { name: 'New folder', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'New folder', exact: true })
  const name = 'QA recovered creation'
  await dialog.getByLabel('Name', { exact: true }).fill(name)
  let injected = false
  await page.route('**/api/v2/admin/folders', async (route) => {
    if (route.request().method() === 'POST' && !injected) {
      injected = true
      await route.fulfill({ status: 503, json: { detail: 'Synthetic isolated failure' } })
    } else await route.continue()
  })
  const create = dialog.getByRole('button', { name: 'Create', exact: true })
  await create.click()
  await expect(page.getByRole('alert')).toContainText('failed. Try again.')
  await expect(create).toBeEnabled()
  await expect(dialog.getByLabel('Name', { exact: true })).toHaveValue(name)
  await create.click()
  await expect(dialog).not.toBeVisible()
  await page.reload()
  const data = await (await page.request.get('/api/v2/admin/library/navigation')).json()
  expect(data.folders.filter((folder: { name: string }) => folder.name === name)).toHaveLength(1)
})
