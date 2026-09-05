import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { ApplicationErrorBoundary } from '../components/ApplicationErrorBoundary'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it('offers retry, explicit reload, and library navigation after a render failure', () => {
  let shouldThrow = true
  const reload = vi.fn()
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
  function Content() {
    if (shouldThrow) throw new Error('chunk failed')
    return <p>Recovered page</p>
  }

  render(<ApplicationErrorBoundary resetKey="/admin" reload={reload}><Content /></ApplicationErrorBoundary>)

  expect(screen.getByRole('heading', { name: 'PathLab could not open this page' })).toBeVisible()
  expect(screen.getByRole('link', { name: 'Go to library' })).toHaveAttribute('href', '/admin')
  fireEvent.click(screen.getByRole('button', { name: 'Reload app' }))
  expect(reload).toHaveBeenCalledOnce()

  shouldThrow = false
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(screen.getByText('Recovered page')).toBeVisible()
})
