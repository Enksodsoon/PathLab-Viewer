import OpenSeadragon from 'openseadragon'

import { createGeometryForTool } from './geometry'
import { AnnotationSpatialIndex } from './spatialIndex'
import type { AnnotationStore } from './store'
import type {
  AnnotationBounds,
  AnnotationGeometry,
  AnnotationInput,
  AnnotationMetadata,
  AnnotationPoint,
  AnnotationRecord,
  AnnotationStyle,
} from './types'

const SVG_NS = 'http://www.w3.org/2000/svg'

export interface AnnotationOverlayOptions {
  store: AnnotationStore
  activeLayerId: () => string | null
  style: () => AnnotationStyle
  metadata: () => AnnotationMetadata
  text: () => string
  onCoordinate?: (point: AnnotationPoint | null) => void
  onDensity?: (prompt: string | null) => void
  onError?: (message: string) => void
}

function svgElement<K extends keyof SVGElementTagNameMap>(
  name: K,
): SVGElementTagNameMap[K] {
  return document.createElementNS(SVG_NS, name)
}

function setAttributes(element: Element, attributes: Record<string, string | number>) {
  for (const [name, value] of Object.entries(attributes)) {
    element.setAttribute(name, String(value))
  }
}

function intersects(left: AnnotationBounds, right: AnnotationBounds): boolean {
  return left.minX <= right.maxX
    && left.maxX >= right.minX
    && left.minY <= right.maxY
    && left.maxY >= right.minY
}

function normalizeBounds(start: AnnotationPoint, end: AnnotationPoint): AnnotationBounds {
  return {
    minX: Math.min(start.x, end.x),
    minY: Math.min(start.y, end.y),
    maxX: Math.max(start.x, end.x),
    maxY: Math.max(start.y, end.y),
  }
}

function imagePoint(
  viewer: OpenSeadragon.Viewer,
  event: PointerEvent | MouseEvent,
): AnnotationPoint {
  const rectangle = viewer.canvas.getBoundingClientRect()
  const point = viewer.viewport.viewerElementToImageCoordinates(new OpenSeadragon.Point(
    event.clientX - rectangle.left,
    event.clientY - rectangle.top,
  ))
  return { x: point.x, y: point.y }
}

function screenPoint(
  viewer: OpenSeadragon.Viewer,
  point: AnnotationPoint,
): OpenSeadragon.Point {
  return viewer.viewport.imageToViewerElementCoordinates(
    new OpenSeadragon.Point(point.x, point.y),
  )
}

function geometryPoints(geometry: AnnotationGeometry): AnnotationPoint[] {
  switch (geometry.type) {
    case 'point':
    case 'text':
      return [{ x: geometry.x, y: geometry.y }]
    case 'rectangle':
      return [
        { x: geometry.x, y: geometry.y },
        { x: geometry.x + geometry.width, y: geometry.y + geometry.height },
      ]
    case 'ellipse':
      return [
        { x: geometry.cx - geometry.rx, y: geometry.cy - geometry.ry },
        { x: geometry.cx + geometry.rx, y: geometry.cy + geometry.ry },
      ]
    case 'angle':
    case 'polyline':
    case 'polygon':
      return geometry.points
  }
}

function shapeFor(
  viewer: OpenSeadragon.Viewer,
  record: AnnotationRecord,
  selected: boolean,
): SVGElement {
  const style = record.style
  let shape: SVGElement
  if (record.geometry.type === 'point') {
    const point = screenPoint(viewer, record.geometry)
    const circle = svgElement('circle')
    setAttributes(circle, { cx: point.x, cy: point.y, r: selected ? 7 : 5 })
    shape = circle
  } else if (record.geometry.type === 'text') {
    const point = screenPoint(viewer, record.geometry)
    const group = svgElement('g')
    const marker = svgElement('circle')
    setAttributes(marker, { cx: point.x, cy: point.y, r: 4 })
    const label = svgElement('text')
    setAttributes(label, { x: point.x + 9, y: point.y - 9 })
    label.textContent = record.geometry.text
    group.append(marker, label)
    shape = group
  } else if (record.geometry.type === 'rectangle') {
    const [start, end] = geometryPoints(record.geometry).map((point) => screenPoint(viewer, point))
    const rectangle = svgElement('rect')
    setAttributes(rectangle, {
      x: Math.min(start.x, end.x),
      y: Math.min(start.y, end.y),
      width: Math.abs(end.x - start.x),
      height: Math.abs(end.y - start.y),
    })
    shape = rectangle
  } else if (record.geometry.type === 'ellipse') {
    const centre = screenPoint(viewer, {
      x: record.geometry.cx,
      y: record.geometry.cy,
    })
    const edge = screenPoint(viewer, {
      x: record.geometry.cx + record.geometry.rx,
      y: record.geometry.cy + record.geometry.ry,
    })
    const ellipse = svgElement('ellipse')
    setAttributes(ellipse, {
      cx: centre.x,
      cy: centre.y,
      rx: Math.abs(edge.x - centre.x),
      ry: Math.abs(edge.y - centre.y),
    })
    shape = ellipse
  } else {
    const path = svgElement(record.geometry.type === 'polygon' ? 'polygon' : 'polyline')
    path.setAttribute(
      'points',
      geometryPoints(record.geometry)
        .map((point) => screenPoint(viewer, point))
        .map((point) => `${point.x},${point.y}`)
        .join(' '),
    )
    shape = path
  }
  shape.setAttribute('data-annotation-id', record.id)
  shape.setAttribute('vector-effect', 'non-scaling-stroke')
  shape.setAttribute('stroke', selected ? '#ffb400' : style.strokeColor)
  shape.setAttribute('stroke-width', String(selected ? Math.max(3, style.strokeWidth) : style.strokeWidth))
  shape.setAttribute('fill', record.geometry.type === 'polyline' || record.geometry.type === 'angle'
    ? 'none'
    : style.fillColor)
  shape.setAttribute('fill-opacity', String(style.opacity * 0.3))
  shape.setAttribute('stroke-opacity', String(style.opacity))
  return shape
}

