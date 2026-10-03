import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { ComparisonPage } from '../pages/ComparisonPage'

const viewportHarness = vi.hoisted(() => ({ enabled: false, bounds: null as [number, number, number, number] | null, applied: vi.fn(), fitted: vi.fn(), current: { centerX: 210, centerY: 330, imageZoom: 2, rotation: 12 } }))

vi.mock('../components/OpenSeadragonViewer', () => ({
  OpenSeadragonViewer: ({ tileSource, onReady, onOpen, onViewportChange, loadingMode, showLoadingMode }: { tileSource: string, onReady?: (handle: unknown) => void, onOpen?: () => void, onViewportChange?: (snapshot: { centerX: number, centerY: number, imageZoom: number, rotation: number }) => void, loadingMode?: string, showLoadingMode?: boolean }) => <button
    type="button"
    aria-label={`Viewer ${tileSource}`}
    data-loading-mode={loadingMode}
    data-loading-control={showLoadingMode === false ? 'hidden' : 'shown'}
    onClick={() => {
      if (viewportHarness.enabled) onReady?.({ getImageViewport: () => ({ ...viewportHarness.current, ...(viewportHarness.bounds ? { visibleBounds: viewportHarness.bounds } : {}) }), setImageViewport: (snapshot: unknown) => viewportHarness.applied(tileSource, snapshot), fitImageBounds: (bounds: unknown) => viewportHarness.fitted(tileSource, bounds), home: vi.fn() })
      onOpen?.()
      onViewportChange?.(viewportHarness.enabled ? { ...viewportHarness.current } : { centerX: 10, centerY: 10, imageZoom: 1, rotation: 0 })
    }}
  />,
}))

beforeEach(() => {
  viewportHarness.enabled = false
  viewportHarness.bounds = null
  viewportHarness.current = { centerX: 210, centerY: 330, imageZoom: 2, rotation: 12 }
  viewportHarness.applied.mockClear()
  viewportHarness.fitted.mockClear()
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
        : { status: 'ready', provenance: 'automatic', movingToReference: [[1, 0, 0], [0, 1, 0]], movingSupport: null, referenceSupport: null, triangles: [{ moving: [[0, 0], [1000, 0], [0, 800]], reference: [[0, 0], [1000, 0], [0, 800]] }] },
    })),
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
})

afterEach(() => {
  cleanup()
  localStorage.removeItem('pathlab-viewer-loading-mode:v1')
})

it('controls tile detail for the active pane from Display and preserves the saved preference', async () => {
  localStorage.setItem('pathlab-viewer-loading-mode:v1', 'full')
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await screen.findByText('Multi-stain set')
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) expect(viewer).toHaveAttribute('data-loading-control', 'hidden')
  await user.click(screen.getByText('Advanced'))
  await user.click(screen.getByText('Display', { exact: true }))
  expect(screen.getByLabelText('Tile detail')).toHaveValue('full')
  await user.selectOptions(screen.getByLabelText('Tile detail'), 'data-saver')
  expect(localStorage.getItem('pathlab-viewer-loading-mode:v1')).toBe('data-saver')
  expect(screen.getByLabelText('Viewer /tiles/1.dzi')).toHaveAttribute('data-loading-mode', 'data-saver')
  expect(screen.getByLabelText('Viewer /tiles/2.dzi')).toHaveAttribute('data-loading-mode', 'full')
  await user.click(screen.getByLabelText('Viewer /tiles/2.dzi'))
  expect(screen.getByLabelText('Tile detail')).toHaveValue('full')
  localStorage.removeItem('pathlab-viewer-loading-mode:v1')
})

it('focuses tissue for approximate siblings when the primary reference is hidden', async () => {
  sessionStorage.setItem('pathlab-comparison-view:admin:set-1', JSON.stringify(['slide-2', 'slide-3']))
  viewportHarness.enabled = true
  const originalFetch = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const response = await originalFetch(input, init)
    const value = await response.json()
    if (value.members) for (const member of value.members) if (member.registration?.status === 'ready') {
      member.registration.status = 'approximate'
      member.registration.overviewTriangles = member.registration.triangles
      member.registration.triangles = []
    }
    return new Response(JSON.stringify(value), { status: 200 })
  })
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await screen.findByText('Multi-stain set')
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) await user.click(viewer)
  await waitFor(() => expect(viewportHarness.fitted).toHaveBeenCalled())
})

