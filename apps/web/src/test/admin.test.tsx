import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AdminPage } from '../pages/AdminPage'

vi.mock('../upload', () => ({ startTusUpload: vi.fn().mockResolvedValue({}) }))

afterEach(() => { cleanup(); vi.restoreAllMocks() })

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
})
