import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api'
import { ClassroomTeacherPage } from '../pages/ClassroomTeacherPage'
import { ThemeProvider } from '../theme/ThemeProvider'

const classroomApi = vi.hoisted(() => ({
  classroomReadiness: vi.fn(),
  classroomSetupFolders: vi.fn(),
  createClassroom: vi.fn(),
  listClassrooms: vi.fn(),
  teacherState: vi.fn(),
}))

vi.mock('../classroom/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../classroom/api')>(),
  ...classroomApi,
}))

const immutableSlides = [{
  id: 'snapshot-slide',
  position: 0,
  displayName: 'Original snapshot name',
  assetVersion: 'immutable-v1',
  tileSource: '/tiles/original/immutable-v1/slide.dzi',
  width: 4000,
  height: 3000,
  tileSize: 512,
  format: 'jpg',
  folderPath: ['Original course', 'Week 1'],
}]

const discovered = {
  id: 'owned-session',
  publicId: 'owned-public-id',
  phase: 'preview' as const,
  joinCode: 'MINT234567',
  reviewExpiresAt: '2026-09-12T12:00:00Z',
}

const teacherSnapshot = {
  session: {
    id: discovered.id,
    status: 'active',
    phase: discovered.phase,
    publicId: discovered.publicId,
    joinCode: discovered.joinCode,
    reviewExpiresAt: discovered.reviewExpiresAt,
  },
  stateVersion: 7,
  slides: immutableSlides,
  participantCount: 0,
  rosterVersion: 0,
  presenter: { sequence: 0, slideId: 'snapshot-slide', viewport: null },
  controller: { participantId: null, leaseId: null, controlEpoch: 0, expiresAt: null },
  participants: [],
  pendingQuestions: [],
  activePins: [],
  teacherPointer: null,
  teachingAnnotations: [],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/admin/classroom']}>
      <ThemeProvider><ClassroomTeacherPage /></ThemeProvider>
    </MemoryRouter>,
  )
}

describe('Classroom teacher fresh-tab resume', () => {
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
    classroomApi.classroomSetupFolders.mockResolvedValue({ items: [], nextCursor: null })
    classroomApi.listClassrooms.mockResolvedValue({ sessions: [discovered] })
    classroomApi.teacherState.mockResolvedValue(teacherSnapshot)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('resumes only an authenticated discovered session with its immutable snapshot', async () => {
    sessionStorage.setItem('pathlab-active-classroom:v1', JSON.stringify({
      id: 'foreign-or-stale-session',
      joinCode: 'FORGED',
      slides: [{ id: 'fabricated-current-library-slide' }],
    }))
    renderPage()

    await userEvent.click(await screen.findByRole('button', {
      name: `Resume classroom ${discovered.joinCode}`,
    }))

    expect(await screen.findByRole('heading', { name: 'Invite students to review' })).toBeInTheDocument()
    expect(screen.getByText(/The protected link opens all\s+1\s+slides/)).toBeInTheDocument()
    expect(classroomApi.teacherState).toHaveBeenCalledWith(discovered.id)
    expect(classroomApi.createClassroom).not.toHaveBeenCalled()
    await waitFor(() => {
      const cached = JSON.parse(sessionStorage.getItem('pathlab-active-classroom:v1') ?? '{}')
      expect(cached.slides).toEqual(immutableSlides)
      expect(cached.stateVersion).toBe(7)
    })
  })

  it('does not trust an expired or foreign cached session that discovery omits', async () => {
    sessionStorage.setItem('pathlab-active-classroom:v1', JSON.stringify({
      id: 'foreign-or-expired',
      joinCode: 'FORGED',
      slides: immutableSlides,
    }))
    classroomApi.listClassrooms.mockResolvedValue({ sessions: [] })
    renderPage()

    expect(await screen.findByText('Create a library folder before starting a classroom.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Resume classroom/i })).not.toBeInTheDocument()
    expect(classroomApi.teacherState).not.toHaveBeenCalled()
    expect(classroomApi.createClassroom).not.toHaveBeenCalled()
  })

  it('removes a session that ends between discovery and resume', async () => {
    classroomApi.teacherState.mockRejectedValue(new ApiError(404, 'CLASSROOM_NOT_FOUND'))
    renderPage()

    await userEvent.click(await screen.findByRole('button', {
      name: `Resume classroom ${discovered.joinCode}`,
    }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'That classroom has ended or expired and cannot be resumed.',
    )
    expect(screen.queryByRole('button', {
      name: `Resume classroom ${discovered.joinCode}`,
    })).not.toBeInTheDocument()
    expect(classroomApi.createClassroom).not.toHaveBeenCalled()
  })
})
