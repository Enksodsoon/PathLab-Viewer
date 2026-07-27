import OpenSeadragon from 'openseadragon'

import { createGeometryForTool } from './geometry'
import { AnnotationSpatialIndex, type DensityCell } from './spatialIndex'
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
import { ANNOTATION_ACCENT } from './palette'

const SVG_NS = 'http://www.w3.org/2000/svg'

export interface AnnotationOverlayOptions {
  store: AnnotationStore
  activeLayerId: () => string | null
  style: () => AnnotationStyle
  metadata: () => AnnotationMetadata
  text: () => string
  onCoordinate?: (point: AnnotationPoint | null) => void
  onDensity?: (prompt: string | null) => void
  onNotice?: (message: string) => void
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
  existing?: SVGGElement,
): SVGGElement {
  const root = existing ?? svgElement('g')
  root.replaceChildren()
  root.setAttribute('data-annotation-id', record.id)
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
    group.append(marker)
    if (style.labelVisible) {
      const label = svgElement('text')
      setAttributes(label, { x: point.x + 9, y: point.y - 9 })
      label.setAttribute('data-annotation-label', 'callout')
      label.textContent = record.geometry.text
      group.append(label)
    }
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
  shape.setAttribute('vector-effect', 'non-scaling-stroke')
  shape.setAttribute('stroke', selected ? ANNOTATION_ACCENT : style.strokeColor)
  shape.setAttribute('stroke-width', String(selected ? Math.max(3, style.strokeWidth) : style.strokeWidth))
  shape.setAttribute('fill', record.geometry.type === 'polyline' || record.geometry.type === 'angle'
    ? 'none'
    : style.fillColor)
  shape.setAttribute('fill-opacity', String(style.opacity * 0.3))
  shape.setAttribute('stroke-opacity', String(style.opacity))
  root.append(shape)

  if (
    style.labelVisible
    && record.geometry.type !== 'text'
    && (record.metadata.title || record.metadata.classification)
  ) {
    const anchor = screenPoint(viewer, {
      x: record.bounds.minX,
      y: record.bounds.minY,
    })
    const label = svgElement('text')
    setAttributes(label, { x: anchor.x + 8, y: anchor.y - 8 })
    label.setAttribute('data-annotation-label', 'ordinary')
    label.textContent = record.metadata.title || record.metadata.classification
    root.append(label)
  }

  if (selected) {
    const accessibleName = record.metadata.title
      || record.metadata.classification
      || 'annotation'
    if ('points' in record.geometry) {
      record.geometry.points.forEach((point, index) => {
        const screen = screenPoint(viewer, point)
        const handle = svgElement('g')
        handle.setAttribute('data-annotation-id', record.id)
        handle.setAttribute('data-annotation-handle', 'vertex')
        handle.setAttribute('data-vertex-index', String(index))
        handle.setAttribute('role', 'button')
        handle.setAttribute('tabindex', '0')
        handle.setAttribute(
          'aria-label',
          `Move vertex ${index + 1} of ${accessibleName}`,
        )
        handle.classList.add('annotation-canvas-handle')
        const hit = svgElement('circle')
        setAttributes(hit, { cx: screen.x, cy: screen.y, r: 22 })
        hit.classList.add('annotation-canvas-handle-hit')
        const glyph = svgElement('circle')
        setAttributes(glyph, { cx: screen.x, cy: screen.y, r: 6 })
        glyph.classList.add('annotation-canvas-handle-glyph')
        handle.append(hit, glyph)
        root.append(handle)
      })
    }
    if (
      record.bounds.maxX > record.bounds.minX
      && record.bounds.maxY > record.bounds.minY
    ) {
      const corners = [
        ['resize-nw', record.bounds.minX, record.bounds.minY],
        ['resize-ne', record.bounds.maxX, record.bounds.minY],
        ['resize-se', record.bounds.maxX, record.bounds.maxY],
        ['resize-sw', record.bounds.minX, record.bounds.maxY],
      ] as const
      const cornerNames = {
        'resize-nw': 'top left',
        'resize-ne': 'top right',
        'resize-se': 'bottom right',
        'resize-sw': 'bottom left',
      } as const
      for (const [kind, x, y] of corners) {
        const screen = screenPoint(viewer, { x, y })
        const handle = svgElement('g')
        handle.setAttribute('data-annotation-id', record.id)
        handle.setAttribute('data-annotation-handle', kind)
        handle.setAttribute('role', 'button')
        handle.setAttribute('tabindex', '0')
        handle.setAttribute(
          'aria-label',
          `Resize ${accessibleName} from ${cornerNames[kind]}`,
        )
        handle.classList.add('annotation-canvas-handle')
        const hit = svgElement('rect')
        setAttributes(hit, {
          x: screen.x - 22,
          y: screen.y - 22,
          width: 44,
          height: 44,
        })
        hit.classList.add('annotation-canvas-handle-hit')
        const glyph = svgElement('rect')
        setAttributes(glyph, {
          x: screen.x - 5,
          y: screen.y - 5,
          width: 10,
          height: 10,
          rx: 2,
        })
        glyph.classList.add('annotation-canvas-handle-glyph')
        handle.append(hit, glyph)
        root.append(handle)
      }
    }
  }
  return root
}

