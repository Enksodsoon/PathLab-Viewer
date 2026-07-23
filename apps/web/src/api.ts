import type {
  AdminSlide,
  LibraryCollection,
  LibraryFacets,
  LibraryFolder,
  LibraryItemsPage,
  LibraryNavigation,
  LibrarySlide,
  LibrarySlideDetails,
  PublicSlide,
  SavedView,
  SlideStatusItem,
} from './types'

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

function csrfHeaders(jsonBody = false): Record<string, string> {
  return {
    ...(jsonBody ? { 'Content-Type': 'application/json' } : {}),
    'X-CSRF-Token': sessionStorage.getItem(CSRF_KEY) ?? '',
  }
}

export async function getLibraryNavigation(): Promise<LibraryNavigation> {
  return json<LibraryNavigation>(
    await fetch('/api/v2/admin/library/navigation', { credentials: 'same-origin' }),
  )
}

export async function getFolderChildren(folderId: string): Promise<LibraryFolder[]> {
  return json<LibraryFolder[]>(
    await fetch(`/api/v2/admin/folders/${encodeURIComponent(folderId)}/children`, {
      credentials: 'same-origin',
    }),
  )
}

export interface LibraryItemsQuery {
  location?: string
  q?: string
  organ?: string
  stain?: string
  diagnosis?: string
  course?: string
  tags?: string[]
  state?: string
  sort?: string
  cursor?: string
  limit?: number
  signal?: AbortSignal
}

function libraryQuery(query: Omit<LibraryItemsQuery, 'signal'>): URLSearchParams {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === '' || value === null) continue
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, item)
    } else {
      params.set(key, String(value))
    }
  }
  return params
}

export async function getLibraryItems(query: LibraryItemsQuery): Promise<LibraryItemsPage> {
  const { signal, ...values } = query
  return json<LibraryItemsPage>(
    await fetch(`/api/v2/admin/library/items?${libraryQuery(values).toString()}`, {
      credentials: 'same-origin',
      signal,
    }),
  )
}

export async function getLibraryFacets(
  location: string,
  q: string,
  signal?: AbortSignal,
): Promise<LibraryFacets> {
  return json<LibraryFacets>(
    await fetch(`/api/v2/admin/library/facets?${libraryQuery({ location, q }).toString()}`, {
      credentials: 'same-origin',
      signal,
    }),
  )
}

export async function getLibrarySlide(slideId: string): Promise<LibrarySlideDetails> {
  return json<LibrarySlideDetails>(
    await fetch(`/api/v2/admin/slides/${encodeURIComponent(slideId)}`, {
      credentials: 'same-origin',
    }),
  )
}

export async function getSlideStatuses(slideIds: string[]): Promise<SlideStatusItem[]> {
  const params = new URLSearchParams({ ids: slideIds.join(',') })
  const body = await json<{ items: SlideStatusItem[] }>(
    await fetch(`/api/v2/admin/slides/status?${params.toString()}`, {
      credentials: 'same-origin',
    }),
  )
  return body.items
}

export async function createFolder(payload: {
  name: string
  parentId: string | null
  description?: string
}): Promise<LibraryFolder> {
  return json<LibraryFolder>(
    await fetch('/api/v2/admin/folders', {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfHeaders(true),
      body: JSON.stringify(payload),
    }),
  )
}

export async function updateFolder(
  folderId: string,
  payload: Partial<Pick<LibraryFolder, 'name' | 'description' | 'parentId' | 'sortOrder'>>,
): Promise<LibraryFolder> {
  return json<LibraryFolder>(
    await fetch(`/api/v2/admin/folders/${encodeURIComponent(folderId)}`, {
      method: 'PATCH',
      credentials: 'same-origin',
      headers: csrfHeaders(true),
      body: JSON.stringify(payload),
    }),
  )
}

export async function mutateFolder(folderId: string, action: 'trash' | 'restore'): Promise<void> {
  await expectOk(await fetch(
    `/api/v2/admin/folders/${encodeURIComponent(folderId)}/${action}`,
    { method: 'POST', credentials: 'same-origin', headers: csrfHeaders() },
  ))
}

export async function createCollection(payload: {
  name: string
  description?: string
}): Promise<LibraryCollection> {
  return json<LibraryCollection>(
    await fetch('/api/v2/admin/collections', {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfHeaders(true),
      body: JSON.stringify(payload),
    }),
  )
}

export async function addCollectionSlides(
  collectionId: string,
  slideIds: string[],
): Promise<string[]> {
  const body = await json<{ slideIds: string[] }>(
    await fetch(`/api/v2/admin/collections/${encodeURIComponent(collectionId)}/items`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfHeaders(true),
      body: JSON.stringify({ slideIds }),
    }),
  )
  return body.slideIds
}

export async function createSavedView(payload: {
  name: string
  definition: SavedView['definition']
  sort: string
}): Promise<SavedView> {
  return json<SavedView>(
    await fetch('/api/v2/admin/saved-views', {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfHeaders(true),
      body: JSON.stringify(payload),
    }),
  )
}

export async function batchMoveSlides(
  slideIds: string[],
  folderId: string | null,
): Promise<LibrarySlide[]> {
  const body = await json<{ items: LibrarySlide[] }>(
    await fetch('/api/v2/admin/slides/batch-move', {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfHeaders(true),
      body: JSON.stringify({ slideIds, folderId }),
    }),
  )
  return body.items
}

export async function batchUpdateSlides(
  slideIds: string[],
  metadata: Record<string, unknown>,
): Promise<LibrarySlide[]> {
  const body = await json<{ items: LibrarySlide[] }>(
    await fetch('/api/v2/admin/slides/batch-metadata', {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfHeaders(true),
      body: JSON.stringify({ slideIds, ...metadata }),
    }),
  )
  return body.items
}

export async function mutateLibrarySlide(
  slideId: string,
  action: 'trash' | 'restore',
): Promise<LibrarySlide> {
  return json<LibrarySlide>(
    await fetch(`/api/v2/admin/slides/${encodeURIComponent(slideId)}/${action}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfHeaders(),
    }),
  )
}
