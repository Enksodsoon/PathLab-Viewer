import type { Page } from '@playwright/test'
import { deflateSync } from 'node:zlib'

export interface SyntheticLandmark {
  x: number
  y: number
  color: string
  radius?: number
}

export interface SyntheticDziOptions {
  path: string
  width: number
  height: number
  tileSize?: number
  landmarks: SyntheticLandmark[]
}

const crcTable = Uint32Array.from({ length: 256 }, (_, value) => {
  let crc = value
  for (let bit = 0; bit < 8; bit += 1) crc = crc & 1 ? 0xedb88320 ^ (crc >>> 1) : crc >>> 1
  return crc >>> 0
})

function pngChunk(type: string, data: Buffer) {
  const typeBytes = Buffer.from(type)
  const payload = Buffer.concat([typeBytes, data])
  let crc = 0xffffffff
  for (const byte of payload) crc = crcTable[(crc ^ byte) & 0xff]! ^ (crc >>> 8)
  const length = Buffer.alloc(4)
  length.writeUInt32BE(data.length)
  const checksum = Buffer.alloc(4)
  checksum.writeUInt32BE((crc ^ 0xffffffff) >>> 0)
  return Buffer.concat([length, payload, checksum])
}

function encodeTile(width: number, height: number, left: number, top: number, scale: number, landmarks: SyntheticLandmark[]) {
  const rowLength = width * 4 + 1
  const pixels = Buffer.alloc(height * rowLength)
  for (let y = 0; y < height; y += 1) {
    const row = y * rowLength
    pixels[row] = 0
    for (let x = 0; x < width; x += 1) {
      const offset = row + 1 + x * 4
      pixels[offset] = 239
      pixels[offset + 1] = 228
      pixels[offset + 2] = 212
      pixels[offset + 3] = 255
    }
  }

  for (const landmark of landmarks) {
    const centerX = landmark.x * scale - left
    const centerY = landmark.y * scale - top
    const radius = Math.max(2, (landmark.radius ?? 18) * scale)
    const [red, green, blue] = landmark.color.match(/[\da-f]{2}/gi)?.slice(0, 3).map((value) => Number.parseInt(value, 16)) ?? [240, 30, 30]
    const innerRadius = Math.max(1, radius * 0.18)
    for (let y = Math.max(0, Math.floor(centerY - radius)); y <= Math.min(height - 1, Math.ceil(centerY + radius)); y += 1) {
      for (let x = Math.max(0, Math.floor(centerX - radius)); x <= Math.min(width - 1, Math.ceil(centerX + radius)); x += 1) {
        const distance = (x + 0.5 - centerX) ** 2 + (y + 0.5 - centerY) ** 2
        if (distance > radius ** 2) continue
        const offset = y * rowLength + 1 + x * 4
        const inner = distance <= innerRadius ** 2
        pixels[offset] = inner ? 255 : red
        pixels[offset + 1] = inner ? 255 : green
        pixels[offset + 2] = inner ? 255 : blue
        pixels[offset + 3] = 255
      }
    }
  }

  const header = Buffer.alloc(13)
  header.writeUInt32BE(width, 0)
  header.writeUInt32BE(height, 4)
  header[8] = 8
  header[9] = 6
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk('IHDR', header),
    pngChunk('IDAT', deflateSync(pixels)),
    pngChunk('IEND', Buffer.alloc(0)),
  ])
}

export async function serveSyntheticDzi(page: Page, options: SyntheticDziOptions) {
  const tileSize = options.tileSize ?? 512
  const maxLevel = Math.ceil(Math.log2(Math.max(options.width, options.height)))
  const served: string[] = []
  await page.route(`**${options.path}.dzi*`, (route) => route.fulfill({
    contentType: 'application/xml',
    body: `<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" TileSize="${tileSize}" Overlap="0" Format="png"><Size Width="${options.width}" Height="${options.height}"/></Image>`,
  }))
  await page.route(`**${options.path}_files/**`, async (route) => {
    const pathname = new URL(route.request().url()).pathname
    const suffix = `${options.path}_files/`
    if (!pathname.includes(suffix)) return route.continue()
    const match = pathname.slice(pathname.indexOf(suffix) + suffix.length).match(/^(\d+)\/(\d+)_(\d+)\.png$/)
    if (!match) return route.fulfill({ status: 404 })
    const [, levelText, columnText, rowText] = match
    const level = Number(levelText)
    const column = Number(columnText)
    const row = Number(rowText)
    const scale = 2 ** (level - maxLevel)
    const levelWidth = Math.ceil(options.width * scale)
    const levelHeight = Math.ceil(options.height * scale)
    const left = column * tileSize
    const top = row * tileSize
    const width = Math.min(tileSize, levelWidth - left)
    const height = Math.min(tileSize, levelHeight - top)
    if (level < 0 || level > maxLevel || width <= 0 || height <= 0) return route.fulfill({ status: 404 })

    const png = encodeTile(width, height, left, top, scale, options.landmarks)
    served.push(pathname)
    return route.fulfill({ contentType: 'image/png', body: png })
  })
  return served
}

export async function visibleSyntheticLandmark(page: Page, color: 'red' | 'blue' = 'red') {
  return page.locator('.openseadragon-canvas canvas').evaluateAll((canvases, color) => {
    for (const canvas of canvases) {
      const context = canvas.getContext('2d')
      if (!context || !canvas.width || !canvas.height) continue
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height)
      let totalX = 0
      let totalY = 0
      let count = 0
      for (let y = 0; y < pixels.height; y += 1) {
        for (let x = 0; x < pixels.width; x += 1) {
          const offset = (y * pixels.width + x) * 4
          const red = pixels.data[offset]
          const green = pixels.data[offset + 1]
          const blue = pixels.data[offset + 2]
          if (color === 'red' ? red > 220 && green < 90 && blue < 90 : blue > 220 && red < 90 && green < 150) {
            totalX += x
            totalY += y
            count += 1
          }
        }
      }
      if (!count) continue
      const bounds = canvas.getBoundingClientRect()
      return {
        x: bounds.left + totalX / count / canvas.width * bounds.width,
        y: bounds.top + totalY / count / canvas.height * bounds.height,
        pixels: count,
      }
    }
    return null
  }, color)
}
