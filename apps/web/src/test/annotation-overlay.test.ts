import type OpenSeadragon from 'openseadragon'

import { cleanup } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { attachAnnotationOverlay } from '../annotations/AnnotationOverlay'
import { AnnotationSpatialIndex } from '../annotations/spatialIndex'
import { createAnnotationStore } from '../annotations/store'
import type { AnnotationLayer, AnnotationRecord } from '../annotations/types'

const layer: AnnotationLayer = {
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

function mockViewer(mapping: {
  toImage?: (point: { x: number; y: number }) => { x: number; y: number }
  toViewer?: (point: { x: number; y: number }) => { x: number; y: number }
} = {}) {
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
  const handlers = new Map<string, Set<() => void>>()
  const viewer = {
    canvas,
    viewport: {
      viewerElementToImageCoordinates: mapping.toImage
        ?? ((point: { x: number; y: number }) => point),
      imageToViewerElementCoordinates: mapping.toViewer
        ?? ((point: { x: number; y: number }) => point),
      getBounds: () => ({ x: 0, y: 0, width: 1000, height: 600 }),
    },
    world: {
      getItemAt: vi.fn(() => ({
        viewportToImageRectangle: (rectangle: unknown) => rectangle,
      })),
    },
    setMouseNavEnabled: vi.fn(),
    setKeyboardNavEnabled: vi.fn(),
    addHandler: vi.fn((name: string, handler: () => void) => {
      const values = handlers.get(name) ?? new Set()
      values.add(handler)
      handlers.set(name, values)
    }),
    removeHandler: vi.fn((name: string, handler: () => void) => {
      handlers.get(name)?.delete(handler)
    }),
    raiseEvent: vi.fn((name: string) => {
      for (const handler of handlers.get(name) ?? []) handler()
    }),
  }
  return viewer as unknown as OpenSeadragon.Viewer
}

function polygonRecord(
  id = '33333333-3333-4333-8333-333333333333',
): AnnotationRecord {
  return {
    id,
    layerId: layer.id,
    geometry: {
      type: 'polygon',
      points: [
        { x: 10, y: 10 },
        { x: 110, y: 10 },
        { x: 110, y: 110 },
        { x: 10, y: 110 },
      ],
    },
    style: {
      strokeColor: '#bf3c32',
      fillColor: '#bf3c32',
      strokeWidth: 2,
      opacity: 0.8,
      labelVisible: true,
    },
    metadata: {
      title: 'Tumour boundary',
      classification: 'Tumour',
      tags: [],
      notes: '',
    },
    version: 1,
    deletedAt: null,
    createdAt: '2026-07-26T00:00:00Z',
    updatedAt: '2026-07-26T00:00:00Z',
    bounds: { minX: 10, minY: 10, maxX: 110, maxY: 110 },
    measurements: {},
  }
}

afterEach(() => {
  cleanup()
  document.body.replaceChildren()
  vi.restoreAllMocks()
})

it('maps pointer gestures into image-pixel annotations and restores navigation on cleanup', () => {
  const store = createAnnotationStore({
    slideId: 'slide-1',
    bounds: { width: 2048, height: 1024 },
    idFactory: () => '22222222-2222-4222-8222-222222222222',
  })
  store.load({ version: 0, layers: [layer], annotations: [] })
  const viewer = mockViewer()
  const cleanupOverlay = attachAnnotationOverlay(viewer, {
    store,
    activeLayerId: () => layer.id,
    style: () => ({
      strokeColor: '#ffb400',
      fillColor: '#ffb400',
      strokeWidth: 2,
      opacity: 1,
      labelVisible: true,
    }),
    metadata: () => ({ title: '', classification: '', tags: [], notes: '' }),
    text: () => 'Callout',
  })

  store.setTool('point')
  const overlay = viewer.canvas.querySelector('.annotation-svg-overlay')
  expect(overlay).toBeInstanceOf(SVGSVGElement)
  overlay!.dispatchEvent(new MouseEvent('pointerdown', {
    bubbles: true,
    clientX: 120,
    clientY: 80,
  }))

  const record = [...store.getState().annotations.values()][0]
  expect(record?.geometry).toEqual({ type: 'point', x: 120, y: 80 })
  expect(viewer.setMouseNavEnabled).toHaveBeenLastCalledWith(false)

  cleanupOverlay()
  expect(viewer.canvas.querySelector('.annotation-svg-overlay')).toBeNull()
  expect(viewer.setMouseNavEnabled).toHaveBeenLastCalledWith(true)
  expect(viewer.setKeyboardNavEnabled).toHaveBeenLastCalledWith(true)
})

it('fails open to pan and zoom when rendering throws', () => {
  const store = createAnnotationStore({ slideId: 'slide-1' })
  store.load({ version: 0, layers: [layer], annotations: [] })
  const viewer = mockViewer()
  const onError = vi.fn()
  const cleanupOverlay = attachAnnotationOverlay(viewer, {
    store,
    activeLayerId: () => layer.id,
    style: () => ({
      strokeColor: '#ffb400',
      fillColor: '#ffb400',
      strokeWidth: 2,
      opacity: 1,
      labelVisible: true,
    }),
    metadata: () => ({ title: '', classification: '', tags: [], notes: '' }),
    text: () => 'Callout',
    onError,
  })

  vi.mocked(viewer.world.getItemAt).mockImplementation(() => {
    throw new Error('overlay render fault')
  })
  store.setTool('select')
  viewer.raiseEvent('animation-finish', {})

  expect(onError).toHaveBeenCalledWith('overlay render fault')
  expect(viewer.setMouseNavEnabled).toHaveBeenLastCalledWith(true)
  expect(viewer.setKeyboardNavEnabled).toHaveBeenLastCalledWith(true)
  cleanupOverlay()
})

it('renders visible labels and supports real canvas vertex and resize handles', () => {
  const record = polygonRecord()
  const store = createAnnotationStore({ slideId: 'slide-1' })
  store.load({ version: 1, layers: [layer], annotations: [record] })
  store.select([record.id])
  store.setTool('select')
  const viewer = mockViewer()
  const cleanupOverlay = attachAnnotationOverlay(viewer, {
    store,
    activeLayerId: () => layer.id,
    style: () => record.style,
    metadata: () => record.metadata,
    text: () => 'Callout',
  })
  const overlay = viewer.canvas.querySelector('.annotation-svg-overlay')!

  expect(overlay.querySelector('[data-annotation-label]')?.textContent).toContain('Tumour boundary')
  const vertex = overlay.querySelector<SVGElement>(
    '[data-annotation-handle="vertex"][data-vertex-index="0"]',
  )!
  expect(vertex).toHaveAttribute('role', 'button')
  expect(vertex).toHaveAttribute('aria-label', 'Move vertex 1 of Tumour boundary')
  expect(vertex.querySelector('.annotation-canvas-handle-hit')).toHaveAttribute('r', '22')
  const touchDown = new MouseEvent('pointerdown', {
    bubbles: true,
    clientX: 10,
    clientY: 10,
  })
  Object.defineProperty(touchDown, 'pointerType', { value: 'touch' })
  vertex.dispatchEvent(touchDown)
  const touchMove = new MouseEvent('pointermove', {
    bubbles: true,
    clientX: 20,
    clientY: 25,
  })
  Object.defineProperty(touchMove, 'pointerType', { value: 'touch' })
  overlay.dispatchEvent(touchMove)
  const touchUp = new MouseEvent('pointerup', {
    bubbles: true,
    clientX: 20,
    clientY: 25,
  })
  Object.defineProperty(touchUp, 'pointerType', { value: 'touch' })
  overlay.dispatchEvent(touchUp)
  const edited = store.getState().annotations.get(record.id)?.geometry
  expect(edited?.type).toBe('polygon')
  if (edited?.type !== 'polygon') throw new Error('Expected the selected polygon to remain a polygon')
  expect(edited.points).toEqual([
    { x: 20, y: 25 },
    { x: 110, y: 10 },
    { x: 110, y: 110 },
    { x: 10, y: 110 },
  ])

  const resize = overlay.querySelector<SVGElement>(
    '[data-annotation-handle="resize-se"]',
  )!
  expect(resize).toHaveAttribute('role', 'button')
  expect(resize).toHaveAttribute('aria-label', 'Resize Tumour boundary from bottom right')
  expect(resize.querySelector('.annotation-canvas-handle-hit')).toMatchObject({
    tagName: 'rect',
  })
  expect(resize.querySelector('.annotation-canvas-handle-hit')).toHaveAttribute('width', '44')
  expect(resize.querySelector('.annotation-canvas-handle-hit')).toHaveAttribute('height', '44')
  resize.dispatchEvent(new MouseEvent('pointerdown', {
    bubbles: true,
    clientX: 110,
    clientY: 110,
  }))
  overlay.dispatchEvent(new MouseEvent('pointermove', {
    bubbles: true,
    clientX: 150,
    clientY: 160,
  }))
  overlay.dispatchEvent(new MouseEvent('pointerup', {
    bubbles: true,
    clientX: 150,
    clientY: 160,
  }))
  expect(store.getState().annotations.get(record.id)?.bounds).toMatchObject({
    maxX: 150,
    maxY: 160,
  })

  store.update(record.id, { style: { ...record.style, labelVisible: false } })
  expect(overlay.querySelector('[data-annotation-label]')).toBeNull()
  cleanupOverlay()
})

it('uses atomic brush semantics for a selected ROI and cancels gestures without committing', async () => {
  const record = polygonRecord()
  const store = createAnnotationStore({ slideId: 'slide-1' })
  store.load({ version: 1, layers: [layer], annotations: [record] })
  store.select([record.id])
  const brush = vi.spyOn(store, 'brush').mockResolvedValue([record.id])
  const viewer = mockViewer()
  const cleanupOverlay = attachAnnotationOverlay(viewer, {
    store,
    activeLayerId: () => layer.id,
    style: () => record.style,
    metadata: () => record.metadata,
    text: () => 'Callout',
  })
  const overlay = viewer.canvas.querySelector('.annotation-svg-overlay')!

  store.setTool('brush-subtract')
  overlay.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, clientX: 20, clientY: 20 }))
  overlay.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 40, clientY: 20 }))
  overlay.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 40, clientY: 40 }))
  overlay.dispatchEvent(new MouseEvent('pointerup', { bubbles: true, clientX: 20, clientY: 40 }))
  await vi.waitFor(() => expect(brush).toHaveBeenCalledWith(
    'subtract',
    record.id,
    expect.objectContaining({ type: 'polygon' }),
  ))
  expect(store.getState().annotations.size).toBe(1)

  store.setTool('rectangle')
  overlay.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, clientX: 200, clientY: 200 }))
  overlay.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 300, clientY: 300 }))
  overlay.dispatchEvent(new MouseEvent('pointercancel', { bubbles: true, clientX: 300, clientY: 300 }))
  expect(store.getState().annotations.size).toBe(1)
  cleanupOverlay()
})

