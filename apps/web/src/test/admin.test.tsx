import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AdminPage } from '../pages/AdminPage'

const startTusUploadMock = vi.hoisted(() => vi.fn())

vi.mock('../upload', () => ({ startTusUpload: startTusUploadMock }))

const RECOVERY_CODE = 'one-time-secret'
const CURRENT_PASSWORD = 'correct horse battery'
const NEW_PASSWORD = 'new correct horse battery'
const DIFFERENT_PASSWORD = 'different correct password'

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.toString()
  return input.url
}

function requestBody(init: RequestInit | undefined, failureMessage: string): Record<string, unknown> {
  try {
    return JSON.parse(String(init?.body)) as Record<string, unknown>
  } catch {
    throw new Error(failureMessage)
  }
}

function errorResponse(code: string, status = 400): Response {
  return new Response(
    JSON.stringify({ detail: { code } }),
    { status, headers: { 'Content-Type': 'application/json' } },
  )
}

function slideResponse(state: string): Response {
  return new Response(
    JSON.stringify([{
      id: 'slide-polling',
      publicId: 'public-polling',
      displayName: 'Polling slide',
      filename: 'polling.ome.tif',
      sourceBytes: 1024,
      state,
      errorCode: null,
      errorMessage: null,
      metadata: null,
      createdAt: '2026-07-19T10:00:00Z',
    }]),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  )
}

async function flushReactWork() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

function assertCleared(label: RegExp, failureMessage: string) {
  const input = screen.getByLabelText(label)
  if (!(input instanceof HTMLInputElement) || input.value.length !== 0) throw new Error(failureMessage)
}

function recoveryControls() {
  return {
    recoveryCode: screen.getByLabelText(/recovery code/i),
    newPassword: screen.getByLabelText(/^new password$/i),
    confirmation: screen.getByLabelText(/confirm new password/i),
    submit: screen.getByRole('button', { name: /reset password/i }),
    back: screen.getByRole('button', { name: /back to sign in/i }),
  }
}

function changeControls() {
  return {
    currentPassword: screen.getByLabelText(/current password/i),
    newPassword: screen.getByLabelText(/^new password$/i),
    confirmation: screen.getByLabelText(/confirm new password/i),
    submit: screen.getByRole('button', { name: /change password/i }),
    cancel: screen.getByRole('button', { name: /cancel/i }),
  }
}

function assertNoCredentialSecretsInStorage(failureMessage: string) {
  const secrets = [RECOVERY_CODE, CURRENT_PASSWORD, NEW_PASSWORD, DIFFERENT_PASSWORD]
  for (const storage of [localStorage, sessionStorage]) {
    for (let index = 0; index < storage.length; index += 1) {
      const value = storage.getItem(storage.key(index) ?? '') ?? ''
      if (secrets.some((secret) => value.includes(secret))) throw new Error(failureMessage)
    }
  }
}

function assertRecoveryContract(init: RequestInit | undefined) {
  if (init?.method !== 'POST') throw new Error('Recovery method contract mismatch')
  if (init.credentials !== 'same-origin') throw new Error('Recovery credentials contract mismatch')
  const headers = new Headers(init.headers)
  if (headers.get('Content-Type') !== 'application/json') throw new Error('Recovery content type contract mismatch')
  if (headers.has('X-CSRF-Token')) throw new Error('Recovery request included CSRF')
  const body = requestBody(init, 'Recovery body was not JSON')
  if (Object.keys(body).sort().join(',') !== 'newPassword,recoveryCode,username') {
    throw new Error('Recovery body keys contract mismatch')
  }
  if (body.username !== 'admin') throw new Error('Recovery username contract mismatch')
  if (body.recoveryCode !== RECOVERY_CODE) throw new Error('Recovery code contract mismatch')
  if (body.newPassword !== NEW_PASSWORD) throw new Error('Recovery password contract mismatch')
}

