import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { createRef } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  StudentDrawingOverlay,
  type StudentDrawingHandle,
} from '../classroom/StudentDrawingOverlay'

describe('StudentDrawingOverlay', () => {
  afterEach(cleanup)

  it('keeps a compact local drawing toolbar behind an explicit mode', () => {
    const ref = createRef<StudentDrawingHandle>()
    const done = vi.fn()
    const committed = vi.fn()
    const { rerender } = render(<StudentDrawingOverlay
      ref={ref}
      active={false}
      onDone={done}
      onStrokeCommitted={committed}
    />)

    expect(screen.queryByRole('toolbar', { name: 'Private drawing tools' })).not.toBeInTheDocument()
    expect(ref.current?.hasDrawing()).toBe(false)

    rerender(<StudentDrawingOverlay
      ref={ref}
      active
      onDone={done}
      onStrokeCommitted={committed}
    />)
    expect(screen.getByRole('toolbar', { name: 'Private drawing tools' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Line' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rectangle' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ellipse' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Highlight' }))
    expect(screen.getByRole('button', { name: 'Highlight' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Private slide drawing canvas').parentElement).toHaveAttribute('data-tool', 'highlight')
    fireEvent.click(screen.getByRole('button', { name: 'Drawing style: Coral, medium' }))
    fireEvent.click(screen.getByRole('button', { name: 'Green drawing color' }))
    expect(screen.getByRole('button', { name: 'Drawing style: Green, medium' })).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Bold drawing size' }))
    expect(screen.getByRole('button', { name: 'Bold drawing size' })).toHaveAttribute('aria-pressed', 'true')

    const canvas = screen.getByLabelText('Private slide drawing canvas')
    fireEvent.pointerDown(canvas, { pointerId: 1, clientX: 10, clientY: 10 })
    fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 30, clientY: 30 })
    fireEvent.pointerUp(canvas, { pointerId: 1, clientX: 30, clientY: 30 })
    expect(ref.current?.hasDrawing()).toBe(true)
    expect(committed).toHaveBeenCalledOnce()
    expect(committed.mock.calls[0][0].points).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Annotation history, 1 marks' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Annotation history, 1 marks' }))
    expect(screen.getByRole('list', { name: 'Annotation history' })).toHaveTextContent('Highlight')
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(done).toHaveBeenCalledOnce()
  })

  it('commits an eraser gesture so shared teaching marks can be removed', () => {
    const committed = vi.fn()
    render(<StudentDrawingOverlay active retainCommitted={false} onDone={vi.fn()} onStrokeCommitted={committed} />)

    fireEvent.click(screen.getByRole('button', { name: 'Erase' }))
    const canvas = screen.getByLabelText('Private slide drawing canvas')
    expect(canvas.parentElement).toHaveAttribute('data-tool', 'eraser')
    fireEvent.pointerDown(canvas, { pointerId: 2, clientX: 10, clientY: 10 })
    fireEvent.pointerMove(canvas, { pointerId: 2, clientX: 30, clientY: 30 })
    fireEvent.pointerUp(canvas, { pointerId: 2, clientX: 30, clientY: 30 })

    expect(committed).toHaveBeenCalledOnce()
    expect(committed.mock.calls[0][0].tool).toBe('eraser')
  })

  it('keeps a transient teaching mark visible until server acceptance', async () => {
    let accept: ((value: boolean) => void) | undefined
    const committed = vi.fn(() => new Promise<boolean>((resolve) => { accept = resolve }))
    const ref = createRef<StudentDrawingHandle>()
    render(<StudentDrawingOverlay
      ref={ref}
      active
      retainCommitted={false}
      onDone={vi.fn()}
      onStrokeCommitted={committed}
    />)

    const canvas = screen.getByLabelText('Private slide drawing canvas')
    fireEvent.pointerDown(canvas, { pointerId: 1, clientX: 10, clientY: 10 })
    fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 30, clientY: 30 })
    fireEvent.pointerUp(canvas, { pointerId: 1, clientX: 30, clientY: 30 })
    expect(ref.current?.hasDrawing()).toBe(true)

    await act(async () => { accept?.(true) })
    expect(ref.current?.hasDrawing()).toBe(false)
  })

  it('draws pen movement incrementally without rerendering the full canvas per sample', () => {
    const canvasContext = {
      beginPath: vi.fn(),
      arc: vi.fn(),
      clearRect: vi.fn(),
      fill: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
    }
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext as unknown as CanvasRenderingContext2D)
    render(<StudentDrawingOverlay active onDone={vi.fn()} />)

    const canvas = screen.getByLabelText('Private slide drawing canvas')
    fireEvent.pointerDown(canvas, { pointerId: 1, clientX: 10, clientY: 10 })
    canvasContext.clearRect.mockClear()
    fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 20, clientY: 20 })
    fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 30, clientY: 30 })

    expect(canvasContext.lineTo).toHaveBeenCalledTimes(2)
    expect(canvasContext.clearRect).not.toHaveBeenCalled()
  })
})
