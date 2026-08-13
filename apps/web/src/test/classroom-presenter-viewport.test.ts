import type OpenSeadragon from 'openseadragon'
import { describe, expect, it, vi } from 'vitest'

import { applyPresenterViewport, readPresenterViewport } from '../classroom/presenterViewport'

function viewer(currentZoom = 4, viewportZoomPerImageZoom = 2) {
  const item = {
    source: { dimensions: { x: 2000, y: 1000 } },
    viewportToImageCoordinates: vi.fn(() => ({ x: 1000, y: 500 })),
    viewportToImageZoom: vi.fn((zoom: number) => zoom / viewportZoomPerImageZoom),
    imageToViewportCoordinates: vi.fn(() => ({ x: 0.25, y: 0.125 })),
    imageToViewportZoom: vi.fn((zoom: number) => zoom * viewportZoomPerImageZoom),
  }
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
      world: { getItemAt: vi.fn(() => item) },
    } as unknown as OpenSeadragon.Viewer,
    viewport,
    item,
  }
}

describe('classroom presenter viewport', () => {
  it('publishes image zoom so different screen sizes share one magnification', () => {
    const target = viewer()
    expect(readPresenterViewport(target.value, 'slide-1')).toEqual({
      slideId: 'slide-1', x: 0.5, y: 0.5, zoom: 2, zoomSpace: 'image',
    })
    expect(target.item.viewportToImageZoom).toHaveBeenCalledWith(4)
    expect(target.item.viewportToImageCoordinates).toHaveBeenCalledWith({ x: 0.5, y: 0.5 })
  })

  it('clamps transient out-of-image centers and invalid zoom before sharing', () => {
    const target = viewer()
    target.item.viewportToImageCoordinates.mockReturnValue({ x: -120, y: 1400 })
    target.viewport.getZoom.mockReturnValue(Number.POSITIVE_INFINITY)
    expect(readPresenterViewport(target.value, 'slide-1')).toEqual({
      slideId: 'slide-1', x: 0, y: 1, zoom: 1, zoomSpace: 'image',
    })
  })

  it('pans without restarting zoom or applying receiver-specific constraints', () => {
    const target = viewer(4)
    applyPresenterViewport(target.value, { width: 2000, height: 1000 }, {
      x: 0.6, y: 0.4, zoom: 4, zoomSpace: 'viewport',
    })
    expect(target.viewport.zoomTo).not.toHaveBeenCalled()
    expect(target.item.imageToViewportCoordinates).toHaveBeenCalled()
    expect(target.viewport.panTo).toHaveBeenCalledWith({ x: 0.25, y: 0.125 }, true)
    expect(target.viewport.applyConstraints).not.toHaveBeenCalled()
  })

  it('preserves an edge position when the receiving viewer has a different aspect ratio', () => {
    const target = viewer(3)
    applyPresenterViewport(target.value, { width: 2000, height: 1000 }, {
      x: 0.92, y: 0.08, zoom: 3, zoomSpace: 'viewport',
    })
    expect(target.item.imageToViewportCoordinates).toHaveBeenCalledWith(1840, 80)
    expect(target.viewport.panTo).toHaveBeenCalledWith({ x: 0.25, y: 0.125 }, true)
    expect(target.viewport.applyConstraints).not.toHaveBeenCalled()
  })

  it('converts image zoom for each receiver and accepts legacy viewport zoom', () => {
    const imageTarget = viewer(2)
    applyPresenterViewport(imageTarget.value, { width: 2000, height: 1000 }, {
      x: 0.5, y: 0.5, zoom: 2, zoomSpace: 'image',
    })
    expect(imageTarget.item.imageToViewportZoom).toHaveBeenCalledWith(2)
    expect(imageTarget.viewport.zoomTo).toHaveBeenCalledWith(4, { x: 0.25, y: 0.125 }, true)

    const wideTarget = viewer(2, 3)
    applyPresenterViewport(wideTarget.value, { width: 2000, height: 1000 }, {
      x: 0.5, y: 0.5, zoom: 2, zoomSpace: 'image',
    })
    expect(wideTarget.viewport.zoomTo).toHaveBeenCalledWith(6, { x: 0.25, y: 0.125 }, true)

    const legacyTarget = viewer(2)
    applyPresenterViewport(legacyTarget.value, { width: 2000, height: 1000 }, {
      x: 0.5, y: 0.5, zoom: 3,
    })
    expect(legacyTarget.viewport.imageToViewportZoom).not.toHaveBeenCalled()
    expect(legacyTarget.viewport.zoomTo).toHaveBeenCalledWith(3, { x: 0.25, y: 0.125 }, true)
  })
})
