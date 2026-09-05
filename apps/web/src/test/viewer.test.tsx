import { readFileSync } from 'node:fs'

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { OpenSeadragonViewer } from '../components/OpenSeadragonViewer'
import { ViewerPage } from '../pages/ViewerPage'
import { ThemeProvider } from '../theme/ThemeProvider'

const viewerCss = readFileSync('src/styles.css', 'utf8')

const osdMock = vi.hoisted(() => {
  const handlers = new Map<string, () => void>()
  const viewer = {
    imageLoader: { jobLimit: 12 },
    viewport: {
      zoomBy: vi.fn(),
      goHome: vi.fn(),
      viewportToImageZoom: vi.fn(() => 2),
      getZoom: vi.fn(() => 1),
      getRotation: vi.fn(() => 0),
      setRotation: vi.fn(),
    },
    setFullScreen: vi.fn(),
    isFullPage: vi.fn(() => false),
    addHandler: vi.fn((name: string, handler: () => void) => handlers.set(name, handler)),
    removeAllHandlers: vi.fn((name: string) => { void name }),
    destroy: vi.fn(),
    open: vi.fn(),
  }
  return {
    factory: vi.fn((options: Record<string, unknown>) => { void options; return viewer }),
    handlers,
    viewer,
  }
})

vi.mock('openseadragon', () => ({ default: osdMock.factory }))

function setViewportWidth(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
}

function latestViewerOptions(): Record<string, unknown> {
  const call = osdMock.factory.mock.calls.at(-1)
  if (!call) throw new Error('OpenSeadragon was not initialized')
  return call[0] as Record<string, unknown>
}

function emitViewerEvent(name: string) {
  const handler = osdMock.handlers.get(name)
  if (!handler) throw new Error(`Missing OpenSeadragon handler: ${name}`)
  act(() => handler())
}

function renderViewer(onScaleChange = vi.fn()) {
  return render(
    <OpenSeadragonViewer
      tileSource="/tiles/public-1/slide.dzi"
      onReady={vi.fn()}
      micronsPerPixel={0.5}
      onScaleChange={onScaleChange}
    />,
  )
}

function renderViewerPage(route = '/s/public-1') {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/s/:publicId" element={<ViewerPage />} />
          <Route path="/admin/preview/:slideId" element={<ViewerPage />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  )
}

