import http from 'k6/http'
import { check, fail, sleep } from 'k6'
import { Counter } from 'k6/metrics'

const BASE_URL = __ENV.BASE_URL
const PUBLIC_ID = __ENV.PUBLIC_ID
const ACCESS_CODE = __ENV.ACCESS_CODE
const SHARD = Number(__ENV.SHARD)
const START_EPOCH = Number(__ENV.START_EPOCH)
const TILE_URL = __ENV.TILE_URL
const AUTOSAVES_PER_STUDENT = 20
const HOLD_SECONDS = 60 * 60
const autosaveCount = new Counter('assessment_autosaves')
const reconnectCount = new Counter('assessment_reconnects')
const submitCount = new Counter('assessment_submits')
if (!BASE_URL || !PUBLIC_ID || !ACCESS_CODE || !TILE_URL) fail('campaign inputs are required')
if (!Number.isInteger(SHARD) || SHARD < 1 || SHARD > 5) fail('SHARD must be 1..5')
if (!Number.isFinite(START_EPOCH)) fail('START_EPOCH is required')

export const options = {
  scenarios: {
    seats: { executor: 'per-vu-iterations', vus: 100, iterations: 1, maxDuration: '75m' },
  },
  thresholds: {
    http_req_failed: ['rate<0.001'],
    'http_req_duration{name:autosave}': ['p(95)<=500'],
    'http_req_duration{name:submit}': ['p(95)<=1000'],
    'http_req_duration{name:tile}': ['p(95)<500'],
    checks: ['rate>0.999'],
  },
}

function waitForBarrier() {
  const wait = START_EPOCH - Date.now() / 1000
  if (wait < -30) fail(`campaign barrier missed by ${Math.abs(wait)} seconds`)
  if (wait > 0) sleep(wait)
}

function access(identifier, takeover = false) {
  const response = http.post(
    `${BASE_URL}/api/v2/assessment/access`,
    JSON.stringify({
      kind: 'roster', publicId: PUBLIC_ID, studentIdentifier: identifier,
      accessCode: ACCESS_CODE, takeover,
    }),
    {
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': `access-${SHARD}-${__VU}-${takeover ? 'takeover' : 'initial'}`,
      },
      tags: { name: 'access' },
    },
  )
  check(response, { 'access accepted': (item) => item.status === 201 })
  if (response.status !== 201) fail(`access failed: ${response.status}`)
  return response.json()
}

export default function () {
  waitForBarrier()
  const campaignStarted = Date.now()
  const identifier = `shard-${SHARD}-student-${__VU}`
  let session = access(identifier)
  const headers = {
    'Content-Type': 'application/json',
    'X-CSRF-Token': session.csrfToken,
    'Idempotency-Key': `start-${SHARD}-${__VU}`,
  }
  const started = http.post(`${BASE_URL}/api/v2/assessment/attempts`, null, {
    headers, tags: { name: 'start' },
  })
  check(started, { 'attempt started': (response) => response.status === 201 })
  if (started.status !== 201) fail(`attempt start failed: ${started.status}`)
  const attemptId = started.json('id')

  for (let index = 1; index <= AUTOSAVES_PER_STUDENT; index += 1) {
    headers['Idempotency-Key'] = `save-${SHARD}-${__VU}-${index}`
    const saved = http.patch(
      `${BASE_URL}/api/v2/assessment/attempts/${attemptId}/responses`,
      JSON.stringify({ responses: [{
        itemId: 'capacity-item-1', revision: index,
        response: { optionId: 'capacity-option-a' },
      }] }),
      { headers, tags: { name: 'autosave' } },
    )
    check(saved, { 'autosave accepted': (response) => response.status === 200 })
    if (saved.status === 200) autosaveCount.add(1)
    const tile = http.get(TILE_URL, { tags: { name: 'tile' } })
    check(tile, { 'tile accepted': (response) => response.status === 200 })
    if (index === 10 && __VU % 10 === 0) {
      http.cookieJar().clear(BASE_URL)
      session = access(identifier, true)
      headers['X-CSRF-Token'] = session.csrfToken
      const restored = http.get(`${BASE_URL}/api/v2/assessment/session`, { headers })
      check(restored, {
        'reconnected attempt restored': (response) => response.status === 200
          && response.json('attempt.id') === attemptId,
      })
      if (restored.status === 200) reconnectCount.add(1)
    }
    sleep(150)
  }

  const stormOffset = ((__VU - 1) % 100) / 10
  const elapsed = (Date.now() - campaignStarted) / 1000
  sleep(Math.max(0, HOLD_SECONDS - elapsed + stormOffset))
  headers['Idempotency-Key'] = `submit-${SHARD}-${__VU}`
  const submitted = http.post(
    `${BASE_URL}/api/v2/assessment/attempts/${attemptId}/submit`,
    null, { headers, tags: { name: 'submit' } },
  )
  check(submitted, { 'submission accepted': (response) => response.status === 200 })
  if (submitted.status === 200) submitCount.add(1)
}

export function handleSummary(data) {
  return {
    [`artifacts/assessment-capacity/shard-${SHARD}.json`]: JSON.stringify({
      shard: SHARD,
      seats: 100,
      autosavesPerSeat: AUTOSAVES_PER_STUDENT,
      reconnectPercent: 10,
      holdSeconds: HOLD_SECONDS,
      metrics: data.metrics,
      exactRelease: __ENV.RELEASE_SHA,
    }, null, 2),
    stdout: `assessment shard ${SHARD} completed\n`,
  }
}
