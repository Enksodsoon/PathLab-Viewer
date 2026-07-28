import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test } from 'vitest'

import {
  Brand,
  ThemeControl,
  ThemeProvider,
} from '@enksodsoon/pathlab-ui'

test('shared UI hosts can select product identity and theme behavior', async () => {
  const user = userEvent.setup()

  render(
    <ThemeProvider>
      <Brand product="Forge" variant="library" />
      <ThemeControl />
    </ThemeProvider>,
  )

  expect(screen.getByLabelText('PathLab Forge')).toHaveTextContent('PathLabForge')

  await user.click(screen.getByRole('radio', { name: 'Dark' }))

  expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
})
