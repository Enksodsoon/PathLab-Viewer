import http from 'k6/http'
import { check, sleep } from 'k6'
import { Rate, Trend } from 'k6/metrics'

import { validateManifest } from './manifest_contract.mjs'

const tileFailures = new Rate('tile_failures')
const tileLatency = new Trend('tile_latency', true)
const posterLatency = new Trend('poster_latency', true)
const COMMON_REQUESTS = 7
const RANDOM_REQUESTS = 3

const profiles = {
  acceptance: {
    viewers: { executor: 'constant-vus', vus: 100, duration: '10m' },
  },
  capacity300: {
    viewers: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 300 },
        { duration: '10m', target: 300 },
        { duration: '1m', target: 0 },
      ],
    },
  },
  smoke: {
    viewers: { executor: 'constant-vus', vus: 2, duration: '30s' },
  },
  staged: {
    viewers: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        {
          duration: __ENV.TARGET_RAMP_DURATION || '1m',
          target: Number(__ENV.TARGET_VUS || 0),
        },
        {
          duration: __ENV.TARGET_DURATION || '2m',
          target: Number(__ENV.TARGET_VUS || 0),
        },
        { duration: '30s', target: 0 },
      ],
    },
  },
}

const profile = __ENV.PROFILE || 'acceptance'
if (!(profile in profiles)) {
  throw new Error('PROFILE must be smoke, staged, acceptance, or capacity300')
}
if (
  profile === 'staged' &&
  (!Number.isInteger(profiles.staged.viewers.stages[0].target) ||
    profiles.staged.viewers.stages[0].target < 1 ||
    profiles.staged.viewers.stages[0].target > 300)
) {
  throw new Error('TARGET_VUS must be an integer from 1 to 300 for the staged profile')
}

export const options = {
  scenarios: profiles[profile],
  thresholds: {
    http_req_failed: ['rate<0.001'],
    tile_failures: ['rate<0.001'],
    tile_latency: ['p(95)<500'],
    poster_latency: ['p(95)<1500'],
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
let tileRoot = ''
let activeSlide = null

export default function () {
  if (!tileRoot) {
    activeSlide = slides[(__VU - 1) % slides.length]
    const metadata = http.get(`${base}/api/v1/public/slides/${activeSlide.publicId}`)
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
    const thumbnailUrl =
      metadataBody && typeof metadataBody === 'object' ? metadataBody.thumbnailUrl : null
    if (typeof tileSource !== 'string' || !tileSource.endsWith('/slide.dzi')) {
      tileFailures.add(true)
      sleep(1)
      return
    }
    const hasPoster = typeof thumbnailUrl === 'string'
    const openingRequests = [
      ['GET', `${base}${tileSource}`, null, { tags: { resource: 'descriptor' } }],
    ]
    if (hasPoster) {
      openingRequests.unshift([
        'GET',
        `${base}${thumbnailUrl}`,
        null,
        { tags: { resource: 'poster' } },
      ])
    }
    const opening = http.batch(openingRequests)
    const poster = hasPoster ? opening[0] : null
    const descriptor = opening[hasPoster ? 1 : 0]
    const openingFailed = opening.some((response) => response.status !== 200)
    tileFailures.add(openingFailed)
    posterLatency.add(
      metadata.timings.duration + (poster ?? descriptor).timings.duration,
    )
    if (poster) {
      check(poster, { 'poster 200': (response) => response.status === 200 })
    }
    check(descriptor, { 'descriptor 200': (response) => response.status === 200 })
    if (openingFailed) {
      sleep(1)
      return
    }
    tileRoot = tileSource.replace(/slide\.dzi$/, '')
  }

  const slide = activeSlide
  const tilePaths = []
  for (let index = 0; index < COMMON_REQUESTS; index += 1) {
    tilePaths.push(slide.commonTiles[(__ITER * COMMON_REQUESTS + index) % slide.commonTiles.length])
  }
  for (let index = 0; index < RANDOM_REQUESTS; index += 1) {
    tilePaths.push(slide.randomTiles[Math.floor(Math.random() * slide.randomTiles.length)])
  }
  const responses = http.batch(tilePaths.map((path) => ['GET', `${base}${tileRoot}${path}`]))
  for (const response of responses) {
    tileLatency.add(response.timings.duration)
    tileFailures.add(response.status !== 200)
    check(response, { 'tile 200': (result) => result.status === 200 })
  }
  sleep(3)
}
