import { expect, test } from './qa-test'

import { signIn, uploadSyntheticSlide, waitForSlideConversion } from '../e2e-live/capacity-helpers'
import { exerciseClassroom } from './classroom-journey'

test('interrupted upload, conversion, annotations, sign-in return, publication and revocation', async ({ page, browser }, testInfo) => {
  const username = process.env.PATHLAB_E2E_USERNAME
  const password = process.env.PATHLAB_E2E_PASSWORD
  const source = process.env.PATHLAB_E2E_OME
  if (!username || !password || !source) throw new Error('Run through the isolated stack launcher')
  const name = 'Synthetic full-stack journey'
  await signIn(page, username, password)
  let interrupted = false
  let resumedOffset = 0
  await page.route('**/api/v1/uploads/**', async (route) => {
    const request = route.request()
    const offset = Number(request.headers()['upload-offset'] ?? 0)
    if (request.method() === 'PATCH' && offset > 0 && !interrupted) {
      interrupted = true
      await route.abort('connectionreset')
      return
    }
    if (request.method() === 'PATCH' && interrupted) resumedOffset = Math.max(resumedOffset, offset)
    await route.continue()
  })
  const slideId = await uploadSyntheticSlide(page, source, name)
  await waitForSlideConversion(page, slideId)
  expect(interrupted).toBe(true)
  expect(resumedOffset).toBeGreaterThan(0)
  await page.reload()
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()

  const slideActions = page.getByRole('button', { name: `More actions for ${name}`, exact: true })
  await slideActions.click()
  const privateMenuItems = (await page.getByRole('menu').getByRole('menuitem').allTextContents())
    .map((item) => item.trim().replace(/\s+/g, ' ')).sort()
  expect(privateMenuItems).toEqual([
    'Add to collection', 'Details', 'Edit details', 'Move', 'Move to Trash', 'Preview', 'Publish',
  ])
  await page.keyboard.press('Escape')
  await expect(page.getByRole('menu')).toBeHidden()
  await expect(slideActions).toBeFocused()
  await slideActions.click()
  await page.getByRole('menuitem', { name: 'Preview', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/admin/preview/${slideId}$`))
  await expect(page.locator('.openseadragon-canvas canvas').first()).toBeVisible()
  await page.getByRole('button', { name: 'More annotation tools' }).click()
  await page.getByRole('button', { name: 'Point marker', exact: true }).click()
  const saved = page.waitForResponse((response) => (
    response.request().method() === 'POST'
    && response.url().includes(`/api/v2/admin/annotations/slides/${slideId}/batch`)
  ))
  await page.locator('.annotation-svg-overlay').click({ position: { x: 360, y: 300 } })
  expect((await saved).ok()).toBe(true)
  await page.reload()
  await page.getByRole('button', { name: 'Open annotations' }).click()
  await expect(page.getByRole('button', { name: /point annotation/i })).toBeVisible()
  await page.goBack()

  const returning = await browser.newContext({ baseURL: process.env.PATHLAB_E2E_BASE_URL })
  try {
    const privateViewer = await returning.newPage()
    await privateViewer.goto(`/admin/preview/${slideId}`)
    await privateViewer.getByRole('link', { name: 'Sign in again' }).click()
    await privateViewer.getByLabel('Username', { exact: true }).fill(username)
    await privateViewer.getByLabel('Password', { exact: true }).fill(password)
    await privateViewer.getByRole('button', { name: 'Enter workspace' }).click()
    await expect(privateViewer).toHaveURL(new RegExp(`/admin/preview/${slideId}$`))
    await privateViewer.getByRole('button', { name: 'Open annotations' }).click()
    await expect(privateViewer.getByRole('button', { name: /point annotation/i })).toBeVisible()
  } finally {
    await returning.close()
  }

  await page.getByRole('button', { name: `More actions for ${name}`, exact: true }).click()
  await page.getByRole('menuitem', { name: 'Publish', exact: true }).click()
  const confirmation = page.getByRole('dialog', { name: 'Confirm deidentification' })
  await confirmation.getByRole('checkbox').check()
  const publication = page.waitForResponse((response) => (
    response.request().method() === 'POST'
    && new URL(response.url()).pathname === `/api/v1/admin/slides/${slideId}/publish`
  ))
  await confirmation.getByRole('button', { name: 'Publish 1 slide', exact: true }).click()
  expect((await publication).ok()).toBe(true)
  await expect(confirmation).not.toBeVisible()
  await slideActions.click()
  const publishedMenuItems = (await page.getByRole('menu').getByRole('menuitem').allTextContents())
    .map((item) => item.trim().replace(/\s+/g, ' ')).sort()
  expect(publishedMenuItems).toEqual([
    'Add to collection', 'Copy public link', 'Details', 'Edit details', 'Move', 'Move to Trash',
    'Open public slide', 'Preview', 'Unpublish',
  ])
  const publicSlideLink = page.getByRole('menuitem', { name: 'Open public slide', exact: true })
  const publicPath = await publicSlideLink.getAttribute('href')
  expect(publicPath).toMatch(/^\/s\/[A-Za-z0-9_-]+$/)
  if (!publicPath) throw new Error('Published slide link missing')
  const publicId = publicPath.split('/').pop()!
  const [openedPublicSlide] = await Promise.all([
    page.context().waitForEvent('page'),
    publicSlideLink.click(),
  ])
  await expect(openedPublicSlide).toHaveURL(new RegExp(`${publicPath.replaceAll('/', '\\/')}$`))
  await expect(openedPublicSlide.locator('.openseadragon-canvas canvas').first()).toBeVisible()
  await openedPublicSlide.close()

  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await slideActions.click()
  await page.getByRole('menuitem', { name: 'Copy public link', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Public link copied.')
  expect(await page.evaluate(() => navigator.clipboard.readText()))
    .toBe(new URL(publicPath, page.url()).toString())
  await testInfo.attach('slide-menu-inventory.json', {
    body: JSON.stringify({ private: privateMenuItems, published: publishedMenuItems }, null, 2),
    contentType: 'application/json',
  })
  await exerciseClassroom(page, browser, name)

  const anonymous = await browser.newContext({ baseURL: process.env.PATHLAB_E2E_BASE_URL })
  try {
    const viewer = await anonymous.newPage()
    const tile = viewer.waitForResponse((response) => (
      /\/slide_files\/\d+\/\d+_\d+\.jpe?g$/.test(new URL(response.url()).pathname)
    ))
    await viewer.goto(publicPath)
    await expect(viewer.locator('.openseadragon-canvas canvas').first()).toBeVisible()
    const receivedTile = await tile
    expect(receivedTile.ok(), `${receivedTile.status()} ${receivedTile.url()}`).toBe(true)
    expect(await viewer.evaluate(async (url) => {
      const image = new Image()
      image.src = url
      await image.decode()
      return image.naturalWidth > 0 && image.naturalHeight > 0
    }, receivedTile.url())).toBe(true)
    expect((await anonymous.request.get(`/api/v1/admin/slides/${slideId}`)).status()).toBe(401)

    await page.getByRole('menuitem', { name: 'Unpublish', exact: true }).click()
    await expect.poll(async () => (
      await anonymous.request.get(`/api/v1/public/slides/${publicId}`)
    ).status()).toBe(404)
    expect((await anonymous.request.get(receivedTile.url())).status()).toBe(404)
    await viewer.reload()
    await expect(viewer.getByRole('heading', { name: 'This slide is unavailable' })).toBeVisible()
  } finally {
    await anonymous.close()
  }
})
