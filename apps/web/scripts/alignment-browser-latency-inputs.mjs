import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'

export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex')

export function acceptedCells(receipt) {
  const map = receipt.registration
  if (receipt.outcome !== 'ok' || !['ready', 'approximate'].includes(map?.status)) return null
  const cells = map.status === 'ready' ? map.triangles : map.overviewTriangles
  if (!Array.isArray(cells) || !cells.length || cells.length > 20_000) return null
  const finiteTriangle = points => Array.isArray(points) && points.length === 3
    && points.every(point => Array.isArray(point) && point.length === 2 && point.every(Number.isFinite))
  if (!cells.every(cell => finiteTriangle(cell.moving) && finiteTriangle(cell.reference))) return null
  return cells
}

// Keep both complexity extremes for each recipe, without ranking anatomical quality.
export function selectComplexitySamples(rows, maximumPerRecipe = 2) {
  if (maximumPerRecipe !== 2) throw new Error('The frozen sampling policy requires two complexity extremes')
  const selected = new Set()
  for (const recipe of [...new Set(rows.map(row => row.receipt.recipe))].sort()) {
    const accepted = rows.filter(row => row.receipt.recipe === recipe && acceptedCells(row.receipt))
      .sort((left, right) => acceptedCells(left.receipt).length - acceptedCells(right.receipt).length
        || left.receipt.digest.localeCompare(right.receipt.digest))
    if (accepted.length) {
      selected.add(accepted[0].receipt.digest)
      selected.add(accepted.at(-1).receipt.digest)
    }
  }
  return selected
}

export async function sourceSnapshot(side, maximumBytes = 64 * 1024 ** 2) {
  if (!Array.isArray(side.size) || side.size.length !== 2
    || side.size.some(value => !Number.isSafeInteger(value) || value <= 0)) throw new Error('Invalid source geometry')
  const root = path.resolve(side.path)
  const rootInfo = await fs.lstat(root)
  if (rootInfo.isSymbolicLink() || !rootInfo.isDirectory()) throw new Error('Source root must be a real directory')
  const files = []
  let visitedEntries = 0
  let visitedDirectories = 0
  let total = 0
  async function visit(directory, depth = 0) {
    if (depth > 8 || ++visitedDirectories > 64) throw new Error('Source directory depth/count exceeds bounded thumbnail scope')
    const entries = await fs.opendir(directory)
    for await (const entry of entries) {
      if (++visitedEntries > 512) throw new Error('Source traversal exceeds bounded thumbnail scope')
      if (entry.isSymbolicLink()) throw new Error('Symbolic source inputs are outside this bounded harness')
      const absolute = path.join(directory, entry.name)
      if (entry.isDirectory()) await visit(absolute, depth + 1)
      else if (entry.isFile()) {
        if (files.length >= 256) throw new Error('Source file count exceeds bounded thumbnail scope')
        total += (await fs.stat(absolute)).size
        if (total > maximumBytes) throw new Error('Source bytes exceed bounded thumbnail scope')
        files.push({ absolute, relative: path.relative(root, absolute).split(path.sep).join('/') })
      } else throw new Error('Unsupported source entry outside bounded thumbnail scope')
    }
  }
  await visit(root)
  files.sort((left, right) => left.relative < right.relative ? -1 : left.relative > right.relative ? 1 : 0)
  if (!files.length || files.length > 256) throw new Error('Source file count exceeds bounded thumbnail scope')
  const digest = createHash('sha256')
  let image = null
  for (const file of files) {
    const bytes = await fs.readFile(file.absolute)
    digest.update(file.relative)
    digest.update(bytes)
    if (file.relative === 'thumbnail.jpg' || (!image && /\.(png|jpe?g)$/i.test(file.relative))) {
      image = { bytes, digest: sha256(bytes), type: /\.png$/i.test(file.relative) ? 'image/png' : 'image/jpeg' }
    }
  }
  // Match Python's json.dumps([width, height]) in alignment_benchmark._input_digest.
  digest.update(`[${side.size[0]}, ${side.size[1]}]`)
  if (!image || image.bytes.length > 16 * 1024 ** 2) throw new Error('No bounded browser-readable registered thumbnail')
  return { digest: digest.digest('hex'), image, size: side.size }
}
