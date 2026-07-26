import type OpenSeadragon from 'openseadragon'

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { AnnotationApiError } from '../annotations/api'
import {
  AnnotationWorkspace,
  type AnnotationWorkspaceServices,
} from '../annotations/AnnotationWorkspace'
import { replayDraft } from '../annotations/draftRecovery'
import { createAnnotationStore } from '../annotations/store'
import type { AnnotationDraft } from '../annotations/drafts'
import type {
  AnnotationBatchRequest,
  AnnotationBatchResult,
  AnnotationLayer,
  AnnotationManifest,
  AnnotationRecord,
} from '../annotations/types'

const layerA: AnnotationLayer = {
  id: '11111111-1111-4111-8111-111111111111',
  slideId: 'slide-1',
  name: 'Findings',
  sortOrder: 0,
  visible: true,
  locked: false,
  opacity: 1,
  createdAt: '2026-07-26T00:00:00Z',
  updatedAt: '2026-07-26T00:00:00Z',
}

const layerB: AnnotationLayer = {
  ...layerA,
  id: '22222222-2222-4222-8222-222222222222',
  name: 'Review',
  sortOrder: 1,
}

const lockedLayer: AnnotationLayer = {
  ...layerA,
  id: '33333333-3333-4333-8333-333333333333',
  name: 'Locked reference',
  sortOrder: 2,
  locked: true,
}

function manifest(
  layers: AnnotationLayer[] = [layerA, layerB, lockedLayer],
  version = 1,
): AnnotationManifest {
  return {
    slideId: 'slide-1',
    version,
    bounds: { width: 2048, height: 1024 },
    calibration: { x: 0.5, y: 0.75, unit: 'µm' },
    activeCount: 0,
    trashedCount: 0,
    layers,
    limits: {
      activeAnnotations: 25_000,
      layers: 100,
      verticesPerShape: 8_192,
      verticesPerImport: 250_000,
      batchOperations: 50,
    },
  }
}

function record(index: number, layerId = layerA.id): AnnotationRecord {
  const x = index % 500
  const y = Math.floor(index / 500)
  return {
    id: `annotation-${index}`,
    layerId,
    geometry: { type: 'point', x, y },
    style: {
      strokeColor: '#bf3c32',
      fillColor: '#bf3c32',
      strokeWidth: 2,
      opacity: 0.8,
      labelVisible: true,
    },
    metadata: {
      title: `Finding ${index}`,
      classification: index % 2 ? 'Tumour' : 'Stroma',
      tags: ['review'],
      notes: '',
    },
    version: 1,
    deletedAt: null,
    createdAt: '2026-07-26T00:00:00Z',
    updatedAt: '2026-07-26T00:00:00Z',
    bounds: { minX: x, minY: y, maxX: x, maxY: y },
    measurements: {},
  }
}

function successfulBatch(request: AnnotationBatchRequest, version = request.baseVersion + 1) {
  return {
    mutationId: request.mutationId,
    version,
    results: request.operations.map((operation) => ({
      id: operation.type === 'create' ? operation.item.id : operation.id,
      operation: operation.type,
      version,
      deleted: operation.type === 'delete',
    })),
    purged: 0,
  } satisfies AnnotationBatchResult
}

it('drops a recovered create that is already committed after its response was lost', () => {
  const committed = record(17)
  const store = createAnnotationStore({ slideId: 'slide-1' })
  store.load({ version: 9, layers: [layerA], annotations: [committed] })

  replayDraft(store, {
    schema: 'pathlab-annotation-draft/v1',
    slideId: 'slide-1',
    baseVersion: 8,
    dirty: true,
    savedAt: Date.now(),
    byteSize: 1,
    mutations: [{
      type: 'create',
      item: {
        id: committed.id,
        layerId: committed.layerId,
        geometry: committed.geometry,
        style: committed.style,
        metadata: committed.metadata,
      },
    }],
  })

  expect(store.getState().version).toBe(9)
  expect(store.getState().pendingMutations).toEqual([])
  expect(store.getState().recoveryMutations).toEqual([])
})

