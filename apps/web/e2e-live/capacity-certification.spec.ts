import { expect, test } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'

import {
  csrfJson,
  signIn,
  uploadSyntheticSlide,
  waitForSlideDeletion,
} from './capacity-helpers'

const resultPath = required('CAPACITY_BROWSER_RESULT')
const publicId = required('LOAD_TEST_PUBLIC_ID')
const adminSlideId = required('LOAD_TEST_ADMIN_SLIDE_ID')
const username = required('LOAD_TEST_ADMIN_USERNAME')
const password = required('LOAD_TEST_ADMIN_PASSWORD')
const syntheticPath = required('CAPACITY_SYNTHETIC_OME')
const runMarker = `capacity-${required('GITHUB_RUN_ID')}`

interface BrowserResult {
  adminResponsive: boolean
  cleanupSucceeded: boolean
  conversionSucceeded: boolean
  degradedViewerRecovered: boolean
}

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`${name} is required`)
  return value
}

function updateResult(patch: Partial<BrowserResult>) {
  let current: BrowserResult = {
    adminResponsive: false,
    cleanupSucceeded: false,
    conversionSucceeded: false,
    degradedViewerRecovered: false,
  }
  try {
    current = JSON.parse(readFileSync(resultPath, 'utf8')) as BrowserResult
  } catch {
    // The first check creates the aggregate-only result.
  }
  writeFileSync(resultPath, `${JSON.stringify({ ...current, ...patch }, null, 2)}\n`)
}

test.beforeAll(() => updateResult({}))

test('admin remains responsive and conversion cleanup succeeds', async ({ page }) => {
  let originalNote: string | null = null
  let syntheticSlideId: string | null = null
  let noteChanged = false
  let conversionSucceeded = false
  let cleanupSucceeded = false
  try {
    await signIn(page, username, password)
    const target = await page.evaluate(async (slideId) => {
      const response = await fetch(`/api/v2/admin/slides/${encodeURIComponent(slideId)}`, {
        credentials: 'same-origin',
      })
      if (!response.ok) throw new Error('Approved admin slide was unavailable')
      const body = await response.json() as {
        displayName?: unknown
        adminNotes?: unknown
      }
      if (typeof body.displayName !== 'string' || typeof body.adminNotes !== 'string') {
        throw new Error('Approved admin slide response was incomplete')
      }
      return { displayName: body.displayName, adminNotes: body.adminNotes }
    }, adminSlideId)
    originalNote = target.adminNotes

    const search = page.getByRole('searchbox', { name: 'Search slides' })
    await search.fill(target.displayName)
    await expect(page.getByRole('heading', { name: target.displayName })).toBeVisible()
    await page.getByRole('button', { name: `More actions for ${target.displayName}` }).click()
    await page.getByRole('menuitem', { name: 'Edit details' }).click()
    const note = page.getByLabel('Administrator note')
    await note.fill(`${originalNote}\n${runMarker}`.trim())
    // Cleanup must restore the original even if the save response is interrupted.
    noteChanged = true
    await page.getByRole('button', { name: 'Save details' }).click()
    await expect(page.getByRole('heading', { name: 'Edit slide details' })).toBeHidden()
    updateResult({ adminResponsive: true })

    syntheticSlideId = await uploadSyntheticSlide(
      page,
      syntheticPath,
      `Synthetic certification ${runMarker}`,
    )
    await expect(page.getByText('Upload complete. Processing is queued.', {
      exact: true,
    })).toBeVisible({ timeout: 15 * 60_000 })

    await expect.poll(async () => page.evaluate(async (slideId) => {
      const response = await fetch(`/api/v1/admin/slides/${encodeURIComponent(slideId)}`, {
        credentials: 'same-origin',
      })
      if (!response.ok) return 'unavailable'
      const body = await response.json() as { state?: unknown }
      return typeof body.state === 'string' ? body.state : 'unknown'
    }, syntheticSlideId), {
      timeout: 10 * 60_000,
      intervals: [5_000],
      message: 'Synthetic conversion did not reach a terminal state',
    }).toBe('ready_private')
    conversionSucceeded = true
  } finally {
    let noteRestored = !noteChanged
    let syntheticDeleted = syntheticSlideId === null
    if (noteChanged && originalNote !== null) {
      const response = await csrfJson(page, '/api/v2/admin/slides/batch-metadata', {
        method: 'POST',
        body: { slideIds: [adminSlideId], adminNotes: originalNote },
      }).catch(() => ({ ok: false, status: 0 }))
      noteRestored = response.ok
    }
    if (syntheticSlideId !== null) {
      const response = await csrfJson(
        page,
        `/api/v1/admin/slides/${encodeURIComponent(syntheticSlideId)}`,
        { method: 'DELETE' },
      ).catch(() => ({ ok: false, status: 0 }))
      if (response.ok || response.status === 404) {
        syntheticDeleted = await waitForSlideDeletion(page, syntheticSlideId)
          .then(() => true)
          .catch(() => false)
      }
    }
    cleanupSucceeded = noteRestored && syntheticDeleted
    updateResult({ cleanupSucceeded, conversionSucceeded })
  }
  expect(conversionSucceeded).toBe(true)
  expect(cleanupSucceeded).toBe(true)
})

test('degraded viewer retains context and resumes after an outage', async ({ page, context }) => {
  const session = await context.newCDPSession(page)
  await session.send('Network.enable')
  await session.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: 1_000,
    downloadThroughput: 32_000,
    uploadThroughput: 32_000,
    packetLoss: 5,
  })
  await page.goto(`/s/${encodeURIComponent(publicId)}`, { waitUntil: 'domcontentloaded' })
  const surface = page.locator('.osd-surface')
  await expect(surface).toBeVisible({ timeout: 30_000 })
  await expect(surface.locator('canvas').first()).toBeVisible({ timeout: 60_000 })

  await session.send('Network.emulateNetworkConditions', {
    offline: true,
    latency: 1_000,
    downloadThroughput: 0,
    uploadThroughput: 0,
  })
  await page.evaluate(() => window.dispatchEvent(new Event('offline')))
  await expect(page.getByRole('status')).toContainText('Offline')
  await page.waitForTimeout(30_000)
  await expect(surface).toBeVisible()
  await expect(surface.locator('canvas').first()).toBeVisible()

  await session.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: 1_000,
    downloadThroughput: 32_000,
    uploadThroughput: 32_000,
    packetLoss: 5,
  })
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await expect(page.getByRole('status')).toContainText(/Connection restored|Reconnecting/)
  await expect(surface.locator('canvas').first()).toBeVisible()
  updateResult({ degradedViewerRecovered: true })
})
