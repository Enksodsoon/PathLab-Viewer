import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { AdminPage } from '../pages/AdminPage'

const SLIDE = {
  id: 'slide-1',
  publicId: 'public-1',
  displayName: 'HER2 control',
  filename: 'control.ome.tif',
  sourceBytes: 72_416_508,
  state: 'ready_private',
  errorCode: null,
  errorMessage: null,
  metadata: null,
  createdAt: '2026-07-19T10:00:00Z',
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.toString()
  return input.url
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  sessionStorage.clear()
})

it('uses an in-app confirmation before deleting a slide', async () => {
  sessionStorage.setItem('pathlab-csrf', 'csrf-token')
  const nativeConfirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  let deleted = false
  let deleteRequests = 0

  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = requestUrl(input)
    if (url === '/api/v1/admin/slides' && (init?.method ?? 'GET') === 'GET') {
      return new Response(JSON.stringify(deleted ? [] : [SLIDE]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    if (url === '/api/v1/admin/slides/slide-1' && init?.method === 'DELETE') {
      deleteRequests += 1
      deleted = true
      return new Response(null, { status: 204 })
    }
    throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
  })

  render(<AdminPage />, { wrapper: MemoryRouter })
  await userEvent.click(await screen.findByRole('button', { name: /delete her2 control/i }))

  expect(nativeConfirm).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog', { name: /delete slide/i })).toBeVisible()
  expect(deleteRequests).toBe(0)

  await userEvent.click(screen.getByRole('button', { name: /^delete slide$/i }))
  await waitFor(() => expect(deleteRequests).toBe(1))
  await waitFor(() => expect(screen.queryByRole('dialog', { name: /delete slide/i })).not.toBeInTheDocument())
})