it('maps touch pointers through the rotated viewport transform in image coordinates', () => {
  const store = createAnnotationStore({ slideId: 'slide-1' })
  store.load({ version: 1, layers: [layer], annotations: [] })
  store.setTool('point')
  const viewer = mockViewer({
    toImage: ({ x, y }) => ({ x: y + 100, y: 500 - x }),
    toViewer: ({ x, y }) => ({ x: 500 - y, y: x - 100 }),
  })
  const cleanupOverlay = attachAnnotationOverlay(viewer, {
    store,
    activeLayerId: () => layer.id,
    style: () => polygonRecord().style,
    metadata: () => polygonRecord().metadata,
    text: () => 'Callout',
  })
  const overlay = viewer.canvas.querySelector('.annotation-svg-overlay')!
  const touch = new MouseEvent('pointerdown', {
    bubbles: true,
    clientX: 120,
    clientY: 80,
  })
  Object.defineProperty(touch, 'pointerType', { value: 'touch' })
  overlay.dispatchEvent(touch)

  const created = [...store.getState().annotations.values()][0]
  expect(created.geometry).toEqual({ type: 'point', x: 180, y: 380 })
  const marker = overlay.querySelector('circle')
  expect(marker).toHaveAttribute('cx', '120')
  expect(marker).toHaveAttribute('cy', '80')
  cleanupOverlay()
})

