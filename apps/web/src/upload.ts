import * as tus from 'tus-js-client'

export interface UploadCallbacks {
  progress: (percent: number) => void
  success: () => void
  error: (message: string) => void
}

export async function startTusUpload(
  file: File,
  endpoint: string,
  token: string,
  callbacks: UploadCallbacks,
): Promise<tus.Upload> {
  const upload = new tus.Upload(file, {
    endpoint,
    chunkSize: 20 * 1024 * 1024,
    retryDelays: [0, 1000, 3000, 5000, 10000],
    removeFingerprintOnSuccess: true,
    metadata: { filename: file.name, filetype: file.type, uploadToken: token },
    headers: { Authorization: `Bearer ${token}` },
    onError: (error) => callbacks.error(error.message),
    onProgress: (uploaded, total) => callbacks.progress(Math.round((uploaded / total) * 100)),
    onSuccess: callbacks.success,
  })
  const previous = await upload.findPreviousUploads()
  if (previous.length) upload.resumeFromPreviousUpload(previous[0])
  upload.start()
  return upload
}
