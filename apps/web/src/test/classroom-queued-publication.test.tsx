import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ClassroomTeacherPage } from '../pages/ClassroomTeacherPage'
import { ClassroomStudentPage } from '../pages/ClassroomStudentPage'
import { ThemeProvider } from '../theme/ThemeProvider'

const api = vi.hoisted(() => ({
  classroomSetupFolders: vi.fn(), listClassrooms: vi.fn(), teacherParticipants: vi.fn(),
  teacherState: vi.fn(), studentState: vi.fn(), publishTeacherViewport: vi.fn(),
  publishStudentViewport: vi.fn(), publishTeacherPointer: vi.fn(), clearTeacherPointer: vi.fn(),
}))
const harness = vi.hoisted(() => ({
  handlers: new Map<string, Set<() => void>>(), canvas: null as HTMLDivElement | null,
}))
vi.mock('../classroom/api', async (original) => ({ ...await original<typeof import('../classroom/api')>(), ...api }))
vi.mock('../classroom/notebook', async (original) => ({
  ...await original<typeof import('../classroom/notebook')>(),
  listEntries: vi.fn(async () => []), storageCapability: vi.fn(async () => ({ indexedDb: false })),
}))
vi.mock('../classroom/presenterViewport', () => ({
  readPresenterViewport: () => ({ slideId: 'slide-1', x: .5, y: .5, zoom: 1, zoomSpace: 'image' }),
  applyPresenterViewport: vi.fn(),
}))
vi.mock('../classroom/ClassroomTeachingOverlays', () => ({ ClassroomTeachingOverlays: () => null }))
vi.mock('../classroom/ClassroomPinOverlays', () => ({ ClassroomPinOverlays: () => null }))
vi.mock('../components/OpenSeadragonViewer', async () => {
  const { useEffect } = await import('react')
  return { OpenSeadragonViewer: ({ onViewerAttach }: { onViewerAttach: (viewer: unknown) => unknown }) => {
    useEffect(() => {
      const canvas = document.createElement('div')
      harness.canvas = canvas
      const viewer = {
        canvas, container: document.createElement('div'), setMouseNavEnabled: vi.fn(),
        addHandler: (type: string, callback: () => void) => {
          const handlers = harness.handlers.get(type) ?? new Set()
          handlers.add(callback); harness.handlers.set(type, handlers)
        },
        removeHandler: (type: string, callback: () => void) => harness.handlers.get(type)?.delete(callback),
        world: { getItemAt: () => ({ source: { dimensions: { x: 100, y: 100 } } }) },
        viewport: { pointFromPixel: () => ({ x: 50, y: 50 }), viewportToImageCoordinates: () => ({ x: 50, y: 50 }) },
      }
      return onViewerAttach(viewer) as (() => void) | undefined
    }, [onViewerAttach])
    return <div data-testid="queued-viewer" />
  } }
})
class Source {
  static current: Source | null = null
  listeners = new Map<string, Array<(event: Event) => void>>()
  constructor() { Source.current = this }
  close = vi.fn()
  addEventListener(type: string, handler: (event: Event) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), handler])
  }
  emit(type: string, payload: Record<string, unknown>) {
    for (const handler of this.listeners.get(type) ?? []) handler(new MessageEvent(type, { data: JSON.stringify(payload) }))
  }
}
const slide = { id: 'slide-1', position: 0, displayName: 'Synthetic slide', assetVersion: 'v1', tileSource: '/synthetic.dzi', width: 100, height: 100, tileSize: 100, format: 'png', folderPath: [] }
const teacher = {
  session: { id: 'session', publicId: 'public', phase: 'live', status: 'active', joinCode: 'ABC234DEFG', reviewExpiresAt: '2027-01-01T00:00:00Z' },
  slides: [slide], stateVersion: 4, presenter: { sequence: 0, slideId: slide.id, viewport: null },
  controller: { participantId: null, leaseId: null, controlEpoch: 0, expiresAt: null },
  participants: [], participantCount: 1, rosterVersion: 1, pendingQuestions: [], activePins: [], teacherPointer: null, teachingAnnotations: [],
}
const student = { ...teacher, csrfToken: 'synthetic-csrf', participant: { id: 'learner', alias: 'SYNTHETIC' }, pendingQuestionIds: [], activePin: null,
  control: { isController: true, requested: false, leaseId: 'lease', controlEpoch: 0, expiresAt: null } }