it('coalesces animation frames and preserves mounted SVG child identity', () => {
  let pendingFrame: FrameRequestCallback | null = null
  const requestFrame = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
    pendingFrame = callback
    return 17
  })
  const cancelFrame = vi.spyOn(window, 'cancelAnimationFrame')
  const project = vi.fn((point: { x: number; y: number }) => point)
  const record = polygonRecord()
  const store = createAnnotationStore({ slideId: 'slide-1' })
  store.load({ version: 1, layers: [layer], annotations: [record] })
  const viewer = mockViewer({ toViewer: project })
  const cleanupOverlay = attachAnnotationOverlay(viewer, {
    store,
    activeLayerId: () => layer.id,
    style: () => record.style,
    metadata: () => record.metadata,
    text: () => 'Callout',
  })
  const overlay = viewer.canvas.querySelector('.annotation-svg-overlay')!
  const mounted = overlay.querySelector<SVGGElement>(`[data-annotation-id="${record.id}"]`)!
  const shape = mounted.firstElementChild
  project.mockClear()

  viewer.raiseEvent('animation', {})
  viewer.raiseEvent('animation', {})
  viewer.raiseEvent('animation', {})

  expect(requestFrame).toHaveBeenCalledOnce()
  expect(project).not.toHaveBeenCalled()
  expect(pendingFrame).not.toBeNull()
  pendingFrame!(0)
  expect(project).toHaveBeenCalled()
  expect(overlay.querySelector(`[data-annotation-id="${record.id}"]`)).toBe(mounted)
  expect(mounted.firstElementChild).toBe(shape)

  viewer.raiseEvent('animation', {})
  cleanupOverlay()
  expect(cancelFrame).toHaveBeenCalledWith(17)
})