it('rebases a divergent response-lost create to a retryable server-versioned update', () => {
  const committed = record(18)
  const store = createAnnotationStore({ slideId: 'slide-1' })
  store.load({ version: 9, layers: [layerA], annotations: [committed] })

  replayDraft(store, {
    schema: 'pathlab-annotation-draft/v1',
    slideId: 'slide-1',
    baseVersion: 8,
    dirty: true,
    savedAt: Date.now(),
    byteSize: 1,
    mutations: [{
      type: 'create',
      item: {
        id: committed.id,
        layerId: layerA.id,
        geometry: { type: 'point', x: 701, y: 211 },
        style: { ...committed.style, opacity: 0.42 },
        metadata: { ...committed.metadata, title: 'Recovered local intent' },
      },
    }],
  })

  expect(store.getState().annotations.get(committed.id)).toMatchObject({
    geometry: { type: 'point', x: 701, y: 211 },
    style: { opacity: 0.42 },
    metadata: { title: 'Recovered local intent' },
  })
  expect(store.getState().pendingMutations).toEqual([{
    type: 'update',
    id: committed.id,
    version: committed.version,
    layerId: layerA.id,
    geometry: { type: 'point', x: 701, y: 211 },
    style: { ...committed.style, opacity: 0.42 },
    metadata: { ...committed.metadata, title: 'Recovered local intent' },
  }])
  expect(store.getState().recoveryMutations).toEqual(
    store.getState().pendingMutations,
  )
})

function services(
  overrides: Partial<AnnotationWorkspaceServices> = {},
  items: AnnotationRecord[] = [],
  layers: AnnotationLayer[] = [layerA, layerB, lockedLayer],
): AnnotationWorkspaceServices {
  return {
    getManifest: vi.fn(async () => ({ ...manifest(layers), activeCount: items.length })),
    getItems: vi.fn(async () => ({ items, total: items.length, nextOffset: null })),
    batch: vi.fn(async (request) => successfulBatch(request)),
    createLayer: vi.fn(),
    updateLayer: vi.fn(async (layerId, request) => ({
      version: request.baseVersion + 1,
      layer: {
        ...(layers.find((layer) => layer.id === layerId) ?? layerA),
        ...request,
      },
    })),
    importDocument: vi.fn(async (request) => ({
      mutationId: request.mutationId,
      version: request.baseVersion + 1,
      results: [],
      purged: 0,
    })),
    exportDocument: vi.fn(async () => new Response('{}')),
    revisions: vi.fn(async () => ({ items: [] })),
    restoreRevision: vi.fn(),
    loadDraft: vi.fn(async () => null),
    saveDraft: vi.fn(async () => undefined),
    acknowledgeDraft: vi.fn(async () => undefined),
    discardDraft: vi.fn(async () => undefined),
    ...overrides,
  }
}

