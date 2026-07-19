import http from 'k6/http'
import { check, sleep } from 'k6'
import { Rate, Trend } from 'k6/metrics'

const tileFailures = new Rate('tile_failures')
const tileLatency = new Trend('tile_latency', true)

export const options = {
  scenarios: {
    viewers: { executor: 'constant-vus', vus: 100, duration: '10m' },
  },
  thresholds: {
    http_req_failed: ['rate<0.001'],
    tile_failures: ['rate<0.001'],
    tile_latency: ['p(95)<500'],
  },
}

const base = __ENV.BASE_URL
const publicId = __ENV.PUBLIC_ID
const tilePaths = (__ENV.TILE_PATHS || 'slide_files/0/0_0.jpeg').split(',')

export default function () {
  const metadata = http.get(`${base}/api/v1/public/slides/${publicId}`)
  check(metadata, { 'metadata 200': (response) => response.status === 200 })
  for (const path of tilePaths) {
    const response = http.get(`${base}/tiles/${publicId}/${path}`)
    tileLatency.add(response.timings.duration)
    tileFailures.add(response.status !== 200)
    check(response, { 'tile 200': (result) => result.status === 200 })
  }
  sleep(1)
}