it('updates tool selection handles without rebuilding the spatial render plan', () => {
  const plan = vi.spyOn(AnnotationSpatialIndex.prototype, 'plan')
  const record = polygonRecord()
  const store = createAnnotationStore({ slideId: 'slide-1' })
  store.load({ version: 1, layers: [layer], annotations: [record] })
  const viewer = mockViewer()
  const cleanupOverlay = attachAnnotationOverlay(viewer, {
    store,
    activeLayerId: () => layer.id,
    style: () => record.style,
    metadata: () => record.metadata,
    text: () => 'Callout',
  })
  plan.mockClear()

  store.setTool('select')
  store.select([record.id])

  expect(plan).not.toHaveBeenCalled()
  expect(viewer.canvas.querySelectorAll('[data-annotation-handle="vertex"]')).toHaveLength(4)
  cleanupOverlay()
})

it('keeps 25,000-item animation rendering indexed, incremental, and DOM bounded', () => {
  const load = vi.spyOn(AnnotationSpatialIndex.prototype, 'load')
  const records = Array.from({ length: 25_000 }, (_, index): AnnotationRecord => {
    const x = index % 500
    const y = Math.floor(index / 500)
    return {
      ...polygonRecord(`annotation-${index}`),
      geometry: { type: 'point', x, y },
      metadata: { title: '', classification: '', tags: [], notes: '' },
      bounds: { minX: x, minY: y, maxX: x, maxY: y },
    }
  })
  const store = createAnnotationStore({ slideId: 'slide-1' })
  store.load({ version: 1, layers: [layer], annotations: records })
  const viewer = mockViewer()
  const cleanupOverlay = attachAnnotationOverlay(viewer, {
    store,
    activeLayerId: () => layer.id,
    style: () => records[0].style,
    metadata: () => records[0].metadata,
    text: () => 'Callout',
  })
  const overlay = viewer.canvas.querySelector('.annotation-svg-overlay')!

  expect(overlay.querySelectorAll('[data-annotation-id]')).toHaveLength(0)
  expect(overlay.querySelectorAll('.annotation-density-cell').length).toBeLessThanOrEqual(512)
  viewer.raiseEvent('animation', {})
  viewer.raiseEvent('animation', {})
  viewer.raiseEvent('animation', {})
  expect(load).toHaveBeenCalledOnce()
  expect(overlay.querySelectorAll('[data-annotation-id]')).toHaveLength(0)
  cleanupOverlay()
})