function viewportBounds(viewer: OpenSeadragon.Viewer): AnnotationBounds {
  const item = viewer.world.getItemAt(0)
  if (!item) {
    return {
      minX: Number.MIN_SAFE_INTEGER,
      minY: Number.MIN_SAFE_INTEGER,
      maxX: Number.MAX_SAFE_INTEGER,
      maxY: Number.MAX_SAFE_INTEGER,
    }
  }
  const rectangle = item.viewportToImageRectangle(viewer.viewport.getBounds(true))
  return {
    minX: rectangle.x,
    minY: rectangle.y,
    maxX: rectangle.x + rectangle.width,
    maxY: rectangle.y + rectangle.height,
  }
}

export function attachAnnotationOverlay(
  viewer: OpenSeadragon.Viewer,
  options: AnnotationOverlayOptions,
): () => void {
  const { store } = options
  const svg = svgElement('svg')
  svg.classList.add('annotation-svg-overlay')
  svg.setAttribute('aria-label', 'Slide annotations')
  svg.setAttribute('role', 'img')
  const index = new AnnotationSpatialIndex()
  let state = store.getState()
  let gestureStart: AnnotationPoint | null = null
  let gestureLast: AnnotationPoint | null = null
  let gestureTarget: string | null = null
  let construction: AnnotationPoint[] = []
  let disposed = false

  viewer.canvas.append(svg)

  const setNavigation = () => {
    const navigation = state.tool === 'hand'
    viewer.setMouseNavEnabled(navigation)
    viewer.setKeyboardNavEnabled(navigation)
    svg.style.pointerEvents = navigation ? 'none' : 'auto'
  }

  const render = () => {
    if (disposed) return
    try {
      const visible = store.visibleAnnotations()
      index.load(visible)
      const plan = index.plan(viewportBounds(viewer))
      svg.replaceChildren()
      const selected = state.selection
      for (const record of plan.mounted) {
        const layer = state.layers.get(record.layerId)
        const group = svgElement('g')
        group.style.opacity = String(layer?.opacity ?? 1)
        group.append(shapeFor(viewer, record, selected.has(record.id)))
        svg.append(group)
      }
      if (plan.density.enabled) {
        for (const cell of plan.density.cells.slice(0, 512)) {
          const marker = svgElement('circle')
          setAttributes(marker, {
            cx: ((cell.x + 0.5) / 32) * Math.max(1, viewer.canvas.clientWidth),
            cy: ((cell.y + 0.5) / 32) * Math.max(1, viewer.canvas.clientHeight),
            r: Math.min(10, 2 + Math.log2(cell.count + 1)),
          })
          marker.classList.add('annotation-density-cell')
          svg.append(marker)
        }
      }
      options.onDensity?.(plan.prompt)
      setNavigation()
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Annotation overlay failed'
      options.onError?.(message)
      viewer.setMouseNavEnabled(true)
      viewer.setKeyboardNavEnabled(true)
      svg.style.pointerEvents = 'none'
    }
  }

  const create = (geometry: AnnotationGeometry) => {
    const layerId = options.activeLayerId()
    if (!layerId) return
    const input: AnnotationInput = {
      id: crypto.randomUUID(),
      layerId,
      geometry,
      style: options.style(),
      metadata: options.metadata(),
    }
    store.create(input)
  }

  const finishConstruction = () => {
    if (construction.length === 0) return
    try {
      const geometry = createGeometryForTool(state.tool, construction, {
        text: options.text(),
      })
      if (geometry) create(geometry)
    } catch {
      // Incomplete multi-click constructions remain editable until enough points exist.
    }
    construction = []
  }

  const onPointerDown = (event: PointerEvent) => {
    if (state.tool === 'hand') return
    const point = imagePoint(viewer, event)
    options.onCoordinate?.(point)
    gestureStart = point
    gestureLast = point
    const target = (event.target as Element | null)?.closest<SVGElement>('[data-annotation-id]')
    gestureTarget = target?.dataset.annotationId ?? null
    if (state.tool === 'select') {
      if (gestureTarget) store.select([gestureTarget], event.shiftKey)
      else if (!event.shiftKey) store.clearSelection()
    } else if (state.tool === 'point') {
      const geometry = createGeometryForTool('point', [point])
      if (geometry) create(geometry)
    } else if (state.tool === 'text') {
      const geometry = createGeometryForTool('text', [point], { text: options.text() })
      if (geometry) create(geometry)
    } else if (state.tool === 'angle' || state.tool === 'polygon' || state.tool === 'polyline') {
      construction.push(point)
      if (state.tool === 'angle' && construction.length === 3) finishConstruction()
    } else if (
      state.tool === 'freehand'
      || state.tool === 'brush-add'
      || state.tool === 'brush-subtract'
    ) {
      construction = [point]
    }
    svg.setPointerCapture?.(event.pointerId)
    event.preventDefault()
  }

  const onPointerMove = (event: PointerEvent) => {
    const point = imagePoint(viewer, event)
    options.onCoordinate?.(point)
    if (!gestureStart) return
    if (
      state.tool === 'freehand'
      || state.tool === 'brush-add'
      || state.tool === 'brush-subtract'
    ) {
      const previous = construction.at(-1)
      if (!previous || Math.hypot(point.x - previous.x, point.y - previous.y) >= 1) {
        construction.push(point)
      }
    }
    gestureLast = point
  }

  const onPointerUp = (event: PointerEvent) => {
    if (!gestureStart || !gestureLast) return
    try {
      if (
        state.tool === 'rectangle'
        || state.tool === 'ellipse'
        || state.tool === 'ruler'
      ) {
        const geometry = createGeometryForTool(state.tool, [gestureStart, gestureLast])
        if (geometry) create(geometry)
      } else if (state.tool === 'marquee') {
        const bounds = normalizeBounds(gestureStart, gestureLast)
        const ids = store.visibleAnnotations()
          .filter((record) => intersects(record.bounds, bounds))
          .map((record) => record.id)
        store.select(ids, event.shiftKey)
      } else if (
        state.tool === 'select'
        && gestureTarget
        && (gestureLast.x !== gestureStart.x || gestureLast.y !== gestureStart.y)
      ) {
        store.move(state.selection, gestureLast.x - gestureStart.x, gestureLast.y - gestureStart.y)
      } else if (
        state.tool === 'freehand'
        || state.tool === 'brush-add'
        || state.tool === 'brush-subtract'
      ) {
        finishConstruction()
      }
    } catch (caught) {
      options.onError?.(caught instanceof Error ? caught.message : 'Annotation gesture failed')
    } finally {
      gestureStart = null
      gestureLast = null
      gestureTarget = null
      svg.releasePointerCapture?.(event.pointerId)
    }
  }

  const onDoubleClick = (event: MouseEvent) => {
    if (state.tool === 'polygon' || state.tool === 'polyline') {
      if (construction.length > 0) {
        construction[construction.length - 1] = imagePoint(viewer, event)
      }
      finishConstruction()
      event.preventDefault()
    }
  }

  const onPointerLeave = () => options.onCoordinate?.(null)
  const onViewerUpdate = () => render()
  svg.addEventListener('pointerdown', onPointerDown)
  svg.addEventListener('pointermove', onPointerMove)
  svg.addEventListener('pointerup', onPointerUp)
  svg.addEventListener('pointercancel', onPointerUp)
  svg.addEventListener('pointerleave', onPointerLeave)
  svg.addEventListener('dblclick', onDoubleClick)
  viewer.addHandler('animation', onViewerUpdate)
  viewer.addHandler('resize', onViewerUpdate)
  viewer.addHandler('open', onViewerUpdate)
  const unsubscribe = store.subscribe((next) => {
    state = next
    render()
  })
  render()

  return () => {
    if (disposed) return
    disposed = true
    unsubscribe()
    svg.removeEventListener('pointerdown', onPointerDown)
    svg.removeEventListener('pointermove', onPointerMove)
    svg.removeEventListener('pointerup', onPointerUp)
    svg.removeEventListener('pointercancel', onPointerUp)
    svg.removeEventListener('pointerleave', onPointerLeave)
    svg.removeEventListener('dblclick', onDoubleClick)
    viewer.removeHandler('animation', onViewerUpdate)
    viewer.removeHandler('resize', onViewerUpdate)
    viewer.removeHandler('open', onViewerUpdate)
    svg.remove()
    viewer.setMouseNavEnabled(true)
    viewer.setKeyboardNavEnabled(true)
    options.onCoordinate?.(null)
    options.onDensity?.(null)
  }
}
