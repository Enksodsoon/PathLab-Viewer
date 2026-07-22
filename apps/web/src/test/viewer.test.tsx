import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { OpenSeadragonViewer } from '../components/OpenSeadragonViewer'
import { ViewerPage } from '../pages/ViewerPage'

const osdMock = vi.hoisted(() => {
  const handlers = new Map<string, () => void>()
  const viewer = {
    viewport: {
      zoomBy: vi.fn(),
      goHome: vi.fn(),
      viewportToImageZoom: vi.fn(() => 2),
      getZoom: vi.fn(() => 1),
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

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
  setViewportWidth(1024)
  osdMock.handlers.clear()
  osdMock.factory.mockClear()
  for (const value of Object.values(osdMock.viewer)) {
    if (typeof value === 'function' && 'mockClear' in value) value.mockClear()
  }
  for (const value of Object.values(osdMock.viewer.viewport)) value.mockClear()
})

it('uses conservative desktop loader and cache limits', () => {
  setViewportWidth(1200)
  renderViewer()

  expect(latestViewerOptions()).toMatchObject({
    imageLoaderLimit: 10,
    maxImageCacheCount: 100,
  })
})

it('uses reduced loader and cache limits below 768 pixels', () => {
  setViewportWidth(500)
  renderViewer()

  expect(latestViewerOptions()).toMatchObject({
    imageLoaderLimit: 6,
    maxImageCacheCount: 50,
  })
})

it('sets bounded tile retry and request timeout options', () => {
  renderViewer()

  expect(latestViewerOptions()).toMatchObject({
    tileRetryMax: 2,
    tileRetryDelay: 500,
    timeout: 20000,
  })
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
  expect(vi.getTimerCount()).toBe(1)
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
  const view = renderViewer()
  emitViewerEvent('open-failed')
  expect(vi.getTimerCount()).toBe(1)

  view.unmount()
  expect(vi.getTimerCount()).toBe(0)
  expect(osdMock.viewer.removeAllHandlers.mock.calls.map(([name]) => name)).toEqual([
    'open', 'animation-finish', 'open-failed', 'tile-load-failed',
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
  render(
    <MemoryRouter initialEntries={['/s/public-1']}>
      <Routes>
        <Route path="/s/:publicId" element={<ViewerPage />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByText('HER2 control')).toBeVisible()
  expect(screen.getByRole('button', { name: /zoom in/i })).toBeVisible()
  expect(screen.getByRole('button', { name: /home view/i })).toBeVisible()
  expect(screen.getByText(/µm/)).toBeVisible()
})

it('shows a private-safe not found state', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 404 }))
  render(
    <MemoryRouter initialEntries={['/s/missing']}>
      <Routes>
        <Route path="/s/:publicId" element={<ViewerPage />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByText(/slide is unavailable/i)).toBeVisible()
})
