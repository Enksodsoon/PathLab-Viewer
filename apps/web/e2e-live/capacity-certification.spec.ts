import { expect, test, type Page } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'

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

async function signIn(page: Page) {
  await page.goto('/admin')
  const heading = page.getByRole('heading', { name: 'Administrator sign in' })
  await expect(heading).toBeVisible({ timeout: 30_000 })
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(password)
  const authentication = page.waitForResponse((response) => (
    response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/auth/session'
  ))
  await page.getByRole('button', { name: 'Enter workspace' }).click()
  const authenticationResponse = await authentication
  if (!authenticationResponse.ok()) {
    throw new Error(`Administrator sign-in failed with status ${authenticationResponse.status()}`)
  }
  await expect(page.getByRole('heading', { name: 'All slides' })).toBeVisible({
    timeout: 30_000,
  })
}

async function csrfFetch(
  page: Page,
  path: string,
  init: { method: string; body?: unknown },
): Promise<{ ok: boolean; status: number }> {
  return page.evaluate(async ({ path: requestPath, init: requestInit }) => {
    const token = sessionStorage.getItem('pathlab-csrf') ?? ''
    const response = await fetch(requestPath, {
      method: requestInit.method,
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': token,
      },
      ...(requestInit.body === undefined
        ? {}
        : { body: JSON.stringify(requestInit.body) }),
    })
    return { ok: response.ok, status: response.status }
  }, { path, init })
}

test.beforeAll(() => updateResult({}))

test('admin remains responsive and conversion cleanup succeeds', async ({ page }) => {
  let originalNote: string | null = null
  let syntheticSlideId: string | null = null
  let noteChanged = false
  let conversionSucceeded = false
  let cleanupSucceeded = false
  try {
    await signIn(page)
    const target = await page.evaluate(async (slideId) => {
      const response = await fetch(`/api/v1/admin/slides/${encodeURIComponent(slideId)}`, {
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

    await page.getByRole('button', { name: 'Upload', exact: true }).click()
    await page.getByLabel('Choose OME-TIFF').setInputFiles(syntheticPath)
    await page.getByLabel('Display name').fill(`Synthetic certification ${runMarker}`)
    const reservation = page.waitForResponse((response) => (
      response.request().method() === 'POST'
      && new URL(response.url()).pathname === '/api/v1/admin/slides'
    ))
    await page.getByRole('button', { name: 'Upload slide' }).click()
    const reservationResponse = await reservation
    if (!reservationResponse.ok()) throw new Error('Synthetic upload reservation failed')
    const reservationBody = await reservationResponse.json() as {
      slide?: { id?: unknown }
    }
    if (typeof reservationBody.slide?.id !== 'string') {
      throw new Error('Synthetic upload reservation was incomplete')
    }
    syntheticSlideId = reservationBody.slide.id
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
      const response = await csrfFetch(page, '/api/v2/admin/slides/batch-metadata', {
        method: 'POST',
        body: { slideIds: [adminSlideId], adminNotes: originalNote },
      }).catch(() => ({ ok: false, status: 0 }))
      noteRestored = response.ok
    }
    if (syntheticSlideId !== null) {
      const response = await csrfFetch(
        page,
        `/api/v1/admin/slides/${encodeURIComponent(syntheticSlideId)}`,
        { method: 'DELETE' },
      ).catch(() => ({ ok: false, status: 0 }))
      syntheticDeleted = response.ok || response.status === 404
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
