import { SharedArray } from 'k6/data'
import http from 'k6/http'
import { check, sleep } from 'k6'
import { Trend } from 'k6/metrics'

const baseUrl = __ENV.PATHLAB_BASE_URL
const taskId = __ENV.PATHLAB_STUDY_TASK_ID
if (!baseUrl || !taskId) throw new Error('PATHLAB_BASE_URL and PATHLAB_STUDY_TASK_ID are required')

const codes = new SharedArray('study invitations', () => {
  const lines = open(__ENV.PATHLAB_STUDY_INVITATIONS_CSV).trim().split(/\r?\n/)
  return lines.slice(1).map((line) => line.replace(/^"|"$/g, '').replace(/""/g, '"'))
})
if (codes.length !== 500) throw new Error(`Exactly 500 invitation codes are required; received ${codes.length}`)

const submissionLatency = new Trend('study_submission_latency', true)

export const options = {
  scenarios: {
    one_active_course: {
      executor: 'per-vu-iterations', vus: 500, iterations: 1, maxDuration: '90s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.001'],
    study_submission_latency: ['p(95)<500'],
    checks: ['rate>0.999'],
  },
}

export default function () {
  const invitation = codes[__VU - 1]
  const redemption = http.post(`${baseUrl}/api/v1/study/redeem`, JSON.stringify({
    code: invitation, noticeAccepted: true,
  }), { headers: { 'Content-Type': 'application/json' } })
  check(redemption, { 'invitation redeemed once': (response) => response.status === 201 })
  if (redemption.status !== 201) return

  // Uniformly distribute exactly one accepted submission per learner over 60 seconds.
  sleep((__VU - 1) * 60 / 500)
  const csrf = redemption.json('csrfToken')
  const submission = http.post(
    `${baseUrl}/api/v1/study/tasks/${encodeURIComponent(taskId)}/submit`,
    JSON.stringify({ selectedOption: __ENV.PATHLAB_STUDY_ANSWER }),
    { headers: { 'Content-Type': 'application/json', 'X-Study-CSRF': csrf } },
  )
  submissionLatency.add(submission.timings.duration)
  check(submission, { 'task accepted': (response) => response.status === 200 })
}
