import {
  ArrowCounterClockwise,
  Check,
  Circle,
  ClockCounterClockwise,
  Eraser,
  Highlighter,
  LineSegment,
  Palette,
  PenNib,
  Rectangle,
  Trash,
} from '@phosphor-icons/react'
import {
  forwardRef,
  type CSSProperties,
  type PointerEvent,
  useCallback,
  useEffect,
  useImperativeHandle,
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
const COLOR_LABELS: Record<(typeof COLORS)[number], string> = {
  '#ef765f': 'Coral',
  '#f6c84a': 'Gold',
  '#42b883': 'Green',
  '#4f8be8': 'Blue',
  '#f6f2e8': 'Ivory',
}
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
  if (tool === 'pen') return <PenNib aria-hidden="true" size={18} />
  if (tool === 'highlight') return <Highlighter aria-hidden="true" size={18} />
  if (tool === 'line') return <LineSegment aria-hidden="true" size={18} />
  if (tool === 'rectangle') return <Rectangle aria-hidden="true" size={18} />
  if (tool === 'ellipse') return <Circle aria-hidden="true" size={18} />
  if (tool === 'eraser') return <Eraser aria-hidden="true" size={18} />
  return <Check aria-hidden="true" size={18} />
}

function DrawingUtilityIcon({ icon }: { icon: 'palette' | 'undo' | 'clear' | 'history' }) {
  if (icon === 'palette') return <Palette aria-hidden="true" size={18} />
  if (icon === 'undo') return <ArrowCounterClockwise aria-hidden="true" size={18} />
  if (icon === 'clear') return <Trash aria-hidden="true" size={18} />
  return <ClockCounterClockwise aria-hidden="true" size={18} />
}

