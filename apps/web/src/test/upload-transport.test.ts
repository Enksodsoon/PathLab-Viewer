import { beforeEach, describe, expect, it, vi } from 'vitest'

const tusState = vi.hoisted(() => ({
  options: undefined as {
    onError: (error: Error) => void
    onProgress: (uploaded: number, total: number) => void
    onSuccess: () => void
  } | undefined,
  start: vi.fn(),
}))

vi.mock('tus-js-client', () => ({
  Upload: function Upload(_file: File, options: typeof tusState.options) {
    tusState.options = options
    return {
      findPreviousUploads: vi.fn().mockResolvedValue([]),
      resumeFromPreviousUpload: vi.fn(),
      start: tusState.start,
    }
  },
}))

import { startTusUpload } from '../upload'

describe('tus upload transport', () => {
  beforeEach(() => {
    tusState.options = undefined
    tusState.start.mockReset()
  })

  it('resolves only after the file upload succeeds', async () => {
    const callbacks = {
      progress: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
    }
    let resolved = false
    const upload = startTusUpload(
      new File(['slide'], 'slide.ome.tiff'),
      '/api/v1/uploads/',
      'token',
      callbacks,
    ).then(() => {
      resolved = true
    })

    await vi.waitFor(() => expect(tusState.start).toHaveBeenCalledOnce())
    expect(resolved).toBe(false)
    tusState.options?.onProgress(25, 100)
    expect(callbacks.progress).toHaveBeenCalledWith(25)
    tusState.options?.onSuccess()
    await upload
    expect(resolved).toBe(true)
    expect(callbacks.success).toHaveBeenCalledOnce()
  })

  it('rejects when tus exhausts its retries', async () => {
    const callbacks = {
      progress: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
    }
    const upload = startTusUpload(
      new File(['slide'], 'slide.ome.tiff'),
      '/api/v1/uploads/',
      'token',
      callbacks,
    )

    await vi.waitFor(() => expect(tusState.start).toHaveBeenCalledOnce())
    tusState.options?.onError(new Error('service unavailable'))
    await expect(upload).rejects.toThrow('service unavailable')
    expect(callbacks.error).toHaveBeenCalledWith('service unavailable')
  })
})