function projectShape(
  viewer: OpenSeadragon.Viewer,
  record: AnnotationRecord,
  root: SVGGElement,
): void {
  const shape = root.firstElementChild as SVGElement | null
  if (!shape) return
  if (record.geometry.type === 'point') {
    const point = screenPoint(viewer, record.geometry)
    setAttributes(shape, { cx: point.x, cy: point.y })
  } else if (record.geometry.type === 'text') {
    const point = screenPoint(viewer, record.geometry)
    const marker = shape.querySelector('circle')
    if (marker) setAttributes(marker, { cx: point.x, cy: point.y })
    const label = shape.querySelector('[data-annotation-label="callout"]')
    if (label) setAttributes(label, { x: point.x + 9, y: point.y - 9 })
  } else if (record.geometry.type === 'rectangle') {
    const [start, end] = geometryPoints(record.geometry).map((point) => screenPoint(viewer, point))
    setAttributes(shape, {
      x: Math.min(start.x, end.x),
      y: Math.min(start.y, end.y),
      width: Math.abs(end.x - start.x),
      height: Math.abs(end.y - start.y),
    })
  } else if (record.geometry.type === 'ellipse') {
    const centre = screenPoint(viewer, {
      x: record.geometry.cx,
      y: record.geometry.cy,
    })
    const edge = screenPoint(viewer, {
      x: record.geometry.cx + record.geometry.rx,
      y: record.geometry.cy + record.geometry.ry,
    })
    setAttributes(shape, {
      cx: centre.x,
      cy: centre.y,
      rx: Math.abs(edge.x - centre.x),
      ry: Math.abs(edge.y - centre.y),
    })
  } else {
    shape.setAttribute(
      'points',
      geometryPoints(record.geometry)
        .map((point) => screenPoint(viewer, point))
        .map((point) => `${point.x},${point.y}`)
        .join(' '),
    )
  }

  const label = root.querySelector<SVGElement>('[data-annotation-label="ordinary"]')
  if (label) {
    const anchor = screenPoint(viewer, {
      x: record.bounds.minX,
      y: record.bounds.minY,
    })
    setAttributes(label, { x: anchor.x + 8, y: anchor.y - 8 })
  }
  for (const handle of root.querySelectorAll<SVGElement>('[data-annotation-handle="vertex"]')) {
    const index = Number(handle.dataset.vertexIndex)
    if (!('points' in record.geometry) || !Number.isInteger(index)) continue
    const point = record.geometry.points[index]
    if (!point) continue
    const screen = screenPoint(viewer, point)
    const hit = handle.querySelector<SVGElement>('.annotation-canvas-handle-hit')
    const glyph = handle.querySelector<SVGElement>('.annotation-canvas-handle-glyph')
    if (hit) setAttributes(hit, { cx: screen.x, cy: screen.y })
    if (glyph) setAttributes(glyph, { cx: screen.x, cy: screen.y })
  }
  for (const handle of root.querySelectorAll<SVGElement>('[data-annotation-handle^="resize-"]')) {
    const kind = handle.dataset.annotationHandle ?? ''
    const x = kind.endsWith('w') ? record.bounds.minX : record.bounds.maxX
    const y = kind.includes('-n') ? record.bounds.minY : record.bounds.maxY
    const screen = screenPoint(viewer, { x, y })
    const hit = handle.querySelector<SVGElement>('.annotation-canvas-handle-hit')
    const glyph = handle.querySelector<SVGElement>('.annotation-canvas-handle-glyph')
    if (hit) {
      setAttributes(hit, {
        x: screen.x - 22,
        y: screen.y - 22,
      })
    }
    if (glyph) {
      setAttributes(glyph, {
        x: screen.x - 5,
        y: screen.y - 5,
      })
    }
  }
}

