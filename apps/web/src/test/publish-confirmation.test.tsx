import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PublishConfirmationDialog } from '../components/library/PublishConfirmationDialog'

describe('PublishConfirmationDialog', () => {
  it('requires deidentification confirmation before publishing and resets when reopened', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    const { rerender } = render(
      <PublishConfirmationDialog
        open
        count={2}
        busy={false}
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    )

    const publish = screen.getByRole('button', { name: 'Publish 2 slides' })
    expect(publish).toBeDisabled()

    await user.click(screen.getByRole('checkbox', {
      name: /patient identifiers and private information have been removed/i,
    }))
    expect(publish).toBeEnabled()
    await user.click(publish)
    expect(onConfirm).toHaveBeenCalledTimes(1)

    rerender(
      <PublishConfirmationDialog
        open={false}
        count={2}
        busy={false}
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    )
    rerender(
      <PublishConfirmationDialog
        open
        count={2}
        busy={false}
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    )

    expect(screen.getByRole('button', { name: 'Publish 2 slides' })).toBeDisabled()
  })
})
