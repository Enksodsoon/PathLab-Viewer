import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'

import { LibrarySidebar } from '../components/LibrarySidebar'
import type { LibraryFolder } from '../types'

const folders: LibraryFolder[] = [
  {
    id: 'root',
    parentId: null,
    name: 'Histology',
    description: '',
    sortOrder: 0,
    createdAt: '2026-07-23T00:00:00Z',
    updatedAt: '2026-07-23T00:00:00Z',
    share: null,
  },
  {
    id: 'child',
    parentId: 'root',
    name: 'GI',
    description: '',
    sortOrder: 0,
    createdAt: '2026-07-23T00:00:00Z',
    updatedAt: '2026-07-23T00:00:00Z',
    share: null,
  },
]

it('renders virtual locations and nested folders with accessible selection', async () => {
  const select = vi.fn()
  render(
    <LibrarySidebar
      folders={folders}
      selected="all"
      counts={{ all: 4, unfiled: 1, shared: 2, processing: 1, failed: 0 }}
      onSelect={select}
      onCreate={() => undefined}
    />,
  )
  expect(screen.getByRole('button', { name: /All slides 4/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /GI/ })).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: /GI/ }))
  expect(select).toHaveBeenCalledWith('child')
})
