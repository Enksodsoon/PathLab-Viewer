import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { FolderViewerPage } from '../pages/FolderViewerPage'

vi.mock('../components/OpenSeadragonViewer', () => ({
  OpenSeadragonViewer: ({ tileSource }: { tileSource: string }) => (
    <div data-testid="osd-source">{tileSource}</div>
  ),
}))

const manifest = {
  folderPublicId: 'folder-public',
  name: 'GI teaching',
  description: 'Direct slides only',
  shareStatus: 'active',
  slides: [
    { publicId: 'one', displayName: 'Colon', description: '', stain: 'H&E', organSite: 'Colon', tags: [], teachingNote: '', metadata: null, tileSource: '/tiles/one/slide.dzi', sortOrder: 0 },
    { publicId: 'two', displayName: 'Stomach', description: '', stain: 'PAS', organSite: 'Stomach', tags: [], teachingNote: '', metadata: null, tileSource: '/tiles/two/slide.dzi', sortOrder: 1 },
  ],
}

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

it('switches one viewer source and restores the latest valid slide', async () => {
  localStorage.setItem('pathlab-folder:folder-public:slide', 'two')
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(manifest), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  }))
  render(<MemoryRouter initialEntries={['/f/folder-public']}><Routes>
    <Route path="/f/:folderPublicId" element={<FolderViewerPage />} />
  </Routes></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Stomach' })).toBeVisible()
  expect(screen.getByTestId('osd-source')).toHaveTextContent('/tiles/two/slide.dzi')
  await userEvent.click(screen.getByRole('button', { name: /previous slide/i }))
  expect(screen.getByTestId('osd-source')).toHaveTextContent('/tiles/one/slide.dzi')
  expect(localStorage.getItem('pathlab-folder:folder-public:slide')).toBe('one')
})
