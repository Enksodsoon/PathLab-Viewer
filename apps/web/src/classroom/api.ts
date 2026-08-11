import { ApiError, csrfFetch } from '../api'

export interface ClassroomSlide {
  id: string
  position: number
  displayName: string
  assetVersion: string
  tileSource: string
  width: number
  height: number
  tileSize: number
  format: string
}

export interface PresenterState {
  sequence: number
  slideId: string | null
  viewport: { x: number; y: number; zoom: number } | null
}

export interface CreatedClassroom {
  id: string
  joinCode: string
  stateVersion: number
  slides: ClassroomSlide[]
}

export interface TeacherState {
  session: { id: string; status: string }
  stateVersion: number
  presenter: PresenterState
  controller: {
    participantId: string | null
    leaseId: string | null
    controlEpoch: number
    expiresAt: string | null
  }
  participants: Array<{
    id: string
    alias: string
    displayName: string | null
    status: 'connected' | 'reconnecting' | 'disconnected'
  }>
  pendingQuestions: Array<{
    id: string
    participantId: string
    slideId: string
    text: string
    x: number
    y: number
    zoom: number
  }>
}

export interface StudentState {
  session: { id: string; status: string }
  participant: { id: string; alias: string }
  csrfToken: string
  stateVersion: number
  presenter: PresenterState
  control: {
    isController: boolean
    leaseId: string | null
    controlEpoch: number
    expiresAt: string | null
  }
  slides: ClassroomSlide[]
  pendingQuestionIds: string[]
}

async function body<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let code = `HTTP_${response.status}`
    try {
      const data = await response.json() as { detail?: { code?: string } }
      code = data.detail?.code ?? code
    } catch {
      // Proxy errors need the same compact failure shape.
    }
    throw new ApiError(response.status, code)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function createClassroom(slideIds: string[]): Promise<CreatedClassroom> {
  return body(await csrfFetch('/api/v1/admin/classroom/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slideIds }),
  }))
}

export async function teacherState(sessionId: string): Promise<TeacherState> {
  return body(await fetch(`/api/v1/admin/classroom/sessions/${encodeURIComponent(sessionId)}`, {
    credentials: 'same-origin', cache: 'no-store',
  }))
}

export async function joinClassroom(joinCode: string, displayName?: string): Promise<{
  sessionId: string
  participant: { id: string; alias: string; displayName: string | null }
  csrfToken: string
}> {
  return body(await fetch('/api/v1/classroom/join', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ joinCode, displayName: displayName || null }),
  }))
}

export async function studentState(sessionId: string): Promise<StudentState> {
  return body(await fetch(`/api/v1/classroom/sessions/${encodeURIComponent(sessionId)}`, {
    credentials: 'same-origin', cache: 'no-store',
  }))
}

export async function submitQuestion(
  sessionId: string,
  csrfToken: string,
  question: { slideId: string; text: string; x: number; y: number; zoom: number },
): Promise<void> {
  await body(await fetch(`/api/v1/classroom/sessions/${encodeURIComponent(sessionId)}/questions`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...question,
      csrfToken,
      idempotencyKey: crypto.randomUUID(),
    }),
  }))
}

export async function grantControl(
  sessionId: string, participantId: string,
): Promise<void> {
  await body(await csrfFetch(`/api/v1/admin/classroom/sessions/${sessionId}/control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ participantId, seconds: 120 }),
  }))
}

export async function openQuestion(sessionId: string, questionId: string): Promise<void> {
  await body(await csrfFetch(
    `/api/v1/admin/classroom/sessions/${sessionId}/questions/${questionId}/open`,
    { method: 'POST' },
  ))
}

export async function answerQuestion(sessionId: string, questionId: string): Promise<void> {
  await body(await csrfFetch(
    `/api/v1/admin/classroom/sessions/${sessionId}/questions/${questionId}`,
    { method: 'DELETE' },
  ))
}

export async function endClassroom(sessionId: string): Promise<void> {
  await body(await csrfFetch(`/api/v1/admin/classroom/sessions/${sessionId}`, {
    method: 'DELETE',
  }))
}

export async function publishTeacherViewport(
  sessionId: string,
  viewport: { slideId: string; x: number; y: number; zoom: number },
): Promise<void> {
  await body(await csrfFetch(`/api/v1/admin/classroom/sessions/${sessionId}/presenter`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(viewport),
  }))
}

export async function publishStudentViewport(
  sessionId: string,
  csrfToken: string,
  leaseId: string,
  viewport: { slideId: string; x: number; y: number; zoom: number },
): Promise<void> {
  await body(await fetch(`/api/v1/classroom/sessions/${sessionId}/presenter`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...viewport, csrfToken, leaseId }),
  }))
}
