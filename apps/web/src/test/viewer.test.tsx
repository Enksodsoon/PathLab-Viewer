import { readFileSync } from 'node:fs'

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { OpenSeadragonViewer, type ViewerHandle } from '../components/OpenSeadragonViewer'
import { ViewerPage } from '../pages/ViewerPage'
import { ThemeProvider } from '../theme/ThemeProvider'

const viewerCss = readFileSync('src/styles.css', 'utf8')

const osdMock = vi.hoisted(() => {
  const handlers = new Map<string, () => void>()
  const viewer = {
    imageLoader: { jobLimit: 12 },
    container: { clientWidth: 800, clientHeight: 600 },
    viewport: {
      zoomBy: vi.fn(),
      goHome: vi.fn(),
      viewportToImageZoom: vi.fn(() => 2),
      getZoom: vi.fn(() => 1),
      getRotation: vi.fn(() => 0),
      setRotation: vi.fn(),
      getCenter: vi.fn(() => ({ x: 0, y: 0 })),
      getBounds: vi.fn(() => ({ x: -200, y: -150, width: 400, height: 300, getBoundingBox: () => ({ x: -200, y: -150, width: 400, height: 300 }) })),
      viewportToImageRectangle: vi.fn((bounds: unknown) => bounds),
      viewportToImageCoordinates: vi.fn((point: { x: number, y: number }) => point),
      imageToViewportCoordinates: vi.fn((x: number, y: number) => ({ x, y })),
      imageToViewportZoom: vi.fn((zoom: number) => zoom),
      panTo: vi.fn(),
      zoomTo: vi.fn(),
      applyConstraints: vi.fn(),
      imageToViewportRectangle: vi.fn((x: number, y: number, width: number, height: number) => ({ x, y, width, height })),
      fitBounds: vi.fn(),
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
    metadata: { width: 24970, height: 31087, physicalSizeX: 0.5476, physicalSizeY: 0.5476, physicalSizeUnit: 'um' },
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

it.each([false, true])('renders a usable escape while metadata is still loading (private=%s)', async (privateRoute) => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise<Response>(() => {}))
  render(<MemoryRouter initialEntries={[{pathname: privateRoute ? '/admin/preview/private-1' : '/s/public-1', state: {library: {returnTo: '/admin?location=folder%3Aone&q=kidney', slides: []}}}]}><Routes>
    <Route path="/s/:publicId" element={<ViewerPage />} />
    <Route path="/admin/preview/:slideId" element={<ViewerPage />} />
    <Route path="/admin" element={<h1>Returned library</h1>} />
    <Route path="/" element={<h1>Returned home</h1>} />
  </Routes></MemoryRouter>)
  expect(screen.getByRole('status')).toHaveTextContent('Opening slide')
  const exit = screen.getByRole('link', {name: privateRoute ? 'Library' : 'Home'})
  expect(exit).toHaveAttribute('href', privateRoute ? '/admin?location=folder%3Aone&q=kidney' : '/')
  fireEvent.click(exit)
  expect(screen.getByRole('heading', {name: privateRoute ? 'Returned library' : 'Returned home'})).toBeVisible()
})

it.each([404, 503])('public metadata error %s offers Home without exposing Library', async (status) => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, {status}))
  renderViewerPage()
  await screen.findByRole('heading', {name: status === 404 ? 'This slide is unavailable' : 'This slide could not be opened'})
  expect(screen.getByRole('link', {name: 'Home'})).toHaveAttribute('href', '/')
  expect(screen.queryByRole('link', {name: 'Library'})).not.toBeInTheDocument()
})

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