function publicSlideResponse() {
  return new Response(JSON.stringify({
    publicId: 'public-1',
    displayName: 'HER2 control',
    state: 'published',
    tileSource: '/tiles/public-1/slide.dzi',
    thumbnailUrl: '/tiles/public-1/thumbnail.jpg',
    metadata: { width: 24970, height: 31087, physicalSizeX: 0.5476 },
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  setViewportWidth(1024)
  osdMock.handlers.clear()
  osdMock.factory.mockClear()
  for (const value of Object.values(osdMock.viewer)) {
    if (typeof value === 'function' && 'mockClear' in value) value.mockClear()
  }
  for (const value of Object.values(osdMock.viewer.viewport)) value.mockClear()
})

it('uses bounded desktop loader and cache limits', () => {
  setViewportWidth(1200)
  renderViewer()

  expect(latestViewerOptions()).toMatchObject({
    imageLoaderLimit: 12,
    maxImageCacheCount: 100,
    animationTime: 0.45,
    blendTime: 0.05,
  })
})

it('offers a circular dial with cardinal and fine local rotation controls', () => {
  renderViewer()

  fireEvent.click(screen.getByRole('button', { name: 'Open rotation controls. Current rotation 0 degrees' }))
  fireEvent.click(screen.getByRole('button', { name: 'Rotate to 90 degrees' }))

  expect(osdMock.viewer.viewport.setRotation).toHaveBeenCalledWith(90)
  expect(screen.getByRole('button', { name: 'Open rotation controls. Current rotation 90 degrees' })).toBeInTheDocument()

  fireEvent.keyDown(screen.getByRole('slider', { name: 'Rotation dial' }), { key: 'ArrowLeft' })
  expect(osdMock.viewer.viewport.setRotation).toHaveBeenLastCalledWith(89)

  expect(screen.queryByText('drag', { exact: false })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Rotate to 0 degrees' }))
  expect(osdMock.viewer.viewport.setRotation).toHaveBeenLastCalledWith(0)
})

it('shows a prioritized poster until the first tile is visible', () => {
  render(
    <OpenSeadragonViewer
      tileSource="/tiles/public-1/slide.dzi"
      posterUrl="/tiles/public-1/thumbnail.jpg"
      onReady={vi.fn()}
    />,
  )

  const poster = screen.getByRole('img', { name: 'Slide preview' })
  expect(poster).toHaveAttribute('src', '/tiles/public-1/thumbnail.jpg')
  expect(poster).toHaveAttribute('fetchpriority', 'high')
  emitViewerEvent('open')
  expect(poster).toBeVisible()
  emitViewerEvent('tile-loaded')
  expect(screen.queryByRole('img', { name: 'Slide preview' })).not.toBeInTheDocument()
})

it('lets viewers choose and persist a bounded loading mode', () => {
  renderViewer()

  fireEvent.change(screen.getByRole('combobox', { name: 'Loading mode' }), {
    target: { value: 'data-saver' },
  })
  expect(osdMock.viewer.imageLoader.jobLimit).toBe(2)
  expect(localStorage.getItem('pathlab-viewer-loading-mode:v1')).toBe('data-saver')

  fireEvent.change(screen.getByRole('combobox', { name: 'Loading mode' }), {
    target: { value: 'full' },
  })
  expect(osdMock.viewer.imageLoader.jobLimit).toBe(12)
})

it('keeps the loaded canvas mounted and reports an offline connection', () => {
  renderViewer()
  act(() => window.dispatchEvent(new Event('offline')))

  expect(screen.getByRole('status')).toHaveTextContent('Offline')
  expect(osdMock.viewer.destroy).not.toHaveBeenCalled()
})

it('uses reduced loader and cache limits below 768 pixels', () => {
  setViewportWidth(500)
  renderViewer()

  expect(latestViewerOptions()).toMatchObject({
    imageLoaderLimit: 8,
    maxImageCacheCount: 50,
    showNavigator: false,
  })
})

it('sets bounded tile retry and request timeout options', () => {
  renderViewer()

  expect(latestViewerOptions()).toMatchObject({
    tileRetryMax: 1,
    tileRetryDelay: 1000,
    timeout: 20000,
  })
})

it('keeps one viewer instance and opens the next slide in place', () => {
  const view = render(
    <OpenSeadragonViewer tileSource="/tiles/first/slide.dzi" onReady={vi.fn()} />,
  )
  view.rerender(
    <OpenSeadragonViewer tileSource="/tiles/second/slide.dzi" onReady={vi.fn()} />,
  )
  expect(osdMock.factory).toHaveBeenCalledOnce()
  expect(osdMock.viewer.destroy).not.toHaveBeenCalled()
  expect(osdMock.viewer.open).toHaveBeenCalledWith('/tiles/second/slide.dzi')
})

it('cleans optional attachments before source replacement and viewer destruction', () => {
  const events: string[] = []
  const attach = vi.fn((viewer: unknown) => {
    void viewer
    events.push('attach')
    return () => events.push('cleanup')
  })
  const view = render(
    <OpenSeadragonViewer
      tileSource="/tiles/first/slide.dzi"
      onReady={vi.fn()}
      onViewerAttach={attach}
    />,
  )

  expect(attach).toHaveBeenCalledWith(osdMock.viewer)
  expect(events).toEqual(['attach'])

  view.rerender(
    <OpenSeadragonViewer
      tileSource="/tiles/second/slide.dzi"
      onReady={vi.fn()}
      onViewerAttach={attach}
    />,
  )
  expect(events).toEqual(['attach', 'cleanup', 'attach'])
  expect(osdMock.viewer.open).toHaveBeenCalledWith('/tiles/second/slide.dzi')

  view.unmount()
  expect(events).toEqual(['attach', 'cleanup', 'attach', 'cleanup'])
  expect(osdMock.viewer.destroy).toHaveBeenCalledOnce()
  expect(attach.mock.calls[0][0]).toBe(osdMock.viewer)
})

it('shows an asynchronous loading error when opening fails', async () => {
  vi.useFakeTimers()
  renderViewer()

  emitViewerEvent('open-failed')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  await act(async () => { await vi.runOnlyPendingTimersAsync() })
  expect(screen.getByRole('alert')).toHaveTextContent('Slide tiles could not be loaded')
})

it('bounds repeated tile failures before showing the loading error', async () => {
  vi.useFakeTimers()
  renderViewer()

  emitViewerEvent('tile-load-failed')
  emitViewerEvent('tile-load-failed')
  await act(async () => { await vi.runOnlyPendingTimersAsync() })
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  emitViewerEvent('tile-load-failed')
  emitViewerEvent('tile-load-failed')
  expect(vi.getTimerCount()).toBeGreaterThan(0)
  await act(async () => { await vi.runOnlyPendingTimersAsync() })
  expect(screen.getByRole('alert')).toBeVisible()
})

it('retries the tile source and clears the loading error', async () => {
  vi.useFakeTimers()
  renderViewer()
  emitViewerEvent('open-failed')
  await act(async () => { await vi.runOnlyPendingTimersAsync() })

  fireEvent.click(screen.getByRole('button', { name: 'Retry loading' }))
  expect(osdMock.viewer.open).toHaveBeenCalledWith('/tiles/public-1/slide.dzi')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('automatically retries an opening failure with bounded backoff', async () => {
  vi.useFakeTimers()
  renderViewer()
  emitViewerEvent('open-failed')

  await act(async () => { await vi.advanceTimersByTimeAsync(999) })
  expect(osdMock.viewer.open).not.toHaveBeenCalled()
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  expect(osdMock.viewer.open).toHaveBeenCalledWith('/tiles/public-1/slide.dzi')
})

it('does not cancel reconnection when callback props change', async () => {
  vi.useFakeTimers()
  const view = render(
    <OpenSeadragonViewer
      tileSource="/tiles/public-1/slide.dzi"
      onReady={vi.fn()}
      onScaleChange={vi.fn()}
    />,
  )
  emitViewerEvent('open-failed')
  view.rerender(
    <OpenSeadragonViewer
      tileSource="/tiles/public-1/slide.dzi"
      onReady={vi.fn()}
      onScaleChange={vi.fn()}
    />,
  )

  await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
  expect(osdMock.viewer.open).toHaveBeenCalledWith('/tiles/public-1/slide.dzi')
})

it('updates scale after open and animation finish only', () => {
  const onScaleChange = vi.fn()
  renderViewer(onScaleChange)

  emitViewerEvent('open')
  emitViewerEvent('animation-finish')
  expect(onScaleChange).toHaveBeenCalledTimes(2)
  expect(osdMock.handlers.has('animation')).toBe(false)
})

it('removes handlers, pending errors, and the viewer during cleanup', () => {
  vi.useFakeTimers()
  const clearInterval = vi.spyOn(window, 'clearInterval')
  const view = renderViewer()
  emitViewerEvent('open-failed')
  expect(vi.getTimerCount()).toBeGreaterThan(0)

  view.unmount()
  expect(clearInterval).toHaveBeenCalled()
  expect(osdMock.viewer.removeAllHandlers.mock.calls.map(([name]) => name)).toEqual([
    'open', 'tile-loaded', 'animation-finish', 'open-failed', 'tile-load-failed',
  ])
  expect(osdMock.viewer.destroy).toHaveBeenCalledOnce()
})

it('loads public metadata and exposes responsive viewer controls', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        publicId: 'public-1',
        displayName: 'HER2 control',
        state: 'published',
        tileSource: '/tiles/public-1/slide.dzi',
        thumbnailUrl: '/tiles/public-1/thumbnail.jpg',
        metadata: {
          width: 24970,
          height: 31087,
          physicalSizeX: 0.5476,
          physicalSizeUnit: 'MICROMETER',
        },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ),
  )
  const view = renderViewerPage()
  expect(await screen.findByText('HER2 control')).toBeVisible()
  expect(view.container.querySelector('.brand-mark-layers')).toBeInTheDocument()
  expect(screen.getByRole('group', { name: 'Theme preference' })).toBeVisible()
  expect(screen.getByRole('radio', { name: 'Light' })).toBeVisible()
  expect(screen.getByRole('radio', { name: 'Dark' })).toBeVisible()
  expect(screen.getByRole('radio', { name: 'System' })).toBeVisible()
  expect(screen.getByRole('button', { name: /zoom in/i })).toBeVisible()
  expect(screen.getByRole('button', { name: /home view/i })).toBeVisible()
  expect(screen.getByRole('img', { name: 'Slide preview' })).toHaveAttribute('src', '/tiles/public-1/thumbnail.jpg')
  expect(screen.getByText(/µm/)).toBeVisible()

  fireEvent.click(screen.getByRole('radio', { name: 'Dark' }))
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
  expect(osdMock.factory).toHaveBeenCalledOnce()
  expect(osdMock.viewer.destroy).not.toHaveBeenCalled()
})

it('keeps the authenticated private-preview API branch intact', async () => {
  const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        id: 'private-1',
        publicId: '',
        displayName: 'Private teaching slide',
        filename: 'private-slide.ome.tiff',
        sourceBytes: 1048576,
        state: 'ready_private',
        errorCode: null,
        errorMessage: null,
        tileSource: '/api/v1/admin/slides/private-1/tiles/slide.dzi',
        thumbnailUrl: '/api/v1/admin/slides/private-1/thumbnail',
        metadata: { width: 2048, height: 1024, physicalSizeX: 0.5 },
        annotationsEnabled: false,
        annotationVersion: 0,
        createdAt: '2026-07-26T00:00:00Z',
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ),
  )

  renderViewerPage('/admin/preview/private-1')

  expect(await screen.findByText('Private teaching slide')).toBeVisible()
  expect(fetch).toHaveBeenCalledWith(
    '/api/v1/admin/slides/private-1',
    { credentials: 'same-origin' },
  )
})

