export interface TissueCapture {
  blob: Blob
  width: number
  height: number
  mimeType: 'image/webp' | 'image/jpeg'
  elapsedMs: number
}

const MAX_WIDTH = 1600
const MAX_HEIGHT = 1200
const MAX_BYTES = 2 * 1024 * 1024

export function boundedCaptureDimensions(
  sourceWidth: number,
  sourceHeight: number,
): { width: number; height: number } {
  if (!Number.isFinite(sourceWidth) || !Number.isFinite(sourceHeight)
    || sourceWidth <= 0 || sourceHeight <= 0) {
    throw new Error('Screenshot canvas is empty')
  }
  const scale = Math.min(1, MAX_WIDTH / sourceWidth, MAX_HEIGHT / sourceHeight)
  return {
    width: Math.max(1, Math.round(sourceWidth * scale)),
    height: Math.max(1, Math.round(sourceHeight * scale)),
  }
}

function encode(
  canvas: HTMLCanvasElement,
  mimeType: 'image/webp' | 'image/jpeg',
  quality: number,
): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, mimeType, quality))
}

export async function captureVisibleTissue(source: HTMLCanvasElement): Promise<TissueCapture> {
  const started = performance.now()
  const bounded = boundedCaptureDimensions(source.width, source.height)
  let lastBlob: Blob | null = null

  for (let attempt = 0; attempt < 4; attempt += 1) {
    const scale = 0.85 ** attempt
    const width = Math.max(1, Math.round(bounded.width * scale))
    const height = Math.max(1, Math.round(bounded.height * scale))
    const target = document.createElement('canvas')
    target.width = width
    target.height = height
    const context = target.getContext('2d', { alpha: false })
    if (!context) throw new Error('Screenshot canvas is unavailable')
    try {
      context.drawImage(source, 0, 0, width, height)
    } catch {
      throw new Error('Screenshot is unavailable for this slide')
    }

    const webp = await encode(target, 'image/webp', Math.max(0.5, 0.78 - attempt * 0.1))
    const encoded = webp?.type === 'image/webp'
      ? webp
      : await encode(target, 'image/jpeg', Math.max(0.52, 0.82 - attempt * 0.1))
    if (!encoded) throw new Error('Browser could not encode the screenshot')
    lastBlob = encoded
    if (encoded.size <= MAX_BYTES) {
      return {
        blob: encoded,
        width,
        height,
        mimeType: encoded.type === 'image/webp' ? 'image/webp' : 'image/jpeg',
        elapsedMs: performance.now() - started,
      }
    }
  }

  throw new Error(`Screenshot exceeds the ${MAX_BYTES / 1024 / 1024} MiB limit (${lastBlob?.size ?? 0} bytes)`)
}
