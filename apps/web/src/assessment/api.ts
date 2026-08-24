import { csrfFetch } from '../api'
import type { AssessmentDocument, AssessmentDraft, AssessmentDraftList } from './types'

async function body<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`ASSESSMENT_HTTP_${response.status}`)
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

export async function publishAssessmentDraft(id: string) {
  return body<{ id: string; checksum: string; schema: string }>(
    await csrfFetch(`/api/v2/admin/assessment/drafts/${encodeURIComponent(id)}/publish`, {
      method: 'POST',
    }),
  )
}

export async function getAssessmentMetadata(publicId: string) {
  return body<{
    publicId: string
    mode: 'practice' | 'formative' | 'quiz'
    status: string
    durationSeconds: number
    manifest: AssessmentDocument
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
