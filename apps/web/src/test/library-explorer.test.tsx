import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminPage as CanvasFocusAdminPage } from '../pages/AdminPage'
import { ThemeProvider } from '../theme/ThemeProvider'
import type { LibraryItemsPage, LibraryNavigation, StorageInventory } from '../types'

const api = vi.hoisted(() => ({
  getLibraryNavigation: vi.fn(),
  getLibraryItems: vi.fn(),
  getFolderChildren: vi.fn(),
  getLibrarySlide: vi.fn(),
  getSlideStatuses: vi.fn(),
  addCollectionSlides: vi.fn(),
  batchMoveSlides: vi.fn(),
  batchUpdateSlides: vi.fn(),
  mutateLibrarySlide: vi.fn(),
  mutateSlide: vi.fn(),
  publishSlide: vi.fn(),
  deleteLibrarySlide: vi.fn(),
  emptyLibraryTrash: vi.fn(),
  mutateFolder: vi.fn(),
  listSlides: vi.fn(),
  reserveUpload: vi.fn(),
  getStorageInventory: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api')>(),
  ...api,
}))

const tusUpload = vi.hoisted(() => ({
  startTusUpload: vi.fn(),
}))

vi.mock('../upload', () => tusUpload)

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
  storage: {
    usedBytes: 30 * 1024 ** 3,
    usableBytes: 90 * 1024 ** 3,
    effectiveCapacityBytes: 120 * 1024 ** 3,
  },
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

const storageInventory: StorageInventory = {
  summary: {
    managedBytes: 5_160_000_200,
    usableBytes: 118 * 1024 ** 3,
    effectiveCapacityBytes: 120 * 1024 ** 3,
    applicationCapBytes: 120 * 1024 ** 3,
    physicalTotalBytes: 150 * 1024 ** 3,
    physicalUsedBytes: 25 * 1024 ** 3,
    physicalFreeBytes: 125 * 1024 ** 3,
    libraryBytes: 3_420_000_100,
    processingBytes: 1_740_000_100,
    trashBytes: 0,
    deletingBytes: 0,
    libraryCount: 1,
    processingCount: 1,
    trashCount: 0,
    deletingCount: 0,
  },
  items: [{
    id: 'slide-1',
    displayName: 'Colon adenocarcinoma',
    originalFilename: 'colon.ome.tiff',
    state: 'ready_private',
    sourceBytes: 3_420_000_000,
    derivativeBytes: 100,
    reservedBytes: 0,
    accountedBytes: 3_420_000_100,
    updatedAt: '2026-07-23T00:00:00Z',
    trashedAt: null,
    canTrash: true,
    canRestore: false,
    canDelete: false,
  }],
  offset: 0,
  limit: 50,
  total: 1,
}

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })))
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
  api.addCollectionSlides.mockResolvedValue(['slide-1'])
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
  api.emptyLibraryTrash.mockResolvedValue({ scheduled: 2 })
  api.mutateFolder.mockResolvedValue(undefined)
  api.listSlides.mockResolvedValue([])
  api.reserveUpload.mockImplementation(async (file: File) => ({
    slide: {
      ...items.items[0],
      id: `reserved-${file.name}`,
      displayName: file.name.replace(/\.ome\.tiff?$/i, ''),
      state: 'uploading',
      sourceBytes: file.size,
      thumbnailUrl: null,
    },
    uploadUrl: '/api/v1/uploads/',
    uploadToken: `token-${file.name}`,
    expiresIn: 3600,
  }))
  api.getStorageInventory.mockResolvedValue(storageInventory)
  tusUpload.startTusUpload.mockImplementation(async (
    _file: File,
    _endpoint: string,
    _token: string,
    callbacks: { progress: (value: number) => void; success: () => void },
  ) => {
    callbacks.progress(100)
    callbacks.success()
    return {}
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

function renderCanvasFocusAdmin(initialEntry = '/admin') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AdminPage />
    </MemoryRouter>,
  )
}

function AdminPage() {
  return (
    <ThemeProvider>
      <CanvasFocusAdminPage />
    </ThemeProvider>
  )
}

