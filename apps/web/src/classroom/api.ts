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
  folderPath: string[]
}

export interface PresenterState {
  sequence: number
  slideId: string | null
  viewport: { x: number; y: number; zoom: number; zoomSpace?: 'image' | 'viewport' } | null
}

export interface TeacherPointer {
  slideId: string
  style: 'green-arrow' | 'red-arrow'
  x: number
  y: number
}

export interface TeachingAnnotation {
  id: string
  slideId: string
  tool: 'pen' | 'highlight' | 'line' | 'rectangle' | 'ellipse'
  color: '#ef765f' | '#f6c84a' | '#42b883' | '#4f8be8' | '#f6f2e8'
  width: 2 | 4 | 8
  points: Array<{ x: number; y: number }>
}

export interface CreatedClassroom {
  id: string
  joinCode: string
  publicId: string | null
  phase: ClassroomPhase
  reviewExpiresAt: string | null
  stateVersion: number
  slides: ClassroomSlide[]
}

export type ClassroomPhase = 'preview' | 'live' | 'review' | 'revoked'

export interface ClassroomReadiness {
  folderId: string
  ready: Array<{ id: string; displayName: string; folderPath: string[] }>
  blocked: Array<{
    id: string
    displayName: string
    folderPath: string[]
    reason: 'publication_incomplete' | 'delivery_missing' | 'metadata_invalid'
  }>
  tooManySlides: boolean
}

export interface ClassroomSetupFolder {
  id: string
  name: string
  folderPath: string[]
  depth: number
  hasChildren: boolean
  readyCount: number
  blockedCount: number
  tooManySlides: boolean
}

export interface ClassroomSetupFoldersPage {
  items: ClassroomSetupFolder[]
  nextCursor: string | null
}

export interface ClassroomInviteState {
  sessionId: string
  publicId: string
  phase: ClassroomPhase
  reviewExpiresAt: string
  participant: { id: string; alias: string }
  csrfToken: string
  slides: ClassroomSlide[]
}

export interface ClassroomParticipant {
  id: string
  alias: string
  displayName: string | null
  status: 'connected' | 'reconnecting' | 'disconnected'
  controlRequested: boolean
  controlRequestedAt: number | null
}

export interface TeacherParticipantsPage {
  items: ClassroomParticipant[]
  total: number
  nextCursor: string | null
  rosterVersion: number
}

export interface TeacherState {
  session: {
    id: string
    status: string
    phase: ClassroomPhase
    publicId: string | null
    joinCode: string | null
    reviewExpiresAt: string | null
  }
  stateVersion: number
  slides: ClassroomSlide[]
  participantCount: number
  rosterVersion: number
  presenter: PresenterState
  controller: {
    participantId: string | null
    leaseId: string | null
    controlEpoch: number
    expiresAt: string | null
  }
  participants: ClassroomParticipant[]
  pendingQuestions: Array<{
    id: string
    participantId: string
    slideId: string
    text: string
    x: number
    y: number
    zoom: number
  }>
  activePins: Array<{
    participantId: string
    alias: string
    slideId: string
    x: number
    y: number
    zoom: number
  }>
  teacherPointer: TeacherPointer | null
  teachingAnnotations: TeachingAnnotation[]
}

export interface StudentState {
  session: { id: string; status: string; phase: ClassroomPhase; publicId: string | null }
  participant: { id: string; alias: string }
  csrfToken: string
  stateVersion: number
  presenter: PresenterState
  control: {
    isController: boolean
    requested: boolean
    leaseId: string | null
    controlEpoch: number
    expiresAt: string | null
  }
  slides: ClassroomSlide[]
  pendingQuestionIds: string[]
  activePin: {
    participantId: string
    slideId: string
    x: number
    y: number
    zoom: number
  } | null
  teacherPointer: TeacherPointer | null
  teachingAnnotations: TeachingAnnotation[]
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

export async function classroomReadiness(folderId: string): Promise<ClassroomReadiness> {
  return body(await csrfFetch('/api/v1/admin/classroom/readiness', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ folderId }),
  }))
}

export async function classroomSetupFolders(
  query: { cursor?: string | null; limit?: number; q?: string } = {},
): Promise<ClassroomSetupFoldersPage> {
  const parameters = new URLSearchParams()
  if (query.cursor) parameters.set('cursor', query.cursor)
  parameters.set('limit', String(Math.max(1, Math.min(50, Math.floor(query.limit ?? 20)))))
  const normalizedQuery = query.q?.trim()
  if (normalizedQuery) parameters.set('q', normalizedQuery)
  return body(await fetch(
    `/api/v1/admin/classroom/setup/folders?${parameters.toString()}`,
    { credentials: 'same-origin', cache: 'no-store' },
  ))
}

export async function createClassroom(
  folderId: string,
  reviewExpiresAt: string,
): Promise<CreatedClassroom> {
  return body(await csrfFetch('/api/v1/admin/classroom/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folderId, reviewExpiresAt }),
  }))
}

export async function startLiveClassroom(sessionId: string): Promise<void> {
  await body(await csrfFetch(`/api/v1/admin/classroom/sessions/${sessionId}/start`, { method: 'POST' }))
}

export async function finishLiveClassroom(sessionId: string): Promise<void> {
  await body(await csrfFetch(`/api/v1/admin/classroom/sessions/${sessionId}/end`, { method: 'POST' }))
}

export async function listClassrooms(): Promise<{ sessions: Array<{
  id: string; publicId: string; phase: ClassroomPhase; joinCode: string; reviewExpiresAt: string
}> }> {
  return body(await fetch('/api/v1/admin/classroom/sessions', { credentials: 'same-origin', cache: 'no-store' }))
}

