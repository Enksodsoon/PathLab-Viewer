import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ClassroomTeacherPage } from '../pages/ClassroomTeacherPage'
import { ThemeProvider } from '../theme/ThemeProvider'

const classroomApi = vi.hoisted(() => ({
  classroomSetupFolders: vi.fn(),
  finishLiveClassroom: vi.fn(),
  listClassrooms: vi.fn(),
  teacherParticipants: vi.fn(),
  teacherState: vi.fn(),
}))

vi.mock('../classroom/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../classroom/api')>(),
  ...classroomApi,
}))
vi.mock('../components/OpenSeadragonViewer', () => ({
  OpenSeadragonViewer: () => <div data-testid="classroom-viewer" />,
}))

class EventSourceStub {
  static current: EventSourceStub | null = null
  readonly listeners = new Map<string, Array<(event: Event) => void>>()
  close = vi.fn()

  constructor() {
    EventSourceStub.current = this
  }

  addEventListener(type: string, listener: (event: Event) => void) {
    const listeners = this.listeners.get(type) ?? []
    listeners.push(listener)
    this.listeners.set(type, listeners)
  }

  emit(type: string, payload: Record<string, unknown>) {
    const event = new MessageEvent(type, { data: JSON.stringify(payload) })
    for (const listener of this.listeners.get(type) ?? []) listener(event)
  }
}

const slide = {
  id: 'slide-1', position: 0, displayName: 'Teaching slide', assetVersion: 'v1',
  tileSource: '/tiles/public/v1/slide.dzi', width: 4000, height: 3000,
  tileSize: 512, format: 'jpg', folderPath: ['Teaching cases'],
}

function participant(index: number) {
  return {
    id: `participant-${index}`,
    alias: `AMBER-${String(index).padStart(8, '0')}`,
    displayName: index === 149 ? 'Renal learner' : null,
    status: 'connected' as const,
    controlRequested: false,
    controlRequestedAt: null,
  }
}

function normalRosterCallCount() {
  return classroomApi.teacherParticipants.mock.calls.filter(([, query]) => !query.requested).length
}

async function renderResumedTeacher() {
  render(<MemoryRouter><ThemeProvider><ClassroomTeacherPage /></ThemeProvider></MemoryRouter>)
  await userEvent.click(await screen.findByRole('button', { name: 'Resume classroom ABC234DEFG' }))
}

