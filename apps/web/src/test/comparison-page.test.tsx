import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import { ComparisonPage } from '../pages/ComparisonPage'

vi.mock('../components/OpenSeadragonViewer', () => ({
  OpenSeadragonViewer: ({ tileSource }: { tileSource: string }) => <div aria-label={`Viewer ${tileSource}`} />,
}))

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
    id: 'set-1', name: 'Multi-stain set', referenceSlideId: 'slide-1', status: 'ready', version: 1,
    members: Array.from({ length: 5 }, (_, index) => ({
      slideId: `slide-${index + 1}`, displayName: `Slide ${index + 1}`, stain: index === 0 ? 'H&E' : `IHC ${index}`,
      tileSource: `/tiles/${index + 1}.dzi`, metadata: { width: 1000, height: 800, physicalSizeX: 0.25 },
      registration: index === 0 ? null : { status: 'ready', provenance: 'automatic', movingToReference: [[1, 0, 0], [0, 1, 0]], movingSupport: null, referenceSupport: null },
    })),
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
})

it('mounts two panes by default and caps visible panes at four', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(2)
  await user.click(screen.getByRole('button', { name: 'Add pane' }))
  await user.click(screen.getByRole('button', { name: 'Add pane' }))
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(4)
  expect(screen.queryByRole('button', { name: 'Add pane' })).not.toBeInTheDocument()
})
