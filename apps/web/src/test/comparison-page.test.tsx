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
  vi.stubGlobal('fetch', vi.fn(async (input) => String(input).endsWith('/jobs')
    ? new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    : new Response(JSON.stringify({
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

it('shows durable automatic alignment progress for every stack member', async () => {
  vi.mocked(fetch).mockImplementation(async (input) => String(input).endsWith('/jobs')
    ? new Response(JSON.stringify([
      { id: 'job-pas', kind: 'align', memberId: 'slide-2', setVersion: 4, status: 'succeeded', stage: 'complete', progress: 100, processedPatches: 2, totalPatches: 2, processedComponentPairs: 4, totalComponentPairs: 4, failureCode: null, createdAt: '2026-09-21T10:00:00Z' },
      { id: 'job-silver', kind: 'align', memberId: 'slide-3', setVersion: 4, status: 'running', stage: 'high-resolution-components', progress: 30, processedPatches: 0, totalPatches: 2, processedComponentPairs: 4, totalComponentPairs: 4, failureCode: null, createdAt: '2026-09-21T10:01:00Z' },
      { id: 'job-trichrome', kind: 'align', memberId: 'slide-4', setVersion: 4, status: 'queued', stage: 'queued', progress: 0, processedPatches: 0, totalPatches: 0, processedComponentPairs: 0, totalComponentPairs: 0, failureCode: null, createdAt: '2026-09-21T10:02:00Z' },
    ]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    : new Response(JSON.stringify({
      id: 'set-1', name: 'Renal Test', referenceSlideId: 'slide-1', status: 'running', version: 4,
      members: Array.from({ length: 4 }, (_, index) => ({
        slideId: `slide-${index + 1}`, displayName: `Slide ${index + 1}`, stain: ['H&E', 'PAS', 'Silver', 'Trichrome'][index],
        tileSource: `/tiles/${index + 1}.dzi`, metadata: { width: 1000, height: 800, physicalSizeX: 0.25 },
        registration: index === 1 ? { status: 'approximate', provenance: 'automatic', overviewTriangles: [] } : null,
      })),
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)

  expect(await screen.findByRole('region', { name: 'Automatic alignment progress' })).toHaveTextContent('1 of 3 slides complete · 43%')
  expect(screen.getByText(/high resolution components · 4\/4 regions · 0\/2 patches/)).toBeVisible()
  expect(screen.getByText('Waiting for worker')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Correct alignment' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Benchmark engines' })).toBeDisabled()
})

it('supports a real three-pane layout and makes the replacement target explicit', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()

  await user.selectOptions(screen.getByRole('combobox', { name: 'Pane layout' }), '3')
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(3)
  expect(screen.getByRole('combobox', { name: 'Pane layout' })).toHaveValue('3')
  expect(screen.getByRole('button', { name: 'H&ESlide 1' })).toHaveAttribute('aria-current', 'true')

  await user.click(screen.getByRole('button', { name: 'IHC 2Slide 3' }))
  expect(screen.getByRole('button', { name: 'IHC 2Slide 3' })).toHaveAttribute('aria-current', 'true')
})

it('supports the three-pane keyboard shortcut', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()

  await user.keyboard('3')
  expect(screen.getByRole('combobox', { name: 'Pane layout' })).toHaveValue('3')
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(3)
})

it('can hide the case slide tray without changing the open panes', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()

  await user.click(screen.getByRole('button', { name: 'Hide slides' }))
  expect(screen.getByRole('button', { name: 'Show slides' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(2)
})

it('restores an explicitly selected approximate alignment mode after a page remount', async () => {
  const user = userEvent.setup()
  const first = render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  await user.selectOptions(screen.getByRole('combobox', { name: 'Alignment mode' }), 'approximate')
  first.unmount()

  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)

  expect(await screen.findByRole('combobox', { name: 'Alignment mode' })).toHaveValue('approximate')
})

it('does not use an unverified component proposal in best-available mode', async () => {
  vi.mocked(fetch).mockImplementation(async () => new Response(JSON.stringify({
    id: 'set-1', name: 'Mixed evidence set', referenceSlideId: 'slide-1', status: 'partial', version: 1,
    members: [
      { slideId: 'slide-1', displayName: 'H&E', stain: 'H&E', tileSource: '/tiles/1.dzi', metadata: { width: 1000, height: 800, physicalSizeX: 0.25 }, registration: null },
      {
        slideId: 'slide-2', displayName: 'Silver', stain: 'Silver', tileSource: '/tiles/2.dzi', metadata: { width: 1000, height: 800, physicalSizeX: 0.25 },
        registration: {
          status: 'approximate', provenance: 'automatic', anchorSlideId: 'slide-1', movingToReference: [[1, 0, 20], [0, 1, 10]], triangles: [],
          overviewTriangles: [{ moving: [[0, 0], [500, 0], [0, 500]], reference: [[20, 10], [520, 10], [20, 510]] }],
        },
      },
    ],
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Mixed evidence set')).toBeVisible()

  await user.click(screen.getByRole('button', { name: 'Viewer /tiles/2.dzi' }))
  await user.click(screen.getByRole('button', { name: 'Viewer /tiles/1.dzi' }))

  expect(screen.getByText('Unavailable')).toBeVisible()
  expect(screen.getByRole('status')).toHaveTextContent('No verified correspondence is available at this field for Silver')
  expect(screen.queryByText(/Synchronization suspended/)).not.toBeInTheDocument()
})

it('uses an order-preserving component overview when exact evidence is unavailable', async () => {
  vi.mocked(fetch).mockImplementation(async () => new Response(JSON.stringify({
    id: 'set-1', name: 'Ordered component set', referenceSlideId: 'slide-1', status: 'partial', version: 1,
    members: [
      { slideId: 'slide-1', displayName: 'H&E', stain: 'H&E', tileSource: '/tiles/1.dzi', metadata: { width: 1000, height: 800, physicalSizeX: 0.25 }, registration: null },
      {
        slideId: 'slide-2', displayName: 'Silver', stain: 'Silver', tileSource: '/tiles/2.dzi', metadata: { width: 1000, height: 800, physicalSizeX: 0.25 },
        registration: {
          status: 'approximate', provenance: 'automatic', anchorSlideId: 'slide-1', movingToReference: [[1, 0, 20], [0, 1, 10]], triangles: [],
          overviewTriangles: [{ moving: [[0, 0], [500, 0], [0, 500]], reference: [[20, 10], [520, 10], [20, 510]] }],
          evidence: { componentOrderPreserved: true },
        },
      },
    ],
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Ordered component set')).toBeVisible()

  await user.click(screen.getByRole('button', { name: 'Viewer /tiles/1.dzi' }))

  expect(screen.getByText('Approximate sync')).toBeVisible()
  expect(screen.queryByText('Unavailable')).not.toBeInTheDocument()
})

it('opens a rejected slide independently instead of attempting synchronization', async () => {
  const user = userEvent.setup()
  const first = render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()

  await user.selectOptions(screen.getByRole('combobox', { name: 'Slide shown in pane 2' }), 'slide-5')
  expect(screen.getAllByText('Independent')).toHaveLength(2)
  expect(screen.getByRole('status')).toHaveTextContent('Slide 5 has no reliable counterpart and is opened independently.')
  await user.click(screen.getByRole('button', { name: 'Viewer /tiles/5.dzi' }))
  expect(screen.getByRole('status')).toHaveTextContent('Slide 5 has no reliable counterpart and is opened independently.')

  await user.click(screen.getByRole('button', { name: 'Viewer /tiles/1.dzi' }))
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getAllByText('Independent')).toHaveLength(2)

  first.unmount()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByRole('button', { name: 'Link Slide 5 pane' })).toHaveAttribute('aria-pressed', 'false')
  expect(screen.getAllByText('Independent')).toHaveLength(2)
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

it('focuses the active rejected slide for correction and restores the previous layout on cancel', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  await user.selectOptions(screen.getByRole('combobox', { name: 'Alignment mode' }), 'approximate')
  await user.click(screen.getByRole('button', { name: 'Add pane' }))
  await user.click(screen.getByRole('button', { name: 'Add pane' }))
  await user.selectOptions(screen.getByRole('combobox', { name: 'Slide shown in pane 4' }), 'slide-5')

  await user.click(screen.getByRole('button', { name: 'Correct alignment' }))
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(2)
  expect(screen.getByLabelText('Viewer /tiles/1.dzi')).toBeVisible()
  expect(screen.getByLabelText('Viewer /tiles/5.dzi')).toBeVisible()
  expect(screen.getByRole('combobox', { name: 'Alignment mode' })).toHaveValue('independent')

  await user.click(screen.getByRole('button', { name: 'Cancel correction' }))
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(4)
  expect(screen.getByRole('combobox', { name: 'Slide shown in pane 4' })).toHaveValue('slide-5')
  expect(screen.getByRole('combobox', { name: 'Alignment mode' })).toHaveValue('approximate')
  expect(screen.getByRole('button', { name: 'Views linked' })).toHaveAttribute('aria-pressed', 'true')
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