it('acknowledges the durable draft after an equivalent lost-response create reloads', async () => {
  const committed = record(19)
  const acknowledgeDraft = vi.fn(async () => undefined)
  const recovered: AnnotationDraft = {
    schema: 'pathlab-annotation-draft/v1',
    slideId: 'slide-1',
    baseVersion: 8,
    dirty: true,
    savedAt: Date.now(),
    byteSize: 1,
    mutations: [{
      type: 'create',
      item: {
        id: committed.id,
        layerId: committed.layerId,
        geometry: committed.geometry,
        style: committed.style,
        metadata: committed.metadata,
      },
    }],
  }
  const workspaceServices = services({
    getManifest: vi.fn(async () => ({
      ...manifest([layerA], 9),
      activeCount: 1,
    })),
    loadDraft: vi.fn(async () => recovered),
    acknowledgeDraft,
  }, [committed], [layerA])

  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Lost response"
      services={workspaceServices}
      onAttachmentChange={vi.fn()}
    />,
  )

  await screen.findByRole('toolbar', { name: 'Annotation tools' })
  await waitFor(() => expect(acknowledgeDraft).toHaveBeenCalledOnce())
  expect(workspaceServices.batch).not.toHaveBeenCalled()
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function mockViewer() {
  const canvas = document.createElement('div')
  document.body.append(canvas)
  Object.defineProperties(canvas, {
    clientWidth: { configurable: true, value: 1000 },
    clientHeight: { configurable: true, value: 600 },
  })
  vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue({
    x: 0,
    y: 0,
    left: 0,
    top: 0,
    right: 1000,
    bottom: 600,
    width: 1000,
    height: 600,
    toJSON: () => ({}),
  })
  return {
    canvas,
    viewport: {
      viewerElementToImageCoordinates: (point: { x: number; y: number }) => point,
      imageToViewerElementCoordinates: (point: { x: number; y: number }) => point,
      getBounds: () => ({ x: 0, y: 0, width: 1000, height: 600 }),
      fitBounds: vi.fn(),
    },
    world: {
      getItemAt: vi.fn(() => ({
        viewportToImageRectangle: (rectangle: unknown) => rectangle,
        imageToViewportRectangle: (rectangle: unknown) => rectangle,
      })),
    },
    setMouseNavEnabled: vi.fn(),
    setKeyboardNavEnabled: vi.fn(),
    addHandler: vi.fn(),
    removeHandler: vi.fn(),
  } as unknown as OpenSeadragon.Viewer
}

async function attachAndDrawPoint(
  onAttachmentChange: ReturnType<typeof vi.fn>,
  x = 120,
  y = 80,
  beforeDraw?: () => void,
) {
  await screen.findByRole('toolbar', { name: 'Annotation tools' })
  await waitFor(() => expect(onAttachmentChange.mock.calls.some(
    ([attachment]) => typeof attachment === 'function',
  )).toBe(true))
  const attachment = [...onAttachmentChange.mock.calls]
    .reverse()
    .find((call: unknown[]) => typeof call[0] === 'function')?.[0]
  expect(attachment).toBeTypeOf('function')
  const viewer = mockViewer()
  act(() => {
    attachment(viewer)
  })
  beforeDraw?.()
  fireEvent.click(screen.getByRole('button', { name: 'Point marker' }))
  const overlay = viewer.canvas.querySelector('.annotation-svg-overlay')!
  overlay.dispatchEvent(new MouseEvent('pointerdown', {
    bubbles: true,
    clientX: x,
    clientY: y,
  }))
  return viewer
}

beforeEach(() => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1200 })
})

afterEach(() => {
  cleanup()
  document.body.replaceChildren()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

it('persists queued and in-flight mutations on unmount and recovers them on remount', async () => {
  const pending = deferred<AnnotationBatchResult>()
  let recovered: AnnotationDraft | null = null
  const workflow = services({
    batch: vi.fn(() => pending.promise),
    saveDraft: vi.fn(async (draft) => {
      recovered = { ...structuredClone(draft), byteSize: 1 }
    }),
    loadDraft: vi.fn(async () => recovered),
  })
  const onAttachmentChange = vi.fn()
  const view = render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={workflow}
      onAttachmentChange={onAttachmentChange}
    />,
  )
  await attachAndDrawPoint(onAttachmentChange, 120, 80, () => vi.useFakeTimers())
  await act(() => vi.advanceTimersByTimeAsync(1_000))
  expect(workflow.batch).toHaveBeenCalledOnce()
  expect(recovered).toMatchObject({ dirty: true })
  expect((recovered as AnnotationDraft | null)?.mutations).toHaveLength(1)

  view.unmount()
  expect(workflow.saveDraft).toHaveBeenCalled()
  expect(recovered).toMatchObject({ dirty: true })
  expect(workflow.acknowledgeDraft).not.toHaveBeenCalled()

  vi.useRealTimers()
  const remountAttachment = vi.fn()
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={workflow}
      onAttachmentChange={remountAttachment}
    />,
  )
  expect(await screen.findByText('point annotation')).toBeVisible()
  pending.resolve(successfulBatch(vi.mocked(workflow.batch).mock.calls[0][0]))
})

