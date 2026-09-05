import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { localDateTimeInputValue } from '../classroom/localDateTime'
import { ClassroomTeacherPage } from '../pages/ClassroomTeacherPage'
import { ApiError } from '../api'
import { ThemeProvider } from '../theme/ThemeProvider'

const classroomApi = vi.hoisted(() => ({
  classroomReadiness: vi.fn(),
  classroomSetupFolders: vi.fn(),
  createClassroom: vi.fn(),
  endActiveClassroom: vi.fn(),
  listClassrooms: vi.fn(),
  startLiveClassroom: vi.fn(),
  teacherState: vi.fn(),
}))

vi.mock('../classroom/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../classroom/api')>(),
  ...classroomApi,
}))

const rootFolder = {
  id: 'folder-course',
  name: 'Pathology 101',
  folderPath: ['Pathology 101'],
  depth: 0,
  hasChildren: true,
  readyCount: 2,
  blockedCount: 0,
  tooManySlides: false,
}

const childFolder = {
  ...rootFolder,
  id: 'folder-week-one',
  name: 'Week 1',
  folderPath: ['Pathology 101', 'Year 1', 'Block A', 'Week 1'],
  depth: 3,
  readyCount: 2,
  blockedCount: 0,
  hasChildren: false,
}

const emptyFolder = {
  ...rootFolder,
  id: 'folder-empty',
  name: 'Empty class',
  folderPath: ['Empty class'],
  readyCount: 0,
  blockedCount: 0,
  hasChildren: false,
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
    classroomApi.classroomSetupFolders.mockImplementation(async ({ cursor }: { cursor?: string }) => (
      cursor
        ? { items: [childFolder], nextCursor: null }
        : { items: [rootFolder, emptyFolder], nextCursor: 'page-2' }
    ))
    classroomApi.listClassrooms.mockResolvedValue({ sessions: [] })
    classroomApi.createClassroom.mockReturnValue(new Promise(() => undefined))
    classroomApi.endActiveClassroom.mockResolvedValue(undefined)
    classroomApi.classroomReadiness.mockResolvedValue({
      folderId: rootFolder.id,
      ready: [
        { id: 'slide-root', displayName: 'Root H&E', folderPath: ['Pathology 101'] },
        { id: 'slide-child', displayName: 'Child H&E', folderPath: ['Pathology 101', 'Week 1'] },
      ],
      blocked: [],
      tooManySlides: false,
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
    const root = within(group).getByRole('radio', { name: /Pathology 101.*2 slides.*includes subfolders/i })
    const empty = within(group).getByRole('radio', { name: /Empty class.*No slides/i })

    expect(root.closest('label')?.querySelector('.classroom-folder-picker__icon svg')).toBeInTheDocument()
    expect(empty).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Load more folders' }))
    const child = within(group).getByRole('radio', { name: /Week 1.*2 slides.*Pathology 101.*Year 1.*Block A/i })
    expect(child).toBeEnabled()

    await userEvent.click(root)
    await userEvent.click(screen.getByRole('button', { name: 'Prepare classroom with 2 slides' }))

    await waitFor(() => expect(classroomApi.createClassroom).toHaveBeenCalledWith(
      'folder-course', expect.any(String),
    ))
    expect(screen.getByRole('button', { name: 'Preparing classroom…' })).toBeDisabled()
  })

  it('shows safe empty and error states and clears a recovered deferred folder failure', async () => {
    let rejectSearch!: (error: Error) => void
    const deferredFailure = new Promise<never>((_resolve, reject) => { rejectSearch = reject })
    classroomApi.classroomSetupFolders.mockImplementation(({ q }: { q?: string }) => {
      if (q === 'renal') return deferredFailure
      if (q) return Promise.resolve({ items: [rootFolder], nextCursor: null })
      return Promise.resolve({ items: [], nextCursor: null })
    })
    renderSetup()

    expect(await screen.findByText('Create a library folder before starting a classroom.')).toBeInTheDocument()

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search class folders' }), 'renal')
    await act(async () => rejectSearch(new Error('offline')))
    expect(await screen.findByRole('alert')).toHaveTextContent('Class folders could not be loaded.')

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search class folders' }), 'x')
    expect(await screen.findByRole('radio', { name: /Pathology 101/i })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('Class folders could not be loaded.')).not.toBeInTheDocument())
  })

  it('discards an old load-more page after a new search starts', async () => {
    let resolveOldPage!: (page: { items: Array<typeof childFolder>; nextCursor: string | null }) => void
    const searchFolder = {
      ...childFolder,
      id: 'folder-renal',
      name: 'Renal course',
      folderPath: ['Renal course'],
      depth: 0,
    }
    const staleFolder = { ...childFolder, id: 'folder-stale', name: 'Old page folder' }
    classroomApi.classroomSetupFolders.mockImplementation(({ cursor, q }: {
      cursor?: string; q?: string
    }) => {
      if (cursor) return new Promise((resolve) => { resolveOldPage = resolve })
      if (q) return Promise.resolve({ items: [searchFolder], nextCursor: null })
      return Promise.resolve({ items: [rootFolder], nextCursor: 'old-page' })
    })
    renderSetup()

    await userEvent.click(await screen.findByRole('button', { name: 'Load more folders' }))
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search class folders' }), 'renal')
    expect(await screen.findByRole('radio', { name: /Renal course/i })).toBeInTheDocument()

    await act(async () => resolveOldPage({ items: [staleFolder], nextCursor: 'stale-page' }))

    expect(screen.queryByRole('radio', { name: /Old page folder/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load more folders' })).not.toBeInTheDocument()
  })

  it('uses local wall-clock values for review expiry bounds', () => {
    const instant = new Date('2026-01-15T05:34:00.000Z')
    vi.spyOn(instant, 'getTimezoneOffset').mockReturnValue(-420)

    expect(localDateTimeInputValue(instant)).toBe('2026-01-15T12:34')
  })

  it('submits classroom creation only once while preparation is in flight', async () => {
    renderSetup()

    const group = await screen.findByRole('radiogroup', { name: 'Class folder' })
    await userEvent.click(within(group).getByRole('radio', { name: /Pathology 101/i }))
    const prepare = screen.getByRole('button', { name: 'Prepare classroom with 2 slides' })
    await userEvent.dblClick(prepare)

    await waitFor(() => expect(classroomApi.createClassroom).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('button', { name: 'Preparing classroom…' })).toBeDisabled()
  })

  it('does not offer owner recovery when another classroom is in use', async () => {
    classroomApi.createClassroom.mockRejectedValue(new ApiError(409, 'CLASSROOM_IN_USE'))
    renderSetup()

    await userEvent.click(await screen.findByRole('radio', { name: /Pathology 101/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Prepare classroom with 2 slides' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Another classroom is currently active. Try again after it ends.',
    )
    expect(screen.queryByRole('button', { name: 'End existing classroom' })).not.toBeInTheDocument()
    expect(classroomApi.endActiveClassroom).not.toHaveBeenCalled()
  })

  it('does not claim recovery succeeded when no owned active classroom exists', async () => {
    classroomApi.createClassroom.mockRejectedValue(new ApiError(409, 'CLASSROOM_ALREADY_ACTIVE'))
    classroomApi.endActiveClassroom.mockRejectedValue(new ApiError(404, 'CLASSROOM_NOT_FOUND'))
    renderSetup()

    await userEvent.click(await screen.findByRole('radio', { name: /Pathology 101/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Prepare classroom with 2 slides' }))
    await userEvent.click(await screen.findByRole('button', { name: 'End existing classroom' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'No active classroom owned by this account was found. Refresh and try again.',
    )
    expect(screen.queryByText('The previous classroom ended. You can start a new one now.')).not.toBeInTheDocument()
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
