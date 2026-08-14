import { expect, test } from '@playwright/test'
import { readFileSync, renameSync, writeFileSync } from 'node:fs'
import { randomUUID } from 'node:crypto'

import { csrfJson, signIn } from './capacity-helpers'

const resultPath = required('CAPACITY_SENTINEL_RESULT')
const username = required('LOAD_TEST_ADMIN_USERNAME')
const password = required('LOAD_TEST_ADMIN_PASSWORD')
const slideId = required('CAPACITY_ANNOTATION_SLIDE_ID')
const annotationId = required('CAPACITY_ANNOTATION_ITEM_ID')
const shareTargetId = required('CAPACITY_SHARE_TARGET_ID')
const publicId = required('CAPACITY_DYNAMIC_PUBLIC_ID')
const privateStatePath = required('CAPACITY_SENTINEL_PRIVATE_STATE')

function privateState(patch: Record<string, unknown>) {
  let current: Record<string, unknown> = {}
  try { current = JSON.parse(readFileSync(privateStatePath, 'utf8')) as Record<string, unknown> } catch { /* first resource */ }
  const temporary = `${privateStatePath}.tmp`
  writeFileSync(temporary, `${JSON.stringify({ ...current, ...patch })}\n`, { mode: 0o600 })
  renameSync(temporary, privateStatePath)
}

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`${name} is required`)
  return value
}

function update(patch: Record<string, unknown>) {
  const current = JSON.parse(readFileSync(resultPath, 'utf8')) as Record<string, unknown>
  writeFileSync(resultPath, `${JSON.stringify({ ...current, ...patch }, null, 2)}\n`)
}

