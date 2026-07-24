import http from 'k6/http'
import { check, sleep } from 'k6'
import { Rate, Trend } from 'k6/metrics'

import { validateManifest } from './manifest_contract.mjs'

const tileFailures = new Rate('tile_failures')
const tileLatency = new Trend('tile_latency', true)
const COMMON_REQUESTS = 7
const RANDOM_REQUESTS = 3

const profiles = {
  acceptance: { vus: 100, duration: '10m' },
  smoke: { vus: 2, duration: '30s' },
}

const profile = __ENV.PROFILE || 'acceptance'
if (!(profile in profiles)) {
  throw new Error('PROFILE must be smoke or acceptance')
}

export const options = {
  scenarios: {
    viewers: { executor: 'constant-vus', ...profiles[profile] },
  },
  thresholds: {
    http_req_failed: ['rate<0.001'],
    tile_failures: ['rate<0.001'],
    tile_latency: ['p(95)<500'],
  },
}

const base = __ENV.BASE_URL
const manifestPath = __ENV.MANIFEST_PATH
if (!base || !manifestPath) {
  throw new Error('BASE_URL and MANIFEST_PATH are required')
}
let parsedManifest
try {
  parsedManifest = JSON.parse(open(manifestPath))
} catch {
  throw new Error('Invalid viewer load manifest')
}
const slides = validateManifest(parsedManifest)

export default function () {
  const slide = slides[(__VU - 1) % slides.length]
  const metadata = http.get(`${base}/api/v1/public/slides/${slide.publicId}`)
  check(metadata, { 'metadata 200': (response) => response.status === 200 })
  let metadataBody
  try {
    metadataBody = metadata.json()
  } catch {
    tileFailures.add(true)
    sleep(1)
    return
  }
  const tileSource =
    metadataBody && typeof metadataBody === 'object' ? metadataBody.tileSource : null
  if (typeof tileSource !== 'string' || !tileSource.endsWith('/slide.dzi')) {
    tileFailures.add(true)
    sleep(1)
    return
  }
  const tileRoot = tileSource.replace(/slide\.dzi$/, '')
  const tilePaths = []
  for (let index = 0; index < COMMON_REQUESTS; index += 1) {
    tilePaths.push(slide.commonTiles[(__ITER * COMMON_REQUESTS + index) % slide.commonTiles.length])
  }
  for (let index = 0; index < RANDOM_REQUESTS; index += 1) {
    tilePaths.push(slide.randomTiles[Math.floor(Math.random() * slide.randomTiles.length)])
  }
  for (const path of tilePaths) {
    const response = http.get(`${base}${tileRoot}${path}`)
    tileLatency.add(response.timings.duration)
    tileFailures.add(response.status !== 200)
    check(response, { 'tile 200': (result) => result.status === 200 })
  }
  sleep(1)
}
