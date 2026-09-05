import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ClassroomInvitePage } from '../pages/ClassroomInvitePage'
import { ClassroomTeacherPage } from '../pages/ClassroomTeacherPage'
import { ThemeProvider } from '../theme/ThemeProvider'

const classroomApi = vi.hoisted(() => ({
  classroomInviteState: vi.fn(),
  classroomInvitePhase: vi.fn(),
  joinLiveClassroom: vi.fn(),
  classroomSetupFolders: vi.fn(),
  listClassrooms: vi.fn(),
  teacherState: vi.fn(),
  unlockClassroomInvite: vi.fn(),
}))

vi.mock('../classroom/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../classroom/api')>(),
  ...classroomApi,
}))

vi.mock('../components/OpenSeadragonViewer', () => ({
  OpenSeadragonViewer: ({ tileSource }: { tileSource: string }) => <div data-testid="slide-viewer">{tileSource}</div>,
}))

const slide = {
  id: 'slide-1', position: 0, displayName: 'Teaching slide', assetVersion: 'v1',
  tileSource: '/tiles/public/v1/slide.dzi', width: 4000, height: 3000,
  tileSize: 512, format: 'jpg', folderPath: ['Teaching cases'],
}

describe('smart Classroom invite', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    })))
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
    classroomApi.classroomSetupFolders.mockResolvedValue({ items: [], nextCursor: null })
    classroomApi.listClassrooms.mockResolvedValue({
      sessions: [{
        id: 'session-1', publicId: 'opaque-public-id', joinCode: 'ABC234DEFG',
        phase: 'preview', reviewExpiresAt: '2026-08-20T00:00:00Z',
      }],
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('shows a QR URL without embedding the separate access code', async () => {
    sessionStorage.setItem('pathlab-active-classroom:v1', JSON.stringify({
      id: 'session-1', publicId: 'opaque-public-id', joinCode: 'ABC234DEFG',
      phase: 'preview', reviewExpiresAt: '2026-08-20T00:00:00Z', stateVersion: 1,
      slides: [slide],
    }))
    classroomApi.teacherState.mockResolvedValue({
      session: { id: 'session-1', status: 'active', phase: 'preview', publicId: 'opaque-public-id', joinCode: 'ABC234DEFG', reviewExpiresAt: '2026-08-20T00:00:00Z' },
      presenter: { sequence: 0, slideId: 'slide-1', viewport: null }, stateVersion: 1,
      slides: [slide], participantCount: 0, rosterVersion: 0,
      controller: { participantId: null, leaseId: null, controlEpoch: 0, expiresAt: null },
      participants: [], pendingQuestions: [], activePins: [], teacherPointer: null, teachingAnnotations: [],
    })

    render(<MemoryRouter><ThemeProvider><ClassroomTeacherPage /></ThemeProvider></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Resume classroom ABC234DEFG' }))
    await userEvent.click(await screen.findByRole('button', { name: /Access code.*Display QR and link/i }))
    const link = screen.getByRole('link', { name: /classroom\/invite\/opaque-public-id/i })
    expect(link).toHaveAttribute('href', 'http://localhost:3000/classroom/invite/opaque-public-id')
    expect(link.getAttribute('href')).not.toContain('ABC234DEFG')
    expect(screen.getByLabelText('Classroom invite QR code')).toBeInTheDocument()
    expect(screen.getAllByText('ABC234DEFG')).toHaveLength(2)
  })

  it('requires code unlock and an explicit click before live participation', async () => {
    classroomApi.classroomInviteState
      .mockRejectedValueOnce(new Error('locked'))
      .mockResolvedValue({
        sessionId: 'session-1', publicId: 'opaque-public-id', phase: 'live',
        reviewExpiresAt: '2026-08-20T00:00:00Z', participant: { id: 'p1', alias: 'MINT-12' },
        csrfToken: 'participant-token-long-enough', slides: [slide],
      })
    classroomApi.unlockClassroomInvite.mockResolvedValue({ sessionId: 'session-1', csrfToken: 'participant-token-long-enough', phase: 'live' })
    classroomApi.joinLiveClassroom.mockResolvedValue(undefined)

    render(<MemoryRouter initialEntries={['/classroom/invite/opaque-public-id']}>
      <ThemeProvider><Routes>
        <Route path="/classroom/invite/:publicId" element={<ClassroomInvitePage />} />
        <Route path="/classroom/:sessionId" element={<p>Live classroom opened</p>} />
      </Routes></ThemeProvider>
    </MemoryRouter>)
    await userEvent.type(screen.getByLabelText('Access code'), 'ABC234DEFG')
    await userEvent.type(screen.getByLabelText('Name (optional)'), 'Student')
    await userEvent.click(screen.getByRole('button', { name: 'Open slide review' }))
    expect(await screen.findByTestId('slide-viewer')).toHaveTextContent(
      '/tiles/public/v1/slide.dzi?classroom=session-1',
    )
    expect(classroomApi.unlockClassroomInvite).toHaveBeenCalledWith('opaque-public-id', 'ABC234DEFG', 'Student')
    expect(classroomApi.joinLiveClassroom).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Join live class' }))
    await waitFor(() => expect(classroomApi.joinLiveClassroom).toHaveBeenCalledWith('session-1', 'participant-token-long-enough'))
    expect(await screen.findByText('Live classroom opened')).toBeInTheDocument()
  })
})
