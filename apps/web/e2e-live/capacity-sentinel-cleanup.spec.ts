import { expect, test } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { readFileSync, renameSync, writeFileSync } from 'node:fs'

import { csrfJson, signIn, waitForSlideDeletion } from './capacity-helpers'

const statePath = required('CAPACITY_SENTINEL_PRIVATE_STATE')

interface PrivateState {
  annotation?: {
    slideId: string
    annotationId: string
    originalMetadata: Record<string, unknown>
    version: number
    manifestVersion: number
  } | null
  shareId?: string | null
  desktopToken?: string | null
  ingestId?: string | null
  syntheticSlideId?: string | null
}

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`${name} is required`)
  return value
}

test('idempotently reconciles every locally recorded synthetic sentinel fixture', async ({ page }) => {
  await signIn(page, required('LOAD_TEST_ADMIN_USERNAME'), required('LOAD_TEST_ADMIN_PASSWORD'))
  let state: PrivateState = {}
  try { state = JSON.parse(readFileSync(statePath, 'utf8')) as PrivateState } catch { /* no fixture was created */ }
  let clean = true
  if (state.ingestId && state.desktopToken) {
    const response = await page.request.delete(`/api/v2/desktop/ingests/${encodeURIComponent(state.ingestId)}`, {
      headers: { Authorization: `Bearer ${state.desktopToken}` },
    })
    clean = (response.ok() || response.status() === 404) && clean
  }
  if (state.desktopToken) {
    const response = await page.request.post('/api/v1/desktop/credential/revoke', {
      headers: { Authorization: `Bearer ${state.desktopToken}` },
    })
    clean = (response.ok() || response.status() === 401) && clean
  }
  if (state.shareId) {
    const response = await csrfJson(page, `/api/v2/admin/shares/${encodeURIComponent(state.shareId)}`, { method: 'DELETE' })
    clean = (response.ok || response.status === 404) && clean
  }
  if (state.annotation) {
    const current = await page.evaluate(async ({ slideId, annotationId }) => {
      const [manifestResponse, itemsResponse] = await Promise.all([
        fetch(`/api/v2/admin/annotations/slides/${encodeURIComponent(slideId)}/manifest`, { credentials: 'same-origin' }),
        fetch(`/api/v2/admin/annotations/slides/${encodeURIComponent(slideId)}/items?limit=5000`, { credentials: 'same-origin' }),
      ])
      if (!manifestResponse.ok || !itemsResponse.ok) return null
      const manifest = await manifestResponse.json() as { version: number }
      const items = await itemsResponse.json() as { items: Array<{ id: string, version: number }> }
      const item = items.items.find((candidate) => candidate.id === annotationId)
      return item ? { manifestVersion: manifest.version, itemVersion: item.version } : null
    }, { slideId: state.annotation.slideId, annotationId: state.annotation.annotationId })
    const response = await csrfJson(page, `/api/v2/admin/annotations/slides/${encodeURIComponent(state.annotation.slideId)}/batch`, {
      method: 'POST',
      body: {
        mutationId: randomUUID(),
        baseVersion: current?.manifestVersion ?? state.annotation.manifestVersion,
        operations: [{
          type: 'update', id: state.annotation.annotationId,
          version: current?.itemVersion ?? state.annotation.version,
          metadata: state.annotation.originalMetadata,
        }],
      },
    })
    clean = response.ok && clean
  }
  if (state.syntheticSlideId) {
    const response = await csrfJson(page, `/api/v1/admin/slides/${encodeURIComponent(state.syntheticSlideId)}`, { method: 'DELETE' })
    clean = (response.ok || response.status === 404) && clean
    if (clean) clean = await waitForSlideDeletion(page, state.syntheticSlideId).then(() => true).catch(() => false)
  }
  if (clean) {
    const temporary = `${statePath}.tmp`
    writeFileSync(temporary, '{}\n', { mode: 0o600 })
    renameSync(temporary, statePath)
  }
  expect(clean).toBe(true)
})
