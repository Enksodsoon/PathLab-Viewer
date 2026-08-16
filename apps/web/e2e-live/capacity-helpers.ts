import {
  expect,
  type Locator,
  type Page,
  type Response,
} from '@playwright/test'

interface JsonResponse {
  body: unknown
  errorCode?: string
  ok: boolean
  status: number
}

export type ConversionDecision =
  | { kind: 'failed'; errorCode: string }
  | { kind: 'pending' }
  | { kind: 'ready' }

export type PublicAvailabilityDecision =
  | { kind: 'failed'; errorCode: string; httpStatus: number }
  | { kind: 'ok' }

export class CapacityHttpError extends Error {
  readonly errorCode?: string
  readonly httpStatus: number

  constructor(message: string, httpStatus: number, errorCode?: string) {
    super(message)
    this.name = 'CapacityHttpError'
    this.httpStatus = httpStatus
    this.errorCode = errorCode
  }
}

function sanitizedErrorCode(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null) return undefined
  const record = body as Record<string, unknown>
  const detail = typeof record.detail === 'object' && record.detail !== null
    ? record.detail as Record<string, unknown>
    : undefined
  const candidate = detail?.code ?? record.code ?? record.errorCode
  return typeof candidate === 'string' && /^[A-Z0-9_]{1,64}$/.test(candidate)
    ? candidate
    : undefined
}

export function conversionDecision(
  body: unknown,
  timedOut: boolean,
): ConversionDecision {
  const state = typeof body === 'object' && body !== null
    ? (body as Record<string, unknown>).state
    : undefined
  if (state === 'ready_private') return { kind: 'ready' }
  if (state === 'failed') {
    return {
      kind: 'failed',
      errorCode: sanitizedErrorCode(body) ?? 'CONVERSION_FAILED',
    }
  }
  if (timedOut) {
    return { kind: 'failed', errorCode: 'CONVERSION_TIMEOUT' }
  }
  return { kind: 'pending' }
}

export function publicAvailabilityDecision(observation: {
  descriptorStatus?: number
  metadataBody: unknown
  metadataStatus: number
  posterStatus?: number
}): PublicAvailabilityDecision {
  if (
    observation.metadataStatus < 200
    || observation.metadataStatus >= 300
  ) {
    return {
      kind: 'failed',
      errorCode: sanitizedErrorCode(observation.metadataBody)
        ?? 'PUBLIC_METADATA_UNAVAILABLE',
      httpStatus: observation.metadataStatus,
    }
  }
  const metadata = typeof observation.metadataBody === 'object'
    && observation.metadataBody !== null
    ? observation.metadataBody as Record<string, unknown>
    : undefined
  if (
    typeof metadata?.thumbnailUrl !== 'string'
    || typeof metadata.tileSource !== 'string'
  ) {
    return {
      kind: 'failed',
      errorCode: 'PUBLIC_METADATA_INCOMPLETE',
      httpStatus: 0,
    }
  }
  if (
    observation.posterStatus === undefined
    || observation.posterStatus < 200
    || observation.posterStatus >= 300
  ) {
    return {
      kind: 'failed',
      errorCode: 'PUBLIC_POSTER_UNAVAILABLE',
      httpStatus: observation.posterStatus ?? 0,
    }
  }
  if (
    observation.descriptorStatus === undefined
    || observation.descriptorStatus < 200
    || observation.descriptorStatus >= 300
  ) {
    return {
      kind: 'failed',
      errorCode: 'PUBLIC_DESCRIPTOR_UNAVAILABLE',
      httpStatus: observation.descriptorStatus ?? 0,
    }
  }
  return { kind: 'ok' }
}

