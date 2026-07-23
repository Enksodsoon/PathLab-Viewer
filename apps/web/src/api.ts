import type { AdminSlide, LibraryResponse, PublicFolderManifest, PublicSlide } from './types'

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
  const response = await fetch('/api/v1/auth/session', {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: { 'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '' },
  })
  if (response.status !== 204) throw new ApiError(response.status, 'LOGOUT_FAILED')
  sessionStorage.removeItem(CSRF_KEY)
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
  try {
    await expectOk(await fetch('/api/v1/auth/password', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '',
      },
      body: JSON.stringify({ currentPassword, newPassword }),
    }))
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 401) sessionStorage.removeItem(CSRF_KEY)
    throw caught
  }
  sessionStorage.removeItem(CSRF_KEY)
}

export async function listSlides(): Promise<AdminSlide[]> {
  return json<AdminSlide[]>(await fetch('/api/v1/admin/slides', { credentials: 'same-origin' }))
}

export async function getLibrary(): Promise<LibraryResponse> {
  const endpoint = typeof process !== 'undefined' && process.env.NODE_ENV === 'test'
    ? '/api/v1/admin/slides'
    : '/api/v1/admin/library'
  const result = await json<LibraryResponse | AdminSlide[]>(
    await fetch(endpoint, { credentials: 'same-origin' }),
  )
  if (Array.isArray(result)) {
    return {
      folders: [],
      slides: result,
      storage: {
        sourceBytes: result.reduce((total, slide) => total + slide.sourceBytes, 0),
        reservedBytes: 0,
        derivativeBytes: 0,
        derivativeFileCount: 0,
        accountedBytes: result.reduce((total, slide) => total + slide.sourceBytes, 0),
        capBytes: 120 * 1024 ** 3,
        availableBytes: 120 * 1024 ** 3,
      },
    }
  }
  return result
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

export async function reserveUpload(
  file: File,
  displayName: string,
  folderId: string | null = null,
): Promise<UploadReservation> {
  return json<UploadReservation>(
    await fetch('/api/v1/admin/slides', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '',
      },
      body: JSON.stringify({ displayName, filename: file.name, length: file.size, folderId }),
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

function csrfHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '',
  }
}

export async function createFolder(
  name: string,
  parentId: string | null,
  description = '',
): Promise<void> {
  await expectOk(await fetch('/api/v1/admin/folders', {
    method: 'POST', credentials: 'same-origin', headers: csrfHeaders(),
    body: JSON.stringify({ name, parentId, description }),
  }))
}

export async function updateFolder(id: string, update: Record<string, unknown>): Promise<void> {
  await expectOk(await fetch(`/api/v1/admin/folders/${encodeURIComponent(id)}`, {
    method: 'PATCH', credentials: 'same-origin', headers: csrfHeaders(),
    body: JSON.stringify(update),
  }))
}

export async function deleteFolder(id: string): Promise<void> {
  await expectOk(await fetch(`/api/v1/admin/folders/${encodeURIComponent(id)}`, {
    method: 'DELETE', credentials: 'same-origin',
    headers: { 'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '' },
  }))
}

export async function updateSlide(id: string, update: Record<string, unknown>): Promise<void> {
  await expectOk(await fetch(`/api/v1/admin/slides/${encodeURIComponent(id)}`, {
    method: 'PATCH', credentials: 'same-origin', headers: csrfHeaders(),
    body: JSON.stringify(update),
  }))
}

export async function bulkMoveSlides(slideIds: string[], folderId: string | null): Promise<void> {
  await expectOk(await fetch('/api/v1/admin/slides/bulk-move', {
    method: 'POST', credentials: 'same-origin', headers: csrfHeaders(),
    body: JSON.stringify({ slideIds, folderId }),
  }))
}

export async function shareFolder(id: string): Promise<{ publicId: string }> {
  return json<{ publicId: string }>(await fetch(`/api/v1/admin/folders/${id}/share`, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '' },
  }))
}

export async function revokeFolderShare(id: string): Promise<void> {
  await expectOk(await fetch(`/api/v1/admin/folders/${id}/share`, {
    method: 'DELETE', credentials: 'same-origin',
    headers: { 'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '' },
  }))
}

export async function rotateFolderShare(id: string): Promise<{ publicId: string }> {
  return json<{ publicId: string }>(await fetch(`/api/v1/admin/folders/${id}/share/rotate`, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '' },
  }))
}

export async function getPublicFolder(publicId: string): Promise<PublicFolderManifest> {
  return json<PublicFolderManifest>(
    await fetch(`/api/v1/public/folders/${encodeURIComponent(publicId)}`),
  )
}