it('deletes a dirty draft only after the matching server acknowledgement', async () => {
  const saved: Array<Omit<AnnotationDraft, 'byteSize'>> = []
  const workflow = services({
    saveDraft: vi.fn(async (draft) => {
      saved.push(structuredClone(draft))
    }),
  })
  const onAttachmentChange = vi.fn()
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={workflow}
      onAttachmentChange={onAttachmentChange}
    />,
  )
  await attachAndDrawPoint(onAttachmentChange, 120, 80, () => vi.useFakeTimers())
  await act(() => vi.advanceTimersByTimeAsync(1_250))
  vi.useRealTimers()
  await waitFor(() => expect(workflow.acknowledgeDraft).toHaveBeenCalledOnce())
  expect(saved.length).toBeGreaterThan(0)
  expect(saved.every((draft) => draft.dirty && draft.mutations.length > 0)).toBe(true)
})

it('rebases save-as-duplicate to the server conflict version', async () => {
  const requests: AnnotationBatchRequest[] = []
  const workflow = services({
    batch: vi.fn(async (request) => {
      requests.push(structuredClone(request))
      if (requests.length === 1) {
        throw new AnnotationApiError(409, 'ANNOTATION_CONFLICT', { currentVersion: 9 })
      }
      return successfulBatch(request, 10)
    }),
    getManifest: vi.fn(async () => manifest([layerA], 10)),
  }, [], [layerA])
  const onAttachmentChange = vi.fn()
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={workflow}
      onAttachmentChange={onAttachmentChange}
    />,
  )
  await attachAndDrawPoint(onAttachmentChange, 120, 80, () => vi.useFakeTimers())
  const previousFocus = screen.getByRole('button', { name: 'Save annotations' })
  previousFocus.focus()
  await act(() => vi.advanceTimersByTimeAsync(750))
  vi.useRealTimers()
  const conflict = await screen.findByRole('alertdialog', { name: 'Annotation save conflict' })
  expect(conflict).toHaveAttribute('aria-modal', 'true')
  await waitFor(() => expect(
    within(conflict).getByRole('button', { name: 'Reload server' }),
  ).toHaveFocus())
  fireEvent.click(within(conflict).getByRole('button', { name: 'Save as duplicate' }))
  await waitFor(() => expect(requests).toHaveLength(2))
  expect(requests[1].baseVersion).toBe(9)
  await waitFor(() => expect(previousFocus).toHaveFocus())
})

it('serializes layer reorder with unique indices and commits opacity once per gesture', async () => {
  const layerCalls: Array<{
    layerId: string
    request: Parameters<AnnotationWorkspaceServices['updateLayer']>[1]
  }> = []
  const workflow = services({
    updateLayer: vi.fn(async (layerId, request) => {
      layerCalls.push({ layerId, request: structuredClone(request) })
      return {
        version: request.baseVersion + 1,
        layer: {
          ...([layerA, layerB].find((layer) => layer.id === layerId) ?? layerA),
          ...request,
        },
      }
    }),
  }, [], [layerA, layerB])
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={workflow}
      onAttachmentChange={vi.fn()}
    />,
  )
  await screen.findByRole('button', { name: 'Move Review up' })
  fireEvent.click(screen.getByRole('button', { name: 'Move Review up' }))
  await waitFor(() => expect(layerCalls).toHaveLength(2))
  expect(layerCalls.map(({ layerId, request }) => ({
    layerId,
    baseVersion: request.baseVersion,
    sortOrder: request.sortOrder,
  }))).toEqual([
    { layerId: layerB.id, baseVersion: 1, sortOrder: 0 },
    { layerId: layerA.id, baseVersion: 2, sortOrder: 1 },
  ])

  layerCalls.length = 0
  const opacity = screen.getByRole('slider', { name: 'Review opacity' })
  fireEvent.change(opacity, { target: { value: '0.8' } })
  fireEvent.change(opacity, { target: { value: '0.6' } })
  fireEvent.change(opacity, { target: { value: '0.4' } })
  expect(layerCalls).toHaveLength(0)
  fireEvent.pointerUp(opacity)
  await waitFor(() => expect(layerCalls).toHaveLength(1))
  expect(layerCalls[0].request.opacity).toBe(0.4)
})