it('allows bounded region adjustment during refinement and keeps the displayed pair', async () => {
  sessionStorage.setItem('pathlab-comparison-view:admin:set-1', JSON.stringify(['slide-2', 'slide-3']))
  const originalFetch = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const response = await originalFetch(input, init)
    const value = await response.json()
    if (value.members) value.status = 'running'
    return new Response(JSON.stringify(value), { status: 200 })
  })
  viewportHarness.enabled = true
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await screen.findByText('Multi-stain set')
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) await user.click(viewer)
  await user.click(screen.getByRole('button', { name: 'Adjust region' }))
  expect(screen.getByLabelText('Viewer /tiles/2.dzi')).toBeVisible()
  expect(screen.getByLabelText('Viewer /tiles/3.dzi')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Record point pair' }))
  expect(screen.getByRole('button', { name: 'Preview correction' })).toBeEnabled()
  viewportHarness.current = { ...viewportHarness.current, centerX: 250, centerY: 350 }
  await user.click(screen.getByRole('button', { name: 'Record point pair' }))
  expect(screen.getByRole('button', { name: 'Record point pair' })).toBeDisabled()
  expect(screen.getByText('2 point pairs')).toBeVisible()
})

it('freezes the region preview through polling and saves using its returned version and identity', async () => {
  viewportHarness.bounds = [10, 20, 800, 500]
  const originalFetch = vi.mocked(fetch).getMockImplementation()!
  const posted: Array<Record<string, unknown>> = []
  let reads = 0
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const response = await originalFetch(input, init)
    const value = await response.json()
    if (String(input).endsWith('/region-corrections')) {
      const payload = JSON.parse(String(init?.body)); posted.push(payload)
      value.version = payload.operation === 'preview' ? 7 : 8
      value.regionalCorrections = [{ id: 'revision', regionId: 'captured-region', sourceVersion: 'updated:source-snapshot', targetVersion: 'target-digest', sourceSlideId: payload.sourceSlideId, targetSlideId: payload.targetSlideId, sourceBounds: payload.sourceBounds, registration: { status: 'approximate', provenance: 'manual-region', movingToReference: [[1, 0, 0], [0, 1, 0]], triangles: value.members[1].registration.triangles } }]
      value.regionalCorrections.push({ ...value.regionalCorrections[0], id: 'old-revision', regionId: 'old-region' })
      value.status = payload.operation === 'preview' ? 'running' : 'ready'
      value.name = payload.operation === 'preview' ? 'Preview field' : 'Saved field'
    } else if (value.members) {
      value.status = 'running'
      if (++reads > 1) value.name = 'Background replacement'
    }
    return new Response(JSON.stringify(value), { status: 200 })
  })
  viewportHarness.enabled = true
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await screen.findByText('Multi-stain set')
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) await user.click(viewer)
  await user.click(screen.getByRole('button', { name: 'Adjust region' }))
  await user.click(screen.getByRole('button', { name: 'Record point pair' }))
  await user.click(screen.getByRole('button', { name: 'Preview correction' }))
  expect(await screen.findByText('Preview field')).toBeVisible()
  await new Promise(resolve => setTimeout(resolve, 2200))
  expect(screen.getByText('Preview field')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Preview correction' }))
  await user.click(screen.getByRole('button', { name: 'Save correction' }))
  expect(await screen.findByText('Saved field')).toBeVisible()
  expect(posted).toHaveLength(3)
  expect(posted[0].sourceBounds).toEqual([10, 20, 800, 500])
  expect(posted[0].sourceVersion).toBeUndefined()
  expect(posted[1]).toMatchObject({ operation: 'preview', sourceVersion: 'updated:source-snapshot', targetVersion: 'target-digest' })
  expect(posted[2]).toMatchObject({ operation: 'save', version: 7, regionId: 'captured-region', sourceVersion: 'updated:source-snapshot', targetVersion: 'target-digest', sourceSlideId: 'slide-2', targetSlideId: 'slide-1', movingPoints: [[210, 330]], referencePoints: [[210, 330]] })
})

