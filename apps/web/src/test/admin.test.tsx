import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AccountSecurityDialog, AuthPanel } from '../components/AuthPanels'
import { ThemeProvider } from '../ThemeProvider'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function urlOf(input: RequestInfo | URL) {
  if (typeof input === 'string') return input
  return input instanceof URL ? input.toString() : input.url
}

function renderAuth(onSuccess = vi.fn()) {
  return render(<ThemeProvider><AuthPanel onSuccess={onSuccess} /></ThemeProvider>)
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
  sessionStorage.clear()
})

describe('administrator authentication', () => {
  it('presents the redesigned PathLab landing experience', () => {
    const view = renderAuth()

    expect(screen.getByRole('heading', { name: /see the whole picture/i })).toBeVisible()
    expect(screen.getByRole('heading', { name: /administrator sign in/i })).toBeVisible()
    expect(screen.getByText(/focused workspace for reviewing, organizing, and sharing/i)).toBeVisible()
    expect(view.container.querySelector('.brand-mark-layers')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /enter workspace/i })).toBeVisible()
    expect(screen.getByRole('button', { name: /recover administrator access/i })).toBeVisible()
    expect(screen.getByRole('group', { name: /color theme/i })).toBeVisible()
    expect(screen.getByRole('radio', { name: /system/i })).toBeChecked()
    expect(view.container.querySelectorAll('.auth-path')).toHaveLength(48)
    expect(view.container.querySelectorAll('.auth-path-active')).toHaveLength(12)
  })

  it('switches and persists the login theme without touching the form', async () => {
    renderAuth()
    const username = screen.getByLabelText(/^username$/i)

    await userEvent.clear(username)
    await userEvent.type(username, 'pathlab-admin')
    await userEvent.click(screen.getByRole('radio', { name: /dark/i }))

    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(localStorage.getItem('pathlab-theme')).toBe('dark')
    expect(username).toHaveValue('pathlab-admin')
  })

  it('uses a generic sign-in error and clears the password', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(
      { detail: { code: 'INVALID_CREDENTIALS' } },
      401,
    ))
    renderAuth()
    await userEvent.type(screen.getByLabelText(/^password$/i), 'never-store-this')
    await userEvent.click(screen.getByRole('button', { name: /^enter workspace$/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Sign-in failed')
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('')
  })

  it('reveals and conceals the password without changing its value', async () => {
    renderAuth()
    const password = screen.getByLabelText(/^password$/i)
    await userEvent.type(password, 'local-only-value')

    await userEvent.click(screen.getByRole('button', { name: /show password/i }))
    expect(password).toHaveAttribute('type', 'text')
    expect(password).toHaveValue('local-only-value')

    await userEvent.click(screen.getByRole('button', { name: /hide password/i }))
    expect(password).toHaveAttribute('type', 'password')
  })

  it('validates recovery confirmation locally and clears secrets', async () => {
    const request = vi.spyOn(globalThis, 'fetch')
    renderAuth()
    await userEvent.click(screen.getByRole('button', { name: /recover administrator access/i }))
    await userEvent.type(screen.getByLabelText(/recovery code/i), 'one-time-secret')
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'correct horse battery')
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'different password')
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }))
    expect(screen.getByRole('alert')).toHaveTextContent('do not match')
    expect(screen.getByLabelText(/recovery code/i)).toHaveValue('')
    expect(request).not.toHaveBeenCalled()
  })

  it('sends only the public recovery contract and returns to sign in', async () => {
    const request = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    renderAuth()
    await userEvent.click(screen.getByRole('button', { name: /recover administrator access/i }))
    await userEvent.type(screen.getByLabelText(/recovery code/i), 'one-time-secret')
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'correct horse battery')
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'correct horse battery')
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }))
    await screen.findByRole('button', { name: /^enter workspace$/i })
    const [input, init] = request.mock.calls[0] ?? []
    expect(urlOf(input as RequestInfo)).toBe('/api/v1/auth/password/recover')
    expect(init?.credentials).toBe('same-origin')
    expect(new Headers(init?.headers).has('X-CSRF-Token')).toBe(false)
    expect(JSON.parse(String(init?.body))).toEqual({
      username: 'admin',
      recoveryCode: 'one-time-secret',
      newPassword: 'correct horse battery',
    })
  })
})

describe('account security dialog', () => {
  it('uses native modal semantics and restores focus after cancel', async () => {
    const opener = document.createElement('button')
    opener.textContent = 'Account'
    document.body.append(opener)
    opener.focus()
    const onClose = vi.fn()
    const { rerender } = render(
      <AccountSecurityDialog
        open
        onClose={onClose}
        onChanged={vi.fn()}
        onAuthenticationRequired={vi.fn()}
      />,
    )
    const dialog = screen.getByRole('dialog', { name: /change password/i })
    expect(dialog.tagName).toBe('DIALOG')
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    rerender(
      <AccountSecurityDialog
        open={false}
        onClose={onClose}
        onChanged={vi.fn()}
        onAuthenticationRequired={vi.fn()}
      />,
    )
    await waitFor(() => expect(opener).toHaveFocus())
    opener.remove()
  })

  it('rejects invalid new passwords locally and clears all secrets', async () => {
    const request = vi.spyOn(globalThis, 'fetch')
    render(
      <AccountSecurityDialog
        open
        onClose={vi.fn()}
        onChanged={vi.fn()}
        onAuthenticationRequired={vi.fn()}
      />,
    )
    await userEvent.type(screen.getByLabelText(/current password/i), 'current password')
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'short')
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'short')
    await userEvent.click(screen.getByRole('button', { name: /change password/i }))
    expect(screen.getByRole('alert')).toHaveTextContent('12–128')
    expect(screen.getByLabelText(/current password/i)).toHaveValue('')
    expect(screen.getByLabelText(/^new password$/i)).toHaveValue('')
    expect(request).not.toHaveBeenCalled()
  })

  it('sends the protected change contract and handles expired authentication', async () => {
    sessionStorage.setItem('pathlab-csrf', 'csrf-token')
    const request = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(
      { detail: { code: 'AUTHENTICATION_REQUIRED' } },
      401,
    ))
    const expired = vi.fn()
    render(
      <AccountSecurityDialog
        open
        onClose={vi.fn()}
        onChanged={vi.fn()}
        onAuthenticationRequired={expired}
      />,
    )
    await userEvent.type(screen.getByLabelText(/current password/i), 'current password')
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'correct horse battery')
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'correct horse battery')
    await userEvent.click(screen.getByRole('button', { name: /change password/i }))
    await waitFor(() => expect(expired).toHaveBeenCalledOnce())
    const [input, init] = request.mock.calls[0] ?? []
    expect(urlOf(input as RequestInfo)).toBe('/api/v1/auth/password')
    expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe('csrf-token')
    expect(JSON.parse(String(init?.body))).toEqual({
      currentPassword: 'current password',
      newPassword: 'correct horse battery',
    })
  })
})
