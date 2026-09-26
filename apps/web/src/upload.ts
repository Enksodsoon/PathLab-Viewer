import * as tus from 'tus-js-client'

export interface UploadCallbacks {
  progress: (percent: number) => void
  bytes?: (uploaded: number, total: number) => void
  success: () => void
  error: (message: string) => void
}

export function startTusUpload(
  file: File,
  endpoint: string,
  token: string,
  callbacks: UploadCallbacks,
  reservationId: string = crypto.randomUUID(),
  signal?: AbortSignal,
): Promise<tus.Upload> {
  return new Promise((resolve, reject) => {
    let settled = false
    const finish = (error?: unknown) => {
      if (settled) return
      settled = true
      signal?.removeEventListener('abort', cancel)
      if (error) reject(error)
      else resolve(upload)
    }
    const cancel = () => {
      if (settled) return
      void upload?.abort(false).catch(() => undefined)
      finish(new DOMException('Upload paused by administrator.', 'AbortError'))
    }
    if (signal?.aborted) { reject(new DOMException('Upload paused by administrator.', 'AbortError')); return }
    const upload = new tus.Upload(file, {
      endpoint,
      chunkSize: 20 * 1024 * 1024,
      retryDelays: [0, 1000, 3000, 5000, 10000],
      removeFingerprintOnSuccess: true,
      fingerprint: async () => `pathlab-upload:v1:${endpoint}:${reservationId}`,
      metadata: { filename: file.name, filetype: file.type, uploadToken: token },
      headers: { Authorization: `Bearer ${token}` },
      onError: (error) => {
        if (!settled) callbacks.error(error.message)
        finish(error)
      },
      onProgress: (uploaded, total) => {
        if (settled) return
        callbacks.bytes?.(uploaded, total)
        callbacks.progress(total > 0 ? Math.min(100, Math.max(0, Math.round((uploaded / total) * 100))) : 0)
      },
      onSuccess: () => {
        if (!settled) callbacks.success()
        finish()
      },
    })
    signal?.addEventListener('abort', cancel, { once: true })
    void upload.findPreviousUploads()
      .then((previous) => {
        if (settled || signal?.aborted) return
        if (previous.length) upload.resumeFromPreviousUpload(previous[0])
        upload.start()
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : 'Upload could not start.'
        if (!settled) callbacks.error(message)
        finish(error)
      })
  })
}
