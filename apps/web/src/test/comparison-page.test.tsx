import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { ComparisonPage } from '../pages/ComparisonPage'

vi.mock('../components/OpenSeadragonViewer', () => ({
  OpenSeadragonViewer: ({ tileSource, onOpen, onViewportChange }: { tileSource: string, onOpen?: () => void, onViewportChange?: (snapshot: { centerX: number, centerY: number, imageZoom: number, rotation: number }) => void }) => <button
    type="button"
    aria-label={`Viewer ${tileSource}`}
    onClick={() => {
      onOpen?.()
      onViewportChange?.({ centerX: 10, centerY: 10, imageZoom: 1, rotation: 0 })
    }}
  />,
}))

beforeEach(() => {
  sessionStorage.clear()
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
    id: 'set-1', name: 'Multi-stain set', referenceSlideId: 'slide-1', status: 'ready', version: 1,
    members: Array.from({ length: 5 }, (_, index) => ({
      slideId: `slide-${index + 1}`, displayName: `Slide ${index + 1}`, stain: index === 0 ? 'H&E' : `IHC ${index}`,
      tileSource: `/tiles/${index + 1}.dzi`, metadata: { width: 1000, height: 800, physicalSizeX: 0.25 },
      registration: index === 0 ? null : index === 4
        ? { status: 'rejected', provenance: 'automatic' }
        : { status: 'ready', provenance: 'automatic', movingToReference: [[1, 0, 0], [0, 1, 0]], movingSupport: null, referenceSupport: null },
    })),
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
})

afterEach(() => cleanup())

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

it('restores the selected stain panes after a page remount', async () => {
  const user = userEvent.setup()
  const route = <MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>
  const first = render(route)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  await user.selectOptions(screen.getByRole('combobox', { name: 'Slide shown in pane 2' }), 'slide-3')
  first.unmount()

  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)

  expect(await screen.findByRole('combobox', { name: 'Slide shown in pane 2' })).toHaveValue('slide-3')
})

it('fails closed when an unaligned slide tries to synchronize', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()

  await user.selectOptions(screen.getByRole('combobox', { name: 'Slide shown in pane 2' }), 'slide-5')
  expect(screen.getByText('Not aligned')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Viewer /tiles/5.dzi' }))
  expect(screen.getByRole('status')).toHaveTextContent('Synchronization suspended because Slide 5 is not aligned.')

  await user.click(screen.getByRole('button', { name: 'Viewer /tiles/1.dzi' }))
  expect(screen.getByRole('status')).toHaveTextContent('Synchronization suspended for Slide 5 because reliable correspondence is unavailable.')
})