function recordVisible(record: AnnotationRecord, state: ReturnType<AnnotationStore['getState']>) {
  if (record.deletedAt && !state.filter.includeDeleted) return false
  const layer = state.layers.get(record.layerId)
  if (layer && !layer.visible) return false
  if (state.filter.layerIds.size > 0 && !state.filter.layerIds.has(record.layerId)) return false
  if (
    state.filter.classifications
    && state.filter.classifications.size > 0
    && !state.filter.classifications.has(record.metadata.classification)
  ) return false
  if (
    state.filter.tags
    && state.filter.tags.size > 0
    && !record.metadata.tags.some((tag) => state.filter.tags?.has(tag))
  ) return false
  const search = state.filter.search.trim().toLocaleLowerCase()
  if (!search) return true
  return [
    record.metadata.title,
    record.metadata.classification,
    record.metadata.notes,
    ...record.metadata.tags,
  ].some((value) => value.toLocaleLowerCase().includes(search))
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
  let gestureHandle: string | null = null
  let gestureVertexIndex: number | null = null
  let construction: AnnotationPoint[] = []
  let disposed = false
  let frameId: number | null = null
  let draftCursorPoint: AnnotationPoint | null = null
  let temporaryPan = false
  const indexedRecords = new Map<string, AnnotationRecord>()
  const shapeNodes = new Map<string, SVGGElement>()
  const densityNodes = new Map<string, SVGCircleElement>()
  const mountedRecords = new Map<string, AnnotationRecord>()
  const mountedSelection = new Map<string, boolean>()
  const densityCells = new Map<string, DensityCell>()
  const draftRoot = svgElement('g')
  const draftRect = svgElement('rect')
  const draftEllipse = svgElement('ellipse')
  const draftLine = svgElement('line')
  const draftPolyline = svgElement('polyline')
  const draftCursor = svgElement('circle')
  const draftMeasurement = svgElement('text')

  draftRoot.classList.add('annotation-draft')
  draftMeasurement.classList.add('annotation-draft-measurement')
  draftMeasurement.setAttribute('text-anchor', 'middle')
  draftMeasurement.setAttribute('aria-hidden', 'true')
  for (const element of [
    draftRect,
    draftEllipse,
    draftLine,
    draftPolyline,
    draftCursor,
    draftMeasurement,
  ]) {
    element.setAttribute('display', 'none')
    draftRoot.append(element)
  }

  viewer.canvas.append(svg)

  const syncIndex = (
    next: ReturnType<AnnotationStore['getState']>,
    initial = false,
  ) => {
    if (initial) {
      const records = [...next.annotations.values()].filter((record) => !record.deletedAt)
      index.load(records)
      indexedRecords.clear()
      for (const record of records) indexedRecords.set(record.id, record)
      return
    }
    const nextIds = new Set<string>()
    for (const record of next.annotations.values()) {
      nextIds.add(record.id)
      const previous = indexedRecords.get(record.id)
      if (record.deletedAt) {
        if (previous) {
          index.remove(record.id)
          indexedRecords.delete(record.id)
        }
        continue
      }
      if (
        !previous
        || previous.version !== record.version
        || previous.updatedAt !== record.updatedAt
        || previous.layerId !== record.layerId
        || previous.bounds.minX !== record.bounds.minX
        || previous.bounds.minY !== record.bounds.minY
        || previous.bounds.maxX !== record.bounds.maxX
        || previous.bounds.maxY !== record.bounds.maxY
      ) {
        index.upsert(record)
        indexedRecords.set(record.id, record)
      }
    }
    for (const id of [...indexedRecords.keys()]) {
      if (!nextIds.has(id)) {
        index.remove(id)
        indexedRecords.delete(id)
      }
    }
  }
  syncIndex(state, true)

  const setNavigation = () => {
    const navigation = state.tool === 'hand' || temporaryPan
    viewer.setMouseNavEnabled(navigation)
    viewer.setKeyboardNavEnabled(navigation)
    svg.style.pointerEvents = navigation ? 'none' : 'auto'
  }

  const activeToolLabel = () => (
    state.tool
      .split('-')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ')
  )

  const failOpen = (caught: unknown) => {
    const message = caught instanceof Error ? caught.message : 'Annotation overlay failed'
    options.onError?.(message)
    viewer.setMouseNavEnabled(true)
    viewer.setKeyboardNavEnabled(true)
    svg.style.pointerEvents = 'none'
  }

  const draftElements = [draftRect, draftEllipse, draftLine, draftPolyline, draftCursor]

  const hideDraft = () => {
    for (const element of draftElements) {
      element.setAttribute('display', 'none')
      element.classList.remove('annotation-draft-shape')
    }
    draftMeasurement.setAttribute('display', 'none')
    draftMeasurement.textContent = ''
    draftRoot.remove()
  }

  const showDraftShape = (element: SVGElement) => {
    if (!draftRoot.isConnected) svg.append(draftRoot)
    element.removeAttribute('display')
    element.classList.add('annotation-draft-shape')
    const style = options.style()
    element.setAttribute('stroke', style.strokeColor)
    element.setAttribute('stroke-width', String(Math.max(1, style.strokeWidth)))
    element.setAttribute('fill', style.fillColor)
    element.setAttribute('fill-opacity', String(Math.min(0.16, style.opacity * 0.3)))
    element.setAttribute('vector-effect', 'non-scaling-stroke')
    draftRoot.append(element)
    draftRoot.append(draftMeasurement)
  }

  const showMeasurement = (label: string, point: AnnotationPoint) => {
    const projected = screenPoint(viewer, point)
    setAttributes(draftMeasurement, { x: projected.x, y: projected.y - 10 })
    draftMeasurement.textContent = label
    draftMeasurement.removeAttribute('display')
  }

  const renderDraft = () => {
    hideDraft()
    const start = gestureStart
    const end = gestureLast
    if (
      start
      && end
      && (state.tool === 'rectangle' || state.tool === 'marquee')
    ) {
      const bounds = normalizeBounds(start, end)
      const topLeft = screenPoint(viewer, { x: bounds.minX, y: bounds.minY })
      const bottomRight = screenPoint(viewer, { x: bounds.maxX, y: bounds.maxY })
      setAttributes(draftRect, {
        x: topLeft.x,
        y: topLeft.y,
        width: bottomRight.x - topLeft.x,
        height: bottomRight.y - topLeft.y,
      })
      showDraftShape(draftRect)
      showMeasurement(
        `${Math.round(bounds.maxX - bounds.minX)} × ${Math.round(bounds.maxY - bounds.minY)} px`,
        { x: (bounds.minX + bounds.maxX) / 2, y: bounds.minY },
      )
      return
    }
    if (start && end && state.tool === 'ellipse') {
      const bounds = normalizeBounds(start, end)
      const center = screenPoint(viewer, {
        x: (bounds.minX + bounds.maxX) / 2,
        y: (bounds.minY + bounds.maxY) / 2,
      })
      const edge = screenPoint(viewer, { x: bounds.maxX, y: bounds.maxY })
      setAttributes(draftEllipse, {
        cx: center.x,
        cy: center.y,
        rx: Math.abs(edge.x - center.x),
        ry: Math.abs(edge.y - center.y),
      })
      showDraftShape(draftEllipse)
      showMeasurement(
        `${Math.round(bounds.maxX - bounds.minX)} × ${Math.round(bounds.maxY - bounds.minY)} px`,
        { x: (bounds.minX + bounds.maxX) / 2, y: bounds.minY },
      )
      return
    }
    if (start && end && state.tool === 'ruler') {
      const from = screenPoint(viewer, start)
      const to = screenPoint(viewer, end)
      setAttributes(draftLine, { x1: from.x, y1: from.y, x2: to.x, y2: to.y })
      showDraftShape(draftLine)
      showMeasurement(
        `${Math.round(Math.hypot(end.x - start.x, end.y - start.y))} px`,
        { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 },
      )
      return
    }
    const points = [...construction]
    if (
      (state.tool === 'polygon' || state.tool === 'polyline' || state.tool === 'angle')
      && draftCursorPoint
      && points.length > 0
    ) {
      points.push(draftCursorPoint)
    }
    if (points.length > 0) {
      const projected = points.map((point) => screenPoint(viewer, point))
      draftPolyline.setAttribute(
        'points',
        projected.map((point) => `${point.x},${point.y}`).join(' '),
      )
      showDraftShape(draftPolyline)
    }
    if (
      draftCursorPoint
      && (state.tool === 'brush-add' || state.tool === 'brush-subtract')
    ) {
      const projected = screenPoint(viewer, draftCursorPoint)
      setAttributes(draftCursor, { cx: projected.x, cy: projected.y, r: 8 })
      showDraftShape(draftCursor)
    }
  }

  const project = () => {
    if (disposed) return
    try {
      for (const [id, record] of mountedRecords) {
        const node = shapeNodes.get(id)
        if (node) projectShape(viewer, record, node)
      }
      for (const [key, cell] of densityCells) {
        const marker = densityNodes.get(key)
        if (!marker) continue
        const point = screenPoint(viewer, { x: cell.imageX, y: cell.imageY })
        setAttributes(marker, {
          cx: point.x,
          cy: point.y,
          r: Math.min(10, 2 + Math.log2(cell.count + 1)),
        })
      }
      setNavigation()
    } catch (caught) {
      failOpen(caught)
    }
  }

  const renderPlan = () => {
    if (disposed) return
    try {
      const plan = index.plan(
        viewportBounds(viewer),
        (record) => recordVisible(record, state),
      )
      const selected = state.selection
      const mounted = new Set(plan.mounted.map((record) => record.id))
      for (const [id, node] of shapeNodes) {
        if (!mounted.has(id)) {
          node.remove()
          shapeNodes.delete(id)
          mountedRecords.delete(id)
          mountedSelection.delete(id)
        }
      }
      for (const record of plan.mounted) {
        const layer = state.layers.get(record.layerId)
        const existing = shapeNodes.get(record.id)
        const isSelected = selected.has(record.id) && state.tool === 'select'
        const group = (
          !existing
          || mountedRecords.get(record.id) !== record
          || mountedSelection.get(record.id) !== isSelected
        )
          ? shapeFor(viewer, record, isSelected, existing)
          : existing
        group.style.opacity = String(layer?.opacity ?? 1)
        mountedRecords.set(record.id, record)
        mountedSelection.set(record.id, isSelected)
        if (!existing) {
          shapeNodes.set(record.id, group)
          svg.append(group)
        }
      }
      if (plan.density.enabled) {
        const cells = new Set<string>()
        for (const cell of plan.density.cells.slice(0, 512)) {
          const key = `${cell.x}:${cell.y}`
          cells.add(key)
          const marker = densityNodes.get(key) ?? svgElement('circle')
          densityCells.set(key, cell)
          marker.classList.add('annotation-density-cell')
          if (!densityNodes.has(key)) {
            densityNodes.set(key, marker)
            svg.append(marker)
          }
        }
        for (const [key, node] of densityNodes) {
          if (!cells.has(key)) {
            node.remove()
            densityNodes.delete(key)
            densityCells.delete(key)
          }
        }
      } else {
        for (const node of densityNodes.values()) node.remove()
        densityNodes.clear()
        densityCells.clear()
      }
      options.onDensity?.(plan.prompt)
      project()
    } catch (caught) {
      failOpen(caught)
    }
  }

  const scheduleProjection = () => {
    if (disposed || frameId !== null) return
    frameId = window.requestAnimationFrame(() => {
      frameId = null
      project()
      renderDraft()
    })
  }

  const filterKey = (next: ReturnType<AnnotationStore['getState']>) => [
    next.filter.search,
    [...next.filter.layerIds].sort().join(','),
    [...(next.filter.classifications ?? [])].sort().join(','),
    [...(next.filter.tags ?? [])].sort().join(','),
    String(next.filter.includeDeleted),
  ].join('|')

  const layerRenderKey = (next: ReturnType<AnnotationStore['getState']>) => (
    [...next.layers.values()]
      .map((layer) => `${layer.id}:${layer.visible}:${layer.opacity}`)
      .sort()
      .join('|')
  )

  const refreshSelection = (
    previous: ReturnType<AnnotationStore['getState']>,
    next: ReturnType<AnnotationStore['getState']>,
  ) => {
    const candidates = new Set([...previous.selection, ...next.selection])
    for (const id of candidates) {
      const wasSelected = previous.tool === 'select' && previous.selection.has(id)
      const isSelected = next.tool === 'select' && next.selection.has(id)
      if (wasSelected === isSelected) continue
      const record = mountedRecords.get(id)
      const node = shapeNodes.get(id)
      if (!record || !node) continue
      shapeFor(viewer, record, isSelected, node)
      mountedSelection.set(id, isSelected)
    }
    setNavigation()
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
      if (!geometry) return
      create(geometry)
      construction = []
      draftCursorPoint = null
      renderDraft()
    } catch {
      // Incomplete multi-click constructions remain editable until enough points exist.
    }
  }

  const finishBrush = async (tool: 'brush-add' | 'brush-subtract') => {
    const points = construction
    construction = []
    const geometry = createGeometryForTool(tool, points)
    if (!geometry || geometry.type !== 'polygon') return
    const selected = [...state.selection]
      .map((id) => state.annotations.get(id))
      .find((record) => (
        record
        && !record.deletedAt
        && (
          record.geometry.type === 'polygon'
          || record.geometry.type === 'rectangle'
          || record.geometry.type === 'ellipse'
        )
      ))
    if (!selected) {
      if (tool === 'brush-add') create(geometry)
      else options.onNotice?.('Select an editable closed ROI before erasing')
      return
    }
    try {
      await store.brush(tool === 'brush-add' ? 'add' : 'subtract', selected.id, geometry)
    } catch (caught) {
      options.onNotice?.(caught instanceof Error ? caught.message : 'Brush operation failed')
    }
  }

  const clearGesture = () => {
    gestureStart = null
    gestureLast = null
    gestureTarget = null
    gestureHandle = null
    gestureVertexIndex = null
  }

  const onPointerDown = (event: PointerEvent) => {
    if (state.tool === 'hand') return
    const point = imagePoint(viewer, event)
    options.onCoordinate?.(point)
    draftCursorPoint = point
    gestureStart = point
    gestureLast = point
    const eventElement = event.target as Element | null
    const target = eventElement?.closest<SVGElement>('[data-annotation-id]')
    const handle = eventElement?.closest<SVGElement>('[data-annotation-handle]')
    gestureTarget = target?.dataset.annotationId ?? null
    gestureHandle = handle?.dataset.annotationHandle ?? null
    gestureVertexIndex = handle?.dataset.vertexIndex === undefined
      ? null
      : Number(handle.dataset.vertexIndex)
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
      options.onNotice?.(
        state.tool === 'angle'
          ? 'Angle: click 3 points; press Escape to cancel'
          : `${state.tool === 'polygon' ? 'Polygon' : 'Line'}: click next point; double-click or press Enter to finish`,
      )
      if (state.tool === 'angle' && construction.length === 3) finishConstruction()
    } else if (
      state.tool === 'freehand'
      || state.tool === 'brush-add'
      || state.tool === 'brush-subtract'
    ) {
      construction = [point]
    }
    svg.setPointerCapture?.(event.pointerId)
    scheduleProjection()
    event.preventDefault()
  }

  const onPointerMove = (event: PointerEvent) => {
    const point = imagePoint(viewer, event)
    options.onCoordinate?.(point)
    draftCursorPoint = point
    if (!gestureStart) {
      if (construction.length > 0) scheduleProjection()
      return
    }
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
    scheduleProjection()
  }

  const onPointerUp = (event: PointerEvent) => {
    if (!gestureStart || !gestureLast) return
    try {
      if (
        state.tool === 'select'
        && gestureTarget
        && gestureHandle === 'vertex'
        && gestureVertexIndex !== null
      ) {
        store.editVertex(gestureTarget, gestureVertexIndex, gestureLast)
      } else if (
        state.tool === 'select'
        && gestureTarget
        && gestureHandle?.startsWith('resize-')
      ) {
        const record = state.annotations.get(gestureTarget)
        if (record) {
          const corner = gestureHandle.slice('resize-'.length)
          const minimum = 1
          const bounds = record.bounds
          const next = {
            minX: corner.includes('w')
              ? Math.min(gestureLast.x, bounds.maxX - minimum)
              : bounds.minX,
            minY: corner.includes('n')
              ? Math.min(gestureLast.y, bounds.maxY - minimum)
              : bounds.minY,
            maxX: corner.includes('e')
              ? Math.max(gestureLast.x, bounds.minX + minimum)
              : bounds.maxX,
            maxY: corner.includes('s')
              ? Math.max(gestureLast.y, bounds.minY + minimum)
              : bounds.maxY,
          }
          store.resize(record.id, next)
        }
      } else if (
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
      ) {
        finishConstruction()
      } else if (state.tool === 'brush-add' || state.tool === 'brush-subtract') {
        void finishBrush(state.tool)
      }
    } catch (caught) {
      options.onError?.(caught instanceof Error ? caught.message : 'Annotation gesture failed')
    } finally {
      clearGesture()
      if (
        state.tool !== 'polygon'
        && state.tool !== 'polyline'
        && state.tool !== 'angle'
      ) {
        draftCursorPoint = null
      }
      renderDraft()
      svg.releasePointerCapture?.(event.pointerId)
    }
  }

  const onPointerCancel = (event: PointerEvent) => {
    construction = []
    draftCursorPoint = null
    clearGesture()
    renderDraft()
    svg.releasePointerCapture?.(event.pointerId)
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

  const onKeyDown = (event: KeyboardEvent) => {
    const target = event.target
    if (
      target instanceof Element
      && target.matches('input, textarea, select, [contenteditable="true"]')
    ) return
    if (
      (event.code === 'Space' || event.key === ' ')
      && state.tool !== 'hand'
      && !gestureStart
    ) {
      if (!temporaryPan) {
        temporaryPan = true
        draftCursorPoint = null
        renderDraft()
        setNavigation()
        options.onNotice?.(
          `Pan active; release Space to continue ${activeToolLabel()}`,
        )
      }
      event.preventDefault()
      event.stopImmediatePropagation()
      return
    }
    if (event.key === 'Escape' && (construction.length > 0 || gestureStart || draftCursorPoint)) {
      construction = []
      draftCursorPoint = null
      clearGesture()
      renderDraft()
      options.onNotice?.('Drawing cancelled')
      event.preventDefault()
      event.stopImmediatePropagation()
    } else if (event.key === 'Backspace' && construction.length > 0) {
      construction.pop()
      renderDraft()
      options.onNotice?.('Last point removed')
      event.preventDefault()
      event.stopImmediatePropagation()
    } else if (
      event.key === 'Enter'
      && construction.length > 0
      && (state.tool === 'polygon' || state.tool === 'polyline' || state.tool === 'angle')
    ) {
      finishConstruction()
      event.preventDefault()
      event.stopImmediatePropagation()
    }
  }

  const onKeyUp = (event: KeyboardEvent) => {
    if (
      temporaryPan
      && (event.code === 'Space' || event.key === ' ')
    ) {
      temporaryPan = false
      setNavigation()
      options.onNotice?.(`${activeToolLabel()} active`)
      event.preventDefault()
      event.stopImmediatePropagation()
    }
  }

  const onWindowBlur = () => {
    if (!temporaryPan) return
    temporaryPan = false
    setNavigation()
  }

  const onPointerLeave = () => {
    options.onCoordinate?.(null)
    if (!gestureStart) {
      draftCursorPoint = null
      scheduleProjection()
    }
  }
  const onViewerUpdate = () => scheduleProjection()
  const onViewerSettled = () => renderPlan()
  svg.addEventListener('pointerdown', onPointerDown)
  svg.addEventListener('pointermove', onPointerMove)
  svg.addEventListener('pointerup', onPointerUp)
  svg.addEventListener('pointercancel', onPointerCancel)
  svg.addEventListener('pointerleave', onPointerLeave)
  svg.addEventListener('dblclick', onDoubleClick)
  window.addEventListener('keydown', onKeyDown, true)
  window.addEventListener('keyup', onKeyUp, true)
  window.addEventListener('blur', onWindowBlur)
  viewer.addHandler('animation', onViewerUpdate)
  viewer.addHandler('animation-finish', onViewerSettled)
  viewer.addHandler('resize', onViewerSettled)
  viewer.addHandler('open', onViewerSettled)
  const unsubscribe = store.subscribe((next) => {
    const previous = state
    const annotationsChanged = next.annotations !== previous.annotations
    const filterChanged = filterKey(next) !== filterKey(previous)
    const layersChanged = layerRenderKey(next) !== layerRenderKey(previous)
    if (annotationsChanged) syncIndex(next)
    if (next.tool !== previous.tool) {
      construction = []
      draftCursorPoint = null
      clearGesture()
    }
    state = next
    if (annotationsChanged || filterChanged || layersChanged) renderPlan()
    else refreshSelection(previous, next)
    if (next.tool !== previous.tool) renderDraft()
  })
  renderPlan()

  return () => {
    if (disposed) return
    disposed = true
    if (frameId !== null) {
      window.cancelAnimationFrame(frameId)
      frameId = null
    }
    unsubscribe()
    svg.removeEventListener('pointerdown', onPointerDown)
    svg.removeEventListener('pointermove', onPointerMove)
    svg.removeEventListener('pointerup', onPointerUp)
    svg.removeEventListener('pointercancel', onPointerCancel)
    svg.removeEventListener('pointerleave', onPointerLeave)
    svg.removeEventListener('dblclick', onDoubleClick)
    window.removeEventListener('keydown', onKeyDown, true)
    window.removeEventListener('keyup', onKeyUp, true)
    window.removeEventListener('blur', onWindowBlur)
    viewer.removeHandler('animation', onViewerUpdate)
    viewer.removeHandler('animation-finish', onViewerSettled)
    viewer.removeHandler('resize', onViewerSettled)
    viewer.removeHandler('open', onViewerSettled)
    svg.remove()
    viewer.setMouseNavEnabled(true)
    viewer.setKeyboardNavEnabled(true)
    options.onCoordinate?.(null)
    options.onDensity?.(null)
  }
}
