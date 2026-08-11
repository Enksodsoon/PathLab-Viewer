import type OpenSeadragon from 'openseadragon'
import { describe, expect, it, vi } from 'vitest'

import { applyPresenterViewport, readPresenterViewport } from '../classroom/presenterViewport'

function viewer(currentZoom = 4) {
  const viewport = {
    getCenter: vi.fn(() => ({ x: 0.5, y: 0.5 })),
    getZoom: vi.fn(() => currentZoom),
    viewportToImageCoordinates: vi.fn(() => ({ x: 1000, y: 500 })),
    viewportToImageZoom: vi.fn((zoom: number) => zoom / 2),
    imageToViewportCoordinates: vi.fn(() => ({ x: 0.25, y: 0.125 })),
    imageToViewportZoom: vi.fn((zoom: number) => zoom * 2),
    zoomTo: vi.fn(),
    panTo: vi.fn(),
    applyConstraints: vi.fn(),
  }
  return {
    value: {
      viewport,
      world: { getItemAt: vi.fn(() => ({ source: { dimensions: { x: 2000, y: 1000 } } })) },
    } as unknown as OpenSeadragon.Viewer,
    viewport,
  }
}

describe('classroom presenter viewport', () => {
  it('publishes screen-independent image zoom', () => {
    const target = viewer()
    expect(readPresenterViewport(target.value, 'slide-1')).toEqual({
      slideId: 'slide-1', x: 0.5, y: 0.5, zoom: 2, zoomSpace: 'image',
    })
  })

  it('pans without restarting zoom when magnification is unchanged', () => {
    const target = viewer(4)
    applyPresenterViewport(target.value, { width: 2000, height: 1000 }, {
      x: 0.6, y: 0.4, zoom: 2, zoomSpace: 'image',
    })
    expect(target.viewport.zoomTo).not.toHaveBeenCalled()
    expect(target.viewport.panTo).toHaveBeenCalledWith({ x: 0.25, y: 0.125 }, true)
    expect(target.viewport.applyConstraints).toHaveBeenCalledWith(true)
  })

  it('converts changed image zoom once and accepts legacy viewport zoom', () => {
    const imageTarget = viewer(2)
    applyPresenterViewport(imageTarget.value, { width: 2000, height: 1000 }, {
      x: 0.5, y: 0.5, zoom: 2, zoomSpace: 'image',
    })
    expect(imageTarget.viewport.zoomTo).toHaveBeenCalledWith(4, { x: 0.25, y: 0.125 }, true)

    const legacyTarget = viewer(2)
    applyPresenterViewport(legacyTarget.value, { width: 2000, height: 1000 }, {
      x: 0.5, y: 0.5, zoom: 3,
    })
    expect(legacyTarget.viewport.imageToViewportZoom).not.toHaveBeenCalled()
    expect(legacyTarget.viewport.zoomTo).toHaveBeenCalledWith(3, { x: 0.25, y: 0.125 }, true)
  })
})
