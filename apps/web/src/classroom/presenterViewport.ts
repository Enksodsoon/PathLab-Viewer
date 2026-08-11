import type OpenSeadragon from 'openseadragon'

export interface SharedPresenterViewport {
  slideId: string
  x: number
  y: number
  zoom: number
  zoomSpace: 'viewport'
}

export function readPresenterViewport(
  viewer: OpenSeadragon.Viewer,
  slideId: string,
): SharedPresenterViewport {
  const item = viewer.world.getItemAt(0)
  const viewportCenter = viewer.viewport.getCenter(true)
  const center = item
    ? item.viewportToImageCoordinates(viewportCenter)
    : viewer.viewport.viewportToImageCoordinates(viewportCenter)
  const dimensions = item?.source.dimensions
  return {
    slideId,
    x: dimensions ? center.x / dimensions.x : 0.5,
    y: dimensions ? center.y / dimensions.y : 0.5,
    zoom: viewer.viewport.getZoom(true),
    zoomSpace: 'viewport',
  }
}

export function applyPresenterViewport(
  viewer: OpenSeadragon.Viewer,
  slide: { width: number; height: number },
  viewport: { x: number; y: number; zoom: number; zoomSpace?: 'image' | 'viewport' },
): void {
  const item = viewer.world.getItemAt(0)
  const imageX = viewport.x * slide.width
  const imageY = viewport.y * slide.height
  const point = item
    ? item.imageToViewportCoordinates(imageX, imageY)
    : viewer.viewport.imageToViewportCoordinates(imageX, imageY)
  // A short-lived local build emitted container-dependent image zoom. Replaying
  // that value on a differently sized viewer misaligns the field, so preserve
  // the receiver's current zoom until the next normalized viewport event.
  if (viewport.zoomSpace !== 'image') {
    const currentZoom = viewer.viewport.getZoom(true)
    const relativeDelta = Math.abs(Math.log(viewport.zoom / currentZoom))
    if (Number.isFinite(relativeDelta) && relativeDelta > 0.001) {
      viewer.viewport.zoomTo(viewport.zoom, point, true)
    }
  }
  viewer.viewport.panTo(point, true)
  viewer.viewport.applyConstraints(true)
}
