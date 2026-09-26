import { beforeEach, describe, expect, it, vi } from 'vitest'

const tusState = vi.hoisted(() => ({
  options: undefined as {
    fingerprint: (file: File) => Promise<string>
    onError: (error: Error) => void
    onProgress: (uploaded: number, total: number) => void
    onSuccess: () => void
  } | undefined,
  start: vi.fn(),
  abort: vi.fn().mockResolvedValue(undefined),
  previous: vi.fn().mockResolvedValue([]),
}))

vi.mock('tus-js-client', () => ({
  Upload: function Upload(_file: File, options: typeof tusState.options) {
    tusState.options = options
    return {
      findPreviousUploads: tusState.previous,
      abort: tusState.abort,
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
    tusState.abort.mockClear()
    tusState.previous.mockReset().mockResolvedValue([])
  })

  it('does not start after cancellation during asynchronous resume lookup', async () => {
    let completeLookup: (value: never[]) => void = () => {}
    tusState.previous.mockImplementation(() => new Promise((resolve) => { completeLookup = resolve }))
    const controller = new AbortController()
    const upload = startTusUpload(new File(['slide'], 'slide.ome.tiff'), '/uploads/', 'secret', {progress:vi.fn(),success:vi.fn(),error:vi.fn()}, 'reserved-slide', controller.signal)
    const rejected = expect(upload).rejects.toMatchObject({name:'AbortError'})
    controller.abort(); completeLookup([]); await rejected; await Promise.resolve()
    expect(tusState.start).not.toHaveBeenCalled()
    expect(tusState.abort).toHaveBeenCalledWith(false)
  })
  it('reports measured bytes independently from rounded percentage', async () => {
    const bytes=vi.fn()
    const upload=startTusUpload(new File(['slide'],'slide.ome.tiff'),'/uploads/','token',{bytes,progress:vi.fn(),success:vi.fn(),error:vi.fn()})
    await vi.waitFor(()=>expect(tusState.start).toHaveBeenCalledOnce())
    tusState.options?.onProgress(250,1000); expect(bytes).toHaveBeenCalledWith(250,1000)
    tusState.options?.onSuccess(); await upload
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

  it('reports finite bounded progress even when the total is zero', async () => {
    const callbacks = { progress: vi.fn(), success: vi.fn(), error: vi.fn() }
    const upload = startTusUpload(new File(['slide'], 'slide.ome.tiff'), '/uploads/', 'token', callbacks)
    await vi.waitFor(() => expect(tusState.start).toHaveBeenCalledOnce())
    tusState.options?.onProgress(0, 0)
    expect(callbacks.progress).toHaveBeenLastCalledWith(0)
    tusState.options?.onProgress(150, 100)
    expect(callbacks.progress).toHaveBeenLastCalledWith(100)
    tusState.options?.onSuccess()
    await upload
  })

  it('scopes resumable uploads to a reservation without storing its bearer token', async () => {
    const file = new File(['slide'], 'slide.ome.tiff')
    const callbacks = { progress: vi.fn(), success: vi.fn(), error: vi.fn() }
    const first = startTusUpload(file, '/uploads/', 'secret-token', callbacks, 'slide-one')
    await vi.waitFor(() => expect(tusState.start).toHaveBeenCalledTimes(1))
    const firstKey = await tusState.options!.fingerprint(file)
    tusState.options?.onSuccess()
    await first
    const second = startTusUpload(file, '/uploads/', 'another-token', callbacks, 'slide-two')
    await vi.waitFor(() => expect(tusState.start).toHaveBeenCalledTimes(2))
    const secondKey = await tusState.options!.fingerprint(file)
    expect(firstKey).not.toBe(secondKey)
    expect(firstKey).not.toContain('secret-token')
    tusState.options?.onSuccess()
    await second
  })
})