it('never permits a locked layer to become the active drawing target', async () => {
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={services({}, [], [lockedLayer])}
      onAttachmentChange={vi.fn()}
    />,
  )
  const drawingLayer = await screen.findByRole('combobox', { name: 'Drawing layer' })
  expect(drawingLayer).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Locked reference' })).toBeDisabled()
})

it('previews bounded imports before confirmation and flushes before export', async () => {
  const order: string[] = []
  const workflow = services({
    batch: vi.fn(async (request) => {
      order.push('save')
      return successfulBatch(request)
    }),
    exportDocument: vi.fn(async () => {
      order.push('export')
      return new Response('{}')
    }),
  }, [], [layerA])
  const onAttachmentChange = vi.fn()
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={workflow}
      onAttachmentChange={onAttachmentChange}
    />,
  )
  await screen.findByRole('button', { name: 'Import annotations' })
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
  const oversized = new File(['{}'], 'oversized.json', { type: 'application/json' })
  const oversizedText = vi.fn(async () => '{}')
  Object.defineProperties(oversized, {
    size: { configurable: true, value: 8 * 1024 * 1024 + 1 },
    text: { configurable: true, value: oversizedText },
  })
  fireEvent.change(input, { target: { files: [oversized] } })
  expect(await screen.findAllByText(/8 MiB/i)).not.toHaveLength(0)
  expect(oversizedText).not.toHaveBeenCalled()

  const documentJson = {
    schema: 'pathlab-annotations/v1',
    slide: { id: 'slide-1', width: 2048, height: 1024, annotationVersion: 1 },
    layers: [],
    annotations: [],
  }
  const valid = new File(['{}'], 'valid.json', { type: 'application/json' })
  Object.defineProperty(valid, 'text', {
    configurable: true,
    value: vi.fn(async () => JSON.stringify(documentJson)),
  })
  fireEvent.change(input, { target: { files: [valid] } })
  expect(await screen.findByRole('button', { name: 'Confirm annotation import' })).toBeVisible()
  expect(workflow.importDocument).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm annotation import' }))
  await waitFor(() => expect(workflow.importDocument).toHaveBeenCalledOnce())

  await attachAndDrawPoint(onAttachmentChange, 300, 200)
  fireEvent.click(screen.getByRole('button', { name: 'Export PathLab JSON' }))
  await waitFor(() => expect(workflow.exportDocument).toHaveBeenCalledOnce())
  expect(order.slice(-2)).toEqual(['save', 'export'])
})

