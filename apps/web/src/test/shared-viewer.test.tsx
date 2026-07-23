import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SharedViewerPage } from '../pages/SharedViewerPage'

const osd = vi.hoisted(() => {
  const viewer = {
    viewport: {
      zoomBy: vi.fn(),
      goHome: vi.fn(),
      viewportToImageZoom: vi.fn(() => 1),
      getZoom: vi.fn(() => 1),
    },
    setFullScreen: vi.fn(),
    isFullPage: vi.fn(() => false),
    addHandler: vi.fn(),
    removeAllHandlers: vi.fn(),
    destroy: vi.fn(),
    open: vi.fn(),
  }
  return { factory: vi.fn(() => viewer), viewer }
})

vi.mock('openseadragon', () => ({ default: osd.factory }))

const MANIFEST = {
  publicId: 'share-public',
  targetType: 'folder',
  name: 'GI teaching set',
  description: 'Safe slides',
  expiresAt: null,
  slides: [
    {
      position: 0,
      displayName: 'Colon adenocarcinoma',
      organSite: 'Colon',
      stain: 'H&E',
      diagnosis: 'Adenocarcinoma',
      tags: ['Teaching'],
      teachingNote: 'Safe note',
      thumbnailUrl: '/thumb/0',
      tileSource: '/tiles/public-1/slide.dzi',
      scale: 0.5,
    },
    {
      position: 1,
      displayName: 'Normal colon',
      organSite: 'Colon',
      stain: 'H&E',
      diagnosis: 'Normal',
      tags: [],
      teachingNote: '',
      thumbnailUrl: '/thumb/1',
      tileSource: '/tiles/public-2/slide.dzi',
      scale: 0.5,
    },
  ],
}

function renderShare() {
  return render(
    <MemoryRouter initialEntries={['/f/share-public']}>
      <Routes>
        <Route
          path="/f/:publicId"
          element={<SharedViewerPage targetType="folder" />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
    JSON.stringify(MANIFEST),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  ))
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  sessionStorage.clear()
  osd.factory.mockClear()
  osd.viewer.open.mockClear()
  osd.viewer.destroy.mockClear()
})

describe('shared library viewer', () => {
  it('switches slides through one persistent OpenSeadragon instance', async () => {
    renderShare()
    expect(await screen.findByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()
    await waitFor(() => expect(osd.factory).toHaveBeenCalledOnce())
    await userEvent.click(screen.getByRole('button', { name: 'Next slide' }))
    expect(await screen.findByRole('heading', { name: 'Normal colon' })).toBeVisible()
    expect(osd.factory).toHaveBeenCalledOnce()
    expect(osd.viewer.destroy).not.toHaveBeenCalled()
    expect(osd.viewer.open).toHaveBeenCalledWith('/tiles/public-2/slide.dzi')
    expect(sessionStorage.getItem('pathlab-share-position:folder:share-public')).toBe('1')
  })

  it('supports keyboard navigation, search, and the mobile drawer contract', async () => {
    const { container } = renderShare()
    await screen.findByRole('heading', { name: 'Colon adenocarcinoma' })
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(await screen.findByRole('heading', { name: 'Normal colon' })).toBeVisible()
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(await screen.findByRole('heading', { name: 'Colon adenocarcinoma' })).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'Open slide navigator' }))
    expect(container.querySelector('.shared-viewer-shell')).toHaveClass('drawer-open')
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search shared slides' }), 'normal')
    expect(screen.queryByRole('button', { name: /Colon adenocarcinoma/ })).not.toBeInTheDocument()
  })

  it('uses the same privacy-safe state for unknown, expired, or revoked links', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ detail: { code: 'SHARE_NOT_FOUND' } }),
      { status: 404, headers: { 'Content-Type': 'application/json' } },
    ))
    renderShare()
    expect(await screen.findByText(/shared library is unavailable/i)).toBeVisible()
    await waitFor(() => expect(screen.getByText(/incorrect, expired, or revoked/i)).toBeVisible())
  })
})
