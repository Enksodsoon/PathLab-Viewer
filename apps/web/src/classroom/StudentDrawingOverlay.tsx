import {
  forwardRef,
  type CSSProperties,
  type PointerEvent,
  useCallback,
  useEffect,
  useImperativeHandle,
  useId,
  useRef,
  useState,
} from 'react'

type DrawingTool = 'pen' | 'highlight' | 'eraser'

export interface DrawingPoint {
  x: number
  y: number
}

export interface DrawingStroke {
  id: string
  tool: DrawingTool
  color: string
  width: number
  points: DrawingPoint[]
}

export interface StudentDrawingHandle {
  captureCanvas: () => HTMLCanvasElement | null
  clear: () => void
  hasDrawing: () => boolean
}

const COLORS = ['#ef765f', '#f6c84a', '#42b883', '#4f8be8', '#f6f2e8'] as const
const WIDTHS = [2, 4, 8] as const

export const StudentDrawingOverlay = forwardRef<StudentDrawingHandle, {
  active: boolean
  onDone: () => void
  toolbarLabel?: string
  allowEraser?: boolean
  onStrokeCommitted?: (stroke: DrawingStroke) => void
  onStrokeRemoved?: (strokeId: string) => void
  onClearAll?: () => void
  retainCommitted?: boolean
  showHistoryActions?: boolean
}>(function StudentDrawingOverlay({
  active,
  onDone,
  toolbarLabel = 'Private drawing tools',
  allowEraser = true,
  onStrokeCommitted,
  onStrokeRemoved,
  onClearAll,
  retainCommitted = true,
  showHistoryActions = true,
}, ref) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const strokes = useRef<DrawingStroke[]>([])
  const currentStroke = useRef<DrawingStroke | null>(null)
  const renderFrame = useRef<number | null>(null)
  const maskId = useId().replace(/:/g, '')
  const [tool, setTool] = useState<DrawingTool>('pen')
  const [color, setColor] = useState<string>(COLORS[0])
  const [width, setWidth] = useState<number>(WIDTHS[1])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [revision, setRevision] = useState(0)

  const requestVisibleRender = () => {
    if (renderFrame.current !== null) return
    renderFrame.current = window.requestAnimationFrame(() => {
      renderFrame.current = null
      setRevision((current) => current + 1)
    })
  }

  const redraw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return
    context.clearRect(0, 0, canvas.width, canvas.height)
    context.lineCap = 'round'
    context.lineJoin = 'round'
    for (const stroke of strokes.current) {
      context.globalCompositeOperation = stroke.tool === 'eraser'
        ? 'destination-out'
        : 'source-over'
      context.globalAlpha = stroke.tool === 'highlight' ? 0.42 : 1
      context.strokeStyle = stroke.color
      context.fillStyle = stroke.color
      const toolWidth = stroke.tool === 'highlight'
        ? stroke.width * 4
        : stroke.tool === 'eraser'
          ? stroke.width * 5
          : stroke.width
      context.lineWidth = toolWidth * canvas.width / Math.max(1, canvas.clientWidth)
      const points = stroke.points
      if (!points.length) continue
      if (points.length === 1) {
        context.beginPath()
        context.arc(
          points[0].x * canvas.width,
          points[0].y * canvas.height,
          context.lineWidth / 2,
          0,
          Math.PI * 2,
        )
        context.fill()
        continue
      }
      context.beginPath()
      context.moveTo(points[0].x * canvas.width, points[0].y * canvas.height)
      for (const point of points.slice(1)) {
        context.lineTo(point.x * canvas.width, point.y * canvas.height)
      }
      context.stroke()
    }
    context.globalCompositeOperation = 'source-over'
    context.globalAlpha = 1
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    const container = canvas?.parentElement
    if (!canvas || !container) return
    const resize = () => {
      const bounds = container.getBoundingClientRect()
      const scale = Math.min(window.devicePixelRatio || 1, 2)
      const width = Math.max(1, Math.round(bounds.width * scale))
      const height = Math.max(1, Math.round(bounds.height * scale))
      if (canvas.width === width && canvas.height === height) return
      canvas.width = width
      canvas.height = height
      redraw()
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(container)
    return () => {
      observer.disconnect()
      if (renderFrame.current !== null) window.cancelAnimationFrame(renderFrame.current)
    }
  }, [redraw])

  useImperativeHandle(ref, () => ({
    captureCanvas: () => strokes.current.length ? canvasRef.current : null,
    clear: () => {
      strokes.current = []
      currentStroke.current = null
      redraw()
      setRevision((current) => current + 1)
    },
    hasDrawing: () => strokes.current.length > 0,
  }))

  const pointFromEvent = (event: PointerEvent<HTMLCanvasElement>): DrawingPoint => {
    const bounds = event.currentTarget.getBoundingClientRect()
    return {
      x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
      y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)),
    }
  }

  const begin = (event: PointerEvent<HTMLCanvasElement>) => {
    if (!active) return
    event.preventDefault()
    event.currentTarget.setPointerCapture?.(event.pointerId)
    const stroke = {
      id: crypto.randomUUID(),
      tool,
      color,
      width,
      points: [pointFromEvent(event)],
    }
    strokes.current.push(stroke)
    currentStroke.current = stroke
    redraw()
    requestVisibleRender()
  }

  const move = (event: PointerEvent<HTMLCanvasElement>) => {
    const stroke = currentStroke.current
    if (!active || !stroke) return
    event.preventDefault()
    const coalesced = event.nativeEvent.getCoalescedEvents?.() ?? []
    const samples = coalesced.length ? coalesced : [event.nativeEvent]
    for (const sample of samples) {
      const bounds = event.currentTarget.getBoundingClientRect()
      stroke.points.push({
        x: Math.max(0, Math.min(1, (sample.clientX - bounds.left) / bounds.width)),
        y: Math.max(0, Math.min(1, (sample.clientY - bounds.top) / bounds.height)),
      })
    }
    redraw()
    requestVisibleRender()
  }

  const end = (event: PointerEvent<HTMLCanvasElement>) => {
    const stroke = currentStroke.current
    if (!stroke) return
    event.preventDefault()
    event.currentTarget.releasePointerCapture?.(event.pointerId)
    currentStroke.current = null
    setRevision((current) => current + 1)
    if (stroke.tool !== 'eraser') {
      const stride = Math.max(1, Math.ceil(stroke.points.length / 64))
      const points = stroke.points.filter((_, index) => index % stride === 0)
      const last = stroke.points.at(-1)
      if (last && points.at(-1) !== last) points.push(last)
      onStrokeCommitted?.({ ...stroke, points })
    }
    if (!retainCommitted) {
      strokes.current = strokes.current.filter((item) => item.id !== stroke.id)
      redraw()
      requestVisibleRender()
    }
  }

  const undo = () => {
    const removed = strokes.current.pop()
    if (removed && removed.tool !== 'eraser') onStrokeRemoved?.(removed.id)
    redraw()
    setRevision((current) => current + 1)
  }

  const clear = () => {
    strokes.current = []
    currentStroke.current = null
    onClearAll?.()
    redraw()
    setRevision((current) => current + 1)
  }

  const pathData = (stroke: DrawingStroke) => stroke.points.map((point, index) => (
    `${index ? 'L' : 'M'}${(point.x * 100).toFixed(3)} ${(point.y * 100).toFixed(3)}`
  )).join(' ')

  return <div className={`classroom-drawing${active ? ' is-active' : ''}`}>
    <canvas
      ref={canvasRef}
      aria-label="Private slide drawing canvas"
      onPointerDown={begin}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
    />
    <svg
      className="classroom-drawing-visible"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      data-revision={revision}
      aria-hidden="true"
    >
      <defs><mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100">
        <rect width="100" height="100" fill="white" />
        {strokes.current.filter((stroke) => stroke.tool === 'eraser').map((stroke) => <path
          key={stroke.id}
          d={pathData(stroke)}
          fill="none"
          stroke="black"
          strokeWidth={stroke.width * 5}
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />)}
      </mask></defs>
      <g mask={`url(#${maskId})`}>{strokes.current.filter((stroke) => stroke.tool !== 'eraser').map((stroke) => <path
        key={stroke.id}
        d={pathData(stroke)}
        fill="none"
        stroke={stroke.color}
        strokeWidth={stroke.tool === 'highlight' ? stroke.width * 4 : stroke.width}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={stroke.tool === 'highlight' ? 0.42 : 1}
        vectorEffect="non-scaling-stroke"
      />)}</g>
    </svg>
    {active ? <div className="classroom-drawing-tools" role="toolbar" aria-label={toolbarLabel}>
      {(['pen', 'highlight', ...(allowEraser ? ['eraser'] as const : [])] as DrawingTool[]).map((item) => <button
        key={item}
        className={tool === item ? 'is-active' : ''}
        type="button"
        aria-pressed={tool === item}
        onClick={() => setTool(item)}
      >{item === 'pen' ? 'Pen' : item === 'highlight' ? 'Highlight' : 'Erase'}</button>)}
      <div className="classroom-drawing-colors" role="group" aria-label="Drawing color">
        {COLORS.map((item) => <button
          key={item}
          className={color === item ? 'is-active' : ''}
          type="button"
          aria-label={`Use ${item} color`}
          aria-pressed={color === item}
          style={{ '--drawing-color': item } as CSSProperties}
          onClick={() => setColor(item)}
        />)}
      </div>
      <label className="classroom-drawing-size">Size <select
        aria-label="Drawing size"
        value={width}
        onChange={(event) => setWidth(Number(event.target.value))}
      >{WIDTHS.map((item) => <option key={item} value={item}>{item === 2 ? 'Fine' : item === 4 ? 'Medium' : 'Bold'}</option>)}</select></label>
      {showHistoryActions ? <>
        <button type="button" disabled={!strokes.current.length} onClick={undo}>Undo</button>
        <button type="button" disabled={!strokes.current.length} onClick={clear}>Clear</button>
        <button type="button" disabled={!strokes.current.length} aria-expanded={historyOpen} onClick={() => setHistoryOpen((current) => !current)}>History ({strokes.current.length})</button>
      </> : null}
      <button className="primary" type="button" onClick={onDone}>Done</button>
      {historyOpen && strokes.current.length ? <ol className="classroom-drawing-history" aria-label="Annotation history">
        {[...strokes.current].reverse().map((stroke, index) => <li key={stroke.id}>
          <span style={{ '--drawing-color': stroke.color } as CSSProperties} />
          <strong>{stroke.tool === 'eraser' ? 'Erase' : stroke.tool === 'highlight' ? 'Highlight' : 'Pen'}</strong>
          <small>{stroke.width === 2 ? 'fine' : stroke.width === 4 ? 'medium' : 'bold'} · mark {strokes.current.length - index}</small>
        </li>)}
      </ol> : null}
    </div> : null}
  </div>
})
