import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AdminPage } from '../pages/AdminPage'

vi.mock('../upload', () => ({ startTusUpload: vi.fn().mockResolvedValue({}) }))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  sessionStorage.clear()
  localStorage.clear()
})

describe('admin workflow', () => {
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

  it('recovers a forgotten password without storing secrets', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('', { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /forgot password/i }))
    await userEvent.type(screen.getByLabelText(/recovery code/i), 'one-time-secret')
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'new correct horse battery')
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'new correct horse battery')
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }))
    await screen.findByText(/password reset/i)
    expect(JSON.stringify(fetchMock.mock.calls)).toContain('/api/v1/auth/password/recover')
    expect(sessionStorage.getItem('one-time-secret')).toBeNull()
    expect(screen.queryByLabelText(/recovery code/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/^new password$/i)).not.toBeInTheDocument()
  })

  it('validates matching recovery passwords before sending secrets', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('', { status: 401 }))
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /forgot password/i }))
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'new correct horse battery')
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'different correct password')
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/do not match/i)).toBeVisible()
    expect(screen.getByLabelText(/^new password$/i)).toHaveValue('')
    expect(screen.getByLabelText(/confirm new password/i)).toHaveValue('')
    expect(localStorage.length).toBe(0)
  })

  it('uses generic recovery errors and clears rejected secrets', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('', { status: 401 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ detail: { code: 'INVALID_RECOVERY_CODE' } }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      ))
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /forgot password/i }))
    await userEvent.type(screen.getByLabelText(/recovery code/i), 'rejected-secret')
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'new correct horse battery')
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'new correct horse battery')
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }))
    expect(await screen.findByText('Invalid or expired recovery code.')).toBeVisible()
    expect(screen.getByLabelText(/recovery code/i)).toHaveValue('')
    expect(screen.getByLabelText(/^new password$/i)).toHaveValue('')
    expect(screen.getByLabelText(/confirm new password/i)).toHaveValue('')
  })

  it('disables recovery submission while credentials are in flight', async () => {
    let finishRecovery!: (response: Response) => void
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('', { status: 401 }))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finishRecovery = resolve }))
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /forgot password/i }))
    await userEvent.type(screen.getByLabelText(/recovery code/i), 'one-time-secret')
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'new correct horse battery')
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'new correct horse battery')
    const submit = screen.getByRole('button', { name: /reset password/i })
    await userEvent.click(submit)
    expect(submit).toBeDisabled()
    finishRecovery(new Response(null, { status: 204 }))
    await screen.findByText(/password reset/i)
  })

  it('changes the authenticated password and returns to sign in', async () => {
    sessionStorage.setItem('pathlab-csrf', 'csrf-secret')
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('[]', { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    expect(screen.getByLabelText(/current password/i)).toHaveAttribute('autocomplete', 'current-password')
    expect(screen.getByLabelText(/^new password$/i)).toHaveAttribute('autocomplete', 'new-password')
    await userEvent.type(screen.getByLabelText(/current password/i), 'correct horse battery')
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'new correct horse battery')
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'new correct horse battery')
    await userEvent.click(screen.getByRole('button', { name: /change password/i }))
    expect(await screen.findByText(/sign in again/i)).toBeVisible()
    expect(sessionStorage.getItem('pathlab-csrf')).toBeNull()
  })

  it('clears account secrets when the security dialog is cancelled', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]', { status: 200 }))
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    await userEvent.type(screen.getByLabelText(/current password/i), 'cancelled-secret')
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'cancelled-new-secret')
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /account security/i }))
    expect(screen.getByLabelText(/current password/i)).toHaveValue('')
    expect(screen.getByLabelText(/^new password$/i)).toHaveValue('')
  })

  it('clears account secrets when password confirmation fails', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]', { status: 200 }))
    render(<AdminPage />, { wrapper: MemoryRouter })
    await userEvent.click(await screen.findByRole('button', { name: /account security/i }))
    await userEvent.type(screen.getByLabelText(/current password/i), 'current-secret')
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'new correct horse battery')
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'different correct password')
    await userEvent.click(screen.getByRole('button', { name: /change password/i }))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/do not match/i)).toBeVisible()
    expect(screen.getByLabelText(/current password/i)).toHaveValue('')
    expect(screen.getByLabelText(/^new password$/i)).toHaveValue('')
    expect(screen.getByLabelText(/confirm new password/i)).toHaveValue('')
  })
})