it('lists bounded revision history for explicit preview and restore selection', async () => {
  const source = record(1)
  const workflow = services({
    revisions: vi.fn(async () => ({
      items: [
        {
          id: 'revision-3',
          version: 3,
          layerId: layerA.id,
          geometry: source.geometry,
          style: source.style,
          metadata: { ...source.metadata, title: 'Latest prior state' },
          deletedAt: null,
          createdAt: '2026-07-26T03:00:00Z',
        },
        {
          id: 'revision-2',
          version: 2,
          layerId: layerA.id,
          geometry: source.geometry,
          style: source.style,
          metadata: { ...source.metadata, title: 'Earlier diagnosis' },
          deletedAt: null,
          createdAt: '2026-07-26T02:00:00Z',
        },
      ],
    })),
    restoreRevision: vi.fn(async () => ({ version: 4, item: source })),
  }, [source], [layerA])
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={workflow}
      onAttachmentChange={vi.fn()}
    />,
  )
  fireEvent.click(await screen.findByRole('button', { name: /Finding 1/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Browse annotation revisions' }))
  await waitFor(() => expect(workflow.revisions).toHaveBeenCalledWith(source.id))
  const revisionList = await screen.findByRole('combobox', { name: 'Annotation revisions' })
  expect(within(revisionList).getAllByRole('option').filter(
    (option) => (option as HTMLOptionElement).value !== '',
  )).toHaveLength(2)
  expect(workflow.restoreRevision).not.toHaveBeenCalled()
  fireEvent.change(revisionList, { target: { value: 'revision-2' } })
  expect(screen.getByText('Earlier diagnosis')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Restore selected revision' }))
  await waitFor(() => expect(workflow.restoreRevision).toHaveBeenCalledWith(
    source.id,
    'revision-2',
    expect.any(Object),
  ))
})

it('bounds the object register and offers an accessible continuation', async () => {
  const records = Array.from({ length: 500 }, (_, index) => record(index))
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={services({}, records, [layerA])}
      onAttachmentChange={vi.fn()}
    />,
  )
  const register = await screen.findByLabelText('Annotation list')
  await within(register).findByText('Finding 0')
  expect(within(register).getAllByRole('button', { name: /Finding/ })).toHaveLength(200)
  fireEvent.click(within(register).getByRole('button', { name: /Show 200 more annotations/i }))
  expect(within(register).getAllByRole('button', { name: /Finding/ })).toHaveLength(200)
  expect(within(register).queryByText('Finding 0')).toBeNull()
  expect(within(register).getByText('Finding 200')).toBeVisible()
  fireEvent.click(within(register).getByRole('button', { name: /Show 100 more annotations/i }))
  expect(within(register).getAllByRole('button', { name: /Finding/ })).toHaveLength(100)
  expect(within(register).queryByText('Finding 200')).toBeNull()
  expect(within(register).getByText('Finding 400')).toBeVisible()
})

it('treats the mobile inspector and conflict surface as focus-trapped modal dialogs', async () => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 700 })
  const workflow = services({}, [], [layerA])
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={workflow}
      onAttachmentChange={vi.fn()}
    />,
  )
  const trigger = await screen.findByRole('button', { name: 'Open annotation inspector' })
  trigger.focus()
  fireEvent.click(trigger)
  const dialog = screen.getByRole('dialog', { name: 'Annotation inspector' })
  expect(dialog).toHaveAttribute('aria-modal', 'true')
  const close = within(dialog).getByRole('button', { name: 'Close annotation inspector' })
  await waitFor(() => expect(close).toHaveFocus())
  const focusable = within(dialog).getAllByRole('button')
  focusable.at(-1)!.focus()
  fireEvent.keyDown(dialog, { key: 'Tab' })
  expect(close).toHaveFocus()
  fireEvent.click(close)
  expect(trigger).toHaveFocus()
})

it('does not rerender or clone/filter 25,000 records for pointer coordinate updates', async () => {
  const records = Array.from({ length: 25_000 }, (_, index) => record(index))
  const onAttachmentChange = vi.fn()
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Large private slide"
      services={services({}, records, [layerA])}
      onAttachmentChange={onAttachmentChange}
    />,
  )
  await screen.findByRole('toolbar', { name: 'Annotation tools' }, { timeout: 20_000 })
  await waitFor(() => expect(onAttachmentChange.mock.calls.some(
    ([attachment]) => typeof attachment === 'function',
  )).toBe(true), { timeout: 20_000 })
  const attachment = [...onAttachmentChange.mock.calls]
    .reverse()
    .find((call: unknown[]) => typeof call[0] === 'function')?.[0]
  const viewer = mockViewer()
  act(() => attachment(viewer))
  const originalClone = globalThis.structuredClone
  const cloneCounter = vi.fn(<T,>(value: T) => originalClone(value))
  vi.stubGlobal('structuredClone', cloneCounter)
  const overlay = viewer.canvas.querySelector('.annotation-svg-overlay')!

  for (let index = 0; index < 50; index += 1) {
    overlay.dispatchEvent(new MouseEvent('pointermove', {
      bubbles: true,
      clientX: 100 + index,
      clientY: 200 + index,
    }))
  }

  await waitFor(() => expect(screen.getByText(/X 149\.0\s+Y 249\.0/)).toBeVisible())
  expect(cloneCounter).not.toHaveBeenCalled()
  expect(screen.getByLabelText('Annotation list').querySelectorAll(
    ':scope > .annotation-list-scroll > button[data-annotation-row]',
  ).length).toBeLessThanOrEqual(200)
}, 30_000)

