import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ClassroomStudentPage } from '../pages/ClassroomStudentPage'
import { ThemeProvider } from '../theme/ThemeProvider'

const classroomApi = vi.hoisted(() => ({ studentState: vi.fn(), joinClassroom: vi.fn() }))
const notebook = vi.hoisted(() => ({
  listEntries: vi.fn(), deleteSessionEntries: vi.fn(),
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
        viewport: { getCenter: () => ({ x: 0.5, y: 0.5 }), viewportToImageCoordinates: () => ({ x: 50, y: 50 }), getZoom: () => 1 },
        world: { getItemAt: () => ({ source: { dimensions: { x: 100, y: 100 } } }) } }
      return onViewerAttach(viewer) as (() => void) | undefined
    }, [onViewerAttach])
    return <div />
  } }
})
vi.mock('../classroom/ClassroomPinOverlays', () => ({ ClassroomPinOverlays: () => null }))
vi.mock('../classroom/ClassroomTeachingOverlays', () => ({ ClassroomTeachingOverlays: () => null }))
vi.mock('../classroom/StudentDrawingOverlay', async () => {
  const { forwardRef, useImperativeHandle } = await import('react')
  return { StudentDrawingOverlay: forwardRef((_props, ref) => {
    useImperativeHandle(ref, () => ({ captureCanvas: () => undefined, hasDrawing: () => true, clear: notebook.clearDrawing }))
    return null
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

describe('student notebook failure handling', () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', EventSourceStub)
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
    classroomApi.studentState.mockResolvedValue(state)
    notebook.listEntries.mockResolvedValue([{ id: 'existing', sessionId: 'session-1', slideId: 'slide-1', slideName: 'Teaching slide', note: 'Saved note', createdAt: '' }])
    notebook.storageCapability.mockResolvedValue({ indexedDb: true })
  })
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); vi.unstubAllGlobals() })
  async function mount() {
    render(<MemoryRouter initialEntries={['/classroom/session-1']}><ThemeProvider><Routes>
      <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
    </Routes></ThemeProvider></MemoryRouter>)
    await screen.findByText('AMBER-00000001')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save capture + note' })).toBeEnabled())
  }
  it('keeps an authenticated resumed classroom when notebook loading rejects', async () => {
    notebook.listEntries.mockRejectedValueOnce(new Error('Quota denied'))
    await mount()
    expect(await screen.findByText('Local notebook could not be loaded. Classroom access is active; your saved notes have not been cleared.')).toBeVisible()
    expect(screen.queryByText('Rejoin with the classroom code to continue.')).not.toBeInTheDocument()
  })
  it('enters the joined stage after server acknowledgment despite notebook loading rejection', async () => {
    classroomApi.joinClassroom.mockResolvedValue({ sessionId: 'session-1', csrfToken: 'participant-csrf' })
    notebook.listEntries.mockRejectedValueOnce(new Error('Quota denied'))
    render(<MemoryRouter initialEntries={['/classroom']}><ThemeProvider><Routes>
      <Route path="/classroom" element={<ClassroomStudentPage />} />
      <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
    </Routes></ThemeProvider></MemoryRouter>)
    fireEvent.change(screen.getByRole('textbox', { name: 'Join code' }), { target: { value: 'ABCDEF' } })
    fireEvent.click(screen.getByRole('button', { name: 'Join classroom' }))
    expect(await screen.findByText('AMBER-00000001')).toBeVisible()
    expect(await screen.findByText('Local notebook could not be loaded. Classroom access is active; your saved notes have not been cleared.')).toBeVisible()
    expect(screen.queryByText('That classroom is unavailable or the code is incorrect.')).not.toBeInTheDocument()
  })
  it('keeps the rejoin requirement when the server snapshot rejects', async () => {
    classroomApi.studentState.mockRejectedValueOnce(new Error('Session unauthorized'))
    render(<MemoryRouter initialEntries={['/classroom/session-1']}><ThemeProvider><Routes>
      <Route path="/classroom/:sessionId" element={<ClassroomStudentPage />} />
    </Routes></ThemeProvider></MemoryRouter>)
    expect(await screen.findByText('Rejoin with the classroom code to continue.')).toBeVisible()
    expect(screen.queryByText('AMBER-00000001')).not.toBeInTheDocument()
    expect(screen.queryByText(/Classroom access is active/)).not.toBeInTheDocument()
  })
  it('keeps note and drawing when durable save rejects, then clears only after retry acknowledgment', async () => {
    notebook.saveEntry.mockRejectedValueOnce(new Error('Notebook limit reached (100 entries)')).mockResolvedValueOnce(undefined)
    await mount()
    const note = screen.getByPlaceholderText('Write a private note…')
    fireEvent.change(note, { target: { value: 'Keep my unsaved note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save capture + note' }))
    expect(await screen.findByText(/Notebook limit reached/)).toBeVisible()
    expect(note).toHaveValue('Keep my unsaved note')
    expect(notebook.clearDrawing).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Save capture + note' }))
    await waitFor(() => expect(notebook.clearDrawing).toHaveBeenCalledOnce())
    expect(note).toHaveValue('')
  })
  it('reports rejected export without claiming success', async () => {
    notebook.notebookFile.mockRejectedValueOnce(new Error('Image export failed'))
    await mount()
    fireEvent.click(screen.getByRole('button', { name: 'Share / export' }))
    expect(await screen.findByText(/Notebook export failed/)).toBeVisible()
    expect(screen.queryByText('Notebook exported as an offline file.')).not.toBeInTheDocument()
  })
  it('closes the blank print popup and reports rejected HTML generation', async () => {
    notebook.notebookHtml.mockRejectedValueOnce(new Error('Image export failed'))
    const popup = { document: { open: vi.fn(), write: vi.fn(), close: vi.fn() }, close: vi.fn(), focus: vi.fn(), print: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window)
    await mount()
    fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }))
    expect(await screen.findByText(/Notebook print preparation failed/)).toBeVisible()
    expect(popup.close).toHaveBeenCalledOnce()
    expect(popup.print).not.toHaveBeenCalled()
  })
  it('serializes Share and Print and releases the guard after failure', async () => {
    let rejectExport: ((error: Error) => void) | undefined
    notebook.notebookFile.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectExport = reject }))
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    await mount()
    const share = screen.getByRole('button', { name: 'Share / export' })
    const print = screen.getByRole('button', { name: 'Print / PDF' })
    act(() => { fireEvent.click(share); fireEvent.click(share); fireEvent.click(print) })
    expect(notebook.notebookFile).toHaveBeenCalledOnce()
    expect(notebook.notebookHtml).not.toHaveBeenCalled()
    expect(open).not.toHaveBeenCalled()
    expect(print).toBeDisabled()
    await act(async () => { rejectExport?.(new Error('export denied')) })
    expect(share).toBeEnabled()
    expect(print).toBeEnabled()
  })
  it('retains notebook entries and reports a rejected delete', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    notebook.deleteSessionEntries.mockRejectedValueOnce(new Error('transaction failed'))
    await mount()
    fireEvent.click(screen.getByRole('button', { name: 'Delete local notes' }))
    expect(await screen.findByText('Local notes could not be deleted. Your saved notes are kept; try again.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Share / export' })).toBeEnabled()
  })

})
