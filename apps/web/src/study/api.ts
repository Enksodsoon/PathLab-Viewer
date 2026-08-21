import { ApiError, csrfFetch } from '../api'
import type { StudyCourseSummary, StudyPackSummary, StudySession } from './types'

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
  return body<StudySession>(await fetch('/api/v1/study/session', {
    credentials: 'same-origin', cache: 'no-store',
  }))
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
  }>(await studyFetch(`/api/v1/study/tasks/${encodeURIComponent(taskId)}/submit`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(submission),
  }))
}

export async function reportStudyReadiness(outcome: 'ready' | 'fallback') {
  const response = await studyFetch('/api/v1/study/readiness', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ outcome }),
  })
  if (!response.ok) throw new ApiError(response.status, 'STUDY_READINESS_FAILED')
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
}): Promise<StudyCourseSummary> {
  return body(await csrfFetch('/api/v1/admin/study/courses', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
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
