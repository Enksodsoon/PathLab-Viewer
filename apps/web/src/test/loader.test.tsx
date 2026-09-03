import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Loader } from '../components/Loader'

describe('PathLab loader', () => {
  it('renders the shared CSS loader with an accessible status label', () => {
    const { container } = render(
      <Loader label="Loading slides…" size="large" fullscreen />,
    )

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Loading slides…')
    expect(status).toHaveClass(
      'pathlab-loader--large',
      'pathlab-loader--fullscreen',
    )
    expect(container.querySelector('.pathlab-loader__indicator')).toBeInTheDocument()
    expect(container.querySelector('svg')).not.toBeInTheDocument()
  })

  it('supports a compact inline treatment without changing the loader graphic', () => {
    const { container } = render(
      <Loader label="Loading filter values…" size="small" inline />,
    )

    expect(within(container).getByRole('status')).toHaveClass(
      'pathlab-loader--small',
      'pathlab-loader--inline',
    )
    expect(container.querySelectorAll('.pathlab-loader__indicator')).toHaveLength(1)
  })
})