it('ignores a slide A layer completion after slide B has replaced the workspace', async () => {
  const slideALayer = { ...layerA, name: 'Slide A layer' }
  const slideBLayer = { ...layerA, id: layerB.id, name: 'Slide B layer' }
  const update = deferred<Awaited<ReturnType<AnnotationWorkspaceServices['updateLayer']>>>()
  const slideA = services({
    updateLayer: vi.fn(() => update.promise),
  }, [], [slideALayer])
  const slideB = services({}, [], [slideBLayer])
  const view = render(
    <AnnotationWorkspace
      slideId="slide-a"
      slideName="Slide A"
      services={slideA}
      onAttachmentChange={vi.fn()}
    />,
  )
  const visible = await screen.findByRole('checkbox', { name: 'Show Slide A layer' })
  fireEvent.click(visible)
  await waitFor(() => expect(slideA.updateLayer).toHaveBeenCalledOnce())

  view.rerender(
    <AnnotationWorkspace
      slideId="slide-b"
      slideName="Slide B"
      services={slideB}
      onAttachmentChange={vi.fn()}
    />,
  )
  await screen.findByRole('button', { name: 'Slide B layer' })
  update.resolve({
    version: 2,
    layer: { ...slideALayer, visible: false },
  })
  await act(async () => {
    await update.promise
    await Promise.resolve()
  })

  expect(screen.getByRole('button', { name: 'Slide B layer' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Slide A layer' })).toBeNull()
  expect(slideA.getManifest).toHaveBeenCalledOnce()
  expect(slideB.getManifest).toHaveBeenCalledOnce()
})

it('clears slide-bound import and revision work and ignores stale completions', async () => {
  const source = record(1)
  const importResult = deferred<AnnotationBatchResult>()
  const revisionResult = deferred<Awaited<ReturnType<AnnotationWorkspaceServices['revisions']>>>()
  const slideA = services({
    importDocument: vi.fn(() => importResult.promise),
    revisions: vi.fn(() => revisionResult.promise),
  }, [source], [layerA])
  const slideBLayer = { ...layerB, name: 'Slide B layer' }
  const slideB = services({}, [], [slideBLayer])
  const view = render(
    <AnnotationWorkspace
      slideId="slide-a"
      slideName="Slide A"
      services={slideA}
      onAttachmentChange={vi.fn()}
    />,
  )
  await screen.findByRole('button', { name: /Finding 1/ })
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
  const documentJson = {
    schema: 'pathlab-annotations/v1',
    slide: { id: 'slide-a', width: 2048, height: 1024, annotationVersion: 1 },
    layers: [],
    annotations: [],
  }
  const valid = new File(['{}'], 'slide-a.json')
  Object.defineProperty(valid, 'text', {
    configurable: true,
    value: vi.fn(async () => JSON.stringify(documentJson)),
  })
  fireEvent.change(input, { target: { files: [valid] } })
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm annotation import' }))
  await waitFor(() => expect(slideA.importDocument).toHaveBeenCalledOnce())
  fireEvent.click(screen.getByRole('button', { name: /Finding 1/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Browse annotation revisions' }))
  await waitFor(() => expect(slideA.revisions).toHaveBeenCalledOnce())

  view.rerender(
    <AnnotationWorkspace
      slideId="slide-b"
      slideName="Slide B"
      services={slideB}
      onAttachmentChange={vi.fn()}
    />,
  )
  await screen.findByRole('button', { name: 'Slide B layer' })
  expect(screen.queryByRole('button', { name: 'Confirm annotation import' })).toBeNull()
  importResult.resolve({
    mutationId: 'import-a',
    version: 2,
    results: [],
    purged: 0,
  })
  revisionResult.resolve({
    items: [{
      id: 'revision-a',
      version: 1,
      layerId: layerA.id,
      geometry: source.geometry,
      style: source.style,
      metadata: { ...source.metadata, title: 'Stale A revision' },
      deletedAt: null,
      createdAt: '2026-07-26T01:00:00Z',
    }],
  })
  await act(async () => {
    await Promise.all([importResult.promise, revisionResult.promise])
    await Promise.resolve()
  })

  expect(screen.queryByText('Stale A revision')).toBeNull()
  expect(screen.getByRole('button', { name: 'Slide B layer' })).toBeVisible()
  expect(slideA.getManifest).toHaveBeenCalledOnce()
})

it('reports an offline dirty draft as retained without acknowledging or discarding it', async () => {
  const workflow = services({
    getManifest: vi.fn(async () => {
      throw new TypeError('offline')
    }),
    loadDraft: vi.fn(async (): Promise<AnnotationDraft> => ({
      schema: 'pathlab-annotation-draft/v1',
      slideId: 'slide-1',
      baseVersion: 1,
      mutations: [{
        type: 'update',
        id: 'annotation-1',
        version: 1,
        metadata: {
          title: 'Unsaved diagnosis',
          classification: '',
          tags: [],
          notes: '',
        },
      }],
      savedAt: 100,
      dirty: true,
      byteSize: 400,
    })),
  })
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Offline slide"
      services={workflow}
      onAttachmentChange={vi.fn()}
    />,
  )

  expect(await screen.findAllByText(/unsaved local draft.*retained/i))
    .not.toHaveLength(0)
  expect(workflow.loadDraft).toHaveBeenCalledOnce()
  expect(workflow.acknowledgeDraft).not.toHaveBeenCalled()
  expect(workflow.discardDraft).not.toHaveBeenCalled()
})

it('preflights the exact 8 MiB serialized import request and accepts a near-boundary request', async () => {
  const workflow = services({}, [], [layerA])
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Boundary slide"
      services={workflow}
      onAttachmentChange={vi.fn()}
    />,
  )
  await screen.findByRole('button', { name: 'Import annotations' })
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
  const boundaryText = (targetBytes: number) => {
    const documentJson = {
      schema: 'pathlab-annotations/v1',
      slide: { id: 'slide-1', width: 2048, height: 1024, annotationVersion: 1 },
      layers: [{
        id: layerA.id,
        name: 'Boundary',
        sortOrder: 0,
        visible: true,
        locked: false,
        opacity: 1,
      }],
      annotations: Array.from({ length: 1_950 }, (_, index) => ({
        id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
        layerId: layerA.id,
        geometry: { type: 'point', x: 1, y: 1 },
        style: record(0).style,
        metadata: {
          title: '',
          classification: '',
          tags: [],
          notes: 'x'.repeat(4_000),
        },
      })),
    }
    let overflow = new TextEncoder().encode(JSON.stringify(documentJson)).byteLength - targetBytes
    for (let index = documentJson.annotations.length - 1; overflow > 0; index -= 1) {
      const reduction = Math.min(4_000, overflow)
      documentJson.annotations[index].metadata.notes = 'x'.repeat(4_000 - reduction)
      overflow -= reduction
    }
    return JSON.stringify(documentJson)
  }
  const exactText = boundaryText(8 * 1024 * 1024)
  expect(new TextEncoder().encode(exactText)).toHaveLength(8 * 1024 * 1024)
  const importFile = (text: string, name: string) => {
    const file = new File(['{}'], name)
    Object.defineProperties(file, {
      size: {
        configurable: true,
        value: new TextEncoder().encode(text).byteLength,
      },
      text: {
        configurable: true,
        value: vi.fn(async () => text),
      },
    })
    return file
  }
  fireEvent.change(input, {
    target: { files: [importFile(exactText, 'exact-limit.json')] },
  })
  expect(await screen.findAllByText(/serialized import request exceeds the 8 MiB limit/i))
    .not.toHaveLength(0)
  expect(workflow.importDocument).not.toHaveBeenCalled()

  const nearText = boundaryText(8 * 1024 * 1024 - 1024)
  fireEvent.change(input, {
    target: { files: [importFile(nearText, 'near-limit.json')] },
  })
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm annotation import' }))
  await waitFor(() => expect(workflow.importDocument).toHaveBeenCalledOnce())
  const request = vi.mocked(workflow.importDocument).mock.calls[0][0]
  expect(new TextEncoder().encode(JSON.stringify(request)).byteLength)
    .toBeLessThanOrEqual(8 * 1024 * 1024)
}, 30_000)
