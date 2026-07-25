import { expect, test, type Page } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'

const action = required('CAPACITY_FIXTURE_ACTION')
const resultPath = required('CAPACITY_FIXTURE_RESULT')
const diagnosticPath = required('CAPACITY_FIXTURE_DIAGNOSTIC')
const username = required('LOAD_TEST_ADMIN_USERNAME')
const password = required('LOAD_TEST_ADMIN_PASSWORD')

interface FixtureRecord {
  publicId?: string
  slideId: string
}

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`${name} is required`)
  return value
}

function readRecord(): FixtureRecord {
  return JSON.parse(readFileSync(resultPath, 'utf8')) as FixtureRecord
}

function writeRecord(record: FixtureRecord) {
  writeFileSync(resultPath, `${JSON.stringify(record)}\n`)
}

function writeDiagnostic(stage: string) {
  writeFileSync(diagnosticPath, `${JSON.stringify({ stage })}\n`)
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

async function csrfJson(
  page: Page,
  path: string,
  method: 'DELETE' | 'POST',
): Promise<{ body: unknown; ok: boolean; status: number }> {
  return page.evaluate(async ({ requestPath, requestMethod }) => {
    const response = await fetch(requestPath, {
      method: requestMethod,
      credentials: 'same-origin',
      headers: {
        'X-CSRF-Token': sessionStorage.getItem('pathlab-csrf') ?? '',
      },
    })
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      // DELETE may legitimately return no JSON body.
    }
    return { body, ok: response.ok, status: response.status }
  }, { requestPath: path, requestMethod: method })
}

test('prepare a synthetic public capacity fixture', async ({ page }) => {
  test.skip(action !== 'prepare', 'Fixture preparation was not requested')
  const syntheticPath = required('CAPACITY_FIXTURE_OME')
  let slideId: string | null = null
  let stage = 'admin-sign-in'
  try {
    writeDiagnostic(stage)
    await signIn(page)
    stage = 'upload-reservation'
    writeDiagnostic(stage)
    await page.getByRole('button', { name: 'Upload', exact: true }).click()
    await page.getByLabel('Choose OME-TIFF').setInputFiles(syntheticPath)
    await page.getByLabel('Display name').fill('Synthetic public capacity fixture')
    const reservation = page.waitForResponse((response) => (
      response.request().method() === 'POST'
      && new URL(response.url()).pathname === '/api/v1/admin/slides'
    ))
    await page.getByRole('button', { name: 'Upload slide' }).click()
    const reservationResponse = await reservation
    if (!reservationResponse.ok()) throw new Error('Synthetic fixture reservation failed')
    const reservationBody = await reservationResponse.json() as {
      slide?: { id?: unknown }
    }
    if (typeof reservationBody.slide?.id !== 'string') {
      throw new Error('Synthetic fixture reservation was incomplete')
    }
    slideId = reservationBody.slide.id
    writeRecord({ slideId })

    stage = 'upload-and-conversion'
    writeDiagnostic(stage)
    await expect(page.getByText('Upload complete. Processing is queued.', {
      exact: true,
    })).toBeVisible({ timeout: 15 * 60_000 })
    await expect.poll(async () => page.evaluate(async (approvedSlideId) => {
      const response = await fetch(
        `/api/v1/admin/slides/${encodeURIComponent(approvedSlideId)}`,
        { credentials: 'same-origin' },
      )
      if (!response.ok) return 'unavailable'
      const body = await response.json() as { state?: unknown }
      return typeof body.state === 'string' ? body.state : 'unknown'
    }, slideId), {
      timeout: 10 * 60_000,
      intervals: [5_000],
      message: 'Synthetic fixture conversion did not reach ready_private',
    }).toBe('ready_private')

    stage = 'publication'
    writeDiagnostic(stage)
    const publication = await csrfJson(
      page,
      `/api/v1/admin/slides/${encodeURIComponent(slideId)}/publish`,
      'POST',
    )
    if (!publication.ok) throw new Error('Synthetic fixture publication failed')
    const published = publication.body as { publicId?: unknown }
    if (typeof published.publicId !== 'string') {
      throw new Error('Synthetic fixture publication response was incomplete')
    }

    const publicResult = await page.evaluate(async (publicId) => {
      const metadataResponse = await fetch(
        `/api/v1/public/slides/${encodeURIComponent(publicId)}`,
      )
      if (!metadataResponse.ok) return { ok: false }
      const metadata = await metadataResponse.json() as {
        thumbnailUrl?: unknown
        tileSource?: unknown
      }
      if (
        typeof metadata.thumbnailUrl !== 'string'
        || typeof metadata.tileSource !== 'string'
      ) {
        return { ok: false }
      }
      const [poster, descriptor] = await Promise.all([
        fetch(metadata.thumbnailUrl),
        fetch(metadata.tileSource),
      ])
      return { ok: poster.ok && descriptor.ok }
    }, published.publicId)
    if (!publicResult.ok) {
      throw new Error('Synthetic public poster or DZI was unavailable')
    }
    writeRecord({ slideId, publicId: published.publicId })
  } catch (error) {
    writeDiagnostic(stage)
    if (slideId !== null) {
      await csrfJson(
        page,
        `/api/v1/admin/slides/${encodeURIComponent(slideId)}`,
        'DELETE',
      ).catch(() => null)
    }
    throw error
  }
})

test('remove the synthetic public capacity fixture', async ({ page }) => {
  test.skip(action !== 'cleanup', 'Fixture cleanup was not requested')
  const { slideId } = readRecord()
  let stage = 'cleanup-admin-sign-in'
  try {
    writeDiagnostic(stage)
    await signIn(page)
    stage = 'fixture-deletion'
    writeDiagnostic(stage)
    const deletion = await csrfJson(
      page,
      `/api/v1/admin/slides/${encodeURIComponent(slideId)}`,
      'DELETE',
    )
    if (!deletion.ok && deletion.status !== 404) {
      throw new Error('Synthetic fixture deletion was rejected')
    }
    await expect.poll(async () => page.evaluate(async (approvedSlideId) => {
      const response = await fetch(
        `/api/v1/admin/slides/${encodeURIComponent(approvedSlideId)}`,
        { credentials: 'same-origin' },
      )
      return response.status
    }, slideId), {
      timeout: 5 * 60_000,
      intervals: [5_000],
      message: 'Synthetic fixture was not removed',
    }).toBe(404)
  } catch (error) {
    writeDiagnostic(stage)
    throw error
  }
})
