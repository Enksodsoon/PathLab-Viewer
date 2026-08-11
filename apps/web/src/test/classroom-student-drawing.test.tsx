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
    const { rerender } = render(<StudentDrawingOverlay ref={ref} active={false} onDone={done} />)

    expect(screen.queryByRole('toolbar', { name: 'Private drawing tools' })).not.toBeInTheDocument()
    expect(ref.current?.hasDrawing()).toBe(false)

    rerender(<StudentDrawingOverlay ref={ref} active onDone={done} />)
    expect(screen.getByRole('toolbar', { name: 'Private drawing tools' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Highlight' }))
    expect(screen.getByRole('button', { name: 'Highlight' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(done).toHaveBeenCalledOnce()
  })
})
