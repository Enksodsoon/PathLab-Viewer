import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { classroomGuideDelay } from '../classroom/reconnect'
import { ClassroomStudentPage } from '../pages/ClassroomStudentPage'
import { ThemeProvider } from '../theme/ThemeProvider'

const classroomApi = vi.hoisted(() => ({ studentState: vi.fn(), joinClassroom: vi.fn(), publishPin: vi.fn(), askQuestion: vi.fn() }))
const notebook = vi.hoisted(() => ({
  listEntries: vi.fn(),
  storageCapability: vi.fn(), saveEntry: vi.fn(), notebookFile: vi.fn(), notebookHtml: vi.fn(), clearDrawing: vi.fn(),
}))

vi.mock('../classroom/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../classroom/api')>(),
  ...classroomApi,
}))
vi.mock('../classroom/notebook', async (importOriginal) => ({
  ...await importOriginal<typeof import('../classroom/notebook')>(),
  ...notebook,
}))
vi.mock('../components/OpenSeadragonViewer', async () => {
  const { useEffect } = await import('react')
  return { OpenSeadragonViewer: ({ onViewerAttach }: { onViewerAttach: (viewer: unknown) => unknown }) => {
    useEffect(() => {
      const viewer = { container: document.createElement('div'), canvas: document.createElement('div'),
        addHandler: vi.fn(), removeHandler: vi.fn(), setMouseNavEnabled: vi.fn(),
        viewport: { getCenter: () => ({ x: 0.5, y: 0.5 }), viewportToImageCoordinates: () => ({ x: 50, y: 50 }), getZoom: () => 1, pointFromPixel: () => ({ x: 50, y: 50 }), pixelFromPoint: () => ({ x: 50, y: 50 }) },
        world: { getItemAt: () => ({ source: { dimensions: { x: 100, y: 100 } } }) } }
      return onViewerAttach(viewer) as (() => void) | undefined
    }, [onViewerAttach])
    return <div />
  } }
})
vi.mock('../classroom/presenterViewport', async (original) => ({ ...await original<typeof import('../classroom/presenterViewport')>(), applyPresenterViewport: vi.fn() }))
vi.mock('../classroom/ClassroomPinOverlays', () => ({ ClassroomPinOverlays: ({ pins }: { pins: Array<{ x: number }> }) => <p data-testid="pin-x">{pins[0]?.x ?? 'none'}</p> }))
vi.mock('../classroom/ClassroomQuestionComposer', () => ({ ClassroomQuestionComposer: ({ busy, onSubmit, onQuestion }: { busy: boolean; onSubmit: () => void; onQuestion: (text: string) => void }) => <><input aria-label="Synthetic question" onChange={(event) => onQuestion(event.target.value)} /><button disabled={busy} onClick={onSubmit}>Synthetic send</button></> }))
vi.mock('../classroom/ClassroomTeachingOverlays', () => ({ ClassroomTeachingOverlays: () => null }))
vi.mock('../classroom/StudentDrawingOverlay', async () => {
  const { forwardRef, useImperativeHandle, useState } = await import('react')
  return { StudentDrawingOverlay: forwardRef(({ onDone }: { onDone: () => void }, ref) => {
    const [marks, setMarks] = useState(0)
    useImperativeHandle(ref, () => ({ captureCanvas: () => undefined, hasDrawing: () => marks > 0, clear: () => setMarks(0) }))
    return <><p data-testid="drawing-marks">{marks}</p><button onClick={() => setMarks(1)}>Synthetic stroke</button><button onClick={onDone}>Done synthetic drawing</button></>
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

describe('student pin recovery and slide drawing scope', () => {
  beforeEach(() => {
    EventSourceStub.current = null
    vi.stubGlobal('EventSource', EventSourceStub)
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
    classroomApi.studentState.mockResolvedValue({ ...state, activePin: { slideId: 'slide-1', x: .1, y: .1, zoom: 1 } })
    notebook.listEntries.mockResolvedValue([])
    notebook.storageCapability.mockResolvedValue({ indexedDb: true })
  })
  afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.clearAllMocks(); vi.unstubAllGlobals() })
  async function mount() {
    render(<MemoryRouter initialEntries={['/classroom/session-1']}><ThemeProvider><Routes>
      <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
    </Routes></ThemeProvider></MemoryRouter>)
    await screen.findByText('AMBER-00000001')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Ask at visible centre (P)' })).toBeEnabled())
  }
  it('restores the previous marker after publishing rejects and provides a retry', async () => {
    classroomApi.publishPin.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(undefined)
    await mount()
    fireEvent.click(screen.getByRole('button', { name: 'Ask at visible centre (P)' }))
    expect(await screen.findByText(/The teacher could not receive this pin/)).toBeVisible()
    expect(screen.getByTestId('pin-x')).toHaveTextContent('0.1')
    fireEvent.click(screen.getByRole('button', { name: 'Retry publishing pin' }))
    await waitFor(() => expect(classroomApi.publishPin).toHaveBeenCalledTimes(2))
    expect(screen.getByTestId('pin-x')).not.toHaveTextContent('0.1')
  })
  it('does not erase a newer pin when an older publish fails late', async () => {
    let rejectOld: ((error: Error) => void) | undefined
    classroomApi.publishPin.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectOld = reject })).mockResolvedValueOnce(undefined)
    await mount()
    fireEvent.click(screen.getByRole('button', { name: 'Ask at visible centre (P)' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask at visible centre (P)' }))
    await act(async () => { rejectOld?.(new Error('old request failed')) })
    expect(screen.getByTestId('pin-x')).not.toHaveTextContent('0.1')
    expect(screen.queryByRole('button', { name: 'Retry publishing pin' })).not.toBeInTheDocument()
  })
  it('scopes private strokes to the slide on a guided SSE transition and retains text notes', async () => {
    await mount()
    const note = screen.getByPlaceholderText('Write a private note…')
    fireEvent.change(note, { target: { value: 'Keep my text note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Draw on slide' }))
    fireEvent.click(screen.getByRole('button', { name: 'Synthetic stroke' }))
    fireEvent.click(screen.getByRole('button', { name: 'Done synthetic drawing' }))
    expect(screen.getByTestId('drawing-marks')).toHaveTextContent('1')
    vi.useFakeTimers()
    act(() => EventSourceStub.current?.emit('stream-ready', { hubEpoch: 'epoch', eventSequence: 0, stateVersion: 4 }))
    act(() => EventSourceStub.current?.emit('presenter', { hubEpoch: 'epoch', eventSequence: 1, presenterSequence: 1, slideId: 'slide-2', viewport: { x: .5, y: .5, zoom: 1, zoomSpace: 'viewport' } }))
    act(() => { vi.advanceTimersByTime(classroomGuideDelay('participant-1', 'slide-2')) })
    expect(screen.getByRole('button', { name: '2. Second slide' })).toBeVisible()
    expect(screen.getByTestId('drawing-marks')).toHaveTextContent('0')
    expect(screen.getByText('Unsaved drawing cleared when the slide changed. Your text note and saved notebook entries are kept.')).toBeVisible()
    expect(note).toHaveValue('Keep my text note')
  })
  it('blocks sending the prior coordinates while a replacement pin awaits publication', async () => {
    let resolvePin: (() => void) | undefined
    classroomApi.publishPin.mockImplementationOnce(() => new Promise<void>((resolve) => { resolvePin = resolve }))
    await mount()
    fireEvent.change(screen.getByLabelText('Synthetic question'), { target: { value: 'Question at new point' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask at visible centre (P)' }))
    expect(screen.getByRole('button', { name: 'Synthetic send' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Synthetic send' }))
    expect(classroomApi.askQuestion).not.toHaveBeenCalled()
    await act(async () => { resolvePin?.() })
    expect(screen.getByRole('button', { name: 'Synthetic send' })).toBeEnabled()
  })

})
