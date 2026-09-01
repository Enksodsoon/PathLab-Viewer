import { ArrowCounterClockwise, Broom, Camera, Crosshair, Hand, MagnifyingGlassMinus, MagnifyingGlassPlus, PencilSimpleLine, Rectangle, Trash } from '@phosphor-icons/react'
import OpenSeadragon from 'openseadragon'
import { useCallback, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'

import type { DiagnosticSelection } from '../assessment/types'
import { OpenSeadragonViewer, type ViewerAttachmentCallback, type ViewerHandle } from './OpenSeadragonViewer'

interface Props {
  tileSource: string
  selections: DiagnosticSelection[]
  onCommit: (selection: DiagnosticSelection) => void
  onClear?: () => void
  multiple?: boolean
  label: string
  capture?: Extract<DiagnosticSelection, { kind: 'rectangle' }>
  onCapture?: (selection: Extract<DiagnosticSelection, { kind: 'rectangle' }>, image?: CapturedFrame) => void
  onUpdateSelection?: (index: number, selection: DiagnosticSelection) => void
  onDeleteSelection?: (index: number) => void
  authoringLabel?: string
  allowFreehand?: boolean
  showLoadingMode?: boolean
}

export interface CapturedFrame {
  dataUrl: string
  width: number
  height: number
  bytes: number
}

type Tool = 'pan' | 'point' | 'rectangle' | 'freehand'
type NormalizedPoint = { x: number; y: number }
type DrawingTool = Extract<Tool, 'rectangle' | 'freehand'>
type GestureDraft = { tool: DrawingTool; start: NormalizedPoint; points: NormalizedPoint[]; element: HTMLDivElement }

const SVG_NAMESPACE = 'http://www.w3.org/2000/svg'
const MAX_FREEHAND_POINTS = 2048
const CAPTURE_MAX_EDGE = 1600
const CAPTURE_MAX_BYTES = 475 * 1024

function clamp(value: number) {
  return Math.max(0, Math.min(1, value))
}

function rectangleBetween(start: NormalizedPoint, end: NormalizedPoint) {
  const width = Math.abs(end.x - start.x)
  const height = Math.abs(end.y - start.y)
  if (width < 0.006 && height < 0.006) {
    const x = clamp(start.x - 0.05)
    const y = clamp(start.y - 0.05)
    return { kind: 'rectangle' as const, x, y, width: Math.min(0.1, 1 - x), height: Math.min(0.1, 1 - y) }
  }
  const x = Math.min(start.x, end.x)
  const y = Math.min(start.y, end.y)
  return { kind: 'rectangle' as const, x, y, width: Math.max(0.002, Math.min(1 - x, width)), height: Math.max(0.002, Math.min(1 - y, height)) }
}

function freehandBounds(points: NormalizedPoint[]) {
  const xs = points.map((point) => point.x)
  const ys = points.map((point) => point.y)
  const minX = Math.min(...xs)
  const minY = Math.min(...ys)
  const maxX = Math.max(...xs)
  const maxY = Math.max(...ys)
  const padding = 0.003
  const x = clamp(minX - padding)
  const y = clamp(minY - padding)
  return { x, y, width: Math.max(0.006, Math.min(1 - x, maxX - minX + padding * 2)), height: Math.max(0.006, Math.min(1 - y, maxY - minY + padding * 2)) }
}

function setFreehandPath(element: HTMLElement, points: NormalizedPoint[]) {
  const bounds = freehandBounds(points)
  element.querySelector('polyline')?.setAttribute('points', points.map((point) => `${((point.x - bounds.x) / bounds.width) * 100},${((point.y - bounds.y) / bounds.height) * 100}`).join(' '))
  return bounds
}

function makeFreehandElement(className: string) {
  const element = document.createElement('div')
  element.className = className
  const svg = document.createElementNS(SVG_NAMESPACE, 'svg')
  svg.setAttribute('viewBox', '0 0 100 100')
  svg.setAttribute('preserveAspectRatio', 'none')
  svg.setAttribute('aria-hidden', 'true')
  svg.append(document.createElementNS(SVG_NAMESPACE, 'polyline'))
  element.append(svg)
  return element
}

function offsetSelection(selection: DiagnosticSelection, distance = 0.018): DiagnosticSelection {
  if (selection.kind === 'point') return { ...selection, x: clamp(selection.x + distance), y: clamp(selection.y + distance) }
  if (selection.kind === 'rectangle') return { ...selection, x: Math.min(1 - selection.width, clamp(selection.x + distance)), y: Math.min(1 - selection.height, clamp(selection.y + distance)) }
  return { ...selection, points: selection.points.map((point) => ({ x: clamp(point.x + distance), y: clamp(point.y + distance) })) }
}

function canvasBlob(canvas: HTMLCanvasElement, quality: number) {
  return new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/webp', quality))
}

function blobDataUrl(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('CAPTURE_READ_FAILED'))
    reader.onerror = () => reject(new Error('CAPTURE_READ_FAILED'))
    reader.readAsDataURL(blob)
  })
}