test('runs mutation, sharing, dynamic-viewer, and Desktop sentinels with cleanup', async ({ page }) => {
  const startedAt = new Date().toISOString()
  await signIn(page, username, password)
  const csrf = await page.evaluate(() => sessionStorage.getItem('pathlab-csrf') ?? '')
  let annotationVersion = 0
  let annotationItemVersion = 0
  let originalMetadata: Record<string, unknown> | null = null
  let shareId: string | null = null
  let desktopToken: string | null = null
  let ingestId: string | null = null
  const passed = { uploadConversion: false, annotations: false, libraryShare: false, dynamicViewer: false, desktop: false }
  let cleanup = true
  try {
    const annotation = await page.evaluate(async ({ id, itemId }) => {
      const [manifestResponse, itemsResponse] = await Promise.all([
        fetch(`/api/v2/admin/annotations/slides/${encodeURIComponent(id)}/manifest`, { credentials: 'same-origin' }),
        fetch(`/api/v2/admin/annotations/slides/${encodeURIComponent(id)}/items?limit=5000`, { credentials: 'same-origin' }),
      ])
      if (!manifestResponse.ok || !itemsResponse.ok) throw new Error('annotation sentinel unavailable')
      const manifest = await manifestResponse.json() as { version: number }
      const items = await itemsResponse.json() as { items: Array<{ id: string; version: number; metadata: Record<string, unknown> }> }
      const item = items.items.find((candidate) => candidate.id === itemId)
      if (!item) throw new Error('dedicated annotation sentinel item is missing')
      return { manifest, item }
    }, { id: slideId, itemId: annotationId })
    annotationVersion = annotation.manifest.version
    annotationItemVersion = annotation.item.version
    originalMetadata = annotation.item.metadata
    if (originalMetadata.notes !== undefined && originalMetadata.notes !== '') {
      throw new Error('dedicated annotation sentinel item does not have the clean baseline')
    }
    privateState({ annotation: { slideId, annotationId, originalMetadata, version: annotationItemVersion, manifestVersion: annotationVersion } })
    const saved = await csrfJson(page, `/api/v2/admin/annotations/slides/${encodeURIComponent(slideId)}/batch`, {
      method: 'POST',
      body: {
        mutationId: randomUUID(), baseVersion: annotationVersion,
        operations: [{ type: 'update', id: annotationId, version: annotationItemVersion,
          metadata: { ...originalMetadata, notes: `Synthetic capacity ${required('GITHUB_RUN_ID')}` } }],
      },
    })
    if (!saved.ok) throw new Error('annotation save failed')
    annotationVersion = (saved.body as { version: number }).version
    annotationItemVersion = (saved.body as { results: Array<{ version: number }> }).results[0].version
    privateState({ annotation: { slideId, annotationId, originalMetadata, version: annotationItemVersion, manifestVersion: annotationVersion } })
    const reloaded = await page.evaluate(async ({ id, itemId }) => {
      const response = await fetch(`/api/v2/admin/annotations/slides/${encodeURIComponent(id)}/items?limit=5000`, { credentials: 'same-origin' })
      if (!response.ok) return false
      const body = await response.json() as { items: Array<{ id: string; metadata: { notes?: string } }> }
      return body.items.some((item) => item.id === itemId && item.metadata.notes?.startsWith('Synthetic capacity '))
    }, { id: slideId, itemId: annotationId })
    const exported = await page.evaluate(async (id) => fetch(`/api/v2/admin/annotations/slides/${encodeURIComponent(id)}/export?format=pathlab`, { credentials: 'same-origin' }).then((r) => r.ok))
    passed.annotations = reloaded && exported

    const share = await csrfJson(page, '/api/v2/admin/shares', {
      method: 'POST', headers: { 'X-PathLab-Synthetic-Run': required('GITHUB_RUN_ID') }, body: {
      targetType: 'folder', targetId: shareTargetId, includeDescendants: false,
      autoIncludeNew: false, deidentifiedConfirmed: true,
    } })
    if (!share.ok) throw new Error('library share sentinel failed')
    shareId = (share.body as { id: string }).id
    privateState({ shareId })
    passed.libraryShare = true

    await page.goto(`/s/${encodeURIComponent(publicId)}`)
    await expect(page.locator('.osd-surface canvas').first()).toBeVisible({ timeout: 60_000 })
    passed.dynamicViewer = true

    const pairing = await page.request.post('/api/v1/desktop/pairings', { data: { deviceName: `Synthetic capacity ${required('GITHUB_RUN_ID')}` } })
    expect(pairing.ok()).toBeTruthy()
    const pairingBody = await pairing.json() as { userCode: string; deviceCode: string; deviceSecret: string }
    const approved = await page.request.post('/api/v1/desktop/pairings/approve', { headers: { 'X-CSRF-Token': csrf }, data: { userCode: pairingBody.userCode } })
    expect(approved.ok()).toBeTruthy()
    const exchanged = await page.request.post('/api/v1/desktop/pairings/exchange', { data: { deviceCode: pairingBody.deviceCode, deviceSecret: pairingBody.deviceSecret } })
    desktopToken = ((await exchanged.json()) as { accessToken: string }).accessToken
    privateState({ desktopToken })
    const createdIngest = await page.request.post('/api/v1/desktop/ome-ingests', { headers: { Authorization: `Bearer ${desktopToken}` }, data: {
      displayName: 'Synthetic cancelled ingest', artifactRevisionId: `capacity-${required('GITHUB_RUN_ID')}`,
      omeLength: 1024, omeSha256: 'a'.repeat(64), profile: 'ome-dynamic-v1', width: 1024, height: 1024, downsample: 1, jpegQuality: 75,
    } })
    expect(createdIngest.ok()).toBeTruthy()
    ingestId = ((await createdIngest.json()) as { id: string }).id
    privateState({ desktopToken, ingestId })
    passed.desktop = true
  } finally {
    if (ingestId && desktopToken) cleanup = (await page.request.delete(`/api/v2/desktop/ingests/${encodeURIComponent(ingestId)}`, { headers: { Authorization: `Bearer ${desktopToken}` } })).ok() && cleanup
    if (desktopToken) cleanup = (await page.request.post('/api/v1/desktop/credential/revoke', { headers: { Authorization: `Bearer ${desktopToken}` } })).ok() && cleanup
    if (shareId) cleanup = (await csrfJson(page, `/api/v2/admin/shares/${encodeURIComponent(shareId)}`, { method: 'DELETE' })).ok && cleanup
    if (originalMetadata) cleanup = (await csrfJson(page, `/api/v2/admin/annotations/slides/${encodeURIComponent(slideId)}/batch`, { method: 'POST', body: { mutationId: randomUUID(), baseVersion: annotationVersion, operations: [{ type: 'update', id: annotationId, version: annotationItemVersion, metadata: originalMetadata }] } })).ok && cleanup
    if (cleanup) privateState({ annotation: null, shareId: null, desktopToken: null, ingestId: null })
    const current = JSON.parse(readFileSync(resultPath, 'utf8')) as { cleanupSucceeded?: boolean, conversionSucceeded?: boolean }
    passed.uploadConversion = current.conversionSucceeded === true
    update({ schemaVersion: 1, runId: required('CAPACITY_RUN_ID'), workflowSha: required('CAPACITY_WORKFLOW_SHA'), planDigest: required('CAPACITY_PLAN_DIGEST'), startedAt, completedAt: new Date().toISOString(), fixtureBytes: Number(required('CAPACITY_FIXTURE_BYTES')), functionalSentinels: passed, cleanupSucceeded: current.cleanupSucceeded === true && cleanup, aggregateOnly: true, syntheticOnly: true })
  }
  expect(Object.values(passed).every(Boolean)).toBe(true)
  expect(cleanup).toBe(true)
})
