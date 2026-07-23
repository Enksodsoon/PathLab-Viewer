import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { AdminPage } from '../pages/AdminPage'

const SLIDE = {
  id: 'slide-privacy',
  publicId: 'public-privacy',
  displayName: 'Teaching slide',
  filename: 'teaching.ome.tif',
  sourceBytes: 10_000,
  state: 'ready_private',
  errorCode: null,
  errorMessage: null,
  metadata: null,
  createdAt: '2026-07-23T03:00:00Z',
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

it('requires an explicit de-identification check before publishing', async () => {
  sessionStorage.setItem('pathlab-csrf', 'csrf-token')
  let published = false
  let publishRequests = 0

  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = requestUrl(input)
    if (url === '/api/v1/admin/slides' && (init?.method ?? 'GET') === 'GET') {
      return new Response(JSON.stringify([{
        ...SLIDE,
        state: published ? 'published' : 'ready_private',
      }]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    if (url === '/api/v1/admin/slides/slide-privacy/publish' && init?.method === 'POST') {
      publishRequests += 1
      published = true
      return new Response(JSON.stringify({ ...SLIDE, state: 'published' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`)
  })

  render(<AdminPage />, { wrapper: MemoryRouter })
  await userEvent.click(await screen.findByRole('button', { name: /^publish$/i }))

  expect(screen.getByRole('dialog', { name: /publish slide/i })).toBeVisible()
  expect(screen.getByText(/anyone with the link can view/i)).toBeVisible()
  expect(screen.getByText(/patient names, medical record numbers, dates of birth/i)).toBeVisible()
  expect(publishRequests).toBe(0)

  const publishButton = screen.getByRole('button', { name: /^publish slide$/i })
  expect(publishButton).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /slide is de-identified/i }))
  expect(publishButton).toBeEnabled()
  await userEvent.click(publishButton)

  await waitFor(() => expect(publishRequests).toBe(1))
  await waitFor(() => {
    expect(screen.queryByRole('dialog', { name: /publish slide/i })).not.toBeInTheDocument()
  })
})