describe('teacher paginated roster', () => {
  beforeEach(() => {
    EventSourceStub.current = null
    sessionStorage.clear()
    sessionStorage.setItem('pathlab-active-classroom:v1', JSON.stringify({
      id: 'session-1', publicId: 'public-1', joinCode: 'ABC234DEFG', phase: 'live',
      reviewExpiresAt: '2026-08-20T00:00:00Z', stateVersion: 4, slides: [slide],
    }))
    vi.stubGlobal('EventSource', EventSourceStub)
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    })))
    classroomApi.classroomSetupFolders.mockResolvedValue({ items: [], nextCursor: null })
    classroomApi.listClassrooms.mockResolvedValue({ sessions: [{
      id: 'session-1', publicId: 'public-1', joinCode: 'ABC234DEFG', phase: 'live',
      reviewExpiresAt: '2026-08-20T00:00:00Z',
    }] })
    classroomApi.teacherState.mockResolvedValue({
      session: { id: 'session-1', status: 'active', phase: 'live', publicId: 'public-1', joinCode: 'ABC234DEFG', reviewExpiresAt: '2026-08-20T00:00:00Z' },
      presenter: { sequence: 0, slideId: 'slide-1', viewport: null }, stateVersion: 4,
      slides: [slide],
      participantCount: 150, rosterVersion: 7,
      controller: { participantId: null, leaseId: null, controlEpoch: 0, expiresAt: null },
      participants: [], pendingQuestions: [], activePins: [], teacherPointer: null,
      teachingAnnotations: [],
    })
    classroomApi.teacherParticipants.mockImplementation(async (_sessionId: string, query: {
      after?: string | null; q?: string; requested?: boolean
    }) => {
      if (query.requested) {
        return { items: [], total: 0, nextCursor: null, rosterVersion: 7 }
      }
      if (query.q === 'renal') {
        return { items: [participant(149)], total: 1, nextCursor: null, rosterVersion: 7 }
      }
      if (query.after) {
        return {
          items: Array.from({ length: 50 }, (_, index) => participant(index + 100)),
          total: 150,
          nextCursor: null,
          rosterVersion: 7,
        }
      }
      return {
        items: Array.from({ length: 100 }, (_, index) => participant(index)),
        total: 150,
        nextCursor: 'AMBER-00000099',
        rosterVersion: 7,
      }
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('retires live controls after a terminal event from another admin despite an event gap', async () => {
    await renderResumedTeacher()
    await waitFor(() => expect(EventSourceStub.current).not.toBeNull())
    const stream = EventSourceStub.current!
    act(() => stream.emit('stream-ready', { hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4 }))
    const requests = classroomApi.teacherState.mock.calls.length
    act(() => stream.emit('session-ended', { hubEpoch: 'epoch-a', eventSequence: 3, stateVersion: 5 }))
    expect(await screen.findByText('This live classroom has ended or been revoked. Open a current classroom to continue.')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'End class' })).not.toBeInTheDocument()
    expect(sessionStorage.getItem('pathlab-active-classroom:v1')).toBeNull()
    expect(stream.close).toHaveBeenCalled()
    expect(classroomApi.teacherState).toHaveBeenCalledTimes(requests)
    const previous = await classroomApi.teacherState.mock.results[0].value
    classroomApi.teacherState.mockResolvedValue({ ...previous, session: { ...previous.session, phase: 'review', status: 'ended' }, stateVersion: 5 })
    await userEvent.click(screen.getByRole('button', { name: 'Resume classroom ABC234DEFG' }))
    expect(await screen.findByText('Review remains open')).toBeVisible()
  })

  it('renders one bounded page, loads the next page, and searches server-side', async () => {
    await renderResumedTeacher()

    const roster = await screen.findByRole('list', { name: 'Student roster' })
    await waitFor(() => expect(within(roster).getAllByRole('listitem')).toHaveLength(100))
    expect(screen.getByLabelText('150 students')).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'Load more (100 of 150)' }))
    await waitFor(() => expect(within(roster).getAllByRole('listitem')).toHaveLength(150))
    expect(classroomApi.teacherParticipants).toHaveBeenCalledWith('session-1', {
      after: 'AMBER-00000099', limit: 100, q: '',
    })

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search students' }), 'renal')
    await waitFor(() => expect(within(roster).getAllByRole('listitem')).toHaveLength(1))
    expect(screen.getByText('Renal learner · connected')).toBeVisible()
    expect(classroomApi.teacherParticipants).toHaveBeenCalledWith('session-1', {
      limit: 100, q: 'renal',
    })
  })

  it('reconciles the roster after reconnect and after a gapped roster signal', async () => {
    await renderResumedTeacher()

    await screen.findByRole('list', { name: 'Student roster' })
    await waitFor(() => expect(EventSourceStub.current).not.toBeNull())
    await waitFor(() => expect(normalRosterCallCount()).toBe(1))
    act(() => EventSourceStub.current?.emit('stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4,
    }))
    act(() => EventSourceStub.current?.emit('stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4,
    }))
    await waitFor(() => expect(normalRosterCallCount()).toBe(2))

    act(() => EventSourceStub.current?.emit('roster-changed', {
      hubEpoch: 'epoch-a', eventSequence: 2, rosterVersion: 8,
    }))
    await waitFor(() => expect(normalRosterCallCount()).toBe(3), {
      timeout: 1500,
    })
  })

  it('keeps multiple off-page control requesters distinctly visible and actionable', async () => {
    await renderResumedTeacher()

    await screen.findByRole('list', { name: 'Student roster' })
    await waitFor(() => expect(EventSourceStub.current).not.toBeNull())
    act(() => EventSourceStub.current?.emit('stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4,
    }))
    classroomApi.teacherState.mockResolvedValue({
      session: { id: 'session-1', status: 'active', phase: 'live', publicId: 'public-1', joinCode: 'ABC234DEFG', reviewExpiresAt: '2026-08-20T00:00:00Z' },
      presenter: { sequence: 0, slideId: 'slide-1', viewport: null }, stateVersion: 5,
      slides: [slide],
      participantCount: 151, rosterVersion: 8,
      controller: { participantId: null, leaseId: null, controlEpoch: 0, expiresAt: null },
      participants: [], pendingQuestions: [], activePins: [], teacherPointer: null,
      teachingAnnotations: [],
    })
    act(() => EventSourceStub.current?.emit('roster-changed', {
      hubEpoch: 'epoch-a', eventSequence: 1, rosterVersion: 8,
    }))
    act(() => EventSourceStub.current?.emit('control-requested', {
      hubEpoch: 'epoch-a', eventSequence: 2, stateVersion: 5,
      participantId: 'participant-1000',
      participant: {
        id: 'participant-1000', alias: 'AMBER-00001000', displayName: 'Learner one',
        status: 'connected', controlRequested: true, controlRequestedAt: 1000,
      },
    }))
    act(() => EventSourceStub.current?.emit('control-requested', {
      hubEpoch: 'epoch-a', eventSequence: 3, stateVersion: 5,
      participantId: 'participant-1001',
      participant: {
        id: 'participant-1001', alias: 'AMBER-00001001', displayName: 'Learner two',
        status: 'connected', controlRequested: true, controlRequestedAt: 1001,
      },
    }))

    expect(await screen.findByRole('button', { name: 'Give control to AMBER-00001000' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Give control to AMBER-00001001' })).toBeVisible()
  })

  it('restores bounded off-page pending requests after teacher reload', async () => {
    classroomApi.teacherParticipants.mockImplementation(async (_sessionId: string, query: {
      after?: string | null; requested?: boolean
    }) => query.requested ? {
      items: query.after
        ? [{ ...participant(1100), alias: 'AMBER-00001100', controlRequested: true }]
        : Array.from({ length: 100 }, (_, index) => ({
            ...participant(index + 1000), controlRequested: true,
          })),
      total: 101,
      nextCursor: query.after ? null : 'AMBER-00001099',
      rosterVersion: 7,
    } : {
      items: Array.from({ length: 100 }, (_, index) => participant(index)),
      total: 150, nextCursor: 'AMBER-00000099', rosterVersion: 7,
    })

    await renderResumedTeacher()

    expect(await screen.findByRole('button', { name: 'Give control to AMBER-00001000' })).toBeVisible()
    expect(classroomApi.teacherParticipants).toHaveBeenCalledWith('session-1', {
      limit: 100, requested: true,
    })
    await userEvent.click(screen.getByRole('button', {
      name: 'Load more control requests (100 of 101)',
    }))
    expect(await screen.findByRole('button', { name: 'Give control to AMBER-00001100' })).toBeVisible()
    expect(classroomApi.teacherParticipants).toHaveBeenCalledWith('session-1', {
      after: 'AMBER-00001099', limit: 100, requested: true,
    })
  })
  it('keeps the live class available and reports a failed end request', async () => {
    classroomApi.finishLiveClassroom.mockRejectedValueOnce(new Error('Synthetic failure'))
    await renderResumedTeacher()
    await userEvent.click(await screen.findByRole('button', { name: 'End class' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The live class could not end.')
    expect(screen.getByRole('button', { name: 'End class' })).toBeVisible()
  })

  it('retains acknowledged independent review when terminal SSE arrives before effect cleanup', async () => {
    classroomApi.finishLiveClassroom.mockResolvedValueOnce(undefined)
    await renderResumedTeacher()
    const stream = EventSourceStub.current!
    act(() => stream.emit('stream-ready', { hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4 }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'End class' }))
      await Promise.resolve()
      await Promise.resolve()
      stream.emit('session-ended', { hubEpoch: 'epoch-a', eventSequence: 1, stateVersion: 5, phase: 'review' })
    })
    expect(await screen.findByText('Review remains open')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'End class' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Revoke review access' })).toBeVisible()
  })
  it('retains independent review when another teacher ends the live phase', async () => {
    await renderResumedTeacher()
    const stream = EventSourceStub.current!
    act(() => stream.emit('stream-ready', { hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4 }))
    act(() => stream.emit('session-ended', { hubEpoch: 'epoch-a', eventSequence: 1, stateVersion: 5, phase: 'review' }))
    expect(await screen.findByText('Review remains open')).toBeVisible()
    expect(stream.close).toHaveBeenCalled()
  })

})
