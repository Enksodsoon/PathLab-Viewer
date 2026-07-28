import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { UploadWorkspace } from '../components/library/UploadWorkspace'

const file = new File(['slide'], 'sample.ome.tiff', { type: 'image/tiff' })

describe('UploadWorkspace', () => {
  afterEach(cleanup)

  it('keeps upload status and progress inside the selected file card', () => {
    render(
      <UploadWorkspace
        file={file}
        displayName="Sample"
        progress={42}
        preparing={false}
        error=""
        onFileChange={vi.fn()}
        onDisplayNameChange={vi.fn()}
        onUpload={vi.fn()}
      />,
    )

    const fileCard = screen.getByText('sample.ome.tiff').closest('.upload-workspace-file')
    expect(fileCard).not.toBeNull()
    expect(within(fileCard as HTMLElement).getByText(/Uploading 42%/)).toBeVisible()
    expect(screen.getByRole('progressbar', { name: 'sample.ome.tiff upload progress' }))
      .toHaveAttribute('aria-valuenow', '42')
    expect(screen.queryByRole('button', { name: /remove sample/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Uploading 42%' })).toBeDisabled()
  })

  it('shows completion in the same file card', () => {
    render(
      <UploadWorkspace
        file={file}
        displayName="Sample"
        progress={100}
        preparing={false}
        error=""
        onFileChange={vi.fn()}
        onDisplayNameChange={vi.fn()}
        onUpload={vi.fn()}
      />,
    )

    expect(screen.getByText(/Upload complete/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Uploaded' })).toBeDisabled()
  })
})
