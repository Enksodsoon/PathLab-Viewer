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

type DrawingTool = 'pen' | 'highlight' | 'line' | 'rectangle' | 'ellipse' | 'eraser'

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

const TOOL_LABELS: Record<DrawingTool, string> = {
  pen: 'Pen',
  highlight: 'Highlight',
  line: 'Line',
  rectangle: 'Rectangle',
  ellipse: 'Ellipse',
  eraser: 'Erase',
}

function DrawingToolIcon({ tool }: { tool: DrawingTool | 'done' }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {tool === 'pen' ? <><path d="m4 20 4-1 11-11-3-3L5 16l-1 4Z" /><path d="m14 7 3 3" /></> : null}
    {tool === 'highlight' ? <><path d="m5 15 7-10 5 3-7 10-5-3Z" /><path d="M4 20h15M5 15l5 3" /></> : null}
    {tool === 'line' ? <><path d="M5 19 19 5" /><circle cx="5" cy="19" r="1" fill="currentColor" /><circle cx="19" cy="5" r="1" fill="currentColor" /></> : null}
    {tool === 'rectangle' ? <rect x="4.5" y="6" width="15" height="12" rx="1" /> : null}
    {tool === 'ellipse' ? <ellipse cx="12" cy="12" rx="8" ry="6" /> : null}
    {tool === 'eraser' ? <><path d="m7 18-3-3 9-10 6 6-7 7H7Z" /><path d="m10 8 6 6M11 18h9" /></> : null}
    {tool === 'done' ? <path d="m5 12 4 4L19 6" /> : null}
  </svg>
}

function normalizedPath(stroke: DrawingStroke): string {
  const first = stroke.points[0]
  const last = stroke.points.at(-1)
  if (!first || !last) return ''
  const x1 = first.x * 100
  const y1 = first.y * 100
  const x2 = last.x * 100
  const y2 = last.y * 100
  if (stroke.tool === 'line') return `M${x1} ${y1}L${x2} ${y2}`
  if (stroke.tool === 'rectangle') return `M${x1} ${y1}H${x2}V${y2}H${x1}Z`
  if (stroke.tool === 'ellipse') {
    const cx = (x1 + x2) / 2
    const cy = (y1 + y2) / 2
    const rx = Math.abs(x2 - x1) / 2
    const ry = Math.abs(y2 - y1) / 2
    return `M${cx - rx} ${cy}A${rx} ${ry} 0 1 0 ${cx + rx} ${cy}A${rx} ${ry} 0 1 0 ${cx - rx} ${cy}`
  }
  return stroke.points.map((point, index) => (
    `${index ? 'L' : 'M'}${(point.x * 100).toFixed(3)} ${(point.y * 100).toFixed(3)}`
  )).join(' ')
}

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
      const first = points[0]
      const last = points.at(-1) ?? first
      if (stroke.tool === 'line') {
        context.beginPath()
        context.moveTo(first.x * canvas.width, first.y * canvas.height)
        context.lineTo(last.x * canvas.width, last.y * canvas.height)
        context.stroke()
        continue
      }
      if (stroke.tool === 'rectangle') {
        context.strokeRect(
          first.x * canvas.width,
          first.y * canvas.height,
          (last.x - first.x) * canvas.width,
          (last.y - first.y) * canvas.height,
        )
        continue
      }
      if (stroke.tool === 'ellipse') {
        const left = Math.min(first.x, last.x) * canvas.width
        const top = Math.min(first.y, last.y) * canvas.height
        const shapeWidth = Math.abs(last.x - first.x) * canvas.width
        const shapeHeight = Math.abs(last.y - first.y) * canvas.height
        context.beginPath()
        context.ellipse(
          left + shapeWidth / 2,
          top + shapeHeight / 2,
          shapeWidth / 2,
          shapeHeight / 2,
          0,
          0,
          Math.PI * 2,
        )
        context.stroke()
        continue
      }
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
    if (stroke.tool === 'line' || stroke.tool === 'rectangle' || stroke.tool === 'ellipse') {
      stroke.points = [stroke.points[0], pointFromEvent(event)]
      redraw()
      requestVisibleRender()
      return
    }
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
          d={normalizedPath(stroke)}
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
        d={normalizedPath(stroke)}
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
      {(['pen', 'highlight', 'line', 'rectangle', 'ellipse', ...(allowEraser ? ['eraser'] as const : [])] as DrawingTool[]).map((item) => <button
        key={item}
        className={`classroom-drawing-tool${tool === item ? ' is-active' : ''}`}
        type="button"
        aria-pressed={tool === item}
        aria-label={TOOL_LABELS[item]}
        title={TOOL_LABELS[item]}
        onClick={() => setTool(item)}
      ><DrawingToolIcon tool={item} /></button>)}
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
      <label className="classroom-drawing-size"><span>Stroke</span><select
        aria-label="Drawing size"
        value={width}
        onChange={(event) => setWidth(Number(event.target.value))}
      >{WIDTHS.map((item) => <option key={item} value={item}>{item === 2 ? 'Fine' : item === 4 ? 'Medium' : 'Bold'}</option>)}</select></label>
      {showHistoryActions ? <>
        <button type="button" disabled={!strokes.current.length} onClick={undo}>Undo</button>
        <button type="button" disabled={!strokes.current.length} onClick={clear}>Clear</button>
        <button type="button" disabled={!strokes.current.length} aria-expanded={historyOpen} onClick={() => setHistoryOpen((current) => !current)}>History ({strokes.current.length})</button>
      </> : null}
      <button className="primary classroom-drawing-done" type="button" aria-label="Done" title="Done" onClick={onDone}><DrawingToolIcon tool="done" /></button>
      {historyOpen && strokes.current.length ? <ol className="classroom-drawing-history" aria-label="Annotation history">
        {[...strokes.current].reverse().map((stroke, index) => <li key={stroke.id}>
          <span style={{ '--drawing-color': stroke.color } as CSSProperties} />
          <strong>{TOOL_LABELS[stroke.tool]}</strong>
          <small>{stroke.width === 2 ? 'fine' : stroke.width === 4 ? 'medium' : 'bold'} · mark {strokes.current.length - index}</small>
        </li>)}
      </ol> : null}
    </div> : null}
  </div>
})
