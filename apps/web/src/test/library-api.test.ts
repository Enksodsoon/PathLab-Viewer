import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  batchMoveSlides,
  createFolder,
  emptyLibraryTrash,
  getLibraryItems,
  getLibraryNavigation,
  getSlideStatuses,
} from '../api'

describe('library v2 API contracts', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.restoreAllMocks()
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
})