it.each([{ scale: 1, zoomMode: 'physical', zoom: 2 }, { scale: 2, zoomMode: 'physical', zoom: 2 }, { scale: 2, zoomMode: 'tissue', zoom: 4 }])('links a supported saved region with scale $scale and $zoomMode zoom when automatic registration rejected that slide', async ({ scale, zoomMode, zoom }) => {
  sessionStorage.setItem('pathlab-comparison-view:admin:set-1:preferences', JSON.stringify({ zoomMode, alignmentMode: 'matched' }))
  const originalFetch = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const response = await originalFetch(input, init)
    const value = await response.json()
    if (value.members) {
      value.members[1].registration = { status: 'rejected', provenance: 'automatic' }
      value.regionalCorrections = [{ id: 'revision', regionId: 'region', sourceSlideId: 'slide-2', targetSlideId: 'slide-1', sourceBounds: [0, 0, 1000, 800], registration: { status: 'approximate', provenance: 'manual-region', movingToReference: [[scale, 0, 50], [0, scale, 0]], triangles: [{ moving: [[0, 0], [1000, 0], [0, 800]], reference: [[50, 0], [1000 * scale + 50, 0], [50, 800 * scale]] }] } }]
    }
    return new Response(JSON.stringify(value), { status: 200 })
  })
  viewportHarness.enabled = true
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await screen.findByText('Multi-stain set')
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) await user.click(viewer)
  viewportHarness.applied.mockClear()
  await user.click(screen.getByLabelText('Viewer /tiles/1.dzi'))
  await waitFor(() => expect(viewportHarness.applied).toHaveBeenCalledWith('/tiles/2.dzi', expect.objectContaining({ centerX: 160 / scale, centerY: 330 / scale, imageZoom: zoom })))
})

it('initializes and resets a region-only displayed pair inside supported tissue', async () => {
  sessionStorage.setItem('pathlab-comparison-view:admin:set-1', JSON.stringify(['slide-2', 'slide-3']))
  const originalFetch = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const value = await (await originalFetch(input, init)).json()
    if (value.members) {
      for (const member of value.members) member.registration = null
      value.regionalCorrections = [{ id: 'revision', regionId: 'region', sourceSlideId: 'slide-2', targetSlideId: 'slide-3', sourceBounds: [600, 500, 300, 200], registration: { status: 'approximate', provenance: 'manual-region', triangles: [{ moving: [[600, 500], [900, 500], [600, 700]], reference: [[600, 500], [900, 500], [600, 700]] }] } }]
    }
    return new Response(JSON.stringify(value), { status: 200 })
  })
  viewportHarness.enabled = true
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await screen.findByText('Multi-stain set')
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) await user.click(viewer)
  await waitFor(() => expect(viewportHarness.fitted).toHaveBeenCalled())
  const bounds = viewportHarness.fitted.mock.calls.at(-1)![1]
  expect((bounds[0] + bounds[2]) / 2).toBeCloseTo(700)
  expect((bounds[1] + bounds[3]) / 2).toBeCloseTo(1700 / 3)
  viewportHarness.fitted.mockClear()
  await user.click(screen.getByText('Advanced', { exact: true }))
  await user.click(screen.getByRole('button', { name: 'Reset view' }))
  await waitFor(() => expect(viewportHarness.fitted).toHaveBeenCalled())
})

it('keeps the durable four-pane preference while a temporary correction pair is displayed', async () => {
  viewportHarness.enabled = true
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await screen.findByText('Multi-stain set')
  await user.click(screen.getByRole('button', { name: 'Add pane' }))
  await user.click(screen.getByRole('button', { name: 'Add pane' }))
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) await user.click(viewer)
  const saved = sessionStorage.getItem('pathlab-comparison-view:admin:set-1')
  await user.click(screen.getByRole('button', { name: 'Adjust region' }))
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(2)
  expect(sessionStorage.getItem('pathlab-comparison-view:admin:set-1')).toBe(saved)
})

it('mounts two panes by default and caps visible panes at four', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Slides' })).toHaveAttribute('aria-expanded', 'false')
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
      { id: 'job-silver', kind: 'align', memberId: 'slide-3', setVersion: 4, status: 'running', stage: 'high-resolution-components', progress: 30, processedPatches: 0, totalPatches: 2, processedComponentPairs: 4, totalComponentPairs: 4, failureCode: null, createdAt: new Date(Date.now() - 75_000).toISOString(), updatedAt: new Date().toISOString(), heartbeatAt: new Date().toISOString() },
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
  await userEvent.click(screen.getByText(/Alignment in progress · 43%/))
  expect(screen.getByText(/high resolution components · 4\/4 regions · 0\/2 patches/)).toBeVisible()
  expect(screen.getByText(/Worker active · 1m \d+s elapsed/)).toBeVisible()
  expect(screen.getByText('Waiting for worker')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Correct alignment' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Benchmark engines' })).toBeDisabled()
})

