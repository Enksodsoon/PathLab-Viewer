import { csrfFetch } from '../api'
import type {
  AssessmentDocument,
  AssessmentDraft,
  AssessmentDraftList,
  EligibleAssessmentSlide,
} from './types'

export class AssessmentHttpError extends Error {
  constructor(public status: number, public detail: Record<string, unknown>) {
    super(`ASSESSMENT_HTTP_${status}`)
  }
}

async function body<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: Record<string, unknown> }
    throw new AssessmentHttpError(response.status, payload.detail ?? {})
  }
  return response.json() as Promise<T>
}

export async function listAssessmentDrafts(): Promise<AssessmentDraftList> {
  return body(await fetch('/api/v2/admin/assessment/drafts', {
    credentials: 'same-origin',
    cache: 'no-store',
  }))
}

export async function getAssessmentDraft(id: string): Promise<AssessmentDraft> {
  return body(await fetch(`/api/v2/admin/assessment/drafts/${encodeURIComponent(id)}`, {
    credentials: 'same-origin',
    cache: 'no-store',
  }))
}

export async function createAssessmentDraft(
  title: string,
  document: AssessmentDocument,
): Promise<AssessmentDraft> {
  return body(await csrfFetch('/api/v2/admin/assessment/drafts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, document }),
  }))
}

export async function saveAssessmentDraft(
  id: string,
  revision: number,
  document: AssessmentDocument,
): Promise<AssessmentDraft> {
  return body(await csrfFetch(`/api/v2/admin/assessment/drafts/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'If-Match': String(revision) },
    body: JSON.stringify({ document }),
  }))
}

export async function previewAssessmentDraft(id: string) {
  return body<{ learnerManifest: AssessmentDocument; checksum: string }>(
    await csrfFetch(`/api/v2/admin/assessment/drafts/${encodeURIComponent(id)}/preview`, {
      method: 'POST',
    }),
  )
}

export interface PublishAssessmentSettings {
  mode: 'practice' | 'formative' | 'quiz'
  cohortId?: string
  durationSeconds: number
  maxAttempts: number
  accessCode?: string
}

export async function duplicateAssessmentDraft(id: string, title?: string) {
  return body<AssessmentDraft>(await csrfFetch(
    `/api/v2/admin/assessment/drafts/${encodeURIComponent(id)}/duplicate`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) },
  ))
}

export async function archiveAssessmentDraft(id: string) {
  return body<AssessmentDraft>(await csrfFetch(
    `/api/v2/admin/assessment/drafts/${encodeURIComponent(id)}/archive`,
    { method: 'POST' },
  ))
}

export async function importAssessmentQuestions(id: string, sourceDraftId: string, itemIds: string[], expectedRevision: number) {
  return body<AssessmentDraft>(await csrfFetch(
    `/api/v2/admin/assessment/drafts/${encodeURIComponent(id)}/import-questions`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sourceDraftId, itemIds, expectedRevision }) },
  ))
}

export async function publishAssessmentDraft(id: string, settings?: PublishAssessmentSettings) {
  return body<{
    id: string
    checksum: string
    schema: string
    publicId: string | null
    administrationId: string | null
  }>(
    await csrfFetch(`/api/v2/admin/assessment/drafts/${encodeURIComponent(id)}/publish`, {
      method: 'POST',
      ...(settings ? {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      } : {}),
    }),
  )
}

export async function getAssessmentMetadata(publicId: string) {
  return body<{
    publicId: string
    mode: 'practice' | 'formative' | 'quiz'
    status: string
    durationSeconds: number
    closesAt: string | null
    manifest: AssessmentDocument
    assets: Record<string, string>
  }>(await fetch(`/api/v2/assessment/administrations/${encodeURIComponent(publicId)}`, {
    credentials: 'same-origin',
    cache: 'no-store',
  }))
}

export async function getPracticeBundle(publicId: string) {
  return body<{
    publicId: string
    storage: 'browser-local'
    definition: AssessmentDocument
    assets: Record<string, string>
  }>(await fetch(`/api/v2/assessment/practice/${encodeURIComponent(publicId)}`, {
    credentials: 'same-origin',
    cache: 'no-store',
  }))
}

export async function listAssessmentClasses() {
  return body<{
    items: Array<{ id: string; name: string; status: string; studentCount: number }>
    total: number
  }>(await fetch('/api/v2/admin/assessment/classes', {
    credentials: 'same-origin',
    cache: 'no-store',
  }))
}

export async function createAssessmentClass(name: string) {
  return body<{ id: string; name: string; status: string }>(
    await csrfFetch('/api/v2/admin/assessment/classes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }),
  )
}

export async function listEligibleAssessmentSlides(query = '') {
  const search = new URLSearchParams({ query })
  return body<{ items: EligibleAssessmentSlide[] }>(
    await fetch(`/api/v2/admin/assessment/slides?${search}`, {
      credentials: 'same-origin',
      cache: 'no-store',
    }),
  )
}

export async function previewAssessmentRoster(cohortId: string, rows: string) {
  return body<{ validCount: number; checksum: string; preview: Array<{ displayName: string | null }> }>(
    await csrfFetch(`/api/v2/admin/assessment/classes/${encodeURIComponent(cohortId)}/import/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows }),
    }),
  )
}

