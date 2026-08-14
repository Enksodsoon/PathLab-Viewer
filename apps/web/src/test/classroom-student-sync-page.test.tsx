import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ClassroomStudentPage } from '../pages/ClassroomStudentPage'
import { classroomGuideDelay } from '../classroom/reconnect'
import { ThemeProvider } from '../theme/ThemeProvider'

const classroomApi = vi.hoisted(() => ({ studentState: vi.fn() }))
const notebook = vi.hoisted(() => ({
  listEntries: vi.fn(),
  storageCapability: vi.fn(),
}))

vi.mock('../classroom/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../classroom/api')>(),
  ...classroomApi,
}))
vi.mock('../classroom/notebook', async (importOriginal) => ({
  ...await importOriginal<typeof import('../classroom/notebook')>(),
  ...notebook,
}))
vi.mock('../components/OpenSeadragonViewer', () => ({
  OpenSeadragonViewer: () => <div data-testid="classroom-viewer" />,
}))

class EventSourceStub {
  static current: EventSourceStub | null = null
  readonly listeners = new Map<string, Array<(event: Event) => void>>()
  close = vi.fn()

  constructor(readonly url: string) {
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

const state = {
  session: { id: 'session-1', status: 'active', phase: 'live' as const, publicId: 'public-1' },
  participant: { id: 'participant-1', alias: 'AMBER-00000001' },
  csrfToken: 'participant-csrf', stateVersion: 4,
  presenter: { sequence: 0, slideId: 'slide-1', viewport: null },
  control: { isController: false, requested: false, leaseId: null, controlEpoch: 0, expiresAt: null },
  slides: [{
    id: 'slide-1', position: 0, displayName: 'Teaching slide', assetVersion: 'v1',
    tileSource: '/tiles/public/v1/slide.dzi', width: 4000, height: 3000,
    tileSize: 512, format: 'jpg', folderPath: ['Teaching cases'],
  }, {
    id: 'slide-2', position: 1, displayName: 'Second slide', assetVersion: 'v1',
    tileSource: '/tiles/public/v1/second.dzi', width: 4000, height: 3000,
    tileSize: 512, format: 'jpg', folderPath: ['Teaching cases'],
  }],
  pendingQuestionIds: [], activePin: null, teacherPointer: null, teachingAnnotations: [],
}

describe('student initial snapshot stream sync', () => {
  beforeEach(() => {
    EventSourceStub.current = null
    vi.stubGlobal('EventSource', EventSourceStub)
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    })))
    classroomApi.studentState.mockResolvedValue(state)
    notebook.listEntries.mockResolvedValue([])
    notebook.storageCapability.mockResolvedValue({ indexedDb: false })
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('keeps one matching initial snapshot and resynchronizes a later critical gap', async () => {
    render(<MemoryRouter initialEntries={['/classroom/session-1']}>
      <ThemeProvider><Routes>
        <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
      </Routes></ThemeProvider>
    </MemoryRouter>)

    expect(await screen.findByText('AMBER-00000001')).toBeVisible()
    await waitFor(() => expect(EventSourceStub.current).not.toBeNull())
    expect(classroomApi.studentState).toHaveBeenCalledTimes(1)

    act(() => EventSourceStub.current?.emit('stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4,
    }))
    await act(async () => { await Promise.resolve() })
    expect(classroomApi.studentState).toHaveBeenCalledTimes(1)

    classroomApi.studentState.mockResolvedValue({ ...state, stateVersion: 5 })
    act(() => EventSourceStub.current?.emit('control', {
      hubEpoch: 'epoch-a', eventSequence: 2, stateVersion: 5,
    }))
    await waitFor(() => expect(classroomApi.studentState).toHaveBeenCalledTimes(2))
  })

  it('applies an authoritative session end without requesting an unavailable live snapshot', async () => {
    render(<MemoryRouter initialEntries={['/classroom/session-1']}>
      <ThemeProvider><Routes>
        <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
        <Route path="/classroom/invite/:publicId" element={<p>Independent review</p>} />
      </Routes></ThemeProvider>
    </MemoryRouter>)

    expect(await screen.findByText('AMBER-00000001')).toBeVisible()
    await waitFor(() => expect(EventSourceStub.current).not.toBeNull())
    act(() => EventSourceStub.current?.emit('stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4,
    }))
    act(() => EventSourceStub.current?.emit('session-ended', {
      hubEpoch: 'epoch-a', eventSequence: 1, stateVersion: 5,
    }))

    expect(await screen.findByText('Independent review')).toBeVisible()
    expect(classroomApi.studentState).toHaveBeenCalledTimes(1)
  })

  it('keeps the first guide deadline when updates continue for the same target slide', async () => {
    render(<MemoryRouter initialEntries={['/classroom/session-1']}>
      <ThemeProvider><Routes>
        <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
      </Routes></ThemeProvider>
    </MemoryRouter>)

    expect(await screen.findByRole('button', { name: '1. Teaching slide' })).toBeVisible()
    await waitFor(() => expect(EventSourceStub.current).not.toBeNull())
    act(() => EventSourceStub.current?.emit('stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4,
    }))

    const delay = classroomGuideDelay('participant-1', 'slide-2')
    expect(delay).toBeGreaterThan(1)
    const firstWindow = Math.floor(delay / 2)
    vi.useFakeTimers()
    act(() => EventSourceStub.current?.emit('presenter', {
      hubEpoch: 'epoch-a', eventSequence: 1, presenterSequence: 1,
      slideId: 'slide-2', viewport: { x: 0.5, y: 0.5, zoom: 1, zoomSpace: 'viewport' },
    }))
    act(() => { vi.advanceTimersByTime(firstWindow) })
    act(() => EventSourceStub.current?.emit('presenter', {
      hubEpoch: 'epoch-a', eventSequence: 2, presenterSequence: 2,
      slideId: 'slide-2', viewport: { x: 0.6, y: 0.5, zoom: 1, zoomSpace: 'viewport' },
    }))
    act(() => { vi.advanceTimersByTime(delay - firstWindow) })

    expect(screen.getByRole('button', { name: '2. Second slide' })).toBeVisible()
  })
})
