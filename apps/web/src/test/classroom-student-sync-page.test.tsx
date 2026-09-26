import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ClassroomStudentPage } from '../pages/ClassroomStudentPage'
import { classroomGuideDelay } from '../classroom/reconnect'
import { ThemeProvider } from '../theme/ThemeProvider'

const teachingOverlay = vi.hoisted(() => ({ setPointer: vi.fn() }))
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

vi.mock('../classroom/ClassroomTeachingOverlays', async () => {
  const React = await import('react')
  return { ClassroomTeachingOverlays: React.forwardRef((_, ref) => {
    React.useImperativeHandle(ref, () => teachingOverlay)
    return <div data-testid="teaching-overlay" />
  }) }
})

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

  it('returns to joining when access is explicitly revoked', async () => {
    render(<MemoryRouter initialEntries={['/classroom/session-1']}>
      <ThemeProvider><Routes>
        <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
        <Route path="/classroom" element={<p>Join a current classroom</p>} />
        <Route path="/classroom/invite/:publicId" element={<p>Independent review</p>} />
      </Routes></ThemeProvider>
    </MemoryRouter>)
    expect(await screen.findByText('AMBER-00000001')).toBeVisible()
    await waitFor(() => expect(EventSourceStub.current).not.toBeNull())
    act(() => EventSourceStub.current?.emit('stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4,
    }))
    act(() => EventSourceStub.current?.emit('session-ended', {
      hubEpoch: 'epoch-a', eventSequence: 1, stateVersion: 5, phase: 'revoked',
    }))
    expect(await screen.findByText('Join a current classroom')).toBeVisible()
    expect(screen.queryByText('Independent review')).not.toBeInTheDocument()
    expect(classroomApi.studentState).toHaveBeenCalledTimes(1)
  })

  it('buffers bounded continuous ephemeral traffic without starving the gap snapshot', async () => {
    render(<MemoryRouter initialEntries={['/classroom/session-1']}>
      <ThemeProvider><Routes>
        <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
      </Routes></ThemeProvider>
    </MemoryRouter>)
    expect(await screen.findByText('AMBER-00000001')).toBeVisible()
    await waitFor(() => expect(EventSourceStub.current).not.toBeNull())
    act(() => EventSourceStub.current?.emit('stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4,
    }))
    let finish!: (value: typeof state) => void
    classroomApi.studentState.mockImplementationOnce(() => new Promise<typeof state>((resolve) => { finish = resolve }))
    classroomApi.studentState.mockResolvedValue({
      ...state, stateVersion: 5, presenter: { sequence: 2, slideId: 'slide-2', viewport: null },
    })
    act(() => EventSourceStub.current?.emit('control', {
      hubEpoch: 'epoch-a', eventSequence: 2, stateVersion: 5,
    }))
    await waitFor(() => expect(classroomApi.studentState).toHaveBeenCalledTimes(2))
    vi.useFakeTimers()
    act(() => EventSourceStub.current?.emit('presenter', {
      hubEpoch: 'epoch-a', eventSequence: 3, presenterSequence: 2,
      slideId: 'slide-2', viewport: { x: .7, y: .3, zoom: 2, zoomSpace: 'image' },
    }))
    act(() => {
      for (let sequence = 4; sequence <= 1003; sequence += 1) {
        EventSourceStub.current?.emit('pointer', {
          hubEpoch: 'epoch-a', eventSequence: sequence, slideId: 'slide-2',
          style: 'green-arrow', x: sequence / 2000, y: .3,
        })
      }
      vi.advanceTimersByTime(5000)
    })
    expect(screen.getByRole('button', { name: '1. Teaching slide' })).toBeVisible()
    await act(async () => { finish({ ...state, stateVersion: 5 }); await Promise.resolve() })
    expect(classroomApi.studentState).toHaveBeenCalledTimes(2)
    expect(teachingOverlay.setPointer).toHaveBeenLastCalledWith(expect.objectContaining({
      slideId: 'slide-2', x: 1003 / 2000, y: .3,
    }))
    act(() => { vi.advanceTimersByTime(5000) })
    vi.useRealTimers()
    expect(await screen.findByRole('button', { name: '2. Second slide' })).toBeVisible()
  })

  it('does not replay an older buffered presenter over a newer authoritative snapshot', async () => {
    render(<MemoryRouter initialEntries={['/classroom/session-1']}>
      <ThemeProvider><Routes>
        <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
      </Routes></ThemeProvider>
    </MemoryRouter>)
    expect(await screen.findByText('AMBER-00000001')).toBeVisible()
    await waitFor(() => expect(EventSourceStub.current).not.toBeNull())
    act(() => EventSourceStub.current?.emit('stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 0, stateVersion: 4,
    }))
    let finish!: (value: typeof state) => void
    classroomApi.studentState.mockImplementationOnce(() => new Promise<typeof state>((resolve) => { finish = resolve }))
    act(() => EventSourceStub.current?.emit('control', {
      hubEpoch: 'epoch-a', eventSequence: 2, stateVersion: 5,
    }))
    await waitFor(() => expect(classroomApi.studentState).toHaveBeenCalledTimes(2))
    act(() => EventSourceStub.current?.emit('presenter', {
      hubEpoch: 'epoch-a', eventSequence: 3, presenterSequence: 2,
      slideId: 'slide-2', viewport: { x: .7, y: .3, zoom: 2, zoomSpace: 'image' },
    }))
    vi.useFakeTimers()
    await act(async () => {
      finish({ ...state, stateVersion: 5, presenter: { sequence: 3, slideId: 'slide-1', viewport: null } })
      await Promise.resolve()
    })
    act(() => { vi.advanceTimersByTime(5000) })
    vi.useRealTimers()
    expect(screen.getByRole('button', { name: '1. Teaching slide' })).toBeVisible()
    expect(classroomApi.studentState).toHaveBeenCalledTimes(2)
  })

  it('clears buffered live fields when terminal access arrives before the snapshot acknowledgment', async () => {
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
    let finish!: (value: typeof state) => void
    classroomApi.studentState.mockImplementationOnce(() => new Promise<typeof state>((resolve) => { finish = resolve }))
    act(() => EventSourceStub.current?.emit('control', {
      hubEpoch: 'epoch-a', eventSequence: 2, stateVersion: 5,
    }))
    await waitFor(() => expect(classroomApi.studentState).toHaveBeenCalledTimes(2))
    act(() => EventSourceStub.current?.emit('presenter', {
      hubEpoch: 'epoch-a', eventSequence: 3, presenterSequence: 2,
      slideId: 'slide-2', viewport: { x: .7, y: .3, zoom: 2, zoomSpace: 'image' },
    }))
    act(() => EventSourceStub.current?.emit('session-ended', {
      hubEpoch: 'epoch-a', eventSequence: 4, stateVersion: 6, phase: 'review',
    }))
    expect(await screen.findByText('Independent review')).toBeVisible()
    await act(async () => { finish({ ...state, stateVersion: 5 }); await Promise.resolve() })
    expect(screen.getByText('Independent review')).toBeVisible()
    expect(screen.queryByRole('button', { name: '2. Second slide' })).not.toBeInTheDocument()
    expect(classroomApi.studentState).toHaveBeenCalledTimes(2)
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
  it('fetches a new snapshot when reconnect ready reports a missed teaching mutation', async () => {
    render(<MemoryRouter initialEntries={['/classroom/session-1']}>
      <ThemeProvider><Routes>
        <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
      </Routes></ThemeProvider>
    </MemoryRouter>)
    await screen.findByText('AMBER-00000001')
    await waitFor(() => expect(EventSourceStub.current).not.toBeNull())
    act(() => EventSourceStub.current?.emit('stream-ready', {
      hubEpoch: 'epoch', eventSequence: 10, stateVersion: 4,
    }))
    classroomApi.studentState.mockResolvedValue({ ...state, stateVersion: 5 })
    act(() => EventSourceStub.current?.emit('stream-ready', {
      hubEpoch: 'epoch', eventSequence: 11, stateVersion: 5,
    }))
    await waitFor(() => expect(classroomApi.studentState).toHaveBeenCalledTimes(2))
  })

})
