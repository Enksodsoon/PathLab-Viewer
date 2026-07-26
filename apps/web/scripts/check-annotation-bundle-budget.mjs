import { gzipSync } from 'node:zlib'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve } from 'node:path'

const MAX_PUBLIC_INITIAL_GZIP_DELTA = 5 * 1024
const MAX_ANNOTATION_CHUNK_BYTES = 300 * 1024

function option(name) {
  const position = process.argv.indexOf(name)
  return position === -1 ? null : process.argv[position + 1]
}

function initialAssets(distDirectory) {
  const index = readFileSync(resolve(distDirectory, 'index.html'), 'utf8')
  const paths = [...index.matchAll(
    /(?:src|href)="\/(assets\/[^"]+\.(?:js|css))"/g,
  )].map((match) => match[1])
  return {
    index,
    paths,
    gzipBytes: paths.reduce((total, path) => {
      const content = readFileSync(resolve(distDirectory, path))
      return total + gzipSync(content, { level: 9 }).byteLength
    }, 0),
  }
}

function annotationAssets(distDirectory) {
  return readdirSync(resolve(distDirectory, 'assets'))
    .filter((name) => /^AnnotationWorkspace-.*\.(?:js|css)$/.test(name))
    .map((name) => ({
      name,
      rawBytes: statSync(resolve(distDirectory, 'assets', name)).size,
      gzipBytes: gzipSync(
        readFileSync(resolve(distDirectory, 'assets', name)),
        { level: 9 },
      ).byteLength,
    }))
}

const distDirectory = resolve(option('--dist') ?? 'dist')
const baselineOption = option('--baseline')
const currentInitial = initialAssets(distDirectory)
const annotation = annotationAssets(distDirectory)
const annotationJavaScript = annotation.find((asset) => asset.name.endsWith('.js'))

if (!annotationJavaScript) {
  throw new Error('Missing lazy AnnotationWorkspace JavaScript chunk')
}
if (annotationJavaScript.rawBytes > MAX_ANNOTATION_CHUNK_BYTES) {
  throw new Error(
    `Annotation chunk is ${annotationJavaScript.rawBytes} bytes; ` +
    `budget is ${MAX_ANNOTATION_CHUNK_BYTES}`,
  )
}
if (currentInitial.index.includes(annotationJavaScript.name)) {
  throw new Error('AnnotationWorkspace must not be an initial HTML asset')
}

let baselineInitialGzipBytes = null
let publicInitialGzipDeltaBytes = null
if (baselineOption) {
  baselineInitialGzipBytes = initialAssets(resolve(baselineOption)).gzipBytes
  publicInitialGzipDeltaBytes =
    currentInitial.gzipBytes - baselineInitialGzipBytes
  if (publicInitialGzipDeltaBytes > MAX_PUBLIC_INITIAL_GZIP_DELTA) {
    throw new Error(
      `Public initial gzip grew ${publicInitialGzipDeltaBytes} bytes; ` +
      `budget is ${MAX_PUBLIC_INITIAL_GZIP_DELTA}`,
    )
  }
}

const result = {
  currentInitialGzipBytes: currentInitial.gzipBytes,
  baselineInitialGzipBytes,
  publicInitialGzipDeltaBytes,
  publicInitialGzipDeltaBudgetBytes: MAX_PUBLIC_INITIAL_GZIP_DELTA,
  annotationChunkBudgetBytes: MAX_ANNOTATION_CHUNK_BYTES,
  annotationAssets: annotation,
}
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`)
