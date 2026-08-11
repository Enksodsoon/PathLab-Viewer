import type OpenSeadragon from 'openseadragon'

export interface SharedPresenterViewport {
  slideId: string
  x: number
  y: number
  zoom: number
  zoomSpace: 'image'
}

export function readPresenterViewport(
  viewer: OpenSeadragon.Viewer,
  slideId: string,
): SharedPresenterViewport {
  const center = viewer.viewport.viewportToImageCoordinates(viewer.viewport.getCenter(true))
  const dimensions = viewer.world.getItemAt(0)?.source.dimensions
  return {
    slideId,
    x: dimensions ? center.x / dimensions.x : 0.5,
    y: dimensions ? center.y / dimensions.y : 0.5,
    zoom: viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom(true)),
    zoomSpace: 'image',
  }
}

export function applyPresenterViewport(
  viewer: OpenSeadragon.Viewer,
  slide: { width: number; height: number },
  viewport: { x: number; y: number; zoom: number; zoomSpace?: 'image' | 'viewport' },
): void {
  const point = viewer.viewport.imageToViewportCoordinates(
    viewport.x * slide.width,
    viewport.y * slide.height,
  )
  const targetZoom = viewport.zoomSpace === 'image'
    ? viewer.viewport.imageToViewportZoom(viewport.zoom)
    : viewport.zoom
  const currentZoom = viewer.viewport.getZoom(true)
  const relativeDelta = Math.abs(Math.log(targetZoom / currentZoom))
  if (Number.isFinite(relativeDelta) && relativeDelta > 0.001) {
    viewer.viewport.zoomTo(targetZoom, point, true)
  }
  viewer.viewport.panTo(point, true)
  viewer.viewport.applyConstraints(true)
}
