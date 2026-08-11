import { fireEvent, render, screen } from '@testing-library/react'
import { createRef } from 'react'
import { describe, expect, it, vi } from 'vitest'

import {
  StudentDrawingOverlay,
  type StudentDrawingHandle,
} from '../classroom/StudentDrawingOverlay'

describe('StudentDrawingOverlay', () => {
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
    fireEvent.click(screen.getByRole('button', { name: 'Use #42b883 color' }))
    expect(screen.getByRole('button', { name: 'Use #42b883 color' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.change(screen.getByRole('combobox', { name: 'Drawing size' }), { target: { value: '8' } })
    expect(screen.getByRole('combobox', { name: 'Drawing size' })).toHaveValue('8')

    const canvas = screen.getByLabelText('Private slide drawing canvas')
    fireEvent.pointerDown(canvas, { pointerId: 1, clientX: 10, clientY: 10 })
    fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 30, clientY: 30 })
    fireEvent.pointerUp(canvas, { pointerId: 1, clientX: 30, clientY: 30 })
    expect(ref.current?.hasDrawing()).toBe(true)
    expect(committed).toHaveBeenCalledOnce()
    expect(committed.mock.calls[0][0].points).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'History (1)' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'History (1)' }))
    expect(screen.getByRole('list', { name: 'Annotation history' })).toHaveTextContent('Highlight')
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(done).toHaveBeenCalledOnce()
  })
})