export const StudentDrawingOverlay = forwardRef<StudentDrawingHandle, {
  active: boolean
  onDone: () => void
  toolbarLabel?: string
  allowEraser?: boolean
  onStrokeCommitted?: (stroke: DrawingStroke) => void | boolean | Promise<void | boolean>
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
  const [tool, setTool] = useState<DrawingTool>('pen')
  const [color, setColor] = useState<string>(COLORS[0])
  const [width, setWidth] = useState<number>(WIDTHS[1])
  const [styleOpen, setStyleOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [, setRevision] = useState(0)

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

  const drawIncrement = (
    canvas: HTMLCanvasElement,
    stroke: DrawingStroke,
    from: DrawingPoint,
    to: DrawingPoint,
  ) => {
    const context = canvas.getContext('2d')
    if (!context) return
    context.save()
    context.lineCap = 'round'
    context.lineJoin = 'round'
    context.globalCompositeOperation = stroke.tool === 'eraser' ? 'destination-out' : 'source-over'
    context.globalAlpha = stroke.tool === 'highlight' ? 0.42 : 1
    context.strokeStyle = stroke.color
    context.lineWidth = (stroke.tool === 'highlight' ? stroke.width * 4 : stroke.tool === 'eraser' ? stroke.width * 5 : stroke.width)
      * canvas.width / Math.max(1, canvas.clientWidth)
    context.beginPath()
    context.moveTo(from.x * canvas.width, from.y * canvas.height)
    context.lineTo(to.x * canvas.width, to.y * canvas.height)
    context.stroke()
    context.restore()
  }

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
  }

  const move = (event: PointerEvent<HTMLCanvasElement>) => {
    const stroke = currentStroke.current
    if (!active || !stroke) return
    event.preventDefault()
    if (stroke.tool === 'line' || stroke.tool === 'rectangle' || stroke.tool === 'ellipse') {
      stroke.points = [stroke.points[0], pointFromEvent(event)]
      redraw()
      return
    }
    const coalesced = event.nativeEvent.getCoalescedEvents?.() ?? []
    const samples = coalesced.length ? coalesced : [event.nativeEvent]
    const bounds = event.currentTarget.getBoundingClientRect()
    for (const sample of samples) {
      const previous = stroke.points.at(-1) ?? stroke.points[0]
      const next = {
        x: Math.max(0, Math.min(1, (sample.clientX - bounds.left) / bounds.width)),
        y: Math.max(0, Math.min(1, (sample.clientY - bounds.top) / bounds.height)),
      }
      stroke.points.push(next)
      drawIncrement(event.currentTarget, stroke, previous, next)
    }
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
      const committed = onStrokeCommitted?.({ ...stroke, points })
      if (!retainCommitted) {
        void Promise.resolve(committed).then((accepted) => {
          if (accepted === false) return
          strokes.current = strokes.current.filter((item) => item.id !== stroke.id)
          redraw()
          setRevision((current) => current + 1)
        }).catch(() => undefined)
      }
    } else {
      const committed = onStrokeCommitted?.({ ...stroke })
      if (!retainCommitted) {
        void Promise.resolve(committed).then((accepted) => {
          if (accepted === false) return
          strokes.current = strokes.current.filter((item) => item.id !== stroke.id)
          redraw()
          setRevision((current) => current + 1)
        }).catch(() => undefined)
      }
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

  return <div className={`classroom-drawing${active ? ' is-active' : ''}`} data-tool={tool}>
    <canvas
      ref={canvasRef}
      aria-label="Private slide drawing canvas"
      onPointerDown={begin}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
    />
    {active ? <div className="classroom-drawing-tools" role="toolbar" aria-label={toolbarLabel}>
      <div className="classroom-drawing-cluster classroom-drawing-toolset" role="group" aria-label="Drawing tool">
        {(['pen', 'highlight', 'line', 'rectangle', 'ellipse', ...(allowEraser ? ['eraser'] as const : [])] as DrawingTool[]).map((item) => <button
          key={item}
          className={`classroom-drawing-tool${tool === item ? ' is-active' : ''}`}
          type="button"
          aria-pressed={tool === item}
          aria-label={TOOL_LABELS[item]}
          title={TOOL_LABELS[item]}
          onClick={() => setTool(item)}
        ><DrawingToolIcon tool={item} /></button>)}
      </div>
      <div className="classroom-drawing-style">
        <button
          className="classroom-drawing-style-trigger"
          type="button"
          aria-label={`Drawing style: ${COLOR_LABELS[color as keyof typeof COLOR_LABELS]}, ${width === 2 ? 'fine' : width === 4 ? 'medium' : 'bold'}`}
          aria-expanded={styleOpen}
          title="Color and stroke size"
          onClick={() => setStyleOpen((current) => !current)}
        ><span className="classroom-drawing-style-swatch" style={{ '--drawing-color': color } as CSSProperties} /></button>
        {styleOpen ? <div className="classroom-drawing-style-menu" role="group" aria-label="Drawing style">
          <div className="classroom-drawing-colors" role="group" aria-label="Drawing color">
            {COLORS.map((item) => <button
              key={item}
              className={color === item ? 'is-active' : ''}
              type="button"
              aria-label={`${COLOR_LABELS[item]} drawing color`}
              aria-pressed={color === item}
              title={COLOR_LABELS[item]}
              style={{ '--drawing-color': item } as CSSProperties}
              onClick={() => setColor(item)}
            />)}
          </div>
          <div className="classroom-drawing-widths" role="group" aria-label="Drawing size">
            {WIDTHS.map((item) => <button
              key={item}
              className={width === item ? 'is-active' : ''}
              type="button"
              aria-label={`${item === 2 ? 'Fine' : item === 4 ? 'Medium' : 'Bold'} drawing size`}
              aria-pressed={width === item}
              title={item === 2 ? 'Fine stroke' : item === 4 ? 'Medium stroke' : 'Bold stroke'}
              onClick={() => setWidth(item)}
            ><span style={{ '--stroke-size': `${item === 2 ? 2 : item === 4 ? 4 : 7}px` } as CSSProperties} /></button>)}
          </div>
        </div> : null}
      </div>
      {showHistoryActions ? <>
        <span className="classroom-drawing-separator" />
        <button className="classroom-drawing-action" type="button" aria-label="Undo last mark" title="Undo" disabled={!strokes.current.length} onClick={undo}><DrawingUtilityIcon icon="undo" /></button>
        <button className="classroom-drawing-action" type="button" aria-label="Clear all marks" title="Clear" disabled={!strokes.current.length} onClick={clear}><DrawingUtilityIcon icon="clear" /></button>
        <button className="classroom-drawing-action classroom-drawing-history-trigger" type="button" aria-label={`Annotation history, ${strokes.current.length} marks`} title="History" disabled={!strokes.current.length} aria-expanded={historyOpen} onClick={() => setHistoryOpen((current) => !current)}><DrawingUtilityIcon icon="history" />{strokes.current.length ? <span>{strokes.current.length}</span> : null}</button>
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