it('sends an expired private-preview session back to administrator sign in', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({ detail: { code: 'AUTH_REQUIRED' } }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    ),
  )

  renderViewerPage('/admin/preview/private-1')

  expect(await screen.findByRole('heading', { name: 'Administrator session expired' })).toBeVisible()
  expect(screen.getByText(/reopen this private slide and its annotation tools/i)).toBeVisible()
  expect(screen.getByRole('link', { name: 'Sign in again' })).toHaveAttribute(
    'href',
    '/admin?returnTo=%2Fadmin%2Fpreview%2Fprivate-1',
  )
  expect(screen.queryByText(/slide is unavailable/i)).not.toBeInTheDocument()
})

it.each([
  ['network failure', () => Promise.reject(new TypeError('Failed to fetch'))],
  ['server failure', () => Promise.resolve(new Response(null, { status: 503 }))],
])('retries a transient metadata %s', async (_label, firstResponse) => {
  const fetch = vi.spyOn(globalThis, 'fetch')
    .mockImplementationOnce(firstResponse)
    .mockResolvedValueOnce(publicSlideResponse())

  renderViewerPage()

  expect(await screen.findByRole('heading', { name: 'This slide could not be opened' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

  expect(await screen.findByText('HER2 control')).toBeVisible()
  expect(fetch).toHaveBeenCalledTimes(2)
})

it.each([404, 410])('keeps permanent metadata status %i unavailable without retry', async (status) => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status }))

  renderViewerPage()

  expect(await screen.findByRole('heading', { name: 'This slide is unavailable' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
})

it('loads annotation code and APIs only for an enabled private admin slide', async () => {
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const route = String(input)
    if (route === '/api/v1/admin/slides/private-1') {
      return new Response(JSON.stringify({
        id: 'private-1',
        publicId: '',
        displayName: 'Private teaching slide',
        filename: 'private-slide.ome.tiff',
        sourceBytes: 1048576,
        state: 'ready_private',
        errorCode: null,
        errorMessage: null,
        tileSource: '/api/v1/admin/slides/private-1/tiles/slide.dzi',
        thumbnailUrl: null,
        metadata: {
          width: 2048,
          height: 1024,
          physicalSizeX: 0.5,
          physicalSizeY: 0.75,
          physicalSizeUnit: 'MICROMETER',
        },
        annotationsEnabled: true,
        annotationVersion: 0,
        createdAt: '2026-07-26T00:00:00Z',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    if (route.endsWith('/manifest')) {
      return new Response(JSON.stringify({
        slideId: 'private-1',
        version: 0,
        bounds: { width: 2048, height: 1024 },
        calibration: { x: 0.5, y: 0.75, unit: 'µm' },
        activeCount: 0,
        trashedCount: 0,
        layers: [{
          id: '11111111-1111-4111-8111-111111111111',
          slideId: 'private-1',
          name: 'Findings',
          sortOrder: 0,
          visible: true,
          locked: false,
          opacity: 1,
          createdAt: '2026-07-26T00:00:00Z',
          updatedAt: '2026-07-26T00:00:00Z',
        }],
        limits: {
          activeAnnotations: 25000,
          layers: 100,
          verticesPerShape: 8192,
          verticesPerImport: 250000,
          batchOperations: 50,
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    if (route.includes('/items?')) {
      return new Response(JSON.stringify({
        items: [],
        total: 0,
        nextOffset: null,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    throw new Error(`Unexpected fetch: ${route}`)
  })

  renderViewerPage('/admin/preview/private-1')

  expect(await screen.findByRole('toolbar', { name: 'Annotation tools' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'More annotation tools' }))
  expect(await screen.findByRole(
    'button',
    { name: 'Point marker' },
    { timeout: 20_000 },
  )).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Open annotation inspector' }))
  fireEvent.click(screen.getByRole('button', { name: 'Show advanced annotation details' }))
  expect(await screen.findByRole('button', { name: 'Findings' })).toBeVisible()
  expect(fetch.mock.calls.some(([input]) => String(input).endsWith('/manifest'))).toBe(true)
  expect(fetch.mock.calls.some(([input]) => String(input).includes('/items?'))).toBe(true)
}, 20_000)

it('keeps the public slide branch annotation-free even if unknown fields are present', async () => {
  const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({
      publicId: 'public-1',
      displayName: 'HER2 control',
      state: 'published',
      tileSource: '/tiles/public-1/slide.dzi',
      thumbnailUrl: null,
      metadata: { width: 2048, height: 1024 },
      annotationsEnabled: true,
      annotationVersion: 99,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
  )

  renderViewerPage('/s/public-1')

  expect(await screen.findByText('HER2 control')).toBeVisible()
  expect(screen.queryByRole('toolbar', { name: 'Annotation tools' })).not.toBeInTheDocument()
  expect(screen.queryByText('Annotations')).not.toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(String(fetch.mock.calls[0][0])).toBe('/api/v1/public/slides/public-1')
})

it('shows a private-safe not found state', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 404 }))
  renderViewerPage('/s/missing')
  expect(await screen.findByText(/slide is unavailable/i)).toBeVisible()
})

it('keeps pathology posters and viewer stages free of theme color filters', () => {
  expect(viewerCss).not.toMatch(/(?:^|[;{])\s*(?:filter|mix-blend-mode)\s*:/m)
  expect(viewerCss).not.toMatch(/invert\(/i)
})