export async function commitAssessmentRoster(cohortId: string, rows: string, checksum: string) {
  return body<{ created: number }>(
    await csrfFetch(`/api/v2/admin/assessment/classes/${encodeURIComponent(cohortId)}/import/commit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows, checksum }),
    }),
  )
}

export async function listAssessmentStudents(cohortId: string, offset = 0) {
  return body<{
    items: Array<{ id: string; displayName: string | null; status: string }>
    total: number
  }>(await fetch(
    `/api/v2/admin/assessment/classes/${encodeURIComponent(cohortId)}/students?limit=50&offset=${offset}`,
    { credentials: 'same-origin', cache: 'no-store' },
  ))
}

export async function updateAssessmentEnrollment(cohortId: string, learnerId: string, status: 'active' | 'withdrawn') {
  return body<{ learnerId: string; status: string }>(await csrfFetch(
    `/api/v2/admin/assessment/classes/${encodeURIComponent(cohortId)}/students/${encodeURIComponent(learnerId)}`,
    { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) },
  ))
}

export interface AssessmentAdministrationSummary {
  id: string
  publicId: string
  title: string
  mode: 'practice' | 'formative' | 'quiz'
  status: string
  responses: number
  createdAt: string
}

export async function listAssessmentAdministrations() {
  return body<{ items: AssessmentAdministrationSummary[]; total: number }>(await fetch(
    '/api/v2/admin/assessment/administrations',
    { credentials: 'same-origin', cache: 'no-store' },
  ))
}

export interface AssessmentResults {
  administration: { id: string; mode: string; status: string }
  summary: {
    responses: number
    averagePoints: string
    completionRate: string
    needsGrading: number
    questions: Record<string, {
      responseCount: number
      scoredCount: number
      averagePoints: string
      spatialHeatmap?: { width: number; height: number; counts: number[][] }
    }>
  }
  individuals: {
    total: number
    items: Array<{
      attemptId: string
      displayName: string | null
      status: string
      scoreVersion: number | null
      points: string | null
      maximumPoints: string | null
      breakdown: Record<string, string | null>
      responses: Record<string, Record<string, unknown>>
    }>
  }
}

export async function getAssessmentResults(administrationId: string, offset = 0) {
  return body<AssessmentResults>(await fetch(
    `/api/v2/admin/assessment/administrations/${encodeURIComponent(administrationId)}/results?limit=50&offset=${offset}`,
    { credentials: 'same-origin', cache: 'no-store' },
  ))
}

export async function gradeAssessmentResponse(administrationId: string, payload: {
  attemptId: string
  itemId: string
  points: string
  expectedScoreVersion: number
}) {
  return body<{ scoreVersion: number; points: string; maximumPoints: string }>(await csrfFetch(
    `/api/v2/admin/assessment/administrations/${encodeURIComponent(administrationId)}/manual-grade`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
  ))
}

export async function releaseAssessmentResults(administrationId: string) {
  return body<{ id: string; releasedAt: string }>(await csrfFetch(
    `/api/v2/admin/assessment/administrations/${encodeURIComponent(administrationId)}/release`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ showScore: true, showAnswers: false, showFeedback: false }) },
  ))
}

export async function updateAssessmentRetention(administrationId: string, retentionDays: number, hold: boolean) {
  return body<{ retentionDays: number; hold: boolean }>(await csrfFetch(
    `/api/v2/admin/assessment/administrations/${encodeURIComponent(administrationId)}/retention`,
    { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ retentionDays, hold }) },
  ))
}

export async function purgeAssessmentRecords(administrationId: string) {
  return body<{ status: string; deleted: number; remaining: number }>(await csrfFetch(
    `/api/v2/admin/assessment/administrations/${encodeURIComponent(administrationId)}/purge?batchSize=100`,
    { method: 'POST' },
  ))
}

export interface AssessmentAccessResult {
  kind: 'anonymous' | 'roster'
  publicId: string
  csrfToken: string
  receipt?: string
}

export async function accessAssessment(payload: {
  kind: 'anonymous' | 'roster'
  publicId: string
  studentIdentifier?: string
  accessCode?: string
  takeover?: boolean
}) {
  return body<AssessmentAccessResult>(await fetch('/api/v2/assessment/access', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

function studentMutation(path: string, csrfToken: string, idempotencyKey: string, init: RequestInit) {
  return fetch(path, {
    ...init,
    credentials: 'same-origin',
    headers: {
      ...init.headers,
      'X-CSRF-Token': csrfToken,
      'Idempotency-Key': idempotencyKey,
    },
  })
}

export async function restoreAssessmentSession(csrfToken: string) {
  return body<{
    kind: 'anonymous' | 'roster'
    publicId: string
    status: string
    manifest: AssessmentDocument
    deviceGeneration: number
    attempt: null | {
      id: string
      ordinal: number
      status: string
      startedAt: string
      responses: Array<{ itemId: string; revision: number; response: Record<string, unknown> }>
    }
  }>(await fetch('/api/v2/assessment/session', {
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'X-CSRF-Token': csrfToken },
  }))
}

export async function startAssessmentAttempt(csrfToken: string, idempotencyKey: string) {
  return body<{ id: string; ordinal: number; status: string; startedAt: string }>(
    await studentMutation('/api/v2/assessment/attempts', csrfToken, idempotencyKey, { method: 'POST' }),
  )
}

export async function saveAssessmentResponses(
  attemptId: string,
  csrfToken: string,
  idempotencyKey: string,
  responses: Array<{ itemId: string; revision: number; response: Record<string, unknown> }>,
) {
  return body<{ saved: number }>(await studentMutation(
    `/api/v2/assessment/attempts/${encodeURIComponent(attemptId)}/responses`,
    csrfToken,
    idempotencyKey,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ responses }),
    },
  ))
}

export async function submitAssessmentAttempt(
  attemptId: string,
  csrfToken: string,
  idempotencyKey: string,
) {
  return body<{
    status: string
    score?: { points: string; maximumPoints: string }
    needsGrading: boolean
  }>(await studentMutation(
    `/api/v2/assessment/attempts/${encodeURIComponent(attemptId)}/submit`,
    csrfToken,
    idempotencyKey,
    { method: 'POST' },
  ))
}

export async function getAssessmentResult(attemptId: string, csrfToken: string) {
  return body<{
    status: string
    released: boolean
    score?: { points: string; maximumPoints: string }
    breakdown?: Record<string, string | null>
  }>(await fetch(`/api/v2/assessment/attempts/${encodeURIComponent(attemptId)}/result`, {
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'X-CSRF-Token': csrfToken },
  }))
}
