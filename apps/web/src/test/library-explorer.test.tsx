import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminPage } from '../pages/AdminPage'
import type { LibraryItemsPage, LibraryNavigation } from '../types'

const api = vi.hoisted(() => ({
  getLibraryNavigation: vi.fn(),
  getLibraryItems: vi.fn(),
  getFolderChildren: vi.fn(),
  getLibrarySlide: vi.fn(),
  getSlideStatuses: vi.fn(),
  batchMoveSlides: vi.fn(),
  mutateLibrarySlide: vi.fn(),
  listSlides: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api')>(),
  ...api,
}))

const navigation: LibraryNavigation = {
  counts: { all: 2, unfiled: 0, shared: 0, processing: 1, failed: 0, trash: 0 },
  folders: [{
    id: 'folder-organs',
    parentId: null,
    name: 'Organ systems',
    description: '',
    sortOrder: 0,
    itemCount: 0,
    childCount: 1,
    hasChildren: true,
    trashedAt: null,
    updatedAt: '2026-07-23T00:00:00Z',
  }],
  collections: [{
    id: 'collection-week-5',
    name: 'Week 5 Teaching Set',
    description: '',
    sortOrder: 0,
    itemCount: 2,
    updatedAt: '2026-07-23T00:00:00Z',
  }],
  savedViews: [],
}

const items: LibraryItemsPage = {
  items: [
    {
      id: 'slide-1',
      publicId: 'public-1',
      displayName: 'Colon adenocarcinoma',
      description: '',
      folderId: 'folder-organs',
      caseId: 'GI-2026-014',
      organSite: 'Colon',
      stain: 'H&E',
      diagnosis: 'Adenocarcinoma',
      course: '',
      tags: ['Teaching'],
      teachingNote: '',
      sourceBytes: 3_420_000_000,
      derivativeBytes: 100,
      state: 'ready_private',
      errorCode: null,
      createdAt: '2026-07-23T00:00:00Z',
      updatedAt: '2026-07-23T00:00:00Z',
      trashedAt: null,
      thumbnailUrl: '/api/v2/admin/slides/slide-1/thumbnail',
    },
    {
      id: 'slide-2',
      publicId: 'public-2',
      displayName: 'HER2 gastric IHC',
      description: '',
      folderId: 'folder-organs',
      caseId: 'GI-2026-020',
      organSite: 'Stomach',
      stain: 'IHC',
      diagnosis: '',
      course: '',
      tags: [],
      teachingNote: '',
      sourceBytes: 1_740_000_000,
      derivativeBytes: 100,
      state: 'converting',
      errorCode: null,
      createdAt: '2026-07-23T00:00:00Z',
      updatedAt: '2026-07-23T00:00:00Z',
      trashedAt: null,
      thumbnailUrl: null,
    },
  ],
  nextCursor: null,
  total: 2,
}

beforeEach(() => {
  api.getLibraryNavigation.mockResolvedValue(navigation)
  api.getLibraryItems.mockResolvedValue(items)
  api.getFolderChildren.mockResolvedValue([{
    ...navigation.folders[0],
    id: 'folder-gi',
    parentId: 'folder-organs',
    name: 'GI',
    hasChildren: false,
    childCount: 0,
    itemCount: 2,
  }])
  api.getSlideStatuses.mockResolvedValue([])
  api.listSlides.mockResolvedValue([])
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.useRealTimers()
})

describe('dark library explorer', () => {
  it('shows only functional destinations and lazily expands folders', async () => {
    render(<AdminPage />, { wrapper: MemoryRouter })

    expect(await screen.findByRole('heading', { name: /slides library/i })).toBeVisible()
    expect(screen.getByRole('button', { name: /^library$/i })).toBeVisible()
    expect(screen.getByRole('button', { name: /^uploads$/i })).toBeVisible()
    expect(screen.queryByText('Cases')).not.toBeInTheDocument()
    expect(screen.queryByText('Annotations')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /expand organ systems/i }))
    expect(api.getFolderChildren).toHaveBeenCalledWith('folder-organs')
    expect(await screen.findByRole('treeitem', { name: /gi/i })).toBeVisible()
  })

  it('debounces search, switches table mode, and exposes bulk actions', async () => {
    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findAllByText('Colon adenocarcinoma')

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'lung' } })
    expect(api.getLibraryItems).toHaveBeenCalledTimes(1)
    await act(async () => new Promise((resolve) => window.setTimeout(resolve, 200)))
    expect(api.getLibraryItems).toHaveBeenCalledTimes(1)
    await act(async () => new Promise((resolve) => window.setTimeout(resolve, 20)))
    await waitFor(() => expect(api.getLibraryItems).toHaveBeenCalledTimes(2))

    fireEvent.click(screen.getByRole('button', { name: /table view/i }))
    expect(screen.getByRole('columnheader', { name: /diagnosis/i })).toBeVisible()
    fireEvent.click(screen.getByRole('checkbox', { name: /select colon adenocarcinoma/i }))
    expect(screen.getAllByText('1 selected').some((element) => element.matches('strong'))).toBe(true)
    expect(screen.getAllByRole('button', { name: /^move$/i }).some(
      (element) => element.closest('.selection-action-bar'),
    )).toBe(true)
  })

  it('polls only active slide IDs and stops while hidden', async () => {
    vi.useFakeTimers()
    let visibility: DocumentVisibilityState = 'visible'
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility)
    render(<AdminPage />, { wrapper: MemoryRouter })
    await act(async () => Promise.resolve())
    const initialItemsCalls = api.getLibraryItems.mock.calls.length

    await act(async () => vi.advanceTimersByTime(4000))
    expect(api.getSlideStatuses).toHaveBeenCalledWith(['slide-2'])
    expect(api.getLibraryItems).toHaveBeenCalledTimes(initialItemsCalls)

    visibility = 'hidden'
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
      await Promise.resolve()
    })
    const callsWhileVisible = api.getSlideStatuses.mock.calls.length
    await act(async () => vi.advanceTimersByTime(15_000))
    expect(api.getSlideStatuses).toHaveBeenCalledTimes(callsWhileVisible)
  })
})
