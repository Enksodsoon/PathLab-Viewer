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
  batchUpdateSlides: vi.fn(),
  mutateLibrarySlide: vi.fn(),
  mutateSlide: vi.fn(),
  publishSlide: vi.fn(),
  deleteLibrarySlide: vi.fn(),
  mutateFolder: vi.fn(),
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
  api.getLibrarySlide.mockResolvedValue({
    ...items.items[0],
    filename: 'colon.ome.tiff',
    adminNotes: 'Private teaching preparation',
    metadata: null,
  })
  api.batchUpdateSlides.mockImplementation(async (_ids, metadata) => ([{
    ...items.items[0],
    ...metadata,
  }]))
  api.mutateLibrarySlide.mockImplementation(async (_id, action) => ({
    ...items.items[0],
    trashedAt: action === 'trash' ? '2026-07-23T00:00:00Z' : null,
  }))
  api.mutateSlide.mockImplementation(async (id, action) => ({
    ...items.items.find((slide) => slide.id === id),
    state: action === 'unpublish' ? 'ready_private' : action === 'retry' ? 'queued' : 'published',
  }))
  api.publishSlide.mockImplementation(async (id) => ({
    ...items.items.find((slide) => slide.id === id),
    state: 'published',
  }))
  api.deleteLibrarySlide.mockResolvedValue(undefined)
  api.mutateFolder.mockResolvedValue(undefined)
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

  it('provides forward navigation and all creation actions from the toolbar', async () => {
    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findAllByText('Colon adenocarcinoma')

    expect(screen.getByRole('button', { name: /^forward$/i })).toBeEnabled()
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }))
    expect(screen.getByRole('menuitem', { name: /new folder/i })).toBeVisible()
    expect(screen.getByRole('menuitem', { name: /new collection/i })).toBeVisible()
    expect(screen.getByRole('menuitem', { name: /new saved view/i })).toBeVisible()
  })

  it('exposes mobile-safe accessible names and selected view state', async () => {
    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findAllByText('Colon adenocarcinoma')

    expect(screen.getByRole('button', { name: /^filters$/i })).toHaveAttribute(
      'aria-label',
      'Filters',
    )
    expect(screen.getByRole('button', { name: /grid view/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByRole('button', { name: /list view/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    )

    await userEvent.click(screen.getByRole('button', { name: /list view/i }))

    expect(screen.getByRole('button', { name: /grid view/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
    expect(screen.getByRole('button', { name: /list view/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('isolates the mobile navigator and restores focus after Escape', async () => {
    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findAllByText('Colon adenocarcinoma')

    const toggle = screen.getByRole('button', { name: /open library navigator/i })
    const main = screen.getByRole('main')
    const productNavigation = screen.getByRole('complementary', {
      name: /product navigation/i,
    })

    expect(toggle).toHaveAttribute('aria-controls', 'library-navigator')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(document.querySelector('#library-navigator')).toBeInTheDocument()

    await userEvent.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(main).toHaveAttribute('inert')
    expect(productNavigation).toHaveAttribute('inert')

    await userEvent.keyboard('{Escape}')

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(main).not.toHaveAttribute('inert')
    expect(productNavigation).not.toHaveAttribute('inert')
    expect(toggle).toHaveFocus()
  })

  it('turns the card overflow control into a complete metadata workflow', async () => {
    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findAllByText('Colon adenocarcinoma')

    await userEvent.click(screen.getByRole('button', {
      name: /more actions for colon adenocarcinoma/i,
    }))
    await userEvent.click(screen.getByRole('menuitem', { name: /edit details/i }))

    expect(await screen.findByRole('heading', { name: /edit slide details/i })).toBeVisible()
    expect(screen.getByRole('textbox', { name: /^display name$/i })).toHaveValue(
      'Colon adenocarcinoma',
    )
    expect(screen.getByRole('textbox', { name: /administrator note/i })).toHaveValue(
      'Private teaching preparation',
    )

    await userEvent.clear(screen.getByRole('textbox', { name: /^diagnosis$/i }))
    await userEvent.type(
      screen.getByRole('textbox', { name: /^diagnosis$/i }),
      'Updated diagnosis',
    )
    await userEvent.click(screen.getByRole('button', { name: /save details/i }))

    await waitFor(() => expect(api.batchUpdateSlides).toHaveBeenCalledWith(
      ['slide-1'],
      expect.objectContaining({ diagnosis: 'Updated diagnosis' }),
    ))
  })

  it('replaces publish and trash with restore and permanent delete inside Trash', async () => {
    const trashedPage: LibraryItemsPage = {
      ...items,
      items: items.items.map((slide) => ({
        ...slide,
        trashedAt: '2026-07-23T00:00:00Z',
      })),
    }
    api.getLibraryItems.mockResolvedValue(trashedPage)

    render(
      <MemoryRouter initialEntries={['/admin?location=trash']}>
        <AdminPage />
      </MemoryRouter>,
    )
    await screen.findAllByText('Colon adenocarcinoma')

    await userEvent.click(screen.getByRole('checkbox', {
      name: /select colon adenocarcinoma/i,
    }))
    const actions = screen.getByRole('toolbar', { name: /selection actions/i })
    expect(actions).toHaveTextContent('Restore')
    expect(actions).toHaveTextContent('Delete permanently')
    expect(actions).not.toHaveTextContent('Publish')
    expect(actions).not.toHaveTextContent(/^Trash$/)
  })

  it('exposes working organization actions from the navigator', async () => {
    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findAllByText('Colon adenocarcinoma')

    await userEvent.click(screen.getByRole('button', {
      name: /more actions for organ systems/i,
    }))
    expect(screen.getByRole('menuitem', { name: /^rename$/i })).toBeVisible()
    expect(screen.getByRole('menuitem', { name: /^move$/i })).toBeVisible()
    await userEvent.click(screen.getByRole('menuitem', { name: /move to trash/i }))
    expect(screen.getByRole('heading', { name: /move folder to trash/i })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: /^move folder to trash$/i }))

    await waitFor(() => expect(api.mutateFolder).toHaveBeenCalledWith(
      'folder-organs',
      'trash',
    ))

    await userEvent.click(screen.getByRole('button', {
      name: /more actions for week 5 teaching set/i,
    }))
    await userEvent.click(screen.getByRole('menuitem', { name: /^rename$/i }))
    expect(screen.getByRole('heading', { name: /rename collection/i })).toBeVisible()
    expect(screen.getByRole('textbox', { name: /^name$/i })).toHaveValue(
      'Week 5 Teaching Set',
    )
  })

  it('offers state-safe actions and the same overflow menu in table view', async () => {
    api.getLibraryItems.mockResolvedValue({
      ...items,
      items: [
        { ...items.items[0], state: 'published' },
        { ...items.items[1], state: 'failed', displayName: 'Failed conversion' },
      ],
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findAllByText('Colon adenocarcinoma')

    await userEvent.click(screen.getByRole('button', {
      name: /more actions for colon adenocarcinoma/i,
    }))
    expect(screen.getByRole('menuitem', { name: /open public slide/i })).toBeVisible()
    expect(screen.getByRole('menuitem', { name: /copy public link/i })).toBeVisible()
    await userEvent.click(screen.getByRole('menuitem', { name: /^unpublish$/i }))
    await waitFor(() => expect(api.mutateSlide).toHaveBeenCalledWith('slide-1', 'unpublish'))

    await userEvent.click(screen.getByRole('button', {
      name: /more actions for failed conversion/i,
    }))
    expect(screen.queryByRole('menuitem', { name: /^preview$/i })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('menuitem', { name: /retry conversion/i }))
    await waitFor(() => expect(api.mutateSlide).toHaveBeenCalledWith('slide-2', 'retry'))

    await userEvent.click(screen.getByRole('button', { name: /table view/i }))
    expect(screen.getByRole('button', {
      name: /more actions for colon adenocarcinoma/i,
    })).toBeVisible()
  })

  it('keeps failed mutations visible instead of leaving a dead control', async () => {
    api.publishSlide.mockRejectedValueOnce(new Error('offline'))
    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findAllByText('Colon adenocarcinoma')

    await userEvent.click(screen.getByRole('button', {
      name: /more actions for colon adenocarcinoma/i,
    }))
    await userEvent.click(screen.getByRole('menuitem', { name: /^publish$/i }))
    await userEvent.click(screen.getByRole('checkbox', {
      name: /patient identifiers and private information have been removed/i,
    }))
    await userEvent.click(screen.getByRole('button', { name: /publish 1 slide/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/publish.*failed/i)
    expect(screen.getByRole('button', {
      name: /more actions for colon adenocarcinoma/i,
    })).toBeEnabled()
  })
})