it('keeps the current map usable while a replacement registration runs', async () => {
  vi.mocked(fetch).mockImplementation(async (input) => String(input).endsWith('/jobs')
    ? new Response(JSON.stringify([{
      id: 'job-rerun', kind: 'align', memberId: 'slide-2', setVersion: 2,
      status: 'running', stage: 'high-resolution-components', progress: 30,
      processedPatches: 0, totalPatches: 2, processedComponentPairs: 4, totalComponentPairs: 4,
      failureCode: null, createdAt: new Date(Date.now() - 30_000).toISOString(),
      updatedAt: new Date().toISOString(), heartbeatAt: new Date().toISOString(),
    }]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    : new Response(JSON.stringify({
      id: 'set-1', name: 'Rerunning set', referenceSlideId: 'slide-1', status: 'running', version: 2,
      members: [
        { slideId: 'slide-1', displayName: 'H&E', stain: 'H&E', tileSource: '/tiles/1.dzi', metadata: { width: 1000, height: 800, physicalSizeX: 0.25 }, registration: null },
        { slideId: 'slide-2', displayName: 'P40', stain: 'P40', tileSource: '/tiles/2.dzi', metadata: { width: 1000, height: 800, physicalSizeX: 0.25 }, registration: { status: 'approximate', provenance: 'automatic', anchorSlideId: 'slide-1', movingToReference: [[1, 0, 20], [0, 1, 10]], triangles: [], overviewTriangles: [{ moving: [[0, 0], [500, 0], [0, 500]], reference: [[20, 10], [520, 10], [20, 510]] }] } },
      ],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)

  expect(await screen.findByRole('region', { name: 'Automatic alignment progress' })).toHaveTextContent('0 of 1 slides complete · 30%')
  await userEvent.click(screen.getByText(/Alignment in progress · 30%/))
  expect(screen.getByText(/Worker active/)).toBeVisible()
  expect(screen.getByRole('combobox', { name: 'Alignment mode' })).toBeEnabled()
})

it('does not offer promotion for a locally unqualified engine map', async () => {
  vi.mocked(fetch).mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/jobs')) return new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } })
    if (url.endsWith('/candidates')) return new Response(JSON.stringify({
      comparisonSetId: 'set-1', setVersion: 1, engineAvailability: {},
      candidates: [{ id: 'candidate-1', slideId: 'slide-2', setVersion: 1, anchorSlideId: 'slide-1', engine: 'hisalign-0.2.1', engineVersion: 'current', settingsDigest: 'current', currentSettings: true, status: 'ready', validationState: 'engineering_passed', registration: { status: 'ready', provenance: 'automatic-candidate', evidence: { hisalignLocalEvidenceQualified: false } }, evidence: {}, artifactSha256: null, failureReason: null, createdAt: '2026-09-28T00:00:00Z' }],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    return new Response(JSON.stringify({ id: 'set-1', name: 'Unsafe candidate set', referenceSlideId: 'slide-1', status: 'partial', version: 1, members: [
      { slideId: 'slide-1', displayName: 'H&E', stain: 'H&E', tileSource: '/tiles/1.dzi', metadata: { width: 1000, height: 800, physicalSizeX: 0.25 }, registration: null },
      { slideId: 'slide-2', displayName: 'P40', stain: 'P40', tileSource: '/tiles/2.dzi', metadata: { width: 1000, height: 800, physicalSizeX: 0.25 }, registration: null },
    ] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await user.click(await screen.findByText('Advanced'))
  await user.click(await screen.findByText('Registration engine candidates'))
  expect(screen.getByText(/local map unqualified/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Promote hisalign-0.2.1 for P40' })).toBeDisabled()
})

it('blocks promotion after independent benchmark qualification fails while allowing inspection', async () => {
  const originalFetch = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (input, init) => String(input).endsWith('/candidates')
    ? new Response(JSON.stringify({ candidates: [{ id: 'failed-gates', slideId: 'slide-2', setVersion: 1, engine: 'native-v12', status: 'ready', validationState: 'engineering_passed', registration: { status: 'ready', provenance: 'automatic-candidate' }, benchmarkMeasurements: { qualified: false } }] }), { status: 200 })
    : originalFetch(input, init))
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await screen.findByText('Multi-stain set')
  await user.click(screen.getByText('Advanced'))
  await user.click(screen.getByText('Registration engine candidates'))
  expect(screen.getByRole('button', { name: 'Preview native-v12 for Slide 2' })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Promote native-v12 for Slide 2' })).toBeDisabled()
})

it.each(['native-wsireg', 'valis-rigid-wsireg', 'native-valis'].flatMap(engine => [
  { engine, validationState: 'engineering_passed', qualified: true, improvesOnIndividualStages: true, digest: 'current', enabled: false },
  { engine, validationState: 'landmark_passed', qualified: true, improvesOnIndividualStages: false, digest: 'current', enabled: false },
  { engine, validationState: 'landmark_passed', qualified: true, improvesOnIndividualStages: true, digest: 'old', enabled: false },
  { engine, validationState: 'landmark_passed', qualified: false, improvesOnIndividualStages: true, digest: 'current', enabled: false },
  { engine, validationState: 'landmark_passed', qualified: true, improvesOnIndividualStages: true, digest: 'current', enabled: true },
]))('requires independently qualified improvement before promoting $engine ($validationState/$qualified/$improvesOnIndividualStages/$digest)', async ({ engine, validationState, qualified, improvesOnIndividualStages, digest, enabled }) => {
  const originalFetch = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (input, init) => String(input).endsWith('/candidates')
    ? new Response(JSON.stringify({ candidates: [{ id: 'hybrid', slideId: 'slide-2', setVersion: 1, engine, status: 'ready', currentSettings: true, settingsDigest: 'current', validationState, registration: { status: 'ready', provenance: 'automatic-candidate', evidence: { valisLocalEvidenceQualified: true } }, benchmarkMeasurements: { qualified, improvesOnIndividualStages, settingsDigest: digest } }] }), { status: 200 })
    : originalFetch(input, init))
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await screen.findByText('Multi-stain set')
  await user.click(screen.getByText('Advanced'))
  await user.click(screen.getByText('Registration engine candidates'))
  expect(screen.getByRole('button', { name: `Preview ${engine} for Slide 2` })).toBeEnabled()
  if (enabled) expect(screen.getByRole('button', { name: `Promote ${engine} for Slide 2` })).toBeEnabled()
  else expect(screen.getByRole('button', { name: `Promote ${engine} for Slide 2` })).toBeDisabled()
})

it.each([{ status: 'partial', currentSettings: true }, { status: 'running', currentSettings: true }, { status: 'partial', currentSettings: false }])('handles candidate freshness and $status refreshes with currentSettings=$currentSettings', async ({ status, currentSettings }) => {
  let setReads = 0
  const savedRegistration = { status: 'approximate', provenance: 'automatic', anchorSlideId: 'slide-1', movingToReference: [[1, 0, 20], [0, 1, 10]], overviewTriangles: [{ moving: [[0, 0], [500, 0], [0, 500]], reference: [[20, 10], [520, 10], [20, 510]] }] }
  const candidateRegistration = { status: 'approximate', provenance: 'automatic-candidate', anchorSlideId: 'slide-1', movingToReference: [[1.03, 0, 40], [0, 1.03, 25]], overviewTriangles: [{ moving: [[0, 0], [500, 0], [0, 500]], reference: [[40, 25], [555, 25], [40, 540]], maxResidualPixels: 0.2 }], evidence: { featureMatchCount: 7 } }
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/jobs')) return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    if (url.endsWith('/candidates')) return new Response(JSON.stringify({
      comparisonSetId: 'set-1', setVersion: 1, engineAvailability: {},
      candidates: [{ id: 'candidate-1', slideId: 'slide-2', setVersion: 1, anchorSlideId: 'slide-1', engine: 'hisalign-0.2.1', engineVersion: 'c56d1eb', settingsDigest: 'abc', currentSettings, status: 'approximate', validationState: 'rejected', registration: candidateRegistration, evidence: {}, artifactSha256: 'hash', failureReason: null, createdAt: '2026-09-22T00:00:00Z' }],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    if (init?.method === 'POST') throw new Error('Preview must not mutate the server')
    setReads += 1
    return new Response(JSON.stringify({
      id: 'set-1', name: setReads > 1 ? 'Refreshed preview set' : 'Candidate preview set', referenceSlideId: 'slide-1', status, version: 1,
      members: [
        { slideId: 'slide-1', displayName: 'H&E', stain: 'H&E', tileSource: '/tiles/1.dzi', metadata: { width: 1000, height: 800, physicalSizeX: 0.25 }, registration: null },
        { slideId: 'slide-2', displayName: 'P40', stain: 'P40', tileSource: '/tiles/2.dzi', metadata: { width: 1000, height: 800, physicalSizeX: 0.25 }, registration: savedRegistration },
      ],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)

  expect(await screen.findByText('Candidate preview set')).toBeVisible()
  await user.click(screen.getByText('Advanced'))
  await user.click(await screen.findByText('Registration engine candidates'))
  if (!currentSettings) {
    expect(screen.getByRole('button', { name: 'Preview hisalign-0.2.1 for P40' })).toBeDisabled()
    expect(screen.queryByText('Experimental alignment preview')).not.toBeInTheDocument()
    return
  }
  viewportHarness.enabled = true
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) await user.click(viewer)
  const originalViewport = { ...viewportHarness.current }
  viewportHarness.fitted.mockClear()
  await user.click(screen.getByRole('button', { name: 'Preview hisalign-0.2.1 for P40' }))

  expect(screen.getByText('Experimental alignment preview')).toBeVisible()
  expect(screen.getByRole('status')).toHaveTextContent('No server changes have been saved')
  expect(screen.getByRole('combobox', { name: 'Alignment mode' })).toHaveValue('approximate')
  expect(screen.getByRole('button', { name: 'Stop previewing hisalign-0.2.1 for P40' })).toBeVisible()
  await new Promise(resolve => setTimeout(resolve, 50))
  expect(viewportHarness.fitted).not.toHaveBeenCalled()
  expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining('/promote'), expect.anything())
  if (status === 'running') {
    expect(await screen.findByText('Refreshed preview set', {}, { timeout: 3500 })).toBeVisible()
    expect(screen.getByText('7 feature candidates')).toBeInTheDocument()
    expect(screen.getByText('Experimental alignment preview')).toBeVisible()
  }

  if (status !== 'running') {
  await user.click(screen.getByRole('button', { name: 'Correct alignment' }))
  expect(screen.getByRole('combobox', { name: 'Alignment mode' })).toHaveValue('independent')
  expect(screen.getByRole('button', { name: 'Restore saved alignment' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Stop previewing hisalign-0.2.1 for P40' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Benchmark engines' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Restore saved alignment' }))
  expect(screen.getByRole('combobox', { name: 'Alignment mode' })).toHaveValue('independent')
  await user.click(screen.getByRole('button', { name: 'Cancel correction' }))
  expect(screen.getByText('Experimental alignment preview')).toBeVisible()
  }
  viewportHarness.current = { centerX: 650, centerY: 470, imageZoom: 4, rotation: 35 }
  viewportHarness.applied.mockClear()
  await user.click(screen.getByRole('button', { name: 'Restore saved alignment' }))
  expect(screen.queryByText('Experimental alignment preview')).not.toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: 'Alignment mode' })).toHaveValue('matched')
  await waitFor(() => {
    expect(viewportHarness.applied).toHaveBeenCalledWith('/tiles/1.dzi', originalViewport)
    expect(viewportHarness.applied).toHaveBeenCalledWith('/tiles/2.dzi', originalViewport)
  })
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

  await user.click(screen.getByRole('button', { name: 'Slides' }))
  expect(screen.getByRole('button', { name: 'Slides' })).toHaveAttribute('aria-expanded', 'true')
  await user.click(screen.getByRole('button', { name: 'Slides' }))
  expect(screen.getByRole('button', { name: 'Slides' })).toHaveAttribute('aria-expanded', 'false')
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

it('labels short overview gaps approximate instead of freezing the linked pane', async () => {
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

  expect(screen.getByText('Approximate sync')).toBeVisible()
  expect(screen.queryByText('Unavailable')).not.toBeInTheDocument()
})

it('automatically uses and labels an order-preserving component overview', async () => {
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

  expect(screen.getByRole('combobox', { name: 'Alignment mode' })).toHaveValue('matched')
  expect(screen.getByText('Approximate sync')).toBeVisible()
  await user.selectOptions(screen.getByRole('combobox', { name: 'Alignment mode' }), 'approximate')
  expect(screen.getByText('Approximate sync')).toBeVisible()
})

it('automatically uses and labels a whole-slide structural overview', async () => {
  vi.mocked(fetch).mockImplementation(async () => new Response(JSON.stringify({
    id: 'set-1', name: 'Whole-slide structural set', referenceSlideId: 'slide-1', status: 'partial', version: 1,
    members: [
      { slideId: 'slide-1', displayName: 'H&E', stain: 'H&E', tileSource: '/tiles/1.dzi', metadata: { width: 1000, height: 800, physicalSizeX: 0.25 }, registration: null },
      {
        slideId: 'slide-2', displayName: 'P40', stain: 'P40', tileSource: '/tiles/2.dzi', metadata: { width: 1030, height: 860, physicalSizeX: 0.25 },
        registration: {
          status: 'approximate', provenance: 'automatic', anchorSlideId: 'slide-1', movingToReference: [[1, 0, 20], [0, 1.08, 10]], triangles: [],
          overviewTriangles: [{ moving: [[0, 0], [500, 0], [0, 500]], reference: [[20, 10], [520, 10], [20, 550]] }],
          evidence: { source: 'bounded-pyramid-whole-slide-structure' },
        },
      },
    ],
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Whole-slide structural set')).toBeVisible()

  expect(screen.getByRole('combobox', { name: 'Alignment mode' })).toHaveValue('matched')
  expect(screen.getByText('Approximate sync')).toBeVisible()
  await user.selectOptions(screen.getByRole('combobox', { name: 'Alignment mode' }), 'approximate')
  expect(screen.getByText('Approximate sync')).toBeVisible()
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
  expect(screen.getByRole('status')).toHaveTextContent('Slide 5 has no reliable counterpart and is opened independently.')
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


it('restores a maximized pane after cancelling a region correction', async () => {
  viewportHarness.enabled = true
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await screen.findByText('Multi-stain set')
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) await user.click(viewer)
  await user.click(screen.getByRole('button', { name: 'Maximize Slide 2 pane' }))
  await user.click(screen.getByRole('button', { name: 'Adjust region' }))
  await user.click(screen.getByRole('button', { name: 'Cancel correction' }))
  expect(screen.getByRole('button', { name: 'Restore Slide 2 pane' })).toBeVisible()
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(1)
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

it.each([
  { code: 'AUTH_REQUIRED', status: 401, message: /Your session expired/ },
  { code: 'LANDMARK_ON_GLASS', status: 422, message: /A point is on blank glass/ },
])('explains a rejected correction without discarding recorded points: $code', async ({ code, status, message }) => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  const originalFetch = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation((input, init) => String(input).includes('/corrections/')
    ? Promise.resolve(new Response(JSON.stringify({ detail: { code } }), { status }))
    : originalFetch(input, init))
  await user.click(screen.getByRole('button', { name: 'Correct alignment' }))
  viewportHarness.enabled = true
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) await user.click(viewer)
  for (const [centerX, centerY] of [[100, 100], [500, 100], [100, 500]]) {
    viewportHarness.current = { ...viewportHarness.current, centerX, centerY }
    await user.click(screen.getByRole('button', { name: 'Record point pair' }))
  }
  await user.click(screen.getByRole('button', { name: 'Preview correction' }))
  expect(await screen.findByText(message)).toBeVisible()
  expect(screen.getByText('3 point pairs')).toBeVisible()
})

it('labels a successful correction preview as unsaved', async () => {
  const originalFetch = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    if (String(input).includes('/corrections/') && init?.method === 'POST') {
      const original = await originalFetch('/admin/comparisons/set-1')
      const comparison = await original.json()
      comparison.members[1].registration = {
        status: 'ready', provenance: 'manual', anchorSlideId: 'slide-1',
        movingToReference: [[1, 0, 0], [0, 1, 0]],
        triangles: [{ moving: [[0, 0], [1000, 0], [0, 800]], reference: [[0, 0], [1000, 0], [0, 800]] }],
      }
      return new Response(JSON.stringify(comparison), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    return originalFetch(input, init)
  })
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await user.click(await screen.findByRole('button', { name: 'Correct alignment' }))
  viewportHarness.enabled = true
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) await user.click(viewer)
  for (const [centerX, centerY] of [[100, 100], [500, 100], [100, 500]]) {
    viewportHarness.current = { ...viewportHarness.current, centerX, centerY }
    await user.click(screen.getByRole('button', { name: 'Record point pair' }))
  }
  await user.click(screen.getByRole('button', { name: 'Preview correction' }))
  expect(await screen.findByText('Unsaved correction preview')).toHaveClass('alignment-approximate')
  expect(screen.getByRole('button', { name: 'Save correction' })).toBeEnabled()
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

it('restores the original microscopic field when cancelling a four-pane correction', async () => {
  viewportHarness.enabled = true
  viewportHarness.current = { centerX: 210, centerY: 330, imageZoom: 2, rotation: 12 }
  const original = { ...viewportHarness.current }
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Multi-stain set')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Add pane' }))
  await user.click(screen.getByRole('button', { name: 'Add pane' }))
  for (const viewer of screen.getAllByLabelText(/^Viewer /)) await user.click(viewer)
  await user.click(screen.getByRole('button', { name: 'Correct alignment' }))
  viewportHarness.current = { centerX: 700, centerY: 650, imageZoom: 0.1, rotation: 0 }
  await user.click(screen.getByLabelText('Viewer /tiles/1.dzi'))
  viewportHarness.applied.mockClear()
  await user.click(screen.getByRole('button', { name: 'Cancel correction' }))
  expect(screen.getAllByLabelText(/^Viewer /)).toHaveLength(4)
  await waitFor(() => expect(viewportHarness.applied).toHaveBeenCalledWith('/tiles/1.dzi', original))
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
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({
    id: 'set-1', name: 'Unmatched set', referenceSlideId: 'slide-1', status: 'partial', version: 1,
    members: [1, 2].map(i => ({ slideId: `slide-${i}`, displayName: `Slide ${i}`, stain: '', tileSource: `/tiles/${i}.dzi`, metadata: { width: 1000, height: 800 }, registration: null })),
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
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


it.each(['slide-2', 'slide-3'])('reroots the reference graph when selecting descendant %s as primary', async (referenceId) => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/admin/comparisons/set-1']}><Routes><Route path="/admin/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes></MemoryRouter>)
  await screen.findByText('Multi-stain set')
  await user.click(screen.getByText('Advanced', { exact: true }))
  await user.click(screen.getByRole('button', { name: 'Groups' }))
  await user.selectOptions(screen.getByLabelText('Anchor for Slide 3'), 'slide-2')
  await user.selectOptions(screen.getByLabelText('Primary reference'), referenceId)
  const originalFetch = vi.mocked(fetch).getMockImplementation()!
  let posted: { referenceSlideId: string; anchors: Record<string, string> } | undefined
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    if (init?.method === 'PATCH') posted = JSON.parse(String(init.body))
    return originalFetch(input, init)
  })
  await user.click(screen.getByRole('button', { name: 'Save and register' }))
  await waitFor(() => expect(posted).toBeDefined())
  expect(posted!.referenceSlideId).toBe(referenceId)
  expect(posted!.anchors[referenceId]).toBeUndefined()
  for (const member of ['slide-1', 'slide-2', 'slide-3', 'slide-4', 'slide-5']) {
    const visited = new Set<string>(); let current = member
    while (current !== referenceId && !visited.has(current)) { visited.add(current); current = posted!.anchors[current] }
    expect(current).toBe(referenceId)
  }
})

it.each([false, true])('requeues obsolete maps on admin opening only (public: %s)', async (shared) => {
  const queued: string[] = []
  vi.mocked(fetch).mockImplementation(async (input) => {
    const url = String(input)
    let payload: unknown = {
      id: 'set-1', name: 'Obsolete map', referenceSlideId: 'slide-1', status: 'ready', version: 1,
      members: [
        { slideId: 'slide-1', displayName: 'Reference', stain: 'H&E', tileSource: '/tiles/1.dzi', registration: null },
        { slideId: 'slide-2', displayName: 'Moving', stain: 'IHC', tileSource: '/tiles/2.dzi', registration: { status: 'stale', provenance: 'automatic', triangles: [] } },
      ],
    }
    if (url.endsWith('/session')) payload = { csrfToken: 'fixture-token' }
    if (url.endsWith('/jobs') || url.endsWith('/candidates')) payload = []
    if (url.endsWith('/register')) { queued.push(url); payload = { queuedPairs: 1 } }
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  const route = shared ? '/shared/share-1/comparisons/set-1' : '/admin/comparisons/set-1'
  render(<MemoryRouter initialEntries={[route]}><Routes><Route path={shared ? '/shared/:publicId/comparisons/:comparisonId' : '/admin/comparisons/:comparisonId'} element={<ComparisonPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Obsolete map')).toBeVisible()
  if (shared) expect(queued).toHaveLength(0)
  else await waitFor(() => expect(queued).toHaveLength(1))
})
