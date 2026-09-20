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


it('activates an already open tray slide instead of duplicating its viewer', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'IHC 1Slide 2' }))
  expect(screen.getAllByLabelText('Viewer /tiles/1.dzi')).toHaveLength(1)
  expect(screen.getAllByLabelText('Viewer /tiles/2.dzi')).toHaveLength(1)
  await user.click(screen.getByRole('button', { name: 'IHC 2Slide 3' }))
  expect(screen.getByRole('combobox', { name: 'Slide shown in pane 2' })).toHaveValue('slide-3')
})

it('tolerates invalid persisted pane data', async () => {
  sessionStorage.setItem('pathlab-comparison-view:admin:set-1', '{}')
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(2)
})


it('unmounts hidden viewers when maximizing and restores them afterwards', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Maximize Slide 2 pane' }))
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(1)
  expect(screen.getByLabelText('Viewer /tiles/2.dzi')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Restore Slide 2 pane' }))
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(2)
})

it('opens a correction with independent panes and requires preview before save', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Correct alignment' }))
  expect(screen.getByRole('combobox', { name: 'Alignment mode' })).toHaveValue('independent')
  expect(screen.getByRole('button', { name: 'Save correction' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Preview correction' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Cancel correction' }))
  expect(screen.queryByRole('button', { name: 'Record point pair' })).not.toBeInTheDocument()
})


it('enables matched navigation when linking a pane from independent mode', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  await user.selectOptions(screen.getByRole('combobox', { name: 'Alignment mode' }), 'independent')
  await user.click(screen.getByRole('button', { name: 'Link Slide 2 pane' }))
  expect(screen.getByRole('combobox', { name: 'Alignment mode' })).toHaveValue('matched')
  expect(screen.getByRole('button', { name: 'Unlink Slide 2 pane' })).toHaveAttribute('aria-pressed', 'true')
  await user.click(screen.getByRole('button', { name: 'Unlink Slide 2 pane' }))
  expect(screen.getByRole('button', { name: 'Link Slide 2 pane' })).toHaveAttribute('aria-pressed', 'false')
})

it('explains missing anatomical maps before the first navigation gesture', async () => {
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByRole('note', { name: 'Alignment unavailable' })).toHaveTextContent('Linking panes cannot align these slides.')
})

it('lets an administrator save a direct serial-section anchor and queue registration', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  const response = {
    id: 'set-1', name: 'Multi-stain set', referenceSlideId: 'slide-1', status: 'draft', version: 2,
    alignmentConfig: { anchors: { 'slide-4': 'slide-3' } },
    members: Array.from({ length: 5 }, (_, index) => ({
      slideId: `slide-${index + 1}`, displayName: `Slide ${index + 1}`, stain: index === 0 ? 'H&E' : `IHC ${index}`,
      tileSource: `/tiles/${index + 1}.dzi`, metadata: { width: 1000, height: 800, physicalSizeX: 0.25 }, registration: null,
    })),
  }
  vi.mocked(fetch).mockImplementation(async (_input, init) => init?.method === 'PATCH'
    ? new Response(JSON.stringify(response), { status: 200, headers: { 'Content-Type': 'application/json' } })
    : new Response(null, { status: 202 }))

  await user.click(screen.getByRole('button', { name: 'Groups' }))
  await user.selectOptions(screen.getByRole('combobox', { name: 'Anchor for Slide 4' }), 'slide-3')
  await user.click(screen.getByRole('button', { name: 'Save and register' }))

  await vi.waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/v1/admin/comparison-sets/set-1', expect.objectContaining({ method: 'PATCH' })))
  const patchCall = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'PATCH')
  expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({ version: 1, anchors: { 'slide-4': 'slide-3' } })
  expect(await screen.findByText('Registration queued with the updated reference groups.')).toBeVisible()
})