function assertChangeContract(init: RequestInit | undefined) {
  if (init?.method !== 'POST') throw new Error('Password change method contract mismatch')
  if (init.credentials !== 'same-origin') throw new Error('Password change credentials contract mismatch')
  const headers = new Headers(init.headers)
  if (headers.get('Content-Type') !== 'application/json') throw new Error('Password change content type contract mismatch')
  if (headers.get('X-CSRF-Token') !== 'csrf-token') throw new Error('Password change CSRF contract mismatch')
  const body = requestBody(init, 'Password change body was not JSON')
  if (Object.keys(body).sort().join(',') !== 'currentPassword,newPassword') {
    throw new Error('Password change body keys contract mismatch')
  }
  if (body.currentPassword !== CURRENT_PASSWORD) throw new Error('Current password contract mismatch')
  if (body.newPassword !== NEW_PASSWORD) throw new Error('New password contract mismatch')
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
  startTusUploadMock.mockReset()
  sessionStorage.clear()
  localStorage.clear()
})

describe('admin workflow', () => {
  it('polls while at least one slide is active', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () => slideResponse('converting'),
    )
    render(<AdminPage />, { wrapper: MemoryRouter })
    await flushReactWork()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(3999)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('stops polling after all slides become stable', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(slideResponse('converting'))
      .mockResolvedValue(slideResponse('ready_private'))
    render(<AdminPage />, { wrapper: MemoryRouter })
    await flushReactWork()

    await vi.advanceTimersByTimeAsync(4000)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await flushReactWork()
    await vi.advanceTimersByTimeAsync(12000)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('stops polling while the document is hidden', async () => {
    vi.useFakeTimers()
    let visibility: DocumentVisibilityState = 'visible'
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility)
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () => slideResponse('queued'),
    )
    render(<AdminPage />, { wrapper: MemoryRouter })
    await flushReactWork()

    visibility = 'hidden'
    document.dispatchEvent(new Event('visibilitychange'))
    await flushReactWork()
    await vi.advanceTimersByTimeAsync(8000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('refreshes exactly once when the document becomes visible', async () => {
    vi.useFakeTimers()
    let visibility: DocumentVisibilityState = 'hidden'
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility)
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () => slideResponse('converting'),
    )
    render(<AdminPage />, { wrapper: MemoryRouter })
    await flushReactWork()

    visibility = 'visible'
    document.dispatchEvent(new Event('visibilitychange'))
    await flushReactWork()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('cleans polling timers and visibility listeners on unmount', async () => {
    vi.useFakeTimers()
    const clearInterval = vi.spyOn(window, 'clearInterval')
    const removeEventListener = vi.spyOn(document, 'removeEventListener')
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(slideResponse('validating'))
    const view = render(<AdminPage />, { wrapper: MemoryRouter })
    await flushReactWork()

    view.unmount()
    expect(clearInterval).toHaveBeenCalled()
    expect(removeEventListener).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
  })

  it('refreshes immediately when upload completion is reported', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('[]', { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        slide: { id: 'slide-1', state: 'uploading' },
        uploadUrl: '/api/v1/uploads/',
        uploadToken: 'signed-token',
      }), { status: 201, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response('[]', { status: 200 }))
    startTusUploadMock.mockImplementationOnce(async (...args: unknown[]) => {
      const handlers = args[3] as { success: () => void }
      handlers.success()
      return {}
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    const chooser = await screen.findByLabelText(/choose ome-tiff/i)
    fireEvent.change(chooser, { target: { files: [new File(['pixels'], 'case.ome.tif')] } })
    await userEvent.click(screen.getByRole('button', { name: /upload slide/i }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
  })

  it('renders real lifecycle states from the API', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            id: 'slide-1',
            publicId: 'public-1',
            displayName: 'HER2 control',
            filename: 'control.ome.tif',
            sourceBytes: 72416508,
            state: 'converting',
            errorCode: null,
            errorMessage: null,
            metadata: null,
            createdAt: '2026-07-19T10:00:00Z',
          },
        ]),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    render(<AdminPage />, { wrapper: MemoryRouter })
    expect(await screen.findByText('HER2 control')).toBeVisible()
    expect(screen.getByText('Converting')).toBeVisible()
    expect(screen.getByRole('button', { name: /choose ome-tiff/i })).toBeVisible()
  })

  it('requires an OME-TIFF and starts a resumable upload', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('[]', { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            slide: { id: 'slide-1', state: 'uploading' },
            uploadUrl: '/api/v1/uploads/',
            uploadToken: 'signed-token',
          }),
          { status: 201, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    render(<AdminPage />, { wrapper: MemoryRouter })
    const input = await screen.findByLabelText(/choose ome-tiff/i)
    await userEvent.upload(input, new File(['II*\0'], 'test.ome.tif', { type: 'image/tiff' }))
    await userEvent.click(screen.getByRole('button', { name: /upload slide/i }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(await screen.findByText(/upload prepared/i)).toBeVisible()
  })

  it('recovers a forgotten password with the complete public request contract', async () => {
    let recoveryRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return new Response('', { status: 401 })
      if (url !== '/api/v1/auth/password/recover') throw new Error('Recovery URL contract mismatch')
      recoveryRequests += 1
      assertRecoveryContract(init)
      return new Response(null, { status: 204 })
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /forgot password/i }))
    const controls = recoveryControls()
    const requirements = screen.getByText('12–128 characters.')
    expect(requirements).toBeVisible()
    if (controls.newPassword.getAttribute('aria-describedby') !== requirements.id) {
      throw new Error('Recovery password requirements were not associated with the field')
    }
    await userEvent.type(controls.recoveryCode, RECOVERY_CODE)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.submit)
    await screen.findByText(/password reset/i)
    if (recoveryRequests !== 1) throw new Error('Recovery request count mismatch')
    if (screen.queryByLabelText(/recovery code/i)) throw new Error('Recovery code remained rendered after success')
    assertNoCredentialSecretsInStorage('Credential secret was persisted after recovery')
  })

  it('validates matching recovery passwords and clears secrets before any request', async () => {
    let recoveryRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return new Response('', { status: 401 })
      recoveryRequests += 1
      return new Response(null, { status: 204 })
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /forgot password/i }))
    const controls = recoveryControls()
    await userEvent.type(controls.recoveryCode, RECOVERY_CODE)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, DIFFERENT_PASSWORD)
    await userEvent.click(controls.submit)
    expect(screen.getByText(/do not match/i)).toBeVisible()
    if (recoveryRequests !== 0) throw new Error('Mismatch submitted a recovery request')
    assertCleared(/recovery code/i, 'Recovery code was retained after mismatch')
    assertCleared(/^new password$/i, 'New password was retained after mismatch')
    assertCleared(/confirm new password/i, 'Password confirmation was retained after mismatch')
    assertNoCredentialSecretsInStorage('Credential secret was persisted after mismatch')
  })

  it('uses generic recovery errors and clears rejected secrets', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return new Response('', { status: 401 })
      if (url !== '/api/v1/auth/password/recover') throw new Error('Recovery error URL mismatch')
      assertRecoveryContract(init)
      return errorResponse('INVALID_RECOVERY_CODE')
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /forgot password/i }))
    const controls = recoveryControls()
    await userEvent.type(controls.recoveryCode, RECOVERY_CODE)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.submit)
    expect(await screen.findByText('Invalid or expired recovery code.')).toBeVisible()
    assertCleared(/recovery code/i, 'Recovery code was retained after rejection')
    assertCleared(/^new password$/i, 'New password was retained after rejection')
    assertCleared(/confirm new password/i, 'Password confirmation was retained after rejection')
  })

  it('maps recovery throttling to neutral retry-later guidance', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return new Response('', { status: 401 })
      return errorResponse('AUTH_THROTTLED', 429)
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /forgot password/i }))
    const controls = recoveryControls()
    await userEvent.type(controls.recoveryCode, RECOVERY_CODE)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.submit)
    expect(await screen.findByText('Too many attempts. Try again later.')).toBeVisible()
    if (screen.queryByText('Invalid or expired recovery code.')) {
      throw new Error('Throttle response was presented as a credential failure')
    }
  })

  it('prevents duplicate recovery submissions while credentials are in flight', async () => {
    let finishRecovery!: (response: Response) => void
    let recoveryRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return Promise.resolve(new Response('', { status: 401 }))
      if (url !== '/api/v1/auth/password/recover') return Promise.reject(new Error('Recovery busy URL mismatch'))
      recoveryRequests += 1
      assertRecoveryContract(init)
      return new Promise<Response>((resolve) => { finishRecovery = resolve })
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /forgot password/i }))
    const controls = recoveryControls()
    await userEvent.type(controls.recoveryCode, RECOVERY_CODE)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.submit)
    if (!(controls.submit instanceof HTMLButtonElement) || !controls.submit.disabled) throw new Error('Recovery submit stayed enabled while busy')
    await userEvent.keyboard('{Enter}')
    if (recoveryRequests !== 1) throw new Error('Recovery was submitted more than once while busy')
    finishRecovery(new Response(null, { status: 204 }))
    await screen.findByText(/password reset/i)
  })

  it('clears recovery secrets when returning to sign in', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (requestUrl(input) === '/api/v1/admin/slides') return new Response('', { status: 401 })
      throw new Error('Recovery back made an unexpected request')
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /forgot password/i }))
    const controls = recoveryControls()
    await userEvent.type(controls.recoveryCode, RECOVERY_CODE)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.back)
    await userEvent.click(screen.getByRole('button', { name: /forgot password/i }))
    assertCleared(/recovery code/i, 'Recovery code was retained after back')
    assertCleared(/^new password$/i, 'New password was retained after back')
    assertCleared(/confirm new password/i, 'Password confirmation was retained after back')
  })

  it('prevents login mode changes and duplicate submissions while login is pending', async () => {
    let finishLogin!: (response: Response) => void
    let loginRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') {
        return Promise.resolve(new Response(loginRequests === 0 ? '' : '[]', { status: loginRequests === 0 ? 401 : 200 }))
      }
      if (url !== '/api/v1/auth/session') return Promise.reject(new Error('Login URL contract mismatch'))
      if (init?.method !== 'POST') return Promise.reject(new Error('Login method contract mismatch'))
      loginRequests += 1
      return new Promise<Response>((resolve) => { finishLogin = resolve })
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    const password = await screen.findByLabelText(/^password$/i)
    const signIn = screen.getByRole('button', { name: /^sign in$/i })
    const forgot = screen.getByRole('button', { name: /forgot password/i })
    await userEvent.type(password, CURRENT_PASSWORD)
    await userEvent.click(signIn)
    if (!(signIn instanceof HTMLButtonElement) || !signIn.disabled) throw new Error('Login submit stayed enabled while busy')
    if (!(forgot instanceof HTMLButtonElement) || !forgot.disabled) throw new Error('Forgot password stayed enabled while login was busy')
    await userEvent.keyboard('{Enter}')
    await userEvent.click(forgot)
    if (loginRequests !== 1) throw new Error('Login was submitted more than once while busy')
    if (screen.queryByText(/recover your account/i)) throw new Error('Login mode changed while busy')
    finishLogin(new Response(JSON.stringify({ csrfToken: 'csrf-token' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    await screen.findByRole('button', { name: /account security/i })
    assertNoCredentialSecretsInStorage('Credential secret was persisted after login')
  })

  it('changes the authenticated password with the complete protected request contract', async () => {
    let changeRequests = 0
    sessionStorage.setItem('pathlab-csrf', 'csrf-token')
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      if (url !== '/api/v1/auth/password') throw new Error('Password change URL contract mismatch')
      changeRequests += 1
      assertChangeContract(init)
      return new Response(null, { status: 204 })
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    const controls = changeControls()
    const requirements = screen.getByText('12–128 characters. Must differ from your current password.')
    expect(requirements).toBeVisible()
    if (controls.newPassword.getAttribute('aria-describedby') !== requirements.id) {
      throw new Error('New password requirements were not associated with the field')
    }
    if (controls.currentPassword.getAttribute('autocomplete') !== 'current-password') {
      throw new Error('Current password autocomplete mismatch')
    }
    if (controls.newPassword.getAttribute('autocomplete') !== 'new-password') {
      throw new Error('New password autocomplete mismatch')
    }
    await userEvent.type(controls.currentPassword, CURRENT_PASSWORD)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.submit)
    expect(await screen.findByText(/sign in again/i)).toBeVisible()
    if (changeRequests !== 1) throw new Error('Password change request count mismatch')
    if (sessionStorage.getItem('pathlab-csrf') !== null) throw new Error('CSRF remained after password change')
  })

  it('explains password requirements before submitting and rejects invalid lengths locally', async () => {
    let changeRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (requestUrl(input) === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      changeRequests += 1
      return new Response(null, { status: 204 })
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    const controls = changeControls()
    await userEvent.type(controls.currentPassword, CURRENT_PASSWORD)
    await userEvent.type(controls.newPassword, 'too short')
    await userEvent.type(controls.confirmation, 'too short')
    await userEvent.click(controls.submit)
    expect(screen.getByRole('alert')).toHaveTextContent('New password must contain 12–128 characters.')
    if (changeRequests !== 0) throw new Error('Invalid password length reached the API')
    assertCleared(/current password/i, 'Current password was retained after length validation')
    assertCleared(/^new password$/i, 'New password was retained after length validation')
    assertCleared(/confirm new password/i, 'Password confirmation was retained after length validation')
  })

  it('requires the current password locally with an accurate message', async () => {
    let changeRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (requestUrl(input) === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      changeRequests += 1
      return new Response(null, { status: 204 })
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    const controls = changeControls()
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.submit)
    expect(screen.getByRole('alert')).toHaveTextContent('Enter your current password.')
    if (changeRequests !== 0) throw new Error('Empty current password reached the API')
    assertCleared(/^new password$/i, 'New password was retained after current-password validation')
    assertCleared(/confirm new password/i, 'Password confirmation was retained after current-password validation')
  })

  it('identifies an incorrect current password after local requirements pass', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      if (url === '/api/v1/auth/password') return errorResponse('CURRENT_PASSWORD_INVALID')
      throw new Error('Incorrect-current-password test made an unexpected request')
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    const controls = changeControls()
    await userEvent.type(controls.currentPassword, 'incorrect current password')
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.submit)
    expect(await screen.findByRole('alert')).toHaveTextContent('Current password is incorrect.')
  })

  it('counts Unicode code points when validating a new password', async () => {
    let changeRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (requestUrl(input) === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      changeRequests += 1
      return new Response(null, { status: 204 })
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    const controls = changeControls()
    const sixEmoji = '🔬🔬🔬🔬🔬🔬'
    await userEvent.type(controls.currentPassword, CURRENT_PASSWORD)
    fireEvent.change(controls.newPassword, { target: { value: sixEmoji } })
    fireEvent.change(controls.confirmation, { target: { value: sixEmoji } })
    await userEvent.click(controls.submit)
    expect(screen.getByRole('alert')).toHaveTextContent('New password must contain 12–128 characters.')
    if (changeRequests !== 0) throw new Error('Six Unicode code points bypassed local length validation')
  })

  it('allows a Unicode password within the backend code-point limit', async () => {
    let submittedPassword = ''
    sessionStorage.setItem('pathlab-csrf', 'csrf-token')
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      if (url !== '/api/v1/auth/password') throw new Error('Unicode password used an unexpected URL')
      submittedPassword = (JSON.parse(String(init?.body)) as { newPassword: string }).newPassword
      return new Response(null, { status: 204 })
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    const controls = changeControls()
    const sixtyFiveEmoji = '🔬'.repeat(65)
    await userEvent.type(controls.currentPassword, CURRENT_PASSWORD)
    fireEvent.change(controls.newPassword, { target: { value: sixtyFiveEmoji } })
    fireEvent.change(controls.confirmation, { target: { value: sixtyFiveEmoji } })
    await userEvent.click(controls.submit)
    expect(await screen.findByText(/sign in again/i)).toBeVisible()
    if (submittedPassword !== sixtyFiveEmoji) throw new Error('Valid Unicode password was not submitted intact')
  })

  it('uses native modal semantics, focuses the password, and restores focus after cancel', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (requestUrl(input) === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      throw new Error('Dialog cancel made an unexpected request')
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    const trigger = await screen.findByRole('button', { name: /account security/i })
    await userEvent.click(trigger)
    const dialog = screen.getByRole('dialog')
    if (!(dialog instanceof HTMLDialogElement) || !dialog.open) throw new Error('Account security was not opened as a native modal')
    const controls = changeControls()
    if (document.activeElement !== controls.currentPassword) throw new Error('Current password did not receive initial dialog focus')
    await userEvent.type(controls.currentPassword, CURRENT_PASSWORD)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.click(controls.cancel)
    if (screen.queryByRole('dialog')) throw new Error('Account security stayed open after cancel')
    if (document.activeElement !== trigger) throw new Error('Account security trigger did not regain focus')
    await userEvent.click(trigger)
    assertCleared(/current password/i, 'Current password was retained after cancel')
    assertCleared(/^new password$/i, 'New password was retained after cancel')
  })

  it('closes the native account security modal on Escape and restores focus', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (requestUrl(input) === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      throw new Error('Dialog Escape made an unexpected request')
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    const trigger = await screen.findByRole('button', { name: /account security/i })
    await userEvent.click(trigger)
    const controls = changeControls()
    await userEvent.type(controls.currentPassword, CURRENT_PASSWORD)
    await userEvent.keyboard('{Escape}')
    if (screen.queryByRole('dialog')) throw new Error('Account security stayed open after Escape')
    if (document.activeElement !== trigger) throw new Error('Account security trigger did not regain focus after Escape')
    await userEvent.click(trigger)
    assertCleared(/current password/i, 'Current password was retained after Escape')
  })

  it('clears account secrets when password confirmation fails', async () => {
    let changeRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (requestUrl(input) === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      changeRequests += 1
      return new Response(null, { status: 204 })
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    const controls = changeControls()
    await userEvent.type(controls.currentPassword, CURRENT_PASSWORD)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, DIFFERENT_PASSWORD)
    await userEvent.click(controls.submit)
    expect(screen.getByText(/do not match/i)).toBeVisible()
    if (changeRequests !== 0) throw new Error('Mismatch submitted a password change request')
    assertCleared(/current password/i, 'Current password was retained after mismatch')
    assertCleared(/^new password$/i, 'New password was retained after mismatch')
    assertCleared(/confirm new password/i, 'Password confirmation was retained after mismatch')
  })

  it('maps rejected authenticated changes safely and clears secrets', async () => {
    sessionStorage.setItem('pathlab-csrf', 'csrf-token')
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      if (url !== '/api/v1/auth/password') throw new Error('Rejected password change URL mismatch')
      assertChangeContract(init)
      return errorResponse('PASSWORD_REUSE')
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    const controls = changeControls()
    await userEvent.type(controls.currentPassword, CURRENT_PASSWORD)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.submit)
    expect(await screen.findByText('Choose a password different from the current password.')).toBeVisible()
    assertCleared(/current password/i, 'Current password was retained after rejection')
    assertCleared(/^new password$/i, 'New password was retained after rejection')
    assertCleared(/confirm new password/i, 'Password confirmation was retained after rejection')
  })

  it('returns immediately to sign-in when password change authentication expires', async () => {
    sessionStorage.setItem('pathlab-csrf', 'csrf-token')
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      if (url === '/api/v1/auth/password') return errorResponse('SESSION_EXPIRED', 401)
      throw new Error('Expired password change made an unexpected request')
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    const controls = changeControls()
    await userEvent.type(controls.currentPassword, CURRENT_PASSWORD)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.submit)
    expect(await screen.findByText('Session expired. Sign in again.')).toBeVisible()
    if (sessionStorage.getItem('pathlab-csrf') !== null) {
      throw new Error('Expired password change retained the CSRF token')
    }
  })

  it('prevents duplicate authenticated password changes while a request is in flight', async () => {
    let finishChange!: (response: Response) => void
    let changeRequests = 0
    sessionStorage.setItem('pathlab-csrf', 'csrf-token')
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return Promise.resolve(new Response('[]', { status: 200 }))
      if (url !== '/api/v1/auth/password') return Promise.reject(new Error('Password change busy URL mismatch'))
      changeRequests += 1
      assertChangeContract(init)
      return new Promise<Response>((resolve) => { finishChange = resolve })
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    const controls = changeControls()
    await userEvent.type(controls.currentPassword, CURRENT_PASSWORD)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.submit)
    if (!(controls.submit instanceof HTMLButtonElement) || !controls.submit.disabled) {
      throw new Error('Password change submit stayed enabled while busy')
    }
    await userEvent.keyboard('{Enter}')
    if (changeRequests !== 1) throw new Error('Password change was submitted more than once while busy')
    finishChange(new Response(null, { status: 204 }))
    await screen.findByText(/sign in again/i)
  })

  it('keeps sign-in visible when an old refresh resolves after password change', async () => {
    let adminRequests = 0
    let finishStaleRefresh!: (response: Response) => void
    sessionStorage.setItem('pathlab-csrf', 'csrf-token')
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') {
        adminRequests += 1
        if (adminRequests === 1) return Promise.resolve(new Response('[]', { status: 200 }))
        return new Promise<Response>((resolve) => { finishStaleRefresh = resolve })
      }
      if (url === '/api/v1/auth/password') {
        assertChangeContract(init)
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.reject(new Error('Password race made an unexpected request'))
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /refresh slides/i }))
    await waitFor(() => { if (adminRequests !== 2) throw new Error('Stale refresh did not start') })
    await userEvent.click(screen.getByRole('button', { name: /account security/i }))
    const controls = changeControls()
    await userEvent.type(controls.currentPassword, CURRENT_PASSWORD)
    await userEvent.type(controls.newPassword, NEW_PASSWORD)
    await userEvent.type(controls.confirmation, NEW_PASSWORD)
    await userEvent.click(controls.submit)
    expect(await screen.findByText(/sign in again/i)).toBeVisible()
    await act(async () => {
      finishStaleRefresh(new Response('[]', { status: 200 }))
      await Promise.resolve()
    })
    expect(screen.getByText(/sign in again/i)).toBeVisible()
    if (screen.queryByRole('button', { name: /account security/i })) throw new Error('Stale refresh restored the admin after password change')
  })

  it('does not expose sign-in until a deferred logout request settles', async () => {
    let finishLogout!: (response: Response) => void
    let logoutSettled = false
    let loginRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return Promise.resolve(new Response('[]', { status: 200 }))
      if (url !== '/api/v1/auth/session') return Promise.reject(new Error('Logout serialization URL mismatch'))
      if (init?.method === 'DELETE') return new Promise<Response>((resolve) => { finishLogout = resolve })
      loginRequests += 1
      if (!logoutSettled) return Promise.reject(new Error('Login started before logout settled'))
      return Promise.resolve(new Response(JSON.stringify({ csrfToken: 'csrf-token' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /sign out/i }))
    expect(await screen.findByText('Signing out…')).toBeVisible()
    if (screen.queryByRole('button', { name: /^sign in$/i })) throw new Error('Sign-in was interactive before logout settled')
    if (screen.queryByRole('button', { name: /forgot password/i })) throw new Error('Recovery was interactive before logout settled')
    if (loginRequests !== 0) throw new Error('Login request started before logout settled')
    await act(async () => {
      logoutSettled = true
      finishLogout(new Response(null, { status: 204 }))
      await Promise.resolve()
    })
    await screen.findByRole('button', { name: /^sign in$/i })
  })

  it('retains the authenticated UI and CSRF token when logout is rejected', async () => {
    let failLogout!: (reason?: unknown) => void
    sessionStorage.setItem('pathlab-csrf', 'csrf-token')
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return Promise.resolve(new Response('[]', { status: 200 }))
      if (url === '/api/v1/auth/session' && init?.method === 'DELETE') {
        return new Promise<Response>((_resolve, reject) => { failLogout = reject })
      }
      return Promise.reject(new Error('Failed logout made an unexpected request'))
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /sign out/i }))
    expect(await screen.findByText('Signing out…')).toBeVisible()
    if (screen.queryByRole('button', { name: /^sign in$/i })) throw new Error('Sign-in was interactive during failed logout')
    await act(async () => {
      failLogout(new Error('network unavailable'))
      await Promise.resolve()
    })
    await screen.findByRole('button', { name: /account security/i })
    expect(screen.getByRole('alert')).toHaveTextContent('Sign-out failed. Try again.')
    if (sessionStorage.getItem('pathlab-csrf') !== 'csrf-token') {
      throw new Error('Failed logout cleared the authenticated CSRF token')
    }
  })

  it('retains the authenticated UI when logout returns a non-204 response', async () => {
    sessionStorage.setItem('pathlab-csrf', 'csrf-token')
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') return new Response('[]', { status: 200 })
      if (url === '/api/v1/auth/session' && init?.method === 'DELETE') {
        return errorResponse('SERVER_ERROR', 500)
      }
      throw new Error('Non-204 logout made an unexpected request')
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /sign out/i }))
    await screen.findByRole('button', { name: /account security/i })
    expect(screen.getByRole('alert')).toHaveTextContent('Sign-out failed. Try again.')
    if (sessionStorage.getItem('pathlab-csrf') !== 'csrf-token') {
      throw new Error('Non-204 logout cleared the authenticated CSRF token')
    }
  })

  it('keeps sign-in visible when an old refresh resolves after sign-out', async () => {
    let adminRequests = 0
    let finishStaleRefresh!: (response: Response) => void
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = requestUrl(input)
      if (url === '/api/v1/admin/slides') {
        adminRequests += 1
        if (adminRequests === 1) return Promise.resolve(new Response('[]', { status: 200 }))
        return new Promise<Response>((resolve) => { finishStaleRefresh = resolve })
      }
      if (url === '/api/v1/auth/session') return Promise.resolve(new Response(null, { status: 204 }))
      return Promise.reject(new Error('Sign-out race made an unexpected request'))
    })
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /refresh slides/i }))
    await waitFor(() => { if (adminRequests !== 2) throw new Error('Sign-out stale refresh did not start') })
    await userEvent.click(screen.getByRole('button', { name: /sign out/i }))
    await screen.findByRole('button', { name: /forgot password/i })
    await act(async () => {
      finishStaleRefresh(new Response('[]', { status: 200 }))
      await Promise.resolve()
    })
    if (!screen.queryByRole('button', { name: /forgot password/i })) throw new Error('Stale refresh hid sign-in after sign-out')
    if (screen.queryByRole('button', { name: /account security/i })) throw new Error('Stale refresh restored the admin after sign-out')
  })
})