export async function teacherState(sessionId: string): Promise<TeacherState> {
  return body(await fetch(`/api/v1/admin/classroom/sessions/${encodeURIComponent(sessionId)}`, {
    credentials: 'same-origin', cache: 'no-store',
  }))
}

export async function teacherParticipants(
  sessionId: string,
  query: { after?: string | null; limit?: number; q?: string; requested?: boolean } = {},
): Promise<TeacherParticipantsPage> {
  const parameters = new URLSearchParams()
  if (query.after) parameters.set('after', query.after)
  parameters.set('limit', String(Math.max(1, Math.min(100, Math.floor(query.limit ?? 100)))))
  const normalizedQuery = query.q?.trim()
  if (normalizedQuery) parameters.set('q', normalizedQuery)
  if (query.requested) parameters.set('requested', 'true')
  return body(await fetch(
    `/api/v1/admin/classroom/sessions/${encodeURIComponent(sessionId)}/participants?${parameters.toString()}`,
    { credentials: 'same-origin', cache: 'no-store' },
  ))
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

export async function unlockClassroomInvite(
  publicId: string, accessCode: string, displayName?: string,
): Promise<{ sessionId: string; csrfToken: string; phase: ClassroomPhase }> {
  return body(await fetch(`/api/v1/classroom/invites/${encodeURIComponent(publicId)}/unlock`, {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accessCode, displayName: displayName || null }),
  }))
}

export async function classroomInviteState(publicId: string): Promise<ClassroomInviteState> {
  return body(await fetch(`/api/v1/classroom/invites/${encodeURIComponent(publicId)}`, {
    credentials: 'same-origin', cache: 'no-store',
  }))
}

export async function classroomInvitePhase(publicId: string): Promise<{
  sessionId: string; phase: ClassroomPhase; reviewExpiresAt: string
}> {
  return body(await fetch(`/api/v1/classroom/invites/${encodeURIComponent(publicId)}/phase`, {
    credentials: 'same-origin', cache: 'no-store',
  }))
}

export async function joinLiveClassroom(sessionId: string, csrfToken: string): Promise<void> {
  await body(await fetch(`/api/v1/classroom/sessions/${encodeURIComponent(sessionId)}/live-join`, {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csrfToken }),
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

export async function publishPin(
  sessionId: string,
  csrfToken: string,
  pin: { slideId: string; x: number; y: number; zoom: number },
): Promise<void> {
  await body(await fetch(`/api/v1/classroom/sessions/${encodeURIComponent(sessionId)}/pin`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...pin, csrfToken }),
  }))
}

export async function clearPin(sessionId: string, csrfToken: string): Promise<void> {
  await body(await fetch(`/api/v1/classroom/sessions/${encodeURIComponent(sessionId)}/pin`, {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csrfToken }),
  }))
}

export async function requestControl(sessionId: string, csrfToken: string): Promise<void> {
  await body(await fetch(
    `/api/v1/classroom/sessions/${encodeURIComponent(sessionId)}/control-request`,
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ csrfToken }),
    },
  ))
}

export async function cancelControlRequest(
  sessionId: string,
  csrfToken: string,
): Promise<void> {
  await body(await fetch(
    `/api/v1/classroom/sessions/${encodeURIComponent(sessionId)}/control-request`,
    {
      method: 'DELETE',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ csrfToken }),
    },
  ))
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

export async function revokeControl(sessionId: string): Promise<void> {
  await body(await csrfFetch(`/api/v1/admin/classroom/sessions/${sessionId}/control`, {
    method: 'DELETE',
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

export async function endActiveClassroom(): Promise<void> {
  await body(await csrfFetch('/api/v1/admin/classroom/sessions/active', {
    method: 'DELETE',
  }))
}

export async function publishTeacherViewport(
  sessionId: string,
  viewport: { slideId: string; x: number; y: number; zoom: number; zoomSpace: 'image' | 'viewport' },
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
  viewport: { slideId: string; x: number; y: number; zoom: number; zoomSpace: 'image' | 'viewport' },
): Promise<void> {
  await body(await fetch(`/api/v1/classroom/sessions/${sessionId}/presenter`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...viewport, csrfToken, leaseId }),
  }))
}

export async function publishTeacherPointer(
  sessionId: string,
  pointer: TeacherPointer,
): Promise<void> {
  await body(await csrfFetch(`/api/v1/admin/classroom/sessions/${sessionId}/pointer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(pointer),
  }))
}

export async function clearTeacherPointer(sessionId: string): Promise<void> {
  await body(await csrfFetch(`/api/v1/admin/classroom/sessions/${sessionId}/pointer`, {
    method: 'DELETE',
  }))
}

export async function publishTeachingAnnotation(
  sessionId: string,
  annotation: TeachingAnnotation,
): Promise<void> {
  await body(await csrfFetch(`/api/v1/admin/classroom/sessions/${sessionId}/annotations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(annotation),
  }))
}

export async function removeTeachingAnnotation(
  sessionId: string,
  annotationId: string,
): Promise<void> {
  await body(await csrfFetch(
    `/api/v1/admin/classroom/sessions/${sessionId}/annotations/${encodeURIComponent(annotationId)}`,
    { method: 'DELETE' },
  ))
}

export async function clearTeachingAnnotations(sessionId: string): Promise<void> {
  await body(await csrfFetch(`/api/v1/admin/classroom/sessions/${sessionId}/annotations`, {
    method: 'DELETE',
  }))
}
