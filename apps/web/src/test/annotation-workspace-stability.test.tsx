import type OpenSeadragon from 'openseadragon'

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { AnnotationApiError } from '../annotations/api'
import {
  AnnotationWorkspace,
  type AnnotationWorkspaceServices,
} from '../annotations/AnnotationWorkspace'
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
  expect(within(register).getByRole('button', { name: /Show 200 more annotations/i })).toBeVisible()
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
