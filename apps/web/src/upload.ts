import * as tus from 'tus-js-client'

export interface UploadCallbacks {
  progress: (percent: number) => void
  success: () => void
  error: (message: string) => void
}

export function startTusUpload(
  file: File,
  endpoint: string,
  token: string,
  callbacks: UploadCallbacks,
): Promise<tus.Upload> {
  return new Promise((resolve, reject) => {
    let settled = false
    const upload = new tus.Upload(file, {
      endpoint,
      chunkSize: 20 * 1024 * 1024,
      retryDelays: [0, 1000, 3000, 5000, 10000],
      removeFingerprintOnSuccess: true,
      metadata: { filename: file.name, filetype: file.type, uploadToken: token },
      headers: { Authorization: `Bearer ${token}` },
      onError: (error) => {
        callbacks.error(error.message)
        if (!settled) {
          settled = true
          reject(error)
        }
      },
      onProgress: (uploaded, total) => callbacks.progress(Math.round((uploaded / total) * 100)),
      onSuccess: () => {
        callbacks.success()
        if (!settled) {
          settled = true
          resolve(upload)
        }
      },
    })
    void upload.findPreviousUploads()
      .then((previous) => {
        if (previous.length) upload.resumeFromPreviousUpload(previous[0])
        upload.start()
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : 'Upload could not start.'
        callbacks.error(message)
        if (!settled) {
          settled = true
          reject(error)
        }
      })
  })
}
