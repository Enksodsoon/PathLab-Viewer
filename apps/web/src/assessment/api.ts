import { csrfFetch as baseCsrfFetch } from '../api'
import type {
  AssessmentDocument,
  AssessmentDraft,
  AssessmentDraftList,
  EligibleAssessmentSlide,
} from './types'

function csrfFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const idempotencyKey = globalThis.crypto?.randomUUID?.()
    ?? `assessment-${Date.now()}-${Math.random()}`
  return baseCsrfFetch(input, {
    ...init,
    headers: {
      ...(init.headers as Record<string, string> | undefined),
      'Idempotency-Key': idempotencyKey,
    },
  })
}

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

export async function listAssessmentDrafts(classId?: string): Promise<AssessmentDraftList> {
  const search = classId ? `?cohort_id=${encodeURIComponent(classId)}` : ''
  return body(await fetch(`/api/v2/admin/assessment/drafts${search}`, {
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
  context?: { courseId: string; classId?: string },
): Promise<AssessmentDraft> {
  return body(await csrfFetch('/api/v2/admin/assessment/drafts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, document, ...context }),
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
  draftId: string
  cohortId: string | null
  publicId: string
  title: string
  version: number
  mode: 'practice' | 'formative' | 'quiz'
  status: string
  responses: number
  expectedParticipants: number | null
  completedParticipants: number
  createdAt: string
}

export async function restoreAssessmentDraft(id: string) {
  return body<AssessmentDraft>(await csrfFetch(
    `/api/v2/admin/assessment/drafts/${encodeURIComponent(id)}/restore`,
    { method: 'POST' },
  ))
}

export interface AssessmentCourseClass {
  id: string
  name: string
  sectionCode: string | null
  description: string | null
  location: string | null
  folderId: string | null
  rosterRule: AssessmentClassRosterRule
  opensAt: string | null
  closesAt: string | null
  status: string
  studentCount: number
}

export interface AssessmentCourse {
  id: string
  name: string
  courseCode: string
  semester: string
  academicYear: string | null
  iconKey: import('./courseIcons').CourseIconKey
  scoringMethod: 'points' | 'percentage' | 'weighted' | 'pass_fail'
  description: string | null
  opensAt: string | null
  closesAt: string | null
  status: 'draft' | 'active' | 'archived'
  rosterCount: number
  classCount: number
  classes?: AssessmentCourseClass[]
}

export interface AssessmentCourseInput {
  name: string
  courseCode: string
  semester: string
  academicYear: string
  iconKey: AssessmentCourse['iconKey']
  scoringMethod: AssessmentCourse['scoringMethod']
  description: string
  opensAt: string | null
  closesAt: string | null
  status: AssessmentCourse['status']
}

export async function listAssessmentCourses() {
  return body<{ items: AssessmentCourse[]; total: number }>(await fetch('/api/v2/admin/assessment/courses', {
    credentials: 'same-origin', cache: 'no-store',
  }))
}

export async function getAssessmentCourse(courseId: string) {
  return body<AssessmentCourse>(await fetch(`/api/v2/admin/assessment/courses/${encodeURIComponent(courseId)}`, {
    credentials: 'same-origin', cache: 'no-store',
  }))
}

export async function createAssessmentCourse(input: AssessmentCourseInput) {
  return body<AssessmentCourse>(await csrfFetch('/api/v2/admin/assessment/courses', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  }))
}

export async function updateAssessmentCourse(courseId: string, input: Partial<AssessmentCourseInput>) {
  return body<AssessmentCourse>(await csrfFetch(`/api/v2/admin/assessment/courses/${encodeURIComponent(courseId)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  }))
}

export async function previewAssessmentCourseRoster(courseId: string, rows: string) {
  return body<{ validCount: number; checksum: string; warningCount: number; warnings: AssessmentRosterWarning[]; preview: Array<{ studentId: string; firstName: string; lastName: string | null; displayName: string; group: string | null; subgroup: string | null; metadata: Record<string, string> }> }>(await csrfFetch(
    `/api/v2/admin/assessment/courses/${encodeURIComponent(courseId)}/roster/import/preview`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rows }) },
  ))
}

export async function commitAssessmentCourseRoster(courseId: string, rows: string, checksum: string, confirmWarnings = false) {
  return body<{ created: number; skipped: number }>(await csrfFetch(
    `/api/v2/admin/assessment/courses/${encodeURIComponent(courseId)}/roster/import/commit`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rows, checksum, confirmWarnings }) },
  ))
}

export interface AssessmentRosterWarning {
  code: 'existing_student_id' | 'matching_full_name' | 'matching_identifier'
  studentId: string
  matchedStudentId: string
  field?: string
  message: string
}

export interface AssessmentRosterColumn {
  key: string
  label: string
  sortable: boolean
}

export interface AssessmentRosterLearner {
  id: string
  studentId: string | null
  firstName: string | null
  lastName: string | null
  displayName: string | null
  group: string | null
  subgroup: string | null
  email: string | null
  metadata: Record<string, string>
  status: string
}

export type AssessmentRosterSort = 'name' | 'student_id' | 'group' | 'subgroup' | 'email' | 'status'

export async function listAssessmentCourseRoster(courseId: string, options: { query?: string; sortBy?: AssessmentRosterSort; sortDirection?: 'asc' | 'desc'; limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams({
    query: options.query ?? '', sort_by: options.sortBy ?? 'name', sort_direction: options.sortDirection ?? 'asc',
    limit: String(options.limit ?? 100), offset: String(options.offset ?? 0),
  })
  return body<{ items: AssessmentRosterLearner[]; columns: AssessmentRosterColumn[]; total: number; limit: number; offset: number }>(await fetch(
    `/api/v2/admin/assessment/courses/${encodeURIComponent(courseId)}/roster?${search}`,
    { credentials: 'same-origin', cache: 'no-store' },
  ))
}

export async function listAllAssessmentCourseRoster(courseId: string) {
  const items: AssessmentRosterLearner[] = []
  let offset = 0
  for (;;) {
    const page = await listAssessmentCourseRoster(courseId, { limit: 200, offset })
    items.push(...page.items)
    if (items.length >= page.total || page.items.length === 0) return items
    offset += page.items.length
  }
}

export function assessmentCourseRosterExportUrl(courseId: string) {
  return `/api/v2/admin/assessment/courses/${encodeURIComponent(courseId)}/roster/export`
}

export async function updateAssessmentCourseEnrollment(courseId: string, learnerId: string, status: 'active' | 'withdrawn') {
  return body<{ learnerId: string; status: string }>(await csrfFetch(
    `/api/v2/admin/assessment/courses/${encodeURIComponent(courseId)}/roster/${encodeURIComponent(learnerId)}`,
    { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) },
  ))
}

export interface AssessmentRosterLearnerInput {
  studentId: string
  firstName: string
  lastName: string
  group: string
  subgroup: string
  email: string
  metadata: Record<string, string>
}

export async function updateAssessmentCourseLearner(courseId: string, learnerId: string, input: AssessmentRosterLearnerInput) {
  return body<AssessmentRosterLearner>(await csrfFetch(
    `/api/v2/admin/assessment/courses/${encodeURIComponent(courseId)}/roster/${encodeURIComponent(learnerId)}/profile`,
    { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) },
  ))
}

export async function removeAllAssessmentCourseLearners(courseId: string) {
  return body<{ removed: number }>(await csrfFetch(
    `/api/v2/admin/assessment/courses/${encodeURIComponent(courseId)}/roster`,
    { method: 'DELETE' },
  ))
}

export interface AssessmentClassInput {
  name: string
  sectionCode: string
  description: string
  location: string
  opensAt: string | null
  closesAt: string | null
  rosterRule: AssessmentClassRosterRule
}

export interface AssessmentClassRosterFilter {
  field: string
  values: string[]
}

export interface AssessmentClassRosterRule {
  mode: 'all' | 'filters' | 'existing'
  filters: AssessmentClassRosterFilter[]
}

export async function createAssessmentCourseClass(courseId: string, input: AssessmentClassInput) {
  return body<AssessmentCourseClass>(await csrfFetch(
    `/api/v2/admin/assessment/courses/${encodeURIComponent(courseId)}/classes`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) },
  ))
}

export async function updateAssessmentClass(classId: string, input: Partial<AssessmentClassInput> & { status?: string; folderId?: string | null }) {
  return body<AssessmentCourseClass>(await csrfFetch(`/api/v2/admin/assessment/classes/${encodeURIComponent(classId)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  }))
}

export async function replaceAssessmentClassRoster(classId: string, rosterRule: AssessmentClassRosterRule) {
  return body<{ active: number }>(await csrfFetch(`/api/v2/admin/assessment/classes/${encodeURIComponent(classId)}/roster`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rosterRule }),
  }))
}

export async function getAssessmentClassRosterSelection(classId: string) {
  return body<{
    items: Array<{ id: string; studentId: string | null; displayName: string | null; group: string | null; subgroup: string | null; metadata: Record<string, string>; selected: boolean }>
    rosterRule: AssessmentClassRosterRule
    total: number
  }>(await fetch(
    `/api/v2/admin/assessment/classes/${encodeURIComponent(classId)}/roster-selection`,
    { credentials: 'same-origin', cache: 'no-store' },
  ))
}

export async function listAssessmentAdministrations(cohortId?: string) {
  const search = cohortId ? `?cohort_id=${encodeURIComponent(cohortId)}` : ''
  return body<{ items: AssessmentAdministrationSummary[]; total: number }>(await fetch(
    `/api/v2/admin/assessment/administrations${search}`,
    { credentials: 'same-origin', cache: 'no-store' },
  ))
}

export async function setAssessmentAdministrationStatus(
  administrationId: string,
  currentStatus: string,
  targetStatus: 'draft' | 'open' | 'closed',
) {
  const path = `/api/v2/admin/assessment/administrations/${encodeURIComponent(administrationId)}`
  void currentStatus
  return body<{ id: string; status: string }>(await csrfFetch(`${path}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: targetStatus }),
  }))
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
      studentId?: string | null
      firstName?: string | null
      lastName?: string | null
      displayName: string | null
      group?: string | null
      subgroup?: string | null
      email?: string | null
      metadata?: Record<string, string>
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
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': globalThis.crypto?.randomUUID?.() ?? `access-${Date.now()}`,
    },
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
