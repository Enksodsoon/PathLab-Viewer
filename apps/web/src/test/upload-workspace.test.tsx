import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  UploadWorkspace,
  type UploadQueueItemView,
} from '../components/library/UploadWorkspace'

const files = [
  new File(['slide-one'], 'one.ome.tiff', { type: 'image/tiff' }),
  new File(['slide-two'], 'two.ome.tiff', { type: 'image/tiff' }),
]

function renderQueue(items: UploadQueueItemView[], running = false) {
  const props = {
    items,
    running,
    onFilesAdded: vi.fn(),
    onDisplayNameChange: vi.fn(),
    onRemove: vi.fn(),
    onRetry: vi.fn(),
    onStart: vi.fn(),
  }
  render(<UploadWorkspace {...props} />)
  return props
}

describe('UploadWorkspace', () => {
  afterEach(cleanup)

  it('accepts multiple OME-TIFF files in one chooser', async () => {
    const props = renderQueue([])
    const input = screen.getByLabelText('Choose OME-TIFF files')

    expect(input).toHaveAttribute('multiple')
    await userEvent.upload(input, files)

    expect(props.onFilesAdded).toHaveBeenCalledWith(files)
  })

  it('shows a sequential queue with only the active file uploading', () => {
    renderQueue([
      {
        id: 'one',
        file: files[0],
        displayName: 'One',
        phase: 'uploading',
        progress: 42,
        error: '',
      },
      {
        id: 'two',
        file: files[1],
        displayName: 'Two',
        phase: 'queued',
        progress: 0,
        error: '',
      },
    ], true)

    const first = screen.getByText('one.ome.tiff').closest('.upload-workspace-file')
    const second = screen.getByText('two.ome.tiff').closest('.upload-workspace-file')
    expect(within(first as HTMLElement).getByText(/Uploading 42%/)).toBeVisible()
    expect(within(first as HTMLElement).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42')
    expect(within(second as HTMLElement).getByText(/Queued · 1 ahead/)).toBeVisible()
    expect(within(second as HTMLElement).queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Uploading…' })).toBeDisabled()
  })

  it('offers a compact retry with a friendly queue error', async () => {
    const props = renderQueue([{
      id: 'one',
      file: files[0],
      displayName: 'One',
      phase: 'error',
      progress: 0,
      error: 'The upload service is unavailable. Start the local tus service, then retry.',
    }])

    expect(screen.getByRole('alert')).toHaveTextContent('upload service is unavailable')
    await userEvent.click(screen.getByRole('button', { name: 'Retry one.ome.tiff' }))
    expect(props.onRetry).toHaveBeenCalledWith('one')
  })
})
