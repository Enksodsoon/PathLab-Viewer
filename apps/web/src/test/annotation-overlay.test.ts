import type OpenSeadragon from 'openseadragon'

import { cleanup } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { attachAnnotationOverlay } from '../annotations/AnnotationOverlay'
import { createAnnotationStore } from '../annotations/store'
import type { AnnotationLayer } from '../annotations/types'

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
  const handlers = new Map<string, Set<() => void>>()
  const viewer = {
    canvas,
    viewport: {
      viewerElementToImageCoordinates: (point: { x: number; y: number }) => point,
      imageToViewerElementCoordinates: (point: { x: number; y: number }) => point,
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
  }
  return viewer as unknown as OpenSeadragon.Viewer
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

  expect(onError).toHaveBeenCalledWith('overlay render fault')
  expect(viewer.setMouseNavEnabled).toHaveBeenLastCalledWith(true)
  expect(viewer.setKeyboardNavEnabled).toHaveBeenLastCalledWith(true)
  cleanupOverlay()
})
