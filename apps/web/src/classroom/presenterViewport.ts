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
  const item = viewer.world.getItemAt(0)
  const viewportCenter = viewer.viewport.getCenter(true)
  const center = item
    ? item.viewportToImageCoordinates(viewportCenter)
    : viewer.viewport.viewportToImageCoordinates(viewportCenter)
  const dimensions = item?.source.dimensions
  const normalizedX = dimensions ? center.x / dimensions.x : 0.5
  const normalizedY = dimensions ? center.y / dimensions.y : 0.5
  const viewportZoom = viewer.viewport.getZoom(true)
  const zoom = item
    ? item.viewportToImageZoom(viewportZoom)
    : viewer.viewport.viewportToImageZoom(viewportZoom)
  return {
    slideId,
    // OpenSeadragon can briefly report a center beyond the image while an
    // animated constraint settles. Keep the wire contract valid during that
    // frame instead of surfacing an avoidable 422 to the teacher.
    x: Number.isFinite(normalizedX) ? Math.max(0, Math.min(1, normalizedX)) : 0.5,
    y: Number.isFinite(normalizedY) ? Math.max(0, Math.min(1, normalizedY)) : 0.5,
    zoom: Number.isFinite(zoom) ? Math.max(0.000001, Math.min(1000, zoom)) : 1,
    zoomSpace: 'image',
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
  const targetZoom = viewport.zoomSpace === 'image'
    ? item?.imageToViewportZoom(viewport.zoom) ?? viewer.viewport.imageToViewportZoom(viewport.zoom)
    : viewport.zoom
  const currentZoom = viewer.viewport.getZoom(true)
  const relativeDelta = Math.abs(Math.log(targetZoom / currentZoom))
  if (Number.isFinite(relativeDelta) && relativeDelta > 0.001) {
    viewer.viewport.zoomTo(targetZoom, point, true)
  }
  viewer.viewport.panTo(point, true)
  // The presenter center is already clamped to the image on the wire. Applying
  // local viewport constraints here would move that center again according to
  // the receiver's aspect ratio. A tall teacher view and a wide student view
  // would therefore land on different image coordinates near an edge. Preserve
  // the shared center; any extra stage area is preferable to coordinate drift.
}
