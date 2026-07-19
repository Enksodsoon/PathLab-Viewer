import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { ViewerPage } from '../pages/ViewerPage'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

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