it('keeps viewing and loading controls working when local storage is blocked', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('Blocked', 'SecurityError') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Blocked', 'SecurityError') })
  renderViewer()
  fireEvent.change(screen.getByRole('combobox', { name: 'Loading mode' }), { target: { value: 'data-saver' } })
  expect(osdMock.viewer.imageLoader.jobLimit).toBe(2)
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

it('keeps synchronized rotation visible and resets orientation with the home handle', () => {
  let handle: ViewerHandle | null = null
  render(
    <OpenSeadragonViewer
      tileSource="/tiles/public-1/slide.dzi"
      onReady={(value) => { handle = value }}
    />,
  )

  expect(handle).not.toBeNull()
  osdMock.viewer.viewport.applyConstraints.mockClear()
  act(() => handle!.setImageViewport({ centerX: 40, centerY: 30, imageZoom: 2, rotation: 90 }))
  expect(osdMock.viewer.viewport.panTo).toHaveBeenLastCalledWith({ x: 40, y: 30 }, true)
  expect(osdMock.viewer.viewport.zoomTo).toHaveBeenLastCalledWith(2, { x: 40, y: 30 }, true)
  expect(osdMock.viewer.viewport.applyConstraints).not.toHaveBeenCalled()
  expect(handle!.getImageViewport().visibleRadiusPixels).toBe(150)
  expect(screen.getByRole('button', { name: 'Open rotation controls. Current rotation 90 degrees' })).toBeInTheDocument()

  act(() => handle!.home())
  expect(osdMock.viewer.viewport.goHome).toHaveBeenCalled()
  expect(osdMock.viewer.viewport.setRotation).toHaveBeenLastCalledWith(0)
  expect(screen.getByRole('button', { name: 'Open rotation controls. Current rotation 0 degrees' })).toBeInTheDocument()
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

it('applies externally controlled detail modes within the network profile without reopening the viewer', () => {
  localStorage.setItem('pathlab-viewer-loading-mode:v1', 'data-saver')
  const onReady = vi.fn()
  const profile = { maximumJobLimit: 4 }
  const view = render(<OpenSeadragonViewer tileSource="/tiles/public-1/slide.dzi" onReady={onReady} showLoadingMode={false} loadingMode="full" networkProfile={profile} />)
  expect(screen.queryByRole('combobox', { name: 'Loading mode' })).not.toBeInTheDocument()
  expect(latestViewerOptions().imageLoaderLimit).toBe(4)
  osdMock.viewer.open.mockClear()
  view.rerender(<OpenSeadragonViewer tileSource="/tiles/public-1/slide.dzi" onReady={onReady} showLoadingMode={false} loadingMode="data-saver" networkProfile={profile} />)
  expect(osdMock.viewer.imageLoader.jobLimit).toBe(2)
  expect(localStorage.getItem('pathlab-viewer-loading-mode:v1')).toBe('data-saver')
  view.rerender(<OpenSeadragonViewer tileSource="/tiles/public-1/slide.dzi" onReady={onReady} showLoadingMode={false} loadingMode="full" networkProfile={{ initialJobLimit: 2, maximumJobLimit: 4 }} />)
  expect(osdMock.viewer.imageLoader.jobLimit).toBe(2)
  expect(osdMock.viewer.open).not.toHaveBeenCalled()
  expect(osdMock.viewer.destroy).not.toHaveBeenCalled()
})

it('keeps the loaded canvas mounted and reports an offline connection', () => {
  renderViewer()
  act(() => window.dispatchEvent(new Event('offline')))

  expect(screen.getByRole('status')).toHaveTextContent('Offline')
  expect(osdMock.viewer.destroy).not.toHaveBeenCalled()
})

it('uses the canvas renderer when the optional offscreen context constructor is absent', () => {
  vi.stubGlobal('OffscreenCanvasRenderingContext2D', undefined)
  try {
    renderViewer()
    expect(latestViewerOptions().drawer).toBe('canvas')
    cleanup()
    vi.stubGlobal('OffscreenCanvasRenderingContext2D', class {})
    renderViewer()
    expect(latestViewerOptions().drawer).toEqual(['auto', 'webgl', 'canvas', 'html'])
  } finally {
    vi.unstubAllGlobals()
  }
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

it('clears transient tile failures after a tile loads successfully', async () => {
  vi.useFakeTimers()
  renderViewer()

  emitViewerEvent('tile-load-failed')
  emitViewerEvent('tile-load-failed')
  emitViewerEvent('tile-loaded')
  emitViewerEvent('tile-load-failed')
  emitViewerEvent('tile-load-failed')
  emitViewerEvent('tile-load-failed')
  emitViewerEvent('tile-load-failed')
  await act(async () => { await vi.runOnlyPendingTimersAsync() })

  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('reports image close and reopen using current callbacks without recreating its viewer', () => {
  const firstClose = vi.fn(), currentClose = vi.fn(), onOpen = vi.fn(), onReady = vi.fn(), onDispose = vi.fn()
  const view = render(<OpenSeadragonViewer tileSource="/tiles/public-1/slide.dzi" onReady={onReady} onOpen={onOpen} onClose={firstClose} onDispose={onDispose} />)
  emitViewerEvent('open')
  expect(onOpen).toHaveBeenCalledOnce()
  const instanceCount = osdMock.factory.mock.calls.length
  view.rerender(<OpenSeadragonViewer tileSource="/tiles/public-1/slide.dzi" onReady={onReady} onOpen={onOpen} onClose={currentClose} onDispose={onDispose} />)
  act(() => osdMock.handlers.get('close')?.())
  expect(currentClose).toHaveBeenCalledOnce()
  expect(firstClose).not.toHaveBeenCalled()
  expect(onDispose).not.toHaveBeenCalled()
  expect(osdMock.factory).toHaveBeenCalledTimes(instanceCount)
  emitViewerEvent('open')
  expect(onOpen).toHaveBeenCalledTimes(2)
  expect(onReady).toHaveBeenCalledOnce()
  view.unmount()
  expect(osdMock.viewer.removeAllHandlers).toHaveBeenCalledWith('close')
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

it('updates the physical scale after an immediate synchronized viewport change', () => {
  const onScaleChange = vi.fn()
  let handle: ViewerHandle | null = null
  render(
    <OpenSeadragonViewer
      tileSource="/tiles/public-1/slide.dzi"
      micronsPerPixel={0.25}
      onReady={(value) => { handle = value }}
      onScaleChange={onScaleChange}
    />,
  )

  act(() => handle!.setImageViewport({ centerX: 40, centerY: 30, imageZoom: 2, rotation: 15 }))

  expect(onScaleChange).toHaveBeenCalledOnce()
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
    'close', 'open', 'tile-loaded', 'animation-finish', 'pan', 'zoom', 'rotate', 'after-resize', 'open-failed', 'tile-load-failed',
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
          physicalSizeY: 0.5476,
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
        metadata: { width: 2048, height: 1024, physicalSizeX: 0.5, physicalSizeY: 0.5, physicalSizeUnit: 'um' },
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
  await waitFor(() => expect(screen.getByRole('button', { name: 'More annotation tools' })).toBeEnabled())
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


it('does not swallow the first user drag after a synchronized viewport update', () => {
  let handle: ViewerHandle | undefined
  const onViewportChange = vi.fn()
  const { container } = render(<OpenSeadragonViewer tileSource="/tiles/test.dzi" onReady={(value) => { handle = value }} onViewportChange={onViewportChange} />)
  act(() => handle!.setImageViewport({ centerX: 25, centerY: 30, imageZoom: 1, rotation: 12.345 }, 'sync-1'))
  expect(osdMock.viewer.viewport.setRotation).toHaveBeenLastCalledWith(expect.closeTo(12.345, 6))
  fireEvent.pointerDown(container.querySelector('.osd-surface')!)
  emitViewerEvent('animation-finish')
  expect(onViewportChange).toHaveBeenLastCalledWith(expect.any(Object), undefined)
})


it('does not promote an initial image load into a driving user gesture', () => {
  const onViewportChange = vi.fn()
  render(<OpenSeadragonViewer tileSource="/tiles/test.dzi" onReady={vi.fn()} onViewportChange={onViewportChange} />)
  emitViewerEvent('open')
  emitViewerEvent('animation-finish')
  expect(onViewportChange).not.toHaveBeenCalled()
})


it('avoids a filter stacking context for neutral display while retaining requested adjustments', () => {
  const { container, rerender } = render(<OpenSeadragonViewer tileSource="/tiles/test.dzi" onReady={vi.fn()} />)
  const surface = container.querySelector('.osd-surface > div') as HTMLElement
  expect(surface.style.filter).toBe('none')
  rerender(<OpenSeadragonViewer tileSource="/tiles/test.dzi" onReady={vi.fn()} displayAdjustments={{ brightness: 1.2, contrast: 1, gamma: 1 }} />)
  expect(surface.style.filter).toContain('brightness(1.2)')
  expect(surface.style.filter).toContain('url(#slide-gamma-')
})

it.each(['/tiles/s/0/0_0.jpg', '/_pathlab_ome/7/0_0.jpg'])('samples slow tile resources from %s', async (path) => {
  vi.useFakeTimers()
  let receive: PerformanceObserverCallback | undefined
  const Observer = vi.fn(function (callback: PerformanceObserverCallback) {
    receive = callback
    return { observe: vi.fn(), disconnect: vi.fn() }
  })
  const previous = globalThis.PerformanceObserver
  Object.defineProperty(globalThis, 'PerformanceObserver', { configurable: true, value: Observer })
  try {
    renderViewer()
    expect(receive).toBeDefined()
    const entries = Array.from({ length: 12 }, () => ({ name: path, transferSize: 100, duration: 2500 }))
    act(() => receive!({ getEntries: () => entries } as unknown as PerformanceObserverEntryList, {} as PerformanceObserver))
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(osdMock.viewer.imageLoader.jobLimit).toBe(2)
  } finally {
    cleanup()
    Object.defineProperty(globalThis, 'PerformanceObserver', { configurable: true, value: previous })
  }
})

it('uses the horizontal screen axis for an anisotropic scale bar after rotation', () => {
  const onScaleChange = vi.fn()
  render(<OpenSeadragonViewer tileSource="/tiles/public-1/slide.dzi" micronsPerPixel={0.25} micronsPerPixelY={0.5} onReady={() => {}} onScaleChange={onScaleChange} />)
  osdMock.viewer.viewport.getRotation.mockReturnValue(90)
  emitViewerEvent('open')
  const [microns, width] = onScaleChange.mock.calls.at(-1)!
  expect(microns / width).toBeCloseTo(0.5 / 2)
  osdMock.viewer.viewport.getRotation.mockReturnValue(0)
})

it('refreshes the anisotropic physical scale immediately on rotation', () => {
  const onScaleChange = vi.fn()
  render(<OpenSeadragonViewer tileSource="/tiles/public-1/slide.dzi" micronsPerPixel={0.25} micronsPerPixelY={0.5} onReady={() => {}} onScaleChange={onScaleChange} />)
  emitViewerEvent('open')
  expect(onScaleChange.mock.calls.at(-1)![0] / onScaleChange.mock.calls.at(-1)![1]).toBeCloseTo(0.25 / 2)
  osdMock.viewer.viewport.getRotation.mockReturnValue(90)
  try {
    emitViewerEvent('rotate')
    expect(onScaleChange).toHaveBeenCalledTimes(2)
    const [microns, width] = onScaleChange.mock.calls.at(-1)!
    expect(microns / width).toBeCloseTo(0.5 / 2)
  } finally { osdMock.viewer.viewport.getRotation.mockReturnValue(0) }
})

it.each([
  { angle: 0, restored: false }, { angle: 37, restored: false }, { angle: 90, restored: false },
  { angle: 5.68e-14, restored: false }, { angle: -5.68e-14, restored: false },
  { angle: 360 - 1e-10, restored: false }, { angle: 360, restored: false },
  { angle: 5.68e-14, restored: true },
])('reports axis-aligned image bounds for the real OSD Rect at $angle degrees (restored=$restored)', async ({ angle, restored }) => {
  const { default: OpenSeadragon } = await vi.importActual<{ default: typeof import('openseadragon') }>('openseadragon')
  const center = { x: 557.8588, y: 331.5 }, width = 1166.8407, height = 1133.7277
  const rectangle = new OpenSeadragon.Rect(center.x - width / 2, center.y - height / 2, width, height).rotate(-angle)
  const boundsImplementation = osdMock.viewer.viewport.getBounds.getMockImplementation()!
  const centerImplementation = osdMock.viewer.viewport.getCenter.getMockImplementation()!
  const rotationImplementation = osdMock.viewer.viewport.getRotation.getMockImplementation()!
  osdMock.viewer.viewport.getBounds.mockReturnValue(rectangle)
  osdMock.viewer.viewport.getCenter.mockReturnValue(center)
  osdMock.viewer.viewport.getRotation.mockReturnValue(restored ? 0 : angle)
  let handle: ViewerHandle | null = null
  const onViewportChange = vi.fn()
  try {
    render(<OpenSeadragonViewer tileSource="/tiles/public-1/slide.dzi" onReady={value => { handle = value }} onViewportChange={onViewportChange} />)
    emitViewerEvent('open')
    if (restored) {
      act(() => handle!.setImageViewport({ centerX: center.x, centerY: center.y, imageZoom: 2, rotation: 0 }, 'restore-field'))
      expect(osdMock.viewer.viewport.panTo).toHaveBeenLastCalledWith(center, true)
      expect(osdMock.viewer.viewport.setRotation).toHaveBeenLastCalledWith(0)
    } else fireEvent.pointerDown(document.querySelector('.osd-surface')!)
    emitViewerEvent('animation-finish')
    // Independent envelope of a centered, rotated viewport, in original pixels.
    const radians = angle * Math.PI / 180
    const envelopeWidth = Math.abs(Math.cos(radians)) * width + Math.abs(Math.sin(radians)) * height
    const envelopeHeight = Math.abs(Math.sin(radians)) * width + Math.abs(Math.cos(radians)) * height
    const expected = [center.x - envelopeWidth / 2, center.y - envelopeHeight / 2, envelopeWidth, envelopeHeight]
    const actual = handle!.getImageViewport()
    const reported = onViewportChange.mock.calls.at(-1)![0]
    for (const snapshot of [actual, reported]) {
      expect(snapshot.centerX).toBe(center.x)
      expect(snapshot.centerY).toBe(center.y)
      for (const [index, value] of snapshot.visibleBounds!.entries()) expect(value).toBeCloseTo(expected[index], 8)
      const [left, top, extentX, extentY] = snapshot.visibleBounds!
      expect(left).toBeLessThanOrEqual(center.x)
      expect(left + extentX).toBeGreaterThanOrEqual(center.x)
      expect(top).toBeLessThanOrEqual(center.y)
      expect(top + extentY).toBeGreaterThanOrEqual(center.y)
    }
    if (restored) expect(onViewportChange.mock.calls.at(-1)![1]).toBe('restore-field')
  } finally {
    osdMock.viewer.viewport.getBounds.mockImplementation(boundsImplementation)
    osdMock.viewer.viewport.getCenter.mockImplementation(centerImplementation)
    osdMock.viewer.viewport.getRotation.mockImplementation(rotationImplementation)
  }
})

it('reports actual visible image bounds alongside user navigation coordinates', () => {
  const onViewportChange = vi.fn()
  render(<OpenSeadragonViewer tileSource="/tiles/public-1/slide.dzi" onReady={() => {}} onViewportChange={onViewportChange} />)
  fireEvent.pointerDown(document.querySelector('.osd-surface')!)
  emitViewerEvent('animation-finish')
  expect(onViewportChange).toHaveBeenCalledWith(expect.objectContaining({ visibleBounds: [-200, -150, 400, 300], centerX: 0, centerY: 0, imageZoom: 2 }), undefined)
})

it.each([{ size: 0.25, unit: 'um' }, { size: 250, unit: 'nm' }, { size: 0.00025, unit: 'mm' }])('renders the same physical scale bar for declared $unit metadata', async ({ size, unit }) => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ publicId: 'public-1', displayName: 'Calibrated image', state: 'published', tileSource: '/tiles/public-1/slide.dzi', metadata: { width: 640, height: 480, physicalSizeX: size, physicalSizeY: size, physicalSizeUnit: unit } }), { status: 200 })))
  render(<ThemeProvider><MemoryRouter initialEntries={['/slide/public-1']}><Routes><Route path="/slide/:publicId" element={<ViewerPage />} /></Routes></MemoryRouter></ThemeProvider>)
  await screen.findByText('Calibrated image')
  act(() => emitViewerEvent('open'))
  expect(screen.getByText('10 µm')).toBeVisible()
  expect(document.querySelector('.scale-bar i')).toHaveStyle({ width: '80px' })
})
