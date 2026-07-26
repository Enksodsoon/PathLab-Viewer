import { existsSync, readFileSync, statSync } from 'node:fs'
import { resolve } from 'node:path'
import { gzipSync } from 'node:zlib'

const MAX_PUBLIC_INITIAL_GZIP_DELTA = 5 * 1024
const MAX_ANNOTATION_LAZY_BYTES = 300 * 1024
const ANNOTATION_SOURCE = 'src/annotations/AnnotationWorkspace.tsx'
const VIEWER_SOURCE = 'src/pages/ViewerPage.tsx'

function option(name) {
  const position = process.argv.indexOf(name)
  const value = position === -1 ? null : process.argv[position + 1]
  return value && !value.startsWith('--') ? value : null
}

function requiredDirectory(name) {
  const value = option(name)
  if (!value) throw new Error(`${name} is required`)
  const directory = resolve(value)
  if (!existsSync(directory)) {
    throw new Error(`${name} directory does not exist: ${directory}`)
  }
  return directory
}

function assetSize(distDirectory, path) {
  const absolute = resolve(distDirectory, path)
  if (!existsSync(absolute)) {
    throw new Error(`Bundle references missing asset: ${path}`)
  }
  const content = readFileSync(absolute)
  return {
    name: path,
    rawBytes: statSync(absolute).size,
    gzipBytes: gzipSync(content, { level: 9 }).byteLength,
  }
}

function initialAssets(distDirectory) {
  const index = readFileSync(resolve(distDirectory, 'index.html'), 'utf8')
  const paths = [...new Set(
    [...index.matchAll(
      /<(?:script|link)\b[^>]*(?:src|href)=["']\/([^"'?#]+\.(?:js|css))(?:[?#][^"']*)?["'][^>]*>/gi,
    )].map((match) => match[1]),
  )]
  if (paths.length === 0) {
    throw new Error('index.html has no initial JavaScript or CSS assets')
  }
  const assets = paths.map((path) => assetSize(distDirectory, path))
  return {
    index,
    paths,
    assets,
    gzipBytes: assets.reduce((total, asset) => total + asset.gzipBytes, 0),
  }
}

function manifest(distDirectory) {
  const path = resolve(distDirectory, '.vite/manifest.json')
  if (!existsSync(path)) {
    throw new Error(`Missing Vite manifest: ${path}`)
  }
  return JSON.parse(readFileSync(path, 'utf8'))
}

function manifestKeyBySource(entries, source) {
  const match = Object.entries(entries).find(([, entry]) => entry.src === source)
  if (!match) throw new Error(`Vite manifest is missing ${source}`)
  return match[0]
}

function manifestClosure(
  entries,
  key,
  visited = new Set(),
  assets = new Set(),
  includeDynamic = false,
  dynamicBoundary = new Set(),
) {
  if (visited.has(key)) return assets
  visited.add(key)
  const entry = entries[key]
  if (!entry) throw new Error(`Vite manifest references missing entry: ${key}`)
  if (entry.file) assets.add(entry.file)
  for (const path of entry.css ?? []) assets.add(path)
  for (const path of entry.assets ?? []) assets.add(path)
  for (const imported of entry.imports ?? []) {
    manifestClosure(
      entries,
      imported,
      visited,
      assets,
      includeDynamic,
      dynamicBoundary,
    )
  }
  if (includeDynamic && !dynamicBoundary.has(key)) {
    for (const imported of entry.dynamicImports ?? []) {
      manifestClosure(
        entries,
        imported,
        visited,
        assets,
        true,
        dynamicBoundary,
      )
    }
  }
  return assets
}

function addEmittedReferences(distDirectory, assets, excludedAssets) {
  const queue = [...assets]
  for (let position = 0; position < queue.length; position += 1) {
    const path = queue[position]
    if (!/\.(?:js|css)$/.test(path)) continue
    const content = readFileSync(resolve(distDirectory, path), 'utf8')
    for (const match of content.matchAll(/assets\/[A-Za-z0-9._-]+\.[A-Za-z0-9]+/g)) {
      const referenced = match[0]
      if (
        !assets.has(referenced) &&
        !excludedAssets.has(referenced) &&
        existsSync(resolve(distDirectory, referenced))
      ) {
        assets.add(referenced)
        queue.push(referenced)
      }
    }
  }
}

const distDirectory = resolve(option('--dist') ?? 'dist')
const baselineDirectory = requiredDirectory('--baseline')
const currentInitial = initialAssets(distDirectory)
const baselineInitial = initialAssets(baselineDirectory)
const entries = manifest(distDirectory)
const annotationKey = manifestKeyBySource(entries, ANNOTATION_SOURCE)
const viewerKey = manifestKeyBySource(entries, VIEWER_SOURCE)
const loadedKeys = new Set()
const loaded = manifestClosure(entries, 'index.html', loadedKeys)
manifestClosure(entries, viewerKey, loadedKeys, loaded)
const completeAnnotation = manifestClosure(
  entries,
  annotationKey,
  new Set(),
  new Set(),
  true,
  loadedKeys,
)

const annotationPaths = new Set(
  [...completeAnnotation].filter((path) => !loaded.has(path)),
)
addEmittedReferences(distDirectory, annotationPaths, loaded)

for (const initialPath of currentInitial.paths) {
  if (annotationPaths.has(initialPath)) {
    throw new Error(`Annotation asset must remain lazy: ${initialPath}`)
  }
}

const annotationAssets = [...annotationPaths]
  .sort()
  .map((path) => assetSize(distDirectory, path))
const annotationLazyRawBytes = annotationAssets.reduce(
  (total, asset) => total + asset.rawBytes,
  0,
)
const annotationLazyGzipBytes = annotationAssets.reduce(
  (total, asset) => total + asset.gzipBytes,
  0,
)
if (annotationLazyRawBytes > MAX_ANNOTATION_LAZY_BYTES) {
  throw new Error(
    `Total annotation lazy payload is ${annotationLazyRawBytes} bytes; ` +
    `budget is ${MAX_ANNOTATION_LAZY_BYTES}`,
  )
}

const publicInitialGzipDeltaBytes =
  currentInitial.gzipBytes - baselineInitial.gzipBytes
if (publicInitialGzipDeltaBytes > MAX_PUBLIC_INITIAL_GZIP_DELTA) {
  throw new Error(
    `Public initial gzip grew ${publicInitialGzipDeltaBytes} bytes; ` +
    `budget is ${MAX_PUBLIC_INITIAL_GZIP_DELTA}`,
  )
}

const result = {
  currentInitialGzipBytes: currentInitial.gzipBytes,
  baselineInitialGzipBytes: baselineInitial.gzipBytes,
  publicInitialGzipDeltaBytes,
  publicInitialGzipDeltaBudgetBytes: MAX_PUBLIC_INITIAL_GZIP_DELTA,
  annotationLazyRawBytes,
  annotationLazyGzipBytes,
  annotationLazyBudgetBytes: MAX_ANNOTATION_LAZY_BYTES,
  currentInitialAssets: currentInitial.assets,
  baselineInitialAssets: baselineInitial.assets,
  annotationAssets,
}
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`)