describe('Canvas Focus library explorer', () => {
  it('uses a compact rail with two destinations and account utilities', async () => {
    renderCanvasFocusAdmin()

    await screen.findAllByText('Colon adenocarcinoma')
    const rail = screen.getByRole('complementary', { name: /product navigation/i })

    expect(rail).toHaveAttribute('data-canvas-region', 'icon-rail')
    expect(within(rail).getByRole('button', { name: /slide library/i })).toBeVisible()
    expect(within(rail).getByRole('button', { name: /^upload$/i })).toBeVisible()
    expect(within(rail).queryByRole('button', { name: /^processing$/i })).not.toBeInTheDocument()
    expect(within(rail).queryByRole('button', { name: /^failed$/i })).not.toBeInTheDocument()
    expect(within(rail).queryByRole('button', { name: /^trash$/i })).not.toBeInTheDocument()
    expect(within(rail).queryByRole('group', { name: /theme preference/i })).not.toBeInTheDocument()
    expect(screen.getByRole('group', { name: /theme preference/i })).toBeVisible()
    expect(within(rail).getByRole('button', { name: /^account$/i })).toBeVisible()
    expect(within(rail).getByRole('button', { name: /^sign out$/i })).toBeVisible()
    const storage = within(rail).getByRole('meter', {
      name: /usable storage remaining/i,
    })
    expect(storage).toHaveAttribute('aria-valuenow', '75')
    expect(storage).toHaveAttribute(
      'aria-valuetext',
      '90.00 GB available',
    )
    expect(storage.closest('.library-storage-meter')).toHaveAttribute(
      'aria-label',
      'Open storage, 90.00 GB available',
    )
    const thumbnailCard = screen.getByRole('button', {
      name: 'Open details for Colon adenocarcinoma',
    }).closest('.library-slide-card')
    expect(thumbnailCard).toHaveClass('library-slide-card--immersive')
    expect(thumbnailCard?.querySelector('.library-slide-thumbnail img')).toHaveAttribute(
      'src',
      '/api/v2/admin/slides/slide-1/thumbnail',
    )
    expect(thumbnailCard?.querySelector('.card-content-details')).toHaveTextContent(
      'Colon · H&E',
    )

    const toggle = within(rail).getByRole('button', { name: /expand navigation rail/i })
    expect(document.querySelector('.library-shell')).not.toHaveClass('rail-expanded')
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(document.querySelector('.library-shell')).toHaveClass('rail-expanded')
    expect(localStorage.getItem('pathlab-library-rail:v1')).toBe('expanded')
  })

  it('opens managed storage from the rail and moves a file to recoverable Trash', async () => {
    const user = userEvent.setup()
    renderCanvasFocusAdmin()
    await screen.findAllByText('Colon adenocarcinoma')

    await user.click(screen.getByRole('button', { name: /open storage/i }))

    expect(await screen.findByRole('heading', { name: /^storage$/i })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Files' })).toBeVisible()
    expect(await screen.findByText('colon.ome.tiff')).toBeVisible()
    expect(api.getStorageInventory).toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /move to trash/i }))
    await waitFor(() => expect(api.mutateLibrarySlide).toHaveBeenCalledWith('slide-1', 'trash'))
    expect(await screen.findByText(/moved to Trash/i)).toBeVisible()
  })

  it('restores or permanently deletes only items already in Trash', async () => {
    const user = userEvent.setup()
    api.getStorageInventory.mockResolvedValue({
      ...storageInventory,
      summary: { ...storageInventory.summary, libraryBytes: 0, libraryCount: 0, trashBytes: 3_420_000_100, trashCount: 1 },
      items: [{
        ...storageInventory.items[0],
        trashedAt: '2026-07-23T00:00:00Z',
        canTrash: false,
        canRestore: true,
        canDelete: true,
      }],
    })
    renderCanvasFocusAdmin('/admin?location=storage')

    await screen.findByRole('heading', { name: /^storage$/i })
    await screen.findByText('colon.ome.tiff')
    await user.click(screen.getByRole('button', { name: /^restore:/i }))
    await waitFor(() => expect(api.mutateLibrarySlide).toHaveBeenCalledWith('slide-1', 'restore'))

    await user.click(screen.getByRole('button', { name: /delete permanently/i }))
    const dialog = screen.getByRole('dialog', { name: /delete permanently/i })
    await user.click(within(dialog).getByRole('button', { name: /^delete permanently$/i }))
    await waitFor(() => expect(api.deleteLibrarySlide).toHaveBeenCalledWith('slide-1'))
  })

  it('opens the Classroom workspace from the product rail when enabled', async () => {
    api.getLibraryNavigation.mockResolvedValue({
      ...navigation,
      capabilities: { classroom: true },
    })

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/admin/classroom" element={<h1>Classroom workspace</h1>} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findAllByText('Colon adenocarcinoma')
    const rail = screen.getByRole('complementary', { name: /product navigation/i })
    await userEvent.click(within(rail).getByRole('button', { name: /^classroom$/i }))

    expect(screen.getByRole('heading', { name: 'Classroom workspace' })).toBeVisible()
  })

  it('leaves absent card metadata blank instead of showing placeholder copy', async () => {
    api.getLibraryItems.mockResolvedValue({
      ...items,
      items: [{
        ...items.items[0],
        id: 'slide-without-metadata',
        displayName: 'Unlabelled slide',
        description: '',
        caseId: '',
        organSite: '',
        stain: '',
        diagnosis: '',
        tags: [],
        state: 'published',
      }],
      total: 1,
    })

    renderCanvasFocusAdmin()

    const card = (await screen.findByRole('button', {
      name: 'Open details for Unlabelled slide',
    })).closest('.library-slide-card')
    expect(card).not.toBeNull()
    expect(card).not.toHaveTextContent('Metadata pending')
    expect(card).not.toHaveTextContent('Case —')
    expect(card?.querySelector('.card-description')).not.toBeInTheDocument()
  })

  it('integrates quick views inside the Canvas Focus navigator overlay', async () => {
    renderCanvasFocusAdmin()
    await screen.findAllByText('Colon adenocarcinoma')

    const toggle = screen.getByRole('button', { name: /slide library/i })
    const main = screen.getByRole('main')
    const productNavigation = screen.getByRole('complementary', {
      name: /product navigation/i,
    })
    await userEvent.click(toggle)

    const navigator = screen.getByRole('complementary', { name: /library navigator/i })
    const overlay = navigator.closest('#library-navigator')
    const quickViews = within(navigator).getByRole('region', { name: /quick views/i })
    const rootFolder = within(navigator).getByRole('treeitem', {
      name: navigation.folders[0].name,
    })
    expect(overlay).toHaveAttribute('data-overlay', 'navigator')
    expect(overlay).toHaveAttribute('aria-hidden', 'false')
    expect(quickViews).toBeVisible()
    expect(within(rootFolder).getByLabelText('1 subfolder')).toHaveTextContent('1')
    expect(within(navigator).getByRole('button', { name: /processing 1/i })).toBeVisible()
    expect(within(navigator).getByRole('button', { name: /failed 0/i })).toBeVisible()
    expect(within(navigator).getByRole('button', { name: /trash 0/i })).toBeVisible()
    expect(within(quickViews).getByRole('button', {
      name: /week 5 teaching set 2/i,
    })).toBeVisible()
    expect(main).toHaveAttribute('inert')
    expect(productNavigation).toHaveAttribute('inert')

    await userEvent.keyboard('{Escape}')
    expect(overlay).toHaveAttribute('aria-hidden', 'true')
    await waitFor(() => expect(toggle).toHaveFocus())

    await userEvent.click(toggle)
    await userEvent.click(within(quickViews).getByRole('button', {
      name: /colon adenocarcinoma/i,
    }))
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('complementary', { name: /slide details/i })).toBeVisible()
  })

  it('opens slide details as a right overlay without adding a shell grid track', async () => {
    const view = renderCanvasFocusAdmin()
    await screen.findAllByText('Colon adenocarcinoma')

    await userEvent.click(screen.getByRole('button', {
      name: /open details for colon adenocarcinoma/i,
    }))

    const inspector = screen.getByRole('complementary', { name: /slide details/i })
    expect(inspector).toHaveAttribute('data-overlay', 'inspector')
    expect(view.container.querySelector('.library-shell')).toHaveAttribute(
      'data-layout',
      'canvas-focus',
    )
    expect(view.container.querySelector('.library-main')).toHaveAttribute(
      'data-canvas-region',
      'content',
    )
  })

  it('keeps only one cursor page rendered and restores the previous page from memory', async () => {
    const firstPage = { ...items, nextCursor: 'cursor-2', total: 3 }
    const secondPage = {
      items: [{ ...items.items[0], id: 'slide-3', displayName: 'Next page slide' }],
      nextCursor: null,
      total: 0,
    }
    api.getLibraryItems
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage)
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminPage />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Next page' }))
    expect(await screen.findByRole('heading', { name: 'Next page slide' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Colon adenocarcinoma' })).not.toBeInTheDocument()
    expect(api.getLibraryItems).toHaveBeenLastCalledWith(expect.objectContaining({
      cursor: 'cursor-2',
      includeTotal: false,
    }))

    await user.click(screen.getByRole('button', { name: 'Previous page' }))
    expect(await screen.findByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Next page slide' })).not.toBeInTheDocument()
    expect(api.getLibraryItems).toHaveBeenCalledTimes(2)
  })

  it('uses failed-only messaging when there are no failed files', async () => {
    api.getLibraryItems.mockResolvedValue({ items: [], nextCursor: null, total: 0 })
    render(
      <MemoryRouter initialEntries={['/admin?location=failed']}>
        <AdminPage />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'No failed files' })).toBeVisible()
    expect(screen.getByText('Files that fail processing will appear here.')).toBeVisible()
    expect(screen.getByRole('button', { name: /retry selected/i })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /^upload slide$/i })).not.toBeInTheDocument()
    expect(api.getLibraryItems).toHaveBeenCalledWith(expect.objectContaining({ location: 'failed' }))
  })

  it('uses processing-only messaging when no work is active', async () => {
    api.getLibraryItems.mockResolvedValue({ items: [], nextCursor: null, total: 0 })
    render(
      <MemoryRouter initialEntries={['/admin?location=processing']}>
        <AdminPage />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'No files processing' })).toBeVisible()
    expect(screen.getByText('Active uploads and conversions will appear here.')).toBeVisible()
    expect(screen.queryByRole('button', { name: /^upload slide$/i })).not.toBeInTheDocument()
  })

  it('shows honest processing stages and removes completed files', async () => {
    vi.useFakeTimers()
    api.getLibraryItems.mockResolvedValue({
      items: [
        { ...items.items[1], state: 'uploading', id: 'uploading-slide', displayName: 'Uploading slide' },
        { ...items.items[1], state: 'queued', id: 'queued-slide', displayName: 'Queued slide' },
        { ...items.items[1], state: 'validating', id: 'validating-slide', displayName: 'Validating slide' },
        { ...items.items[1], state: 'converting', id: 'converting-slide', displayName: 'Converting slide' },
      ],
      nextCursor: null,
      total: 4,
    })
    api.getSlideStatuses.mockResolvedValue([
      { id: 'uploading-slide', state: 'uploading', errorCode: null },
      { id: 'queued-slide', state: 'queued', errorCode: null },
      { id: 'validating-slide', state: 'validating', errorCode: null },
      { id: 'converting-slide', state: 'ready_private', errorCode: null },
    ])

    render(
      <MemoryRouter initialEntries={['/admin?location=processing']}>
        <AdminPage />
      </MemoryRouter>,
    )
    await act(async () => {
      await api.getLibraryItems.mock.results[0]?.value
      await Promise.resolve()
    })

    expect(screen.getByText('Receiving source file')).toBeVisible()
    expect(screen.getByText('Waiting for processing capacity')).toBeVisible()
    expect(screen.getByText('Checking image structure and OME metadata')).toBeVisible()
    expect(screen.getByText('Generating viewer tiles')).toBeVisible()
    expect(screen.getAllByRole('progressbar')).toHaveLength(4)

    await act(async () => vi.advanceTimersByTimeAsync(4000))

    expect(screen.queryByText('Converting slide')).not.toBeInTheDocument()
    expect(screen.getByText('3 slides')).toBeVisible()
  })

  it('explains failed files and retries the selected originals without re-uploading', async () => {
    const failedSlide = {
      ...items.items[1],
      displayName: 'Failed conversion',
      state: 'failed' as const,
      errorCode: 'UPLOAD_LENGTH_MISMATCH',
    }
    api.getLibraryItems.mockResolvedValue({
      items: [failedSlide],
      nextCursor: null,
      total: 1,
    })
    api.getLibraryNavigation.mockResolvedValue({
      ...navigation,
      counts: { ...navigation.counts, failed: 1 },
    })

    render(
      <MemoryRouter initialEntries={['/admin?location=failed']}>
        <AdminPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText('The uploaded file was incomplete.')).toBeVisible()
    expect(screen.getByText('Error code: UPLOAD_LENGTH_MISMATCH')).toBeVisible()
    const retry = screen.getByRole('button', { name: /retry selected/i })
    expect(retry).toBeDisabled()

    await userEvent.click(screen.getByRole('checkbox', { name: /select failed conversion/i }))
    expect(retry).toBeEnabled()
    await userEvent.click(retry)

    await waitFor(() => expect(api.mutateSlide).toHaveBeenCalledWith('slide-2', 'retry'))
    expect(await screen.findByRole('heading', { name: 'No failed files' })).toBeVisible()
    expect(screen.getAllByText('1 slide queued.')[0]).toBeVisible()
  })

  it('uses trash-specific messaging and disables unavailable trash actions', async () => {
    api.getLibraryItems.mockResolvedValue({ items: [], nextCursor: null, total: 0 })
    render(
      <MemoryRouter initialEntries={['/admin?location=trash']}>
        <AdminPage />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Trash is empty' })).toBeVisible()
    expect(screen.getByText('Deleted files will appear here until permanently removed.')).toBeVisible()
    expect(screen.queryByRole('button', { name: /^upload slide$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /restore selected/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /empty trash/i })).toBeDisabled()
  })

  it('uses neutral messaging when the current folder is empty', async () => {
    api.getLibraryItems.mockResolvedValue({ items: [], nextCursor: null, total: 0 })
    api.getFolderChildren.mockResolvedValue([])
    render(
      <MemoryRouter initialEntries={['/admin?location=folder%3Afolder-organs']}>
        <AdminPage />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'No files in this folder' })).toBeVisible()
    expect(screen.getByText('This folder is currently empty.')).toBeVisible()
    expect(screen.queryByRole('button', { name: /^upload slide$/i })).not.toBeInTheDocument()
  })

  it('shows and opens child folders instead of showing an empty-folder message', async () => {
    api.getLibraryItems.mockResolvedValue({ items: [], nextCursor: null, total: 0 })
    render(
      <MemoryRouter initialEntries={['/admin?location=folder%3Afolder-organs']}>
        <AdminPage />
      </MemoryRouter>,
    )

    await waitFor(() => expect(api.getFolderChildren).toHaveBeenCalledWith('folder-organs'))
    const childFolder = await screen.findByRole('button', { name: 'Open folder GI' })
    expect(screen.queryByRole('heading', { name: 'No files in this folder' }))
      .not.toBeInTheDocument()
    expect(screen.getByText('1 folder · 0 slides')).toBeVisible()

    await userEvent.click(childFolder)

    expect(await screen.findByRole('heading', { name: 'GI' })).toBeVisible()
    await waitFor(() => expect(api.getLibraryItems).toHaveBeenLastCalledWith(
      expect.objectContaining({ location: 'folder:folder-gi' }),
    ))
  })

  it('renders child folders in grid, list, and table modes with working navigation', async () => {
    api.getLibraryItems.mockResolvedValue({ items: [], nextCursor: null, total: 0 })
    renderCanvasFocusAdmin('/admin?location=folder%3Afolder-organs')

    const region = await screen.findByRole('region', { name: 'Folders' })
    expect(region).toHaveAttribute('data-view', 'grid')
    expect(region.querySelectorAll('.folder-artwork__paper')).toHaveLength(3)

    await userEvent.click(screen.getByRole('button', { name: /list view/i }))
    expect(region).toHaveAttribute('data-view', 'list')
    expect(region.querySelector('.library-folder-grid')).toHaveClass('list-view')

    await userEvent.click(screen.getByRole('button', { name: /table view/i }))
    expect(screen.getByRole('table', { name: 'Folders' })).toBeVisible()
    expect(screen.getByRole('columnheader', { name: 'Subfolders' })).toBeVisible()
    expect(region.querySelector('.folder-artwork--compact')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Open folder GI' }))
    expect(await screen.findByRole('heading', { name: 'GI' })).toBeVisible()
  })

  it('restores a nested folder title and breadcrumb on direct reload', async () => {
    const child = {
      ...navigation.folders[0],
      id: 'folder-gi',
      parentId: 'folder-organs',
      name: 'GI',
      hasChildren: false,
      childCount: 0,
    }
    api.getLibraryNavigation.mockResolvedValue({
      ...navigation,
      folderPath: [navigation.folders[0], child],
    })
    api.getLibraryItems.mockResolvedValue({ items: [], nextCursor: null, total: 0 })
    api.getFolderChildren.mockResolvedValue([])

    renderCanvasFocusAdmin('/admin?location=folder%3Afolder-gi')

    expect(await screen.findByRole('heading', { name: 'GI' })).toBeVisible()
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toHaveTextContent(
      'All slidesOrgan systemsGI',
    )
    expect(api.getLibraryNavigation).toHaveBeenCalledWith('folder-gi')
  })

  it('hydrates and expands the active folder path in the navigator', async () => {
    const root = navigation.folders[0]
    const child = {
      ...root,
      id: 'folder-gi',
      parentId: root.id,
      name: 'GI',
      hasChildren: true,
      childCount: 3,
    }
    const grandchildren = ['Test 1.1.1', '1', 'Hello'].map((name, index) => ({
      ...child,
      id: `nested-${index}`,
      parentId: child.id,
      name,
      hasChildren: false,
      childCount: 0,
    }))
    api.getLibraryNavigation.mockResolvedValue({
      ...navigation,
      folderPath: [root, child],
    })
    api.getLibraryItems.mockResolvedValue({ items: [], nextCursor: null, total: 0 })
    api.getFolderChildren.mockImplementation(async (folderId) => (
      folderId === root.id ? [child] : grandchildren
    ))

    renderCanvasFocusAdmin('/admin?location=folder%3Afolder-gi')

    expect(await screen.findByRole('heading', { name: 'GI' })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: /slide library/i }))

    const rootItem = await screen.findByRole('treeitem', { name: root.name })
    const childItem = await screen.findByRole('treeitem', { name: child.name })
    expect(rootItem).toHaveAttribute('aria-expanded', 'true')
    expect(childItem).toHaveAttribute('aria-expanded', 'true')
    for (const folder of grandchildren) {
      expect(await screen.findByRole('treeitem', { name: folder.name })).toBeVisible()
    }
    expect(api.getFolderChildren).toHaveBeenCalledWith(root.id)
    expect(api.getFolderChildren).toHaveBeenCalledWith(child.id)
  })

  it('combines OME-TIFF selection and upload details in one workspace', async () => {
    render(<AdminPage />, { wrapper: MemoryRouter })

    await screen.findByRole('heading', { name: /all slides/i })
    await userEvent.click(within(screen.getByRole('complementary', {
      name: /product navigation/i,
    })).getByRole('button', { name: /^upload$/i }))

    const fileInput = screen.getByLabelText('Choose OME-TIFF files')
    expect(fileInput).toHaveClass('upload-file-input')
    expect(screen.getByText('Drop OME-TIFF files here')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Choose files' })).toBeVisible()
    expect(fileInput).toHaveAttribute('accept', '.ome.tif,.ome.tiff,image/tiff')
    expect(fileInput).toHaveAttribute('multiple')

    await userEvent.upload(fileInput, new File(['slide'], 'sample.ome.tiff', { type: 'image/tiff' }))
    expect(screen.getByText('sample.ome.tiff')).toBeVisible()
    expect(screen.getByText(/Queued/)).toBeVisible()
    expect(screen.getByRole('textbox', { name: 'Display name' })).toHaveValue('sample')
    expect(screen.getByRole('button', { name: 'Upload 1 file' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Remove sample.ome.tiff' })).toBeVisible()
  })

  it('uploads a multi-file selection sequentially', async () => {
    let finishFirst: (() => void) | undefined
    tusUpload.startTusUpload
      .mockImplementationOnce((
        _file: File,
        _endpoint: string,
        _token: string,
        callbacks: { progress: (value: number) => void; success: () => void },
      ) => new Promise((resolve) => {
        callbacks.progress(40)
        finishFirst = () => {
          callbacks.success()
          resolve({})
        }
      }))
      .mockImplementationOnce(async (
        _file: File,
        _endpoint: string,
        _token: string,
        callbacks: { progress: (value: number) => void; success: () => void },
      ) => {
        callbacks.progress(100)
        callbacks.success()
        return {}
      })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findByRole('heading', { name: /all slides/i })
    await userEvent.click(within(screen.getByRole('complementary', {
      name: /product navigation/i,
    })).getByRole('button', { name: /^upload$/i }))

    await userEvent.upload(screen.getByLabelText('Choose OME-TIFF files'), [
      new File(['one'], 'one.ome.tiff', { type: 'image/tiff' }),
      new File(['two'], 'two.ome.tiff', { type: 'image/tiff' }),
    ])
    await userEvent.click(screen.getByRole('button', { name: 'Upload 2 files' }))

    await waitFor(() => expect(tusUpload.startTusUpload).toHaveBeenCalledTimes(1))
    expect(api.reserveUpload).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/Uploading 40%/)).toBeVisible()
    expect(screen.getByText(/Queued · 1 ahead/)).toBeVisible()

    await act(async () => finishFirst?.())

    await waitFor(() => {
      expect(tusUpload.startTusUpload).toHaveBeenCalledTimes(2)
      expect(api.reserveUpload).toHaveBeenCalledTimes(2)
    })
    expect(await screen.findAllByText(/Upload complete/)).toHaveLength(2)
  })

  it('shows only functional destinations and lazily expands folders', async () => {
    render(<AdminPage />, { wrapper: MemoryRouter })

    expect(await screen.findByRole('heading', { name: /all slides/i })).toBeVisible()
    expect(within(screen.getByRole('complementary', {
      name: /product navigation/i,
    })).getByRole('button', { name: /^upload$/i })).toBeVisible()
    expect(screen.queryByText('Cases')).not.toBeInTheDocument()
    expect(screen.queryByText('Annotations')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', {
      name: /slide library/i,
    }))
    expect(screen.getByRole('button', { name: /^all slides 2$/i })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: /expand organ systems/i }))
    expect(api.getFolderChildren).toHaveBeenCalledWith('folder-organs')
    expect(await screen.findByRole('treeitem', { name: /gi/i })).toBeVisible()
  })

  it('debounces search, switches table mode, and exposes bulk actions', async () => {
    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findAllByText('Colon adenocarcinoma')

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'lung' } })
    expect(api.getLibraryItems).toHaveBeenCalledTimes(1)
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

  it('refreshes navigator counters when a processing slide changes state', async () => {
    vi.useFakeTimers()
    api.getSlideStatuses.mockResolvedValue([{
      id: 'slide-2',
      state: 'published',
      errorCode: null,
    }])
    api.getLibraryNavigation
      .mockResolvedValueOnce(navigation)
      .mockResolvedValue({
        ...navigation,
        counts: { ...navigation.counts, shared: 1, processing: 0 },
      })

    render(<AdminPage />, { wrapper: MemoryRouter })
    await act(async () => {
      await api.getLibraryNavigation.mock.results[0]?.value
      await Promise.resolve()
    })
    expect(api.getLibraryNavigation).toHaveBeenCalledTimes(1)
    expect(api.getLibraryItems).toHaveBeenCalledTimes(1)
    await act(async () => {
      await api.getLibraryItems.mock.results[0]?.value
      await Promise.resolve()
    })

    await act(async () => vi.advanceTimersByTimeAsync(4000))

    expect(api.getSlideStatuses).toHaveBeenCalledWith(['slide-2'])
    expect(api.getLibraryNavigation).toHaveBeenCalledTimes(2)
    fireEvent.click(screen.getByRole('button', {
      name: /slide library/i,
    }))
    expect(screen.getByRole('button', { name: /shared 1/i })).toBeVisible()
    expect(screen.getByRole('button', { name: /processing 0/i })).toBeVisible()
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

    const toggle = screen.getByRole('button', { name: /slide library/i })
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
    await waitFor(() => expect(toggle).toHaveFocus())
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
    api.getLibraryNavigation.mockResolvedValue({
      ...navigation,
      counts: { ...navigation.counts, trash: 2 },
    })

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
    expect(screen.getByRole('button', { name: /restore selected/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /empty trash/i })).toBeEnabled()
  })

  it('confirms before scheduling the complete Trash for deletion', async () => {
    api.getLibraryItems.mockResolvedValue({
      ...items,
      items: items.items.map((slide) => ({
        ...slide,
        trashedAt: '2026-07-23T00:00:00Z',
      })),
    })
    api.getLibraryNavigation.mockResolvedValue({
      ...navigation,
      counts: { ...navigation.counts, trash: 2 },
    })

    render(
      <MemoryRouter initialEntries={['/admin?location=trash']}>
        <AdminPage />
      </MemoryRouter>,
    )
    await screen.findAllByText('Colon adenocarcinoma')

    await userEvent.click(screen.getByRole('button', { name: /empty trash/i }))
    const dialog = screen.getByRole('dialog', { name: /empty trash/i })
    expect(dialog).toHaveTextContent('2 files')
    await userEvent.click(within(dialog).getByRole('button', { name: /^empty trash$/i }))

    await waitFor(() => expect(api.emptyLibraryTrash).toHaveBeenCalledTimes(1))
    expect((await screen.findAllByText(
      '2 files queued for permanent deletion.',
    ))[0]).toBeVisible()
  })

  it('exposes working organization actions from the navigator', async () => {
    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findAllByText('Colon adenocarcinoma')

    await userEvent.click(screen.getByRole('button', {
      name: /slide library/i,
    }))
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

  it('refreshes the collection count immediately after adding slides', async () => {
    api.getLibraryNavigation
      .mockResolvedValueOnce(navigation)
      .mockResolvedValue({
        ...navigation,
        collections: navigation.collections.map((collection) => ({
          ...collection,
          itemCount: 3,
        })),
      })

    render(<AdminPage />, { wrapper: MemoryRouter })
    await screen.findAllByText('Colon adenocarcinoma')

    await userEvent.click(screen.getByRole('checkbox', {
      name: /select colon adenocarcinoma/i,
    }))
    await userEvent.click(screen.getByRole('button', {
      name: /^add to collection$/i,
    }))
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: /collection/i }),
      'collection-week-5',
    )
    await userEvent.click(screen.getByRole('button', { name: /add slides/i }))

    await waitFor(() => expect(api.addCollectionSlides).toHaveBeenCalledWith(
      'collection-week-5',
      ['slide-1'],
    ))
    await userEvent.click(screen.getByRole('button', {
      name: /slide library/i,
    }))
    expect((await screen.findAllByRole('button', {
      name: /week 5 teaching set 3/i,
    }))[0]).toBeVisible()
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
    expect(screen.getByText('Public')).toBeVisible()

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
    })).toHaveClass('slide-actions-trigger')
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
