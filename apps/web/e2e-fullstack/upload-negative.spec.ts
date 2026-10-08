import { expect, test } from './qa-test'
import path from 'node:path'
import { signIn, waitForSlideConversion } from '../e2e-live/capacity-helpers'
import { fault } from './fixture-faults'

test.beforeEach(async ({ page }) => {
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
})

test('invalid and duplicate files are rejected; queued removal and quota retry recover', async ({ page }) => {
  await page.getByRole('button', { name: 'Upload', exact: true }).first().click()
  const dialog = page.getByRole('dialog', { name: 'Upload OME-TIFF', exact: true })
  const files = dialog.getByLabel('Choose OME-TIFF files', { exact: true })
  await files.setInputFiles({ name: 'unsupported.txt', mimeType: 'text/plain', buffer: Buffer.from('synthetic') })
  await expect(page.getByText(/unsupported.*skipped/)).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Upload 1 file', exact: true })).not.toBeVisible()
  const source = process.env.PATHLAB_E2E_OME!
  await files.setInputFiles([source, source])
  await expect(dialog.locator('.upload-workspace-file')).toHaveCount(1)
  await dialog.getByRole('button', { name: `Remove ${path.basename(source)}`, exact: true }).click()
  await expect(dialog.locator('.upload-workspace-file')).toHaveCount(0)
  await files.setInputFiles(source)
  await dialog.getByLabel('Display name', { exact: true }).fill('QA quota recovery')
  fault('quota-full')
  try {
    const rejected = page.waitForResponse((response) => response.request().method() === 'POST'
      && new URL(response.url()).pathname === '/api/v1/admin/slides')
    await dialog.getByRole('button', { name: 'Upload 1 file', exact: true }).click()
    expect((await rejected).status()).toBe(507)
    await expect(dialog.getByText(/Not enough usable storage/)).toBeVisible()
  } finally { fault('quota-clear') }
  const reservation = page.waitForResponse((response) => response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/admin/slides')
  await dialog.getByRole('button', { name: `Retry ${path.basename(source)}`, exact: true }).click()
  const response = await reservation
  expect(response.ok()).toBe(true)
  const id = (await response.json()).slide.id
  await waitForSlideConversion(page, id)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'QA quota recovery', exact: true })).toBeVisible()
})

test('corrupt OME content ends in a durable failed state instead of a usable slide', async ({ page }) => {
  await page.getByRole('button', { name: 'Upload', exact: true }).first().click()
  const dialog = page.getByRole('dialog', { name: 'Upload OME-TIFF', exact: true })
  await dialog.getByLabel('Choose OME-TIFF files', { exact: true }).setInputFiles({
    name: 'qa-corrupt.ome.tif', mimeType: 'image/tiff', buffer: Buffer.from('Synthetic invalid TIFF'),
  })
  await dialog.getByLabel('Display name', { exact: true }).fill('QA corrupt conversion')
  const reserved = page.waitForResponse((response) => response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/admin/slides')
  await dialog.getByRole('button', { name: 'Upload 1 file', exact: true }).click()
  const id = (await (await reserved).json()).slide.id
  await expect.poll(async () => (await (await page.request.get(`/api/v1/admin/slides/${id}`)).json()).state,
    { timeout: 30_000 }).toBe('failed')
  await page.goto('/admin?location=failed')
  await expect(page.getByRole('heading', { name: 'QA corrupt conversion', exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: 'More actions for QA corrupt conversion', exact: true }).click()
  await expect(page.getByRole('menuitem', { name: 'Preview', exact: true })).not.toBeVisible()
  await page.getByRole('menuitem', { name: 'Retry conversion', exact: true }).click()
  await expect.poll(async () => (await (await page.request.get(`/api/v1/admin/slides/${id}`)).json()).state,
    { timeout: 30_000 }).toBe('failed')
})
