import {
  forwardRef,
  type PointerEvent,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'

type DrawingTool = 'pen' | 'highlight' | 'eraser'

interface DrawingPoint {
  x: number
  y: number
}

interface DrawingStroke {
  tool: DrawingTool
  points: DrawingPoint[]
}

export interface StudentDrawingHandle {
  captureCanvas: () => HTMLCanvasElement | null
  clear: () => void
  hasDrawing: () => boolean
}

const TOOL_STYLE: Record<DrawingTool, { color: string; width: number }> = {
  pen: { color: '#ef765f', width: 4 },
  highlight: { color: 'rgb(250 202 64 / 58%)', width: 16 },
  eraser: { color: 'transparent', width: 24 },
}

export const StudentDrawingOverlay = forwardRef<StudentDrawingHandle, {
  active: boolean
  onDone: () => void
}>(function StudentDrawingOverlay({ active, onDone }, ref) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const strokes = useRef<DrawingStroke[]>([])
  const currentStroke = useRef<DrawingStroke | null>(null)
  const [tool, setTool] = useState<DrawingTool>('pen')
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
      const style = TOOL_STYLE[stroke.tool]
      context.globalCompositeOperation = stroke.tool === 'eraser'
        ? 'destination-out'
        : 'source-over'
      context.strokeStyle = style.color
      context.fillStyle = style.color
      context.lineWidth = style.width * canvas.width / Math.max(1, canvas.clientWidth)
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
    return () => observer.disconnect()
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
    event.currentTarget.setPointerCapture(event.pointerId)
    const stroke = { tool, points: [pointFromEvent(event)] }
    strokes.current.push(stroke)
    currentStroke.current = stroke
    redraw()
  }

  const move = (event: PointerEvent<HTMLCanvasElement>) => {
    const stroke = currentStroke.current
    if (!active || !stroke) return
    event.preventDefault()
    stroke.points.push(pointFromEvent(event))
    redraw()
  }

  const end = (event: PointerEvent<HTMLCanvasElement>) => {
    if (!currentStroke.current) return
    event.preventDefault()
    currentStroke.current = null
    setRevision((current) => current + 1)
  }

  const undo = () => {
    strokes.current.pop()
    redraw()
    setRevision((current) => current + 1)
  }

  const clear = () => {
    strokes.current = []
    currentStroke.current = null
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
    {active ? <div className="classroom-drawing-tools" role="toolbar" aria-label="Private drawing tools">
      {(['pen', 'highlight', 'eraser'] as const).map((item) => <button
        key={item}
        className={tool === item ? 'is-active' : ''}
        type="button"
        aria-pressed={tool === item}
        onClick={() => setTool(item)}
      >{item === 'pen' ? 'Pen' : item === 'highlight' ? 'Highlight' : 'Erase'}</button>)}
      <button type="button" disabled={!strokes.current.length} onClick={undo}>Undo</button>
      <button type="button" disabled={!strokes.current.length} onClick={clear}>Clear</button>
      <button className="primary" type="button" onClick={onDone}>Done</button>
    </div> : null}
  </div>
})