function annotationName(selection: DiagnosticSelection, index: number) {
  const label = selection.kind === 'point' ? 'Point' : selection.kind === 'rectangle' ? 'Box' : 'Drawing'
  return `${label} ${index + 1}`
}

export function AssessmentDiagnosticField({
  tileSource,
  selections,
  onCommit,
  onClear,
  label,
  capture,
  onCapture,
  onUpdateSelection,
  onDeleteSelection,
  authoringLabel = 'Slide selection tools',
  allowFreehand = false,
  showLoadingMode = true,
}: Props) {
  const [tool, setTool] = useState<Tool>('pan')
  const [viewerHandle, setViewerHandle] = useState<ViewerHandle | null>(null)
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)
  const gestureRef = useRef<GestureDraft | null>(null)
  const clipboardRef = useRef<DiagnosticSelection | null>(null)
  const redoRef = useRef<DiagnosticSelection[]>([])
  const [captureState, setCaptureState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  const commitSelection = useCallback((selection: DiagnosticSelection) => {
    redoRef.current = []
    onCommit(selection)
  }, [onCommit])

  const normalizedPoint = useCallback((viewportPoint: OpenSeadragon.Point) => {
    const tiledImage = viewerRef.current?.world.getItemAt(0)
    if (!tiledImage) return null
    const imagePoint = tiledImage.viewportToImageCoordinates(viewportPoint)
    const size = tiledImage.getContentSize()
    return { x: clamp(imagePoint.x / size.x), y: clamp(imagePoint.y / size.y) }
  }, [])

  const normalizedPointFromPixel = useCallback((viewer: OpenSeadragon.Viewer, pixel: OpenSeadragon.Point) => normalizedPoint(viewer.viewport.pointFromPixel(pixel)), [normalizedPoint])

  const commitAtViewportPoint = useCallback((viewportPoint: OpenSeadragon.Point, rectangle = false) => {
    const point = normalizedPoint(viewportPoint)
    if (!point) return
    commitSelection(rectangle ? rectangleBetween(point, point) : { kind: 'point', ...point })
  }, [commitSelection, normalizedPoint])

  const attach = useCallback<ViewerAttachmentCallback>((viewer) => {
    viewerRef.current = viewer
    viewer.setMouseNavEnabled(tool === 'pan')
    const overlays: HTMLElement[] = []
    const tiledImage = () => viewer.world.getItemAt(0)
    const addRectangleOverlay = (element: HTMLElement, rectangle: Extract<DiagnosticSelection, { kind: 'rectangle' }>) => {
      const image = tiledImage()
      if (!image) return
      const size = image.getContentSize()
      viewer.addOverlay({ element, location: image.imageToViewportRectangle(new OpenSeadragon.Rect(rectangle.x * size.x, rectangle.y * size.y, rectangle.width * size.x, rectangle.height * size.y)), checkResize: false })
    }
    const addFreehandOverlay = (element: HTMLElement, points: NormalizedPoint[]) => {
      const image = tiledImage()
      if (!image) return
      const size = image.getContentSize()
      const bounds = setFreehandPath(element, points)
      viewer.addOverlay({ element, location: image.imageToViewportRectangle(new OpenSeadragon.Rect(bounds.x * size.x, bounds.y * size.y, bounds.width * size.x, bounds.height * size.y)), checkResize: false })
    }
    const renderOverlays = () => {
      overlays.forEach((element) => viewer.removeOverlay(element))
      overlays.length = 0
      const image = tiledImage()
      if (!image) return
      const size = image.getContentSize()
      if (capture) {
        const element = document.createElement('div')
        element.className = 'assessment-diagnostic-capture'
        element.setAttribute('aria-hidden', 'true')
        viewer.addOverlay({ element, location: image.imageToViewportRectangle(new OpenSeadragon.Rect(capture.x * size.x, capture.y * size.y, capture.width * size.x, capture.height * size.y)), checkResize: false })
        overlays.push(element)
      }
      selections.forEach((selection, index) => {
        const element = selection.kind === 'freehand' ? makeFreehandElement('assessment-diagnostic-freehand') : document.createElement('div')
        if (selection.kind !== 'freehand') element.className = selection.kind === 'point' ? 'assessment-diagnostic-point' : 'assessment-diagnostic-rectangle'
        element.setAttribute('aria-hidden', 'true')
        if (selection.label) element.dataset.label = selection.label
        element.dataset.selectionIndex = String(index)
        if (selection.kind === 'freehand') addFreehandOverlay(element, selection.points)
        else {
          const imageRect = selection.kind === 'point'
            ? new OpenSeadragon.Rect(selection.x * size.x - 8, selection.y * size.y - 8, 16, 16)
            : new OpenSeadragon.Rect(selection.x * size.x, selection.y * size.y, selection.width * size.x, selection.height * size.y)
          viewer.addOverlay({ element, location: image.imageToViewportRectangle(imageRect), checkResize: false })
        }
        overlays.push(element)
      })
    }
    const updateGestureOverlay = (draft: GestureDraft, end: NormalizedPoint) => {
      const image = tiledImage()
      if (!image) return
      const size = image.getContentSize()
      const bounds = draft.tool === 'rectangle' ? rectangleBetween(draft.start, end) : setFreehandPath(draft.element, draft.points)
      viewer.updateOverlay(draft.element, image.imageToViewportRectangle(new OpenSeadragon.Rect(bounds.x * size.x, bounds.y * size.y, bounds.width * size.x, bounds.height * size.y)))
    }
    let animationFrame: number | null = null
    let pendingGestureEnd: NormalizedPoint | null = null
    const scheduleGestureOverlay = (draft: GestureDraft, end: NormalizedPoint) => {
      pendingGestureEnd = end
      if (animationFrame !== null) return
      animationFrame = requestAnimationFrame(() => {
        animationFrame = null
        const pending = pendingGestureEnd
        pendingGestureEnd = null
        if (pending && gestureRef.current === draft) updateGestureOverlay(draft, pending)
      })
    }
    renderOverlays()
    viewer.addHandler('open', renderOverlays)
    const tracker = new OpenSeadragon.MouseTracker({
      element: viewer.canvas,
      clickHandler: (event) => {
        if (tool === 'point' && event.quick) commitAtViewportPoint(viewer.viewport.pointFromPixel(event.position))
      },
      pressHandler: (event) => {
        if (tool !== 'rectangle' && tool !== 'freehand') return
        const point = normalizedPointFromPixel(viewer, event.position)
        if (!point) return
        const element = tool === 'freehand' ? makeFreehandElement('assessment-diagnostic-freehand is-drawing') : document.createElement('div')
        if (tool === 'rectangle') element.className = 'assessment-diagnostic-rectangle is-drawing'
        gestureRef.current = { tool, start: point, points: [point], element }
        if (tool === 'rectangle') addRectangleOverlay(element, rectangleBetween(point, point))
        else addFreehandOverlay(element, [point, { x: clamp(point.x + 0.0001), y: clamp(point.y + 0.0001) }])
      },
      dragHandler: (event) => {
        const draft = gestureRef.current
        if (!draft) return
        const point = normalizedPointFromPixel(viewer, event.position)
        if (!point) return
        if (draft.tool === 'freehand') {
          const last = draft.points[draft.points.length - 1]
          if (draft.points.length < MAX_FREEHAND_POINTS && Math.hypot(point.x - last.x, point.y - last.y) > 0.00065) draft.points.push(point)
        }
        scheduleGestureOverlay(draft, point)
      },
      releaseHandler: (event) => {
        const draft = gestureRef.current
        if (!draft) return
        const point = normalizedPointFromPixel(viewer, event.position) ?? draft.points[draft.points.length - 1]
        if (animationFrame !== null) cancelAnimationFrame(animationFrame)
        animationFrame = null
        pendingGestureEnd = null
        updateGestureOverlay(draft, point)
        viewer.removeOverlay(draft.element)
        gestureRef.current = null
        if (draft.tool === 'rectangle') commitSelection(rectangleBetween(draft.start, point))
        else {
          const points = draft.points.length > 1 ? draft.points : [draft.start, point]
          if (points.length > 1 && Math.hypot(points[0].x - points[points.length - 1].x, points[0].y - points[points.length - 1].y) > 0.002) commitSelection({ kind: 'freehand', points })
        }
      },
    })
    tracker.setTracking(true)
    return () => {
      tracker.destroy()
      if (animationFrame !== null) cancelAnimationFrame(animationFrame)
      viewer.removeHandler('open', renderOverlays)
      if (gestureRef.current) viewer.removeOverlay(gestureRef.current.element)
      gestureRef.current = null
      overlays.forEach((element) => viewer.removeOverlay(element))
      viewer.setMouseNavEnabled(true)
      if (viewerRef.current === viewer) viewerRef.current = null
    }
  }, [capture, commitAtViewportPoint, commitSelection, normalizedPointFromPixel, selections, tool])

  async function capturedFrame(viewer: OpenSeadragon.Viewer, tiledImage: OpenSeadragon.TiledImage): Promise<CapturedFrame | undefined> {
    const sourceCanvas = viewer.canvas.querySelector('canvas')
    if (!(sourceCanvas instanceof HTMLCanvasElement) || sourceCanvas.width === 0 || sourceCanvas.height === 0) return undefined
    const imageBounds = tiledImage.getBounds(true)
    const viewportBounds = viewer.viewport.getBounds(true)
    const left = Math.max(imageBounds.x, viewportBounds.x)
    const top = Math.max(imageBounds.y, viewportBounds.y)
    const right = Math.min(imageBounds.x + imageBounds.width, viewportBounds.x + viewportBounds.width)
    const bottom = Math.min(imageBounds.y + imageBounds.height, viewportBounds.y + viewportBounds.height)
    if (right <= left || bottom <= top) return undefined
    const startPixel = viewer.viewport.pixelFromPoint(new OpenSeadragon.Point(left, top), true)
    const endPixel = viewer.viewport.pixelFromPoint(new OpenSeadragon.Point(right, bottom), true)
    const scaleX = sourceCanvas.width / Math.max(1, viewer.canvas.clientWidth)
    const scaleY = sourceCanvas.height / Math.max(1, viewer.canvas.clientHeight)
    const sourceX = Math.max(0, Math.round(startPixel.x * scaleX))
    const sourceY = Math.max(0, Math.round(startPixel.y * scaleY))
    const sourceWidth = Math.max(1, Math.min(sourceCanvas.width - sourceX, Math.round((endPixel.x - startPixel.x) * scaleX)))
    const sourceHeight = Math.max(1, Math.min(sourceCanvas.height - sourceY, Math.round((endPixel.y - startPixel.y) * scaleY)))
    const outputScale = Math.min(1, CAPTURE_MAX_EDGE / Math.max(sourceWidth, sourceHeight))
    const output = document.createElement('canvas')
    output.width = Math.max(1, Math.round(sourceWidth * outputScale))
    output.height = Math.max(1, Math.round(sourceHeight * outputScale))
    const context = output.getContext('2d', { alpha: false })
    if (!context) return undefined
    context.fillStyle = '#090807'
    context.fillRect(0, 0, output.width, output.height)
    context.imageSmoothingEnabled = true
    context.imageSmoothingQuality = 'high'
    context.drawImage(sourceCanvas, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, output.width, output.height)
    let quality = 0.92
    let blob = await canvasBlob(output, quality)
    while (blob && blob.size > CAPTURE_MAX_BYTES && quality > 0.58) {
      quality -= 0.07
      blob = await canvasBlob(output, quality)
    }
    if (!blob || blob.size > CAPTURE_MAX_BYTES) return undefined
    return { dataUrl: await blobDataUrl(blob), width: output.width, height: output.height, bytes: blob.size }
  }

  async function captureCurrentView() {
    const viewer = viewerRef.current
    const tiledImage = viewer?.world.getItemAt(0)
    if (!viewer || !tiledImage || !onCapture) return
    const size = tiledImage.getContentSize()
    const imageRect = tiledImage.viewportToImageRectangle(viewer.viewport.getBounds(true))
    const x = clamp(imageRect.x / size.x)
    const y = clamp(imageRect.y / size.y)
    const width = Math.max(0.01, Math.min(1 - x, imageRect.width / size.x))
    const height = Math.max(0.01, Math.min(1 - y, imageRect.height / size.y))
    setCaptureState('saving')
    try {
      const image = await capturedFrame(viewer, tiledImage)
      onCapture({ kind: 'rectangle', x, y, width, height }, image)
      setCaptureState('saved')
    } catch {
      onCapture({ kind: 'rectangle', x, y, width, height })
      setCaptureState('error')
    }
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLElement>) {
    const target = event.target as HTMLElement
    if (target.matches('input, textarea, select, [contenteditable="true"]')) return
    const key = event.key.toLocaleLowerCase()
    const command = event.ctrlKey || event.metaKey
    if (command && key === 's' && onCapture) { event.preventDefault(); void captureCurrentView(); return }
    if (command && key === 'z') {
      event.preventDefault()
      if (event.shiftKey) {
        const selection = redoRef.current.pop()
        if (selection) onCommit(selection)
      } else if (onDeleteSelection && selections.length > 0) {
        redoRef.current.push(selections[selections.length - 1])
        onDeleteSelection(selections.length - 1)
      }
      return
    }
    if (command && key === 'c') { event.preventDefault(); clipboardRef.current = selections.at(-1) ?? null; return }
    if (command && key === 'x' && onDeleteSelection && selections.length > 0) {
      event.preventDefault()
      clipboardRef.current = selections.at(-1) ?? null
      onDeleteSelection(selections.length - 1)
      return
    }
    if (command && key === 'v' && clipboardRef.current) { event.preventDefault(); commitSelection(offsetSelection(clipboardRef.current)); return }
    if ((event.key === 'Delete' || event.key === 'Backspace') && onDeleteSelection && selections.length > 0) { event.preventDefault(); onDeleteSelection(selections.length - 1); return }
    if (event.key === 'Escape') { event.preventDefault(); setTool('pan'); return }
    if (key === 'v' || key === 'h' || key === ' ') { event.preventDefault(); setTool('pan') }
    if (key === 'p') { event.preventDefault(); setTool('point') }
    if (key === 'r') { event.preventDefault(); setTool('rectangle') }
    if (key === 'f' && allowFreehand) { event.preventDefault(); setTool('freehand') }
    if (key === '+' || key === '=') { event.preventDefault(); viewerHandle?.zoomIn() }
    if (key === '-') { event.preventDefault(); viewerHandle?.zoomOut() }
    if (key === '0') { event.preventDefault(); viewerHandle?.home() }
  }

  return <section className="assessment-diagnostic-workspace" aria-label={label} tabIndex={0} onKeyDown={handleKeyDown}>
    <div className="assessment-diagnostic-toolbar" role="toolbar" aria-label={authoringLabel}>
      <button type="button" aria-label="Pan or zoom" title="Pan or zoom (V)" aria-pressed={tool === 'pan'} onClick={() => setTool('pan')}><Hand aria-hidden="true" /></button>
      <button type="button" aria-label="Zoom in" title="Zoom in (+)" disabled={!viewerHandle} onClick={() => viewerHandle?.zoomIn()}><MagnifyingGlassPlus aria-hidden="true" /></button>
      <button type="button" aria-label="Zoom out" title="Zoom out (−)" disabled={!viewerHandle} onClick={() => viewerHandle?.zoomOut()}><MagnifyingGlassMinus aria-hidden="true" /></button>
      <button type="button" aria-label="Reset view" title="Reset view (0)" disabled={!viewerHandle} onClick={() => viewerHandle?.home()}><ArrowCounterClockwise aria-hidden="true" /></button>
      <span className="assessment-diagnostic-toolbar-divider" aria-hidden="true" />
      <button type="button" aria-label="Add point" title="Add point (P)" aria-pressed={tool === 'point'} onClick={() => setTool('point')}><Crosshair aria-hidden="true" /></button>
      <button type="button" aria-label="Draw rectangle" title="Draw rectangle (R)" aria-pressed={tool === 'rectangle'} onClick={() => setTool('rectangle')}><Rectangle aria-hidden="true" /></button>
      {allowFreehand ? <button type="button" aria-label="Draw freehand" title="Draw freehand (F)" aria-pressed={tool === 'freehand'} onClick={() => setTool('freehand')}><PencilSimpleLine aria-hidden="true" /></button> : null}
      <span className="assessment-diagnostic-toolbar-spacer" aria-hidden="true" />
      {onCapture ? <button type="button" aria-label="Capture current view" title="Capture current view (Ctrl/Cmd+S)" aria-busy={captureState === 'saving'} onClick={() => void captureCurrentView()}><Camera aria-hidden="true" /></button> : null}
      {onClear ? <button type="button" aria-label="Erase all annotations" title="Erase all annotations" disabled={selections.length === 0} onClick={onClear}><Broom aria-hidden="true" /></button> : null}
    </div>
    <div className="assessment-diagnostic-viewer"><OpenSeadragonViewer tileSource={tileSource} onReady={setViewerHandle} onViewerAttach={attach} showLoadingMode={showLoadingMode} /></div>
    {selections.length > 0 && onUpdateSelection ? <div className="assessment-diagnostic-annotations" aria-label="Annotation labels"><header><strong>Annotation labels</strong><span>Add clear learner-facing text to each mark.</span></header>{selections.map((selection, index) => { const name = annotationName(selection, index); return <label key={index}><span>{name}</span><input aria-label={`${name} label`} maxLength={120} placeholder="Describe this finding" value={selection.label ?? ''} onChange={(event) => onUpdateSelection(index, { ...selection, label: event.target.value || undefined })} />{onDeleteSelection ? <button type="button" aria-label={`Delete ${name.toLocaleLowerCase()}`} onClick={() => onDeleteSelection(index)}><Trash aria-hidden="true" /></button> : null}</label> })}</div> : null}
    <p className="visually-hidden" role="status">{captureState === 'saving' ? 'Saving captured view. ' : captureState === 'saved' ? 'Captured view saved. ' : captureState === 'error' ? 'Capture coordinates saved without a preview image. ' : ''}{capture ? 'Capture region ready. ' : ''}{selections.length} committed annotation{selections.length === 1 ? '' : 's'}.</p>
  </section>
}
