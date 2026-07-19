import type { AdminSlide, PublicSlide } from './types'

const CSRF_KEY = 'pathlab-csrf'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code)
  }
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let code = `HTTP_${response.status}`
    try {
      const body = (await response.json()) as { detail?: { code?: string } }
      code = body.detail?.code ?? code
    } catch {
      // A proxy-generated response may not be JSON.
    }
    throw new ApiError(response.status, code)
  }
  return (await response.json()) as T
}

async function expectOk(response: Response): Promise<void> {
  if (!response.ok) await json<never>(response)
}

export async function login(username: string, password: string): Promise<void> {
  const body = await json<{ csrfToken: string }>(
    await fetch('/api/v1/auth/session', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }),
  )
  sessionStorage.setItem(CSRF_KEY, body.csrfToken)
}

export async function logout(): Promise<void> {
  try {
    await fetch('/api/v1/auth/session', {
      method: 'DELETE',
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '' },
    })
  } finally {
    sessionStorage.removeItem(CSRF_KEY)
  }
}

export async function recoverPassword(
  username: string,
  recoveryCode: string,
  newPassword: string,
): Promise<void> {
  await expectOk(await fetch('/api/v1/auth/password/recover', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, recoveryCode, newPassword }),
  }))
  sessionStorage.removeItem(CSRF_KEY)
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await expectOk(await fetch('/api/v1/auth/password', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '',
    },
    body: JSON.stringify({ currentPassword, newPassword }),
  }))
  sessionStorage.removeItem(CSRF_KEY)
}

export async function listSlides(): Promise<AdminSlide[]> {
  return json<AdminSlide[]>(await fetch('/api/v1/admin/slides', { credentials: 'same-origin' }))
}

export async function getPrivateSlide(slideId: string): Promise<AdminSlide> {
  return json<AdminSlide>(
    await fetch(`/api/v1/admin/slides/${encodeURIComponent(slideId)}`, {
      credentials: 'same-origin',
    }),
  )
}

export interface UploadReservation {
  slide: AdminSlide
  uploadUrl: string
  uploadToken: string
  expiresIn: number
}

export async function reserveUpload(file: File, displayName: string): Promise<UploadReservation> {
  return json<UploadReservation>(
    await fetch('/api/v1/admin/slides', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '',
      },
      body: JSON.stringify({ displayName, filename: file.name, length: file.size }),
    }),
  )
}

export async function mutateSlide(id: string, action: string): Promise<AdminSlide> {
  return json<AdminSlide>(
    await fetch(`/api/v1/admin/slides/${id}/${action}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '' },
    }),
  )
}

export async function deleteSlide(id: string): Promise<void> {
  const response = await fetch(`/api/v1/admin/slides/${id}`, {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: { 'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '' },
  })
  if (!response.ok) throw new ApiError(response.status, `HTTP_${response.status}`)
}

export async function getPublicSlide(publicId: string): Promise<PublicSlide> {
  return json<PublicSlide>(await fetch(`/api/v1/public/slides/${encodeURIComponent(publicId)}`))
}