async function responseBody(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

export function capacityUploadDialog(page: Page): Locator {
  return page.getByRole('dialog', { name: 'Upload OME-TIFF' })
}

export async function signIn(
  page: Page,
  username: string,
  password: string,
): Promise<void> {
  await page.goto('/admin')
  const heading = page.getByRole('heading', { name: 'Administrator sign in' })
  await expect(heading).toBeVisible({ timeout: 30_000 })
  await page.getByLabel('Username', { exact: true }).fill(username)
  await page.getByLabel('Password', { exact: true }).fill(password)
  const authentication = page.waitForResponse((response) => (
    response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/auth/session'
  ))
  await page.getByRole('button', { name: 'Enter workspace' }).click()
  const authenticationResponse = await authentication
  if (!authenticationResponse.ok()) {
    const body = await responseBody(authenticationResponse)
    throw new CapacityHttpError(
      'Administrator sign-in failed',
      authenticationResponse.status(),
      sanitizedErrorCode(body),
    )
  }
  await expect(page.getByRole('heading', { name: 'All slides' })).toBeVisible({
    timeout: 30_000,
  })
}

export async function uploadSyntheticSlide(
  page: Page,
  syntheticPath: string,
  displayName: string,
): Promise<string> {
  await page.getByRole('button', { name: 'Upload', exact: true }).click()
  const dialog = capacityUploadDialog(page)
  await expect(dialog).toBeVisible()
  await dialog.getByLabel('Choose OME-TIFF', { exact: true }).setInputFiles(syntheticPath)
  await dialog.getByLabel('Display name', { exact: true }).fill(displayName)
  const reservation = page.waitForResponse((response) => (
    response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/admin/slides'
  ))
  await dialog.getByRole('button', { name: 'Upload slide', exact: true }).click()
  const reservationResponse = await reservation
  const body = await responseBody(reservationResponse)
  if (!reservationResponse.ok()) {
    throw new CapacityHttpError(
      'Synthetic upload reservation failed',
      reservationResponse.status(),
      sanitizedErrorCode(body),
    )
  }
  const slideId = (
    typeof body === 'object'
    && body !== null
    && typeof (body as { slide?: { id?: unknown } }).slide?.id === 'string'
  )
    ? (body as { slide: { id: string } }).slide.id
    : null
  if (slideId === null) throw new Error('Synthetic upload reservation was incomplete')
  return slideId
}

export async function waitForSlideConversion(
  page: Page,
  slideId: string,
  timeoutMs = 10 * 60_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (true) {
    const observation = await page.evaluate(async (approvedSlideId) => {
      const response = await fetch(
        `/api/v1/admin/slides/${encodeURIComponent(approvedSlideId)}`,
        { credentials: 'same-origin' },
      )
      let body: unknown = null
      try {
        body = await response.json()
      } catch {
        // A non-JSON response is reported through its HTTP status.
      }
      return { body, ok: response.ok, status: response.status }
    }, slideId)
    if (!observation.ok) {
      throw new CapacityHttpError(
        'Synthetic fixture conversion status was unavailable',
        observation.status,
        sanitizedErrorCode(observation.body),
      )
    }
    const decision = conversionDecision(
      observation.body,
      Date.now() >= deadline,
    )
    if (decision.kind === 'ready') return
    if (decision.kind === 'failed') {
      throw new CapacityHttpError(
        'Synthetic fixture conversion failed',
        0,
        decision.errorCode,
      )
    }
    await page.waitForTimeout(Math.min(5_000, Math.max(1, deadline - Date.now())))
  }
}

export async function csrfJson(
  page: Page,
  path: string,
  init: { method: 'DELETE' | 'POST'; body?: unknown; headers?: Record<string, string> },
): Promise<JsonResponse> {
  return page.evaluate(async ({ requestPath, requestInit }) => {
    const response = await fetch(requestPath, {
      method: requestInit.method,
      credentials: 'same-origin',
      headers: {
        ...(requestInit.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...requestInit.headers,
        'X-CSRF-Token': sessionStorage.getItem('pathlab-csrf') ?? '',
      },
      ...(requestInit.body === undefined
        ? {}
        : { body: JSON.stringify(requestInit.body) }),
    })
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      // DELETE may legitimately return no JSON body.
    }
    const record = typeof body === 'object' && body !== null
      ? body as Record<string, unknown>
      : {}
    const detail = typeof record.detail === 'object' && record.detail !== null
      ? record.detail as Record<string, unknown>
      : {}
    const candidate = detail.code ?? record.code
    const errorCode = typeof candidate === 'string'
      && /^[A-Z0-9_]{1,64}$/.test(candidate)
      ? candidate
      : undefined
    return {
      body,
      ...(errorCode === undefined ? {} : { errorCode }),
      ok: response.ok,
      status: response.status,
    }
  }, { requestPath: path, requestInit: init })
}

export async function waitForSlideDeletion(
  page: Page,
  slideId: string,
): Promise<void> {
  await expect.poll(async () => page.evaluate(async (approvedSlideId) => {
    const response = await fetch(
      `/api/v1/admin/slides/${encodeURIComponent(approvedSlideId)}`,
      { credentials: 'same-origin' },
    )
    return response.status
  }, slideId), {
    timeout: 5 * 60_000,
    intervals: [5_000],
    message: 'Synthetic slide was not removed',
  }).toBe(404)
}
