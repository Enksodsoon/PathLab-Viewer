import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { DesktopConnectPage } from '../pages/DesktopConnectPage'

function renderPage(code: string) {
  return render(
    <MemoryRouter
      initialEntries={[`/admin/connect?code=${encodeURIComponent(code)}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <DesktopConnectPage />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  sessionStorage.clear()
})

it('shows a normalized valid pairing code ready for explicit approval', () => {
  renderPage('abcd-efgh')

  expect(screen.getByText('ABCD-EFGH')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Approve this Forge device' })).toBeEnabled()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('rejects an invalid pairing code before making a request', async () => {
  const request = vi.spyOn(globalThis, 'fetch')
  renderPage('ABCD-10IO')

  expect(screen.getByRole('alert')).toHaveTextContent(
    'This pairing code is invalid, expired, or already used.',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Approve this Forge device' }))
  expect(request).not.toHaveBeenCalled()
})

it('approves the code through the existing desktop API and shows completion', async () => {
  sessionStorage.setItem('pathlab-csrf', 'csrf-token')
  const request = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(null, { status: 204 }),
  )
  renderPage('ABCD-EFGH')

  await userEvent.click(screen.getByRole('button', { name: 'Approve this Forge device' }))

  expect(await screen.findByRole('status')).toHaveTextContent('Forge connected')
  const [input, init] = request.mock.calls[0] ?? []
  expect(input).toBe('/api/v1/desktop/pairings/approve')
  expect(init?.method).toBe('POST')
  expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe('csrf-token')
  expect(JSON.parse(String(init?.body))).toEqual({ userCode: 'ABCD-EFGH' })
})

it('shows sign-in-required state when approval has no administrator session', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
    JSON.stringify({ detail: { code: 'AUTHENTICATION_REQUIRED' } }),
    { status: 401, headers: { 'Content-Type': 'application/json' } },
  ))
  renderPage('ABCD-EFGH')

  await userEvent.click(screen.getByRole('button', { name: 'Approve this Forge device' }))

  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(
    'Sign in to Viewer, then reopen this verification link.',
  ))
  expect(screen.getByRole('button', { name: 'Approve this Forge device' })).toBeEnabled()
})