function movement() { act(() => { for (const handler of harness.handlers.get('animation-finish') ?? []) handler() }) }
function ready() { act(() => Source.current?.emit('stream-ready', { hubEpoch: 'epoch', eventSequence: 0, stateVersion: 4 })) }
function handoff() { act(() => Source.current?.emit('control', { hubEpoch: 'epoch', eventSequence: 1, stateVersion: 5 })) }
async function mountTeacher() {
  render(<MemoryRouter><ThemeProvider><ClassroomTeacherPage /></ThemeProvider></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: 'Resume classroom ABC234DEFG' }))
  await screen.findByRole('button', { name: 'Guide students' })
  await waitFor(() => expect(harness.handlers.get('animation-finish')?.size).toBeGreaterThan(0))
  ready()
}
describe('queued classroom publication boundaries', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    harness.handlers.clear(); Source.current = null; sessionStorage.clear()
    vi.stubGlobal('EventSource', Source)
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
    api.classroomSetupFolders.mockResolvedValue({ items: [], nextCursor: null })
    api.listClassrooms.mockResolvedValue({ sessions: [teacher.session] })
    api.teacherParticipants.mockResolvedValue({ items: [], total: 0, nextCursor: null, rosterVersion: 1 })
    api.teacherState.mockResolvedValue(teacher); api.studentState.mockResolvedValue(student)
    api.publishTeacherViewport.mockResolvedValue(undefined); api.publishStudentViewport.mockResolvedValue(undefined)
    api.publishTeacherPointer.mockResolvedValue(undefined); api.clearTeacherPointer.mockResolvedValue(undefined)
  })
  afterEach(() => { cleanup(); vi.useRealTimers(); vi.clearAllMocks(); vi.unstubAllGlobals() })
  it('preserves a locally selected teacher slide on annotation refresh but follows participant control', async () => {
    const second = { ...slide, id: 'slide-2', position: 1, displayName: 'Second synthetic slide' }
    const snapshot = { ...teacher, slides: [slide, second] }
    api.teacherState.mockResolvedValue(snapshot)
    await mountTeacher()
    fireEvent.click(screen.getByRole('button', { name: '1. Synthetic slide' }))
    fireEvent.click(screen.getByRole('button', { name: /Slide 2\s*Second synthetic slide/ }))
    expect(screen.getByRole('button', { name: '2. Second synthetic slide' })).toBeVisible()
    api.teacherState.mockResolvedValue({ ...snapshot, stateVersion: 5 })
    act(() => Source.current?.emit('teaching-annotation-added', { hubEpoch: 'epoch', eventSequence: 1, stateVersion: 5 }))
    await waitFor(() => expect(api.teacherState).toHaveBeenCalledTimes(2))
    await act(async () => {})
    expect(screen.getByRole('button', { name: '2. Second synthetic slide' })).toBeVisible()
    api.teacherState.mockResolvedValue({ ...snapshot, stateVersion: 6, controller: { participantId: 'learner', leaseId: 'lease', controlEpoch: 1, expiresAt: null } })
    act(() => Source.current?.emit('control', { hubEpoch: 'epoch', eventSequence: 2, stateVersion: 6 }))
    await waitFor(() => expect(screen.getByRole('button', { name: '1. Synthetic slide' })).toBeVisible())
  })
  it('drops a queued teacher field while handoff acknowledgment is pending', async () => {
    await mountTeacher()
    fireEvent.click(screen.getByRole('button', { name: 'Guide students' }))
    await waitFor(() => expect(api.publishTeacherViewport).toHaveBeenCalledTimes(1))
    api.teacherState.mockImplementationOnce(() => new Promise(() => {}))
    vi.useFakeTimers(); movement(); handoff()
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(api.publishTeacherViewport).toHaveBeenCalledTimes(1)
  })
  it('drops a queued teacher field after guide mode is disabled', async () => {
    await mountTeacher()
    fireEvent.click(screen.getByRole('button', { name: 'Guide students' }))
    await waitFor(() => expect(api.publishTeacherViewport).toHaveBeenCalledTimes(1))
    vi.useFakeTimers(); movement()
    fireEvent.click(screen.getByRole('button', { name: 'Stop guiding students' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(api.publishTeacherViewport).toHaveBeenCalledTimes(1)
  })
  it('does not enable immediate guide publication while handoff acknowledgment is pending', async () => {
    await mountTeacher()
    api.teacherState.mockImplementationOnce(() => new Promise(() => {}))
    handoff()
    fireEvent.click(screen.getByRole('button', { name: 'Guide students' }))
    expect(api.publishTeacherViewport).not.toHaveBeenCalled()
  })
  it('does not republish a pointer after it has left the canvas', async () => {
    await mountTeacher()
    fireEvent.click(screen.getByRole('button', { name: 'Arrow pointer' }))
    api.clearTeacherPointer.mockClear()
    vi.useFakeTimers()
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })
    act(() => {
      harness.canvas!.dispatchEvent(new MouseEvent('pointermove', { buttons: 0, clientX: 20, clientY: 20 }))
      harness.canvas!.dispatchEvent(new MouseEvent('pointerleave'))
    })
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(api.clearTeacherPointer).toHaveBeenCalledTimes(1)
    expect(api.publishTeacherPointer).not.toHaveBeenCalled()
  })
  it('still publishes the teacher pointer while a participant controls the field', async () => {
    await mountTeacher()
    fireEvent.click(screen.getByRole('button', { name: 'Arrow pointer' }))
    api.teacherState.mockResolvedValue({ ...teacher, stateVersion: 5, controller: { ...teacher.controller, participantId: 'learner', leaseId: 'lease' } })
    handoff()
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
    api.clearTeacherPointer.mockClear()
    vi.useFakeTimers()
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })
    act(() => { harness.canvas!.dispatchEvent(new MouseEvent('pointermove', { buttons: 0, clientX: 20, clientY: 20 })) })
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(api.publishTeacherPointer).toHaveBeenCalledTimes(1)
  })
  it('drops a queued student field while its control snapshot is pending', async () => {
    render(<MemoryRouter initialEntries={['/classroom/session']}><ThemeProvider><Routes>
      <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
    </Routes></ThemeProvider></MemoryRouter>)
    await screen.findByText('SYNTHETIC')
    await waitFor(() => expect(harness.handlers.get('animation-finish')?.size).toBeGreaterThan(0))
    ready()
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
    api.studentState.mockImplementationOnce(() => new Promise(() => {}))
    vi.useFakeTimers(); movement(); movement(); handoff()
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(api.publishStudentViewport).not.toHaveBeenCalled()
  })
})
