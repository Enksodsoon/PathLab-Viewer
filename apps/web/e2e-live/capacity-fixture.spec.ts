import { expect, test } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'

import {
  CapacityHttpError,
  csrfJson,
  signIn,
  uploadSyntheticSlide,
  waitForSlideDeletion,
} from './capacity-helpers'

const action = required('CAPACITY_FIXTURE_ACTION')
const resultPath = required('CAPACITY_FIXTURE_RESULT')
const prepareDiagnosticPath = required('CAPACITY_FIXTURE_PREPARE_DIAGNOSTIC')
const cleanupDiagnosticPath = required('CAPACITY_FIXTURE_CLEANUP_DIAGNOSTIC')
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

function writeDiagnostic(path: string, stage: string, error?: unknown) {
  if (!/^[a-z0-9-]+$/.test(stage)) throw new Error('Invalid diagnostic stage')
  const diagnostic: {
    errorCode?: string
    httpStatus?: number
    stage: string
  } = { stage }
  if (error instanceof CapacityHttpError) {
    if (error.httpStatus >= 100 && error.httpStatus <= 599) {
      diagnostic.httpStatus = error.httpStatus
    }
    if (error.errorCode && /^[A-Z0-9_]{1,64}$/.test(error.errorCode)) {
      diagnostic.errorCode = error.errorCode
    }
  }
  writeFileSync(path, `${JSON.stringify(diagnostic)}\n`)
}

test('prepare a synthetic public capacity fixture', async ({ page }) => {
  test.skip(action !== 'prepare', 'Fixture preparation was not requested')
  const syntheticPath = required('CAPACITY_FIXTURE_OME')
  let slideId: string | null = null
  let stage = 'admin-sign-in'
  try {
    writeDiagnostic(prepareDiagnosticPath, stage)
    await signIn(page, username, password)
    stage = 'upload-reservation'
    writeDiagnostic(prepareDiagnosticPath, stage)
    slideId = await uploadSyntheticSlide(
      page,
      syntheticPath,
      'Synthetic public capacity fixture',
    )
    writeRecord({ slideId })

    stage = 'upload-and-conversion'
    writeDiagnostic(prepareDiagnosticPath, stage)
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
    writeDiagnostic(prepareDiagnosticPath, stage)
    const publication = await csrfJson(
      page,
      `/api/v1/admin/slides/${encodeURIComponent(slideId)}/publish`,
      { method: 'POST', body: { deidentifiedConfirmed: true } },
    )
    if (!publication.ok) {
      throw new CapacityHttpError(
        'Synthetic fixture publication failed',
        publication.status,
        publication.errorCode,
      )
    }
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
    writeDiagnostic(prepareDiagnosticPath, stage, error)
    if (slideId !== null) {
      try {
        writeDiagnostic(cleanupDiagnosticPath, 'prepare-rollback-deletion')
        const deletion = await csrfJson(
          page,
          `/api/v1/admin/slides/${encodeURIComponent(slideId)}`,
          { method: 'DELETE' },
        )
        if (!deletion.ok && deletion.status !== 404) {
          throw new CapacityHttpError(
            'Synthetic fixture rollback deletion was rejected',
            deletion.status,
            deletion.errorCode,
          )
        }
        await waitForSlideDeletion(page, slideId)
      } catch (cleanupError) {
        writeDiagnostic(
          cleanupDiagnosticPath,
          'prepare-rollback-deletion',
          cleanupError,
        )
      }
    }
    throw error
  }
})

test('remove the synthetic public capacity fixture', async ({ page }) => {
  test.skip(action !== 'cleanup', 'Fixture cleanup was not requested')
  const { slideId } = readRecord()
  let stage = 'cleanup-admin-sign-in'
  try {
    writeDiagnostic(cleanupDiagnosticPath, stage)
    await signIn(page, username, password)
    stage = 'fixture-deletion'
    writeDiagnostic(cleanupDiagnosticPath, stage)
    const deletion = await csrfJson(
      page,
      `/api/v1/admin/slides/${encodeURIComponent(slideId)}`,
      { method: 'DELETE' },
    )
    if (!deletion.ok && deletion.status !== 404) {
      throw new CapacityHttpError(
        'Synthetic fixture deletion was rejected',
        deletion.status,
        deletion.errorCode,
      )
    }
    await waitForSlideDeletion(page, slideId)
  } catch (error) {
    writeDiagnostic(cleanupDiagnosticPath, stage, error)
    throw error
  }
})
