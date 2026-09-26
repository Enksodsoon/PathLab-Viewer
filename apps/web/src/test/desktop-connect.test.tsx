import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { DesktopConnectPage } from '../pages/DesktopConnectPage'
import { AdminPage } from '../pages/AdminPage'
import { ThemeProvider } from '../theme/ThemeProvider'

function renderPage(code: string) {
  return render(
    <MemoryRouter
      initialEntries={[`/admin/connect?code=${encodeURIComponent(code)}`]}
    >
      <DesktopConnectPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  })))
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
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
    'Sign in to Viewer to return to this verification code.',
  ))
  expect(screen.getByRole('link', {name: 'Sign in to Viewer'})).toHaveAttribute('href', '/admin?returnTo=%2Fadmin%2Fconnect%3Fcode%3DABCD-EFGH')
  expect(screen.getByRole('button', { name: 'Approve this Forge device' })).toBeEnabled()
})

function CodeNavigation() {
  const navigate = useNavigate()
  return <><DesktopConnectPage /><button onClick={() => navigate('/admin/connect?code=JKLM-NPQR')}>Change code</button></>
}

it.each([204, 400])('resets completed approval state when the query code changes (%s)', async (status) => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, {status}))
  render(<MemoryRouter initialEntries={['/admin/connect?code=ABCD-EFGH']}><CodeNavigation /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', {name: 'Approve this Forge device'}))
  await screen.findByRole(status === 204 ? 'status' : 'alert')
  fireEvent.click(screen.getByRole('button', {name: 'Change code'}))
  expect(screen.getByText('JKLM-NPQR')).toBeVisible()
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getByRole('button', {name: 'Approve this Forge device'})).toBeEnabled()
})

it('ignores an old pending approval after changing the query code', async () => {
  let resolve!: (response: Response) => void
  vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise<Response>((done) => {resolve = done}))
  render(<MemoryRouter initialEntries={['/admin/connect?code=ABCD-EFGH']}><CodeNavigation /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', {name: 'Approve this Forge device'}))
  fireEvent.click(screen.getByRole('button', {name: 'Change code'}))
  await act(async () => {resolve(new Response(null, {status: 204}))})
  expect(screen.getByText('JKLM-NPQR')).toBeVisible()
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getByRole('button', {name: 'Approve this Forge device'})).toBeEnabled()
})

it('returns through actual sign in to the original pairing query without auto-approval', async () => {
  const requests = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (String(input) === '/api/v1/auth/session' && init?.method === 'POST') return new Response(JSON.stringify({csrfToken: 'synthetic-csrf'}), {status: 200})
    return new Response(JSON.stringify({detail: {code: 'AUTHENTICATION_REQUIRED'}}), {status: 401})
  })
  render(<ThemeProvider><MemoryRouter initialEntries={['/admin/connect?code=abcd-efgh&source=forge']}><Routes>
    <Route path="/admin/connect" element={<DesktopConnectPage />} />
    <Route path="/admin" element={<AdminPage />} />
  </Routes></MemoryRouter></ThemeProvider>)
  await userEvent.click(screen.getByRole('button', {name: 'Approve this Forge device'}))
  const link = await screen.findByRole('link', {name: 'Sign in to Viewer'})
  expect(link).toHaveAttribute('href', '/admin?returnTo=%2Fadmin%2Fconnect%3Fcode%3Dabcd-efgh%26source%3Dforge')
  await userEvent.click(link)
  await userEvent.type(await screen.findByLabelText('Username'), 'synthetic-admin')
  await userEvent.type(screen.getByLabelText('Password', {selector: 'input'}), 'synthetic-password')
  await userEvent.click(screen.getByRole('button', {name: 'Enter workspace'}))
  expect(await screen.findByText('ABCD-EFGH')).toBeVisible()
  expect(screen.getByRole('button', {name: 'Approve this Forge device'})).toBeEnabled()
  expect(requests.mock.calls.filter(([input]) => String(input) === '/api/v1/desktop/pairings/approve')).toHaveLength(1)
})
