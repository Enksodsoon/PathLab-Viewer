import { ApiError, csrfFetch } from '../api'
import type {
  EvidenceBundle, KnowledgePack, StudyAction, StudyAuthoringSlide, StudyCourseSummary,
  StudyPackDefinition, StudyPackSummary,
  StudySession,
} from './types'

const STUDY_CSRF_KEY = 'pathlab-study-csrf'

async function body<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let code = `HTTP_${response.status}`
    try {
      const value = await response.json() as { detail?: { code?: string } }
      code = value.detail?.code ?? code
    } catch { /* proxy response */ }
    throw new ApiError(response.status, code)
  }
  return response.json() as Promise<T>
}

function studyFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  return fetch(input, {
    ...init,
    credentials: 'same-origin',
    headers: {
      ...(init.headers as Record<string, string> | undefined),
      'X-Study-CSRF': sessionStorage.getItem(STUDY_CSRF_KEY) ?? '',
    },
  })
}

export async function redeemStudyInvitation(code: string): Promise<StudySession> {
  const result = await body<StudySession & { csrfToken: string }>(await fetch('/api/v1/study/redeem', {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, noticeAccepted: true }),
  }))
  sessionStorage.setItem(STUDY_CSRF_KEY, result.csrfToken)
  return result
}

export async function getStudySession(): Promise<StudySession> {
  const result = await body<StudySession & { csrfToken: string }>(await fetch('/api/v1/study/session', {
    credentials: 'same-origin', cache: 'no-store',
  }))
  sessionStorage.setItem(STUDY_CSRF_KEY, result.csrfToken)
  return result
}

export async function submitStudyTask(
  taskId: string,
  submission: { selectedOption?: string; x?: number; y?: number },
) {
  return body<{
    taskId: string
    correct: boolean
    status: 'attempted' | 'completed'
    attemptCount: number
    hints: string[]
    explanation: string
    sources: Array<{ title: string; url: string }>
    spatialError?: number
    claimIds?: string[]
    evidence?: { manifestSha256: string; url: string }
  }>(await studyFetch(`/api/v1/study/tasks/${encodeURIComponent(taskId)}/submit`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(submission),
  }))
}

export async function getStudyKnowledgePack(url: string): Promise<KnowledgePack> {
  return body(await studyFetch(url, { cache: 'no-store' }))
}

export async function getStudyEvidence(url: string): Promise<EvidenceBundle> {
  return body(await studyFetch(url, { cache: 'no-store' }))
}

export async function reportStudyReadiness(outcome: 'ready' | 'fallback') {
  const response = await studyFetch('/api/v1/study/readiness', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ outcome }),
  })
  if (!response.ok) throw new ApiError(response.status, 'STUDY_READINESS_FAILED')
}

export async function reportStudyAiEvent(taskId: string, outcome: StudyAction | 'fallback') {
  const response = await studyFetch('/api/v1/study/ai-events', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ taskId, outcome }),
  })
  if (!response.ok) throw new ApiError(response.status, 'STUDY_AI_EVENT_FAILED')
}

export async function withdrawStudy(): Promise<void> {
  const response = await studyFetch('/api/v1/study/withdraw', { method: 'POST' })
  if (!response.ok) throw new ApiError(response.status, 'STUDY_WITHDRAW_FAILED')
  sessionStorage.removeItem(STUDY_CSRF_KEY)
}

export async function listStudyPacks(): Promise<StudyPackSummary[]> {
  return body(await fetch('/api/v1/admin/study/packs', { credentials: 'same-origin' }))
}

export async function listStudyCourses(): Promise<StudyCourseSummary[]> {
  return body(await fetch('/api/v1/admin/study/courses', { credentials: 'same-origin' }))
}

export async function createStudyCourse(payload: {
  packId: string; title: string; retentionDays: number; learnerLimit: number; endsAt?: string
  aiMode: 'deterministic' | 'closed_pilot_trace_sim'; pilotAcknowledged: boolean
}): Promise<StudyCourseSummary> {
  return body(await csrfFetch('/api/v1/admin/study/courses', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }))
}

export async function listStudyAuthoringSlides(): Promise<StudyAuthoringSlide[]> {
  return body(await fetch('/api/v1/admin/study/authoring/slides', { credentials: 'same-origin' }))
}

export async function validateStudyPack(definition: StudyPackDefinition) {
  return body<{ canonicalCore: StudyPackDefinition; checksum: string }>(await csrfFetch(
    '/api/v1/admin/study/packs/validate',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(definition) },
  ))
}

export async function publishStudyPack(definition: StudyPackDefinition): Promise<StudyPackSummary> {
  return body(await csrfFetch('/api/v1/admin/study/packs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(definition),
  }))
}

export async function transitionStudyCourse(courseId: string, action: 'prepare' | 'activate' | 'end' | 'purge') {
  return body<StudyCourseSummary>(await csrfFetch(
    `/api/v1/admin/study/courses/${encodeURIComponent(courseId)}/${action}`,
    { method: 'POST' },
  ))
}

export async function downloadStudyInvitations(courseId: string, count: number): Promise<void> {
  const response = await csrfFetch(`/api/v1/admin/study/courses/${encodeURIComponent(courseId)}/invitations`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ count }),
  })
  if (!response.ok) throw new ApiError(response.status, 'STUDY_INVITATIONS_FAILED')
  const link = document.createElement('a')
  link.href = URL.createObjectURL(await response.blob())
  link.download = `study-invitations-${courseId}.csv`
  link.click()
  URL.revokeObjectURL(link.href)
}

export function downloadStudyProgress(courseId: string): void {
  window.location.assign(`/api/v1/admin/study/courses/${encodeURIComponent(courseId)}/progress.csv`)
}
