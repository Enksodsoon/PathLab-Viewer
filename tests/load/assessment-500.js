import http from 'k6/http'
import { check, fail, sleep } from 'k6'

const BASE_URL = __ENV.BASE_URL
const PUBLIC_ID = __ENV.PUBLIC_ID
const AUTOSAVES_PER_STUDENT = 20
if (!BASE_URL || !PUBLIC_ID) fail('BASE_URL and PUBLIC_ID are required')

export const options = {
  vus: 100,
  duration: '60m',
  thresholds: {
    http_req_failed: ['rate<0.001'],
    'http_req_duration{name:autosave}': ['p(95)<=500'],
    'http_req_duration{name:submit}': ['p(95)<=1000'],
    checks: ['rate>0.999'],
  },
}

export default function () {
  if (__VU > 100) fail('each shard is bounded to 100 learners')
  const identifier = `shard-${__ENV.SHARD}-student-${__VU}`
  const access = http.post(
    `${BASE_URL}/api/v2/assessment/access`,
    JSON.stringify({
      kind: 'roster', publicId: PUBLIC_ID, studentIdentifier: identifier,
      accessCode: __ENV.ACCESS_CODE,
    }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'access' } },
  )
  check(access, { 'access accepted': (response) => response.status === 201 })
  if (access.status !== 201) fail(`access failed: ${access.status}`)
  const payload = access.json()
  const headers = {
    'Content-Type': 'application/json',
    'X-CSRF-Token': payload.csrfToken,
    'Idempotency-Key': `start-${__ENV.SHARD}-${__VU}`,
  }
  const started = http.post(`${BASE_URL}/api/v2/assessment/attempts`, null, { headers })
  check(started, { 'attempt started': (response) => response.status === 201 })
  const attemptId = started.json('id')
  for (let index = 1; index <= AUTOSAVES_PER_STUDENT; index += 1) {
    headers['Idempotency-Key'] = `save-${__ENV.SHARD}-${__VU}-${index}`
    const saved = http.patch(
      `${BASE_URL}/api/v2/assessment/attempts/${attemptId}/responses`,
      JSON.stringify({ responses: [{
        itemId: 'capacity-item-1', revision: index,
        response: { optionId: 'capacity-option-a' },
      }] }),
      { headers, tags: { name: 'autosave' } },
    )
    check(saved, { 'autosave accepted': (response) => response.status === 200 })
    if (index === 10 && __VU % 10 === 0) sleep(2)
    sleep(2.5)
  }
  sleep((__VU % 10) / 10)
  headers['Idempotency-Key'] = `submit-${__ENV.SHARD}-${__VU}`
  const submitted = http.post(
    `${BASE_URL}/api/v2/assessment/attempts/${attemptId}/submit`,
    null, { headers, tags: { name: 'submit' } },
  )
  check(submitted, { 'submission accepted': (response) => response.status === 200 })
}
