import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ClassroomTeacherPage } from '../pages/ClassroomTeacherPage'
import { ApiError } from '../api'
import { ThemeProvider } from '../theme/ThemeProvider'
import type { AdminSlide, LibraryFolder, LibraryNavigation } from '../types'

const api = vi.hoisted(() => ({
  listSlides: vi.fn(),
  getLibraryNavigation: vi.fn(),
  getFolderChildren: vi.fn(),
}))

const classroomApi = vi.hoisted(() => ({
  classroomReadiness: vi.fn(),
  createClassroom: vi.fn(),
  startLiveClassroom: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api')>(),
  ...api,
}))

vi.mock('../classroom/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../classroom/api')>(),
  ...classroomApi,
}))

const rootFolder: LibraryFolder = {
  id: 'folder-course',
  parentId: null,
  name: 'Pathology 101',
  description: '',
  sortOrder: 0,
  itemCount: 2,
  childCount: 1,
  hasChildren: true,
  trashedAt: null,
  updatedAt: '2026-08-13T00:00:00Z',
}

const childFolder: LibraryFolder = {
  ...rootFolder,
  id: 'folder-week-one',
  parentId: rootFolder.id,
  name: 'Week 1',
  itemCount: 2,
  childCount: 0,
  hasChildren: false,
}

const emptyFolder: LibraryFolder = {
  ...rootFolder,
  id: 'folder-empty',
  name: 'Empty class',
  itemCount: 0,
  childCount: 0,
  hasChildren: false,
}

function slide(overrides: Partial<AdminSlide>): AdminSlide {
  return {
    id: 'slide-root',
    publicId: 'public-slide-root',
    displayName: 'Root H&E',
    filename: 'root.ome.tiff',
    sourceBytes: 1024,
    state: 'published',
    errorCode: null,
    errorMessage: null,
    metadata: { width: 1000, height: 800 },
    createdAt: '2026-08-13T00:00:00Z',
    folderId: rootFolder.id,
    renderMode: 'static_dzi',
    ...overrides,
  }
}

const navigation: LibraryNavigation = {
  capabilities: { classroom: true },
  counts: { all: 5, unfiled: 1, shared: 0, processing: 0, failed: 0, trash: 0 },
  folders: [rootFolder, emptyFolder],
  collections: [],
  savedViews: [],
  storage: { usedBytes: 1024, usableBytes: 1024, effectiveCapacityBytes: 2048 },
}

function renderSetup() {
  return render(
    <MemoryRouter initialEntries={['/admin/classroom']}>
      <ThemeProvider><ClassroomTeacherPage /></ThemeProvider>
    </MemoryRouter>,
  )
}

describe('Classroom folder setup', () => {
  beforeEach(() => {
    sessionStorage.clear()
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
    api.getFolderChildren.mockImplementation(async (folderId: string) => (
      folderId === rootFolder.id ? [childFolder] : []
    ))
    api.listSlides.mockResolvedValue([
      slide({}),
      slide({ id: 'slide-child', displayName: 'Child H&E', folderId: childFolder.id }),
      slide({ id: 'slide-dynamic', displayName: 'Dynamic slide', folderId: childFolder.id, renderMode: 'ome_dynamic' }),
      slide({ id: 'slide-private', displayName: 'Private slide', state: 'ready_private' }),
      slide({ id: 'slide-unfiled', displayName: 'Unfiled slide', folderId: null }),
    ])
    classroomApi.createClassroom.mockReturnValue(new Promise(() => undefined))
    classroomApi.classroomReadiness.mockResolvedValue({
      folderId: rootFolder.id,
      ready: [
        { id: 'slide-root', displayName: 'Root H&E', folderPath: ['Pathology 101'] },
        { id: 'slide-child', displayName: 'Child H&E', folderPath: ['Pathology 101', 'Week 1'] },
      ],
      blocked: [],
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('selects one folder and starts the classroom with every eligible descendant slide', async () => {
    renderSetup()

    const group = await screen.findByRole('radiogroup', { name: 'Class folder' })
    const root = within(group).getByRole('radio', { name: /Pathology 101.*4 slides.*includes subfolders/i })
    const child = within(group).getByRole('radio', { name: /Week 1.*2 slides/i })
    const empty = within(group).getByRole('radio', { name: /Empty class.*No slides/i })

    expect(root.closest('label')?.querySelector('.classroom-folder-picker__icon svg')).toBeInTheDocument()
    expect(child).toBeEnabled()
    expect(empty).toBeDisabled()

    await userEvent.click(root)
    await userEvent.click(screen.getByRole('button', { name: 'Prepare classroom with 2 slides' }))

    await waitFor(() => expect(classroomApi.createClassroom).toHaveBeenCalledWith(
      'folder-course', expect.any(String),
    ))
  })

  it('explains that background jobs are draining without polling', async () => {
    classroomApi.createClassroom.mockResolvedValue({
      id: 'classroom-1',
      joinCode: 'MINT-1234',
      publicId: 'public-classroom-1',
      phase: 'preview',
      reviewExpiresAt: '2026-08-23T00:00:00Z',
      stateVersion: 1,
      slides: [{
        id: 'slide-root', position: 0, displayName: 'Root H&E', assetVersion: 'v1',
        tileSource: '/tiles/slide-root/v1/slide.dzi', width: 1000, height: 800,
        tileSize: 512, format: 'jpg', folderPath: ['Pathology 101'],
      }],
    })
    classroomApi.startLiveClassroom.mockRejectedValue(
      new ApiError(409, 'CLASSROOM_DRAINING'),
    )
    renderSetup()

    const group = await screen.findByRole('radiogroup', { name: 'Class folder' })
    await userEvent.click(within(group).getByRole('radio', { name: /Pathology 101/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Prepare classroom with 2 slides' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Start live class' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Background preparation is stopping to protect the live class',
    )
    expect(classroomApi.startLiveClassroom).toHaveBeenCalledTimes(1)
  })
})
