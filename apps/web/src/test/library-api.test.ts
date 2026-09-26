import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  batchMoveSlides,
  createFolder,
  emptyLibraryTrash,
  getLibraryItems,
  getLibraryNavigation,
  getSlideStatuses,
  reserveUpload,
  login,
  logout,
  csrfFetch,
  changePassword,
  recoverPassword,
} from '../api'

describe('library v2 API contracts', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('keeps server-authenticated mutations usable when session storage is denied', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: 'memory-token' })))
      .mockResolvedValueOnce(new Response(JSON.stringify([])))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({})))
    for (const method of ['getItem', 'setItem', 'removeItem'] as const) {
      vi.spyOn(Storage.prototype, method).mockImplementation(() => { throw new DOMException('Denied', 'SecurityError') })
    }
    await login('synthetic-owner', 'synthetic-password')
    await batchMoveSlides(['slide-1'], 'folder-1')
    expect(fetchMock.mock.calls[1]?.[1]?.headers).toMatchObject({ 'X-CSRF-Token': 'memory-token' })
    await logout()
    await csrfFetch('/synthetic')
    expect(fetchMock.mock.calls[3]?.[1]?.headers).toMatchObject({ 'X-CSRF-Token': '' })
  })

  it('uses memory CSRF when storage reads work but writes and removal fail', async () => {
    sessionStorage.setItem('pathlab-csrf', 'stale-token')
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: 'fresh-token' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({})))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({})))
    for (const method of ['setItem', 'removeItem'] as const) {
      vi.spyOn(Storage.prototype, method).mockImplementation(() => { throw new DOMException('Quota', 'QuotaExceededError') })
    }
    await login('owner', 'synthetic-password')
    await csrfFetch('/synthetic')
    expect(fetchMock.mock.calls[1]?.[1]?.headers).toMatchObject({ 'X-CSRF-Token': 'fresh-token' })
    await logout()
    await csrfFetch('/synthetic')
    expect(fetchMock.mock.calls[3]?.[1]?.headers).toMatchObject({ 'X-CSRF-Token': '' })
  })

  it.each([200, 401])('does not end, overwrite or replay a prior session after a newer login (refresh %s)', async (status) => {
    let finishRefresh!: (response: Response) => void
    const refresh = new Promise<Response>((resolve) => { finishRefresh = resolve })
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'CSRF_INVALID' } }), { status: 403 }))
      .mockImplementationOnce(() => refresh)
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: 'new-session' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({})))
    const pending = csrfFetch('/prior-session-mutation', { method: 'POST' })
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    await login('new-owner', 'synthetic-password')
    const dispatch = vi.spyOn(window, 'dispatchEvent')
    finishRefresh(new Response(JSON.stringify({ csrfToken: 'old-session' }), { status }))
    expect((await pending).status).toBe(403)
    expect(dispatch).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledTimes(3)
    await csrfFetch('/new-session-mutation')
    expect(fetchMock.mock.calls[3]?.[1]?.headers).toMatchObject({ 'X-CSRF-Token': 'new-session' })
  })

  it('ignores a stale refresh denial whose body arrives after a newer login', async () => {
    let finishBody!: (body: unknown) => void
    const delayedBody = new Promise<unknown>((resolve) => { finishBody = resolve })
    const denied = new Response(null, { status: 401 })
    const parse = vi.spyOn(denied, 'json').mockImplementation(() => delayedBody)
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'CSRF_INVALID' } }), { status: 403 }))
      .mockResolvedValueOnce(denied)
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: 'new-session' })))
    const pending = csrfFetch('/prior-session-mutation', { method: 'POST' })
    await vi.waitFor(() => expect(parse).toHaveBeenCalledOnce())
    await login('new-owner', 'synthetic-password')
    const dispatch = vi.spyOn(window, 'dispatchEvent')
    finishBody({ detail: { code: 'UNAUTHENTICATED' } })
    expect((await pending).status).toBe(403)
    expect(dispatch).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(sessionStorage.getItem('pathlab-csrf')).toBe('new-session')
  })

  it.each(['change', 'recover'])('ends upload ownership after successful password %s', async (action) => {
    sessionStorage.setItem('pathlab-csrf', 'old-token')
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    const ended = vi.fn()
    window.addEventListener('pathlab-session-ended', ended)
    try {
      if (action === 'change') await changePassword('old-password', 'new-password')
      else await recoverPassword('owner', 'recovery-code', 'new-password')
      expect(ended).toHaveBeenCalledTimes(1)
      await csrfFetch('/synthetic')
      expect(vi.mocked(fetch).mock.calls.at(-1)?.[1]?.headers).toMatchObject({ 'X-CSRF-Token': '' })
    } finally {
      window.removeEventListener('pathlab-session-ended', ended)
    }
  })

  it('requests navigation separately from paginated items', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({
        counts: { all: 0, unfiled: 0, shared: 0, processing: 0, failed: 0, trash: 0 },
        folders: [],
        collections: [],
        savedViews: [],
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        items: [],
        nextCursor: null,
        total: 0,
      })))
    const controller = new AbortController()

    await getLibraryNavigation()
    await getLibraryItems({
      location: 'folder:folder-1',
      q: 'lung',
      organ: 'Lung',
      sort: 'updated_desc',
      limit: 48,
      signal: controller.signal,
    })

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v2/admin/library/navigation', {
      credentials: 'same-origin',
    })
    const itemUrl = String(fetchMock.mock.calls[1]?.[0])
    expect(itemUrl).toContain('/api/v2/admin/library/items?')
    expect(itemUrl).toContain('location=folder%3Afolder-1')
    expect(itemUrl).toContain('q=lung')
    expect(itemUrl).toContain('organ=Lung')
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      credentials: 'same-origin',
      signal: controller.signal,
    })
  })

  it('sends CSRF-protected bounded mutations and targeted status IDs', async () => {
    sessionStorage.setItem('pathlab-csrf', 'csrf-token')
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockImplementation(async () => new Response(JSON.stringify({
        id: 'folder-1',
        name: 'Lung',
      })))

    await createFolder({ name: 'Lung', parentId: null })
    await batchMoveSlides(['slide-1', 'slide-2'], 'folder-1')
    await getSlideStatuses(['slide-1', 'slide-2'])
    await emptyLibraryTrash()

    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf-token',
      },
    })
    expect(fetchMock.mock.calls[1]?.[1]?.body).toBe(JSON.stringify({
      slideIds: ['slide-1', 'slide-2'],
      folderId: 'folder-1',
    }))
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain('ids=slide-1%2Cslide-2')
    expect(fetchMock.mock.calls[3]).toEqual([
      '/api/v2/admin/trash',
      {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': 'csrf-token' },
      },
    ])
  })

  it('refreshes a stale CSRF token and retries a mutation only once', async () => {
    sessionStorage.setItem('pathlab-csrf', 'stale-token')
    const forbidden = new Response(
      JSON.stringify({ detail: { code: 'CSRF_INVALID' } }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    )
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(forbidden)
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: 'fresh-token' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        slide: { id: 'slide-1' },
        uploadUrl: '/files/',
        uploadToken: 'upload-token',
        expiresIn: 900,
      })))

    await reserveUpload(
      new File(['fixture'], 'synthetic.ome.tiff', { type: 'image/tiff' }),
      'Synthetic',
    )

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[1]).toEqual([
      '/api/v1/auth/session',
      { credentials: 'same-origin', cache: 'no-store' },
    ])
    expect(new Headers(fetchMock.mock.calls[2]?.[1]?.headers).get('X-CSRF-Token'))
      .toBe('fresh-token')
    expect(sessionStorage.getItem('pathlab-csrf')).toBe('fresh-token')
  })

  it('does not retry unrelated forbidden mutations', async () => {
    sessionStorage.setItem('pathlab-csrf', 'csrf-token')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ detail: { code: 'STORAGE_CAPACITY_EXCEEDED' } }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    ))

    await expect(reserveUpload(
      new File(['fixture'], 'synthetic.ome.tiff', { type: 'image/tiff' }),
      'Synthetic',
    )).rejects.toMatchObject({ status: 403, code: 'STORAGE_CAPACITY_EXCEEDED' })
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
